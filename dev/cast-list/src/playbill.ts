// The RH of the cast, with no model: the same cast as people — the staff board, the org chart, the post of each role
// and type, a résumé for each one, and its development plan. Everything comes from the files, the telemetry and the
// tables people gave; a field nothing says is left empty, never guessed.
import type { Cast } from './cast'
import type { Fired, Result } from './compare'
import type { AgentFacts } from './extract'
import { labelOf, type Lang } from './labels'
import { pdiOf, type PdiItem } from './pdi'
import type { Rule } from './profile'
import type { Look } from './review'

export type Situation = 'hiring' | 'noOwner' | 'neverPublished' | 'pdi' | 'ok'
export interface Person { id: string; name: string; situation: Situation[] }
export interface Requirement { key: string; en: string; pt: string; proposal: boolean }
export interface Post { scope: string; name: { en: string; pt: string }; requirements: Requirement[] }
export interface Resume {
  id: string
  name: string
  role: 'orchestrator' | 'specialist'
  types: string[]
  /** The first sentence of its instructions, as written. */
  title?: string
  manager?: string
  team?: Said
  owner?: Said
  created?: Said
  published?: Said
  schemaName?: string
  environment?: Said
  /** The first list of its instructions, as written (at most 5). */
  summary: string[]
  tools: { en: string; pt: string }[]
  conduct: { en: string; pt: string }[]
  goal?: Said
  /** From the telemetry: topic starts and errors logged; none when there was no export. */
  performance?: { days: number; starts: number; errors: number; notFired: string[]; silent: boolean }
  pdi: PdiItem[]
  sources: string[]
  seal: 'ok' | 'pdi'
}
export interface Said { value: string; source: string }
export interface Playbill {
  name?: string
  /** Each situation with who is in it: only those the tables given can tell. */
  staff: { key: 'cast' | Situation; people: { id: string; name: string }[] }[]
  /** The tables that would tell more. */
  missing: ('inventory' | 'team' | 'telemetry')[]
  org: { orchestrators: Person[]; types: { id: string; name: string; people: Person[] }[]; ghosts: { id: string; name: string; caller: string }[] }
  posts: Post[]
  resumes: Resume[]
}

// the requirement a fact makes, in the words of a job post; any other fact: «Has «…»»
const REQUIRE: Record<string, { en: string; pt: string }> = {
  'trigger:OnEscalate': { en: 'Hands over to a person (escalation)', pt: 'Sabe encaminhar para uma pessoa (escalonamento)' },
  'called-with:history': { en: 'Gets the conversation history from the orchestrator', pt: 'Recebe do gestor o histórico da conversa' },
  'node:LogCustomTelemetryEvent': { en: 'Logs its own errors (telemetry)', pt: 'Registra os próprios erros (telemetria)' },
  'declared:kpi': { en: 'Has a goal (KPI)', pt: 'Tem uma meta (KPI)' },
  'declared:owner': { en: 'Has an owner', pt: 'Tem um responsável' },
  'declared:team': { en: 'Has a team', pt: 'Tem uma equipe' },
}
export const requirement = (key: string, lang: Lang, names: Record<string, string> = {}) => REQUIRE[key]?.[lang] ?? (lang === 'pt' ? `Tem «${labelOf(key, lang, names)}»` : `Has «${labelOf(key, lang, names)}»`)
export const REQUIREMENTS = REQUIRE

const INVENTORY = ['owner', 'environment', 'created-on', 'last-published']
const sentence = (s: string) => /^\s*([^\n]*?[.!?])(\s|$)/.exec(s)?.[1].trim() ?? s.split('\n')[0].trim()
const firstList = (s: string) => {
  const lines = s.split('\n')
  const at = lines.findIndex((l) => /^\s*([-*•]|\d+[.)])\s+/.test(l))
  if (at < 0) return []
  const out: string[] = []
  for (const l of lines.slice(at)) {
    const m = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/.exec(l)
    if (!m) break
    out.push(m[1].trim())
  }
  return out.slice(0, 5)
}

