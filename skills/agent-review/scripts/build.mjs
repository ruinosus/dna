#!/usr/bin/env node
// Compares the Copilot Studio agents cloned in a folder: what most of them do (a pattern), who is off it, what only
// one has, the team's rules not met — and makes the map (one HTML page that opens with no internet), the workbook
// (.xlsx) and the review file (what people said, what was decided). No model, no install, no network: Node 18 or later.
//
//   node build.mjs <agents-folder> --check [--profile <team>.standard.yaml] [--lang en|pt]     only compare: nothing is written
//   node build.mjs <agents-folder> [--profile <team>.standard.yaml] [--html] [--xlsx] [--lesson] [--team] [--topology] [--diagrams] [--all] [--lang en|pt] [--out <folder>]
//   node build.mjs <agents-folder> --facts [--out <folder>]                         only the facts, for a model: <id>.facts.json
//   node build.mjs <agents-folder> --from <edited.xlsx> [--take <key,key…|all>] [--out <folder>]
//                                  what was filled in the workbook (Declared, the Decision column): listed with a key each,
//                                  and with --take written to the review file
//   node build.mjs <agents-folder> --declared <table.csv|.xlsx> [--declared <another>] [--agent-column <title>] [--take <key,…|all>]
//                                  what a spreadsheet says about the agents (the team's, the admin center's inventory): each
//                                  column becomes a declared fact, listed with a key, and with --take written to the review file
//   … --evals <folder>              the exports of Copilot Studio's Evaluate tab («Evaluate <agent> <date>.csv»): who
//                                  passed how many, by method — the counts only, never what was asked or answered
//   … --telemetry <export.csv|.xlsx> [--telemetry-days <n>]   what fired, from Application Insights (references/telemetry.md):
//                                  the events in the YAML that did not fire, and who has no line at all
//
// With no --html/--xlsx/--lesson/--team/--topology/--diagrams it makes the map. Files go in --out (or beside the folder), named by the folder:
// <id>.html, <id>.xlsx, <id>.lesson.html (a visual-explainer lesson), <id>.team.html (the agents as a team), <id>.topology.html (who calls whom),
// <id>.diagrams.md with <id>.diagrams/*.mmd (what was read, in plain Mermaid) and
// <id>.review.yaml, kept up to date (read again on every
// run). Exit codes: 0 done (what to look at is printed, and is not an error); 1 the profile or the review file breaks its
// format (each problem with its line), or no agent in the folder; 2 bad arguments; 3 made, but the lesson's reviewer
// found something to fix. The outputs hold the client's data: keep them in the client's environment. The lesson's
// review uses Chrome, Chromium or Edge when there is one.
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from './browser.mjs'
import { CAST_FORMAT, CAST_KIND, DNA_API, PROFILE_FORMAT, PROFILE_KIND, upgradeHeader, agentsIn, applyChanges, compare, declaredFrom, DEFAULT_PROFILE, evalsFrom, extractAgent, firedFrom, fromSheets, groupLooks, playbillOf, stageOf, mergeDeclared, knownKinds, labelOf, lessonOf, problemText, readCast, readCsv, readProfile, reviewCast, diagramsDoc, diagramsOf, validateScene, withEvals, workbookFile, workbookOf, writeCast } from './engine.mjs'
import { readXlsx } from './read-xlsx.mjs'
import { fill, inline } from './page.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const valued = new Set(['--lang', '--out', '--profile', '--from', '--take', '--declared', '--agent-column', '--telemetry', '--telemetry-days', '--evals'])
const flags = new Set(['--check', '--html', '--xlsx', '--lesson', '--team', '--topology', '--playbill', '--plot', '--diagrams', '--all', '--facts', '--upgrade', '--write', ...valued])
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const options = (name) => argv.flatMap((a, i) => (a === name && argv[i + 1] ? [argv[i + 1]] : []))
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const usage = `usage: node build.mjs <agents-folder> --check [--profile <team>.standard.yaml] [--lang en|pt]
       node build.mjs <agents-folder> [--profile <team>.standard.yaml] [--html] [--xlsx] [--lesson] [--team] [--topology] [--diagrams] [--all] [--lang en|pt] [--out <folder>]
       node build.mjs <agents-folder> --facts [--out <folder>]
       node build.mjs <agents-folder> --from <edited.xlsx> [--take <key,key…|all>] [--out <folder>]
       node build.mjs <agents-folder> --declared <table.csv|.xlsx> [--agent-column <title>] [--take <key,key…|all>] [--out <folder>]
       … [--telemetry <export.csv|.xlsx>] [--telemetry-days <n>] [--evals <folder>]
       node build.mjs <file>.yaml --upgrade [--write]    a profile or a review file of before, with DNA's header`
