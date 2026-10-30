#!/usr/bin/env node
// Checks a chalk-talk recipe and turns it into one HTML file that plays the lesson.
//
//   node build.mjs <recipe.json> [out.html] [--no-review]
//
// Exit codes: 0 drawn and checked (or no browser to check with); 1 the recipe breaks the contract (nothing written);
// 2 bad arguments; 3 drawn, but the reviewer found something to fix (off the paper, text over text, a line across a
// text). Needs Node 18 or later and nothing else; the review uses Chrome, Chromium or Edge when one is installed.
import { readFileSync, statSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from './browser.mjs'
import { chaptersFor, validateScene } from './contract.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2).filter((a) => !a.startsWith('--'))
const noReview = process.argv.includes('--no-review')
if (!args[0]) {
  console.error('usage: node build.mjs <recipe.json> [out.html] [--no-review]')
  process.exit(2)
}

const source = resolve(args[0])
let scene
try {
  scene = validateScene(JSON.parse(readFileSync(source, 'utf8')))
} catch (e) {
  console.error(`✗ contract: ${e.message}`)
  process.exit(1)
}

const slug = String(scene.id || basename(source, '.json')).replace(/[^a-z0-9-]+/gi, '-').slice(0, 60) || 'drawing'
const out = resolve(args[1] ?? join(dirname(source), `${slug}.html`))
// JSON inside a <script> tag: "<" escaped so no text in the recipe can end the tag.
const recipe = JSON.stringify(scene).replace(/</g, '\\u003c')
const page = readFileSync(join(here, '../assets/player.html'), 'utf8').replace('{{RECIPE}}', () => recipe)
writeFileSync(out, page)

const values = Object.keys(scene.params ?? {}).length + Object.keys(scene.switches ?? {}).length
console.log(`✓ contract  ${scene.steps.length} steps, ${chaptersFor(scene).length} chapters, ${values} values`)

let code = 0
if (noReview) console.log('• review    skipped (--no-review); the page checks itself when opened')
else {
  const r = runPage(out, 'review')
  if (!r) console.log('• review    no Chrome, Chromium or Edge here: the page checks itself when opened')
  else if (r.error) console.log(`• review    could not run (${r.error}); the page checks itself when opened`)
  else if (!r.problems.length) console.log(`✓ review    ${r.combos} ${r.combos === 1 ? "setting" : "settings"}: nothing off the paper, no text over text`)
  else {
    for (const p of r.problems) console.log(`! review    ${p}`)
    code = 3
  }
}
console.log(`→ ${out} (${Math.round(statSync(out).size / 1024)} KB, opens offline)`)
process.exit(code)
