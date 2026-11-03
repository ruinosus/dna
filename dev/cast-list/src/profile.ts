// The profile (format cast-list/profile-v1): the team's standard, written so a run can check it — who is the
// orchestrator, how common a fact must be to be a pattern, the rules every agent of a role must follow, the focus
// areas, what to leave out. Private: it names the team's agents. With no profile, the defaults below hold.
import { readFormat } from '@kit/format'
import type { AgentFacts } from './extract'
import { matches } from './labels'
import type { Problem } from './problems'

export const PROFILE_FORMAT = 'cast-list/profile-v1'
export const ROLES = ['orchestrator', 'specialist'] as const
export type Role = (typeof ROLES)[number]
/** A list of agent ids, or «*»: every agent not named elsewhere. */
export type Members = string[] | '*'
/** What an agent of `role` (any role, when absent) must have (`has`) or must not have (`not`) — when it has `when`. */
export interface Rule { id: string; role?: Role; when?: string[]; has?: string; not?: string; says: string }
/** A pattern of words in the texts: a fact `text:<id>`, or `text:<id>=<value>` with the captured `value`. */
export interface Marker { id: string; name: string; in: 'instructions' | 'descriptions' | 'all'; pattern: string; value?: string }
/** A block of text the team pastes in every agent of `role`. */
export interface OfficialBlock { id: string; name: string; text: string; role: Role }
export interface AgentType { id: string; name: string; when: { all?: string[]; any?: string[]; none?: string[] }; minAgents: number }
export interface FocusArea { id: string; name: string; facts: string[] }
export interface Profile {
  name?: string
  roles: { orchestrator?: Members; specialist?: Members }
  /** A pattern: a fact in at least this share of a role's agents… */
  threshold: number
  /** …when the role has at least this many agents. */
  minAgents: number
  rules: Rule[]
  markers: Marker[]
  blocks: OfficialBlock[]
  types: AgentType[]
  focusAreas: FocusArea[]
  ignore: string[]
  microsoftPatterns: boolean
}

export const DEFAULT_PROFILE: Profile = { roles: {}, threshold: 0.7, minAgents: 3, rules: [], markers: [], blocks: [], types: [], focusAreas: [], ignore: [], microsoftPatterns: true }

const FIELDS = ['format', 'name', 'roles', 'threshold', 'min_agents', 'rules', 'markers', 'blocks', 'types', 'focus_areas', 'ignore', 'microsoft_patterns']
const IN = ['instructions', 'descriptions', 'all']
// the kinds of key there are (references/keys.md): a key in a type or a rule must start with one
const PREFIXES = new Set(['trigger', 'setting', 'topics', 'instructions', 'connector', 'operation', 'connref', 'mcp', 'flow', 'knowledge', 'node', 'calls', 'reaches', 'child', 'var', 'var-in', 'model', 'auth', 'ms', 'declared', 'text', 'yaml-only', 'called-with', 'routing', 'flow-uses', 'flow-returns', 'orphan', 'disabled', 'telemetry', 'eval'])
const knownKey = (key: string) => PREFIXES.has(key.split(':')[0])
export { matches } from './labels'
type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v)
const str = (v: unknown) => (typeof v === 'string' ? v.trim() : typeof v === 'number' ? String(v) : '')
const strs = (v: unknown) => (Array.isArray(v) ? v.map(str).filter(Boolean) : str(v) ? [str(v)] : [])
const isRole = (v: string): v is Role => (ROLES as readonly string[]).includes(v)

