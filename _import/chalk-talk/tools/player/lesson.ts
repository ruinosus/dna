// One lesson mounted inside an element: chapters, Next / Back, the narration, the values, the question that waits, the
// quiz, the check and the downloads, around the drawing engine (Renderer, chapters, reviewer). It is not a second
// engine: it only builds the lesson around the drawing. Nothing is global (no ids, styles under .chalk-talk), so a page
// can hold several — the HTML file holds one, an Obsidian note as many as it has blocks.
// Spec 2026-10-30 (chalk-talk no Obsidian): `compact` is the lesson inside a note — chapters, Values and Expand on top,
// the bar below, nothing beside it; it opens on chapter 1 drawn and still.
import { buildScope, Renderer, type Theme } from '@engine/renderer'
import { chaptersFor, defaultValues, type Scene } from '@engine/recipe'
import { reviewScene } from '@engine/review'
import { formatNumber, interpolate } from '@engine/expr'
import { playFrames, recordWebm } from '@engine/record'
import { applyPalette, GIFEncoder, quantize } from 'gifenc'

export const TEXT = {
  en: {
    start: 'Start', back: 'Back', next: 'Next', playAll: 'Play all', chapter: (n: number, of: number) => `Chapter ${n} of ${of}`,
    values: 'Move the values', think: 'Think about it', answer: 'One possible answer', caveat: 'Where the comparison stops',
    download: 'Download', checking: 'Checking the drawing…',
    checked: (n: number) => `Checked at ${n} ${n === 1 ? 'setting' : 'settings'}: nothing leaves the paper and no text covers another.`,
    problems: 'The check found:', broken: 'This drawing could not be opened:', keys: '→ next · ← back · Space play all', made: 'Made with chalk-talk',
    board: 'Chalkboard', voice: 'Narration', recording: (p: number) => `Recording… ${p}%`, show: 'Show me', yourTurn: 'Your turn', transcript: 'Transcript', again: 'Try another',
    valuesShort: (n: number) => `Values (${n})`, expand: 'Expand', all: 'All',
  },
  pt: {
    start: 'Início', back: 'Voltar', next: 'Próximo', playAll: 'Tocar tudo', chapter: (n: number, of: number) => `Capítulo ${n} de ${of}`,
    values: 'Mexa nos valores', think: 'Para pensar', answer: 'Uma resposta possível', caveat: 'Onde a comparação para',
    download: 'Baixar', checking: 'Conferindo o desenho…',
    checked: (n: number) => `Conferido em ${n} ${n === 1 ? 'posição' : 'posições'}: nada sai do papel e nenhum texto cobre outro.`,
    problems: 'A conferência achou:', broken: 'Este desenho não pôde ser aberto:', keys: '→ próximo · ← voltar · Espaço tocar tudo', made: 'Feito com chalk-talk',
    board: 'Quadro-negro', voice: 'Narração', recording: (p: number) => `Gravando… ${p}%`, show: 'Mostrar', yourTurn: 'Sua vez', transcript: 'Transcrição', again: 'Tentar outra',
    valuesShort: (n: number) => `Valores (${n})`, expand: 'Expandir', all: 'Tudo',
  },
}
export type Lang = keyof typeof TEXT
type Words = (typeof TEXT)[Lang]

export const browserLang = (): Lang => (navigator.language.toLowerCase().startsWith('pt') ? 'pt' : 'en')

export interface LessonOptions {
  /** The @font-face rules of the drawing's faces: they go inside the SVG and PNG downloads and the recordings. */
  faces: string
  lang?: Lang
  /** The lesson inside a note: no side panel, and it opens on chapter 1 drawn and still. */
  compact?: boolean
  /** The theme when the recipe has none (the recipe's own wins). */
  theme?: Theme
  /** 'document': the arrow keys and Space move the lesson anywhere on the page (the HTML file); otherwise only while
   * the focus is inside it. */
  keys?: 'document' | 'self'
  /** Shows «Expand», which calls this. */
  onExpand?: () => void
}

export interface Mounted {
  destroy(): void
}

