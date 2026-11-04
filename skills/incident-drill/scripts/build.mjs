#!/usr/bin/env node
// Checks a drill (<id>.drill.yaml) and makes the game — one HTML page that opens with no internet — and the
// facilitator's script. What does not hold is printed («to look at») and the game is still made; what would break the
// game (a choice to no scene, a scene with no way on, a drawing that does not read…) says its line and nothing is made.
//
//   node build.mjs <id>.drill.yaml --check [--json] [--lang en|pt]   only check it: nothing is written
//   node build.mjs <id>.drill.yaml [--facilitator] [--all] [--lang en|pt] [--out <folder>]
//
// With no --facilitator it makes the game; --all makes both. When the drill's «from» is a file beside it (the runbook),
// each choice's «runbook» mark is looked up in it: the game shows that passage, and a mark the runbook does not have is
// to look at. Exit codes: 0 done; 1 the file breaks the format (each problem with its line; nothing written); 2 bad
// arguments. Needs Node 18 or later and nothing else.
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { DNA_API, facilitator, findPassage, FORMAT, KIND, problemText, readDrill, readRecipe, reviewDrill, upgradeHeader } from './engine.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const valued = new Set(['--lang', '--out'])
const flags = new Set(['--check', '--json', '--facilitator', '--all', '--upgrade', '--write', ...valued])
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const usage = `usage: node build.mjs <id>.drill.yaml --check [--json] [--lang en|pt]
       node build.mjs <id>.drill.yaml [--facilitator] [--all] [--lang en|pt] [--out <folder>]`
const lang = option('--lang') ?? 'en'
const fail = (msg) => {
  console.error(`${msg}\n${usage}`)
  process.exit(2)
}
if (args.length !== 1 || !/\.(ya?ml|json)$/.test(args[0])) fail('✗ one .drill.yaml to read')
const unknown = argv.find((a) => a.startsWith('--') && !flags.has(a))
if (unknown) fail(`✗ unknown option ${unknown}`)
if (!['en', 'pt'].includes(lang)) fail('✗ --lang is en or pt')

const T = {
  en: { ok: (d) => `✓ ${d.scenes.length} scenes, ${d.scenes.filter((s) => s.end).length} ends, ${d.roles.length} roles`, look: 'to look at', nothing: '✓ nothing to look at', draw: (s) => `the drawing of «${s}»`, runbook: (f) => `• runbook   ${f}`, noRunbook: (f) => `• runbook   «${f}» is not a file here: the marks were not looked up` },
  pt: { ok: (d) => `✓ ${d.scenes.length} cenas, ${d.scenes.filter((s) => s.end).length} fins, ${d.roles.length} papéis`, look: 'para olhar', nothing: '✓ nada para olhar', draw: (s) => `o desenho de «${s}»`, runbook: (f) => `• runbook   ${f}`, noRunbook: (f) => `• runbook   «${f}» não é um arquivo aqui: as marcas não foram conferidas` },
}[lang]

const file = resolve(args[0])
// ---- --upgrade: the header of before (`format: dress-rehearsal/v1`) as DNA's, the rest of the text as it is ----
if (argv.includes('--upgrade')) {
  const text = readFileSync(file, 'utf8')
  const up = upgradeHeader(text, FORMAT, KIND)
  const pt = lang === 'pt'
  if (up === undefined) {
    if (/^apiVersion:/m.test(text)) {
      console.log(pt ? `✓ ${basename(file)} já tem o cabeçalho do DNA` : `✓ ${basename(file)} already has DNA's header`)
      process.exit(0)
    }
  } else {
    if (JSON.stringify(readDrill(up).drill) !== JSON.stringify(readDrill(text).drill) || readDrill(up).problems.length !== readDrill(text).problems.length) {
      console.error(pt ? `✗ ${basename(file)}: depois do cabeçalho novo, o arquivo não se lê igual; nada escrito` : `✗ ${basename(file)}: with the new header the file does not read the same; nothing written`)
      process.exit(1)
    }
    if (!argv.includes('--write')) {
      process.stdout.write(up)
      process.exit(0)
    }
    writeFileSync(file, up)
    console.log(pt ? `✓ ${basename(file)}: agora com apiVersion ${DNA_API} e kind ${KIND}; o resto como estava` : `✓ ${basename(file)}: now apiVersion ${DNA_API} and kind ${KIND}; the rest as it was`)
    process.exit(0)
  }
}
const read = readDrill(readFileSync(file, 'utf8'))
const problems = read.problems.map((p) => `✗ ${basename(file)}:${p.line}: ${problemText(p, lang)}`)
// each drawing must read (visual-explainer's text syntax or JSON); its mistake says the line in this file
if (read.drill)
  for (const s of read.drill.scenes.filter((x) => x.draw)) {
    try {
      readRecipe(s.draw)
    } catch (e) {
      const line = (read.drawLines?.[s.id] ?? 1) + (typeof e.line === 'number' ? e.line - 1 : 0)
      problems.push(`✗ ${basename(file)}:${line}: ${T.draw(s.id)}: ${e.message}`)
    }
  }
if (problems.length) {
  for (const p of problems) console.error(p)
  process.exit(1)
}
const drill = read.drill
const id = basename(file).replace(/(\.drill)?\.(ya?ml|json)$/, '')
// with --check --json the output is one JSON document: the lines for people stay quiet
const asJson = argv.includes('--check') && argv.includes('--json')
if (!asJson) console.log(T.ok(drill))

// the runbook it came from, when it is a file beside the drill: the passages the choices cite
const runbookFile = drill.from ? resolve(dirname(file), drill.from) : undefined
const runbook = runbookFile && existsSync(runbookFile) ? readFileSync(runbookFile, 'utf8') : undefined
if (drill.from && !asJson) console.log(runbook ? T.runbook(drill.from) : T.noRunbook(drill.from))
const excerpts = {}
if (runbook) {
  for (const ref of new Set(drill.scenes.flatMap((s) => (s.choices ?? []).map((c) => c.runbook).filter(Boolean)))) {
    const found = findPassage(runbook, ref)
    if (found) excerpts[ref] = found.text
  }
}
const looks = reviewDrill(drill, runbook)
// --check --json: the drill as read, what to look at and the runbook's passages, as one JSON document (what the mod's
// /drill plays in its pane)
if (asJson) {
  process.stdout.write(`${JSON.stringify({ format: 'incident-drill/read-v1', drill, looks: looks.map((l) => ({ en: l.en, pt: l.pt })), excerpts })}\n`)
  process.exit(0)
}
if (looks.length) for (const l of looks) console.log(`! ${T.look}: ${l[lang]}`)
else console.log(T.nothing)
if (argv.includes('--check')) process.exit(0)

const out = resolve(option('--out') ?? dirname(file))
const all = argv.includes('--all')
const wantGame = all || !argv.includes('--facilitator')
if (wantGame) {
  // JSON inside a <script> tag: "<" escaped so no text in the drill can end the tag.
  const json = JSON.stringify({ id, lang, drill, looks, excerpts }).replace(/</g, '\\u003c')
  const page = join(out, `${id}.drill.html`)
  writeFileSync(page, readFileSync(join(here, '../assets/drill.html'), 'utf8').replace('{{DRILL}}', () => json))
  console.log(`✓ game        ${page}`)
}
if (all || argv.includes('--facilitator')) {
  const md = join(out, `${id}.facilitator.md`)
  writeFileSync(md, facilitator(drill, looks, lang))
  console.log(`✓ facilitator ${md}`)
}
