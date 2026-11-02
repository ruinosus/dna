// The comparison on one page that opens with no internet: «to look at» on top; the matrix — a row per fact by
// dimension, a column per agent, ● has it, × off a pattern, ◐ declared — filtered by role and focus area; the patterns
// someone is off as cards, the rest folded. A fact, a mark or a card opens who has it and the file and line of each.
// Tabs: the patterns as the workbook has them, the cast (a card per agent), the Microsoft patterns, what the analysis
// did not understand. Downloads: the workbook, the cast file, a PNG of the matrix.
import type { Cast } from '../cast'
import type { Result } from '../compare'
import { DIMENSIONS, dimensionOf, labelOf, type Dimension, type Lang } from '../labels'
import { MS_PATTERNS, PATTERNS_URL } from '../microsoft'
import type { FocusArea, Role } from '../profile'
import { groupPatterns, type Look } from '../review'
import { workbookFile, workbookOf, type Sheet } from '../workbook'
import { roleWord, SHEET_WORDS } from '../words'

declare const __MAP_CSS__: string

interface Data { id: string; lang: Lang; result: Result; looks: Look[]; cast: Cast; castYaml: string; focusAreas: FocusArea[]; threshold: number }
const UI = {
  en: {
    map: 'Map', patterns: 'Patterns', cast: 'Cast', microsoft: 'Microsoft', unknown: (n: number) => `What the analysis did not understand (${n})`,
    matrix: 'Who has what', candidates: 'Patterns to decide', everyone: (n: number) => `Everybody already does it (${n})`, all: 'All', role: 'Role', focus: 'Focus',
    legend: '● has it (click for the file) · × off a pattern of its role · ◐ declared by people', pattern: 'pattern', of: (h: number, n: number, r: string) => `${h} of ${n} ${r}`,
    who: 'Who has it', lacks: 'Off it', none: 'nobody', decision: 'Decision', toDecide: 'to decide — in the workbook or the cast file', alone: 'Only one has it: innovation or debt?',
    orchestratorDoes: 'Only the orchestrator does it', sign: 'How cast-list knows', follows: 'Who follows it', declaredOnly: 'only declared', nothingUnknown: 'Everything was understood.',
    facts: 'Facts', off: 'Off a pattern', solo: 'Only it has', children: 'Children', close: 'Close ✕', foot: 'The facts come from the YAML files; nothing was made up.',
    summary: (n: number, p: number, o: number, s: number, t: number) => `${n} in the cast · ${p} patterns · ${o} off a pattern · ${s} only one has · threshold ${t}% of each role`,
    excel: '⬇ Excel', yaml: '⬇ cast.yaml', png: '⬇ PNG', name: 'Name', said: 'declared',
  },
  pt: {
    map: 'Mapa', patterns: 'Padrões', cast: 'Elenco', microsoft: 'Microsoft', unknown: (n: number) => `O que a análise não entendeu (${n})`,
    matrix: 'Quem tem o quê', candidates: 'Padrões para decidir', everyone: (n: number) => `Todos já fazem (${n})`, all: 'Todos', role: 'Papel', focus: 'Foco',
    legend: '● tem (clique para ver o arquivo) · × fora de um padrão do seu papel · ◐ declarado por pessoas', pattern: 'padrão', of: (h: number, n: number, r: string) => `${h} de ${n} ${r}`,
    who: 'Quem tem', lacks: 'Fora', none: 'ninguém', decision: 'Decisão', toDecide: 'a decidir — na planilha ou no cast.yaml', alone: 'Só um tem: inovação ou dívida?',
    orchestratorDoes: 'Só o orquestrador faz', sign: 'Como a cast-list sabe', follows: 'Quem segue', declaredOnly: 'só declarado', nothingUnknown: 'Tudo foi entendido.',
    facts: 'Fatos', off: 'Fora do padrão', solo: 'Só ele tem', children: 'Filhos', close: 'Fechar ✕', foot: 'Os fatos vêm dos arquivos YAML; nada foi inventado.',
    summary: (n: number, p: number, o: number, s: number, t: number) => `${n} no elenco · ${p} padrões · ${o} fora do padrão · ${s} só um tem · limite ${t}% de cada papel`,
    excel: '⬇ Excel', yaml: '⬇ cast.yaml', png: '⬇ PNG', name: 'Nome', said: 'declarado',
  },
}

