// Compares the agents: what most agents of a role have (a pattern, and whether the orchestrator has it too — then it is
// the platform's), who is off a pattern, what only one specialist has (innovation or debt: someone has to say), what
// only the orchestrator does, the profile's rules not met, and what people said that the YAML contradicts. A decision
// in the cast file marks a pattern; an accepted one is checked even when it would no longer be a pattern by its share.
// A part of a fact (a topic that leads to escalation is part of escalating) is never a pattern of its own: it is
// checked only on the agents that have the fact, takes the fact's decision, and is never a solo.
//
// What an orchestrator passes each agent it calls becomes the called agent's facts (called-with:, routing:), so it is
// compared like any other; the calls to an agent not in the folder, the specialists no orchestrator calls and the short
// routing descriptions are told apart. What nothing uses and what is switched off (orphan:, disabled:) is never a
// pattern nor a solo: it is listed on its own, to remove or to switch on.
import type { Cast, Decision, Scope } from './cast'
import { blocksOf, type BlockFamily } from './blocks'
import type { AgentFacts, Call, Facts, Flow, Source, Unknown } from './extract'
import { partOf, SHORT_ROUTING } from './labels'
import { markerFindings, markersOf, type MarkerFinding } from './markers'
import { MS_PATTERNS } from './microsoft'
import { matches, rolesOf, typesOf, type Profile, type Role, type Rule } from './profile'

export type { Scope }
export interface Pattern {
  key: string
  /** The role where it is a pattern (or, for a decision, the one its scope names first). */
  role: Role
  scope: Scope
  /** The share of the role's agents that have it. */
  share: number
  /** Who has it. */
  agents: string[]
  sources: Source[]
  decision?: Decision
  /** The fact this is a part of (`trigger:OnEscalate` for `reaches:OnEscalate`). */
  partOf?: string
  /** The official block's name, when the pattern is the profile's block. */
  official?: string
}
export interface OffPattern { agent: string; key: string; scope: Scope; partOf?: string; /** It has a variation of the block. */ variant?: boolean }
export interface Holding { key: string; agents: string[]; sources: Source[] }
export interface Gap { rule: Rule; agents: string[] }
export interface Conflict { agent: string; key: string; declared: string; observed: boolean; source: string }
/** A call of an orchestrator, with the agent of the folder it reaches (none when it is not in the folder). */
export interface Route extends Call { caller: string; agent?: string }
export interface Unused { agent: string; key: string; how: 'orphan' | 'disabled'; what: string; name: string; sources: Source[] }
export interface Result {
  name?: string
  roles: Record<string, Role>
  /** Agents the profile names that are not in the folder. */
  unmatched: string[]
  /** Each agent with what it has: what was seen (less what the profile ignores) and what people declared. */
  agents: { id: string; role: Role; schemaName?: string; displayName?: string; facts: Facts; children: AgentFacts['children'] }[]
  patterns: Pattern[]
  offPattern: OffPattern[]
  solos: Holding[]
  orchestratorDoes: Holding[]
  gaps: Gap[]
  conflicts: Conflict[]
  unknown: (Unknown & { agent: string })[]
  /** Readable names: a connector's API name or an agent's schema name → the name people know it by. */
  names: Record<string, string>
  /** Each specialist's types (none for an orchestrator), and the types' names. */
  types: Record<string, string[]>
  typeNames: Record<string, string>
  /** Types with too few agents to compare in: nothing is a pattern of them. */
  typeNotes: { type: string; agents: string[] }[]
  /** The blocks of text agents share, with who has each and each variation. */
  blocks: BlockFamily[]
  markerFindings: MarkerFinding[]
  /** The orchestrators' calls: every one, those to an agent not in the folder, the specialists nobody calls, the short
   * routing descriptions. */
  contract: { routes: Route[]; missing: Route[]; uncalled: string[]; short: Route[] }
  /** Every flow of every agent, called or not. */
  flows: (Flow & { agent: string })[]
  unused: Unused[]
}


