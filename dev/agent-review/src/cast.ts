// The review file (format cast-list/cast-v1): the agents of the last run and their roles, what people said about them
// (declared, with the source) and what was decided about each pattern. build.mjs keeps it; a person or the model edits
// it, or it comes back from the workbook. Written back over the previous file, it keeps the comments people wrote.
import { DNA_API, readFormat } from '@kit/format'
import { RELEASE } from './release'
import { Document, isMap, isSeq, parseDocument, type YAMLMap } from 'yaml'
import type { Problem } from './problems'
import { ROLES, type Role } from './profile'

export const CAST_FORMAT = 'cast-list/cast-v1'
/** The kind under DNA's header (apiVersion github.com/ruinosus/dna/v1); CAST_FORMAT is the line of before. */
export const CAST_KIND = 'AgentReview'
export const STATUSES = ['accepted', 'rejected'] as const
export const SCOPES = ['platform', 'specialist', 'orchestrator'] as const
/** A scope: everybody, a role, or the agents of a type (`type:<id>`). */
export type Scope = (typeof SCOPES)[number] | `type:${string}`
const isScope = (s: string): s is Scope => (SCOPES as readonly string[]).includes(s) || /^type:[\w-]+$/.test(s)
export interface Declared { agent: string; key: string; value: string; source: string }
export interface Decision { key: string; status: (typeof STATUSES)[number]; scope: Scope; why: string }
export interface Cast {
  name?: string
  agents: { id: string; role: Role; types?: string[] }[]
  /** The blocks of text of the last run, so a block keeps its id across small edits. */
  blocks: { id: string; text: string }[]
  declared: Declared[]
  decisions: Decision[]
}

const FIELDS = ['format', 'name', 'agents', 'blocks', 'declared', 'decisions']
type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v)
const str = (v: unknown) => (typeof v === 'string' ? v.trim() : typeof v === 'number' || typeof v === 'boolean' ? String(v) : '')

export function readCast(text: string): { cast?: Cast; problems: Problem[] } {
  const read = readFormat(text, CAST_FORMAT, CAST_KIND)
  if (!read.ok) return { problems: [read.problem.key === 'format' ? { ...read.problem, format: CAST_FORMAT, kind: CAST_KIND } : read.problem] }
  const { raw, at } = read.format
  const problems: Problem[] = []
  for (const k of Object.keys(raw)) if (!FIELDS.includes(k)) problems.push({ line: at([k]), key: 'unknownKey', what: k })
  const list = (k: string) => (Array.isArray(raw[k]) ? (raw[k] as unknown[]) : []).filter(isObj)
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
  const agents = list('agents').map((a, i) => {
    const role = str(a.role)
    if (!(ROLES as readonly string[]).includes(role)) problems.push({ line: at(['agents', i, 'role']), key: 'role', what: `agents[${i}].role`, value: role })
    const types = Array.isArray(a.types) ? a.types.map(str).filter(Boolean) : []
    return { id: need(a.id, `agents[${i}].id`, ['agents', i]), role: role as Role, ...(types.length ? { types } : {}) }
  })
  const blocks = list('blocks').map((b, i) => ({ id: need(b.id, `blocks[${i}].id`, ['blocks', i]), text: need(b.text, `blocks[${i}].text`, ['blocks', i]) }))
  once('blocks', blocks.map((b) => b.id))
  once('agents', agents.map((a) => a.id))
  const declared = list('declared').map((d, i) => ({
    agent: need(d.agent, `declared[${i}].agent`, ['declared', i]),
    key: need(d.key, `declared[${i}].key`, ['declared', i]),
    value: str(d.value),
    source: str(d.source),
  }))
  once('declared', declared.map((d) => `${d.agent} ${d.key}`))
  const decisions = list('decisions').map((d, i) => {
    const status = str(d.status)
    const scope = str(d.scope)
    if (!(STATUSES as readonly string[]).includes(status)) problems.push({ line: at(['decisions', i, 'status']), key: 'status', value: status })
    if (!isScope(scope)) problems.push({ line: at(['decisions', i, 'scope']), key: 'scope', value: scope })
    return { key: need(d.key, `decisions[${i}].key`, ['decisions', i]), status, scope, why: str(d.why) } as Decision
  })
  once('decisions', decisions.map((d) => d.key))
  if (problems.length) return { problems }
  return { cast: { ...(str(raw.name) ? { name: str(raw.name) } : {}), agents, blocks, declared, decisions }, problems }
}

const HEADER = ` What people said about the agents, and what was decided. build.mjs keeps it up to date; edit it, or fill the
 workbook's «Declared» sheet and the «Decision» column and read it back with --from.
 Written by agent-review ${RELEASE}.`
// how each list's items are told apart, so an item that changed keeps its node (and its comments)
const LISTS = {
  agents: (x: Obj) => str(x.id),
  blocks: (x: Obj) => str(x.id),
  declared: (x: Obj) => `${str(x.agent)} ${str(x.key)}`,
  decisions: (x: Obj) => str(x.key),
} as const
// a field left empty is not written
const plain = (item: object) => Object.fromEntries(Object.entries(item).filter(([, v]) => v !== '' && v !== undefined))

/** The cast as YAML: over `previous` (keeping its comments and layout) when there is one. */
export function writeCast(cast: Cast, previous?: string): string {
  const old = previous ? parseDocument(previous) : undefined
  const doc = old && !old.errors.length && isMap(old.contents) ? old : new Document({ apiVersion: DNA_API, kind: CAST_KIND })
  // the header is ours: a new file gets it, and one that has it gets this run's version
  if (doc !== old || doc.commentBefore?.includes('build.mjs keeps it up to date')) doc.commentBefore = HEADER
  // what the file says it is: DNA's header for a new one; one written with the format line of before keeps it
  const dna = doc.get('format') === undefined
  if (dna) {
    if (doc.get('apiVersion') !== DNA_API) doc.set('apiVersion', DNA_API)
    if (doc.get('kind') !== CAST_KIND) doc.set('kind', CAST_KIND)
  } else if (doc.get('format') !== CAST_FORMAT) doc.set('format', CAST_FORMAT)
  const nameAt = dna ? ['metadata', 'name'] : ['name']
  if (cast.name === undefined) {
    if (doc.hasIn(nameAt)) doc.deleteIn(nameAt)
  } else if (doc.getIn(nameAt) !== cast.name) doc.setIn(nameAt, cast.name)
  for (const [k, id] of Object.entries(LISTS) as [keyof typeof LISTS, (x: Obj) => string][]) {
    const items = cast[k] as object[]
    if (!items.length) {
      doc.delete(k)
      continue
    }
    let seq = doc.get(k, true)
    if (!isSeq(seq)) doc.set(k, (seq = doc.createNode([])))
    if (!isSeq(seq)) continue
    const before = new Map(seq.items.filter(isMap).map((n) => [id((n as YAMLMap).toJSON() as Obj), n as YAMLMap]))
    seq.items = items.map((item) => {
      const want = plain(item)
      const node = before.get(id(want as Obj))
      if (!node) {
        const fresh = doc.createNode(want) as YAMLMap
        // one line per item, except a block of text: its lines read as they are
        fresh.flow = k !== 'blocks'
        return fresh
      }
      for (const [f, v] of Object.entries(want)) if (JSON.stringify((node.toJSON() as Obj)[f]) !== JSON.stringify(v)) node.set(f, v)
      for (const f of Object.keys(node.toJSON() as Obj)) if (!(f in want)) node.delete(f)
      return node
    })
  }
  return doc.toString({ lineWidth: 0, flowCollectionPadding: true })
}
