#!/usr/bin/env node
// Checks a way of working (<id>.way.yaml) and makes what is asked of it: the map (an HTML page that opens with no
// internet), the workbook (.xlsx) and an explainer drawn with visual-explainer that walks it drawing. And the way back: a workbook someone
// changed is read as the changes it proposes, one per line, and only the ones taken go into the .way.yaml.
//
//   node build.mjs <id>.way.yaml --check [--lang en|pt]                       only check it: nothing is written
//   node build.mjs <id>.way.yaml [--html] [--xlsx] [--explainer] [--all] [--lang en|pt] [--out <folder>]
//   node build.mjs <id>.way.yaml --from <edited.xlsx> [--lang en|pt]           the changes, each with its key
//   node build.mjs <id>.way.yaml --from <edited.xlsx> --take <key,key…|all>    writes the ones taken into the .way.yaml
//
// With no --html/--xlsx/--explainer it makes the map. Files go beside the .way.yaml (or in --out), named by its id.
// Exit codes: 0 done (what to look at is printed, and is not an error); 1 the file breaks the format (each problem with
// its line; nothing written); 2 bad arguments; 3 made, but the explainer's reviewer found something to fix. Needs Node 18
// or later and nothing else; the explainer's review uses Chrome, Chromium or Edge when there is one.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from './browser.mjs'
import { fill, inline } from './page.mjs'
import { applyRows, checkWay, DNA, DNA_API, DNA_KIND, exportWay, fromSheets, itemName, problemText, readWay, reviewWay, show, STAGE_DOOR, upgradeHeader, validateScene, wayDiff, wayLesson, workbookOf, xlsx } from './engine.mjs'
import { readXlsx } from './read-xlsx.mjs'
import { blueprintOf, drillOf, simOf } from './lenses.mjs'

const here = dirname(fileURLToPath(import.meta.url))
// DNA 2.2.0: --lesson, the explainer's flag before, still works.
const argv = process.argv.slice(2).map((a) => (a === '--lesson' ? '--explainer' : a))
const valued = new Set(['--lang', '--out', '--from', '--take', '--lens', '--gate'])
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const flags = new Set(['--check', '--json', '--html', '--xlsx', '--explainer', '--all', '--write', '--force', '--upgrade', ...valued])
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const usage = `usage: node build.mjs <id>.way.yaml --check [--json] [--lang en|pt]
       node build.mjs <id>.way.yaml [--html] [--xlsx] [--explainer] [--all] [--lang en|pt] [--out <folder>]
       node build.mjs <id>.way.yaml --from <edited.xlsx> [--take <key,key…|all>]
       node build.mjs <id>.way.yaml --lens sim|blueprint|drill [--gate <id>] [--lang en|pt] [--write [--force]] [--out <folder>]`
const lang = option('--lang') ?? 'en'
const fail = (msg) => {
  console.error(`${msg}\n${usage}`)
  process.exit(2)
}
if (args.length !== 1 || !/\.(ya?ml|json)$/.test(args[0])) fail('✗ one .way.yaml (or .yaml / .json) to read')
if (argv.some((a) => a.startsWith('--') && !flags.has(a))) fail(`✗ unknown option ${argv.find((a) => a.startsWith('--') && !flags.has(a))}`)
if (!['en', 'pt'].includes(lang)) fail('✗ --lang is en or pt')
if (argv.includes('--take') && !argv.includes('--from')) fail('✗ --take goes with --from')

