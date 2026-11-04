// Draws a checked recipe as an SVG flow: arrivals, steps, routes with their shares, ends.
import { fmtDuration, label } from './core'
import type { Checked } from './core'
import type { PreviewLang } from '../../types'

const C = { bg: '#ffffff', ink: '#17211f', muted: '#5b6965', line: '#cdd6d3', edge: '#9fb0ab', accent: '#b86a0e', crit: '#b23a3a', soft: '#f6f8f7' }
const esc = (s: string) => String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' } as Record<string, string>)[ch] ?? ch)
const cut = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + '…' : s)
const pct = (x: number) => `${Math.round(x * 100)}%`

type Node = { id: string; kind: 'src' | 'step' | 'end'; col: number; x: number; y: number; w: number; h: number; title: string; sub: string; strong?: boolean; danger?: boolean }
type Edge = { from: string; to: string; label: string; ab?: boolean }

export function flowSvg(c: Checked, locale: PreviewLang): { svg: string; width: number; height: number } {
  const P = c.plan, M = c.model
  const name = (t: any) => (t.e ? 'end:' + P.ends[t.i] : P.steps[t.i].name)
  const depth: number[] = P.steps.map(() => 1)
  const d = (i: number) => depth[i] ?? 1
  for (let guard = 0, moved = true; moved && guard < 50; guard++) {
    moved = false
    P.routes.forEach((r: any, i: number) => {
      const ts = r.k === 's' ? [r.to] : r.k === 'b' ? r.tos : [...r.byAttr, r.other]
      ts.forEach((t: any) => {
        if (t && !t.e && d(t.i) < d(i) + 1) { depth[t.i] = d(i) + 1; moved = true }
      })
    })
  }
  const endCol = Math.max(...depth) + 1
  const cols: string[][] = []
  const nodes: Record<string, Node> = {}
  const add = (n: Omit<Node, 'x' | 'y' | 'w' | 'h'>) => {
    ;(cols[n.col] = cols[n.col] || []).push(n.id)
    nodes[n.id] = { ...n, x: 0, y: 0, w: 0, h: 0 }
  }
  const rate = M.arrival.rate
  add({ id: 'src', kind: 'src', col: 0, title: label(M, M.arrival.item, locale), sub: `${compact(P.statedPerMin * rate.per)} per ${unitName(rate.per)}` })
  P.steps.forEach((st: any, i: number) => {
    const tm = st.time
    const time = (tm.k === 'e' ? '~' : '') + (tm.k === 'u' ? `${fmtDuration(tm.a)}–${fmtDuration(tm.b)}` : fmtDuration(tm.a))
    const sub = st.pool >= 0 ? `${P.pools[st.pool].qty} × ${label(M, P.pools[st.pool].name, locale)} · ${time}` : time
    add({ id: st.name, kind: 'step', col: d(i), title: label(M, st.name, locale), sub, strong: st.pool >= 0 })
  })
  const abandonEnds = new Set<string>()
  P.abandon.forEach((a: any) => { if (a) abandonEnds.add(P.ends[a.to.i]) })
  P.ends.forEach((n: string) => add({ id: 'end:' + n, kind: 'end', col: endCol, title: label(M, n, locale), sub: '', danger: abandonEnds.has(n) }))

  const edges: Edge[] = [{ from: 'src', to: name(P.entry), label: '' }]
  P.routes.forEach((r: any, i: number) => {
    const from = P.steps[i].name
    if (r.k === 's') edges.push({ from, to: name(r.to), label: '' })
    else if (r.k === 'b') r.tos.forEach((t: any, k: number) => edges.push({ from, to: name(t), label: pct(r.ps[k]) }))
    else {
      M.mix.values.forEach((v: string, a: number) => { if (r.byAttr[a]) edges.push({ from, to: name(r.byAttr[a]), label: label(M, v, locale) }) })
      if (r.other) edges.push({ from, to: name(r.other), label: locale === 'pt-BR' ? 'senão' : 'otherwise' })
    }
    const ab = P.abandon[i]
    if (ab) edges.push({ from, to: name(ab.to), label: (locale === 'pt-BR' ? 'desiste após ' : 'gives up after ') + fmtDuration(ab.after), ab: true })
  })

  const colW = 196, rowH = 92, top = 64
  const maxRows = Math.max(...cols.map(c => c.length))
  const width = cols.length * colW + 24
  const height = top + maxRows * rowH + 20
  cols.forEach((ids, ci) => {
    const off = top + ((maxRows - ids.length) * rowH) / 2
    ids.forEach((id, ri) => {
      const n = nodes[id]
      if (!n) return
      n.w = 164; n.h = n.kind === 'end' ? 44 : 52
      n.x = 12 + ci * colW + (colW - n.w) / 2
      n.y = off + ri * rowH + (rowH - n.h) / 2
    })
  })

  const parts: string[] = []
  parts.push(`<rect width="${width}" height="${height}" rx="10" fill="${C.bg}"/>`)
  parts.push(`<text x="16" y="28" font-size="15" font-weight="600" fill="${C.ink}">${esc(cut(M.name, 80))}</text>`)
  parts.push(`<text x="16" y="46" font-size="11.5" fill="${C.muted}">${esc(c.ok ? (c.warnings.length ? `${c.warnings.length} warning(s)` : 'valid recipe') : `${c.errors.length} error(s)`)}</text>`)
  parts.push(`<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${C.edge}"/></marker><marker id="arr-ab" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${C.crit}"/></marker></defs>`)
  const labels: string[] = []
  for (const ed of edges) {
    const a = nodes[ed.from], b = nodes[ed.to]
    if (!a || !b) continue
    const x1 = a.x + a.w, y1 = a.y + a.h / 2 + (ed.ab ? 14 : 0), x2 = b.x, y2 = b.y + b.h / 2, dx = (x2 - x1) / 2
    parts.push(`<path d="M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}" fill="none" stroke="${ed.ab ? C.crit : C.edge}" stroke-width="1.4"${ed.ab ? ' stroke-dasharray="4 4"' : ''} marker-end="url(#${ed.ab ? 'arr-ab' : 'arr'})"/>`)
    if (ed.label) {
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, w = ed.label.length * 6.4 + 12
      labels.push(`<rect x="${mx - w / 2}" y="${my - 9}" width="${w}" height="18" rx="9" fill="${C.soft}" stroke="${C.line}"/><text x="${mx}" y="${my + 4}" font-size="11" text-anchor="middle" fill="${ed.ab ? C.crit : C.muted}">${esc(ed.label)}</text>`)
    }
  }
  for (const n of Object.values(nodes)) {
    const r = n.kind === 'src' ? n.h / 2 : 8
    const stroke = n.kind === 'src' ? C.accent : n.danger ? C.crit : n.strong ? C.ink : C.line
    parts.push(`<rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="${r}" fill="${C.bg}" stroke="${stroke}" stroke-width="${n.strong || n.kind === 'src' ? 1.6 : 1}"/>`)
    const ty = n.sub ? n.y + n.h / 2 - 3 : n.y + n.h / 2 + 4
    parts.push(`<text x="${n.x + n.w / 2}" y="${ty}" font-size="12.5" font-weight="600" text-anchor="middle" fill="${n.danger ? C.crit : C.ink}">${esc(cut(n.title, 24))}</text>`)
    if (n.sub) parts.push(`<text x="${n.x + n.w / 2}" y="${n.y + n.h / 2 + 13}" font-size="11" text-anchor="middle" fill="${C.muted}">${esc(cut(n.sub, 28))}</text>`)
  }
  parts.push(...labels)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" font-family="system-ui, -apple-system, Segoe UI, sans-serif">${parts.join('')}</svg>`
  return { svg, width, height }
}

