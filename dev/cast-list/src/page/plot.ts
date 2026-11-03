// The stage on one page that opens with no internet: the cast as nodes and arrows, the traffic moving along the arrows
// in proportion to each one's topic starts, lenses that light who follows a pattern and who is off, a follow spot that
// walks one call of the orchestrator step by step, and the card of an actor. With reduced motion, nothing moves.
import { shortNames, type Lang } from '../labels'
import type { Scene, Stage, StageEdge, StageNode } from '../stage'

interface Data { id: string; lang: Lang; stage: Stage; map?: string; playbill?: string }
const UI = {
  en: {
    title: 'Stage', sub: 'The cast on stage: who talks to whom, the traffic each one gets, the patterns as lenses, and a follow spot that walks a call.',
    privacy: 'This file holds the client’s data: keep it in the client’s environment.', client: 'Customer',
    lenses: 'Lenses — light a pattern', lensHint: 'Pick a lens: who follows the pattern lights green, who is off blinks red.',
    scenes: 'Follow spot — walk a call', narrIdle: 'Pick a call under «Follow spot» to walk it step by step here.', actor: 'Actor', actorHint: 'Click someone on stage.', resume: 'See the résumé →', map: '← Map',
    vol: (n: number, d: number) => `${n.toLocaleString('en')} topic starts / ${d} days`, silent: 'no telemetry', noTraffic: 'The traffic shows with the export of Application Insights (--telemetry).',
    legend: ['traffic (topic starts of who receives it)', 'off a pattern', 'to decide', 'not in the folder / unused'], structure: 'Inner arrows (flows, systems) are structure, not measured traffic.',
    step: (k: number, n: number) => `step ${k}/${n}`, keys: '← → to move · space plays all · Esc leaves',
    orchestrator: 'Orchestrator', specialist: 'Specialist', fingerprint: 'Fingerprint of its instructions', foot: 'cast-list · no model: what is here is what the files and tables say.',
  },
  pt: {
    title: 'Palco', sub: 'O elenco no palco: quem fala com quem, o tráfego de cada um, os padrões como lentes, e um canhão que segue uma chamada.',
    privacy: 'Este arquivo tem dados do cliente: deixe-o no ambiente dele.', client: 'Cliente',
    lenses: 'Lentes — acenda um padrão', lensHint: 'Escolha uma lente: quem segue o padrão acende em verde, quem foge pisca em vermelho.',
    scenes: 'Canhão seguidor — siga uma chamada', narrIdle: 'Escolha uma chamada em «Canhão seguidor» para segui-la passo a passo aqui.', actor: 'Ator', actorHint: 'Clique em alguém no palco.', resume: 'Ver currículo →', map: '← Mapa',
    vol: (n: number, d: number) => `${n.toLocaleString('pt-BR')} inícios de tópico / ${d} dias`, silent: 'sem telemetria', noTraffic: 'O tráfego aparece com a exportação do Application Insights (--telemetry).',
    legend: ['tráfego (inícios de tópico de quem recebe)', 'fora do padrão', 'a decidir', 'fora da pasta / sem uso'], structure: 'As setas internas (fluxos, sistemas) são estrutura, não tráfego medido.',
    step: (k: number, n: number) => `passo ${k}/${n}`, keys: '← → avançam e voltam · espaço toca tudo · Esc sai',
    orchestrator: 'Orquestrador', specialist: 'Especialista', fingerprint: 'Impressão digital das instruções', foot: 'cast-list · sem modelo: o que está aqui é o que os arquivos e as planilhas dizem.',
  },
}

const data: Data = JSON.parse(document.getElementById('cast')!.textContent!)
const { stage: st, lang } = data
const u = UI[lang]
document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
document.title = `${u.title} · ${st.name ?? data.id}`
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const app = document.getElementById('app')!
const still = matchMedia('(prefers-reduced-motion: reduce)').matches
const W = 168
const H = 48
// about how wide a character of an arrow's label is (11px), to keep a label off the nodes
const CHAR = 5.6
const overNode = (b: { x: number; y: number; w: number }) => st.nodes.some((n) => b.x < n.x + W / 2 && b.x + b.w > n.x - W / 2 && b.y > n.y - H / 2 - 2 && b.y - 11 < n.y + H / 2 + 2)
const at = (id: string) => st.nodes.find((n) => n.id === id)!
const isAgent = (n: StageNode) => n.kind === 'orchestrator' || n.kind === 'specialist'
let lens: string | undefined
let scene: Scene | undefined
let step = 0
let actor: string | undefined
let playing: number | undefined

