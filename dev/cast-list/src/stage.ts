// The stage (the light plot), with no model: the cast as nodes and arrows in columns — the customer, the orchestrators,
// the specialists by type, the flows, the systems — with the traffic each one gets (its topic starts, from the export
// of Application Insights), the patterns as lenses that light who follows them and who is off, one scene per call of
// the orchestrator, and a card per actor. The same run gives the same stage; no volume is ever invented.
import type { Fired, Result } from './compare'
import type { AgentFacts } from './extract'
import { labelOf } from './labels'
import { requirement } from './playbill'
import { groupPatterns, type Look } from './review'

type Two = { en: string; pt: string }
export type NodeKind = 'client' | 'orchestrator' | 'specialist' | 'ghost' | 'flow' | 'system'
export interface StageNode { id: string; kind: NodeKind; label: string; sub: Two; x: number; y: number; volume?: number; silent?: boolean; unused?: boolean }
export interface StageEdge { from: string; to: string; kind: 'traffic' | 'structure'; label?: Two; tone?: 'bad' | 'amber' | 'ghost'; volume?: number; dashed?: boolean }
export interface Lens { id: string; name: Two; caption: Two; ok: string[]; amber: string[]; bad: string[] }
export interface Step { node: string; text: Two; warn?: boolean; /** Client text the step quotes, as written (a routing description). */ quote?: string }
export interface Scene { id: string; to: string; title: Two; steps: Step[] }
export interface Actor { id: string; name: string; role: 'orchestrator' | 'specialist'; types: string[]; volume?: number; silent?: boolean; fingerprint: { kind: 'shared' | 'official' | 'variant' | 'marker' | 'own'; size: number; label?: string }[]; checks: { key: string; en: string; pt: string; state: 'ok' | 'off' | 'decide' }[] }
export interface Stage { name?: string; width: number; height: number; hasTelemetry: boolean; days?: number; groups: { label: string; y1: number; y2: number }[]; nodes: StageNode[]; edges: StageEdge[]; lenses: Lens[]; scenes: Scene[]; actors: Actor[] }

const X = { client: 80, orchestrator: 290, specialist: 590, flow: 880, system: 1110 }
const ROW = 96
const TOP = 110
const GAP = 46
const both = (en: string, pt: string): Two => ({ en, pt })