const T = {
  en: {
    syntax: (d) => `does not read as YAML (${d})`, format: `the file starts with «apiVersion: ${DNA_API}» and «kind: ${DNA_KIND}» (or «format: ${STAGE_DOOR}», from before)`, noLanes: 'no lanes: a way needs at least one (who leads the stages)',
    shape: (w) => `${w} must be a list of items, each with an id`, duplicate: (w, id) => `${w}: the id «${id}» is repeated`,
    laneUnknown: (s, l, ls) => `stage ${s}: the lane «${l}» does not exist (lanes: ${ls})`, phaseUnknown: (s, p, ps) => `stage ${s}: the phase «${p}» does not exist (phases: ${ps})`,
    gateUnknown: (g, a) => `gate ${g}: «after» names «${a}», which is not a stage`,
    ok: (s) => `✓ ${s.stages} stages, ${s.gates} gates, ${s.phases} phases, ${s.lanes} lanes, ${s.outputs} outputs`, look: 'to look at', nothing: '✓ nothing to look at',
    changes: (n) => (n ? `${n} change${n === 1 ? '' : 's'} in the workbook (take them with --take <key,…> or --take all):` : '✓ the workbook changes nothing'),
    add: 'add', remove: 'remove', set: 'change', risky: 'ask first', empty: '(empty)', yes: 'yes', no: 'no', took: (n, f) => `✓ ${n} change${n === 1 ? '' : 's'} written to ${f}`,
    unknownKey: (k) => `✗ no change has the key «${k}»`,
  },
  pt: {
    syntax: (d) => `não lê como YAML (${d})`, format: `o arquivo começa com «apiVersion: ${DNA_API}» e «kind: ${DNA_KIND}» (ou com «format: ${STAGE_DOOR}», de antes)`, noLanes: 'nenhuma raia: o jeito de trabalhar precisa de pelo menos uma (quem lidera as etapas)',
    shape: (w) => `${w} precisa ser uma lista de itens, cada um com id`, duplicate: (w, id) => `${w}: o id «${id}» se repete`,
    laneUnknown: (s, l, ls) => `etapa ${s}: a raia «${l}» não existe (raias: ${ls})`, phaseUnknown: (s, p, ps) => `etapa ${s}: a fase «${p}» não existe (fases: ${ps})`,
    gateUnknown: (g, a) => `gate ${g}: «after» diz «${a}», que não é uma etapa`,
    ok: (s) => `✓ ${s.stages} etapas, ${s.gates} gates, ${s.phases} fases, ${s.lanes} raias, ${s.outputs} entregas`, look: 'para olhar', nothing: '✓ nada para olhar',
    changes: (n) => (n ? `${n} ${n === 1 ? 'mudança' : 'mudanças'} na planilha (aceite com --take <chave,…> ou --take all):` : '✓ a planilha não muda nada'),
    add: 'incluir', remove: 'tirar', set: 'mudar', risky: 'perguntar antes', empty: '(vazio)', yes: 'sim', no: 'não', took: (n, f) => `✓ ${n} ${n === 1 ? 'mudança escrita' : 'mudanças escritas'} em ${f}`,
    unknownKey: (k) => `✗ nenhuma mudança tem a chave «${k}»`,
  },
}[lang]

// ---- read and check ----
const file = resolve(args[0])
// ---- --upgrade: the header of before (`format: stage-door/v1`) as DNA's, the rest of the text as it is ----
if (argv.includes('--upgrade')) {
  const text = readFileSync(file, 'utf8')
  const up = upgradeHeader(text, STAGE_DOOR, DNA_KIND)
  const pt = lang === 'pt'
  if (up === undefined) {
    if (/^apiVersion:/m.test(text)) {
      console.log(pt ? `✓ ${basename(file)} já tem o cabeçalho do DNA` : `✓ ${basename(file)} already has DNA's header`)
      process.exit(0)
    }
  } else {
    if (readWay(up).problems.length !== readWay(text).problems.length || JSON.stringify(readWay(up).def) !== JSON.stringify(readWay(text).def)) {
      console.error(pt ? `✗ ${basename(file)}: depois do cabeçalho novo, o arquivo não se lê igual; nada escrito` : `✗ ${basename(file)}: with the new header the file does not read the same; nothing written`)
      process.exit(1)
    }
    if (!argv.includes('--write')) {
      process.stdout.write(up)
      process.exit(0)
    }
    writeFileSync(file, up)
    console.log(pt ? `✓ ${basename(file)}: agora com apiVersion ${DNA_API} e kind ${DNA_KIND}; o resto como estava` : `✓ ${basename(file)}: now apiVersion ${DNA_API} and kind ${DNA_KIND}; the rest as it was`)
    process.exit(0)
  }
}
const source = readFileSync(file, 'utf8')
const read = readWay(source)
const at = (line, text) => `✗ ${basename(file)}:${line}: ${text}`
const messages = read.problems.map((p) =>
  at(p.line, p.key === 'syntax' ? T.syntax(p.detail) : p.key === 'format' ? T.format : p.key === 'noLanes' ? T.noLanes : p.key === 'shape' ? T.shape(p.what) : p.key === 'duplicate' ? T.duplicate(p.what, p.id) : p.key === 'laneUnknown' ? T.laneUnknown(p.stage, p.lane, p.lanes) : p.key === 'phaseUnknown' ? T.phaseUnknown(p.stage, p.phase, p.phases) : T.gateUnknown(p.gate, p.after)))
