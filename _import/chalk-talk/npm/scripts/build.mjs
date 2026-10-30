#!/usr/bin/env node
// Checks chalk-talk recipes and turns them into one HTML file that plays the lesson — or, given several, a course: one
// file with every lesson and a list to go from one to another. A recipe can be JSON (.json), text (.chalk), a Mermaid
// flowchart (.mmd, with `%% # chapter` and `%% > narration`), or Markdown (.md): each ```chalk-talk or ```mermaid block
// in it is a lesson.
//
//   node build.mjs <recipe.json|.chalk|.mmd|.md> [out.html] [--no-review]
//   node build.mjs <one> <two> … --out course.html [--title "The course"] [--no-review]
//   node build.mjs <recipe> [out.svg] --svg      an SVG that draws itself, with no script: it plays inside an <img>,
//                                                in a README on GitHub too (one SVG per lesson, named by its id)
//
// Only paths ending in .html or .svg are ever written. Exit codes: 0 drawn and checked (or no browser to check with); 1 a
// recipe breaks the contract (nothing written); 2 bad arguments; 3 drawn, but the reviewer found something to fix (off
// the paper, text over text, a line across a text); 4 --svg with no browser to draw it in. Needs Node 18 or later and
// nothing else; the review and --svg use Chrome, Chromium or Edge.
import { mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from './browser.mjs'
import { ChalkTextError, chaptersFor, parseChalk, PROP_ALIASES, PROP_NAMES, validateScene } from './contract.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const valued = new Set(['--out', '--title'])
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const noReview = argv.includes('--no-review')
const asSvg = argv.includes('--svg')
const ext = asSvg ? '.svg' : '.html'
const KINDS = ['.json', '.chalk', '.mmd', '.md']
const sources = args.filter((a) => KINDS.some((k) => a.endsWith(k)))
const outArg = option('--out') ?? args.find((a) => a.endsWith(ext))
const usage = 'usage: node build.mjs <recipe.json> [out.html] [--no-review]\n       node build.mjs <one.json> <two.json> … --out course.html [--title "…"] [--no-review]\n       node build.mjs <recipe.json> [out.svg] --svg'
if (!sources.length || args.some((a) => !KINDS.some((k) => a.endsWith(k)) && !a.endsWith(ext)) || (outArg && !outArg.endsWith(ext))) {
  console.error(usage)
  process.exit(2)
}

const PROPS = [...PROP_NAMES, ...Object.keys(PROP_ALIASES)]
// The Mermaid converter is large: loaded only for a Mermaid block.
const mermaid = async (text) => (await import('./mermaid.mjs')).fromMermaid(text)

/** The recipes a file holds: one for .json, .chalk and .mmd; one per ```chalk-talk / ```mermaid block in a .md. */
async function recipesOf(file) {
  const text = readFileSync(resolve(file), 'utf8')
  if (file.endsWith('.json')) return [JSON.parse(text)]
  if (file.endsWith('.chalk')) return [parseChalk(text, PROPS)]
  if (file.endsWith('.mmd')) return [await mermaid(text)]
  const blocks = [...text.matchAll(/^```(chalk-talk|mermaid)[^\n]*\n([\s\S]*?)^```/gm)]
  if (!blocks.length) throw new Error('no ```chalk-talk or ```mermaid block in this file.')
  const out = []
  for (const [, kind, body] of blocks) out.push(kind === 'mermaid' ? await mermaid(body) : parseChalk(body, PROPS))
  return out
}

const scenes = []
for (const file of sources) {
  try {
    for (const recipe of await recipesOf(file)) scenes.push(validateScene(recipe))
  } catch (e) {
    const where = sources.length > 1 || file.endsWith('.md') ? `${basename(file)}: ` : ''
    console.error(`✗ ${e instanceof ChalkTextError ? 'text' : 'contract'}: ${where}${e.message}`)
    process.exit(1)
  }
}

const course = scenes.length > 1
const slugOf = (scene, file) => String(scene.id || basename(file).replace(/\.[^.]+$/, '')).replace(/[^a-z0-9-]+/gi, '-').slice(0, 60) || 'drawing'
const slug = slugOf(scenes[0], sources[0])
// With --svg the page is only the browser's workbench: it goes to a folder of its own and away at the end.
const work = asSvg ? mkdtempSync(join(tmpdir(), 'chalk-talk-svg-')) : undefined
const out = work ? join(work, 'page.html') : resolve(outArg ?? join(dirname(resolve(sources[0])), `${slug}.html`))
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
if (!asSvg) {
  console.log(`→ ${out} (${Math.round(statSync(out).size / 1024)} KB, opens offline${course ? `, ${scenes.length} lessons` : ''})`)
  process.exit(code)
}

// --svg: each lesson drawn by the browser with its timing as CSS; one file, or one per lesson beside the first source.
const where = outArg && !course ? undefined : dirname(resolve(outArg ?? sources[0]))
for (let k = 0; k < scenes.length; k++) {
  const r = runPage(out, 'svg', course ? `lesson=${k + 1}` : '')
  if (!r) {
    console.error('✗ svg       no Chrome, Chromium or Edge here to draw it (set CHROME_PATH)')
    code = 4
    break
  }
  if (r.error) {
    console.error(`✗ svg       ${r.error}`)
    code = 4
    break
  }
  const file = where ? join(where, `${slugOf(scenes[k], sources[0])}.svg`) : resolve(outArg)
  writeFileSync(file, r.svg)
  console.log(`→ ${file} (${Math.round(statSync(file).size / 1024)} KB, draws itself in ${Math.round(r.ms / 1000)} s)`)
}
rmSync(work, { recursive: true, force: true })
process.exit(code)
