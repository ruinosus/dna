#!/usr/bin/env node
// Checks a service blueprint (<id>.blueprint.yaml) and makes what is asked of it: the map (one HTML page that opens with
// no internet), the workbook (.xlsx) and a chalk-talk lesson that walks the journey.
//
//   node build.mjs <id>.blueprint.yaml --check [--lang en|pt]       only check it: nothing is written
//   node build.mjs <id>.blueprint.yaml [--html] [--xlsx] [--lesson] [--all] [--lang en|pt] [--out <folder>]
//
// With no --html/--xlsx/--lesson it makes the map. Files go beside the blueprint (or in --out), named by its id.
// Exit codes: 0 done (what to look at is printed, and is not an error); 1 the file breaks the format (each problem with
// its line; nothing written); 2 bad arguments; 3 made, but the lesson's reviewer found something to fix. Needs Node 18
// or later and nothing else; the lesson's review uses Chrome, Chromium or Edge when there is one.
import { readFileSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from './browser.mjs'
import { fill, inline } from './page.mjs'
import { lessonOf, problemText, readBlueprint, reviewBlueprint, validateScene, workbookFile, workbookOf } from './engine.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const valued = new Set(['--lang', '--out'])
const flags = new Set(['--check', '--json', '--html', '--xlsx', '--lesson', '--all', ...valued])
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const usage = `usage: node build.mjs <id>.blueprint.yaml --check [--json] [--lang en|pt]
       node build.mjs <id>.blueprint.yaml [--html] [--xlsx] [--lesson] [--all] [--lang en|pt] [--out <folder>]`
const lang = option('--lang') ?? 'en'
const fail = (msg) => {
  console.error(`${msg}\n${usage}`)
  process.exit(2)
}
if (args.length !== 1 || !/\.(ya?ml|json)$/.test(args[0])) fail('✗ one .blueprint.yaml to read')
const unknown = argv.find((a) => a.startsWith('--') && !flags.has(a))
if (unknown) fail(`✗ unknown option ${unknown}`)
if (!['en', 'pt'].includes(lang)) fail('✗ --lang is en or pt')

const T = {
  en: { ok: (b) => `✓ ${b.moments.length} moments, ${b.phases.length} phases, ${b.actors.length} actors, ${b.systems.length} systems, ${b.actions.length} actions`, look: 'to look at', nothing: '✓ nothing to look at' },
  pt: { ok: (b) => `✓ ${b.moments.length} momentos, ${b.phases.length} fases, ${b.actors.length} atores, ${b.systems.length} sistemas, ${b.actions.length} ações`, look: 'para olhar', nothing: '✓ nada para olhar' },
}[lang]

const file = resolve(args[0])
const source = readFileSync(file, 'utf8')
const read = readBlueprint(source)
if (read.problems.length) {
  for (const p of read.problems) console.error(`✗ ${basename(file)}:${p.line}: ${problemText(p, lang)}`)
  process.exit(1)
}
const blueprint = read.blueprint
const id = basename(file).replace(/(\.blueprint)?\.(ya?ml|json)$/, '')
// --check --json: the blueprint as it was read and what to look at, as one JSON document (what the mod's preview draws)
if (argv.includes('--check') && argv.includes('--json')) {
  console.log(JSON.stringify({ format: 'service-blueprint/read-v1', blueprint, looks: reviewBlueprint(blueprint).map((l) => ({ en: l.en, pt: l.pt })) }))
  process.exit(0)
}
console.log(T.ok(blueprint))
const looks = reviewBlueprint(blueprint)
if (looks.length) for (const l of looks) console.log(`! ${T.look}: ${l[lang]}`)
else console.log(T.nothing)
if (argv.includes('--check')) process.exit(0)

const all = argv.includes('--all')
const want = { html: all || argv.includes('--html'), xlsx: all || argv.includes('--xlsx'), lesson: all || argv.includes('--lesson') }
if (!want.xlsx && !want.lesson) want.html = true
const out = resolve(option('--out') ?? dirname(file))
const asset = (f) => readFileSync(join(here, '../assets', f), 'utf8')
if (want.html) {
  const page = join(out, `${id}.html`)
  writeFileSync(page, fill(asset('map.html'), { BLUEPRINT: inline({ id, lang, blueprint, looks, yaml: source }) }))
  console.log(`✓ map       ${page}`)
}
if (want.xlsx) {
  const book = join(out, `${id}.xlsx`)
  writeFileSync(book, workbookFile(workbookOf(blueprint, looks, lang)))
  console.log(`✓ workbook  ${book}`)
}
let exit = 0
if (want.lesson) {
  const scene = validateScene(lessonOf(blueprint, lang))
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
