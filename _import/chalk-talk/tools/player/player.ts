// The page of every chalk-talk HTML file (and of player.js on a CDN): it reads the recipe from the page, checks it and
// mounts the lesson (lesson.ts) — or, for a course, the list of lessons above it. Opened with #review, #snapshot,
// #snapshots, #svg, #still or #export, it does the job of scripts/build.mjs and of the repository's tools instead; with
// #present it opens presenting.
import { buildScope, playbackBeats, Renderer, setLottiePlayer, type LottiePlayer } from '@engine/renderer'
import { chaptersFor, defaultValues, validateScene, type Scene } from '@engine/recipe'
import { PROP_ALIASES, PROP_NAMES } from '@engine/props'
import { parseChalk } from '@engine/text'
import { combinations, reviewScene } from '@engine/review'
import { animatedSvg, playFrames, recordVideo, videoType } from '@engine/record'
import { formatNumber, interpolate } from '@engine/expr'
import { applyPalette, GIFEncoder, quantize } from 'gifenc'
import { browserLang, fontsLoaded, langOf, mountLesson, stillLesson, svgText, tag, TEXT } from './lesson'

// Lottie: the build puts lottie-web's light player before this script only when the lesson has an animation.
declare const lottie: LottiePlayer | undefined
if (typeof lottie !== 'undefined') setLottiePlayer(lottie)

// Until the recipe is read (a broken one says so in the browser's language); then the recipe's `locale` rules.
const t = TEXT[browserLang()]

// Onda 4: the player loaded on its own (npm / CDN) brings the page around the recipe — its markup, styles and fonts;
// inside a built file (assets/player.html) they are already on the page and this is null.
declare const __CHALK_SHELL__: { body: string; css: string; fonts: string } | null

function mount() {
  if (!__CHALK_SHELL__ || document.getElementById('stage')) return
  const fonts = document.createElement('style')
  fonts.id = 'chalk-fonts'
  fonts.textContent = __CHALK_SHELL__.fonts
  const css = document.createElement('style')
  css.textContent = __CHALK_SHELL__.css
  document.head.append(fonts, css)
  if (!document.querySelector('meta[name=viewport]')) document.head.append(Object.assign(document.createElement('meta'), { name: 'viewport', content: 'width=device-width, initial-scale=1' }))
  document.body.insertAdjacentHTML('afterbegin', __CHALK_SHELL__.body)
}

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
const faces = () => $('chalk-fonts')?.textContent ?? ''

// Onda 4: the page holds one recipe, or a course — { course, lessons } — of which `?lesson=n` is the one shown.
interface Course { title: string; lessons: Scene[]; at: number }

function readRecipe(): { scene: Scene; course?: Course } {
  const holder = $('chalk-recipe')
  // The recipe may come as text (<script type="text/chalk-talk">) instead of JSON.
  const raw = holder.getAttribute('type') === 'text/chalk-talk'
    ? parseChalk(holder.textContent ?? '', [...PROP_NAMES, ...Object.keys(PROP_ALIASES)])
    : JSON.parse(holder.textContent ?? '')
  if (!raw || !Array.isArray(raw.lessons)) return { scene: validateScene(raw) }
  const lessons = (raw.lessons as unknown[]).map((l) => validateScene(l))
  const wanted = Number(new URLSearchParams(location.search).get('lesson'))
  const at = Number.isInteger(wanted) && wanted >= 1 && wanted <= lessons.length ? wanted - 1 : 0
  return { scene: lessons[at], course: { title: String(raw.course ?? lessons[0].title), lessons, at } }
}

/** The list of the course's lessons; each is a link to the same page with `?lesson=n`. */
function contents(course: Course) {
  const nav = $('course')
  nav.hidden = false
  nav.append(tag('b', {}, course.title))
  const list = tag('ol')
  course.lessons.forEach((lesson, k) => {
    const item = tag('li')
    const link = tag('a', { href: `?lesson=${k + 1}` }, lesson.title)
    if (k === course.at) link.setAttribute('aria-current', 'page')
    item.append(link)
    list.append(item)
  })
  nav.append(list)
}

