#!/usr/bin/env node
// Checks a way of working (<id>.way.yaml) and makes what is asked of it: the map (an HTML page that opens with no
// internet), the workbook (.xlsx) and a chalk-talk lesson that walks it drawing. And the way back: a workbook someone
// changed is read as the changes it proposes, one per line, and only the ones taken go into the .way.yaml.
//
//   node build.mjs <id>.way.yaml --check [--lang en|pt]                       only check it: nothing is written
//   node build.mjs <id>.way.yaml [--html] [--xlsx] [--lesson] [--all] [--lang en|pt] [--out <folder>]
//   node build.mjs <id>.way.yaml --from <edited.xlsx> [--lang en|pt]           the changes, each with its key
//   node build.mjs <id>.way.yaml --from <edited.xlsx> --take <key,key…|all>    writes the ones taken into the .way.yaml
//
// With no --html/--xlsx/--lesson it makes the map. Files go beside the .way.yaml (or in --out), named by its id.
// Exit codes: 0 done (what to look at is printed, and is not an error); 1 the file breaks the format (each problem with
// its line; nothing written); 2 bad arguments; 3 made, but the lesson's reviewer found something to fix. Needs Node 18
// or later and nothing else; the lesson's review uses Chrome, Chromium or Edge when there is one.
import { readFileSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from './browser.mjs'
import { fill, inline } from './page.mjs'
import { applyRows, checkWay, exportWay, fromSheets, itemName, problemText, readWay, reviewWay, show, STAGE_DOOR, validateScene, wayDiff, wayLesson, workbookOf, xlsx } from './engine.mjs'
import { readXlsx } from './read-xlsx.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const valued = new Set(['--lang', '--out', '--from', '--take'])
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const flags = new Set(['--check', '--html', '--xlsx', '--lesson', '--all', ...valued])
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const usage = `usage: node build.mjs <id>.way.yaml --check [--lang en|pt]
       node build.mjs <id>.way.yaml [--html] [--xlsx] [--lesson] [--all] [--lang en|pt] [--out <folder>]
       node build.mjs <id>.way.yaml --from <edited.xlsx> [--take <key,key…|all>]`
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
    syntax: (d) => `does not read as YAML (${d})`, format: `«format» must be ${STAGE_DOOR}`, noLanes: 'no lanes: a way needs at least one (who leads the stages)',
    shape: (w) => `${w} must be a list of items, each with an id`, duplicate: (w, id) => `${w}: the id «${id}» is repeated`,
    laneUnknown: (s, l, ls) => `stage ${s}: the lane «${l}» does not exist (lanes: ${ls})`, phaseUnknown: (s, p, ps) => `stage ${s}: the phase «${p}» does not exist (phases: ${ps})`,
    gateUnknown: (g, a) => `gate ${g}: «after» names «${a}», which is not a stage`,
    ok: (s) => `✓ ${s.stages} stages, ${s.gates} gates, ${s.phases} phases, ${s.lanes} lanes, ${s.outputs} outputs`, look: 'to look at', nothing: '✓ nothing to look at',
    changes: (n) => (n ? `${n} change${n === 1 ? '' : 's'} in the workbook (take them with --take <key,…> or --take all):` : '✓ the workbook changes nothing'),
    add: 'add', remove: 'remove', set: 'change', risky: 'ask first', empty: '(empty)', yes: 'yes', no: 'no', took: (n, f) => `✓ ${n} change${n === 1 ? '' : 's'} written to ${f}`,
    unknownKey: (k) => `✗ no change has the key «${k}»`,
  },
  pt: {
    syntax: (d) => `não lê como YAML (${d})`, format: `«format» precisa ser ${STAGE_DOOR}`, noLanes: 'nenhuma raia: o jeito de trabalhar precisa de pelo menos uma (quem lidera as etapas)',
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
  writeFileSync(file, exportWay(name, next, file.endsWith('.json') ? 'json' : 'yaml', STAGE_DOOR))
  console.log(T.took(keys.length, basename(file)))
  process.exit(0)
}

// ---- what to make ----
if (argv.includes('--check')) process.exit(0)
const all = argv.includes('--all')
const want = { html: all || argv.includes('--html'), xlsx: all || argv.includes('--xlsx'), lesson: all || argv.includes('--lesson') }
if (!want.xlsx && !want.lesson) want.html = true
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
if (want.lesson) {
  const scene = validateScene(wayLesson(name, way, lang))
  const page = join(out, `${id}.lesson.html`)
  writeFileSync(page, fill(asset('lesson.html'), { RECIPE: inline(scene) }))
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
process.exit(exit)
