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
// To present (back-of-napkin 0.2.0), one lesson only:
//   --present                         the page opens presenting: one chapter at a time, full screen and the speaker
//                                     notes with the first key; PageDown (a clicker) next, PageUp back
//   --pptx [static|steps|video|all]   <id>.pptx: a slide per chapter (static, the default), per beat (steps) or a video
//                                     of each chapter drawing itself (video, MP4); title = the chapter, notes = narration
//   --slides <folder>                 for the Claude Slides type: NN.png and NN.gif per chapter and notes.json
//                                     (--slides-steps adds NN-MM.png per beat)
//   --settings a,b                    a sequence per setting, by the contact sheet's names (default when absent)
//
// Only .html, .svg, .png, .gif, .json and .pptx files are ever written. Exit codes: 0 drawn and checked (or no browser
// to check with); 1 a recipe breaks the contract (nothing written); 2 bad arguments; 3 drawn, but the reviewer found
// something to fix (off the paper, text over text, a line across a text); 4 --svg, --snapshots, --pptx or --slides could
// not be made (no browser, or the browser cannot record MP4) — the page is still written. Needs Node 18
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
const pptxAt = argv.indexOf('--pptx')
const MODES = ['static', 'steps', 'video', 'all']
const pptxMode = pptxAt < 0 ? undefined : MODES.includes(argv[pptxAt + 1]) ? argv[pptxAt + 1] : 'static'
const presenting = argv.includes('--present')
const slidesFolder = option('--slides')
const settings = option('--settings')
const exporting = !!pptxMode || !!slidesFolder
const valued = new Set(['--out', '--title', '--review-timeout', '--slides', '--settings'])
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]) && !(snapFolder && i === snapAt + 1) && !(i === pptxAt + 1 && MODES.includes(a)))
const noReview = argv.includes('--no-review')
const timeout = Number(option('--review-timeout') ?? 20)
const sources = args.filter((a) => KINDS.some((k) => a.endsWith(k)))
const outArg = option('--out') ?? args.find((a) => a.endsWith(ext))
const usage = 'usage: node build.mjs <recipe.json> [out.html] [--no-review] [--snapshots [folder]] [--review-timeout <s>]\n       node build.mjs <recipe> [--present] [--pptx [static|steps|video|all]] [--slides <folder> [--slides-steps]] [--settings a,b]\n       node build.mjs <one.json> <two.json> … --out course.html [--title "…"] [--no-review]\n       node build.mjs <recipe.json> [out.svg] --svg'
const presentsOne = !(presenting || exporting) || (sources.length === 1 && !asSvg)
if (!sources.length || args.some((a) => !KINDS.some((k) => a.endsWith(k)) && !a.endsWith(ext)) || (outArg && !outArg.endsWith(ext)) || !(timeout > 0) || (asSvg && snapAt >= 0) || !presentsOne || (argv.includes('--slides') && !slidesFolder)) {
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
const idOf = (file) => basename(file).replace(/\.[^.]+$/, '').replace(/[^a-z0-9-]+/gi, '-').slice(0, 60) || 'drawing'
async function recipesOf(file) {
  const text = readFileSync(resolve(file), 'utf8')
  if (file.endsWith('.json')) return [JSON.parse(text)]
  // A .chalk file with no `id` line is named after the file (drawing.chalk → drawing.html), not the reader's default.
  if (file.endsWith('.chalk')) return [/^id\s/m.test(text) ? chalk(text) : { ...chalk(text), id: idOf(file) }]
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
// --present: the page opens presenting (the player reads data-present on the body).
if (presenting) page = page.replace('<body>', '<body data-present="1">')
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
// What the PowerPoint and the Slides material are made of: the page draws it all in #export.
const want = new Set()
if (pptxMode === 'all') ['static', 'steps', 'video'].forEach((m) => want.add(m))
else if (pptxMode) want.add(pptxMode)
if (want.has('video')) want.add('static') // the video's cover
if (slidesFolder) ['static', 'gif', ...(argv.includes('--slides-steps') ? ['steps'] : [])].forEach((m) => want.add(m))
if (exporting) jobs.push({ what: 'export', k: 0, file: out, mode: 'export', query: new URLSearchParams({ export: [...want].join(','), ...(settings ? { settings } : {}) }).toString() })
// Recording draws in real time: the export gets the drawing's length per setting, and more.
const drawn = exporting ? scenes[0].steps.reduce((ms, s) => ms + (s.type === 'pause' ? s.ms ?? 600 : 1600), 0) / 1000 : 0
const runs = (settings ? settings.split(',').length : 1) * ((want.has('video') ? 1 : 0) + (want.has('gif') ? 1 : 0))
const ran = jobs.length ? await runPages(jobs, { timeout: Math.max(timeout, exporting ? 60 + drawn * runs * 1.5 : 0) }) : { results: [] }
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

if (exporting) code = Math.max(code, await exportsFrom(result('export', 0)))

if (!asSvg) {
  console.log(`→ ${out} (${Math.round(statSync(out).size / 1024)} KB, opens offline${course ? `, ${scenes.length} lessons` : ''}${presenting ? ', opens presenting' : ''})`)
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

/** The PowerPoint and the Slides material from what the page drew in #export; the exit code they leave (0 or 4). */
async function exportsFrom(r) {
  if (!r || r.error) {
    console.error(`✗ export    ${r ? r.error : 'no Chrome, Chromium or Edge here to draw it (set CHROME_PATH)'}`)
    return 4
  }
  let worst = 0
  const data = (url) => Buffer.from(url.replace(/^data:[^,]*,/, ''), 'base64')
  const many = r.sets.length > 1
  const titled = (title, set) => (many ? `${title} · ${set.name}` : title)
  const notes = (k) => r.notes[k].narration
  if (pptxMode) {
    const { buildPptx, inspectPptx } = await import('./pptx.mjs')
    for (const mode of pptxMode === 'all' ? ['static', 'steps', 'video'] : [pptxMode]) {
      if (mode === 'video' && !String(r.videoType ?? '').startsWith('video/mp4')) {
        console.error('✗ pptx      video: this browser does not record MP4 (PowerPoint needs it) — use static or steps')
        worst = 4
        continue
      }
      const slides = r.sets.flatMap((set) => r.notes.flatMap((n, k) => {
        if (mode === 'static') return [{ title: titled(n.title, set), notes: notes(k), image: set.static[k] }]
        if (mode === 'video') return [{ title: titled(n.title, set), notes: notes(k), video: set.video[k], cover: set.static[k] }]
        return set.steps[k].map((image) => ({ title: titled(n.title, set), notes: notes(k), image }))
      }))
      const file = resolve(dirname(out), `${slug}${pptxMode === 'all' ? `.${mode}` : ''}.pptx`)
      const buffer = await buildPptx({ title: r.title, width: r.width, height: r.height, paper: r.paper, slides })
      writeFileSync(file, buffer)
      // What was made, opened again: every slide, its notes, its media.
      const got = await inspectPptx(buffer)
      const media = mode === 'video' ? got.media.mp4 : got.media.png
      if (got.slides !== slides.length || got.notes < slides.filter((s) => s.notes).length || media < (mode === 'video' ? slides.length : 1)) {
        console.error(`✗ pptx      ${mode}: ${got.slides} slides, ${got.notes} notes, ${media} media (expected ${slides.length})`)
        worst = 4
        continue
      }
      const mb = buffer.length / 1048576
      console.log(`→ ${file} (${mode}: ${slides.length} slides with notes, ${mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.round(buffer.length / 1024)} KB`})`)
      if (mb > 50) console.log(`! pptx      ${Math.round(mb)} MB: large to send by e-mail — static or steps is lighter`)
    }
  }
  if (slidesFolder) {
    const two = (n) => String(n).padStart(2, '0')
    for (const set of r.sets) {
      const into = resolve(slidesFolder, many ? set.name : '')
      mkdirSync(into, { recursive: true })
      r.notes.forEach((_, k) => {
        writeFileSync(join(into, `${two(k + 1)}.png`), data(set.static[k]))
        writeFileSync(join(into, `${two(k + 1)}.gif`), data(set.gif[k]))
        set.steps?.[k].forEach((png, b) => writeFileSync(join(into, `${two(k + 1)}-${two(b + 1)}.png`), data(png)))
      })
      writeFileSync(join(into, 'notes.json'), JSON.stringify(r.notes.map((n, k) => ({ chapter: k + 1, ...n })), null, 2))
      console.log(`→ ${into} (${r.notes.length} chapters: NN.png, NN.gif${set.steps ? ', NN-MM.png' : ''} and notes.json, for the Slides type)`)
    }
  }
  return worst
}