const lang = option('--lang') ?? 'en'
const fail = (msg) => {
  console.error(`${msg}\n${usage}`)
  process.exit(2)
}
// ---- --upgrade: a profile or a review file of before (format: cast-list/…) with DNA's header, the rest as it is ----
if (argv.includes('--upgrade')) {
  if (args.length !== 1 || !existsSync(args[0]) || !statSync(args[0]).isFile()) fail('✗ one profile or review file (.cast.yaml) to upgrade')
  const file = resolve(args[0])
  const text = readFileSync(file, 'utf8')
  const pt = lang === 'pt'
  const [format, kind, reader] = /^format:\s*["']?cast-list\/profile-v1/m.test(text) ? [PROFILE_FORMAT, PROFILE_KIND, readProfile] : [CAST_FORMAT, CAST_KIND, readCast]
  const up = upgradeHeader(text, format, kind)
  if (up === undefined) {
    console.log(/^apiVersion:/m.test(text) ? (pt ? `✓ ${basename(file)} já tem o cabeçalho do DNA` : `✓ ${basename(file)} already has DNA's header`) : (pt ? `✗ ${basename(file)} não é um perfil nem um arquivo de decisões do agent-review` : `✗ ${basename(file)} is neither an agent-review profile nor a review file`))
    process.exit(/^apiVersion:/m.test(text) ? 0 : 1)
  }
  const same = (r) => JSON.stringify({ ...(r.profile ?? r.cast), name: undefined })
  if (same(reader(up)) !== same(reader(text)) || reader(up).problems.length !== reader(text).problems.length) {
    console.error(pt ? `✗ ${basename(file)}: depois do cabeçalho novo, o arquivo não se lê igual; nada escrito` : `✗ ${basename(file)}: with the new header the file does not read the same; nothing written`)
    process.exit(1)
  }
  if (!argv.includes('--write')) {
    process.stdout.write(up)
    process.exit(0)
  }
  writeFileSync(file, up)
  console.log(pt ? `✓ ${basename(file)}: agora com apiVersion ${DNA_API} e kind ${kind}; o resto como estava` : `✓ ${basename(file)}: now apiVersion ${DNA_API} and kind ${kind}; the rest as it was`)
  process.exit(0)
}
if (args.length !== 1 || !existsSync(args[0]) || !statSync(args[0]).isDirectory()) fail('✗ one folder with the cloned agents')
const unknown = argv.find((a) => a.startsWith('--') && !flags.has(a))
if (unknown) fail(`✗ unknown option ${unknown}`)
if (!['en', 'pt'].includes(lang)) fail('✗ --lang is en or pt')
for (const v of valued) if (argv.includes(v) && !option(v)) fail(`✗ ${v} needs a value`)
if (argv.includes('--take') && !argv.includes('--from') && !argv.includes('--declared')) fail('✗ --take goes with --from or --declared')
if (argv.includes('--from') && argv.includes('--declared')) fail('✗ --from or --declared, one at a time')
for (const f of [...options('--declared'), ...options('--telemetry')]) if (!existsSync(f) || !/\.(csv|xlsx)$/i.test(f)) fail(`✗ ${f}: a .csv or an .xlsx that is there`)
if (option('--evals') && !(existsSync(option('--evals')) && statSync(option('--evals')).isDirectory())) fail(`✗ ${option('--evals')}: a folder with the exports of the Evaluate tab`)
const days = Number(option('--telemetry-days') ?? 30)
if (!Number.isInteger(days) || days < 1) fail('✗ --telemetry-days is a whole number of days')

const T = {
  en: {
    found: (n, o, s) => `✓ ${n} agents: ${o} orchestrator${o === 1 ? '' : 's'}, ${s} specialist${s === 1 ? '' : 's'}`,
    result: (p, off, solos) => `✓ ${p} patterns · ${off} off a pattern · ${solos} only one has`,
    look: 'to look at', nothing: '✓ nothing to look at', facts: (f) => `✓ facts     ${f}`,
    changes: (n) => (n ? `${n} change${n === 1 ? '' : 's'} in the workbook (take them with --take <key,…> or --take all):` : '✓ the workbook changes nothing'),
    took: (n, f) => `✓ took ${n} change${n === 1 ? '' : 's'} into ${f}`, unknownKey: (k) => `✗ no change with the key «${k}»`,
    declared: 'declared', decision: 'decision', add: '+', set: '~', remove: '−', accepted: 'accepted', rejected: 'rejected', platform: 'platform', specialist: 'specialist', orchestrator: 'orchestrator', none: (f) => `✗ ${f} has no folder with agent.mcs.yml`, privacy: '• the files hold the client’s data: keep them in the client’s environment',
    noColumn: (f, cols) => `✗ ${f}: no column names the agents of the folder (by schema name, folder or display name): say which with --agent-column "<title>" (columns: ${cols.join(', ')})`,
    tie: (f, cols) => `✗ ${f}: the columns ${cols.map((c) => `«${c}»`).join(' and ')} name the agents in different ways: say which with --agent-column "<title>"`,
    noHeader: (f, cols) => `✗ ${f}: no column with that title (columns: ${cols.join(', ')})`,
    noEvent: (f, cols) => `✗ ${f}: no column of the event («evento», «event» or «name»; columns: ${cols.join(', ')})`,
    unmatched: (n, f, list) => `• ${f}: ${n} ${n === 1 ? 'row names' : 'rows name'} nobody in the folder: ${list}`, line: 'line',
    telemetry: (f, n, d) => `✓ telemetry ${f}: ${n} ${n === 1 ? 'row' : 'rows'} of the folder's agents, ${d} days`,
    evals: (d, n, a) => `✓ evals     ${d}: ${n} ${n === 1 ? 'evaluation' : 'evaluations'} of ${a} in the folder (counts only)`,
    evalUnknown: (f, why) => `• evals     ${f}: ${why === 'testset' ? 'a test set (prompts and expected answers) with no results yet: import it in the Evaluate tab, run it and export the results' : why === 'who' ? 'its name says nobody in the folder («Evaluate <name> <date>.csv»)' : 'no result_1 column: not an export of the Evaluate tab'}`,
  },
  pt: {
    found: (n, o, s) => `✓ ${n} agentes: ${o} ${o === 1 ? 'orquestrador' : 'orquestradores'}, ${s} ${s === 1 ? 'especialista' : 'especialistas'}`,
    result: (p, off, solos) => `✓ ${p} padrões · ${off} fora do padrão · ${solos} só um tem`,
    look: 'para olhar', nothing: '✓ nada para olhar', facts: (f) => `✓ fatos     ${f}`,
    changes: (n) => (n ? `${n} ${n === 1 ? 'mudança' : 'mudanças'} na planilha (aceite com --take <chave,…> ou --take all):` : '✓ a planilha não muda nada'),
    took: (n, f) => `✓ ${n} ${n === 1 ? 'mudança gravada' : 'mudanças gravadas'} em ${f}`, unknownKey: (k) => `✗ nenhuma mudança com a chave «${k}»`,
    declared: 'declarado', decision: 'decisão', add: '+', set: '~', remove: '−', accepted: 'aceito', rejected: 'rejeitado', platform: 'plataforma', specialist: 'especialista', orchestrator: 'orquestrador', none: (f) => `✗ ${f} não tem nenhuma pasta com agent.mcs.yml`, privacy: '• os arquivos têm dados do cliente: deixe-os no ambiente dele',
    noColumn: (f, cols) => `✗ ${f}: nenhuma coluna cita os agentes da pasta (pelo nome de esquema, pela pasta ou pelo nome de exibição): diga qual com --agent-column "<título>" (colunas: ${cols.join(', ')})`,
    tie: (f, cols) => `✗ ${f}: as colunas ${cols.map((c) => `«${c}»`).join(' e ')} citam os agentes de jeitos diferentes: diga qual com --agent-column "<título>"`,
    noHeader: (f, cols) => `✗ ${f}: nenhuma coluna com esse título (colunas: ${cols.join(', ')})`,
    noEvent: (f, cols) => `✗ ${f}: nenhuma coluna do evento («evento», «event» ou «name»; colunas: ${cols.join(', ')})`,
    unmatched: (n, f, list) => `• ${f}: ${n} ${n === 1 ? 'linha não cita' : 'linhas não citam'} ninguém da pasta: ${list}`, line: 'linha',
    telemetry: (f, n, d) => `✓ telemetria ${f}: ${n} ${n === 1 ? 'linha' : 'linhas'} dos agentes da pasta, ${d} dias`,
    evals: (d, n, a) => `✓ avaliações ${d}: ${n} ${n === 1 ? 'avaliação' : 'avaliações'} de ${a} da pasta (só as contagens)`,
    evalUnknown: (f, why) => `• avaliações ${f}: ${why === 'testset' ? 'um conjunto de teste (perguntas e respostas esperadas), ainda sem resultado: importe na aba Evaluate, rode e exporte o resultado' : why === 'who' ? 'o nome não cita ninguém da pasta («Evaluate <nome> <data>.csv»)' : 'sem a coluna result_1: não é uma exportação da aba Evaluate'}`,
  },
}[lang]

const folder = resolve(args[0])
const id = basename(folder)
const read = (file, reader) => {
  const r = reader(readFileSync(file, 'utf8'))
  if (r.problems.length) {
    for (const p of r.problems) console.error(`✗ ${basename(file)}:${p.line}: ${problemText(p, lang)}`)
    process.exit(1)
  }
  return r
}
const profile = option('--profile') ? read(resolve(option('--profile')), readProfile).profile : DEFAULT_PROFILE
const out = resolve(option('--out') ?? dirname(folder))
// the review file (what people said, what was decided): <id>.review.yaml; one of before, <id>.review.yaml, takes its
// name the first time — nothing in it is lost
const castFile = join(out, `${id}.review.yaml`)
const before = join(out, `${id}.review.yaml`)
if (!existsSync(castFile) && existsSync(before)) {
  renameSync(before, castFile)
  console.log(lang === 'pt' ? `• ${id}.review.yaml agora se chama ${id}.review.yaml` : `• ${id}.review.yaml is now ${id}.review.yaml`)
}
const castText = existsSync(castFile) ? readFileSync(castFile, 'utf8') : undefined
const cast = castText !== undefined ? read(castFile, readCast).cast : { ...(profile.name ? { name: profile.name } : {}), agents: [], blocks: [], declared: [], decisions: [] }

// a table from outside: the sheets of an .xlsx, or a .csv
const tablesOf = (file) => (/\.xlsx$/i.test(file) ? readXlsx(readFileSync(file)) : [readCsv(readFileSync(file, 'utf8'), '')])
const tableProblem = (file, p) => {
  console.error(p.problem === 'tie' ? T.tie(basename(file), p.titles) : p.problem === 'header' ? T.noHeader(basename(file), p.titles) : p.problem === 'event' ? T.noEvent(basename(file), p.titles) : T.noColumn(basename(file), p.titles))
  process.exit(1)
}
const line = (c) => {
  const x = c.after ?? c.before
  if (c.kind === 'declared') return `${T[c.op]} ${T.declared}  ${x.agent} · ${labelOf(x.key.includes(':') ? x.key : `declared:${x.key}`, lang)}${x.value ? ` = «${x.value}»` : ''}${x.source ? ` (${x.source})` : ''}`
  return `${T[c.op]} ${T.decision}  ${labelOf(x.key, lang)}: ${T[x.status]} (${T[x.scope]})${x.why ? ` — ${x.why}` : ''}`
}
// what changes the review file: listed, each with its key, and with --take written
const proposeOrTake = (changes) => {
  const take = option('--take')
  if (!take) {
    console.log(T.changes(changes.length))
    for (const c of changes) console.log(`  ${c.key}  ${line(c)}`)
    process.exit(0)
  }
  const keys = take === 'all' ? changes.map((c) => c.key) : take.split(',').map((k) => k.trim()).filter(Boolean)
  const missing = keys.find((k) => !changes.some((c) => c.key === k))
  if (missing) {
    console.error(T.unknownKey(missing))
    process.exit(2)
  }
  mkdirSync(out, { recursive: true })
  writeFileSync(castFile, writeCast(applyChanges(cast, changes, keys), castText))
  console.log(T.took(keys.length, basename(castFile)))
  process.exit(0)
}
// ---- the way back: an edited workbook as the changes it proposes ----
if (argv.includes('--from')) {
  const edited = fromSheets(cast, readXlsx(readFileSync(resolve(option('--from')))), Object.fromEntries(profile.types.map((t) => [t.id, t.name])))
  if (edited.problems.length) {
    for (const p of edited.problems) console.error(`✗ ${basename(option('--from'))}: ${p}`)
    process.exit(1)
  }
  proposeOrTake(edited.changes)
}

// the schema's kinds, to tell a made-up one; without the schema every kind is taken as real
const schema = join(here, '../vendor/microsoft/reference/bot.schema.yaml-authoring.json')
const kinds = existsSync(schema) ? knownKinds(JSON.parse(readFileSync(schema, 'utf8'))) : undefined
const found = agentsIn(folder).map((a) => extractAgent(a.id, a.files, kinds))
if (!found.length) {
  console.error(T.none(args[0]))
  process.exit(1)
}
// only the facts, for a model to read: what was seen in each agent, with the file and line
if (argv.includes('--facts')) {
  mkdirSync(out, { recursive: true })
  const file = join(out, `${id}.facts.json`)
  writeFileSync(file, `${JSON.stringify({ format: 'agent-review/facts-v1', agents: found }, null, 2)}\n`)
  console.log(T.facts(file))
  console.log(T.privacy)
  process.exit(0)
}
if (argv.includes('--declared')) {
  const changes = []
  for (const file of options('--declared')) {
    const sheets = tablesOf(file)
    let read = 0
    let problem
    for (const t of sheets) {
      const r = declaredFrom(t, found, cast, { file: basename(file), lang, agentColumn: option('--agent-column') })
      if (r.problem) {
        problem ??= r.problem
        continue
      }
      read++
      changes.push(...r.changes)
      if (r.unmatched.length) console.log(T.unmatched(r.unmatched.length, basename(file), `${r.unmatched.slice(0, 5).map((u) => `${T.line} ${u.line} («${u.value}»)`).join(', ')}${r.unmatched.length > 5 ? ', …' : ''}`))
    }
    if (!read) tableProblem(file, problem)
  }
  proposeOrTake(mergeDeclared(changes))
}
let fired
if (option('--telemetry')) {
  const file = option('--telemetry')
  let problem
  for (const t of tablesOf(file)) {
    const r = firedFrom(t, found, { file: basename(file), days, agentColumn: option('--agent-column') })
    if ('problem' in r) problem ??= r.problem
    else {
      fired = r
      break
    }
  }
  if (!fired) tableProblem(file, problem)
}
// the evaluations of the Evaluate tab: the counts only, and eval:run for who has one (a rule «has: eval:*»)
let evalSets
if (option('--evals')) {
  const dir = option('--evals')
  const names = readdirSync(dir).filter((f) => /\.csv$/i.test(f)).sort()
  const ev = evalsFrom(names.map((name) => ({ name: `${basename(dir)}/${name}`, table: readCsv(readFileSync(join(dir, name), 'utf8'), name) })), found)
  evalSets = ev.sets
  console.log(T.evals(dir, ev.sets.length, new Set(ev.sets.map((s) => s.agent)).size))
  for (const u of ev.unknown) console.log(T.evalUnknown(u.file, u.why))
}
const result = compare(evalSets ? withEvals(found, evalSets) : found, profile, cast, fired)
const looks = reviewCast(result)
const roles = Object.values(result.roles)
console.log(T.found(found.length, roles.filter((r) => r === 'orchestrator').length, roles.filter((r) => r === 'specialist').length))
console.log(T.result(result.patterns.length, new Set(result.offPattern.map((o) => o.agent)).size, looks.filter((l) => l.key === 'solo').length))
// in groups, each with how many; every look keeps its own «! to look at» line
if (looks.length) for (const g of groupLooks(looks)) {
  console.log(`▸ ${g[lang]} · ${g.looks.length}`)
  for (const { look } of g.looks) console.log(`! ${T.look}: ${look[lang]}`)
}
else console.log(T.nothing)
if (argv.includes('--check')) process.exit(0)

const all = argv.includes('--all')
// --team and --topology (--playbill and --plot, their names of before, still work)
const want = { html: all || argv.includes('--html'), xlsx: all || argv.includes('--xlsx'), lesson: all || argv.includes('--lesson'), playbill: all || argv.includes('--team') || argv.includes('--playbill'), plot: all || argv.includes('--topology') || argv.includes('--plot'), diagrams: all || argv.includes('--diagrams') }
if (!want.xlsx && !want.lesson && !want.playbill && !want.plot && !want.diagrams) want.html = true
mkdirSync(out, { recursive: true })
// the review file keeps this run's roles and blocks of text (so a block keeps its id across small edits), under what
// people wrote in it; the types a person gave an agent stay, the ones the profile works out are not written
const givenTypes = Object.fromEntries(cast.agents.filter((a) => a.types?.length).map((a) => [a.id, a.types]))
const kept = { ...cast, agents: result.agents.map((a) => ({ id: a.id, role: a.role, ...(givenTypes[a.id] ? { types: givenTypes[a.id] } : {}) })), blocks: result.blocks.map((b) => ({ id: b.id, text: b.text })) }
const castYaml = writeCast(kept, castText)
writeFileSync(castFile, castYaml)
console.log(`✓ review    ${castFile}`)
if (want.html) {
  const page = join(out, `${id}.html`)
  const map = readFileSync(join(here, '../assets/map.html'), 'utf8')
  writeFileSync(page, fill(map, { CAST: inline({ id, lang, result, looks, cast: kept, castYaml, focusAreas: profile.focusAreas, threshold: profile.threshold, ...(want.playbill ? { playbill: `${id}.team.html` } : {}), ...(want.plot ? { plot: `${id}.topology.html` } : {}) }) }))
  console.log(`✓ map       ${page}`)
}
if (want.playbill) {
  const page = join(out, `${id}.team.html`)
  const playbill = playbillOf(result, looks, found, kept, profile.rules, fired, evalSets)
  writeFileSync(page, fill(readFileSync(join(here, '../assets/playbill.html'), 'utf8'), { CAST: inline({ id, lang, playbill, ...(want.html ? { map: `${id}.html` } : {}) }) }))
  console.log(`✓ team      ${page}`)
}
if (want.plot) {
  const page = join(out, `${id}.topology.html`)
  const stage = stageOf(result, looks, found, fired)
  writeFileSync(page, fill(readFileSync(join(here, '../assets/plot.html'), 'utf8'), { CAST: inline({ id, lang, stage, ...(want.html ? { map: `${id}.html` } : {}), ...(want.playbill ? { playbill: `${id}.team.html` } : {}) }) }))
  console.log(`✓ topology  ${page}`)
}
if (want.diagrams) {
  const doc = join(out, `${id}.diagrams.md`)
  const dir = join(out, `${id}.diagrams`)
  const diagrams = diagramsOf(stageOf(result, looks, found, fired), result, lang)
  mkdirSync(dir, { recursive: true })
  for (const d of diagrams) writeFileSync(join(dir, `${d.name}.mmd`), d.mermaid)
  writeFileSync(doc, diagramsDoc(id, diagrams, result, looks, lang))
  console.log(`✓ diagrams  ${doc} (${diagrams.length} in ${dir})`)
}
if (want.xlsx) {
  const book = join(out, `${id}.xlsx`)
  writeFileSync(book, workbookFile(workbookOf(result, looks, kept, lang)))
  console.log(`✓ workbook  ${book}`)
}
let exit = 0
if (want.lesson) {
  const page = join(out, `${id}.lesson.html`)
  writeFileSync(page, fill(readFileSync(join(here, '../assets/lesson.html'), 'utf8'), { RECIPE: inline(validateScene(lessonOf(result, looks, lang))) }))
  console.log(`✓ lesson    ${page}`)
  const r = await runPage(page, 'review')
  if (r === null) console.log('• review    no Chrome, Chromium or Edge here: the lesson checks itself when opened')
  else if (r.error) console.log(`✗ review    not checked: ${r.error}`)
  else if (!r.problems.length) console.log(`✓ review    ${r.combos} ${r.combos === 1 ? 'setting' : 'settings'}: nothing off the paper, no text over text`)
  else {
    for (const p of r.problems) console.log(`! review    ${p}`)
    exit = 3
  }
}
console.log(T.privacy)
process.exit(exit)
