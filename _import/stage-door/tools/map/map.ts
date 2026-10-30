// The map of a way of working, one page that opens with no internet: the phases on top, the lanes (who leads) in the
// rows, the stages in order, each gate under the stage it closes. A stage or a gate opens its detail; «To look at» says
// what does not hold (reviewWay) and marks where; the Roles, Gates and Outputs tabs are the workbook's own sheets; the
// buttons download the workbook, the .way.yaml it was drawn from, and a PNG of the map.
import type { LaneColor } from '@engine/murals/api'
import type { WayDef, WayGate, WayStage } from '@engine/murals/way'
import { reviewWay, type Look } from '@engine/ways/review'
import { workbookOf, type Sheet, type Value } from '@engine/ways/workbook'
import { xlsx } from '@engine/ways/xlsx'

declare const __MAP_CSS__: string

interface Data {
  id: string
  name: string
  lang: 'en' | 'pt'
  way: WayDef
  yaml: string
}

const WORDS = {
  en: {
    map: 'Map', excel: 'Excel', yaml: 'YAML', png: 'PNG', look: 'To look at', stage: 'Stage', gate: 'Gate', optional: 'optional',
    leads: 'Led by', takePart: 'Take part', comesIn: 'Comes in', delivers: 'Delivers', activities: 'Activities', where: 'Where', limit: 'Limit',
    then: 'Then', approves: 'Approves', nobody: 'nobody yet', criteria: 'Must be ready', onFail: 'If not', back: 'back to', after: 'After', results: 'Results',
    pick: 'Pick a stage or a gate on the map to see it whole.', summary: (s: number, g: number, r: number) => `${s} stages · ${g} gates · ${r} roles`,
  },
  pt: {
    map: 'Mapa', excel: 'Excel', yaml: 'YAML', png: 'PNG', look: 'Para olhar', stage: 'Etapa', gate: 'Gate', optional: 'opcional',
    leads: 'Lidera', takePart: 'Participam', comesIn: 'Entra', delivers: 'Entrega', activities: 'Atividades', where: 'Onde', limit: 'Limite',
    then: 'Depois', approves: 'Aprova', nobody: 'ninguém ainda', criteria: 'Precisa estar pronto', onFail: 'Se não', back: 'volta para', after: 'Depois de', results: 'Resultados',
    pick: 'Escolha uma etapa ou um gate no mapa para ver inteiro.', summary: (s: number, g: number, r: number) => `${s} etapas · ${g} gates · ${r} papéis`,
  },
}
// The lanes' ink, by the colours the workbook fills them with.
const INKS: Record<LaneColor, string> = { prod: '#2F5BEA', tech: '#2E8F62', qa: '#C77700', forge: '#7B4FC9', slate: '#5E5A52', coral: '#C8442C' }
const ORDER: LaneColor[] = ['prod', 'tech', 'qa', 'forge', 'slate', 'coral']

const data: Data = JSON.parse(document.getElementById('way')!.textContent!)
const { way, lang, name } = data
const w = WORDS[lang]
const gates = way.gates ?? []
const roles = way.roles ?? []
const looks = reviewWay(way)
const sheets = workbookOf(name, way, lang)
document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
document.title = name

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const colorOf = (laneId: string): LaneColor => {
  const i = way.lanes.findIndex((l) => l.id === laneId)
  return way.lanes[i]?.color ?? ORDER[Math.max(0, i) % ORDER.length]
}
const acronym = (id?: string | null) => (id ? (roles.find((r) => r.id === id)?.acronym ?? id) : '')
const stageName = (id?: string | null) => (id ? (way.stages.find((s) => s.id === id)?.name ?? id) : '')
const laneName = (id: string) => way.lanes.find((l) => l.id === id)?.name ?? id
const gateAfter = (stage: string) => gates.find((g) => g.after === stage)
const flagged = (at: Look['at']) => looks.some((l) => l.at && Object.entries(at ?? {}).every(([k, v]) => (l.at as Record<string, string>)[k] === v))
// What a gate checks, as the workbook writes it (one line each).
const criteriaOf = (g: WayGate) => {
  const sheet = sheets.find((s) => s.key === 'gates')!
  const row = sheet.rows.find((r) => r[0] === g.id)
  const cell = row?.[4]
  return String(typeof cell === 'object' ? cell.v : (cell ?? '')).split('\n').filter(Boolean)
}

type Tab = 'map' | 'roles' | 'gates' | 'outputs'
let tab: Tab = 'map'
let picked: { stage?: string; gate?: string } = {}
const app = document.getElementById('app')!