// what the format's rules say beyond the reading (a gate's approver that is not a role…): no line, the item says where;
// only when the reading found nothing, so one mistake is not told twice
if (read.def && !messages.length) messages.push(...checkWay(read.def).map((p) => `✗ ${basename(file)}: ${problemText(p)}`))
if (read.fatal || messages.length) {
  for (const m of messages) console.error(m)
  process.exit(1)
}
const way = read.def
const name = read.name || basename(file).replace(/(\.way)?\.(ya?ml|json)$/, '')
const id = basename(file).replace(/(\.way)?\.(ya?ml|json)$/, '')
// --check --json: the way as it was read and what to look at, as one JSON document (what the mod's preview draws)
if (argv.includes('--check') && argv.includes('--json')) {
  console.log(JSON.stringify({ format: 'way-of-working/read-v1', name, way, looks: reviewWay(way).map((l) => ({ en: l.en, pt: l.pt })) }))
  process.exit(0)
}
// ---- the lenses: the same way as another skill's recipe ----
if (argv.includes('--lens')) {
  const kind = option('--lens')
  const lensLang = lang === 'pt' ? 'pt' : 'en'
  const from = `${basename(file)}@${createHash('sha256').update(source).digest('hex').slice(0, 8)}`
  const made = kind === 'sim' ? simOf(way, name, from, lensLang) : kind === 'blueprint' ? blueprintOf(way, name, from, id, lensLang) : kind === 'drill' ? drillOf(way, name, from, option('--gate'), lensLang) : { error: '--lens is sim, blueprint or drill' }
  if (made.error) fail(`✗ ${made.error}`)
  const target = { sim: `${id}.sim`, blueprint: `${id}.blueprint.yaml`, drill: `${id}.drill.yaml` }[kind]
  const skill = { sim: 'process-simulation', blueprint: 'service-blueprint', drill: 'incident-drill' }[kind]
  const bets = lang === 'pt' ? `${made.bets.length} ${made.bets.length === 1 ? 'número ou texto apostado' : 'números ou textos apostados'} (# bet:): troque pelos seus` : `${made.bets.length} ${made.bets.length === 1 ? 'number or line bet' : 'numbers or lines bet'} (# bet:): replace them with your own`
  if (!argv.includes('--write')) {
    process.stdout.write(made.text)
    console.error(`• ${bets}`)
    process.exit(0)
  }
  const path = join(resolve(option('--out') ?? dirname(file)), target)
  if (existsSync(path) && readFileSync(path, 'utf8') !== made.text && !argv.includes('--force')) {
    fail(lang === 'pt' ? `✗ ${target} já existe e é diferente (talvez editado à mão): --force escreve por cima` : `✗ ${target} is there and differs (maybe edited by hand): --force writes over it`)
  }
  writeFileSync(path, made.text)
  console.log(`✓ ${kind.padEnd(9)} ${path}`)
  console.log(`• ${bets}`)
  // checked by its own skill, when it is beside this one (the plugin, the npm package)
  const script = join(here, `../../${skill}/scripts/build.mjs`)
  if (existsSync(script)) {
    const c = spawnSync(process.execPath, [script, path, '--check', ...(kind === 'sim' ? [] : ['--lang', lang])], { encoding: 'utf8' })
    for (const l of `${c.stdout}${c.stderr}`.trim().split('\n')) if (l) console.log(`  ${l}`)
    process.exit(c.status === 0 ? 0 : 1)
  }
  console.log(lang === 'pt' ? `• ${skill} não está aqui ao lado: confira com a skill ${skill}` : `• ${skill} is not beside this skill: check it with ${skill}`)
  process.exit(0)
}

