#!/usr/bin/env node
// Checks chalk-talk recipes and turns them into one HTML file that plays the lesson — or, given several, a course: one
// file with every lesson and a list to go from one to another.
//
//   node build.mjs <recipe.json> [out.html] [--no-review]
//   node build.mjs <one.json> <two.json> … --out course.html [--title "The course"] [--no-review]
//
// Only a path ending in .html is ever written. Exit codes: 0 drawn and checked (or no browser to check with); 1 a recipe
// breaks the contract (nothing written); 2 bad arguments; 3 drawn, but the reviewer found something to fix (off the
// paper, text over text, a line across a text). Needs Node 18 or later and nothing else; the review uses Chrome,
// Chromium or Edge when one is installed.
import { readFileSync, statSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from './browser.mjs'
import { chaptersFor, validateScene } from './contract.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const valued = new Set(['--out', '--title'])
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const noReview = argv.includes('--no-review')
const sources = args.filter((a) => a.endsWith('.json'))
const outArg = option('--out') ?? args.find((a) => a.endsWith('.html'))
const usage = 'usage: node build.mjs <recipe.json> [out.html] [--no-review]\n       node build.mjs <one.json> <two.json> … --out course.html [--title "…"] [--no-review]'
if (!sources.length || args.some((a) => !a.endsWith('.json') && !a.endsWith('.html')) || (outArg && !outArg.endsWith('.html')) || (sources.length > 1 && !outArg)) {
  console.error(usage)
  process.exit(2)
}

const scenes = []
for (const file of sources) {
  try {
    scenes.push(validateScene(JSON.parse(readFileSync(resolve(file), 'utf8'))))
  } catch (e) {
    console.error(`✗ contract: ${sources.length > 1 ? `${basename(file)}: ` : ''}${e.message}`)
    process.exit(1)
  }
}

const course = scenes.length > 1
const slug = String(scenes[0].id || basename(sources[0], '.json')).replace(/[^a-z0-9-]+/gi, '-').slice(0, 60) || 'drawing'
const out = resolve(outArg ?? join(dirname(resolve(sources[0])), `${slug}.html`))
const content = course ? { course: option('--title') ?? scenes[0].title, lessons: scenes } : scenes[0]
// JSON inside a <script> tag: "<" escaped so no text in a recipe can end the tag.
const recipe = JSON.stringify(content).replace(/</g, '\\u003c')
const page = readFileSync(join(here, '../assets/player.html'), 'utf8').replace('{{RECIPE}}', () => recipe)
writeFileSync(out, page)

scenes.forEach((scene, k) => {
  const values = Object.keys(scene.params ?? {}).length + Object.keys(scene.switches ?? {}).length
  const who = course ? `  (${k + 1}) ${scene.title}: ` : '  '
  console.log(`✓ contract${who}${scene.steps.length} steps, ${chaptersFor(scene).length} chapters, ${values} values`)
})

let code = 0
if (noReview) console.log('• review    skipped (--no-review); the page checks itself when opened')
else {
  for (let k = 0; k < scenes.length; k++) {
    const who = course ? ` (${k + 1})` : ''
    const r = runPage(out, 'review', course ? `lesson=${k + 1}` : '')
    if (!r) {
      console.log('• review    no Chrome, Chromium or Edge here: the page checks itself when opened')
      break
    }
    if (r.error) console.log(`• review${who}    could not run (${r.error}); the page checks itself when opened`)
    else if (!r.problems.length) console.log(`✓ review${who}    ${r.combos} ${r.combos === 1 ? 'setting' : 'settings'}: nothing off the paper, no text over text`)
    else {
      for (const p of r.problems) console.log(`! review${who}    ${p}`)
      code = 3
    }
  }
}
console.log(`→ ${out} (${Math.round(statSync(out).size / 1024)} KB, opens offline${course ? `, ${scenes.length} lessons` : ''})`)
process.exit(code)
