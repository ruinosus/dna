#!/usr/bin/env node
// Turns a .sim recipe (a process: what arrives, who handles it, what it costs) into an animated what-if simulation —
// one HTML page that opens offline — and checks, runs and translates recipes. No model, no install, no network:
// Node 18 or later.
//
//   node build.mjs <recipe.sim> [<another.sim> …] [--lang en|pt] [--out <folder>]   the page: <id>.box-office.html,
//                                  opening on the first recipe (the others in its Example menu)
//   node build.mjs <recipe.sim> --check                     only check: the validator's errors and warnings
//   node build.mjs <recipe.sim> --run [--seeds N] [--set knob=value …] [--json]
//                                  run it here: the median and the p10 to p90 range of each metric
//   node build.mjs <recipe.sim> --to en|pt-BR [--write]     the same recipe in the other language (exact round trip)
//
// Exit codes: 0 done (warnings are not errors); 1 the recipe has errors (each with its message); 2 bad arguments.
// The format is in references/format.md.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { BO, SIMLANG } from './engine.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const valued = new Set(['--lang', '--out', '--seeds', '--set', '--to'])
const flags = new Set(['--check', '--run', '--json', '--write', ...valued])
const usage = `usage: node build.mjs <recipe.sim> [<another.sim> …] [--lang en|pt] [--out <folder>]
       node build.mjs <recipe.sim> --check
       node build.mjs <recipe.sim> --run [--seeds N] [--set knob=value …] [--json]
       node build.mjs <recipe.sim> --to en|pt-BR [--write]`
const fail = (msg) => {
  console.error(`${msg}\n\n${usage}`)
  process.exit(2)
}
const files = []
const sets = {}
for (let i = 0; i < argv.length; i++) {
  const a = argv[i]
  if (!a.startsWith('--')) files.push(a)
  else if (!flags.has(a)) fail(`✗ unknown option ${a}`)
  else if (valued.has(a)) {
    const v = argv[++i]
    if (v === undefined) fail(`✗ ${a} needs a value`)
    if (a === '--set') {
      const [k, x] = v.split('=')
      if (!k || x === undefined) fail(`✗ --set is knob=value, not «${v}»`)
      sets[k] = /%$/.test(x) ? parseFloat(x) / 100 : parseFloat(x)
    }
  }
}
const option = (name) => {
  const i = argv.indexOf(name)
  return i >= 0 ? argv[i + 1] : undefined
}
if (!files.length) fail('✗ name a .sim recipe')
for (const f of files) if (!existsSync(f)) fail(`✗ ${f} does not exist`)
const lang = option('--lang') ?? 'en'
if (!['en', 'pt'].includes(lang)) fail('✗ --lang is en or pt')

const initialKnobs = (model, overrides = {}) => Object.fromEntries(model.knobOrder.map((k) => [k, k in overrides ? overrides[k] : model.knobs[k].init]))
/** The recipe's diagnostics, with the warning of a pool asked for more than it can do. */
function check(src, overrides = {}) {
  const r = SIMLANG.parse(src)
  if (r.ok) {
    const plan = SIMLANG.compile(r.model, initialKnobs(r.model, overrides))
    for (const ld of SIMLANG.flows(r.model, plan).loads) {
      if (ld.load > 1.001) r.diags.push({ sev: 'warn', text: SIMLANG.fmtMsg('unstable', { x: plan.steps[ld.steps[0]].name, v: `${Math.round(ld.load * 100)}%` }, r.model.lang) })
    }
  }
  return r
}
const tell = (file, r) => {
  for (const d of r.diags) console.log(`${d.sev === "error" ? "✗" : "!"} ${basename(file)}: ${d.text}`)
}
const src = (f) => readFileSync(f, 'utf8')

if (argv.includes('--to')) {
  const to = /^pt/i.test(option('--to')) ? 'pt-BR' : 'en'
  const out = SIMLANG.translate(src(files[0]), to)
  if (argv.includes('--write')) {
    writeFileSync(files[0], out)
    console.log(`✓ translated ${files[0]} to ${to}`)
  } else process.stdout.write(out)
  process.exit(0)
}

