#!/usr/bin/env node
// Checks chalk-talk recipes and turns them into one HTML file that plays the lesson — or, given several, a course: one
// file with every lesson and a list to go from one to another. A recipe can be JSON (.json), text (.chalk), a Mermaid
// flowchart (.mmd, with `%% # chapter` and `%% > narration`), or Markdown (.md): each ```chalk-talk or ```mermaid block
// in it is a lesson.
//
//   node build.mjs <recipe.json|.chalk|.mmd|.md> [out.html] [--no-review] [--snapshots [folder]] [--review-timeout <s>]
//   node build.mjs <one> <two> … --out course.html [--title "The course"] [--no-review]
//   node build.mjs <recipe> [out.svg] --svg      an SVG that draws itself, with no script: it plays inside an <img>,
//                                                in a README on GitHub too (one SVG per lesson, named by its id)
//
// --snapshots writes, in <id>.snapshots/ beside the page (or the folder given), a PNG of each chapter as it ends at each
// setting the reviewer tries, and <id>.contact-sheet.png with them all: a picture to look at before delivering.
//
// Only .html, .svg and .png files are ever written. Exit codes: 0 drawn and checked (or no browser to check with); 1 a
// recipe breaks the contract (nothing written); 2 bad arguments; 3 drawn, but the reviewer found something to fix (off
// the paper, text over text, a line across a text); 4 --svg or --snapshots with no browser to draw them in. Needs Node 18
// or later and nothing else; the review, --snapshots and --svg use Chrome, Chromium or Edge (Playwright's Chromium too).
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPages } from './browser.mjs'
import { fill, inline } from './page.mjs'
import { ChalkTextError, chaptersFor, parseChalk, PROP_ALIASES, PROP_NAMES, purposeWarnings, validateScene } from './contract.mjs'
import { syntaxForLine, syntaxForStep } from './syntax.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const option = (name) => {
  const at = argv.indexOf(name)
  return at >= 0 ? argv[at + 1] : undefined
}
const KINDS = ['.json', '.chalk', '.mmd', '.md']
const asSvg = argv.includes('--svg')
const ext = asSvg ? '.svg' : '.html'
// --snapshots takes a folder only when one follows it (not another option, a recipe or the page).
const snapAt = argv.indexOf('--snapshots')
const snapFolder = snapAt >= 0 && argv[snapAt + 1] && !argv[snapAt + 1].startsWith('--') && ![...KINDS, ext].some((k) => argv[snapAt + 1].endsWith(k)) ? argv[snapAt + 1] : undefined
const valued = new Set(['--out', '--title', '--review-timeout'])
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]) && !(snapFolder && i === snapAt + 1))
const noReview = argv.includes('--no-review')
const timeout = Number(option('--review-timeout') ?? 20)
const sources = args.filter((a) => KINDS.some((k) => a.endsWith(k)))
const outArg = option('--out') ?? args.find((a) => a.endsWith(ext))
const usage = 'usage: node build.mjs <recipe.json> [out.html] [--no-review] [--snapshots [folder]] [--review-timeout <s>]\n       node build.mjs <one.json> <two.json> … --out course.html [--title "…"] [--no-review]\n       node build.mjs <recipe.json> [out.svg] --svg'
if (!sources.length || args.some((a) => !KINDS.some((k) => a.endsWith(k)) && !a.endsWith(ext)) || (outArg && !outArg.endsWith(ext)) || !(timeout > 0) || (asSvg && snapAt >= 0)) {
  console.error(usage)
  process.exit(2)
}

const PROPS = [...PROP_NAMES, ...Object.keys(PROP_ALIASES)]
// The Mermaid converter is large: loaded only for a Mermaid block.
const mermaid = async (text) => (await import('./mermaid.mjs')).fromMermaid(text)

// The text being read and the recipe being checked, so a mistake can show how its line is written.
let reading = ''
let checking
const chalk = (text) => parseChalk((reading = text), PROPS)

/** The recipes a file holds: one for .json, .chalk and .mmd; one per ```chalk-talk / ```mermaid block in a .md. */
async function recipesOf(file) {
  const text = readFileSync(resolve(file), 'utf8')
  if (file.endsWith('.json')) return [JSON.parse(text)]
  if (file.endsWith('.chalk')) return [chalk(text)]
  if (file.endsWith('.mmd')) return [await mermaid(text)]
  const blocks = [...text.matchAll(/^```(chalk-talk|mermaid)[^\n]*\n([\s\S]*?)^```/gm)]
  if (!blocks.length) throw new Error('no ```chalk-talk or ```mermaid block in this file.')
  const out = []
  for (const [, kind, body] of blocks) out.push(kind === 'mermaid' ? await mermaid(body) : chalk(body))
  return out
}