export function readProfile(text: string): { profile?: Profile; problems: Problem[] } {
  const read = readFormat(text, PROFILE_FORMAT)
  if (!read.ok) return { problems: [read.problem.key === 'format' ? { ...read.problem, format: PROFILE_FORMAT } : read.problem] }
  const { raw, at } = read.format
  const problems: Problem[] = []
  for (const k of Object.keys(raw)) if (!FIELDS.includes(k)) problems.push({ line: at([k]), key: 'unknownKey', what: k })
  const need = (v: unknown, what: string, path: (string | number)[]) => {
    if (!str(v)) problems.push({ line: at(path), key: 'missing', what })
    return str(v)
  }
  const once = (what: string, ids: string[]) => {
    const seen = new Set<string>()
    ids.forEach((id, i) => {
      if (id && seen.has(id)) problems.push({ line: at([what, i]), key: 'duplicate', what, id })
      seen.add(id)
    })
  }
  const list = (k: string) => (Array.isArray(raw[k]) ? (raw[k] as unknown[]) : [])

  const threshold = raw.threshold === undefined ? DEFAULT_PROFILE.threshold : Number(raw.threshold)
  if (!(threshold > 0 && threshold <= 1)) problems.push({ line: at(['threshold']), key: 'threshold', value: str(raw.threshold) })
  const minAgents = raw.min_agents === undefined ? DEFAULT_PROFILE.minAgents : Number(raw.min_agents)
  if (!(Number.isInteger(minAgents) && minAgents >= 1)) problems.push({ line: at(['min_agents']), key: 'minAgents', value: str(raw.min_agents) })

  const roles: Profile['roles'] = {}
  const r = isObj(raw.roles) ? raw.roles : {}
  for (const k of Object.keys(r)) {
    if (!isRole(k)) problems.push({ line: at(['roles', k]), key: 'role', what: `roles.${k}`, value: k })
    else roles[k] = str(r[k]) === '*' ? '*' : strs(r[k])
  }
  const role = (v: unknown, what: string, path: (string | number)[]): Role => {
    if (!isRole(str(v))) problems.push({ line: at(path), key: 'role', what, value: str(v) })
    return str(v) as Role
  }
  // keys a type or a rule names must be keys there can be
  const keys = (v: unknown, what: string, path: (string | number)[]) => {
    const ks = strs(v)
    for (const k of ks) if (!knownKey(k)) problems.push({ line: at(path), key: 'prefix', what, value: k })
    return ks
  }
  const rules: Rule[] = list('rules').filter(isObj).map((x, i) => {
    const what = `rules[${i}]`
    const has = keys(x.has, what, ['rules', i])[0]
    const not = keys(x.not, what, ['rules', i])[0]
    const when = keys(x.when, what, ['rules', i])
    if (!has && !not) problems.push({ line: at(['rules', i]), key: 'rule', what })
    return {
      id: need(x.id, `${what}.id`, ['rules', i]),
      ...(x.role !== undefined ? { role: role(x.role, `${what}.role`, ['rules', i, 'role']) } : {}),
      ...(when.length ? { when } : {}), ...(has ? { has } : {}), ...(not ? { not } : {}),
      says: str(x.says) || has || `not ${not}`,
    }
  })
  once('rules', rules.map((x) => x.id))
  const markers: Marker[] = list('markers').filter(isObj).map((x, i) => {
    const what = `markers[${i}]`
    const pattern = need(x.pattern, `${what}.pattern`, ['markers', i])
    try {
      if (pattern) new RegExp(pattern, 'i')
    } catch (e) {
      problems.push({ line: at(['markers', i]), key: 'regex', what: `${what}.pattern`, detail: (e as Error).message.replace(/^Invalid regular expression: /, '') })
    }
    const where = str(x.in) || 'instructions'
    if (!IN.includes(where)) problems.push({ line: at(['markers', i]), key: 'in', what: `${what}.in`, value: where })
    const id = need(x.id, `${what}.id`, ['markers', i])
    return { id, name: str(x.name) || id, in: where as Marker['in'], pattern, ...(str(x.value) ? { value: str(x.value) } : {}) }
  })
  once('markers', markers.map((x) => x.id))
  const blocks: OfficialBlock[] = list('blocks').filter(isObj).map((x, i) => {
    const id = need(x.id, `blocks[${i}].id`, ['blocks', i])
    return { id, name: str(x.name) || id, text: need(x.text, `blocks[${i}].text`, ['blocks', i]), role: x.role !== undefined ? role(x.role, `blocks[${i}].role`, ['blocks', i, 'role']) : 'specialist' }
  })
  once('blocks', blocks.map((x) => x.id))
  const types: AgentType[] = list('types').filter(isObj).map((x, i) => {
    const what = `types[${i}]`
    const w = isObj(x.when) ? x.when : {}
    const when = Object.fromEntries((['all', 'any', 'none'] as const).filter((k) => w[k] !== undefined).map((k) => [k, keys(w[k], what, ['types', i])]))
    if (!when.all?.length && !when.any?.length) problems.push({ line: at(['types', i]), key: 'when', what })
    const min = x.min_agents === undefined ? 2 : Number(x.min_agents)
    if (!(Number.isInteger(min) && min >= 1)) problems.push({ line: at(['types', i, 'min_agents']), key: 'minAgents', value: str(x.min_agents) })
    const id = need(x.id, `${what}.id`, ['types', i])
    return { id, name: str(x.name) || id, when, minAgents: min }
  })
  once('types', types.map((x) => x.id))
  const focusAreas: FocusArea[] = list('focus_areas').filter(isObj).map((x, i) => {
    const facts = strs(x.facts)
    if (!facts.length) problems.push({ line: at(['focus_areas', i]), key: 'missing', what: `focus_areas[${i}].facts` })
    const id = need(x.id, `focus_areas[${i}].id`, ['focus_areas', i])
    return { id, name: str(x.name) || id, facts }
  })
  once('focus_areas', focusAreas.map((x) => x.id))
  const ms = raw.microsoft_patterns
  const profile: Profile = {
    ...(str(raw.name) ? { name: str(raw.name) } : {}),
    roles, threshold, minAgents, rules, markers, blocks, types, focusAreas, ignore: strs(raw.ignore),
    // «on» and «off» are text in YAML 1.2
    microsoftPatterns: !(ms === false || str(ms).toLowerCase() === 'off'),
  }
  return problems.length ? { problems } : { profile, problems }
}

