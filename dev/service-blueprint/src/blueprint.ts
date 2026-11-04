// A service blueprint (format front-of-house/v1): what the customer does at each moment and how they feel, what they see,
// and who makes it happen in front of them, behind the scenes and in the systems — with the promises, the pains and the
// actions. Read from YAML (or JSON) with the line of every problem; what names nothing is an error.
import { DNA_API, readFormat } from '@kit/format'

export const FORMAT = 'front-of-house/v1'
/** The kind under DNA's header (apiVersion github.com/ruinosus/dna/v1): the file of now; FORMAT is the line of before. */
export const KIND = 'ServiceBlueprint'

export interface Phase { id: string; name: string }
export interface Actor {
  id: string
  name: string
  /** front: the customer sees them (the stage); back: they do not (backstage). */
  layer: 'front' | 'back'
}
export interface System { id: string; name: string }
/** What an actor does at a moment (or a screen or thing, with no actor). */
export interface Doing { actor?: string; does: string }
export interface Pledge { says: string; owner?: string; within?: string }
export interface Pain { says: string; source?: string }
export interface Moment {
  id: string
  phase: string
  /** What the customer does. */
  customer: string
  /** How the customer feels, 1 (bad) to 5 (good). */
  feels?: number
  marks?: ('fail' | 'wait')[]
  /** What the customer sees or keeps (a screen, an email, a receipt). */
  evidence?: string[]
  front?: Doing[]
  back?: Doing[]
  /** The systems and partners behind it. */
  support?: string[]
  promise?: Pledge
  pains?: Pain[]
  /** A stage of a way-of-working way of working that sustains it, «way#stage». */
  way?: string
}
export interface Action { id: string; moment: string; does: string; owner?: string; due?: string }
export interface Blueprint {
  name: string
  /** Who lives the journey («Cliente», «a new member»). */
  who: string
  about?: string
  phases: Phase[]
  actors: Actor[]
  systems: System[]
  moments: Moment[]
  actions: Action[]
}

export type Problem =
  | { line: number; key: 'syntax'; detail: string }
  | { line: number; key: 'format' }
  | { line: number; key: 'missing'; what: string }
  | { line: number; key: 'duplicate'; what: string; id: string }
  | { line: number; key: 'unknown'; what: 'phase' | 'actor' | 'system' | 'moment'; id: string; at: string }
  | { line: number; key: 'feels'; moment: string; value: string }

export interface Read {
  blueprint?: Blueprint
  problems: Problem[]
}

type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v)
const str = (v: unknown) => (typeof v === 'string' ? v.trim() : typeof v === 'number' ? String(v) : '')
const slug = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40)
const texts = (v: unknown) => (Array.isArray(v) ? v.map(str).filter(Boolean) : str(v) ? [str(v)] : [])

