// The blueprint on one page that opens with no internet: the phases on top, the line of what the customer feels, the
// five layers with the three lines between them, ⚠ failure points and ⏱ waits. A moment opens its detail; «To look at»
// says what does not hold and opens where; the Pains and Promises tabs are the workbook's own sheets; the buttons
// download the workbook, the .blueprint.yaml it was drawn from and a PNG of the map.
import type { Blueprint, Doing, Moment } from '../blueprint'
import type { Look } from '../review'
import { workbookFile, workbookOf, type Sheet } from '../workbook'
import { FACES, WORDS, type Lang } from '../words'

declare const __MAP_CSS__: string

interface Data {
  id: string
  lang: Lang
  blueprint: Blueprint
  looks: Look[]
  yaml: string
}
const UI = {
  en: { map: 'Blueprint', pick: 'Pick a moment to see it whole.', excel: '⬇ Excel', yaml: '⬇ YAML', png: '⬇ PNG', noAction: 'none yet', of: (n: number) => `${n} of 5`, moments: (n: number) => `${n} moments` },
  pt: { map: 'Blueprint', pick: 'Escolha um momento para ver inteiro.', excel: '⬇ Excel', yaml: '⬇ YAML', png: '⬇ PNG', noAction: 'nenhuma ainda', of: (n: number) => `${n} de 5`, moments: (n: number) => `${n} momentos` },
}

const data: Data = JSON.parse(document.getElementById('blueprint')!.textContent!)
const { blueprint: b, lang, looks } = data
const w = WORDS[lang]
const u = UI[lang]
const sheets = workbookOf(b, looks, lang)
document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
document.title = b.name
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const actor = (id?: string) => b.actors.find((a) => a.id === id)?.name ?? id ?? ''
const system = (id: string) => b.systems.find((s) => s.id === id)?.name ?? id
const doing = (d: Doing) => (d.actor ? `${esc(d.does)} <span class="fh-sub">· ${esc(actor(d.actor))}</span>` : esc(d.does))

type Tab = 'map' | 'pains' | 'promises'
let tab: Tab = 'map'
let picked: string | undefined
const app = document.getElementById('app')!

function render() {
  const tabs: [Tab, string][] = [['map', u.map], ['pains', w.painsActions], ['promises', w.promises]]
  app.innerHTML = `<div class="fh-wrap">
    <header><h1 class="fh-title">${esc(b.name)}</h1><p class="fh-sub">${esc(b.who)} · ${esc(b.phases.map((p) => p.name).join(' → '))} · ${u.moments(b.moments.length)}</p>${b.about ? `<p class="fh-sub">${esc(b.about)}</p>` : ''}</header>
    <div class="fh-bar" role="tablist">${tabs.map(([k, t]) => `<button class="fh-tab" role="tab" aria-selected="${k === tab}" data-tab="${k}">${esc(t)}</button>`).join('')}
      <span class="fh-space"></span><button class="fh-get" data-get="xlsx">${u.excel}</button><button class="fh-get" data-get="yaml">${u.yaml}</button>${tab === 'map' ? `<button class="fh-get" data-get="png">${u.png}</button>` : ''}</div>
    ${looks.length ? `<section class="fh-look"><h2>${w.look}</h2><ul>${looks.map((l, i) => `<li><button data-look="${i}">${esc(l[lang])}</button></li>`).join('')}</ul></section>` : ''}
    ${tab === 'map' ? `<div class="fh-body"><section class="fh-board">${grid()}</section><aside class="fh-detail" aria-live="polite">${detail()}</aside></div>` : table(sheets.find((s) => s.key === tab)!)}
  </div>`
}