/** What a headless browser reads back: <pre id="chalk-<mode>"> with the result as JSON. */
function report(mode: string, result: unknown) {
  document.body.append(tag('pre', { id: `chalk-${mode}` }, encodeURIComponent(JSON.stringify(result))))
}

const offPaper = () => {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  document.body.append(svg)
  return svg
}

// ---------- #review: what scripts/build.mjs reads from a headless browser ----------
async function review(scene: Scene) {
  await fontsLoaded()
  report('review', await reviewScene(scene))
}

// ---------- #snapshot: the whole drawing at its starting values, for the regression gallery (tools/snapshots.mjs) ----------
async function snapshot(scene: Scene) {
  const svg = offPaper()
  // At the recipe's own size, so the measures of the texts do not depend on the window.
  svg.style.width = `${scene.width}px`
  svg.id = 'paper'
  svg.setAttribute('role', 'img')
  await fontsLoaded()
  await new Renderer(svg).render(scene, defaultValues(scene), { animate: false, motion: 'rest' })
  report('snapshot', { svg: svg.outerHTML })
}

// ---------- #snapshots: pictures for whoever wrote the recipe to look at (build.mjs --snapshots) ----------
// Each chapter as it ends, at each setting the reviewer draws (the defaults, each switch flipped, each control at its
// ends), as PNG; and a contact sheet of them all: a row per chapter, a column per setting.
const TILE = 300
async function snapshots(scene: Scene) {
  const svg = offPaper()
  svg.style.width = `${scene.width}px`
  await fontsLoaded()
  const renderer = new Renderer(svg)
  const chapters = chaptersFor(scene)
  const settings = combinations(scene)
  const label = settingName(scene)
  const shots: { chapter: number; title: string; label: string; at: string; png: string; image: HTMLImageElement }[] = []
  for (const [k, chapter] of chapters.entries()) {
    for (const values of settings) {
      await renderer.render(scene, values, { animate: false, until: chapter.end, motion: 'rest' })
      const image = await picture(svgText(svg, faces()))
      const at = Object.entries(values).map(([n, v]) => `${n}=${v}`).join(', ')
      shots.push({ chapter: k + 1, title: chapter.title, label: label(values), at, png: toPng(image, scene.width, scene.height, paperColour(scene)), image })
    }
  }
  report('snapshots', {
    chapters: chapters.length,
    settings: settings.length,
    shots: shots.map(({ image: _, ...s }) => s), // eslint-disable-line @typescript-eslint/no-unused-vars -- not sent
    sheet: contactSheet(scene, chapters.map((c) => c.title), settings.map(label), shots.map((s) => s.image)),
  })
}

/** The name of a setting, as the contact sheet heads its column: default, a switch on or off, a control at min or max. */
function settingName(scene: Scene) {
  const base = defaultValues(scene)
  return (values: Record<string, number>) => {
    const changed = Object.keys(values).find((k) => values[k] !== base[k])
    if (!changed) return 'default'
    if (scene.switches?.[changed]) return `${changed}-${values[changed] ? 'on' : 'off'}`
    return `${changed}-${values[changed] === scene.params?.[changed]?.min ? 'min' : 'max'}`
  }
}

/** A setting as a person reads it, for a slide title: '' for the default, a switch's label and on/off, a control's
 * label and its value — in the recipe's language. */
function settingLabel(scene: Scene) {
  const base = defaultValues(scene)
  const w = TEXT[langOf(scene)]
  return (values: Record<string, number>) => {
    const changed = Object.keys(values).find((k) => values[k] !== base[k])
    if (!changed) return ''
    const sw = scene.switches?.[changed]
    if (sw) return `${sw.label}: ${values[changed] ? w.on : w.off}`
    return `${scene.params?.[changed]?.label ?? changed}: ${formatNumber(values[changed], undefined, scene.locale)}`
  }
}

const paperColour = (scene: Scene) => (scene.theme === 'chalkboard' ? '#26372E' : '#FBF7EE')