export function readBlueprint(text: string): Read {
  const read = readFormat(text, FORMAT, KIND)
  if (!read.ok) return { problems: [read.problem] }
  const { raw, at } = read.format
  const problems: Problem[] = []
  const need = (v: unknown, what: string, path: (string | number)[]) => {
    if (!str(v)) problems.push({ line: at(path), key: 'missing', what })
    return str(v)
  }
  const list = (k: string) => (Array.isArray(raw[k]) ? (raw[k] as unknown[]) : [])
  const name = need(raw.name, 'name', ['name'])
  // a phase, an actor or a system may be a plain name: its id is made from it
  const phases: Phase[] = list('phases').map((p) => (isObj(p) ? { id: str(p.id) || slug(str(p.name)), name: str(p.name) || str(p.id) } : { id: slug(str(p)), name: str(p) }))
  const actors: Actor[] = list('actors').filter(isObj).map((a, i) => ({ id: need(a.id, `actors[${i}].id`, ['actors', i]), name: str(a.name) || str(a.id), layer: str(a.layer) === 'front' ? 'front' : 'back' }))
  const systems: System[] = list('systems').map((s) => (isObj(s) ? { id: str(s.id) || slug(str(s.name)), name: str(s.name) || str(s.id) } : { id: slug(str(s)), name: str(s) }))
  const doing = (v: unknown): Doing[] => (Array.isArray(v) ? v : v ? [v] : []).map((d) => (isObj(d) ? { ...(str(d.actor) ? { actor: str(d.actor) } : {}), does: str(d.does) } : { does: str(d) })).filter((d) => d.does)
  const moments: Moment[] = list('moments').filter(isObj).map((m, i) => {
    const marks = texts(m.marks).filter((x): x is 'fail' | 'wait' => x === 'fail' || x === 'wait')
    const feels = m.feels === undefined || m.feels === null ? undefined : Number(m.feels)
    if (feels !== undefined && !(Number.isInteger(feels) && feels >= 1 && feels <= 5)) problems.push({ line: at(['moments', i, 'feels']), key: 'feels', moment: str(m.id), value: str(m.feels) })
    const promise = isObj(m.promise) && str(m.promise.says) ? { says: str(m.promise.says), ...(str(m.promise.owner) ? { owner: str(m.promise.owner) } : {}), ...(str(m.promise.within) ? { within: str(m.promise.within) } : {}) } : undefined
    const pains = (Array.isArray(m.pains) ? m.pains : []).map((p) => (isObj(p) ? { says: str(p.says), ...(str(p.source) ? { source: str(p.source) } : {}) } : { says: str(p) })).filter((p) => p.says)
    const front = doing(m.front)
    const back = doing(m.back)
    const support = texts(m.support)
    const evidence = texts(m.evidence)
    return {
      id: need(m.id, `moments[${i}].id`, ['moments', i]),
      phase: str(m.phase) ? (phases.find((p) => p.id === str(m.phase) || p.name === str(m.phase))?.id ?? str(m.phase)) : (phases[0]?.id ?? ''),
      customer: need(m.customer, `moments[${i}].customer`, ['moments', i]),
      ...(feels !== undefined && Number.isInteger(feels) ? { feels } : {}),
      ...(marks.length ? { marks } : {}),
      ...(evidence.length ? { evidence } : {}),
      ...(front.length ? { front } : {}),
      ...(back.length ? { back } : {}),
      ...(support.length ? { support } : {}),
      ...(promise ? { promise } : {}),
      ...(pains.length ? { pains } : {}),
      ...(str(m.way) ? { way: str(m.way) } : {}),
    }
  })
  if (!moments.length) problems.push({ line: at(['moments']), key: 'missing', what: 'moments' })
  const actions: Action[] = list('actions').filter(isObj).map((a, i) => ({
    id: str(a.id) || `action-${i + 1}`,
    moment: need(a.moment, `actions[${i}].moment`, ['actions', i]),
    does: need(a.does, `actions[${i}].does`, ['actions', i]),
    ...(str(a.owner) ? { owner: str(a.owner) } : {}),
    ...(str(a.due) ? { due: str(a.due) } : {}),
  }))
  const once = (what: string, ids: string[], k: string) => {
    const seen = new Set<string>()
    ids.forEach((id, i) => {
      if (id && seen.has(id)) problems.push({ line: at([k, i]), key: 'duplicate', what, id })
      seen.add(id)
    })
  }
  once('phases', phases.map((p) => p.id), 'phases')
  once('actors', actors.map((a) => a.id), 'actors')
  once('systems', systems.map((s) => s.id), 'systems')
  once('moments', moments.map((m) => m.id), 'moments')
  // what names nothing
  const has = { phase: new Set(phases.map((p) => p.id)), actor: new Set(actors.map((a) => a.id)), system: new Set(systems.map((s) => s.id)), moment: new Set(moments.map((m) => m.id)) }
  const known = (what: keyof typeof has, id: string | undefined, path: (string | number)[], where: string) => {
    if (id && !has[what].has(id)) problems.push({ line: at(path), key: 'unknown', what, id, at: where })
  }
  moments.forEach((m, i) => {
    if (phases.length) known('phase', m.phase, ['moments', i, 'phase'], m.id)
    ;(['front', 'back'] as const).forEach((layer) => (m[layer] ?? []).forEach((d, k) => known('actor', d.actor, ['moments', i, layer, k], m.id)))
    ;(m.support ?? []).forEach((s, k) => known('system', s, ['moments', i, 'support', k], m.id))
    known('actor', m.promise?.owner, ['moments', i, 'promise', 'owner'], m.id)
  })
  actions.forEach((a, i) => {
    known('moment', a.moment, ['actions', i, 'moment'], a.id)
    known('actor', a.owner, ['actions', i, 'owner'], a.id)
  })
  if (problems.length) return { problems }
  return { blueprint: { name, who: str(raw.who) || 'Customer', ...(str(raw.about) ? { about: str(raw.about) } : {}), phases, actors, systems, moments, actions }, problems }
}

/** A problem in a sentence, in English or Portuguese. */
export function problemText(p: Problem, lang: 'en' | 'pt' = 'en'): string {
  const pt = lang === 'pt'
  const what = { phase: pt ? 'fase' : 'phase', actor: pt ? 'ator' : 'actor', system: pt ? 'sistema' : 'system', moment: pt ? 'momento' : 'moment' }
  switch (p.key) {
    case 'syntax': return pt ? `não se lê como YAML (${p.detail})` : `does not read as YAML (${p.detail})`
    case 'format': return pt ? `o arquivo começa com «apiVersion: ${DNA_API}» e «kind: ${KIND}» (ou com «format: ${FORMAT}», de antes)` : `the file starts with «apiVersion: ${DNA_API}» and «kind: ${KIND}» (or «format: ${FORMAT}», from before)`
    case 'missing': return pt ? `falta «${p.what}»` : `«${p.what}» is missing`
    case 'duplicate': return pt ? `${p.what}: o id «${p.id}» se repete` : `${p.what}: the id «${p.id}» is repeated`
    case 'unknown': return pt ? `«${p.at}» cita o ${what[p.what]} «${p.id}», que não existe` : `«${p.at}» names the ${what[p.what]} «${p.id}», which does not exist`
    case 'feels': return pt ? `«${p.moment}»: «feels» vai de 1 a 5 (está «${p.value}»)` : `«${p.moment}»: «feels» goes from 1 to 5 (it is «${p.value}»)`
  }
}
