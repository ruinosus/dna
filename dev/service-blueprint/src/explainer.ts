// The blueprint explained by drawing it — an explainer drawn with visual-explainer that walks the journey: each moment a column, the customer
// drawn with that moment's mood and as high as they feel, a line over their heads, what they do; then the line of
// visibility and, under it, what happens on stage, backstage and in the systems. A chapter per phase; each moment says
// what the customer does, how it feels and the pain they told.
import { GREY, line, polyline, RED, text, wrap, type Obj, type XY } from '@lib/drawing/mermaidKit'
import type { Blueprint } from './blueprint'
import { WORDS, type Lang } from './words'

const MOOD: Record<number, string | undefined> = { 1: 'sad', 2: 'worried', 3: undefined, 4: 'happy', 5: 'happy' }
const FRONT = '#2F5BEA'
const BACK = '#7B4FC9'

export function explainerOf(b: Blueprint, lang: Lang = 'en'): Obj {
  const w = WORDS[lang]
  const col = 180
  const left = 40
  const width = Math.max(900, left * 2 + b.moments.length * col)
  const faceY = (feels = 3) => 130 + (5 - feels) * 28 // where the customer stands: higher when they feel better
  const visibility = 380
  const actor = (id?: string) => b.actors.find((a) => a.id === id)?.name
  const steps: Obj[] = [text([left, 60], b.name, 34)]
  const heads: XY[] = []
  let phase: string | undefined
  b.moments.forEach((m, i) => {
    const cx = left + col * i + col / 2
    const y = faceY(m.feels)
    const part: Obj[] = []
    const mood = m.feels !== undefined ? MOOD[m.feels] : undefined
    const pain = (m.pains ?? [])[0]?.says
    const say = [m.customer, pain ? `«${pain}»` : ''].filter(Boolean).join(' — ')
    part.push({ type: 'prop', name: 'person', at: [cx, y], size: 64, ...(mood ? { mood } : {}), say })
    if (m.phase !== phase) {
      phase = m.phase
      part[0] = { ...part[0], chapter: b.phases.find((p) => p.id === m.phase)?.name ?? m.phase }
    }
    // the line over the heads, segment by segment as the journey goes on (never across a face)
    const head: XY = [cx, y - 78]
    if (heads.length) part.push(polyline([heads[heads.length - 1], head], { color: RED, dashed: true }))
    heads.push(head)
    // ⚠ / ⏱ by the customer's feet, where the line over the heads never passes
    ;(m.marks ?? []).forEach((k, n) => part.push(text([cx + 34 + n * 22, y - 4], k === 'fail' ? '⚠' : '⏱', 18, 'start', k === 'fail' ? RED : GREY)))
    wrap(m.customer, 17, col - 24).slice(0, 3).forEach((t, k) => part.push(text([cx, 300 + k * 21], t, 17, 'middle')))
    // under the line of visibility: who does it, on stage and behind
    let at = visibility + 34
    const below = (t: string, color: string) => {
      for (const l of wrap(t, 14, col - 20).slice(0, 3)) {
        part.push(text([cx, at], l, 14, 'middle', color))
        at += 18
      }
      at += 6
    }
    for (const d of m.front ?? []) below(d.actor ? `${actor(d.actor)}: ${d.does}` : d.does, FRONT)
    for (const d of m.back ?? []) below(d.actor ? `${actor(d.actor)}: ${d.does}` : d.does, BACK)
    if ((m.support ?? []).length) below((m.support ?? []).map((s) => b.systems.find((x) => x.id === s)?.name ?? s).join(', '), GREY)
    steps.push(...part)
  })
  // the line of visibility, drawn once the moments are on the paper
  steps.push(line([left - 10, visibility], [width - left + 10, visibility], { color: GREY, dashed: true }), text([width - left, visibility - 8], w.lineVisibility, 14, 'end', GREY))
  // the title opens the first phase's chapter
  const first = steps.findIndex((s) => s.chapter)
  if (first > 0) {
    steps[0] = { ...steps[0], chapter: steps[first].chapter }
    const { chapter: _c, ...rest } = steps[first] // eslint-disable-line @typescript-eslint/no-unused-vars -- moved to the title
    steps[first] = rest
  }
  const id = b.name.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'blueprint'
  return { id, title: b.name, width, height: 600, background: 'plain', locale: lang === 'pt' ? 'pt-BR' : 'en-US', steps }
}
