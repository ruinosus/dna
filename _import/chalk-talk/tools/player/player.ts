// The player inside every chalk-talk HTML file. It reads the recipe from the page, checks it, and plays it chapter by
// chapter with the drawing engine (Renderer, chapters, reviewer). It is not a second engine: it only builds
// the page around the drawing. Opened with #review, it runs the reviewer and writes the result for scripts/build.mjs.
import { buildScope, Renderer, type Theme } from '@engine/renderer'
import { chaptersFor, defaultValues, validateScene, type Scene } from '@engine/recipe'
import { reviewScene } from '@engine/review'
import { formatNumber, interpolate } from '@engine/expr'
import { playFrames, recordWebm } from '@engine/record'
import { applyPalette, GIFEncoder, quantize } from 'gifenc'

const TEXT = {
  en: {
    start: 'Start', back: 'Back', next: 'Next', playAll: 'Play all', chapter: (n: number, of: number) => `Chapter ${n} of ${of}`,
    values: 'Move the values', think: 'Think about it', answer: 'One possible answer', caveat: 'Where the comparison stops',
    download: 'Download', checking: 'Checking the drawing…',
    checked: (n: number) => `Checked at ${n} ${n === 1 ? 'setting' : 'settings'}: nothing leaves the paper and no text covers another.`,
    problems: 'The check found:', broken: 'This drawing could not be opened:', keys: '→ next · ← back · Space play all', made: 'Made with chalk-talk',
    board: 'Chalkboard', voice: 'Narration', recording: (p: number) => `Recording… ${p}%`, show: 'Show me', yourTurn: 'Your turn', transcript: 'Transcript', again: 'Try another',
  },
  pt: {
    start: 'Início', back: 'Voltar', next: 'Próximo', playAll: 'Tocar tudo', chapter: (n: number, of: number) => `Capítulo ${n} de ${of}`,
    values: 'Mexa nos valores', think: 'Para pensar', answer: 'Uma resposta possível', caveat: 'Onde a comparação para',
    download: 'Baixar', checking: 'Conferindo o desenho…',
    checked: (n: number) => `Conferido em ${n} ${n === 1 ? 'posição' : 'posições'}: nada sai do papel e nenhum texto cobre outro.`,
    problems: 'A conferência achou:', broken: 'Este desenho não pôde ser aberto:', keys: '→ próximo · ← voltar · Espaço tocar tudo', made: 'Feito com chalk-talk',
    board: 'Quadro-negro', voice: 'Narração', recording: (p: number) => `Gravando… ${p}%`, show: 'Mostrar', yourTurn: 'Sua vez', transcript: 'Transcrição', again: 'Tentar outra',
  },
}
const pt = navigator.language.toLowerCase().startsWith('pt')
const t = pt ? TEXT.pt : TEXT.en
document.documentElement.lang = pt ? 'pt-BR' : 'en'

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
function tag<K extends keyof HTMLElementTagNameMap>(name: K, attrs: Record<string, string> = {}, text = ''): HTMLElementTagNameMap[K] {
  const node = document.createElement(name)
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v)
  // Everything from the recipe is text, never markup.
  if (text) node.textContent = text
  return node
}

// document.fonts.ready does not wait for a face nothing has used yet: load the embedded ones before measuring.
const fontsLoaded = () => Promise.all([...document.fonts].map((f) => f.load())).catch(() => undefined)

// Onda 4: the page holds one recipe, or a course — { course, lessons } — of which `?lesson=n` is the one shown.
interface Course { title: string; lessons: Scene[]; at: number }