/** The RH of a run: its result, what to look at, the facts found, the cast file, the profile's rules and the telemetry. */
export function playbillOf(r: Result, looks: Look[], found: AgentFacts[], cast: Cast, rules: Rule[], fired?: Fired): Playbill {
  const name = (id: string) => r.agents.find((a) => a.id === id)?.displayName ?? id
  const said = (agent: string, key: string): Said | undefined => {
    const d = cast.declared.find((x) => x.agent === agent && x.key === key)
    return d && { value: d.value, source: d.source }
  }
  const inventory = cast.declared.some((d) => INVENTORY.includes(d.key))
  const team = cast.declared.some((d) => d.key === 'team' || d.key === 'kpi')
  const pdi = pdiOf(looks, r)
  const ghosts = r.contract.missing.map((m) => ({ id: m.calls, name: m.name ?? m.calls, caller: m.caller }))
  // the environment most of them are in: one in another is still being hired
  const envs = r.agents.map((a) => said(a.id, 'environment')?.value).filter((v): v is string => !!v)
  const usual = [...new Set(envs)].sort((a, b) => envs.filter((e) => e === b).length - envs.filter((e) => e === a).length)[0]
  const situation = (id: string): Situation[] => {
    const s: Situation[] = []
    const env = said(id, 'environment')?.value
    if (env && usual && env !== usual) s.push('hiring')
    if (inventory && !said(id, 'owner')) s.push('noOwner')
    if (inventory && said(id, 'created-on') && !said(id, 'last-published')) s.push('neverPublished')
    s.push(pdi.some((p) => p.agent === id && p.group !== 'cleanup') ? 'pdi' : 'ok')
    return s
  }
  const person = (id: string): Person => ({ id, name: name(id), situation: situation(id) })
  const people = r.agents.map((a) => a.id)
  const who = (ids: string[]) => ids.map((id) => ({ id, name: name(id) }))
  const ghostsNamed = ghosts.map((g) => ({ id: g.id, name: g.name }))
  const staff: Playbill['staff'] = [
    { key: 'cast', people: who(people) },
    { key: 'hiring', people: [...ghostsNamed, ...who(people.filter((id) => situation(id).includes('hiring')))] },
    ...(inventory ? [{ key: 'noOwner' as const, people: who(people.filter((id) => situation(id).includes('noOwner'))) }, { key: 'neverPublished' as const, people: who(people.filter((id) => situation(id).includes('neverPublished'))) }] : []),
    { key: 'pdi', people: who(people.filter((id) => situation(id).includes('pdi'))) },
    { key: 'ok', people: who(people.filter((id) => situation(id).includes('ok'))) },
  ]

  const orchestrators = r.agents.filter((a) => a.role === 'orchestrator').map((a) => person(a.id))
  const specialists = r.agents.filter((a) => a.role === 'specialist')
  const typeIds = [...new Set(specialists.flatMap((a) => r.types[a.id] ?? []))]
  const types = [
    ...typeIds.map((t) => ({ id: t, name: r.typeNames[t] ?? t, people: specialists.filter((a) => (r.types[a.id] ?? []).includes(t)).map((a) => person(a.id)) })),
    ...(specialists.some((a) => !(r.types[a.id] ?? []).length) ? [{ id: '', name: '', people: specialists.filter((a) => !(r.types[a.id] ?? []).length).map((a) => person(a.id)) }] : []),
  ]

  // the posts: the accepted patterns of a scope and the profile's rules of its role; with no decision yet, what someone
  // is off, as a proposal
  const req = (key: string, proposal: boolean): Requirement => ({ key, en: requirement(key, 'en', r.names), pt: requirement(key, 'pt', r.names), proposal })
  const postOf = (scope: string, nameOf: { en: string; pt: string }, role: 'specialist' | 'orchestrator'): Post => {
    const inScope = r.patterns.filter((p) => !p.partOf && (p.scope === scope || (scope !== 'platform' && p.scope === 'platform')))
    const accepted = inScope.filter((p) => p.decision?.status === 'accepted')
    const off = new Set(r.offPattern.map((o) => o.key))
    const picked = accepted.length ? accepted.map((p) => req(p.key, false)) : inScope.filter((p) => off.has(p.key)).map((p) => req(p.key, true))
    const fromRules = rules.filter((x) => x.has && (!x.role || x.role === role) && !picked.some((p) => p.key === x.has)).map((x) => req(x.has!, false))
    return { scope, name: nameOf, requirements: [...picked, ...fromRules] }
  }
  const posts = [
    postOf('specialist', { en: 'Specialist', pt: 'Especialista' }, 'specialist'),
    ...typeIds.map((t) => postOf(`type:${t}`, { en: `Specialist · ${r.typeNames[t] ?? t}`, pt: `Especialista · ${r.typeNames[t] ?? t}` }, 'specialist')),
    ...(orchestrators.length ? [postOf('orchestrator', { en: 'Orchestrator', pt: 'Orquestrador' }, 'orchestrator')] : []),
  ]

  const resumes = r.agents.map((a): Resume => {
    const f = found.find((x) => x.id === a.id)
    const instructions = f?.texts.find((t) => t.source === 'instructions')?.text ?? ''
    const keys = Object.keys(a.facts)
    const both = (k: string) => ({ en: labelOf(k, 'en', r.names), pt: labelOf(k, 'pt', r.names) })
    const tools = keys.filter((k) => /^(operation|mcp|flow-uses|knowledge):/.test(k) && !k.startsWith('knowledge:count')).map(both)
    const conduct = keys.filter((k) => k.startsWith('text:') && !k.endsWith('~variant')).map(both)
    const caller = r.contract.routes.find((x) => x.agent === a.id)?.caller
    const events = r.telemetry.events.filter((e) => e.agent === a.id)
    const performance = fired && {
      days: fired.days,
      starts: fired.rows.filter((x) => x.agent === a.id && x.event === 'TopicStart').reduce((n, x) => n + x.count, 0),
      errors: events.reduce((n, e) => n + (e.fired ?? 0), 0),
      notFired: r.telemetry.notFired.filter((e) => e.agent === a.id).map((e) => e.name),
      silent: r.telemetry.silent.includes(a.id),
    }
    const sources = [...new Set(['YAML', ...(fired ? [fired.file] : []), ...cast.declared.filter((d) => d.agent === a.id).map((d) => d.source.split(' › ')[0])])]
    const mine = pdi.filter((p) => p.agent === a.id)
    return {
      id: a.id,
      name: name(a.id),
      role: a.role === 'orchestrator' ? 'orchestrator' : 'specialist',
      types: (r.types[a.id] ?? []).map((t) => r.typeNames[t] ?? t),
      ...(instructions ? { title: sentence(instructions) } : {}),
      ...(caller ? { manager: name(caller) } : {}),
      ...(said(a.id, 'team') ? { team: said(a.id, 'team') } : {}),
      ...(said(a.id, 'owner') ? { owner: said(a.id, 'owner') } : {}),
      ...(said(a.id, 'created-on') ? { created: said(a.id, 'created-on') } : {}),
      ...(said(a.id, 'last-published') ? { published: said(a.id, 'last-published') } : {}),
      ...(a.schemaName ? { schemaName: a.schemaName } : {}),
      ...(said(a.id, 'environment') ? { environment: said(a.id, 'environment') } : {}),
      summary: firstList(instructions),
      tools,
      conduct,
      ...(said(a.id, 'kpi') ? { goal: said(a.id, 'kpi') } : {}),
      ...(performance ? { performance } : {}),
      pdi: mine,
      sources,
      seal: mine.some((p) => p.group !== 'cleanup') ? 'pdi' : 'ok',
    }
  })
  const missing = [...(inventory ? [] : ['inventory' as const]), ...(team ? [] : ['team' as const]), ...(fired ? [] : ['telemetry' as const])]
  return { ...(r.name ? { name: r.name } : {}), staff, missing, org: { orchestrators, types, ghosts }, posts, resumes }
}