console.log(T.ok(read.summary))
const looks = reviewWay(way)
if (looks.length) for (const l of looks) console.log(`! ${T.look}: ${l[lang]}`)
else console.log(T.nothing)

// ---- the way back: an edited workbook as the changes it proposes ----
if (argv.includes('--from')) {
  const edited = fromSheets(way, readXlsx(readFileSync(resolve(option('--from')))))
  if (edited.problems.length) {
    for (const p of edited.problems) console.error(`✗ ${basename(option('--from'))}: ${p}`)
    process.exit(1)
  }
  const rows = wayDiff(way, edited.way)
  const words = { empty: T.empty, yes: T.yes, no: T.no, criteria: (c) => (c.kind === 'outputs' ? c.outputs.join(', ') : c.kind === 'activities' ? c.stage : c.kind === 'kpis' ? c.kpis.join(', ') : `${c.min} ${c.result}`) }
  const ws = [edited.way, way]
  const line = (r) => {
    const what = `${r.item} «${itemName(r, ws) || r.id}»`
    if (r.kind !== 'set') return `${T[r.kind]} ${what}`
    return `${T.set} ${r.item === 'way' ? '' : `${what} · `}${r.field}: ${show(r.item, r.field, r.before, ws, words)} → ${show(r.item, r.field, r.after, ws, words)}`
  }
  const take = option('--take')
  if (!take) {
    console.log(T.changes(rows.length))
    for (const r of rows) console.log(`  ${r.key}  ${line(r)}${r.risky ? `  (${T.risky})` : ''}`)
    process.exit(0)
  }
  const keys = take === 'all' ? rows.map((r) => r.key) : take.split(',').map((k) => k.trim()).filter(Boolean)
  const missing = keys.find((k) => !rows.some((r) => r.key === k))
  if (missing) {
    console.error(T.unknownKey(missing))
    process.exit(2)
  }
  const next = applyRows(way, edited.way, rows.filter((r) => keys.includes(r.key)))
  // the file keeps how it said what it is: DNA's header, or the format line of before
  writeFileSync(file, exportWay(name, next, file.endsWith('.json') ? 'json' : 'yaml', /^apiVersion:/m.test(source) || /"apiVersion"/.test(source) ? DNA : STAGE_DOOR))
  console.log(T.took(keys.length, basename(file)))
  process.exit(0)
}

// ---- what to make ----
if (argv.includes('--check')) process.exit(0)
const all = argv.includes('--all')
const want = { html: all || argv.includes('--html'), xlsx: all || argv.includes('--xlsx'), explainer: all || argv.includes('--explainer') }
if (!want.xlsx && !want.explainer) want.html = true
const out = resolve(option('--out') ?? dirname(file))
const asset = (f) => readFileSync(join(here, '../assets', f), 'utf8')

if (want.html) {
  const page = join(out, `${id}.html`)
  writeFileSync(page, fill(asset('map.html'), { WAY: inline({ id, name, lang, way, yaml: source }) }))
  console.log(`✓ map       ${page}`)
}
if (want.xlsx) {
  const book = join(out, `${id}.xlsx`)
  writeFileSync(book, xlsx(workbookOf(name, way, lang)))
  console.log(`✓ workbook  ${book}`)
}
let exit = 0
if (want.explainer) {
  const scene = validateScene(wayLesson(name, way, lang))
  const page = join(out, `${id}.explainer.html`)
  writeFileSync(page, fill(asset('explainer.html'), { RECIPE: inline(scene) }))
  console.log(`✓ explainer    ${page}`)
  const r = await runPage(page, 'review')
  if (r === null) console.log('• review    no Chrome, Chromium or Edge here: the explainer checks itself when opened')
  else if (r.error) console.log(`✗ review    not checked: ${r.error}`)
  else if (!r.problems.length) console.log(`✓ review    ${r.combos} ${r.combos === 1 ? 'setting' : 'settings'}: nothing off the paper, no text over text`)
  else {
    for (const p of r.problems) console.log(`! review    ${p}`)
    exit = 3
  }
}
process.exit(exit)