/** An SVG text as an image (a data: URL — a blob: one does not draw on a canvas from a file page). */
function picture(svg: string): Promise<HTMLImageElement> {
  return new Promise((ok, fail) => {
    const img = new Image()
    img.onload = () => ok(img)
    img.onerror = () => fail(new Error('a snapshot did not draw'))
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
  })
}

function toPng(img: HTMLImageElement, width: number, height: number, paper: string): string {
  const canvas = tag('canvas', { width: String(width), height: String(height) }) as HTMLCanvasElement
  const g = canvas.getContext('2d')!
  g.fillStyle = paper
  g.fillRect(0, 0, width, height)
  g.drawImage(img, 0, 0, width, height)
  return canvas.toDataURL('image/png')
}

/** The pictures in a grid: the settings across, the chapters down, each named. */
function contactSheet(scene: Scene, chapters: string[], settings: string[], images: HTMLImageElement[]): string {
  const h = Math.round((TILE * scene.height) / scene.width)
  const gap = 16
  const left = 150
  const top = 44
  const canvas = tag('canvas', {
    width: String(left + settings.length * (TILE + gap)),
    height: String(top + chapters.length * (h + gap)),
  }) as HTMLCanvasElement
  const g = canvas.getContext('2d')!
  g.fillStyle = '#FFFFFF'
  g.fillRect(0, 0, canvas.width, canvas.height)
  g.fillStyle = '#242424'
  g.font = '15px sans-serif'
  settings.forEach((s, c) => g.fillText(s, left + c * (TILE + gap), 28))
  chapters.forEach((title, r) => {
    const y = top + r * (h + gap)
    g.fillStyle = '#242424'
    wrapText(g, `${r + 1}. ${title}`, 8, y + 18, left - 16, 18)
    settings.forEach((_, c) => {
      const x = left + c * (TILE + gap)
      g.fillStyle = paperColour(scene)
      g.fillRect(x, y, TILE, h)
      g.drawImage(images[r * settings.length + c], x, y, TILE, h)
      g.strokeStyle = '#D8D2C4'
      g.strokeRect(x + 0.5, y + 0.5, TILE - 1, h - 1)
    })
  })
  return canvas.toDataURL('image/png')
}

function wrapText(g: CanvasRenderingContext2D, text: string, x: number, y: number, width: number, line: number) {
  let row = ''
  for (const word of text.split(' ')) {
    if (row && g.measureText(`${row} ${word}`).width > width) {
      g.fillText(row, x, y)
      row = word
      y += line
    } else row = row ? `${row} ${word}` : word
  }
  if (row) g.fillText(row, x, y)
}

// ---------- #svg: the drawing as an SVG that draws itself with no script (build.mjs --svg) ----------
async function animated(scene: Scene) {
  await fontsLoaded()
  try {
    const ms = playbackBeats(scene).reduce((sum, b) => sum + b.duration, 0)
    report('svg', { svg: await animatedSvg(scene, defaultValues(scene), faces()), ms })
  } catch (e) {
    report('svg', { error: (e as Error).message })
  }
}

// ---------- #export: what build.mjs makes a PowerPoint or the Slides material from (back-of-napkin 0.2.0) ----------
// ?export=static,steps,video,gif and ?settings=default,d-max (the contact sheet's names; default when absent). For each
// setting and chapter: the chapter drawn (PNG), each of its beats (PNG), the chapter drawing itself (MP4, else WebM) and
// as a GIF; and each chapter's title and narration, for the notes.
const asData = (blob: Blob) => new Promise<string>((ok) => {
  const r = new FileReader()
  r.onload = () => ok(String(r.result))
  r.readAsDataURL(blob)
})