// The lesson's markup: parts are found by data-part inside the root, never by id.
const MARKUP = `
  <header class="head">
    <div><span class="eyebrow" data-part="category"></span><h1 data-part="title"></h1></div>
    <div class="tools"><button data-part="board" type="button" aria-pressed="false"></button><button data-part="voice" type="button" aria-pressed="false"></button><div data-part="downloads" class="downloads"><button data-part="png" type="button">PNG</button><button data-part="svg" type="button">SVG</button><button data-part="gif" type="button">GIF</button><button data-part="webm" type="button">WebM</button></div></div>
  </header>
  <div class="top"><nav data-part="chapters" class="chapters"></nav><button data-part="values-toggle" type="button" aria-expanded="false" hidden></button><button data-part="expand" type="button" hidden></button></div>
  <div class="layout">
    <section class="board">
      <div class="paper"><svg data-part="paper" role="img"></svg><div data-part="ask" class="ask" role="dialog" aria-live="polite" hidden></div></div>
      <div class="bar">
        <button data-part="back" type="button"></button>
        <button data-part="next" type="button" class="primary"></button>
        <p data-part="say" class="say" aria-live="polite"></p>
        <span data-part="count" class="count"></span>
        <button data-part="all" type="button" class="ghost"></button>
      </div>
    </section>
    <aside>
      <section data-part="controls" class="card controls"></section>
      <section data-part="learning" class="card learning"></section>
      <section data-part="quiz" class="card quiz" hidden></section>
      <div data-part="check" class="check" role="status"></div>
      <details data-part="transcript" class="card transcript"></details>
      <p class="foot"><span data-part="keys"></span><br><span data-part="made"></span></p>
    </aside>
  </div>`

export function tag<K extends keyof HTMLElementTagNameMap>(name: K, attrs: Record<string, string> = {}, text = ''): HTMLElementTagNameMap[K] {
  const node = document.createElement(name)
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v)
  // Everything from the recipe is text, never markup.
  if (text) node.textContent = text
  return node
}

// document.fonts.ready does not wait for a face nothing has used yet: load the embedded ones before measuring.
export const fontsLoaded = () => Promise.all([...document.fonts].map((f) => f.load())).catch(() => undefined)

