#!/usr/bin/env node
// Compares the Copilot Studio agents cloned in a folder: what most of them do (a pattern), who is off it, what only
// one has, the team's rules not met — and makes the map (one HTML page that opens with no internet), the workbook
// (.xlsx) and the cast file (what people said, what was decided). No model, no install, no network: Node 18 or later.
//
//   node build.mjs <agents-folder> --check [--profile <p.cast.yaml>] [--lang en|pt]     only compare: nothing is written
//   node build.mjs <agents-folder> [--profile <p.cast.yaml>] [--html] [--xlsx] [--lesson] [--all] [--lang en|pt] [--out <folder>]
//   node build.mjs <agents-folder> --facts [--out <folder>]                         only the facts, for a model: <id>.facts.json
//   node build.mjs <agents-folder> --from <edited.xlsx> [--take <key,key…|all>] [--out <folder>]
//                                  what was filled in the workbook (Declared, the Decision column): listed with a key each,
//                                  and with --take written to the cast file
//
// With no --html/--xlsx/--lesson it makes the map. Files go in --out (or beside the folder), named by the folder:
// <id>.html, <id>.xlsx, <id>.lesson.html (a chalk-talk lesson), and <id>.cast.yaml, kept up to date (read again on every
// run). Exit codes: 0 done (what to look at is printed, and is not an error); 1 the profile or the cast file breaks its
// format (each problem with its line), or no agent in the folder; 2 bad arguments; 3 made, but the lesson's reviewer
// found something to fix. The outputs hold the client's data: keep them in the client's environment. The lesson's
// review uses Chrome, Chromium or Edge when there is one.
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from './browser.mjs'
import { agentsIn, applyChanges, compare, DEFAULT_PROFILE, extractAgent, fromSheets, knownKinds, labelOf, lessonOf, problemText, readCast, readProfile, reviewCast, validateScene, workbookFile, workbookOf, writeCast } from './engine.mjs'
import { readXlsx } from './read-xlsx.mjs'
import { fill, inline } from './page.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const valued = new Set(['--lang', '--out', '--profile', '--from', '--take'])
const flags = new Set(['--check', '--html', '--xlsx', '--lesson', '--all', '--facts', ...valued])
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const usage = `usage: node build.mjs <agents-folder> --check [--profile <p.cast.yaml>] [--lang en|pt]
       node build.mjs <agents-folder> [--profile <p.cast.yaml>] [--html] [--xlsx] [--lesson] [--all] [--lang en|pt] [--out <folder>]
       node build.mjs <agents-folder> --facts [--out <folder>]
       node build.mjs <agents-folder> --from <edited.xlsx> [--take <key,key…|all>] [--out <folder>]`
const lang = option('--lang') ?? 'en'
const fail = (msg) => {
  console.error(`${msg}\n${usage}`)
  process.exit(2)
}
if (args.length !== 1 || !existsSync(args[0]) || !statSync(args[0]).isDirectory()) fail('✗ one folder with the cloned agents')
const unknown = argv.find((a) => a.startsWith('--') && !flags.has(a))
if (unknown) fail(`✗ unknown option ${unknown}`)
if (!['en', 'pt'].includes(lang)) fail('✗ --lang is en or pt')
for (const v of valued) if (argv.includes(v) && !option(v)) fail(`✗ ${v} needs a value`)
if (argv.includes('--take') && !argv.includes('--from')) fail('✗ --take goes with --from')