function compact(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`
  if (n >= 1e4) return `${(n / 1e3).toFixed(n >= 1e5 ? 0 : 1)}k`
  return n >= 100 ? Math.round(n).toLocaleString('en-US') : String(Math.round(n * 10) / 10)
}

function unitName(perMin: number): string {
  const m: Record<string, string> = { '1': 'minute', '60': 'hour', '1440': 'day', '10080': 'week', '43200': 'month', '525600': 'year' }
  return m[String(perMin)] ?? `${perMin} min`
}

// The same flow as text lines, for the terminal, which draws no SVG.
export function flowText(c: Checked, locale: PreviewLang): string[] {
  const P = c.plan, M = c.model
  const nm = (t: any) => label(M, t.e ? P.ends[t.i] : P.steps[t.i].name, locale)
  const lines = [`${label(M, M.arrival.item, locale)} arrive → ${nm(P.entry)}`]
  P.routes.forEach((r: any, i: number) => {
    const st = P.steps[i]
    const who = st.pool >= 0 ? ` [${P.pools[st.pool].qty} × ${label(M, P.pools[st.pool].name, locale)}]` : ''
    let to = ''
    if (r.k === 's') to = nm(r.to)
    else if (r.k === 'b') to = r.tos.map((t: any, k: number) => `${nm(t)} ${pct(r.ps[k])}`).join(' | ')
    else {
      const cases = M.mix.values.map((v: string, a: number) => (r.byAttr[a] ? `${nm(r.byAttr[a])} (${label(M, v, locale)})` : '')).filter(Boolean)
      if (r.other) cases.push(`${nm(r.other)} (${locale === 'pt-BR' ? 'senão' : 'otherwise'})`)
      to = cases.join(' | ')
    }
    const ab = P.abandon[i]
    lines.push(`${label(M, st.name, locale)}${who} → ${to}${ab ? ` · ${locale === 'pt-BR' ? 'desiste após' : 'gives up after'} ${fmtDuration(ab.after)} → ${nm(ab.to)}` : ''}`)
  })
  return lines
}