if (argv.includes('--check')) {
  let bad = false
  for (const f of files) {
    const r = check(src(f))
    tell(f, r)
    if (r.ok) console.log(`✓ ${basename(f)}: ${r.diags.length ? `${r.diags.length} warning${r.diags.length === 1 ? '' : 's'}` : 'no problems'}`)
    bad ||= !r.ok
  }
  process.exit(bad ? 1 : 0)
}

if (argv.includes('--run')) {
  const r = check(src(files[0]), sets)
  const json = argv.includes('--json')
  // with --json the warnings go in the JSON, so the output stays one document
  if (!json || !r.ok) tell(files[0], r)
  if (!r.ok) process.exit(1)
  const knobs = initialKnobs(r.model, sets)
  const plan = SIMLANG.compile(r.model, knobs)
  const expected = plan.statedPerMin * plan.openFrac * plan.horizon
  const n = Number(option('--seeds') ?? (expected > 200000 ? 6 : 10))
  const seeds = Array.from({ length: Math.max(1, n) }, (_, i) => r.model.seed * 1009 + i * 7919 + 1)
  const t0 = Date.now()
  const values = r.model.shows.map(() => [])
  for (const s of seeds) {
    const sim = new BO.Sim(plan, s, {})
    sim.runUntil(plan.horizon)
    const res = sim.results()
    r.model.shows.forEach((m, i) => values[i].push(BO.metric(m, res)))
  }
  const rows = r.model.shows.map((m, i) => {
    const v = values[i].sort((a, b) => a - b)
    return { metric: m.kind + (m.pn ? ` p${m.pn}` : '') + (m.x ? ` ${m.x}` : m.perName ? ` per ${m.perName}` : ''), p10: BO.quant(v, 0.1), median: BO.quant(v, 0.5), p90: BO.quant(v, 0.9) }
  })
  const unknown = Object.keys(sets).filter((k) => !(k in r.model.knobs))
  if (json) console.log(JSON.stringify({ name: r.model.name, knobs, runs: seeds.length, rows, warnings: r.diags.map((d) => d.text), ...(unknown.length ? { unknown } : {}) }, null, 2))
  else {
    const set = Object.entries(knobs).map(([k, v]) => `${k}=${r.model.knobs[k].pct ? `${Math.round(v * 100)}%` : v}`).join(', ')
    console.log(`✓ ${r.model.name} · ${seeds.length} runs · ${Date.now() - t0} ms${set ? ` · ${set}` : ''}`)
    const f = (x) => (Math.abs(x) >= 100 ? Math.round(x).toLocaleString('en-US') : x.toFixed(3))
    for (const row of rows) console.log(`  ${row.metric.padEnd(36)} median ${f(row.median).padStart(12)}   (${f(row.p10)} to ${f(row.p90)})`)
    if (unknown.length) console.log(`! ignored unknown controls: ${unknown.join(', ')}`)
  }
  process.exit(0)
}

// the page, opening on the first recipe
const recipes = files.map((f) => {
  const text = src(f).replace(/\n+$/, '')
  const r = check(text)
  tell(f, r)
  if (!r.ok) process.exit(1)
  const name = r.model.name || basename(f, '.sim')
  return { id: basename(f, '.sim'), title: /^\s*lang\s+pt/im.test(text) ? `${name} (pt-BR)` : name, src: text }
})
const id = basename(files[0], '.sim').replace(/\.pt-BR$/i, '')
const out = resolve(option('--out') ?? dirname(files[0]))
mkdirSync(out, { recursive: true })
const page = join(out, `${id}.box-office.html`)
const inline = (x) => JSON.stringify(x, null, 2).replace(/</g, '\\u003c')
const html = readFileSync(join(here, '../assets/box-office.html'), 'utf8')
  .replace('/*EXAMPLES*/', () => `var EXAMPLES = ${inline(recipes)};`)
  .replace('/*START_UI*/', () => `var START_UI = ${JSON.stringify(lang)};`)
writeFileSync(page, html)
console.log(`✓ page      ${page}`)
console.log('• a model, not a forecast: say where the numbers came from')