const data: Data = JSON.parse(document.getElementById('cast')!.textContent!)
const { result: r, lang, looks } = data
const u = UI[lang]
const w = SHEET_WORDS[lang]
const sheets = workbookOf(r, looks, data.cast, lang)
document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
document.title = r.name ?? data.id
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const label = (k: string) => esc(labelOf(k, lang))
const agents = [...r.agents].sort((a, b) => (a.role === b.role ? a.id.localeCompare(b.id) : a.role === 'orchestrator' ? -1 : 1))
const patternOf = (k: string) => r.patterns.find((p) => p.key === k)
const offOf = (k: string) => r.offPattern.filter((o) => o.key === k).map((o) => o.agent)
const badge = (k: string) => {
  const p = patternOf(k)
  if (!p) return ''
  const d = p.decision ? `<span class="cl-badge ${p.decision.status}">${esc(w[p.decision.status === 'accepted' ? 'accept' : 'reject'])}</span>` : ''
  return `<span class="cl-badge ${p.scope}">${u.pattern} · ${esc(w[p.scope])}</span>${d}`
}

type Tab = 'map' | 'patterns' | 'cast' | 'microsoft' | 'unknown'
let tab: Tab = 'map'
let picked: { key: string; agent?: string } | undefined
let role: 'all' | Role = 'all'
let focus: string | undefined
const app = document.getElementById('app')!

function render() {
  const tabs: [Tab, string][] = [['map', u.map], ['patterns', u.patterns], ['cast', u.cast], ['microsoft', u.microsoft], ['unknown', u.unknown(r.unknown.length)]]
  const off = new Set(r.offPattern.map((o) => o.agent)).size
  app.innerHTML = `<div class="cl-wrap">
    <header><h1 class="cl-title">${esc(r.name ?? data.id)}</h1><p class="cl-sub">${u.summary(r.agents.length, r.patterns.length, off, looks.filter((l) => l.key === 'solo').length, Math.round(data.threshold * 100))}</p><p class="cl-private">${esc(w.privacy)}</p></header>
    <div class="cl-bar" role="tablist">${tabs.map(([k, t]) => `<button class="cl-tab" role="tab" aria-selected="${k === tab}" data-tab="${k}">${esc(t)}</button>`).join('')}
      <span class="cl-space"></span><button class="cl-get" data-get="xlsx">${u.excel}</button><button class="cl-get" data-get="yaml">${u.yaml}</button>${tab === 'map' ? `<button class="cl-get" data-get="png">${u.png}</button>` : ''}</div>
    ${tab === 'map' ? mapTab() : tab === 'patterns' ? table(sheets.find((s) => s.key === 'patterns')!) : tab === 'cast' ? castTab() : tab === 'microsoft' ? microsoftTab() : unknownTab()}
    <p class="cl-foot">${u.foot}</p>
  </div>`
}

function mapTab() {
  const look = looks.length ? `<section class="cl-look"><h2>${esc(w.look)}</h2><ul>${looks.map((l, i) => `<li><button data-look="${i}">${esc(l[lang])}</button></li>`).join('')}</ul></section>` : ''
  return `${look}<div class="cl-body${picked ? ' with-detail' : ''}"><div class="cl-wrap" style="gap:16px">${matrix()}${patternCards()}</div>${picked ? `<aside class="cl-card cl-detail" aria-live="polite">${detail()}</aside>` : ''}</div>`
}