function render() {
  const tabs: [Tab, string][] = [['map', w.map], ['roles', sheetOf('roles').name], ['gates', sheetOf('gates').name], ['outputs', sheetOf('outputs').name]]
  app.innerHTML = `<div class="sd-wrap">
    <header><h1 class="sd-title">${esc(name)}</h1><p class="sd-sub">${esc(way.phases.map((p) => p.name).join(' → '))} · ${w.summary(way.stages.length, gates.length, roles.length)}</p></header>
    <div class="sd-bar" role="tablist">${tabs.map(([k, t]) => `<button class="sd-tab" role="tab" aria-selected="${k === tab}" data-tab="${k}">${esc(t)}</button>`).join('')}
      <span class="sd-space"></span>
      <button class="sd-get" data-get="xlsx">⬇ ${w.excel}</button><button class="sd-get" data-get="yaml">⬇ ${w.yaml}</button>${tab === 'map' ? `<button class="sd-get" data-get="png">⬇ ${w.png}</button>` : ''}
    </div>
    ${looks.length ? `<section class="sd-look"><h2>${w.look}</h2><ul>${looks.map((l, i) => `<li><button data-look="${i}">${esc(l[lang])}</button></li>`).join('')}</ul></section>` : ''}
    ${tab === 'map' ? `<div class="sd-body"><section class="sd-board">${grid()}</section><aside class="sd-detail" aria-live="polite">${detail()}</aside></div>` : table(sheetOf(tab))}
  </div>`
}

const sheetOf = (key: Sheet['key']) => sheets.find((s) => s.key === key)!

function grid() {
  const n = way.stages.length
  // the phases over the stages they hold, in runs (a phase that comes back later is a run of its own)
  const runs: { phase: string; span: number }[] = []
  for (const s of way.stages) {
    if (runs.at(-1)?.phase === s.phase) runs.at(-1)!.span++
    else runs.push({ phase: s.phase, span: 1 })
  }
  let html = `<div class="sd-grid" style="grid-template-columns: 104px repeat(${n}, minmax(128px, 1fr)); min-width: ${104 + n * 136}px">`
  html += '<div></div>' + runs.map((r) => `<div class="sd-phase" style="grid-column: span ${r.span}">${esc(way.phases.find((p) => p.id === r.phase)?.name ?? r.phase)}</div>`).join('')
  for (const lane of way.lanes) {
    const ink = INKS[colorOf(lane.id)]
    html += `<div class="sd-lane" style="color:${ink}">${esc(lane.name)}${lane.sub ? `<small>${esc(lane.sub)}</small>` : ''}</div>`
    for (const s of way.stages) html += `<div class="sd-cell">${s.lane === lane.id ? stageCard(s, ink) : ''}</div>`
  }
  return html + '</div>'
}

function stageCard(s: WayStage, ink: string) {
  const g = gateAfter(s.id)
  const cls = ['sd-stage', s.optional ? 'optional' : '', flagged({ stage: s.id }) ? 'flag' : '', picked.stage === s.id ? 'sd-picked' : ''].filter(Boolean).join(' ')
  const card = `<button class="${cls}" style="--lane:${ink}" data-stage="${esc(s.id)}"><b>${esc(s.name)}</b>${(s.roles ?? []).length ? `<span>${esc((s.roles ?? []).map(acronym).join(', '))}</span>` : ''}${s.where ? `<span class="sd-where">${w.where.toLowerCase()}: ${esc(s.where)}</span>` : ''}</button>`
  if (!g) return card
  const gcls = ['sd-gate', flagged({ gate: g.id }) ? 'flag' : '', picked.gate === g.id ? 'sd-picked' : ''].filter(Boolean).join(' ')
  return `${card}<button class="${gcls}" data-gate="${esc(g.id)}"><i></i><span>${esc(g.name)}${g.approver ? ` <em>· ${esc(acronym(g.approver))}</em>` : ''}</span></button>`
}

const list = (xs: string[]) => esc(xs.join(' · '))
const row = (k: string, v: string) => (v ? `<dt>${k}</dt><dd>${v}</dd>` : '')