// an arrow: a horizontal Bézier from the right of one to the left of the other (or the other way round)
function path(e: StageEdge) {
  const a = at(e.from)
  const b = at(e.to)
  const forward = b.x >= a.x
  const x1 = a.x + (forward ? W / 2 : -W / 2)
  const x2 = b.x + (forward ? -W / 2 : W / 2)
  const mid = (x1 + x2) / 2
  return { d: `M${x1},${a.y} C${mid},${a.y} ${mid},${b.y} ${x2},${b.y}`, mx: mid, my: (a.y + b.y) / 2, x2, y2: b.y }
}
const label = (n: StageNode) => (n.kind === 'client' ? u.client : n.labels?.[lang] ?? n.label)
const clip = (s: string, max = 24) => (s.length > max ? `${s.slice(0, max - 1)}…` : s)
// the display name without the part every one of the cast shares («Bodega Azul - Pedidos» → «Pedidos»)
const agents = st.nodes.filter(isAgent)
const shorten = shortNames([...agents, ...st.nodes.filter((n) => n.kind === 'ghost')].map((n) => n.label))
const short = (n: StageNode) => (isAgent(n) || n.kind === 'ghost' ? shorten(n.label) : label(n))

function svg() {
  const lensOf = st.lenses.find((l) => l.id === lens)
  const lit = lensOf ? new Set([...lensOf.ok, ...lensOf.amber, ...lensOf.bad]) : undefined
  const cls = (n: StageNode) => {
    const c = ['pl-node', n.kind, n.unused ? 'unused' : '']
    if (lensOf) c.push(lensOf.bad.includes(n.id) ? 'l-bad' : lensOf.amber.includes(n.id) ? 'l-amber' : lensOf.ok.includes(n.id) ? 'l-ok' : '')
    if (scene && scene.steps[step]?.node === n.id && scene.steps[step].warn) c.push('warn')
    return c.filter(Boolean).join(' ')
  }
  const groups = st.groups.map((g) => `<rect class="pl-band" x="${at(st.nodes.find((n) => n.kind === 'specialist')!.id).x - W / 2 - 18}" y="${g.y1}" width="${W + 36}" height="${g.y2 - g.y1}" rx="12"/><text class="pl-group" x="${at(st.nodes.find((n) => n.kind === 'specialist')!.id).x - W / 2 - 10}" y="${g.y1 - 6}">${esc(g.label)}</text>`).join('')
  const edges = st.edges.map((e, i) => {
    const p = path(e)
    const tone = e.tone ?? ''
    // what an arrow into one of the cast says sits by where it arrives, so it never lands on a neighbour
    const into = e.kind === 'traffic' && at(e.to).kind !== 'ghost'
    const text = e.label ? clip(e.label[lang], into ? 56 : 40) : ''
    const box = into ? { x: p.x2 - 10 - text.length * CHAR, y: p.y2 - 9, w: text.length * CHAR } : { x: p.mx - (text.length * CHAR) / 2, y: p.my - 6, w: text.length * CHAR }
    // with a lens, only the arrows that touch someone it lights say something; and never a word over a node
    const quiet = lit && !lit.has(e.from) && !lit.has(e.to)
    const lab = text && !quiet && !overNode(box) ? (into ? `<text class="pl-elabel ${tone}" x="${p.x2 - 10}" y="${p.y2 - 9}" text-anchor="end">${esc(text)}</text>` : `<text class="pl-elabel ${tone}" x="${p.mx}" y="${p.my - 6}" text-anchor="middle">${esc(text)}</text>`) : ''
    return `<path id="e${i}" class="pl-edge ${e.kind} ${tone} ${e.dashed ? 'dashed' : ''}" d="${p.d}"/>${lab}`
  }).join('')
  const nodes = st.nodes.map((n) => {
    const vol = isAgent(n) && st.hasTelemetry ? `<text class="pl-vol ${n.silent ? 'silent' : ''}" x="${W / 2}" y="${H + 14}" text-anchor="middle">${esc(n.silent ? u.silent : n.volume !== undefined ? u.vol(n.volume, st.days ?? 0) : '')}</text>` : ''
    const focusable = isAgent(n) ? ` tabindex="0" role="button" aria-label="${esc(n.label)}"` : ''
    return `<g class="${cls(n)}" data-node="${esc(n.id)}" transform="translate(${n.x - W / 2},${n.y - H / 2})"${focusable}>${vol}<rect width="${W}" height="${H}" rx="${n.kind === 'client' ? H / 2 : 10}"/><text x="${W / 2}" y="21" text-anchor="middle">${esc(clip(short(n), n.kind === 'ghost' ? 30 : 22))}</text><text class="pl-sub" x="${W / 2}" y="37" text-anchor="middle">${esc(clip(n.sub[lang], 30))}</text></g>`
  }).join('')
  const s = scene?.steps[step]
  const spot = s ? at(s.node) : undefined
  return `<svg class="pl-svg ${lensOf ? 'lensing' : ''}" viewBox="0 0 ${st.width} ${st.height}" role="img" aria-label="${esc(u.title)}">
    <defs><radialGradient id="pl-spot" r="0.5"><stop offset="0" stop-color="#000"/><stop offset="0.6" stop-color="#000"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>
    <mask id="pl-mask"><rect width="${st.width}" height="${st.height}" fill="#fff"/>${spot ? `<ellipse cx="${spot.x}" cy="${spot.y}" rx="${W / 2 + 34}" ry="${H / 2 + 30}" fill="url(#pl-spot)"/>` : ''}</mask></defs>
    <g>${groups}</g><g>${edges}</g><g id="pl-parts"></g><g>${nodes}</g>
    <rect class="pl-dark" width="${st.width}" height="${st.height}" mask="url(#pl-mask)" opacity="${scene ? 0.72 : 0}"/>
  </svg>`
}