function grid() {
  const n = b.moments.length
  const runs: { phase: string; span: number }[] = []
  for (const m of b.moments) {
    if (runs.at(-1)?.phase === m.phase) runs.at(-1)!.span++
    else runs.push({ phase: m.phase, span: 1 })
  }
  const cls = (m: Moment, k: string) => `fh-cell ${k}${picked === m.id ? ' picked' : ''}`
  let html = `<div class="fh-grid" style="grid-template-columns: 150px repeat(${n}, minmax(140px, 1fr)); min-width: ${150 + n * 146}px">`
  html += '<div></div>' + runs.map((r) => `<div class="fh-phase" style="grid-column: span ${r.span}">${esc(b.phases.find((p) => p.id === r.phase)?.name ?? r.phase)}</div>`).join('')
  // how the customer feels: a line through the moments, a face at each
  const y = (f = 3) => 10 + (5 - f) * 19
  const pts = b.moments.map((m, i) => `${((i + 0.5) * 100) / n},${y(m.feels)}`).join(' ')
  html += `<div class="fh-row" style="padding-top:34px">${w.feels}</div><div class="fh-curve" style="grid-column: span ${n}"><svg viewBox="0 0 100 96" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="var(--red)" stroke-width="2.5" vector-effect="non-scaling-stroke"/></svg>`
  html += b.moments.map((m, i) => (m.feels ? `<button class="fh-face" data-moment="${esc(m.id)}" title="${esc(u.of(m.feels))}" style="left:${((i + 0.5) * 100) / n}%;top:${y(m.feels)}px">${FACES[m.feels]}</button>` : '')).join('') + '</div>'
  const row = (label: string, k: string, cell: (m: Moment) => string, empty: (m: Moment) => boolean) => {
    html += `<div class="fh-row">${label}</div>` + b.moments.map((m) => `<button class="${cls(m, k)}${empty(m) ? ' empty' : ''}" data-moment="${esc(m.id)}">${cell(m)}</button>`).join('')
  }
  const sep = (label: string) => (html += `<div class="fh-sep" style="grid-column: 1 / span ${n + 1}"><span>${label}</span></div>`)
  const marks = (m: Moment) => (m.marks ?? []).map((k) => `<span class="fh-mark" title="${k === 'fail' ? w.fail : w.wait}">${k === 'fail' ? '⚠' : '⏱'}</span>`).join('')
  row(w.evidence, 'evidence', (m) => (m.evidence ?? []).map(esc).join('<br>') || `(${w.none})`, (m) => !(m.evidence ?? []).length)
  row(w.customer, 'customer', (m) => esc(m.customer) + marks(m), () => false)
  sep(w.lineInteraction)
  row(w.front, 'front', (m) => (m.front ?? []).map(doing).join('<br>') || '—', (m) => !(m.front ?? []).length)
  sep(w.lineVisibility)
  row(w.back, 'back', (m) => (m.back ?? []).map(doing).join('<br>') || '—', (m) => !(m.back ?? []).length)
  sep(w.lineInternal)
  row(w.support, 'support', (m) => (m.support ?? []).map((s) => esc(system(s))).join('<br>') || '—', (m) => !(m.support ?? []).length)
  return html + '</div>'
}

