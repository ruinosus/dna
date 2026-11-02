#!/usr/bin/env node
// Compares the Copilot Studio agents cloned in a folder: what most of them do (a pattern), who is off it, what only
// one has, the team's rules not met — and makes the map (one HTML page that opens with no internet), the workbook
// (.xlsx) and the cast file (what people said, what was decided). No model, no install, no network: Node 18 or later.
//
//   node cast.mjs <agents-folder> --check [--profile <p.cast.yaml>] [--lang en|pt]     only compare: nothing is written
//   node cast.mjs <agents-folder> [--profile <p.cast.yaml>] [--html] [--xlsx] [--lesson] [--all] [--lang en|pt] [--out <folder>]
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
import { agentsIn, compare, DEFAULT_PROFILE, extractAgent, knownKinds, lessonOf, problemText, readCast, readProfile, reviewCast, validateScene, workbookFile, workbookOf, writeCast } from './engine.mjs'
import { fill, inline } from './page.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const valued = new Set(['--lang', '--out', '--profile'])
const flags = new Set(['--check', '--html', '--xlsx', '--lesson', '--all', ...valued])
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const usage = `usage: node cast.mjs <agents-folder> --check [--profile <p.cast.yaml>] [--lang en|pt]
       node cast.mjs <agents-folder> [--profile <p.cast.yaml>] [--html] [--xlsx] [--lesson] [--all] [--lang en|pt] [--out <folder>]`
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

const T = {
  en: {
    found: (n, o, s) => `✓ ${n} in the cast: ${o} orchestrator${o === 1 ? '' : 's'}, ${s} specialist${s === 1 ? '' : 's'}`,
    result: (p, off, solos) => `✓ ${p} patterns · ${off} off a pattern · ${solos} only one has`,
    look: 'to look at', nothing: '✓ nothing to look at', none: (f) => `✗ ${f} has no folder with agent.mcs.yml`, privacy: '• the files hold the client’s data: keep them in the client’s environment',
  },
  pt: {
    found: (n, o, s) => `✓ ${n} no elenco: ${o} ${o === 1 ? 'orquestrador' : 'orquestradores'}, ${s} ${s === 1 ? 'especialista' : 'especialistas'}`,
    result: (p, off, solos) => `✓ ${p} padrões · ${off} fora do padrão · ${solos} só um tem`,
    look: 'para olhar', nothing: '✓ nada para olhar', none: (f) => `✗ ${f} não tem nenhuma pasta com agent.mcs.yml`, privacy: '• os arquivos têm dados do cliente: deixe-os no ambiente dele',
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
const cast = castText !== undefined ? read(castFile, readCast).cast : { ...(profile.name ? { name: profile.name } : {}), agents: [], declared: [], decisions: [] }

// the schema's kinds, to tell a made-up one; without the schema every kind is taken as real
const schema = join(here, '../vendor/microsoft/reference/bot.schema.yaml-authoring.json')
const kinds = existsSync(schema) ? knownKinds(JSON.parse(readFileSync(schema, 'utf8'))) : undefined
const found = agentsIn(folder).map((a) => extractAgent(a.id, a.files, kinds))
if (!found.length) {
  console.error(T.none(args[0]))
  process.exit(1)
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
// the cast file keeps this run's roles, under what people wrote in it
const kept = { ...cast, agents: result.agents.map((a) => ({ id: a.id, role: a.role })) }
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