const NO = /^(no|não|nao|false|off|0)$/i
// a Microsoft pattern with no mark in the YAML can only be declared
const DECLARED_ONLY = new Set(MS_PATTERNS.filter((p) => !p.sign).map((p) => `ms:${p.id}`))
/** A declared key that is a claim about the YAML («trigger:OnEscalate»), not a fact only people know («kpi»). */
const isClaim = (key: string) => key.includes(':') && !key.startsWith('declared:') && !DECLARED_ONLY.has(key)
const declaredKey = (key: string) => (key.startsWith('declared:') ? key : `declared:${key}`)
// a variation of a block says something about the block, not a fact of its own
const isVariant = (key: string) => key.endsWith('~variant')
/** What nothing uses or what is switched off: listed, never compared. */
export const isUnused = (key: string) => /^(orphan|disabled):/.test(key)

export function compare(found: AgentFacts[], profile: Profile, cast: Cast): Result {
  const given = Object.fromEntries(cast.agents.map((a) => [a.id, a.role]))
  const { roles, unmatched } = rolesOf(found, profile, given)
  const ignored = (k: string) => profile.ignore.includes(k) || (!profile.microsoftPatterns && k.startsWith('ms:'))
  const conflicts: Conflict[] = []
  // what the texts say is seen too: the blocks agents share and the profile's markers
  const blocks = blocksOf(found, cast.blocks, profile.blocks)
  const marked = markersOf(found, profile.markers)
  // the contract: what each call passes is a fact of the agent called, seen in the caller's file
  const bySchema = new Map(found.filter((a) => a.schemaName).map((a) => [a.schemaName!, a.id]))
  const routes: Route[] = found.flatMap((a) => (a.contract ?? []).map((c) => ({ ...c, caller: a.id, ...(bySchema.has(c.calls) ? { agent: bySchema.get(c.calls) } : {}) })))
  const called: Record<string, Facts> = {}
  for (const r of routes.filter((x) => x.agent)) {
    const into = (called[r.agent!] ??= {})
    const at = { file: `${r.caller}/${r.file}`, line: r.line }
    const add = (key: string) => (into[key] ??= []).push(at)
    if (r.history) add('called-with:history')
    for (const i of r.inputs) add(`called-with:input:${i}`)
    if (r.description) add('routing:described')
  }
  const seen = (a: AgentFacts): Facts => ({ ...a.facts, ...blocks.facts[a.id], ...marked.facts[a.id], ...called[a.id] })
  const agents = found.map((a) => {
    const observed = seen(a)
    const facts: Facts = Object.fromEntries(Object.entries(observed).filter(([k]) => !ignored(k)))
    for (const d of cast.declared.filter((x) => x.agent === a.id)) {
      const says = !NO.test(d.value)
      if (isClaim(d.key)) {
        // what was seen wins: a claim never changes a fact, it only shows where people and the YAML disagree
        const has = d.key in observed
        if (says !== has) conflicts.push({ agent: a.id, key: d.key, declared: d.value || 'yes', observed: has, source: d.source })
      } else if (says) (facts[declaredKey(d.key)] ??= []).push({ file: d.source ? `declared: ${d.source}` : 'declared' })
    }
    return { id: a.id, role: roles[a.id], ...(a.schemaName ? { schemaName: a.schemaName } : {}), ...(a.displayName ? { displayName: a.displayName } : {}), facts, children: a.children }
  })

  const members = (role: Role) => agents.filter((a) => a.role === role)
  const holders = (key: string, of = agents) => of.filter((a) => key in a.facts)
  const sourcesOf = (key: string, of = agents) => of.flatMap((a) => a.facts[key] ?? [])
  const allKeys = [...new Set(agents.flatMap((a) => Object.keys(a.facts)))].sort()
  const decisionOf = (key: string) => cast.decisions.find((d) => d.key === key)
  const types = typesOf(agents, roles, profile, Object.fromEntries(cast.agents.filter((a) => a.types?.length).map((a) => [a.id, a.types!])))
  const inScope = (scope: Scope) => (scope === 'platform' ? agents : scope.startsWith('type:') ? agents.filter((a) => types[a.id]?.includes(scope.slice(5))) : members(scope as Role))

  const patterns: Pattern[] = []
  for (const role of ['specialist', 'orchestrator'] as Role[]) {
    const them = members(role)
    if (them.length < profile.minAgents) continue
    const other = members(role === 'specialist' ? 'orchestrator' : 'specialist')
    for (const key of allKeys) {
      if (key.startsWith('declared:') || partOf(key) || isVariant(key) || isUnused(key) || patterns.some((p) => p.key === key)) continue
      const has = holders(key, them)
      const share = has.length / them.length
      if (share < profile.threshold) continue
      // the other role has it too (all of it, or as its own pattern): the platform's
      const otherHas = other.length > 0 && holders(key, other).length / other.length >= (other.length >= profile.minAgents ? profile.threshold : 1)
      const decision = decisionOf(key)
      patterns.push({ key, role, scope: decision?.scope ?? (otherHas ? 'platform' : role), share, agents: holders(key).map((a) => a.id), sources: sourcesOf(key), ...(decision ? { decision } : {}) })
    }
  }
  // the patterns of a type, among its specialists, with min_agents of the type: what the role's patterns do not say
  const typeNotes: Result['typeNotes'] = []
  for (const type of profile.types) {
    const them = inScope(`type:${type.id}`)
    if (!them.length) continue
    if (them.length < type.minAgents) {
      typeNotes.push({ type: type.id, agents: them.map((a) => a.id) })
      continue
    }
    for (const key of allKeys) {
      if (key.startsWith('declared:') || partOf(key) || isVariant(key) || isUnused(key) || patterns.some((p) => p.key === key)) continue
      const share = holders(key, them).length / them.length
      if (share < profile.threshold) continue
      const decision = decisionOf(key)
      patterns.push({ key, role: 'specialist', scope: decision?.scope ?? `type:${type.id}`, share, agents: holders(key).map((a) => a.id), sources: sourcesOf(key), ...(decision ? { decision } : {}) })
    }
  }
  // the profile's official blocks are checked on every agent of their role, with or without a majority
  for (const b of profile.blocks) {
    const key = `text:block:${b.id}`
    const found = patterns.find((p) => p.key === key)
    if (found) {
      found.official = b.name
      continue
    }
    const them = members(b.role)
    const decision = decisionOf(key)
    patterns.push({ key, role: b.role, scope: decision?.scope ?? b.role, share: them.length ? holders(key, them).length / them.length : 0, agents: holders(key).map((a) => a.id), sources: sourcesOf(key), official: b.name, ...(decision ? { decision } : {}) })
  }
  // an accepted pattern is checked even when its share no longer makes it one
  for (const decision of cast.decisions.filter((d) => d.status === 'accepted' && !patterns.some((p) => p.key === d.key))) {
    const them = inScope(decision.scope)
    const has = holders(decision.key, them)
    patterns.push({ key: decision.key, role: decision.scope === 'orchestrator' ? 'orchestrator' : 'specialist', scope: decision.scope, share: them.length ? has.length / them.length : 0, agents: has.map((a) => a.id), sources: sourcesOf(decision.key), decision })
  }
  // the parts of a pattern, among the agents of its scope that have the fact; the fact's decision covers them
  for (const key of allKeys.filter((k) => partOf(k))) {
    const parent = patterns.find((p) => p.key === partOf(key))
    if (!parent) continue
    const them = inScope(parent.scope).filter((a) => parent.key in a.facts)
    const share = them.length ? holders(key, them).length / them.length : 0
    if (share < profile.threshold) continue
    const decision = decisionOf(key) ?? parent.decision
    patterns.push({ key, role: parent.role, scope: parent.scope, share, agents: holders(key).map((a) => a.id), sources: sourcesOf(key), partOf: parent.key, ...(decision ? { decision } : {}) })
  }
  patterns.sort((a, b) => a.scope.localeCompare(b.scope) || a.key.localeCompare(b.key))

  const offPattern: OffPattern[] = patterns
    .filter((p) => p.decision?.status !== 'rejected')
    .flatMap((p) => inScope(p.scope).filter((a) => !(p.key in a.facts) && (!p.partOf || p.partOf in a.facts)).map((a) => ({
      agent: a.id, key: p.key, scope: p.scope, ...(p.partOf ? { partOf: p.partOf } : {}), ...(`${p.key}~variant` in a.facts ? { variant: true } : {}),
    })))
    .sort((a, b) => a.agent.localeCompare(b.agent) || a.key.localeCompare(b.key))

  const solos: Holding[] = []
  const orchestratorDoes: Holding[] = []
  for (const key of allKeys) {
    if (key.startsWith('declared:') || partOf(key) || isVariant(key) || isUnused(key)) continue
    const has = holders(key)
    const holding = { key, agents: has.map((a) => a.id), sources: sourcesOf(key) }
    if (has.every((a) => a.role === 'orchestrator')) orchestratorDoes.push(holding)
    else if (has.length === 1) solos.push(holding)
  }

  // a rule: for the agents of its role (or all) that have its `when`, what they must have (`has`) or not have (`not`)
  const holds = (a: (typeof agents)[number], pattern: string) => Object.keys(a.facts).some((k) => matches(k, pattern))
  const gaps: Gap[] = profile.rules
    .map((rule) => ({
      rule,
      agents: (rule.role ? members(rule.role) : agents)
        .filter((a) => (rule.when ?? []).every((w) => holds(a, w)))
        .filter((a) => (rule.has !== undefined && !holds(a, rule.has)) || (rule.not !== undefined && holds(a, rule.not)))
        .map((a) => a.id),
    }))
    .filter((g) => g.agents.length)

  const hasOrchestrator = agents.some((a) => a.role === 'orchestrator')
  const reached = new Set(routes.map((r) => r.agent))
  const unused: Unused[] = agents.flatMap((a) => Object.keys(a.facts).filter(isUnused).sort().map((key) => {
    const [how, what, ...name] = key.split(':')
    return { agent: a.id, key, how: how as Unused['how'], what, name: name.join(':'), sources: a.facts[key] }
  }))

  return {
    ...(profile.name ?? cast.name ? { name: profile.name ?? cast.name } : {}),
    roles, unmatched, agents, patterns, offPattern, solos, orchestratorDoes, gaps, conflicts,
    unknown: found.flatMap((a) => a.unknown.map((u) => ({ ...u, agent: a.id }))),
    names: Object.assign({}, ...found.map((a) => a.names ?? {}), ...found.map((a) => (a.schemaName && a.displayName ? { [a.schemaName]: a.displayName } : {})),
      // the text: a block by its official name or its first words, a marker by its name
      ...blocks.families.map((b) => ({ [`text:block:${b.id}`]: b.official ?? b.label })), ...profile.markers.map((m) => ({ [`text:${m.id}`]: m.name }))),
    types, typeNames: Object.fromEntries(profile.types.map((t) => [t.id, t.name])), typeNotes,
    blocks: blocks.families,
    markerFindings: markerFindings(marked.values, profile.markers, roles),
    contract: {
      routes,
      missing: routes.filter((r) => !r.agent),
      uncalled: hasOrchestrator ? agents.filter((a) => a.role === 'specialist' && !reached.has(a.id)).map((a) => a.id) : [],
      short: routes.filter((r) => r.description && r.description.length < SHORT_ROUTING),
    },
    flows: found.flatMap((a) => (a.flows ?? []).map((f) => ({ ...f, agent: a.id }))),
    unused,
  }
}