function matrix() {
  const cols = agents.filter((a) => role === 'all' || a.role === role)
  const area = data.focusAreas.find((f) => f.id === focus)
  const keys = [...new Set([...r.agents.flatMap((a) => Object.keys(a.facts)), ...r.patterns.map((p) => p.key)])].filter((k) => !area || area.facts.includes(k))
  const off = new Set(r.offPattern.map((o) => `${o.agent} ${o.key}`))
  const chip = (attr: string, value: string, on: boolean, text: string) => `<button class="cl-chip" ${attr}="${esc(value)}" aria-pressed="${on}">${esc(text)}</button>`
  const filters = `<div class="cl-filters">${u.role}: ${chip('data-role', 'all', role === 'all', u.all)}${chip('data-role', 'specialist', role === 'specialist', w.specialist)}${chip('data-role', 'orchestrator', role === 'orchestrator', w.orchestrator)}
    ${data.focusAreas.length ? `<span style="margin-left:10px">${u.focus}:</span> ${chip('data-focus', '', !focus, u.all)}${data.focusAreas.map((f) => chip('data-focus', f.id, focus === f.id, f.name)).join('')}` : ''}</div>`
  let body = ''
  for (const dim of Object.keys(DIMENSIONS) as Dimension[]) {
    const rows = keys.filter((k) => dimensionOf(k) === dim).sort((a, b) => labelOf(a, lang).localeCompare(labelOf(b, lang)))
    if (!rows.length) continue
    body += `<tr class="cl-dim"><td colspan="${cols.length + 1}">${esc(DIMENSIONS[dim][lang])}</td></tr>`
    body += rows.map((k) => `<tr><th scope="row" style="text-align:left;font-weight:400"><button class="cl-fact${picked?.key === k && !picked.agent ? ' picked' : ''}" data-key="${esc(k)}">${label(k)}</button>${badge(k)}</th>${cols.map((a) => {
      const mark = k in a.facts ? (k.startsWith('declared:') ? ['said', '◐'] : ['has', '●']) : off.has(`${a.id} ${k}`) ? ['off', '×'] : undefined
      return `<td class="cl-mark${mark ? ` ${mark[0]}` : ''}">${mark ? `<button data-key="${esc(k)}" data-agent="${esc(a.id)}" aria-label="${esc(a.id)}: ${label(k)}">${mark[1]}</button>` : ''}</td>`
    }).join('')}</tr>`).join('')
  }
  return `<section class="cl-card"><h2>${u.matrix}</h2>${filters}<div class="cl-scroll"><table class="cl-matrix"><thead><tr><th></th>${cols.map((a) => `<th scope="col">${esc(a.id)}<small>${esc(w[a.role])}</small></th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div><p class="cl-legend">${u.legend}</p></section>`
}

function patternCards() {
  const { look, everyone } = groupPatterns(r)
  const card = (key: string) => {
    const p = patternOf(key)!
    const them = r.agents.filter((a) => a.role === p.role).length
    const lacking = offOf(key)
    return `<button class="cl-pattern${picked?.key === key ? ' picked' : ''}" data-pattern="${esc(key)}"><b>${label(key)}</b><span>${badge(key)} ${u.of(p.agents.filter((id) => r.roles[id] === p.role).length, them, roleWord(p.role, lang, them))}</span>
      ${lacking.length ? `<span class="cl-lack">${u.lacks}: ${esc(lacking.join(', '))}</span>` : ''}<span>${u.decision}: ${p.decision ? `${esc(w[p.decision.status === 'accepted' ? 'accept' : 'reject'])}${p.decision.why ? ` — ${esc(p.decision.why)}` : ''}` : `<i>${u.toDecide}</i>`}</span></button>`
  }
  return `<section class="cl-card"><h2>${u.candidates}</h2>${look.length ? `<div class="cl-cards">${look.map((p) => card(p.key)).join('')}</div>` : `<p class="cl-empty">—</p>`}
    ${everyone.length ? `<details class="cl-everyone"><summary>${u.everyone(everyone.length)}</summary><ul>${everyone.map((p) => `<li><button class="cl-fact" data-pattern="${esc(p.key)}">${label(p.key)}</button> <span class="cl-badge ${p.scope}">${esc(w[p.scope])}</span></li>`).join('')}</ul></details>` : ''}</section>`
}

function detail() {
  const { key, agent } = picked!
  const p = patternOf(key)
  const holders = r.agents.filter((a) => key in a.facts && (!agent || a.id === agent))
  const files = holders.map((a) => `<li><b>${esc(a.id)}</b>${a.facts[key].map((s) => `<div class="cl-file">${esc(s.file)}${s.line ? `:${s.line}` : ''}</div>`).join('')}</li>`).join('')
  const lacking = offOf(key).filter((id) => !agent || id === agent)
  const solo = r.solos.some((s) => s.key === key)
  const orch = r.orchestratorDoes.some((s) => s.key === key)
  return `<button class="cl-close" data-close="1">${u.close}</button><span class="cl-kicker">${esc(DIMENSIONS[dimensionOf(key)][lang])}</span><h3>${label(key)}</h3><code>${esc(key)}</code>
    ${p ? `<div>${badge(key)}</div><div>${u.decision}: ${p.decision ? `${esc(w[p.decision.status === 'accepted' ? 'accept' : 'reject'])}${p.decision.why ? ` — ${esc(p.decision.why)}` : ''}` : `<i>${u.toDecide}</i>`}</div>` : ''}
    ${solo ? `<div>${u.alone}</div>` : orch ? `<div>${u.orchestratorDoes}</div>` : ''}
    <div><b>${u.who}</b>${files ? `<ul>${files}</ul>` : ` — ${u.none}`}</div>
    ${lacking.length ? `<div><b>${u.lacks}</b>: <span style="color:var(--off)">${esc(lacking.join(', '))}</span></div>` : ''}`
}

function castTab() {
  return `<div class="cl-agents">${agents.map((a) => {
    const off = r.offPattern.filter((o) => o.agent === a.id)
    const solos = r.solos.filter((s) => s.agents[0] === a.id)
    const unknown = r.unknown.filter((x) => x.agent === a.id)
    return `<section class="cl-card cl-agent"><span class="cl-kicker">${esc(w[a.role])}</span><h3>${esc(a.id)}</h3>${a.displayName ? `<code>${esc(a.displayName)}</code>` : ''}<dl>
      <dt>${u.facts}</dt><dd>${Object.keys(a.facts).length}</dd>
      ${off.length ? `<dt>${u.off}</dt><dd class="cl-lack">${off.map((o) => label(o.key)).join('<br>')}</dd>` : ''}
      ${solos.length ? `<dt>${u.solo}</dt><dd>${solos.map((s) => label(s.key)).join('<br>')}</dd>` : ''}
      ${a.children.length ? `<dt>${u.children}</dt><dd>${a.children.map((c) => `${esc(c.name)} <span class="cl-sub">(${Object.keys(c.facts).map(label).join(', ')})</span>`).join('<br>')}</dd>` : ''}
      ${unknown.length ? `<dt>${esc(w.unknown)}</dt><dd>${unknown.map((x) => esc(x.file)).join('<br>')}</dd>` : ''}</dl></section>`
  }).join('')}</div>`
}

function microsoftTab() {
  const rows = MS_PATTERNS.map((p) => {
    const who = r.agents.filter((a) => `ms:${p.id}` in a.facts || `declared:ms:${p.id}` in a.facts).map((a) => a.id)
    return `<tr><td><a href="${PATTERNS_URL}/${p.id}.md" target="_blank" rel="noopener">${esc(p.name)}</a></td><td>${esc(p.sign ?? u.declaredOnly)}</td><td>${who.length ? esc(who.join(', ')) : `<span class="cl-sub">${u.none}</span>`}</td></tr>`
  }).join('')
  return `<section class="cl-card cl-table"><table><thead><tr><th>${u.microsoft}</th><th>${u.sign}</th><th>${u.follows}</th></tr></thead><tbody>${rows}</tbody></table></section>`
}

function unknownTab() {
  const s = sheets.find((x) => x.key === 'unknown')
  return s ? table(s) : `<section class="cl-card"><p class="cl-empty">${u.nothingUnknown}</p></section>`
}

function table(sheet: Sheet) {
  const cell = (v: unknown, th: boolean) => {
    const c = (typeof v === 'object' && v ? v : { v }) as { v: unknown; fill?: string }
    const tag = th ? 'th' : 'td'
    return `<${tag}${c.fill && !th ? ` style="background:#${c.fill};color:#1d2330"` : ''}>${esc(c.v)}</${tag}>`
  }
  const [head, ...rows] = sheet.rows
  return `<section class="cl-card cl-table" role="tabpanel"><table><thead><tr>${head.map((v) => cell(v, true)).join('')}</tr></thead><tbody>${rows.map((x) => `<tr>${x.map((v) => cell(v, false)).join('')}</tr>`).join('')}</tbody></table></section>`
}

function save(blob: Blob, file: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = file
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

// The matrix as a PNG: inside an SVG (its styles with it, light) as a data: URL, on a canvas at twice the size; a
// browser that will not read the canvas back (Safari) gets the SVG.
async function png() {
  const el = app.querySelector('.cl-matrix') as HTMLElement
  const [width, height] = [el.scrollWidth + 32, el.scrollHeight + 32]
  const inner = new XMLSerializer().serializeToString(el).replace(/ picked/g, '')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml" class="cl light" style="min-height:0;padding:16px;background:#fff;width:${width}px"><style>${__MAP_CSS__}</style>${inner}</div></foreignObject></svg>`
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
  else if (d.role) role = d.role as typeof role
  else if (d.focus !== undefined) focus = d.focus || undefined
  else if (d.key) picked = { key: d.key, ...(d.agent ? { agent: d.agent } : {}) }
  else if (d.pattern) picked = { key: d.pattern }
  else if (d.close) picked = undefined
  else if (d.look) {
    const l = looks[Number(d.look)]
    tab = 'map'
    if (l.fact) picked = { key: l.fact, ...(l.agents.length === 1 ? { agent: l.agents[0] } : {}) }
    // what is off a pattern is not «had»: show the whole fact, with who is off it
    if (l.key === 'off' || l.key === 'gap' || l.key === 'conflict') picked = l.fact ? { key: l.fact } : picked
    if (l.key === 'unknown') tab = 'unknown'
  } else if (d.get === 'xlsx') return save(new Blob([workbookFile(sheets)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), `${data.id}.xlsx`)
  else if (d.get === 'yaml') return save(new Blob([data.castYaml], { type: 'text/yaml' }), `${data.id}.cast.yaml`)
  else if (d.get === 'png') return void png()
  render()
  if (d.key || d.pattern || d.look) app.querySelector('.cl-detail')?.scrollIntoView({ block: 'nearest' })
})

render()