function readRecipe(): { scene: Scene; course?: Course } {
  const raw = JSON.parse($('chalk-recipe').textContent ?? '')
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

// ---------- #review: what scripts/build.mjs reads from a headless browser ----------
async function review(scene: Scene) {
  const out = tag('pre', { id: 'chalk-review' })
  document.body.append(out)
  await fontsLoaded()
  const r = await reviewScene(scene)
  out.textContent = encodeURIComponent(JSON.stringify(r))
}

// ---------- #snapshot: the whole drawing at its starting values, for the regression gallery (tools/snapshots.mjs) ----------
async function snapshot(scene: Scene) {
  const svg = document.querySelector<SVGSVGElement>('#paper')!
  await fontsLoaded()
  await new Renderer(svg).render(scene, defaultValues(scene), { animate: false })
  document.body.append(tag('pre', { id: 'chalk-snapshot' }, encodeURIComponent(JSON.stringify({ svg: svg.outerHTML }))))
}

// ---------- #still: only the paper, the whole drawing, for a picture of it (tools/site.mjs) ----------
async function still(scene: Scene) {
  document.body.classList.add('still')
  document.querySelector('.paper')!.classList.toggle('is-board', scene.theme === 'chalkboard')
  const svg = document.querySelector<SVGSVGElement>('#paper')!
  await fontsLoaded()
  await new Renderer(svg).render(scene, defaultValues(scene), { animate: false })
  document.body.dataset.ready = '1'
}

// ---------- the page ----------
async function play(scene: Scene) {
  document.title = scene.title
  $('category').textContent = scene.category ?? ''
  $('title').textContent = scene.title
  const chapters = chaptersFor(scene, t.start)
  const svg = document.querySelector<SVGSVGElement>('#paper')!
  const say = $('say')
  const renderer = new Renderer(svg, (text) => (say.textContent = text))
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches
  const values = defaultValues(scene)
  let at = 0
  let run = 0
  let theme: Theme = scene.theme ?? 'paper'
  let speaking = false

  const chips = chapters.map((c, i) => {
    const b = tag('button', { type: 'button' }, `${i + 1} · ${c.title}`)
    b.addEventListener('click', () => go(i, i === at + 1))
    $('chapters').append(b)
    return b
  })
  ;($('back') as HTMLButtonElement).textContent = `◀ ${t.back}`
  ;($('next') as HTMLButtonElement).textContent = `${t.next} ▶`
  ;($('all') as HTMLButtonElement).textContent = t.playAll
  $('keys').textContent = t.keys
  $('made').textContent = t.made

  function paint() {
    chips.forEach((b, i) => {
      b.className = i === at ? 'is-on' : i < at ? 'is-seen' : ''
      b.setAttribute('aria-current', i === at ? 'step' : 'false')
    })
    $('count').textContent = t.chapter(at + 1, chapters.length)
    ;($('back') as HTMLButtonElement).disabled = at === 0
    ;($('next') as HTMLButtonElement).disabled = at === chapters.length - 1
  }

  // Before a beat is drawn: a pause with `ask` waits for the person; with narration on, the beat's sentence is spoken.
  async function beat(text: string | undefined, start: number, mine: number) {
    const step = scene.steps[start]
    if (step.type === 'pause' && step.ask) await asked(interpolate(step.ask, buildScope(scene, values), scene.locale))
    if (mine === run && speaking && text) await speak(text, scene.locale ?? 'pt-BR')
  }

  function paper() {
    document.querySelector('.paper')!.classList.toggle('is-board', theme === 'chalkboard')
    $('board').setAttribute('aria-pressed', String(theme === 'chalkboard'))
  }

  // Draws up to chapter i: animated from where the last chapter ended when going forward one, at once otherwise.
  async function go(i: number, animate: boolean, from?: number) {
    at = Math.max(0, Math.min(chapters.length - 1, i))
    paint()
    const mine = ++run
    try {
      await renderer.render(scene, values, {
        animate: animate && !still,
        until: chapters[at].end,
        from: from ?? (at > 0 ? chapters[at - 1].end + 1 : 0),
        theme,
        beforeBeat: (text, start) => beat(text, start, mine),
      })
      if (mine === run && at === chapters.length - 1) quiz(scene)
    } catch (e) {
      // A newer drawing took over (another click, a value moved): nothing to show.
      if (mine === run) throw e
    }
  }

  ;($('board') as HTMLButtonElement).textContent = t.board
  $('board').addEventListener('click', () => {
    theme = theme === 'chalkboard' ? 'paper' : 'chalkboard'
    paper()
    go(at, false)
  })
  paper()
  if ('speechSynthesis' in window) {
    ;($('voice') as HTMLButtonElement).textContent = `🔈 ${t.voice}`
    $('voice').addEventListener('click', () => {
      speaking = !speaking
      $('voice').setAttribute('aria-pressed', String(speaking))
      if (!speaking) speechSynthesis.cancel()
    })
  } else $('voice').remove()
  $('back').addEventListener('click', () => go(at - 1, false))
  $('next').addEventListener('click', () => go(at + 1, true))
  $('all').addEventListener('click', () => go(chapters.length - 1, true, 0))
  document.addEventListener('keydown', (e) => {
    if ((e.target as HTMLElement).closest('input, button, summary')) return
    if (e.key === 'ArrowRight') go(at + 1, true)
    else if (e.key === 'ArrowLeft') go(at - 1, false)
    else if (e.key === ' ') {
      e.preventDefault()
      go(chapters.length - 1, true, 0)
    }
  })

  controls(scene, values, () => go(at, false))
  learning(scene)
  transcript(scene, chapters)
  downloads(scene, svg, () => theme)
  await fontsLoaded()
  // The check draws hidden on its own paper: it does not wait for the lesson (a question may be waiting for a click).
  void check(scene)
  await go(0, true)
}

function controls(scene: Scene, values: Record<string, number>, redraw: () => void) {
  const box = $('controls')
  const params = Object.entries(scene.params ?? {})
  const switches = Object.entries(scene.switches ?? {})
  if (!params.length && !switches.length) return box.remove()
  box.append(tag('h2', {}, t.values))
  for (const [key, p] of params) {
    const label = tag('label', { class: 'value' })
    const shown = tag('b', {}, formatNumber(values[key], undefined, scene.locale))
    const input = tag('input', { type: 'range', min: String(p.min), max: String(p.max), step: String(p.step), value: String(values[key]) })
    input.addEventListener('input', () => {
      values[key] = Number(input.value)
      shown.textContent = formatNumber(values[key], undefined, scene.locale)
      redraw()
    })
    label.append(tag('span', {}, p.label), shown, input)
    box.append(label)
  }
  for (const [key, s] of switches) {
    const label = tag('label', { class: 'switch' })
    const input = tag('input', { type: 'checkbox' })
    input.checked = values[key] === 1
    input.addEventListener('change', () => {
      values[key] = input.checked ? 1 : 0
      redraw()
    })
    label.append(input, tag('span', {}, s.label))
    box.append(label)
  }
}

function learning(scene: Scene) {
  const box = $('learning')
  const l = scene.learning
  if (!l) return box.remove()
  const answer = tag('details')
  answer.append(tag('summary', {}, t.answer), tag('p', {}, l.answer))
  box.append(tag('h2', {}, t.think), tag('p', {}, l.question), answer, tag('p', { class: 'caveat' }, `${t.caveat}: ${l.caveat}`))
}

// ---------- onda 3: a question that waits, the voice, the quiz, the transcript ----------

/** Shows the pause's question over the paper and waits for «Show me». */
function asked(question: string): Promise<void> {
  const box = $('ask')
  box.replaceChildren(tag('p', {}, question))
  const show = tag('button', { type: 'button', class: 'primary' }, t.show)
  box.append(show)
  box.hidden = false
  show.focus()
  return new Promise((resolve) => show.addEventListener('click', () => {
    box.hidden = true
    resolve()
  }, { once: true }))
}

/** Says a sentence with the browser's own voice for the recipe's language; never waits more than 20 s. */
function speak(text: string, lang: string): Promise<void> {
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text)
    u.lang = lang
    const voice = speechSynthesis.getVoices().find((v) => v.lang.toLowerCase().startsWith(lang.toLowerCase().slice(0, 2)))
    if (voice) u.voice = voice
    const done = () => resolve()
    u.onend = done
    u.onerror = done
    setTimeout(done, 20000)
    speechSynthesis.speak(u)
  })
}