const T = {
  en: {
    found: (n, o, s) => `✓ ${n} in the cast: ${o} orchestrator${o === 1 ? '' : 's'}, ${s} specialist${s === 1 ? '' : 's'}`,
    result: (p, off, solos) => `✓ ${p} patterns · ${off} off a pattern · ${solos} only one has`,
    look: 'to look at', nothing: '✓ nothing to look at', facts: (f) => `✓ facts     ${f}`,
    changes: (n) => (n ? `${n} change${n === 1 ? '' : 's'} in the workbook (take them with --take <key,…> or --take all):` : '✓ the workbook changes nothing'),
    took: (n, f) => `✓ took ${n} change${n === 1 ? '' : 's'} into ${f}`, unknownKey: (k) => `✗ no change with the key «${k}»`,
    declared: 'declared', decision: 'decision', add: '+', set: '~', remove: '−', accepted: 'accepted', rejected: 'rejected', platform: 'platform', specialist: 'specialist', orchestrator: 'orchestrator', none: (f) => `✗ ${f} has no folder with agent.mcs.yml`, privacy: '• the files hold the client’s data: keep them in the client’s environment',
  },
  pt: {
    found: (n, o, s) => `✓ ${n} no elenco: ${o} ${o === 1 ? 'orquestrador' : 'orquestradores'}, ${s} ${s === 1 ? 'especialista' : 'especialistas'}`,
    result: (p, off, solos) => `✓ ${p} padrões · ${off} fora do padrão · ${solos} só um tem`,
    look: 'para olhar', nothing: '✓ nada para olhar', facts: (f) => `✓ fatos     ${f}`,
    changes: (n) => (n ? `${n} ${n === 1 ? 'mudança' : 'mudanças'} na planilha (aceite com --take <chave,…> ou --take all):` : '✓ a planilha não muda nada'),
    took: (n, f) => `✓ ${n} ${n === 1 ? 'mudança gravada' : 'mudanças gravadas'} em ${f}`, unknownKey: (k) => `✗ nenhuma mudança com a chave «${k}»`,
    declared: 'declarado', decision: 'decisão', add: '+', set: '~', remove: '−', accepted: 'aceito', rejected: 'rejeitado', platform: 'plataforma', specialist: 'especialista', orchestrator: 'orquestrador', none: (f) => `✗ ${f} não tem nenhuma pasta com agent.mcs.yml`, privacy: '• os arquivos têm dados do cliente: deixe-os no ambiente dele',
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
const castFile = join(out, `${id}.cast.yaml`)
const castText = existsSync(castFile) ? readFileSync(castFile, 'utf8') : undefined
const cast = castText !== undefined ? read(castFile, readCast).cast : { ...(profile.name ? { name: profile.name } : {}), agents: [], blocks: [], declared: [], decisions: [] }

// ---- the way back: an edited workbook as the changes it proposes ----
if (argv.includes('--from')) {
  const edited = fromSheets(cast, readXlsx(readFileSync(resolve(option('--from')))), Object.fromEntries(profile.types.map((t) => [t.id, t.name])))
  if (edited.problems.length) {
    for (const p of edited.problems) console.error(`✗ ${basename(option('--from'))}: ${p}`)
    process.exit(1)
  }
  const line = (c) => {
    const x = c.after ?? c.before
    // a key with no kind («kpi») is something only people know: declared:<key>
    if (c.kind === 'declared') return `${T[c.op]} ${T.declared}  ${x.agent} · ${labelOf(x.key.includes(':') ? x.key : `declared:${x.key}`, lang)}${x.value ? ` = «${x.value}»` : ''}${x.source ? ` (${x.source})` : ''}`
    return `${T[c.op]} ${T.decision}  ${labelOf(x.key, lang)}: ${T[x.status]} (${T[x.scope]})${x.why ? ` — ${x.why}` : ''}`
  }
  const take = option('--take')
  if (!take) {
    console.log(T.changes(edited.changes.length))
    for (const c of edited.changes) console.log(`  ${c.key}  ${line(c)}`)
    process.exit(0)
  }
  const keys = take === 'all' ? edited.changes.map((c) => c.key) : take.split(',').map((k) => k.trim()).filter(Boolean)
  const missing = keys.find((k) => !edited.changes.some((c) => c.key === k))
  if (missing) {
    console.error(T.unknownKey(missing))
    process.exit(2)
  }
  mkdirSync(out, { recursive: true })
  writeFileSync(castFile, writeCast(applyChanges(cast, edited.changes, keys), castText))
  console.log(T.took(keys.length, basename(castFile)))
  process.exit(0)
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
  writeFileSync(file, `${JSON.stringify({ format: 'cast-list/facts-v1', agents: found }, null, 2)}\n`)
  console.log(T.facts(file))
  console.log(T.privacy)
  process.exit(0)
}
const result = compare(found, profile, cast)
const looks = reviewCast(result)
const roles = Object.values(result.roles)
console.log(T.found(found.length, roles.filter((r) => r === 'orchestrator').length, roles.filter((r) => r === 'specialist').length))
console.log(T.result(result.patterns.length, new Set(result.offPattern.map((o) => o.agent)).size, looks.filter((l) => l.key === 'solo').length))
if (looks.length) for (const l of looks) console.log(`! ${T.look}: ${l[lang]}`)
else console.log(T.nothing)
if (argv.includes('--check')) process.exit(0)

const all = argv.includes('--all')
const want = { html: all || argv.includes('--html'), xlsx: all || argv.includes('--xlsx'), lesson: all || argv.includes('--lesson') }
if (!want.xlsx && !want.lesson) want.html = true
mkdirSync(out, { recursive: true })
// the cast file keeps this run's roles and blocks of text (so a block keeps its id across small edits), under what
// people wrote in it; the types a person gave an agent stay, the ones the profile works out are not written
const givenTypes = Object.fromEntries(cast.agents.filter((a) => a.types?.length).map((a) => [a.id, a.types]))
const kept = { ...cast, agents: result.agents.map((a) => ({ id: a.id, role: a.role, ...(givenTypes[a.id] ? { types: givenTypes[a.id] } : {}) })), blocks: result.blocks.map((b) => ({ id: b.id, text: b.text })) }
const castYaml = writeCast(kept, castText)
writeFileSync(castFile, castYaml)
console.log(`✓ cast      ${castFile}`)
if (want.html) {
  const page = join(out, `${id}.html`)
  const map = readFileSync(join(here, '../assets/map.html'), 'utf8')
  writeFileSync(page, fill(map, { CAST: inline({ id, lang, result, looks, cast: kept, castYaml, focusAreas: profile.focusAreas, threshold: profile.threshold }) }))
  console.log(`✓ map       ${page}`)
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
