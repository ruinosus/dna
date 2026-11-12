// The map of a way of working, one page that opens with no internet: the phases on top, the lanes (who leads) in the
// rows, the stages in order, each gate under the stage it closes. A stage or a gate opens its detail; «To look at» says
// what does not hold (reviewWay) and marks where; the Stages tab is the stage table teams know (what comes in and from
// where, what goes out and to whom, roles, metrics; the gate as a row of its own); the Roles, Gates and Outputs tabs are
// the workbook's own sheets; the buttons download the workbook, the .way.yaml it was drawn from, and a PNG of the map.
import type { LaneColor } from '@engine/murals/api'
import { approvalsOf, type WayDef, type WayGate, type WayStage } from '@engine/murals/way'
import { reviewWay, type Look } from '@engine/ways/review'
import { threadOf, type Source } from '@engine/ways/thread'
import { workbookOf, type Sheet, type Value } from '@engine/ways/workbook'
import { xlsx } from '@engine/ways/xlsx'

declare const __MAP_CSS__: string

interface Data {
  id: string
  name: string
  lang: 'en' | 'pt'
  way: WayDef
  yaml: string
  // build.mjs --no-look: «To look at» starts folded and the map marks nothing, for a map published to others
  look?: boolean
}

const WORDS = {
  en: {
    map: 'Map', excel: 'Excel', yaml: 'YAML', png: 'PNG', look: 'To look at', stage: 'Stage', gate: 'Gate', optional: 'optional',
    leads: 'Led by', takePart: 'Take part', comesIn: 'Comes in', delivers: 'Delivers', activities: 'Activities', where: 'Where', limit: 'Limit',
    then: 'Then', approves: 'Approves', approvesAll: 'Who approves (all)', always: 'always', ifWord: 'if', nobody: 'nobody yet', criteria: 'Must be ready', onFail: 'If not', back: 'back to', after: 'After', results: 'Results',
    pick: 'Pick a stage or a gate on the map to see it whole.', summary: (s: number, g: number, r: number) => `${s} ${s === 1 ? 'stage' : 'stages'} · ${g} ${g === 1 ? 'gate' : 'gates'} · ${r} ${r === 1 ? 'role' : 'roles'}`,
    stages: 'Stages', stage2: 'Stage', description: 'Description', roles: 'Roles', metrics: 'Metrics', outside: 'from outside', comesOut: 'What comes out', nobodyTakes: 'nobody receives it',
    fit: 'Fit to width', more: 'Scroll sideways for the rest →', approvesHere: 'approves', approveMany: 'approve', legendNext: 'the order of the stages', legendGate: 'gate, and who approves it', legendLook: 'to look at', legendOptional: 'optional stage',
  },
  pt: {
    map: 'Mapa', excel: 'Excel', yaml: 'YAML', png: 'PNG', look: 'Para olhar', stage: 'Etapa', gate: 'Gate', optional: 'opcional',
    leads: 'Lidera', takePart: 'Participam', comesIn: 'Entra', delivers: 'Entrega', activities: 'Atividades', where: 'Onde', limit: 'Limite',
    then: 'Depois', approves: 'Aprova', approvesAll: 'Quem aprova (todos)', always: 'sempre', ifWord: 'se', nobody: 'ninguém ainda', criteria: 'Precisa estar pronto', onFail: 'Se não', back: 'volta para', after: 'Depois de', results: 'Resultados',
    pick: 'Escolha uma etapa ou um gate no mapa para ver inteiro.', summary: (s: number, g: number, r: number) => `${s} ${s === 1 ? 'etapa' : 'etapas'} · ${g} ${g === 1 ? 'gate' : 'gates'} · ${r} ${r === 1 ? 'papel' : 'papéis'}`,
    stages: 'Etapas', stage2: 'Etapa', description: 'Descrição', roles: 'Papéis', metrics: 'Métricas', outside: 'de fora', comesOut: 'O que sai', nobodyTakes: 'ninguém recebe',
    fit: 'Caber na largura', more: 'Role para o lado para ver o resto →', approvesHere: 'aprova', approveMany: 'aprovam', legendNext: 'a ordem das etapas', legendGate: 'gate, e quem aprova', legendLook: 'para olhar', legendOptional: 'etapa opcional',
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
const showLook = data.look !== false
const sheets = workbookOf(name, way, lang)
const thread = threadOf(way)
document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
document.title = name

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const colorOf = (laneId: string): LaneColor => {
  const i = way.lanes.findIndex((l) => l.id === laneId)
  return way.lanes[i]?.color ?? ORDER[Math.max(0, i) % ORDER.length]
}
const acronym = (id?: string | null) => (id ? (roles.find((r) => r.id === id)?.acronym ?? id) : '')
const roleName = (id: string) => roles.find((r) => r.id === id)?.name ?? ''
const stageName = (id?: string | null) => (id ? (way.stages.find((s) => s.id === id)?.name ?? id) : '')
const laneName = (id: string) => way.lanes.find((l) => l.id === id)?.name ?? id
const gateAfter = (stage: string) => gates.find((g) => g.after === stage)
const placeName = (id?: string) => way.stages.find((s) => s.id === id)?.name ?? gates.find((g) => g.id === id)?.name ?? ''
// An input with where it comes from: an earlier stage or gate, outside, or nowhere (to look at).
const chip = (x: Source) =>
  x.kind === 'outside' ? `<span class="sd-chip out">${w.outside} · ${esc(x.name)}</span>`
    : x.from ? `<span class="sd-chip${x.late ? ' miss' : ''}">← ${esc(placeName(x.from))} · ${esc(x.name)}</span>`
      : `<span class="sd-chip miss">? ${esc(x.name)}</span>`
const chips = (stage: string) => (thread.inputs[stage] ?? []).map(chip).join('')
// An output with who receives it; when the way describes inputs, one nobody takes says so — as the review does: not the
// last stage's, not a number, not what comes out of a gate (`free`).
const goesTo = (o: { id: string; name: string; kpi?: boolean }, free: boolean) => {
  const to = thread.receivers[o.id] ?? []
  const where = to.length ? ` <span class="sd-to">→ ${esc(to.map(placeName).join(', '))}</span>` : thread.uses && !free && !o.kpi ? ` <span class="sd-to miss">→ ${w.nobodyTakes}</span>` : ''
  return `<li>${esc(o.name)}${where}</li>`
}
const outs = (xs: { id: string; name: string; kpi?: boolean }[], free = false) => (xs.length ? `<ul class="sd-outs">${xs.map((o) => goesTo(o, free)).join('')}</ul>` : '')
// The stages and gates tied to the one picked: where its inputs come from and who receives its outputs.
const linked = (): Set<string> => {
  const id = picked.stage ?? picked.gate
  if (!id) return new Set()
  const own = [...(way.stages.find((s) => s.id === id)?.outputs ?? []), ...(gates.find((g) => g.id === id)?.outputs ?? [])]
  // a gate's inputs are what it checks: the stages that deliver them
  const checks = (gates.find((g) => g.id === id)?.criteria ?? []).flatMap((c) => (c.kind === 'outputs' ? c.outputs : []))
  const makers = way.stages.filter((s) => (s.outputs ?? []).some((o) => checks.includes(o.id))).map((s) => s.id)
  return new Set([...(thread.inputs[id] ?? []).map((x) => x.from).filter((x): x is string => !!x), ...makers, ...own.flatMap((o) => thread.receivers[o.id] ?? [])])
}
const flagged = (at: Look['at']) => showLook && looks.some((l) => l.at && Object.entries(at ?? {}).every(([k, v]) => (l.at as Record<string, string>)[k] === v))
const lookText = (at: Look['at']) =>
  looks.filter((l) => l.at && Object.entries(at ?? {}).every(([k, v]) => (l.at as Record<string, string>)[k] === v)).map((l) => l[lang]).join(' · ')
// The arrows between stages: the way's own `next` links, or one stage after another.
const nexts = (): [string, string][] => {
  const own = (way.links ?? []).filter((l) => l.kind === 'next')
  return own.length ? own.map((l) => [l.source, l.target]) : way.stages.slice(1).map((s, i) => [way.stages[i].id, s.id])
}
// What a gate checks, as the workbook writes it (one line each).
const criteriaOf = (g: WayGate) => {
  const sheet = sheets.find((s) => s.key === 'gates')!
  const row = sheet.rows.find((r) => r[0] === g.id)
  const cell = row?.[4]
  return String(typeof cell === 'object' ? cell.v : (cell ?? '')).split('\n').filter(Boolean)
}

type Tab = 'map' | 'stages' | 'roles' | 'gates' | 'outputs'
let tab: Tab = 'map'
let picked: { stage?: string; gate?: string } = {}
let fit = false
const app = document.getElementById('app')!

function render() {
  const tabs: [Tab, string][] = [['map', w.map], ['stages', w.stages], ['roles', sheetOf('roles').name], ['gates', sheetOf('gates').name], ['outputs', sheetOf('outputs').name]]
  app.innerHTML = `<div class="sd-wrap">
    <header><h1 class="sd-title">${esc(name)}</h1><p class="sd-sub">${esc(way.phases.map((p) => p.name).join(' → '))} · ${w.summary(way.stages.length, gates.length, roles.length)}</p></header>
    <div class="sd-bar" role="tablist">${tabs.map(([k, t]) => `<button class="sd-tab" role="tab" aria-selected="${k === tab}" data-tab="${k}">${esc(t)}</button>`).join('')}
      <span class="sd-space"></span>
      ${tab === 'map' ? `<button class="sd-get" data-fit aria-pressed="${fit}">${w.fit}</button>` : ''}<button class="sd-get" data-get="xlsx">⬇ ${w.excel}</button><button class="sd-get" data-get="yaml">⬇ ${w.yaml}</button>${tab === 'map' ? `<button class="sd-get" data-get="png">⬇ ${w.png}</button>` : ''}
    </div>
    ${looks.length ? `<details class="sd-look"${showLook ? ' open' : ''}><summary><h2>${w.look} · ${looks.length}</h2></summary><ul>${looks.map((l, i) => `<li><button data-look="${i}">${esc(l[lang])}</button></li>`).join('')}</ul></details>` : ''}
    ${tab === 'map' ? `<div class="sd-body"><div class="sd-main"><div class="sd-boardwrap"><section class="sd-board" tabindex="0" aria-label="${esc(w.map)}">${grid()}</section><p class="sd-more" aria-hidden="true">${w.more}</p></div>${legend()}</div><aside class="sd-detail" aria-live="polite">${detail()}</aside></div>` : tab === 'stages' ? stagesTable() : table(sheetOf(tab))}
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
  const near = linked()
  let html = `<div class="sd-grid" style="grid-template-columns: 104px repeat(${n}, minmax(128px, 1fr)); min-width: ${104 + n * 144}px"><svg class="sd-wires" aria-hidden="true"></svg>`
  html += '<div></div>' + runs.map((r) => `<div class="sd-phase" style="grid-column: span ${r.span}">${esc(way.phases.find((p) => p.id === r.phase)?.name ?? r.phase)}</div>`).join('')
  for (const lane of way.lanes) {
    const ink = INKS[colorOf(lane.id)]
    html += `<div class="sd-lane" style="color:${ink}">${esc(lane.name)}${lane.sub ? `<small>${esc(lane.sub)}</small>` : ''}</div>`
    for (const s of way.stages) html += `<div class="sd-cell">${s.lane === lane.id ? stageCard(s, ink, near) : approverMark(s, lane.id, near)}</div>`
  }
  return html + '</div>'
}

function stageCard(s: WayStage, ink: string, near: Set<string>) {
  const g = gateAfter(s.id)
  const cls = ['sd-stage', s.optional ? 'optional' : '', flagged({ stage: s.id }) ? 'flag' : '', picked.stage === s.id ? 'sd-picked' : near.has(s.id) ? 'sd-linked' : ''].filter(Boolean).join(' ')
  const card = `<button class="${cls}" style="--lane:${ink}" data-stage="${esc(s.id)}"${flagged({ stage: s.id }) ? ` title="${esc(`${w.look}: ${lookText({ stage: s.id })}`)}"` : ''}><b>${esc(s.name)}</b>${(s.roles ?? []).length ? `<span>${esc((s.roles ?? []).map(acronym).join(', '))}</span>` : ''}${s.where ? `<span class="sd-where">${w.where.toLowerCase()}: ${esc(s.where)}</span>` : ''}</button>`
  if (!g) return card
  const gcls = ['sd-gate', flagged({ gate: g.id }) ? 'flag' : '', picked.gate === g.id ? 'sd-picked' : near.has(g.id) ? 'sd-linked' : ''].filter(Boolean).join(' ')
  // Spec 2026-11-02 (aprovações no gate): who always approves after the name; each that approves only when something
  // holds below, its condition in the colour of a stage's «where»
  const all = approvalsOf(g)
  const always = all.filter((a) => !a.when).map((a) => acronym(a.by))
  const when = all.filter((a) => a.when).map((a) => `<small class="sd-also">+ ${esc(acronym(a.by))} <span class="sd-where">${w.ifWord} ${esc(a.when!)}</span></small>`).join('')
  return `${card}<button class="${gcls}" data-gate="${esc(g.id)}"><i></i><span>${esc(g.name)}${always.length ? ` <em>· ${esc(always.join(', '))}</em>` : ''}${when}</span></button>`
}

// A gate shown again in the lane of a role that approves it, when that lane does not lead the stage it closes: a lane
// that only approves is not left empty.
function approverMark(s: WayStage, lane: string, near: Set<string>) {
  const g = gateAfter(s.id)
  if (!g || s.lane === lane) return ''
  const here = approvalsOf(g).filter((a) => roles.find((r) => r.id === a.by)?.lane === lane)
  if (!here.length) return ''
  // who always approves, then each who approves only when something holds, as under the stage
  const always = here.filter((a) => !a.when).map((a) => acronym(a.by))
  const who = here.map((a) => acronym(a.by)).join(', ')
  const verb = always.length > 1 ? w.approveMany : w.approvesHere
  const when = here.filter((a) => a.when).map((a) => `<small class="sd-also">+ ${esc(acronym(a.by))} <span class="sd-where">${w.ifWord} ${esc(a.when!)}</span></small>`).join('')
  const cls = ['sd-gate', 'sd-approve', picked.gate === g.id ? 'sd-picked' : near.has(g.id) ? 'sd-linked' : ''].filter(Boolean).join(' ')
  return `<button class="${cls}" data-gate="${esc(g.id)}" aria-label="${esc(`${who}: ${g.name}`)}"><i></i><span>${esc(g.name)}${always.length ? ` <em>· ${esc(always.join(', '))} ${verb}</em>` : ''}${when}</span></button>`
}

// What the map's marks mean, only those it has.
function legend() {
  const items = [`<span><svg width="22" height="10" aria-hidden="true"><path d="M1 5 H16" stroke="currentColor" stroke-width="1.5"/><path d="M15 1.5 L21 5 L15 8.5 Z" fill="currentColor"/></svg> ${w.legendNext}</span>`]
  if (gates.length) items.push(`<span><i class="sd-lg-gate"></i> ${w.legendGate}</span>`)
  if (showLook && looks.some((l) => l.at?.stage || l.at?.gate)) items.push(`<span><i class="sd-lg-look"></i> ${w.legendLook}</span>`)
  if (way.stages.some((s) => s.optional)) items.push(`<span><i class="sd-lg-opt"></i> ${w.legendOptional}</span>`)
  return `<p class="sd-legend">${items.join('')}</p>`
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
      <dl>${row(w.leads, esc(laneName(s.lane)))}${row(w.takePart, list(takePart))}${row(w.comesIn, chips(s.id))}${row(w.delivers, outs(s.outputs ?? [], s === way.stages.at(-1)))}${row(w.metrics, list(s.metrics ?? []))}
      ${row(w.activities, list((s.activities ?? []).map((a) => a.name)))}${row(w.where, esc(s.where ?? ''))}${row(w.limit, s.wip ? String(s.wip) : '')}
      ${row(w.then, after ? `<span class="sd-gate-name">◆ ${esc(after.name)}</span>${approvalsOf(after).length ? ` (${esc(approvalsOf(after).map((a) => acronym(a.by)).join(', '))})` : ''}` : '')}</dl>`
  }
  if (g) {
    return `<span class="sd-kicker">${w.gate}</span><h3 class="sd-gate-name">◆ ${esc(g.name)}</h3>${g.description ? `<p>${esc(g.description)}</p>` : ''}
      <dl>${row(w.after, esc(stageName(g.after)))}${approvalsOf(g).length ? row(w.approvesAll, approvalsOf(g).map((a) => `<span class="sd-approval"><b>${esc(acronym(a.by))}</b> ${esc(roleName(a.by))} <span class="${a.when ? 'sd-where' : 'sd-muted'}">${a.when ? `${w.ifWord} ${esc(a.when)}` : w.always}</span></span>`).join('')) : row(w.approves, `<em>${w.nobody}</em>`)}
      ${row(w.criteria, criteriaOf(g).map(esc).join('<br>'))}${row(w.comesOut, outs(g.outputs ?? [], true))}${row(w.onFail, g.on_fail ? `${w.back} ${esc(stageName(g.on_fail))}` : '')}${row(w.metrics, list(g.metrics ?? []))}${row(w.results, list(g.results.map((r) => r.label)))}</dl>`
  }
  return `<p>${w.pick}</p>`
}

// The stage table: what comes in (and from where), what goes out (and to whom), roles, metrics; each gate a row of its
// own after its stage. A stage's or gate's name opens it on the map.
function stagesTable() {
  const head = [w.stage2, w.description, w.comesIn, w.delivers, w.roles, w.metrics].map((h) => `<th>${h}</th>`).join('')
  const ul = (xs: string[]) => (xs.length ? `<ul class="sd-list">${xs.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '')
  const rows = way.stages.flatMap((s, i) => {
    const g = gateAfter(s.id)
    const stage = `<tr><td><button class="sd-link" data-stage="${esc(s.id)}">${i + 1} · ${esc(s.name)}</button></td><td>${esc(s.description ?? s.question ?? '')}</td><td>${chips(s.id)}</td><td>${outs(s.outputs ?? [], i === way.stages.length - 1)}</td><td>${esc((s.roles ?? []).map(acronym).join(', '))}</td><td>${ul(s.metrics ?? [])}</td></tr>`
    if (!g) return [stage]
    const gin = (g.criteria ?? []).flatMap((c) => (c.kind === 'outputs' ? c.outputs : [])).map((o) => {
      const by = [...way.stages, ...gates].find((x) => (x.outputs ?? []).some((y) => y.id === o))
      const name = (by?.outputs ?? []).find((y) => y.id === o)?.name ?? o
      return `<span class="sd-chip">← ${esc(by?.name ?? '')} · ${esc(name)}</span>`
    }).join('')
    const roles2 = [...approvalsOf(g).map((a) => `${acronym(a.by)} (${w.approves.toLowerCase()}${a.when ? `, ${w.ifWord} ${a.when}` : ''})`), ...(g.roles ?? []).map(acronym)].join(', ')
    return [stage, `<tr class="gate"><td><button class="sd-link" data-gate="${esc(g.id)}">◆ ${esc(g.name)}</button></td><td>${esc(g.description ?? '')}</td><td>${gin}</td><td>${outs(g.outputs ?? [], true)}</td><td>${esc(roles2)}</td><td>${ul(g.metrics ?? [])}</td></tr>`]
  })
  return `<div class="sd-table sd-stages" role="tabpanel"><table><thead><tr>${head}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`
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
  const zoom = el.style.zoom
  el.style.zoom = ''
  const [width, height] = [el.scrollWidth + 32, el.scrollHeight + 32]
  el.style.zoom = zoom
  const inner = new XMLSerializer().serializeToString(el).replace(/ sd-picked/g, '').replace(/ ?zoom: [^;"]*;?/, '')
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

// The arrows, drawn over the grid once it is laid out (and again when its size changes): from the right of a stage to
// the left of the next, square corners in the gap between the columns. Offsets, not screen boxes, so «fit» (zoom) and
// the PNG keep them in place.
function wires() {
  const grid = app.querySelector('.sd-grid') as HTMLElement | null
  const svg = grid?.querySelector('.sd-wires') as SVGSVGElement | null
  if (!grid || !svg) return
  const box = (id: string) => {
    const el = grid.querySelector(`[data-stage="${CSS.escape(id)}"]`) as HTMLElement | null
    if (!el) return null
    let [x, y, at] = [0, 0, el as HTMLElement | null]
    while (at && at !== grid) {
      x += at.offsetLeft
      y += at.offsetTop
      at = at.offsetParent as HTMLElement | null
    }
    return { x, y, w: el.offsetWidth, h: el.offsetHeight }
  }
  const [W, H] = [grid.scrollWidth, grid.scrollHeight]
  svg.setAttribute('width', String(W))
  svg.setAttribute('height', String(H))
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`)
  const id = picked.stage
  const paths = nexts().map(([a, b]) => {
    const [p, q] = [box(a), box(b)]
    if (!p || !q) return ''
    const [x1, y1, x2, y2] = [p.x + p.w, p.y + Math.min(p.h / 2, 22), q.x, q.y + Math.min(q.h / 2, 22)]
    if (x2 <= x1) return ''
    const mx = Math.round((x1 + x2) / 2)
    const d = y1 === y2 ? `M${x1} ${y1} H${x2 - 1}` : `M${x1} ${y1} H${mx} V${y2} H${x2 - 1}`
    return `<path class="${id && (a === id || b === id) ? 'on' : ''}" d="${d}" marker-end="url(#sd-arrow)"/>`
  })
  svg.innerHTML = `<defs><marker id="sd-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="currentColor"/></marker></defs>${paths.join('')}`
}

// When the map is wider than the board: «fit» zooms it to the width; otherwise a fade and a line say there is more.
function layout() {
  const board = app.querySelector('.sd-board') as HTMLElement | null
  const grid = app.querySelector('.sd-grid') as HTMLElement | null
  if (!board || !grid) return
  grid.style.zoom = ''
  const room = board.clientWidth - 32
  if (fit && grid.scrollWidth > room) grid.style.zoom = String(Math.max(0.45, room / grid.scrollWidth))
  const more = !fit && board.scrollWidth > board.clientWidth + 4
  const end = board.scrollLeft + board.clientWidth >= board.scrollWidth - 4
  board.parentElement!.classList.toggle('sd-overflow', more && !end)
  wires()
}
new ResizeObserver(() => layout()).observe(app)
app.addEventListener('scroll', (e) => {
  if ((e.target as HTMLElement).classList?.contains('sd-board')) layout()
}, true)

app.addEventListener('click', (e) => {
  const t = (e.target as HTMLElement).closest('button')
  if (!t) return
  const d = t.dataset
  if (d.fit !== undefined) fit = !fit
  else if (d.tab) tab = d.tab as Tab
  else if (d.stage || d.gate) {
    picked = d.stage ? { stage: d.stage } : { gate: d.gate }
    tab = 'map'
  } else if (d.look) {
    const at = looks[Number(d.look)].at ?? {}
    tab = 'map'
    picked = at.stage ? { stage: at.stage } : at.gate ? { gate: at.gate } : picked
  } else if (d.get === 'xlsx') return save(new Blob([xlsx(sheets)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), `${data.id}.xlsx`)
  else if (d.get === 'yaml') return save(new Blob([data.yaml], { type: 'text/yaml' }), `${data.id}.way.yaml`)
  else if (d.get === 'png') return void png()
  const focus = d.fit !== undefined ? '[data-fit]' : d.tab ? `[data-tab="${d.tab}"]` : d.stage ? `[data-stage="${d.stage}"]` : d.gate ? `[data-gate="${d.gate}"]` : undefined
  render()
  layout()
  if (focus) (app.querySelector(focus) as HTMLElement | null)?.focus()
  if (d.look) app.querySelector('.sd-picked')?.scrollIntoView({ block: 'nearest', inline: 'center' })
  // the detail beside the map on a wide screen, under it otherwise: brought into view when it is under
  if (d.stage || d.gate) app.querySelector('.sd-detail')?.scrollIntoView({ block: 'nearest' })
})

render()
layout()