/** The question at the end, once the last chapter is drawn: pick one, see why. */
function quiz(scene: Scene) {
  const box = $('quiz')
  if (!scene.quiz || box.childElementCount) return
  box.hidden = false
  const why = tag('p', { class: 'why', role: 'status' })
  const options = tag('div', { class: 'options' })
  for (const o of scene.quiz.options) {
    const b = tag('button', { type: 'button' }, o.text)
    b.addEventListener('click', () => {
      options.querySelectorAll('button').forEach((x) => x.classList.remove('is-right', 'is-wrong'))
      b.classList.add(o.right ? 'is-right' : 'is-wrong')
      why.textContent = o.why
      why.className = o.right ? 'why is-right' : 'why'
    })
    options.append(b)
  }
  box.append(tag('h2', {}, t.yourTurn), tag('p', {}, scene.quiz.question), options, why)
}

/** Everything the lesson says, in order, by chapter — for reading and for screen readers. */
function transcript(scene: Scene, chapters: { title: string; start: number; end: number }[]) {
  const box = $('transcript')
  const scope = buildScope(scene, defaultValues(scene))
  const list = tag('ol')
  for (const c of chapters) {
    const says = scene.steps.slice(c.start, c.end + 1).flatMap((s) => [s.say, s.type === 'pause' ? s.ask : undefined].filter((x): x is string => !!x))
    const item = tag('li')
    item.append(tag('b', {}, c.title))
    for (const line of says) item.append(tag('p', {}, interpolate(line, scope, scene.locale)))
    list.append(item)
  }
  box.append(tag('summary', {}, t.transcript), list)
}