function panel() {
  const l = st.lenses.find((x) => x.id === lens)
  const lenses = `<section class="pl-box"><h2>${esc(u.lenses)}</h2><div class="pl-chips">${st.lenses.map((x) => `<button data-lens="${esc(x.id)}" aria-pressed="${x.id === lens}">${esc(clip(x.name[lang], 28))}</button>`).join('')}</div><p class="pl-cap">${l ? esc(l.caption[lang]) : `<span class="pl-note">${esc(u.lensHint)}</span>`}</p></section>`
  const scenes = st.scenes.length ? `<section class="pl-box"><h2>${esc(u.scenes)}</h2><div class="pl-scenes">${st.scenes.map((s) => `<button data-scene="${esc(s.id)}" aria-pressed="${s.id === scene?.id}">▶ ${esc(s.title[lang])}</button>`).join('')}</div></section>` : ''
  const a = st.actors.find((x) => x.id === actor)
  const card = a
    ? `<section class="pl-box pl-card" aria-live="polite"><h2>${esc(u.actor)}</h2><p class="pl-name">${esc(a.name)}</p><p class="pl-role">${esc(a.role === 'orchestrator' ? u.orchestrator : u.specialist)}${a.types.length ? ` · ${esc(a.types.join(' · '))}` : ''}${st.hasTelemetry ? ` · ${esc(a.silent ? u.silent : a.volume !== undefined ? u.vol(a.volume, st.days ?? 0) : '')}` : ''}</p>
      ${a.fingerprint.length ? `<p class="pl-note">${esc(u.fingerprint)}</p><div class="pl-dna">${a.fingerprint.map((f) => `<span class="${f.kind}" style="flex:${f.size}" title="${esc(f.label ?? '')}"></span>`).join('')}</div>` : ''}
      <ul class="pl-checks">${a.checks.map((c) => `<li class="${c.state}">${esc(c[lang])}</li>`).join('')}${a.access.map((x) => `<li class="decide">${esc(x[lang])}</li>`).join('')}</ul>
      ${data.playbill ? `<p class="pl-note" style="margin-top:8px"><a href="${esc(data.playbill)}#${encodeURIComponent(a.id)}">${esc(u.resume)}</a></p>` : ''}</section>`
    : `<section class="pl-box pl-card"><h2>${esc(u.actor)}</h2><p class="pl-note">${esc(u.actorHint)}</p></section>`
  const legend = `<section class="pl-box"><div class="pl-legend">${[['var(--beam)', u.legend[0]], ['var(--bad)', u.legend[1]], ['var(--amber)', u.legend[2]], ['var(--ghost)', u.legend[3]]].map(([c, t]) => `<span><i class="pl-dot" style="background:${c}"></i>${esc(t)}</span>`).join('')}</div><p class="pl-note" style="margin-top:8px">${esc(st.hasTelemetry ? u.structure : u.noTraffic)}</p></section>`
  return lenses + scenes + card + legend
}

