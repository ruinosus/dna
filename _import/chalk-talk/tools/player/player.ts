// The page of every chalk-talk HTML file (and of player.js on a CDN): it reads the recipe from the page, checks it and
// mounts the lesson (lesson.ts) — or, for a course, the list of lessons above it. Opened with #review, #snapshot, #svg
// or #still, it does the job of scripts/build.mjs and of the repository's tools instead.
import { playbackBeats, Renderer } from '@engine/renderer'
import { defaultValues, validateScene, type Scene } from '@engine/recipe'
import { PROP_ALIASES, PROP_NAMES } from '@engine/props'
import { parseChalk } from '@engine/text'
import { reviewScene } from '@engine/review'
import { animatedSvg } from '@engine/record'
import { browserLang, fontsLoaded, mountLesson, stillLesson, tag, TEXT } from './lesson'

const lang = browserLang()
const t = TEXT[lang]
document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'

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
  await new Renderer(svg).render(scene, defaultValues(scene), { animate: false })
  report('snapshot', { svg: svg.outerHTML })
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
    if (['review', 'snapshot', 'svg'].includes(mode)) return report(mode, { error: (e as Error).message })
    $('stage').replaceChildren(tag('p', { class: 'broken' }, `${t.broken} ${(e as Error).message}`))
    return
  }
  if (mode === 'review') return review(scene)
  if (mode === 'snapshot') return snapshot(scene)
  if (mode === 'svg') return animated(scene)
  if (mode === 'still') return still(scene)
  document.title = scene.title
  if (course) contents(course)
  await mountLesson($('lesson'), scene, { faces: faces(), lang, keys: 'document' })
}

// A page with only the recipe and this script has no body yet while the script runs: start once it is parsed.
const start = () => {
  mount()
  void main()
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start)
else start()