// ---------- download: the paper as SVG (with its fonts) or PNG ----------
function svgText(svg: SVGSVGElement): string {
  const copy = svg.cloneNode(true) as SVGSVGElement
  copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  const style = document.createElementNS('http://www.w3.org/2000/svg', 'style')
  style.textContent = $('chalk-fonts').textContent ?? ''
  copy.prepend(style)
  return new XMLSerializer().serializeToString(copy)
}

function save(blob: Blob, name: string) {
  const a = tag('a', { href: URL.createObjectURL(blob), download: name })
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

function downloads(scene: Scene, svg: SVGSVGElement, theme: () => Theme) {
  const box = $('downloads')
  box.prepend(tag('span', {}, t.download))
  const name = (ext: string) => `${(scene.id || 'drawing').replace(/[^a-z0-9-]+/gi, '-').slice(0, 60)}.${ext}`
  $('svg').addEventListener('click', () => save(new Blob([svgText(svg)], { type: 'image/svg+xml' }), name('svg')))
  // Onda 4: the lesson drawing itself, recorded out of sight with the engine's recorder (drawing/record.ts).
  const faces = $('chalk-fonts').textContent ?? ''
  const recording = (button: HTMLButtonElement, make: (progress: (f: number) => void) => Promise<Blob>, ext: string) =>
    button.addEventListener('click', async () => {
      const label = button.textContent
      document.querySelectorAll<HTMLButtonElement>('#downloads button').forEach((b) => (b.disabled = true))
      try {
        save(await make((f) => (button.textContent = t.recording(Math.round(f * 100)))), name(ext))
      } finally {
        button.textContent = label
        document.querySelectorAll<HTMLButtonElement>('#downloads button').forEach((b) => (b.disabled = false))
      }
    })
  const paper = () => (theme() === 'chalkboard' ? '#26372E' : '#FBF7EE')
  if ('MediaRecorder' in window) {
    recording($('webm') as HTMLButtonElement, (onProgress) => recordWebm(scene, defaultValues(scene), { faces, paper: paper(), theme: theme(), onProgress }), 'webm')
  } else $('webm').remove()
  recording($('gif') as HTMLButtonElement, async (onProgress) => {
    const gif = GIFEncoder()
    await playFrames(scene, defaultValues(scene), { faces, paper: paper(), theme: theme(), onProgress, fps: 8, scale: 0.6 }, (canvas) => {
      const { data } = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height)
      const palette = quantize(data, 64)
      gif.writeFrame(applyPalette(data, palette), canvas.width, canvas.height, { palette, delay: 125 })
    })
    gif.finish()
    return new Blob([gif.bytes()], { type: 'image/gif' })
  }, 'gif')
  $('png').addEventListener('click', () => {
    const img = new Image()
    img.onload = () => {
      const canvas = tag('canvas', { width: String(scene.width * 2), height: String(scene.height * 2) })
      canvas.getContext('2d')!.drawImage(img, 0, 0, scene.width * 2, scene.height * 2)
      canvas.toBlob((b) => b && save(b, name('png')), 'image/png')
    }
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgText(svg))
  })
}

// ---------- the check, hidden, after the first chapter ----------
async function check(scene: Scene) {
  const box = $('check')
  box.textContent = t.checking
  const r = await reviewScene(scene)
  box.className = r.problems.length ? 'check is-warn' : 'check is-ok'
  if (!r.problems.length) return void (box.textContent = `✓ ${t.checked(r.combos)}`)
  box.textContent = ''
  const list = tag('ul')
  for (const p of r.problems) list.append(tag('li', {}, p))
  box.append(tag('b', {}, `! ${t.problems}`), list)
}

async function main() {
  let scene: Scene
  let course: Course | undefined
  try {
    ;({ scene, course } = readRecipe())
  } catch (e) {
    if (location.hash === '#review' || location.hash === '#snapshot') {
      const out = tag('pre', { id: `chalk-${location.hash.slice(1)}` }, encodeURIComponent(JSON.stringify({ error: (e as Error).message })))
      return void document.body.append(out)
    }
    const main = $('stage')
    main.replaceChildren(tag('p', { class: 'broken' }, `${t.broken} ${(e as Error).message}`))
    return
  }
  if (location.hash === '#review') return review(scene)
  if (location.hash === '#snapshot') return snapshot(scene)
  if (location.hash === '#still') return still(scene)
  if (course) contents(course)
  await play(scene)
}

void main()