async function exported(scene: Scene) {
  const query = new URLSearchParams(location.search)
  const want = new Set((query.get('export') ?? 'static').split(','))
  const named = settingName(scene)
  const labelled = settingLabel(scene)
  const all = combinations(scene)
  const asked = (query.get('settings') ?? 'default').split(',')
  const missing = asked.filter((n) => !all.some((v) => named(v) === n))
  if (missing.length) return report('export', { error: `no setting called ${missing.join(', ')}: the contact sheet names them (${all.map(named).join(', ')})` })
  await fontsLoaded()
  const chapters = chaptersFor(scene)
  const svg = offPaper()
  svg.style.width = `${scene.width}px`
  const renderer = new Renderer(svg)
  const paper = paperColour(scene)
  const shot = async () => toPng(await picture(svgText(svg, faces())), scene.width * 2, scene.height * 2, paper)
  const notes = chapters.map((c, k) => {
    const scope = buildScope(scene, defaultValues(scene))
    const says = scene.steps.slice(c.start, c.end + 1).flatMap((s) => [s.say, s.type === 'pause' ? s.ask : undefined].filter((x): x is string => !!x))
    return { title: c.title, narration: says.map((x) => interpolate(x, scope, scene.locale)).join(' '), next: chapters[k + 1]?.title ?? null }
  })
  const sets = []
  for (const name of asked) {
    const values = all.find((v) => named(v) === name)!
    const set: Record<string, unknown> = { name, label: labelled(values) }
    if (want.has('static')) {
      const pngs = []
      for (const c of chapters) {
        await renderer.render(scene, values, { animate: false, until: c.end, motion: 'rest' })
        pngs.push(await shot())
      }
      set.static = pngs
    }
    if (want.has('steps')) {
      const per = []
      for (const c of chapters) {
        const pngs = []
        for (const b of playbackBeats(scene, c.end).filter((b) => b.start >= c.start)) {
          await renderer.render(scene, values, { animate: false, until: b.end, motion: 'rest' })
          pngs.push(await shot())
        }
        per.push(pngs)
      }
      set.steps = per
    }
    if (want.has('video')) {
      const videos = []
      for (const c of chapters) videos.push(await asData(await recordVideo(scene, values, { faces: faces(), paper, prefer: 'mp4', from: c.start, until: c.end })))
      set.video = videos
    }
    if (want.has('gif')) {
      const gifs = []
      for (const c of chapters) {
        const gif = GIFEncoder()
        await playFrames(scene, values, { faces: faces(), paper, fps: 8, scale: 0.6, from: c.start, until: c.end }, (canvas) => {
          const { data } = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height)
          const palette = quantize(data, 64)
          gif.writeFrame(applyPalette(data, palette), canvas.width, canvas.height, { palette, delay: 125 })
        })
        gif.finish()
        gifs.push(await asData(new Blob([gif.bytes()], { type: 'image/gif' })))
      }
      set.gif = gifs
    }
    sets.push(set)
  }
  report('export', { title: scene.title, width: scene.width, height: scene.height, paper, notes, sets, videoType: 'MediaRecorder' in window ? videoType('mp4') ?? null : null })
}

// ---------- #still: only the paper, the whole drawing, for a picture of it (tools/site.mjs) ----------
async function still(scene: Scene) {
  document.body.classList.add('still')
  await stillLesson($('stage'), scene)
  document.body.dataset.ready = '1'
}

async function main() {
  let scene: Scene
  let course: Course | undefined
  const mode = location.hash.slice(1)
  try {
    ;({ scene, course } = readRecipe())
  } catch (e) {
    if (['review', 'snapshot', 'snapshots', 'svg', 'export'].includes(mode)) return report(mode, { error: (e as Error).message })
    $('stage').replaceChildren(tag('p', { class: 'broken' }, `${t.broken} ${(e as Error).message}`))
    return
  }
  if (mode === 'review') return review(scene)
  if (mode === 'snapshot') return snapshot(scene)
  if (mode === 'snapshots') return snapshots(scene)
  if (mode === 'svg') return animated(scene)
  if (mode === 'still') return still(scene)
  if (mode === 'export') return exported(scene).catch((e) => report('export', { error: (e as Error).message }))
  document.title = scene.title
  const lang = langOf(scene)
  document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
  if (course) contents(course)
  await mountLesson($('lesson'), scene, { faces: faces(), lang, keys: 'document', present: mode === 'present' || document.body.dataset.present === '1' })
}

// A page with only the recipe and this script has no body yet while the script runs: start once it is parsed.
const start = () => {
  mount()
  void main()
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start)
else start()