/** Mounts `scene` inside `root` (its children are replaced). The recipe must already be valid (validateScene). */
export async function mountLesson(root: HTMLElement, scene: Scene, opts: LessonOptions): Promise<Mounted> {
  const t: Words = TEXT[opts.lang ?? browserLang()]
  const compact = !!opts.compact
  root.classList.add('chalk-talk')
  root.classList.toggle('is-compact', compact)
  root.innerHTML = MARKUP
  const part = <T extends HTMLElement>(name: string) => root.querySelector(`[data-part="${name}"]`) as T
  const button = (name: string) => part<HTMLButtonElement>(name)

  const chapters = chaptersFor(scene, t.start)
  const svg = root.querySelector<SVGSVGElement>('[data-part="paper"]')!
  const say = part('say')
  const renderer = new Renderer(svg, (text) => (say.textContent = text))
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches
  const values = defaultValues(scene)
  let at = 0
  let run = 0
  let theme: Theme = scene.theme ?? opts.theme ?? 'paper'
  let speaking = false
  let gone = false

  part('category').textContent = scene.category ?? ''
  part('title').textContent = scene.title
  const chips = chapters.map((c, i) => {
    const b = tag('button', { type: 'button' }, `${i + 1} · ${c.title}`)
    b.addEventListener('click', () => go(i, i === at + 1))
    part('chapters').append(b)
    return b
  })
  button('back').textContent = `◀ ${t.back}`
  button('next').textContent = `${t.next} ▶`
  button('all').textContent = compact ? `▶ ${t.all}` : t.playAll
  part('keys').textContent = opts.keys === 'document' ? t.keys : ''
  part('made').textContent = t.made

  function paint() {
    chips.forEach((b, i) => {
      b.className = i === at ? 'is-on' : i < at ? 'is-seen' : ''
      b.setAttribute('aria-current', i === at ? 'step' : 'false')
    })
    part('count').textContent = t.chapter(at + 1, chapters.length)
    button('back').disabled = at === 0
    button('next').disabled = at === chapters.length - 1
  }

  /** Shows the pause's question over the paper and waits for «Show me». */
  function asked(question: string): Promise<void> {
    const box = part('ask')
    box.replaceChildren(tag('p', {}, question))
    const show = tag('button', { type: 'button', class: 'primary' }, t.show)
    box.append(show)
    box.hidden = false
    show.focus({ preventScroll: true })
    return new Promise((resolve) => show.addEventListener('click', () => {
      box.hidden = true
      resolve()
    }, { once: true }))
  }

  // Before a beat is drawn: a pause with `ask` waits for the person; with narration on, the beat's sentence is spoken.
  async function beat(text: string | undefined, start: number, mine: number) {
    const step = scene.steps[start]
    if (step.type === 'pause' && step.ask) await asked(interpolate(step.ask, buildScope(scene, values), scene.locale))
    if (mine === run && speaking && text) await speak(text, scene.locale ?? 'pt-BR')
  }

  function paper() {
    root.querySelector('.paper')!.classList.toggle('is-board', theme === 'chalkboard')
    part('board').setAttribute('aria-pressed', String(theme === 'chalkboard'))
  }

  // Draws up to chapter i: animated from where the last chapter ended when going forward one, at once otherwise.
  async function go(i: number, animate: boolean, from?: number) {
    if (gone) return
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
      if (mine === run && at === chapters.length - 1) quiz()
    } catch (e) {
      // A newer drawing took over (another click, a value moved): nothing to show.
      if (mine === run) throw e
    }
  }

  button('board').textContent = t.board
  part('board').addEventListener('click', () => {
    theme = theme === 'chalkboard' ? 'paper' : 'chalkboard'
    paper()
    go(at, false)
  })
  paper()
  if ('speechSynthesis' in window && !compact) {
    button('voice').textContent = `🔈 ${t.voice}`
    part('voice').addEventListener('click', () => {
      speaking = !speaking
      part('voice').setAttribute('aria-pressed', String(speaking))
      if (!speaking) speechSynthesis.cancel()
    })
  } else part('voice').remove()
  part('back').addEventListener('click', () => go(at - 1, false))
  part('next').addEventListener('click', () => go(at + 1, true))
  part('all').addEventListener('click', () => go(chapters.length - 1, true, 0))

  const onKey = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement).closest('input, button, summary, textarea, [contenteditable]')) return
    if (e.key === 'ArrowRight') go(at + 1, true)
    else if (e.key === 'ArrowLeft') go(at - 1, false)
    else if (e.key === ' ') {
      e.preventDefault()
      go(chapters.length - 1, true, 0)
    } else return
    e.stopPropagation()
  }
  const keyTarget: Document | HTMLElement = opts.keys === 'document' ? document : root
  if (keyTarget === root) root.tabIndex = 0
  keyTarget.addEventListener('keydown', onKey as EventListener)

  controls()
  if (compact) {
    // The note: the values open under the paper; the rest is in «Expand».
    const toggle = button('values-toggle')
    const count = Object.keys(scene.params ?? {}).length + Object.keys(scene.switches ?? {}).length
    if (count) {
      toggle.hidden = false
      toggle.textContent = `⚙ ${t.valuesShort(count)}`
      toggle.addEventListener('click', () => {
        const open = !root.classList.contains('show-values')
        root.classList.toggle('show-values', open)
        toggle.setAttribute('aria-expanded', String(open))
      })
    }
    for (const p of ['learning', 'quiz', 'check', 'transcript']) part(p).remove()
    part('downloads').remove()
    part('board').remove()
    root.querySelector('.foot')!.remove()
  } else {
    learning()
    transcript()
    downloads()
  }
  if (opts.onExpand) {
    const expand = button('expand')
    expand.hidden = false
    expand.textContent = `⤢ ${t.expand}`
    expand.addEventListener('click', opts.onExpand)
  }

  await fontsLoaded()
  // The check draws hidden on its own paper: it does not wait for the lesson (a question may be waiting for a click).
  if (!compact) void check()
  await go(0, !compact)

  return {
    destroy() {
      gone = true
      run++
      renderer.stop()
      keyTarget.removeEventListener('keydown', onKey as EventListener)
      if (speaking) speechSynthesis.cancel()
      root.replaceChildren()
    },
  }

  function controls() {
    const box = part('controls')
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
        go(at, false)
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
        go(at, false)
      })
      label.append(input, tag('span', {}, s.label))
      box.append(label)
    }
  }

  function learning() {
    const box = part('learning')
    const l = scene.learning
    if (!l) return box.remove()
    const answer = tag('details')
    answer.append(tag('summary', {}, t.answer), tag('p', {}, l.answer))
    box.append(tag('h2', {}, t.think), tag('p', {}, l.question), answer, tag('p', { class: 'caveat' }, `${t.caveat}: ${l.caveat}`))
  }

  /** The question at the end, once the last chapter is drawn: pick one, see why. */
  function quiz() {
    const box = part('quiz')
    if (!box || !scene.quiz || box.childElementCount) return
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
  function transcript() {
    const box = part('transcript')
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

  // ---------- download: the paper as SVG (with its fonts) or PNG, the lesson drawing itself as GIF or WebM ----------
  function downloads() {
    const box = part('downloads')
    box.prepend(tag('span', {}, t.download))
    const name = (ext: string) => `${(scene.id || 'drawing').replace(/[^a-z0-9-]+/gi, '-').slice(0, 60)}.${ext}`
    part('svg').addEventListener('click', () => save(new Blob([svgText(svg, opts.faces)], { type: 'image/svg+xml' }), name('svg')))
    const recording = (b: HTMLButtonElement, make: (progress: (f: number) => void) => Promise<Blob>, ext: string) =>
      b.addEventListener('click', async () => {
        const label = b.textContent
        box.querySelectorAll('button').forEach((x) => (x.disabled = true))
        try {
          save(await make((f) => (b.textContent = t.recording(Math.round(f * 100)))), name(ext))
        } finally {
          b.textContent = label
          box.querySelectorAll('button').forEach((x) => (x.disabled = false))
        }
      })
    const faces = opts.faces
    const back = () => (theme === 'chalkboard' ? '#26372E' : '#FBF7EE')
    if ('MediaRecorder' in window) {
      recording(button('webm'), (onProgress) => recordWebm(scene, defaultValues(scene), { faces, paper: back(), theme, onProgress }), 'webm')
    } else part('webm').remove()
    recording(button('gif'), async (onProgress) => {
      const gif = GIFEncoder()
      await playFrames(scene, defaultValues(scene), { faces, paper: back(), theme, onProgress, fps: 8, scale: 0.6 }, (canvas) => {
        const { data } = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height)
        const palette = quantize(data, 64)
        gif.writeFrame(applyPalette(data, palette), canvas.width, canvas.height, { palette, delay: 125 })
      })
      gif.finish()
      return new Blob([gif.bytes()], { type: 'image/gif' })
    }, 'gif')
    part('png').addEventListener('click', () => {
      const img = new Image()
      img.onload = () => {
        const canvas = tag('canvas', { width: String(scene.width * 2), height: String(scene.height * 2) })
        canvas.getContext('2d')!.drawImage(img, 0, 0, scene.width * 2, scene.height * 2)
        canvas.toBlob((b) => b && save(b, name('png')), 'image/png')
      }
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgText(svg, opts.faces))
    })
  }

  // ---------- the check, hidden, after the first chapter ----------
  async function check() {
    const box = part('check')
    box.textContent = t.checking
    const r = await reviewScene(scene)
    if (gone) return
    box.className = r.problems.length ? 'check is-warn' : 'check is-ok'
    if (!r.problems.length) return void (box.textContent = `✓ ${t.checked(r.combos)}`)
    box.textContent = ''
    const list = tag('ul')
    for (const p of r.problems) list.append(tag('li', {}, p))
    box.append(tag('b', {}, `! ${t.problems}`), list)
  }
}

/** The whole drawing at once, still, inside `root` (an exported PDF, a printed page, a picture of it). */
export async function stillLesson(root: HTMLElement, scene: Scene, theme?: Theme): Promise<void> {
  root.classList.add('chalk-talk', 'is-still')
  const look: Theme = scene.theme ?? theme ?? 'paper'
  const box = tag('div', { class: `paper${look === 'chalkboard' ? ' is-board' : ''}` })
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  box.append(svg)
  root.replaceChildren(box)
  await fontsLoaded()
  await new Renderer(svg).render(scene, defaultValues(scene), { animate: false, theme: look })
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

export function svgText(svg: SVGSVGElement, faces: string): string {
  const copy = svg.cloneNode(true) as SVGSVGElement
  copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  const style = document.createElementNS('http://www.w3.org/2000/svg', 'style')
  style.textContent = faces
  copy.prepend(style)
  return new XMLSerializer().serializeToString(copy)
}

function save(blob: Blob, name: string) {
  const a = tag('a', { href: URL.createObjectURL(blob), download: name })
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}
