// The previews' drawings, from what a skill's --check --json read: a way of working as its stages in lanes, phase by
// phase, with each gate and who approves it; a service blueprint as its moments, with what the customer lives and feels,
// what happens on stage, backstage and in the systems. An SVG for the desktop app, VS Code and the phone; text lines for
// the terminal, which draws no SVG. Fixed light colors on a white card, so it reads in both themes.
import type { PreviewLang } from '../../types'

export const PREVIEW_PANE = 'dna-recipe'
const C = { bg: '#ffffff', ink: '#17211f', muted: '#5b6965', line: '#cdd6d3', soft: '#f6f8f7', gate: '#b23a3a', accent: '#2f5bea', warm: '#b86a0e' }
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' } as Record<string, string>)[ch] ?? ch)
export const cut = (s: unknown, n: number) => {
  const t = String(s ?? '')
  return t.length > n ? `${t.slice(0, n - 1)}…` : t
}
/** Up to `max` lines of about `n` characters, broken at spaces; the last one cut with … only if it still does not fit. */
export function wrap(s: unknown, n: number, max = 2): string[] {
  const words = String(s ?? '').split(/\s+/).filter(Boolean)
  const lines: string[] = []
  let cur = ''
  for (const w of words) {
    if (!cur) cur = w
    else if ((cur + ' ' + w).length <= n) cur += ' ' + w
    else {
      lines.push(cur)
      cur = w
    }
  }
  if (cur) lines.push(cur)
  if (lines.length <= max) return lines
  return [...lines.slice(0, max - 1), cut(lines.slice(max - 1).join(' '), n)]
}
const text = (x: number, y: number, s: string, size = 12, color = C.ink, weight = 400) => `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${color}">${esc(s)}</text>`

type W = { en: string; pt: string }
const say = (w: W, l: PreviewLang) => (l === 'pt-BR' ? w.pt : w.en)
const WORD = {
  stages: { en: 'stages', pt: 'etapas' }, gates: { en: 'gates', pt: 'gates' }, look: { en: 'to look at', pt: 'para olhar' },
  customer: { en: 'Customer', pt: 'Cliente' }, front: { en: 'On stage', pt: 'Palco' }, back: { en: 'Backstage', pt: 'Bastidor' }, support: { en: 'Systems', pt: 'Sistemas' },
  feels: { en: 'feels', pt: 'sente' }, pains: { en: 'pains', pt: 'dores' }, pain: { en: 'pain', pt: 'dor' }, moments: { en: 'moments', pt: 'momentos' }, nobody: { en: 'nobody', pt: 'ninguém' },
}

// ---- a way of working ----
type Way = { lanes: any[]; roles: any[]; phases: any[]; stages: any[]; gates: any[] }
const roleAcr = (w: Way, id: string) => w.roles.find((r) => r.id === id)?.acronym ?? id
const approversOf = (w: Way, g: any): string[] => (Array.isArray(g.approvals) && g.approvals.length ? g.approvals.map((a: any) => roleAcr(w, a.by)) : g.approver ? [roleAcr(w, g.approver)] : [])
const phaseName = (w: Way, id: string) => w.phases.find((p) => p.id === id)?.name ?? id