function narration() {
  const s = scene?.steps[step]
  // below the stage, never over it; when no scene plays, it says how to start one
  if (!scene || !s) return `<div class="pl-narr idle"><span class="pl-note">${esc(u.narrIdle)}</span></div>`
  return `<div class="pl-narr ${s.warn ? 'warn' : ''}" role="status"><span class="pl-step">${esc(u.step(step + 1, scene.steps.length))}</span>${esc(s.text[lang])}${s.quote ? `<q class="pb-quote">${esc(s.quote)}</q>` : ''}<span class="pl-keys">${esc(u.keys)}</span></div>`
}

function render() {
  app.innerHTML = `<header class="pl-head">${data.map ? `<p><a href="${esc(data.map)}">${esc(u.map)}</a></p>` : ''}<h1>${esc(u.title)} · <span>${esc(st.name ?? data.id)}</span></h1><p>${esc(u.sub)}</p><p class="pl-private">${esc(u.privacy)}</p></header>
    <div class="pl-wrap"><div class="pl-stage">${svg()}${narration()}</div><aside class="pl-panel">${panel()}</aside></div>
    <p class="pl-foot">${esc(u.foot)}</p>`
  particles()
}

// the traffic: dots along each arrow, as many as the log of its volume; the structure gets one faint dot
let frame: number | undefined
function particles() {
  if (frame) cancelAnimationFrame(frame)
  const g = app.querySelector('#pl-parts')
  if (!g || !st.hasTelemetry) return
  const dots: { el: SVGCircleElement; path: SVGPathElement; len: number; phase: number; speed: number }[] = []
  st.edges.forEach((e, i) => {
    const p = app.querySelector<SVGPathElement>(`#e${i}`)
    if (!p || e.dashed) return
    const n = e.kind === 'traffic' ? (e.volume ? Math.max(1, Math.min(8, Math.round(Math.log10(e.volume + 1) * 2.2))) : 0) : 1
    const len = p.getTotalLength()
    for (let k = 0; k < n; k++) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
      el.setAttribute('r', e.kind === 'traffic' ? '3' : '2.2')
      el.setAttribute('class', `pl-part ${e.kind}`)
      g.appendChild(el)
      dots.push({ el, path: p, len, phase: k / n, speed: e.kind === 'traffic' ? 0.00011 : 0.00006 })
    }
  })
  const place = (t: number) => {
    for (const d of dots) {
      const pt = d.path.getPointAtLength((((d.phase + t * d.speed) % 1) + 1) % 1 * d.len)
      d.el.setAttribute('cx', pt.x.toFixed(1))
      d.el.setAttribute('cy', pt.y.toFixed(1))
    }
  }
  if (still) return place(0)
  const tick = (t: number) => {
    place(t)
    frame = requestAnimationFrame(tick)
  }
  frame = requestAnimationFrame(tick)
}

function stop() {
  if (playing) clearInterval(playing)
  playing = undefined
}
function go(k: number) {
  if (!scene) return
  step = Math.max(0, Math.min(scene.steps.length - 1, k))
  render()
}

app.addEventListener('click', (e) => {
  const t = e.target as Element
  const b = t.closest('button')
  const n = t.closest<SVGGElement>('[data-node]')
  // a lens and a scene are never on together: one turns the other off
  if (b?.dataset.lens) {
    lens = lens === b.dataset.lens ? undefined : b.dataset.lens
    if (lens) {
      stop()
      scene = undefined
    }
  } else if (b?.dataset.scene) {
    stop()
    scene = scene?.id === b.dataset.scene ? undefined : st.scenes.find((s) => s.id === b.dataset.scene)
    step = 0
    if (scene) lens = undefined
  } else if (n && st.actors.some((a) => a.id === n.dataset.node)) actor = n.dataset.node
  else return
  render()
})
app.addEventListener('keydown', (e) => {
  const n = (e.target as Element).closest?.('[data-node]') as SVGGElement | null
  if (n && (e.key === 'Enter' || e.key === ' ') && st.actors.some((a) => a.id === n.dataset.node)) {
    e.preventDefault()
    actor = n.dataset.node
    render()
    app.querySelector<SVGGElement>(`[data-node="${CSS.escape(actor!)}"]`)?.focus()
  }
})
document.addEventListener('keydown', (e) => {
  if (!scene) return
  if (e.key === 'ArrowRight') go(step + 1)
  else if (e.key === 'ArrowLeft') go(step - 1)
  else if (e.key === 'Escape') {
    stop()
    scene = undefined
    render()
  } else if (e.key === ' ' && !(e.target as Element).closest?.('[data-node]')) {
    e.preventDefault()
    stop()
    playing = window.setInterval(() => (scene && step < scene.steps.length - 1 ? go(step + 1) : stop()), 1800)
  } else return
})

render()