// Lottie (0.16.0): the animations a `lottie` step names — one of the pack, or a file beside the recipe (never a URL) —
// go into the recipe's `lotties`; one from the pack brings its credit. The contract then checks them.
const PACK = ['celebrate', 'think', 'surprised', 'ok', 'idea', 'time']
const NOTO = 'Animated emoji: Noto Animated Emoji by Google, CC BY 4.0 (creativecommons.org/licenses/by/4.0)'
function withLotties(recipe, dir) {
  const found = []
  const walk = (v) => {
    if (Array.isArray(v)) return v.forEach(walk)
    if (!v || typeof v !== 'object') return
    if (v.type === 'lottie' && typeof v.src === 'string') found.push(v.src)
    for (const k of ['steps', 'step']) if (v[k]) walk(v[k])
  }
  walk(recipe.steps)
  if (!found.length) return recipe
  const lotties = { ...(recipe.lotties ?? {}) }
  let pack = false
  for (const src of found) {
    if (lotties[src]) continue
    if (/^[a-z]+:\/\//i.test(src)) throw new Error(`lottie "${src}": an animation comes from a file beside the recipe or from the pack, never from the internet.`)
    if (src.startsWith('.') || src.startsWith('/') || src.endsWith('.json')) {
      const file = resolve(dir, src)
      let text
      try {
        text = readFileSync(file, 'utf8')
      } catch {
        throw new Error(`lottie "${src}": no such file beside the recipe (${file}).`)
      }
      try {
        lotties[src] = JSON.parse(text)
      } catch {
        throw new Error(`lottie "${src}": the file is not JSON.`)
      }
    } else if (PACK.includes(src)) {
      lotties[src] = JSON.parse(readFileSync(join(here, '../assets/lottie', `${src}.json`), 'utf8'))
      pack = true
    } else throw new Error(`lottie "${src}": not in the pack (${PACK.join(', ')}) and not a file (write ./${src}.json for one).`)
  }
  const credits = [...(recipe.credits ?? [])]
  if (pack && !credits.includes(NOTO)) credits.push(NOTO)
  return { ...recipe, lotties, ...(credits.length ? { credits } : {}) }
}

/** How the line or step a mistake names is written, as lines to print under it. */
function example(e) {
  const line = e instanceof ChalkTextError
    ? syntaxForLine(reading.split('\n')[e.line - 1] ?? '', PROPS)
    : syntaxForStep(checking?.steps?.[Number(e.message.match(/^Step (\d+)/)?.[1]) - 1]?.type)
  return line ? `  write it like:\n${line.split('\n').map((l) => `    ${l}`).join('\n')}` : ''
}

const scenes = []
for (const file of sources) {
  try {
    for (const recipe of await recipesOf(file)) scenes.push(validateScene((checking = withLotties(recipe, dirname(resolve(file))))))
  } catch (e) {
    const where = sources.length > 1 || file.endsWith('.md') ? `${basename(file)}: ` : ''
    console.error(`✗ ${e instanceof ChalkTextError ? 'text' : 'contract'}: ${where}${e.message}`)
    const hint = example(e)
    if (hint) console.error(hint)
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
let page = fill(readFileSync(join(here, '../assets/player.html'), 'utf8'), { RECIPE: inline(content) })
// Lottie: the light player goes in only when a lesson has an animation (it is 168 KB).
if (scenes.some((s) => Object.keys(s.lotties ?? {}).length)) {
  const player = readFileSync(join(here, '../assets/lottie_light.js'), 'utf8').replace(/<\/script/gi, '<\\/script')
  page = page.replace('<script type="application/json" id="chalk-recipe">', () => `<script>${player}</script>\n<script type="application/json" id="chalk-recipe">`)
}
writeFileSync(out, page)

// back-of-napkin: what a drawing of its purpose usually misses (a pitch with no ask…) — drawn anyway, to fix like a
// review finding (exit 3).
let warned = false
scenes.forEach((scene, k) => {
  const values = Object.keys(scene.params ?? {}).length + Object.keys(scene.switches ?? {}).length
  const who = course ? `  (${k + 1}) ${scene.title}: ` : '  '
  console.log(`✓ contract${who}${scene.steps.length} steps, ${chaptersFor(scene).length} chapters, ${values} values`)
  // one ready-made animation per drawing reads better (it is polished, not chalk): said, not an error
  const lotties = JSON.stringify(scene.steps).match(/"type":"lottie"/g)?.length ?? 0
  if (lotties > 1) console.log(`• lottie   ${course ? `(${k + 1}) ` : ''}${lotties} animations in one drawing: one reads better (keep the others only if the person asked for them)`)
  for (const w of purposeWarnings(scene)) {
    console.log(`! ${scene.kind.padEnd(9)}${course ? ` (${k + 1})` : ''} ${w.text}`)
    warned = true
  }
})

// Onda C: a figure made with `define` is seen by nobody when the build passes at once (the review measures, it does
// not see): with one, the snapshots are made anyway and the build asks for one look at the contact sheet.
const defined = [...new Set(scenes.flatMap((s) => Object.keys(s.defs ?? {})))]
const snapshots = snapAt >= 0 || (defined.length > 0 && !asSvg)

// One browser for everything the page has to do: the review, the snapshots and the SVGs, lesson by lesson.
const query = (k) => (course ? `lesson=${k + 1}` : '')
const jobs = []
scenes.forEach((_, k) => {
  if (!noReview) jobs.push({ what: 'review', k, file: out, mode: 'review', query: query(k) })
  if (snapshots) jobs.push({ what: 'snapshots', k, file: out, mode: 'snapshots', query: query(k) })
  if (asSvg) jobs.push({ what: 'svg', k, file: out, mode: 'svg', query: query(k) })
})
const ran = jobs.length ? await runPages(jobs, { timeout }) : { results: [] }
const name = (exe) => basename(exe).replace(/\.exe$/i, '')
const result = (what, k) => ran.results?.[jobs.findIndex((j) => j.what === what && j.k === k)]

let code = warned ? 3 : 0
if (noReview) console.log('• review    skipped (--no-review); the page checks itself when opened')
else if (!ran.results) console.log('• review    no Chrome, Chromium or Edge here: the page checks itself when opened')
else {
  for (let k = 0; k < scenes.length; k++) {
    const who = course ? ` (${k + 1})` : ''
    const r = result('review', k)
    if (r.error) console.log(`✗ review${who}    not checked: ${r.error}`)
    else if (!r.problems.length) console.log(`✓ review${who}    ${r.combos} ${r.combos === 1 ? 'setting' : 'settings'}: nothing off the paper, no text over text (${name(ran.used)})`)
    else {
      for (const p of r.problems) console.log(`! review${who}    ${p}`)
      code = 3
    }
  }
}

if (snapshots) {
  const folder = resolve(snapFolder ?? join(dirname(out), `${slug}.snapshots`))
  for (let k = 0; k < scenes.length; k++) {
    const r = result('snapshots', k)
    if (!r || r.error) {
      // asked for: an error; made only for a defined figure: said, and the page is still delivered
      if (snapAt < 0) {
        console.log(`• figures   ${defined.length} defined (${defined.join(', ')}): no browser to draw them here — look at them in the lesson`)
        break
      }
      console.error(`✗ snapshots ${r ? r.error : 'no Chrome, Chromium or Edge here to draw them (set CHROME_PATH)'}`)
      code = 4
      break
    }
    const lesson = slugOf(scenes[k], sources[0])
    const into = course ? join(folder, lesson) : folder
    mkdirSync(into, { recursive: true })
    const png = (file, data) => writeFileSync(join(into, file), Buffer.from(data.replace(/^data:image\/png;base64,/, ''), 'base64'))
    for (const s of r.shots) png(`${lesson}.ch${s.chapter}.${s.label}.png`, s.png)
    const sheet = join(into, `${lesson}.contact-sheet.png`)
    png(`${lesson}.contact-sheet.png`, r.sheet)
    console.log(`→ ${sheet} (${r.chapters} ${r.chapters === 1 ? 'chapter' : 'chapters'} × ${r.settings} ${r.settings === 1 ? 'setting' : 'settings'})`)
    if (defined.length && k === scenes.length - 1) {
      console.log(`• figures   ${defined.length} defined (${defined.join(', ')}): open the contact sheet once and check ${defined.length === 1 ? 'it reads' : 'they read'} right`)
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
  const r = result('svg', k)
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