/** Calls another agent (not one of its own topics). */
export const callsAnAgent = (a: AgentFacts) => Object.keys(a.facts).some((k) => k.startsWith('calls:') && !k.startsWith('calls:topic:') && !k.startsWith('calls:action:'))

/**
 * Each agent's role: named in the profile; else the role the cast file gave it; else «*» in the profile; else an
 * orchestrator when it calls another agent, a specialist otherwise. `unmatched`: ids the profile names that are not here.
 */
export function rolesOf(agents: AgentFacts[], profile: Profile, given: Record<string, Role> = {}): { roles: Record<string, Role>; unmatched: string[] } {
  const { orchestrator: o, specialist: s } = profile.roles
  const named = (m: Members | undefined, id: string) => Array.isArray(m) && m.includes(id)
  const roles = Object.fromEntries(agents.map((a): [string, Role] => [a.id,
    named(o, a.id) ? 'orchestrator'
      : named(s, a.id) ? 'specialist'
        : given[a.id] ?? (o === '*' ? 'orchestrator' : s === '*' ? 'specialist' : callsAnAgent(a) ? 'orchestrator' : 'specialist')]))
  const ids = new Set(agents.map((a) => a.id))
  const unmatched = [o, s].flatMap((m) => (Array.isArray(m) ? m : [])).filter((id) => !ids.has(id))
  return { roles, unmatched }
}

/**
 * Each specialist's types: every type of the profile whose `when` its facts match (all of `all`, one of `any`, none
 * of `none`) — unless the cast file gives its types. An orchestrator has no type.
 */
export function typesOf(agents: { id: string; facts: Record<string, unknown> }[], roles: Record<string, Role>, profile: Profile, given: Record<string, string[]>): Record<string, string[]> {
  const has = (facts: Record<string, unknown>, pattern: string) => Object.keys(facts).some((k) => matches(k, pattern))
  return Object.fromEntries(agents.map((a) => {
    if (roles[a.id] !== 'specialist') return [a.id, []]
    if (given[a.id]?.length) return [a.id, given[a.id]]
    const fit = profile.types.filter(({ when: w }) => (w.all ?? []).every((p) => has(a.facts, p)) && (!w.any?.length || w.any.some((p) => has(a.facts, p))) && !(w.none ?? []).some((p) => has(a.facts, p)))
    return [a.id, fit.map((t) => t.id)]
  }))
}