export function stageOf(r: Result, looks: Look[], found: AgentFacts[], fired?: Fired): Stage {
  const name = (id: string) => r.agents.find((a) => a.id === id)?.displayName ?? id
  const typeName = (t: string) => r.typeNames[t] ?? t
  const silent = new Set(fired ? r.telemetry.silent : [])
  const starts = (id: string) => (fired && !silent.has(id) ? fired.rows.filter((x) => x.agent === id && x.event === 'TopicStart').reduce((n, x) => n + x.count, 0) : undefined)
  const nodes: StageNode[] = []
  const edges: StageEdge[] = []
  const groups: Stage['groups'] = []

  // the specialists, by type: one of two types sits in the first, with both under its name
  const specialists = r.agents.filter((a) => a.role === 'specialist')
  const typeIds = [...new Set(specialists.flatMap((a) => r.types[a.id] ?? []))]
  const placed = new Set<string>()
  let y = TOP
  for (const t of [...typeIds, '']) {
    const members = specialists.filter((a) => !placed.has(a.id) && (t ? (r.types[a.id] ?? [])[0] === t : !(r.types[a.id] ?? []).length))
    if (!members.length) continue
    const y1 = y - 34
    for (const a of members) {
      placed.add(a.id)
      const types = (r.types[a.id] ?? []).map(typeName)
      nodes.push({ id: a.id, kind: 'specialist', label: name(a.id), sub: types.length ? both(types.join(' · '), types.join(' · ')) : both('specialist', 'especialista'), x: X.specialist, y, ...vol(a.id) })
      y += ROW
    }
    if (t) groups.push({ label: typeName(t), y1, y2: y - ROW + 34 })
    y += GAP
  }
  const bottom = Math.max(y - GAP - ROW, TOP)
  const middle = Math.round((TOP + bottom) / 2)
  const orchestrators = r.agents.filter((a) => a.role === 'orchestrator')
  orchestrators.forEach((a, i) => nodes.push({ id: a.id, kind: 'orchestrator', label: name(a.id), sub: both('routes and hands over', 'classifica e encaminha'), x: X.orchestrator, y: middle + (i - (orchestrators.length - 1) / 2) * ROW, ...vol(a.id) }))
  nodes.unshift({ id: 'client', kind: 'client', label: '', sub: both('who is served', 'quem é atendido'), x: X.client, y: middle })
  function vol(id: string) {
    const v = starts(id)
    return silent.has(id) ? { silent: true } : v !== undefined ? { volume: v } : {}
  }
  const at = (id: string) => nodes.find((n) => n.id === id)
  // the customer reaches each orchestrator
  for (const o of orchestrators) edges.push({ from: 'client', to: o.id, kind: 'traffic', ...(at(o.id)?.volume !== undefined ? { volume: at(o.id)!.volume } : {}), ...(silent.has(o.id) ? { dashed: true } : {}) })

  // the calls: what is missing, a short routing description, one not in the folder
  const offOf = (id: string) => r.offPattern.filter((o) => o.agent === id && o.key.startsWith('called-with:'))
  const lacks = (id: string, lang: 'en' | 'pt') => offOf(id).map((o) => (o.key === 'called-with:history' ? (lang === 'pt' ? 'SEM histórico' : 'NO history') : `${lang === 'pt' ? 'SEM' : 'NO'} «${o.key.slice('called-with:input:'.length)}»`)).join(' · ')
  const ghostY = bottom + ROW
  let ghosts = 0
  for (const c of r.contract.routes) {
    if (!c.agent) {
      if (!at(c.calls)) nodes.push({ id: c.calls, kind: 'ghost', label: c.name ?? c.calls, sub: both('called, not in the folder', 'chamado, fora da pasta'), x: X.orchestrator + 40, y: ghostY + ghosts++ * ROW })
      edges.push({ from: c.caller, to: c.calls, kind: 'traffic', tone: 'ghost', dashed: true, label: both('calls it, but it is not in the folder', 'chama, mas não está na pasta') })
      continue
    }
    const short = r.contract.short.some((s) => s.agent === c.agent && s.caller === c.caller)
    const missing = offOf(c.agent).length
    const target = at(c.agent)
    edges.push({
      from: c.caller, to: c.agent, kind: 'traffic',
      ...(target?.volume !== undefined ? { volume: target.volume } : {}),
      ...(silent.has(c.agent) ? { dashed: true } : {}),
      ...(missing ? { tone: 'bad' as const, label: both(lacks(c.agent, 'en'), lacks(c.agent, 'pt')) } : short ? { tone: 'amber' as const, label: both(`routed by «${c.description}»`, `roteado por «${c.description}»`) } : {}),
    })
  }

  // the flows (one node per flow, however many share it) and the systems each one and each specialist reaches
  const flowId = (f: Result['flows'][number]) => `flow:${f.id ?? f.name}`
  const sysOf = (use: string): { id: string; label: string; sub: Two } | undefined => {
    if (use.startsWith('http:')) return { id: `sys:${use}`, label: use.slice(5), sub: both('HTTP', 'HTTP') }
    if (use.startsWith('connector:')) return { id: `sys:${use}`, label: r.names[use.slice(10)] ?? use.slice(10), sub: both('connector', 'conector') }
    if (use.startsWith('mcp:')) return { id: `sys:${use}`, label: r.names[use.slice(4)] ?? use.slice(4), sub: both('MCP server', 'servidor MCP') }
    return undefined
  }
  const flowNodes = new Map<string, StageNode>()
  const sysNodes = new Map<string, StageNode & { reach: { from: number; live: boolean }[] }>()
  const reach = (use: string, fromY: number, live: boolean) => {
    const s = sysOf(use)
    if (!s) return undefined
    const n = sysNodes.get(s.id) ?? { ...s, kind: 'system' as const, x: X.system, y: 0, reach: [] }
    n.reach.push({ from: fromY, live })
    sysNodes.set(s.id, n)
    return s.id
  }
  for (const f of r.flows) {
    const from = at(f.agent)
    if (!from) continue
    const id = flowId(f)
    const n = flowNodes.get(id) ?? { id, kind: 'flow' as const, label: f.name, sub: both('flow', 'fluxo'), x: X.flow, y: 0, unused: true }
    if (f.called) n.unused = false
    flowNodes.set(id, n)
    edges.push({ from: f.agent, to: id, kind: 'structure', ...(f.called ? (f.returns ? {} : { tone: 'amber' as const, label: both('returns nothing', 'não devolve nada') }) : { tone: 'ghost' as const, dashed: true, label: both('nobody calls it', 'ninguém chama') }) })
  }
  for (const f of r.flows) {
    const n = flowNodes.get(flowId(f))!
    for (const use of f.uses) {
      const to = reach(use, at(f.agent)!.y, f.called)
      if (to && !edges.some((e) => e.from === n.id && e.to === to)) edges.push({ from: n.id, to, kind: 'structure', ...(use.startsWith('http:') ? { label: both('HTTP', 'HTTP') } : {}), ...(f.called ? {} : { tone: 'ghost' as const, dashed: true }) })
    }
  }
  for (const a of specialists) {
    const keys = Object.keys(a.facts)
    for (const k of keys.filter((x) => x.startsWith('connector:') || x.startsWith('mcp:'))) {
      const to = reach(k, at(a.id)!.y, true)
      const ops = keys.filter((x) => x.startsWith(`operation:${k.slice(10)}/`)).map((x) => x.slice(x.indexOf('/') + 1))
      if (to) edges.push({ from: a.id, to, kind: 'structure', ...(ops.length ? { label: both(ops.join(', '), ops.join(', ')) } : {}) })
    }
  }
  // a flow sits beside who uses it; a system beside what reaches it; never closer than a row apart
  const settle = (list: StageNode[], ys: (n: StageNode) => number) => {
    const sorted = list.map((n) => ({ n, want: ys(n) })).sort((a, b) => a.want - b.want || a.n.label.localeCompare(b.n.label))
    let last = -Infinity
    for (const s of sorted) {
      s.n.y = Math.round(Math.max(s.want, last + ROW * 0.82))
      last = s.n.y
    }
  }
  const flowsList = [...flowNodes.values()]
  settle(flowsList, (n) => avg(edges.filter((e) => e.to === n.id).map((e) => at(e.from)!.y)))
  nodes.push(...flowsList)
  const sysList = [...sysNodes.values()]
  for (const s of sysList) s.unused = !s.reach.some((x) => x.live)
  settle(sysList, (s) => avg(edges.filter((e) => e.to === s.id).map((e) => nodes.find((n) => n.id === e.from)?.y ?? middle)))
  nodes.push(...sysList.map(({ reach: _, ...s }) => s))

  // the lenses: the accepted patterns and the first ones someone is off, then the contract, the telemetry, the unused
  const ids = r.agents.map((a) => a.id)
  const inScope = (scope: string) => (scope === 'platform' ? ids : scope.startsWith('type:') ? specialists.filter((a) => (r.types[a.id] ?? []).includes(scope.slice(5))).map((a) => a.id) : r.agents.filter((a) => a.role === scope).map((a) => a.id))
  const scopeWord = (scope: string): Two => (scope === 'platform' ? both('platform', 'de plataforma') : scope.startsWith('type:') ? both(`of the type «${typeName(scope.slice(5))}»`, `do tipo «${typeName(scope.slice(5))}»`) : scope === 'orchestrator' ? both('of the orchestrators', 'dos orquestradores') : both('of the specialists', 'dos especialistas'))
  const { look: withSomeoneOff } = groupPatterns(r)
  const picked = [...r.patterns.filter((p) => p.decision?.status === 'accepted'), ...withSomeoneOff].filter((p, i, all) => !p.partOf && all.findIndex((q) => q.key === p.key && q.scope === p.scope) === i).slice(0, 8)
  const lenses: Lens[] = picked.map((p) => {
    const scope = inScope(p.scope)
    const off = r.offPattern.filter((o) => o.key === p.key && o.scope === p.scope)
    const bad = off.filter((o) => !o.variant).map((o) => o.agent)
    const amber = off.filter((o) => o.variant).map((o) => o.agent)
    const okIds = scope.filter((id) => !bad.includes(id) && !amber.includes(id))
    const names = (xs: string[]) => xs.map(name).join(', ')
    const w = scopeWord(p.scope)
    const tail = (lang: 'en' | 'pt') => [bad.length ? (lang === 'pt' ? `Fora: ${names(bad)}.` : `Off: ${names(bad)}.`) : '', amber.length ? (lang === 'pt' ? `Variação: ${names(amber)}.` : `A variation: ${names(amber)}.`) : ''].filter(Boolean).join(' ')
    return {
      id: `pattern:${p.key}`,
      name: both(labelOf(p.key, 'en', r.names), labelOf(p.key, 'pt', r.names)),
      caption: both(`«${labelOf(p.key, 'en', r.names)}» — a pattern ${w.en} (${okIds.length} of ${scope.length}). ${tail('en')}`.trim(), `«${labelOf(p.key, 'pt', r.names)}» — padrão ${w.pt} (${okIds.length} de ${scope.length}). ${tail('pt')}`.trim()),
      ok: okIds, amber, bad,
    }
  })
  const lensOf = (id: string, name: Two, caption: Two, bad: string[], amber: string[], scope: string[]): Lens => {
    const b = [...new Set(bad)]
    const a = [...new Set(amber)].filter((x) => !b.includes(x))
    return { id, name, caption, bad: b, amber: a, ok: scope.filter((x) => !b.includes(x) && !a.includes(x)) }
  }
  const called = r.contract.routes.flatMap((c) => (c.agent ? [c.agent] : []))
  const flowLooks = looks.filter((l) => l.key === 'flow' || (l.key === 'contract' && l.fact === 'routing:described'))
  lenses.push(lensOf('contract', both('Contract', 'Contrato'), both('What the orchestrator passes, and how it routes: red is what is missing; amber, a short routing description or a flow that returns nothing.', 'O que o orquestrador passa, e como encaminha: em vermelho o que falta; em âmbar, uma descrição de roteamento curta ou um fluxo que não devolve nada.'),
    specialists.filter((a) => offOf(a.id).length).map((a) => a.id), flowLooks.flatMap((l) => l.agents), called))
  const telemetryLooks = looks.filter((l) => l.key === 'spelling' || l.key === 'telemetry' || l.fact?.startsWith('telemetry:') || l.fact === 'node:LogCustomTelemetryEvent')
  const telBad = [...silent, ...r.offPattern.filter((o) => o.key === 'node:LogCustomTelemetryEvent').map((o) => o.agent)]
  lenses.push(lensOf('telemetry', both('Telemetry', 'Telemetria'), both('Who logs, and what fires: red logs nothing or has no line; amber spells an event another way, misses a field, or has an event that did not fire.', 'Quem registra, e o que dispara: em vermelho quem não registra ou não tem linha; em âmbar um evento escrito de outro jeito, um campo que falta ou um evento que não disparou.'),
    telBad, telemetryLooks.flatMap((l) => l.agents), ids))
  lenses.push(lensOf('unused', both('Unused', 'Sem uso'), both('What nobody uses, or is switched off: remove it or switch it on?', 'O que ninguém usa, ou está desligado: remover ou ligar?'), [], r.unused.map((u) => u.agent), ids))

  // one scene per call of the orchestrator, in the order of its files
  const scenes: Scene[] = r.contract.routes.map((c, i) => {
    const to = c.agent ?? c.calls
    const who = c.agent ? name(c.agent) : (c.name ?? c.calls)
    const steps: Step[] = [{ node: 'client', text: both('The customer writes.', 'O cliente escreve.') }]
    const short = c.agent && r.contract.short.some((s) => s.agent === c.agent && s.caller === c.caller)
    steps.push(short
      ? { node: c.caller, warn: true, quote: c.description, text: both(`The orchestrator hands over to ${who} by a routing description of ${c.description.length} characters.`, `O orquestrador encaminha para ${who} por uma descrição de roteamento de ${c.description.length} caracteres.`) }
      : { node: c.caller, quote: c.description, text: both(`The orchestrator hands over to ${who}.`, `O orquestrador encaminha para ${who}.`) })
    if (!c.agent) {
      steps.push({ node: to, warn: true, text: both(`It calls ${who}, which is not in the folder: not cloned, or gone?`, `Chama ${who}, que não está na pasta: não foi clonado, ou não existe mais?`) })
      return { id: `scene-${i + 1}`, to, title: both(who, who), steps }
    }
    const miss = offOf(c.agent)
    if (miss.length) {
      const what = (l: 'en' | 'pt') => miss.map((o) => (o.key === 'called-with:history' ? (l === 'pt' ? 'o histórico' : 'the history') : `«${o.key.slice('called-with:input:'.length)}»`)).join(l === 'pt' ? ' e SEM ' : ' and WITHOUT ')
      steps.push({ node: c.agent, warn: true, text: both(`${who} is called WITHOUT ${what('en')}: it does not know what the customer already said.`, `${who} é chamado SEM ${what('pt')}: não sabe o que o cliente já disse.`) })
    } else {
      const gets = (l: 'en' | 'pt') => [c.history ? (l === 'pt' ? 'o histórico' : 'the history') : '', ...c.inputs.map((x) => `«${x}»`)].filter(Boolean).join(l === 'pt' ? ' e ' : ' and ') || (l === 'pt' ? 'a chamada' : 'the call')
      steps.push({ node: c.agent, text: both(`${who} gets ${gets('en')}.`, `${who} recebe ${gets('pt')}.`) })
    }
    for (const f of r.flows.filter((x) => x.agent === c.agent && x.called)) {
      steps.push(f.returns
        ? { node: flowId(f), text: both(`It uses the flow «${f.name}».`, `Usa o fluxo «${f.name}».`) }
        : { node: flowId(f), warn: true, text: both(`The flow «${f.name}» returns nothing to ${who}.`, `O fluxo «${f.name}» não devolve nada para ${who}.`) })
      for (const use of f.uses) {
        const s = sysOf(use)
        if (s) steps.push({ node: s.id, text: both(`The flow reaches ${s.label}.`, `O fluxo chega a ${s.label}.`) })
      }
    }
    for (const e of edges.filter((x) => x.from === c.agent && x.to.startsWith('sys:'))) {
      const s = nodes.find((n) => n.id === e.to)!
      steps.push({ node: s.id, text: both(`It uses ${s.label}${e.label ? ` (${e.label.en})` : ''}.`, `Usa ${s.label}${e.label ? ` (${e.label.pt})` : ''}.`) })
    }
    steps.push({ node: c.caller, text: both('The answer goes back to the customer through the orchestrator.', 'A resposta volta ao cliente pelo orquestrador.') })
    return { id: `scene-${i + 1}`, to, title: both(who, who), steps }
  })

  // the card of each actor: its fingerprint and the post of its role and type
  const actors: Actor[] = r.agents.map((a) => {
    const f = found.find((x) => x.id === a.id)
    const total = f?.texts.filter((t) => t.source === 'instructions').reduce((n, t) => n + t.text.length, 0) ?? 0
    const fp: Actor['fingerprint'] = []
    for (const b of r.blocks) {
      if (b.holders[a.id]) fp.push({ kind: b.official ? 'official' : 'shared', size: b.text.length, label: b.official ?? b.label })
      else if (b.variants[a.id]) fp.push({ kind: 'variant', size: b.variants[a.id].text.length, label: b.official ?? b.label })
    }
    const shared = fp.reduce((n, x) => n + x.size, 0)
    for (const k of Object.keys(a.facts).filter((x) => x.startsWith('text:') && !x.startsWith('text:block:') && !x.endsWith('~variant'))) fp.push({ kind: 'marker', size: 12, label: labelOf(k, 'pt', r.names) })
    if (total > shared) fp.push({ kind: 'own', size: total - shared })
    const scopes = ['platform', a.role, ...(r.types[a.id] ?? []).map((t) => `type:${t}`)]
    const offKeys = new Set(r.offPattern.map((o) => o.key))
    const post = r.patterns.filter((p) => !p.partOf && scopes.includes(p.scope) && (p.decision?.status === 'accepted' || offKeys.has(p.key)))
    const checks = post.filter((p, i, all) => all.findIndex((q) => q.key === p.key) === i).map((p) => {
      const o = r.offPattern.find((x) => x.agent === a.id && x.key === p.key)
      return { key: p.key, en: requirement(p.key, 'en', r.names), pt: requirement(p.key, 'pt', r.names), state: !o ? ('ok' as const) : o.variant ? ('decide' as const) : ('off' as const) }
    })
    return { id: a.id, name: name(a.id), role: a.role === 'orchestrator' ? 'orchestrator' : 'specialist', types: (r.types[a.id] ?? []).map(typeName), ...vol(a.id), fingerprint: fp, checks }
  })

  const height = Math.max(...nodes.map((n) => n.y)) + 90
  return { ...(r.name ? { name: r.name } : {}), width: 1220, height, hasTelemetry: !!fired, ...(fired ? { days: fired.days } : {}), groups, nodes, edges, lenses, scenes, actors }
}

const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0)