export function waySvg(w: Way, name: string, l: PreviewLang): { svg: string; width: number; height: number } {
  const colW = 150, left = 104, laneH = 104, top = 78
  const lanes = w.lanes.length ? w.lanes : [{ id: '', name: '' }]
  const laneY = (id: string) => top + Math.max(0, lanes.findIndex((x) => x.id === id)) * laneH
  const width = left + w.stages.length * colW + 16
  const height = top + lanes.length * laneH + 12
  const p: string[] = [`<rect width="${width}" height="${height}" rx="10" fill="${C.bg}"/>`, text(16, 24, cut(name, 70), 15, C.ink, 600), text(16, 42, `${w.stages.length} ${say(WORD.stages, l)} · ${w.gates.length} ${say(WORD.gates, l)}`, 11.5, C.muted)]
  // the phases, over the stages they hold in a row
  let i = 0
  while (i < w.stages.length) {
    let j = i
    while (j + 1 < w.stages.length && w.stages[j + 1].phase === w.stages[i].phase) j++
    const x = left + i * colW
    p.push(`<line x1="${x + 4}" y1="${top - 8}" x2="${left + (j + 1) * colW - 8}" y2="${top - 8}" stroke="${C.line}"/>`, text(x + 6, top - 13, cut(phaseName(w, w.stages[i].phase).toUpperCase(), Math.floor(((j - i + 1) * colW) / 7.5)), 10, C.muted, 600))
    i = j + 1
  }
  lanes.forEach((ln, k) => {
    const y = top + k * laneH
    p.push(`<line x1="12" y1="${y + laneH - 4}" x2="${width - 12}" y2="${y + laneH - 4}" stroke="${C.soft}"/>`, text(12, y + 20, cut(ln.name, 13), 11.5, C.accent, 600))
  })
  w.stages.forEach((s, k) => {
    const x = left + k * colW, y = laneY(s.lane) + 4
    if (k > 0) {
      const px = left + (k - 1) * colW + 136, py = laneY(w.stages[k - 1].lane) + 26
      p.push(`<path d="M${px} ${py} H${px + 7} V${y + 22} H${x}" fill="none" stroke="${C.line}" stroke-width="1.5"/>`)
    }
    p.push(`<rect x="${x}" y="${y}" width="136" height="44" rx="7" fill="${C.bg}" stroke="${C.ink}" stroke-opacity="0.35"/>`, text(x + 8, y + 18, cut(s.name, 20), 12, C.ink, 600), text(x + 8, y + 34, cut((s.roles ?? []).map((r: string) => roleAcr(w, r)).join(', '), 22), 10.5, C.muted))
    for (const g of w.gates.filter((x) => x.after === s.id).slice(0, 1)) {
      const gy = y + 58
      // the gate's name, and under it who approves: two lines, so a long name never hides the approvers
      const name = wrap(g.name, 19)
      p.push(`<rect x="${x + 6}" y="${gy - 9}" width="9" height="9" transform="rotate(45 ${x + 10.5} ${gy - 4.5})" fill="#fdecec" stroke="${C.gate}" stroke-width="1.5"/>`, ...name.map((t, n) => text(x + 22, gy + n * 13, t, 10.5, C.gate)), text(x + 22, gy + name.length * 13 + 1, cut(approversOf(w, g).join(' + ') || say(WORD.nobody, l), 19), 10, C.muted))
    }
  })
  return { svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" font-family="system-ui, -apple-system, Segoe UI, sans-serif">${p.join('')}</svg>`, width, height }
}

export function wayText(w: Way, name: string, l: PreviewLang): string[] {
  const out = [`${name} · ${w.stages.length} ${say(WORD.stages, l)} · ${w.gates.length} ${say(WORD.gates, l)}`]
  for (const ph of w.phases) {
    const stages = w.stages.filter((s) => s.phase === ph.id)
    if (!stages.length) continue
    out.push(`${ph.name}: ${stages.map((s) => {
      const gates = w.gates.filter((g) => g.after === s.id).map((g) => ` ◆ ${g.name} (${approversOf(w, g).join('+') || say(WORD.nobody, l)})`).join('')
      return `${s.name} [${(s.roles ?? []).map((r: string) => roleAcr(w, r)).join(', ')}]${gates}`
    }).join(' → ')}`)
  }
  return out
}

// ---- a service blueprint ----
type Blueprint = { name: string; who?: string; phases: any[]; actors: any[]; systems: any[]; moments: any[] }
const actorName = (b: Blueprint, id: string) => b.actors.find((a) => a.id === id)?.name ?? id
const systemName = (b: Blueprint, id: string) => b.systems.find((s) => s.id === id)?.name ?? id
// a thing on stage or backstage: who does it and what, or what alone when nobody is named (a screen, an email)
const doing = (b: Blueprint, x: any) => (typeof x === 'string' ? x : x?.does ? (x.actor ? `${actorName(b, x.actor)}: ${x.does}` : x.does) : actorName(b, x?.actor))
const bPhase = (b: Blueprint, id: string) => b.phases.find((p) => (p.id ?? p) === id)?.name ?? b.phases.find((p) => p === id) ?? id

export function blueprintSvg(b: Blueprint, l: PreviewLang): { svg: string; width: number; height: number } {
  const colW = 160, left = 92, top = 78, rows = [92, 70, 70, 46]
  const width = left + b.moments.length * colW + 16
  const ys = [top, top + rows[0]!, top + rows[0]! + rows[1]!, top + rows[0]! + rows[1]! + rows[2]!]
  const height = (ys[3] ?? top) + rows[3]! + 12
  const p: string[] = [`<rect width="${width}" height="${height}" rx="10" fill="${C.bg}"/>`, text(16, 24, cut(b.name, 70), 15, C.ink, 600), text(16, 42, `${b.moments.length} ${say(WORD.moments, l)}${b.who ? ` · ${b.who}` : ''}`, 11.5, C.muted)]
  const labels = [WORD.customer, WORD.front, WORD.back, WORD.support]
  labels.forEach((w, k) => p.push(`<line x1="12" y1="${ys[k]! - 4}" x2="${width - 12}" y2="${ys[k]! - 4}" stroke="${k === 2 ? C.line : C.soft}"${k === 2 ? ' stroke-dasharray="4 3"' : ''}/>`, text(12, ys[k]! + 14, say(w, l), 11, C.accent, 600)))
  let last = ''
  b.moments.forEach((m, k) => {
    const x = left + k * colW
    const ph = String(bPhase(b, m.phase) ?? '')
    if (ph !== last) p.push(text(x + 4, top - 12, cut(ph.toUpperCase(), 22), 10, C.muted, 600))
    last = ph
    p.push(`<rect x="${x}" y="${ys[0]}" width="${colW - 12}" height="${rows[0]! - 10}" rx="7" fill="${(m.pains ?? []).length ? '#fdecec' : C.soft}" stroke="${C.line}"/>`, ...wrap(m.customer, 24).map((t, n) => text(x + 7, ys[0]! + 16 + n * 14, t, 11.5, C.ink, 600)))
    const feels = typeof m.feels === 'number' ? m.feels : undefined
    for (let d = 0; d < 5; d++) p.push(`<circle cx="${x + 11 + d * 11}" cy="${ys[0]! + 50}" r="4" fill="${feels !== undefined && d < feels ? C.warm : C.bg}" stroke="${C.warm}"/>`)
    p.push(text(x + 70, ys[0]! + 54, feels !== undefined ? `${say(WORD.feels, l)} ${feels}/5` : `${say(WORD.feels, l)} ?`, 10, C.muted))
    if ((m.pains ?? []).length) p.push(text(x + 7, ys[0]! + 72, painWord((m.pains ?? []).length, l), 10, C.gate, 600))
    // up to two things a layer, each on up to two lines
    const put = (k2: number, items: string[]) => items.slice(0, 2).flatMap((s2) => wrap(s2, 26)).slice(0, 4).forEach((t, n) => p.push(text(x + 4, ys[k2]! + 14 + n * 13, t, 10.5, C.ink)))
    put(1, (m.front ?? []).map((x2: any) => doing(b, x2)))
    put(2, (m.back ?? []).map((x2: any) => doing(b, x2)))
    put(3, (m.support ?? []).map((s: string) => systemName(b, s)))
  })
  return { svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" font-family="system-ui, -apple-system, Segoe UI, sans-serif">${p.join('')}</svg>`, width, height }
}

export function blueprintText(b: Blueprint, l: PreviewLang): string[] {
  const out = [`${b.name} · ${b.moments.length} ${say(WORD.moments, l)}`]
  b.moments.forEach((m, k) => {
    const parts = [
      `${say(WORD.feels, l)} ${typeof m.feels === 'number' ? `${m.feels}/5` : '?'}`,
      (m.pains ?? []).length ? painWord((m.pains ?? []).length, l) : '',
      (m.front ?? []).length ? `${say(WORD.front, l)}: ${(m.front ?? []).map((x: any) => doing(b, x)).join('; ')}` : '',
      (m.back ?? []).length ? `${say(WORD.back, l)}: ${(m.back ?? []).map((x: any) => doing(b, x)).join('; ')}` : '',
      (m.support ?? []).length ? `${say(WORD.support, l)}: ${(m.support ?? []).map((s: string) => systemName(b, s)).join(', ')}` : '',
    ].filter(Boolean)
    out.push(`${k + 1}. ${m.customer} — ${parts.join(' · ')}`)
  })
  return out
}

export const lookWord = (n: number, l: PreviewLang) => `${n} ${say(WORD.look, l)}`
const painWord = (n: number, l: PreviewLang) => `${n} ${say(n === 1 ? WORD.pain : WORD.pains, l)}`
