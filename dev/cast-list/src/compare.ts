// Compares the agents: what most agents of a role have (a pattern, and whether the orchestrator has it too — then it is
// the platform's), who is off a pattern, what only one specialist has (innovation or debt: someone has to say), what
// only the orchestrator does, the profile's rules not met, and what people said that the YAML contradicts. A decision
// in the cast file marks a pattern; an accepted one is checked even when it would no longer be a pattern by its share.
import type { Cast, Decision } from './cast'
import type { AgentFacts, Facts, Source, Unknown } from './extract'
import { MS_PATTERNS } from './microsoft'
import { rolesOf, type Profile, type Role, type Rule } from './profile'

export type Scope = 'platform' | Role
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
}
export interface OffPattern { agent: string; key: string; scope: Scope }
export interface Holding { key: string; agents: string[]; sources: Source[] }
export interface Gap { rule: Rule; agents: string[] }
export interface Conflict { agent: string; key: string; declared: string; observed: boolean; source: string }
export interface Result {
  name?: string
  roles: Record<string, Role>
  /** Agents the profile names that are not in the folder. */
  unmatched: string[]
  /** Each agent with what it has: what was seen (less what the profile ignores) and what people declared. */
  agents: { id: string; role: Role; displayName?: string; facts: Facts; children: AgentFacts['children'] }[]
  patterns: Pattern[]
  offPattern: OffPattern[]
  solos: Holding[]
  orchestratorDoes: Holding[]
  gaps: Gap[]
  conflicts: Conflict[]
  unknown: (Unknown & { agent: string })[]
}

const NO = /^(no|não|nao|false|off|0)$/i
// a Microsoft pattern with no mark in the YAML can only be declared
const DECLARED_ONLY = new Set(MS_PATTERNS.filter((p) => !p.sign).map((p) => `ms:${p.id}`))
/** A declared key that is a claim about the YAML («trigger:OnEscalate»), not a fact only people know («kpi»). */
const isClaim = (key: string) => key.includes(':') && !key.startsWith('declared:') && !DECLARED_ONLY.has(key)
const declaredKey = (key: string) => (key.startsWith('declared:') ? key : `declared:${key}`)

export function compare(found: AgentFacts[], profile: Profile, cast: Cast): Result {
  const given = Object.fromEntries(cast.agents.map((a) => [a.id, a.role]))
  const { roles, unmatched } = rolesOf(found, profile, given)
  const ignored = (k: string) => profile.ignore.includes(k) || (!profile.microsoftPatterns && k.startsWith('ms:'))
  const conflicts: Conflict[] = []
  const agents = found.map((a) => {
    const facts: Facts = Object.fromEntries(Object.entries(a.facts).filter(([k]) => !ignored(k)))
    for (const d of cast.declared.filter((x) => x.agent === a.id)) {
      const says = !NO.test(d.value)
      if (isClaim(d.key)) {
        // what was seen wins: a claim never changes a fact, it only shows where people and the YAML disagree
        const observed = d.key in a.facts
        if (says !== observed) conflicts.push({ agent: a.id, key: d.key, declared: d.value || 'yes', observed, source: d.source })
      } else if (says) (facts[declaredKey(d.key)] ??= []).push({ file: d.source ? `declared: ${d.source}` : 'declared' })
    }
    return { id: a.id, role: roles[a.id], ...(a.displayName ? { displayName: a.displayName } : {}), facts, children: a.children }
  })

  const members = (role: Role) => agents.filter((a) => a.role === role)
  const holders = (key: string, of = agents) => of.filter((a) => key in a.facts)
  const sourcesOf = (key: string, of = agents) => of.flatMap((a) => a.facts[key] ?? [])
  const allKeys = [...new Set(agents.flatMap((a) => Object.keys(a.facts)))].sort()
  const decisionOf = (key: string) => cast.decisions.find((d) => d.key === key)
  const inScope = (scope: Scope) => (scope === 'platform' ? agents : members(scope))

  const patterns: Pattern[] = []
  for (const role of ['specialist', 'orchestrator'] as Role[]) {
    const them = members(role)
    if (them.length < profile.minAgents) continue
    const other = members(role === 'specialist' ? 'orchestrator' : 'specialist')
    for (const key of allKeys) {
      if (key.startsWith('declared:') || patterns.some((p) => p.key === key)) continue
      const has = holders(key, them)
      const share = has.length / them.length
      if (share < profile.threshold) continue
      // the other role has it too (all of it, or as its own pattern): the platform's
      const otherHas = other.length > 0 && holders(key, other).length / other.length >= (other.length >= profile.minAgents ? profile.threshold : 1)
      const decision = decisionOf(key)
      patterns.push({ key, role, scope: decision?.scope ?? (otherHas ? 'platform' : role), share, agents: holders(key).map((a) => a.id), sources: sourcesOf(key), ...(decision ? { decision } : {}) })
    }
  }
  // an accepted pattern is checked even when its share no longer makes it one
  for (const decision of cast.decisions.filter((d) => d.status === 'accepted' && !patterns.some((p) => p.key === d.key))) {
    const them = inScope(decision.scope)
    const has = holders(decision.key, them)
    patterns.push({ key: decision.key, role: decision.scope === 'orchestrator' ? 'orchestrator' : 'specialist', scope: decision.scope, share: them.length ? has.length / them.length : 0, agents: has.map((a) => a.id), sources: sourcesOf(decision.key), decision })
  }
  patterns.sort((a, b) => a.scope.localeCompare(b.scope) || a.key.localeCompare(b.key))

  const offPattern: OffPattern[] = patterns
    .filter((p) => p.decision?.status !== 'rejected')
    .flatMap((p) => inScope(p.scope).filter((a) => !(p.key in a.facts)).map((a) => ({ agent: a.id, key: p.key, scope: p.scope })))
    .sort((a, b) => a.agent.localeCompare(b.agent) || a.key.localeCompare(b.key))

  const solos: Holding[] = []
  const orchestratorDoes: Holding[] = []
  for (const key of allKeys) {
    if (key.startsWith('declared:')) continue
    const has = holders(key)
    const holding = { key, agents: has.map((a) => a.id), sources: sourcesOf(key) }
    if (has.every((a) => a.role === 'orchestrator')) orchestratorDoes.push(holding)
    else if (has.length === 1) solos.push(holding)
  }

  const gaps: Gap[] = profile.rules
    .map((rule) => ({ rule, agents: members(rule.role).filter((a) => !(rule.has in a.facts)).map((a) => a.id) }))
    .filter((g) => g.agents.length)

  return {
    ...(profile.name ?? cast.name ? { name: profile.name ?? cast.name } : {}),
    roles, unmatched, agents, patterns, offPattern, solos, orchestratorDoes, gaps, conflicts,
    unknown: found.flatMap((a) => a.unknown.map((u) => ({ ...u, agent: a.id }))),
  }
}
