// The profile (format cast-list/profile-v1): the team's standard, written so a run can check it — who is the
// orchestrator, how common a fact must be to be a pattern, the rules every agent of a role must follow, the focus
// areas, what to leave out. Private: it names the team's agents. With no profile, the defaults below hold.
import { readFormat } from '@kit/format'
import type { AgentFacts } from './extract'
import type { Problem } from './problems'

export const PROFILE_FORMAT = 'cast-list/profile-v1'
export const ROLES = ['orchestrator', 'specialist'] as const
export type Role = (typeof ROLES)[number]
/** A list of agent ids, or «*»: every agent not named elsewhere. */
export type Members = string[] | '*'
export interface Rule { id: string; role: Role; has: string; says: string }
export interface FocusArea { id: string; name: string; facts: string[] }
export interface Profile {
  name?: string
  roles: { orchestrator?: Members; specialist?: Members }
  /** A pattern: a fact in at least this share of a role's agents… */
  threshold: number
  /** …when the role has at least this many agents. */
  minAgents: number
  rules: Rule[]
  focusAreas: FocusArea[]
  ignore: string[]
  microsoftPatterns: boolean
}

export const DEFAULT_PROFILE: Profile = { roles: {}, threshold: 0.7, minAgents: 3, rules: [], focusAreas: [], ignore: [], microsoftPatterns: true }

const FIELDS = ['format', 'name', 'roles', 'threshold', 'min_agents', 'rules', 'focus_areas', 'ignore', 'microsoft_patterns']
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
  const rules: Rule[] = list('rules').filter(isObj).map((x, i) => {
    const has = need(x.has, `rules[${i}].has`, ['rules', i])
    return { id: need(x.id, `rules[${i}].id`, ['rules', i]), role: role(x.role, `rules[${i}].role`, ['rules', i, 'role']), has, says: str(x.says) || has }
  })
  once('rules', rules.map((x) => x.id))
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
    roles, threshold, minAgents, rules, focusAreas, ignore: strs(raw.ignore),
    // «on» and «off» are text in YAML 1.2
    microsoftPatterns: !(ms === false || str(ms).toLowerCase() === 'off'),
  }
  return problems.length ? { problems } : { profile, problems }
}

/** Calls another agent (not one of its own topics). */
export const callsAnAgent = (a: AgentFacts) => Object.keys(a.facts).some((k) => k.startsWith('calls:') && !k.startsWith('calls:topic:'))

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