function detail() {
  const s = picked.stage ? way.stages.find((x) => x.id === picked.stage) : undefined
  const g = picked.gate ? gates.find((x) => x.id === picked.gate) : undefined
  if (s) {
    const after = gateAfter(s.id)
    const takePart = (s.roles ?? []).map(acronym)
    return `<span class="sd-kicker">${w.stage}${s.optional ? ` · ${w.optional}` : ''}</span><h3>${esc(s.question ?? s.name)}</h3>${s.question ? `<p>${esc(s.name)}</p>` : ''}
      ${s.description ? `<p>${esc(s.description)}</p>` : ''}
      <dl>${row(w.leads, esc(laneName(s.lane)))}${row(w.takePart, list(takePart))}${row(w.comesIn, list(s.inputs ?? []))}${row(w.delivers, list((s.outputs ?? []).map((o) => o.name)))}
      ${row(w.activities, list((s.activities ?? []).map((a) => a.name)))}${row(w.where, esc(s.where ?? ''))}${row(w.limit, s.wip ? String(s.wip) : '')}
      ${row(w.then, after ? `<span class="sd-gate-name">◆ ${esc(after.name)}</span>${after.approver ? ` (${esc(acronym(after.approver))})` : ''}` : '')}</dl>`
  }
  if (g) {
    return `<span class="sd-kicker">${w.gate}</span><h3 class="sd-gate-name">◆ ${esc(g.name)}</h3>${g.description ? `<p>${esc(g.description)}</p>` : ''}
      <dl>${row(w.after, esc(stageName(g.after)))}${row(w.approves, g.approver ? esc(acronym(g.approver)) : `<em>${w.nobody}</em>`)}
      ${row(w.criteria, criteriaOf(g).map(esc).join('<br>'))}${row(w.onFail, g.on_fail ? `${w.back} ${esc(stageName(g.on_fail))}` : '')}${row(w.results, list(g.results.map((r) => r.label)))}</dl>`
  }
  return `<p>${w.pick}</p>`
}

// A workbook sheet as a table: its header, bold and centred cells, the lanes' fills.
function table(sheet: Sheet) {
  const cell = (v: Value, th: boolean) => {
    const c = typeof v === 'object' ? v : { v }
    const cls = [c.center ? 'c' : '', c.bold && !th ? 'b' : '', c.fill ? 'lane' : ''].filter(Boolean).join(' ')
    const tag = th ? 'th' : 'td'
    return `<${tag}${cls ? ` class="${cls}"` : ''}${c.fill && !th ? ` style="background:#${c.fill}"` : ''}>${esc(c.v)}</${tag}>`
  }
  const [head, ...rows] = sheet.rows
  return `<div class="sd-table" role="tabpanel"><table><thead><tr>${head.map((v) => cell(v, true)).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((v) => cell(v, false)).join('')}</tr>`).join('')}</tbody></table></div>`
}

function save(blob: Blob, file: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = file
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

// The map as a PNG: the grid drawn inside an SVG (its styles with it, light) given as a data: URL (a blob: one leaves
// the canvas unreadable in Chrome), then on a canvas at twice the size. A browser that will not read a canvas back after
// that (Safari) gets the SVG itself.
async function png() {
  const el = app.querySelector('.sd-grid') as HTMLElement
  const [width, height] = [el.scrollWidth + 32, el.scrollHeight + 32]
  const inner = new XMLSerializer().serializeToString(el).replace(/ sd-picked/g, '')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml" class="sd light" style="min-height:0;padding:16px;background:#fff;width:${width}px"><style>${__MAP_CSS__}</style>${inner}</div></foreignObject></svg>`
  const blob = new Blob([svg], { type: 'image/svg+xml' })
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
    save(blob, `${data.id}.svg`)
  }
}

app.addEventListener('click', (e) => {
  const t = (e.target as HTMLElement).closest('button')
  if (!t) return
  const d = t.dataset
  if (d.tab) tab = d.tab as Tab
  else if (d.stage) picked = { stage: d.stage }
  else if (d.gate) picked = { gate: d.gate }
  else if (d.look) {
    const at = looks[Number(d.look)].at ?? {}
    tab = 'map'
    picked = at.stage ? { stage: at.stage } : at.gate ? { gate: at.gate } : picked
  } else if (d.get === 'xlsx') return save(new Blob([xlsx(sheets)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), `${data.id}.xlsx`)
  else if (d.get === 'yaml') return save(new Blob([data.yaml], { type: 'text/yaml' }), `${data.id}.way.yaml`)
  else if (d.get === 'png') return void png()
  const focus = d.tab ? `[data-tab="${d.tab}"]` : d.stage ? `[data-stage="${d.stage}"]` : d.gate ? `[data-gate="${d.gate}"]` : undefined
  render()
  if (focus) (app.querySelector(focus) as HTMLElement | null)?.focus()
  if (d.look) app.querySelector('.sd-picked')?.scrollIntoView({ block: 'nearest', inline: 'center' })
})

render()