const dd = (k: string, v: string) => (v ? `<dt>${k}</dt><dd>${v}</dd>` : '')
function detail() {
  const m = b.moments.find((x) => x.id === picked)
  if (!m) return `<p>${u.pick}</p>`
  const acts = b.actions.filter((a) => a.moment === m.id)
  const ph = b.phases.find((p) => p.id === m.phase)?.name ?? m.phase
  return `<span class="fh-kicker">${esc(w.moment)} · ${esc(ph)}</span><h3>${esc(m.customer)}</h3>
    ${m.feels ? `<div style="font-size:28px">${FACES[m.feels]} <span class="fh-sub">${u.of(m.feels)}${(m.marks ?? []).map((k) => ` · ${k === 'fail' ? `⚠ ${w.fail}` : `⏱ ${w.wait}`}`).join('')}</span></div>` : ''}
    <dl>${dd(w.evidence, (m.evidence ?? []).map(esc).join(' · ') || `<em class="fh-warn">${w.none}</em>`)}${dd(w.front, (m.front ?? []).map(doing).join('<br>') || `<em>${w.nobody}</em>`)}
    ${dd(w.back, (m.back ?? []).map(doing).join('<br>'))}${dd(w.support, (m.support ?? []).map((s) => esc(system(s))).join(' · '))}
    ${dd(w.promise, m.promise ? `«${esc(m.promise.says)}» — ${m.promise.within ? esc(m.promise.within) : `<span class="fh-warn">${w.within.toLowerCase()}?</span>`}, ${m.promise.owner ? esc(actor(m.promise.owner)) : `<span class="fh-warn">${w.owner.toLowerCase()}?</span>`}` : '')}
    ${dd(w.pains, (m.pains ?? []).map((p) => `«${esc(p.says)}»${p.source ? ` <span class="fh-sub">(${esc(p.source)})</span>` : ''}`).join('<br>'))}
    ${dd(w.actions, acts.length ? acts.map((a) => `${esc(a.does)}${a.owner ? ` <span class="fh-sub">· ${esc(actor(a.owner))}${a.due ? ` · ${esc(a.due)}` : ''}</span>` : ''}`).join('<br>') : `<span class="fh-warn">${u.noAction}</span>`)}
    ${dd(w.way, m.way ? esc(m.way) : '')}</dl>`
}

function table(sheet: Sheet) {
  const cell = (v: unknown, th: boolean) => {
    const c = (typeof v === 'object' && v ? v : { v }) as { v: unknown; bold?: boolean; fill?: string }
    const tag = th ? 'th' : 'td'
    return `<${tag}${c.bold && !th ? ' class="b"' : ''}${c.fill && !th ? ` class="fill" style="background:#${c.fill}"` : ''}>${esc(c.v)}</${tag}>`
  }
  const [head, ...rows] = sheet.rows
  return `<div class="fh-table" role="tabpanel"><table><thead><tr>${head.map((v) => cell(v, true)).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((v) => cell(v, false)).join('')}</tr>`).join('')}</tbody></table></div>`
}

function save(blob: Blob, file: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = file
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

// The map as a PNG: the grid inside an SVG (its styles with it, light) as a data: URL, on a canvas at twice the size; a
// browser that will not read the canvas back (Safari) gets the SVG.
async function png() {
  const el = app.querySelector('.fh-grid') as HTMLElement
  const [width, height] = [el.scrollWidth + 32, el.scrollHeight + 32]
  const inner = new XMLSerializer().serializeToString(el).replace(/ picked/g, '')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml" class="fh light" style="min-height:0;padding:16px;background:#fff;width:${width}px"><style>${__MAP_CSS__}</style>${inner}</div></foreignObject></svg>`
  try {
    const img = new Image()
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
    await img.decode()
    const canvas = document.createElement('canvas')
    canvas.width = width * 2
    canvas.height = height * 2
    const ctx = canvas.getContext('2d')!
    ctx.scale(2, 2)
    ctx.drawImage(img, 0, 0)
    const out = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, 'image/png'))
    if (!out) throw new Error('no PNG')
    save(out, `${data.id}.png`)
  } catch {
    save(new Blob([svg], { type: 'image/svg+xml' }), `${data.id}.svg`)
  }
}

app.addEventListener('click', (e) => {
  const t = (e.target as HTMLElement).closest('button')
  if (!t) return
  const d = t.dataset
  if (d.tab) tab = d.tab as Tab
  else if (d.moment) picked = d.moment
  else if (d.look) {
    tab = 'map'
    picked = looks[Number(d.look)].moment ?? picked
  } else if (d.get === 'xlsx') return save(new Blob([workbookFile(sheets)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), `${data.id}.xlsx`)
  else if (d.get === 'yaml') return save(new Blob([data.yaml], { type: 'text/yaml' }), `${data.id}.blueprint.yaml`)
  else if (d.get === 'png') return void png()
  render()
  if (d.moment || d.look) app.querySelector('.fh-detail')?.scrollIntoView({ block: 'nearest' })
})

render()
