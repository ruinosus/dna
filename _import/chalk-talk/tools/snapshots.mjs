// The regression gallery: every example recipe drawn whole at its starting values in a browser without a window, its
// SVG kept in tools/snapshots/. The strokes are seeded by the step's index, so the same engine draws the same SVG; a
// difference names the step that changed. Run after `npm run assets`; `--update` accepts the new drawings.
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from '../skills/chalk-talk/scripts/browser.mjs'
import { recipesIn } from './recipes.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const update = process.argv.includes('--update')
const kept = join(here, 'snapshots')
const player = readFileSync(join(root, 'skills/chalk-talk/assets/player.html'), 'utf8')
const sources = [join(root, 'skills/chalk-talk/references/examples'), join(root, 'docs/examples')]
const recipes = []
for (const d of sources) recipes.push(...(await recipesIn(d)))

// One element a line, so a difference reads as the element that changed.
const lines = (svg) => svg.replace(/></g, '>\n<').split('\n')
const stepOf = (line) => line.match(/data-step="(\d+)"/)?.[1]

mkdirSync(kept, { recursive: true })
const dir = mkdtempSync(join(tmpdir(), 'chalk-talk-snap-'))
let changed = 0
for (const { file: name, scene } of recipes) {
  const page = join(dir, `${name}.html`)
  const recipe = JSON.stringify(scene).replace(/</g, '\\u003c')
  writeFileSync(page, player.replace('{{RECIPE}}', () => recipe))
  const r = await runPage(page, 'snapshot', '', { timeout: 60 })
  if (!r) throw new Error('No Chrome, Chromium or Edge: snapshots need one (set CHROME_PATH).')
  if (r.error) throw new Error(`${name}: ${r.error}`)
  const target = join(kept, `${name}.svg`)
  const now = lines(r.svg)
  if (update || !existsSync(target)) {
    writeFileSync(target, now.join('\n') + '\n')
    console.log(`${existsSync(target) && !update ? '+' : '✓'} ${name}: ${update ? 'kept' : 'new'} (${now.length} elements)`)
    continue
  }
  const before = readFileSync(target, 'utf8').trimEnd().split('\n')
  const at = now.findIndex((l, i) => l !== before[i])
  if (at === -1 && now.length === before.length) {
    console.log(`✓ ${name}`)
    continue
  }
  changed++
  const i = at === -1 ? Math.min(now.length, before.length) : at
  const step = stepOf(now[i] ?? '') ?? stepOf(before[i] ?? '')
  console.log(`✗ ${name}: differs from element ${i + 1}${step ? ` (step ${Number(step) + 1})` : ''}; ${before.length} → ${now.length} elements`)
}
rmSync(dir, { recursive: true, force: true })
if (changed) {
  console.error(`${changed} drawing(s) changed. If on purpose: npm run snapshots -- --update`)
  process.exit(1)
}
