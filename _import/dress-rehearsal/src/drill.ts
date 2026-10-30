// A drill: an incident played as scenes and choices, made from the team's runbook (format dress-rehearsal/v1). Read from
// YAML (or JSON) with the line of every problem; what breaks the game is an error and nothing is made from the file.
import { isMap, LineCounter, parseDocument } from 'yaml'

export const FORMAT = 'dress-rehearsal/v1'

export interface Role {
  id: string
  name: string
  /** Who is playing: in the room from the start. */
  you?: boolean
  /** In the room from the start without being the player. */
  in?: boolean
  /** What this role can do (the choices that need it). */
  can?: string[]
}
export interface Inject {
  at?: string
  says: string
}
export interface Choice {
  label: string
  /** The scene it leads to. */
  go: string
  /** What happens, said after choosing. */
  then?: string
  /** The part of the runbook it follows (a heading or a mark like «§2»). */
  runbook?: string
  minutes?: number
  /** Impact added (in the drill's unit). */
  lost?: number
  /** A role it brings into the room. */
  calls?: string
  /** What it needs someone in the room to be able to do. */
  needs?: string
  /** It tells the people affected. */
  notifies?: boolean
}
export interface Scene {
  id: string
  says: string
  /** A drawing (chalk-talk's text syntax or JSON). */
  draw?: string
  injects?: Inject[]
  choices?: Choice[]
  /** The game ends here. */
  end?: 'resolved' | 'worse'
}
export interface Gap {
  says: string
  /** Where it was seen (the runbook's part, the conversation). */
  source?: string
}
export interface Drill {
  name: string
  /** What it was made from (a runbook, a post-mortem). */
  from?: string
  about?: string
  /** The time when the player comes in, «03:12». */
  clock: string
  /** What the impact counts («pedidos perdidos», «failed payments»). */
  impact?: string
  /** Minutes it takes to call someone in from the room panel. */
  call_minutes?: number
  roles: Role[]
  start: string
  scenes: Scene[]
  gaps?: Gap[]
}

export type Problem =
  | { line: number; key: 'syntax'; detail: string }
  | { line: number; key: 'format' }
  | { line: number; key: 'missing'; what: string }
  | { line: number; key: 'duplicate'; what: string; id: string }
  | { line: number; key: 'unknownScene'; from: string; go: string }
  | { line: number; key: 'unknownRole'; scene: string; role: string }
  | { line: number; key: 'stuck'; scene: string }
  | { line: number; key: 'noEnd' }
  | { line: number; key: 'clock'; value: string }

export interface Read {
  drill?: Drill
  problems: Problem[]
  /** The line each scene's drawing starts on (a mistake in a drawing says its line in the file). */
  drawLines?: Record<string, number>
}

type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v)
const str = (v: unknown) => (typeof v === 'string' ? v.trim() : typeof v === 'number' ? String(v) : '')
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)
export const CLOCK = /^([01]?\d|2[0-3]):[0-5]\d$/

export function readDrill(text: string): Read {
  const lines = new LineCounter()
  const doc = parseDocument(text, { lineCounter: lines, prettyErrors: false })
  const at = (path: (string | number)[]) => {
    for (let p = path; p.length; p = p.slice(0, -1)) {
      const node = doc.getIn(p, true) as { range?: [number, number, number] } | undefined
      if (node?.range) return lines.linePos(node.range[0]).line
    }
    return 1
  }
  if (doc.errors.length) return { problems: [{ line: lines.linePos(doc.errors[0].pos[0]).line, key: 'syntax', detail: doc.errors[0].code }] }
  const raw = doc.toJS() as unknown
  if (!isObj(raw) || raw.format !== FORMAT || !isMap(doc.contents)) return { problems: [{ line: at(['format']), key: 'format' }] }
  const problems: Problem[] = []
  const need = (v: unknown, what: string, path: (string | number)[]) => {
    if (!str(v)) problems.push({ line: at(path), key: 'missing', what })
    return str(v)
  }
  const list = (v: unknown) => (Array.isArray(v) ? v.filter(isObj) : [])
  const name = need(raw.name, 'name', ['name'])
  const clock = str(raw.clock) || '00:00'
  if (!CLOCK.test(clock)) problems.push({ line: at(['clock']), key: 'clock', value: clock })
  const roles: Role[] = list(raw.roles).map((r, i) => ({
    id: need(r.id, `roles[${i}].id`, ['roles', i]),
    name: str(r.name) || str(r.id),
    ...(r.you === true ? { you: true } : {}),
    ...(r.in === true ? { in: true } : {}),
    ...(Array.isArray(r.can) ? { can: r.can.map(str).filter(Boolean) } : {}),
  }))
  if (!roles.length) problems.push({ line: at(['roles']), key: 'missing', what: 'roles' })
  const scenes: Scene[] = list(raw.scenes).map((s, i) => {
    const end = str(s.end)
    return {
      id: need(s.id, `scenes[${i}].id`, ['scenes', i]),
      says: need(s.says, `scenes[${i}].says`, ['scenes', i]),
      ...(str(s.draw) ? { draw: str(s.draw) } : {}),
      ...(Array.isArray(s.injects) ? { injects: list(s.injects).map((x) => ({ ...(str(x.at) ? { at: str(x.at) } : {}), says: str(x.says) })) } : {}),
      ...(Array.isArray(s.choices)
        ? {
            choices: list(s.choices).map((c, k): Choice => ({
              label: need(c.label, `scenes[${i}].choices[${k}].label`, ['scenes', i, 'choices', k]),
              go: need(c.go, `scenes[${i}].choices[${k}].go`, ['scenes', i, 'choices', k]),
              ...(str(c.then) ? { then: str(c.then) } : {}),
              ...(str(c.runbook) ? { runbook: str(c.runbook) } : {}),
              ...(num(c.minutes) !== undefined ? { minutes: num(c.minutes) } : {}),
              ...(num(c.lost) !== undefined ? { lost: num(c.lost) } : {}),
              ...(str(c.calls) ? { calls: str(c.calls) } : {}),
              ...(str(c.needs) ? { needs: str(c.needs) } : {}),
              ...(c.notifies === true ? { notifies: true } : {}),
            })),
          }
        : {}),
      ...(end === 'resolved' || end === 'worse' ? { end } : end ? { end: 'resolved' as const } : {}),
    }
  })
  if (!scenes.length) problems.push({ line: at(['scenes']), key: 'missing', what: 'scenes' })
  const once = (what: string, ids: string[], path: (i: number) => (string | number)[]) => {
    const seen = new Set<string>()
    ids.forEach((id, i) => {
      if (id && seen.has(id)) problems.push({ line: at(path(i)), key: 'duplicate', what, id })
      seen.add(id)
    })
  }
  once('roles', roles.map((r) => r.id), (i) => ['roles', i, 'id'])
  once('scenes', scenes.map((s) => s.id), (i) => ['scenes', i, 'id'])
  const sceneIds = new Set(scenes.map((s) => s.id))
  const roleIds = new Set(roles.map((r) => r.id))
  const start = str(raw.start) || scenes[0]?.id || ''
  if (start && !sceneIds.has(start)) problems.push({ line: at(['start']), key: 'unknownScene', from: 'start', go: start })
  scenes.forEach((s, i) => {
    if (!s.end && !(s.choices ?? []).length) problems.push({ line: at(['scenes', i]), key: 'stuck', scene: s.id })
    ;(s.choices ?? []).forEach((c, k) => {
      if (c.go && !sceneIds.has(c.go)) problems.push({ line: at(['scenes', i, 'choices', k, 'go']), key: 'unknownScene', from: s.id, go: c.go })
      if (c.calls && !roleIds.has(c.calls)) problems.push({ line: at(['scenes', i, 'choices', k, 'calls']), key: 'unknownRole', scene: s.id, role: c.calls })
    })
  })
  const drill: Drill = {
    name,
    ...(str(raw.from) ? { from: str(raw.from) } : {}),
    ...(str(raw.about) ? { about: str(raw.about) } : {}),
    clock,
    ...(str(raw.impact) ? { impact: str(raw.impact) } : {}),
    ...(num(raw.call_minutes) !== undefined ? { call_minutes: num(raw.call_minutes) } : {}),
    roles,
    start,
    scenes,
    ...(Array.isArray(raw.gaps) ? { gaps: list(raw.gaps).map((g) => ({ says: str(g.says), ...(str(g.source) ? { source: str(g.source) } : {}) })).filter((g) => g.says) } : {}),
  }
  // the game must be able to end: some end reachable from the start
  if (!problems.length && !reachable(drill, drill.start).some((id) => drill.scenes.find((s) => s.id === id)?.end)) problems.push({ line: at(['start']), key: 'noEnd' })
  const drawLines: Record<string, number> = {}
  scenes.forEach((s, i) => {
    if (!s.draw) return
    const node = doc.getIn(['scenes', i, 'draw'], true) as { range?: [number, number, number]; type?: string } | undefined
    // a block (|) starts on the line after its key
    if (node?.range) drawLines[s.id] = lines.linePos(node.range[0]).line + (node.type === 'BLOCK_LITERAL' || node.type === 'BLOCK_FOLDED' ? 1 : 0)
  })
  return problems.length ? { problems } : { drill, problems, drawLines }
}

/** The scenes reachable from `from` by choices, in the order found. */
export function reachable(drill: Drill, from: string): string[] {
  const seen = new Set<string>()
  const queue = [from]
  while (queue.length) {
    const id = queue.shift()!
    if (seen.has(id)) continue
    seen.add(id)
    for (const c of drill.scenes.find((s) => s.id === id)?.choices ?? []) queue.push(c.go)
  }
  return [...seen]
}

/** A problem in a sentence, in English or Portuguese. */
export function problemText(p: Problem, lang: 'en' | 'pt' = 'en'): string {
  const pt = lang === 'pt'
  switch (p.key) {
    case 'syntax': return pt ? `não se lê como YAML (${p.detail})` : `does not read as YAML (${p.detail})`
    case 'format': return pt ? `«format» precisa ser ${FORMAT}` : `«format» must be ${FORMAT}`
    case 'missing': return pt ? `falta «${p.what}»` : `«${p.what}» is missing`
    case 'duplicate': return pt ? `${p.what}: o id «${p.id}» se repete` : `${p.what}: the id «${p.id}» is repeated`
    case 'unknownScene': return pt ? `«${p.from}» leva a «${p.go}», que não é uma cena` : `«${p.from}» goes to «${p.go}», which is not a scene`
    case 'unknownRole': return pt ? `uma escolha de «${p.scene}» chama «${p.role}», que não é um dos papéis` : `a choice of «${p.scene}» calls «${p.role}», which is not one of the roles`
    case 'stuck': return pt ? `a cena «${p.scene}» não é um fim e não tem escolha: o jogo trava nela` : `the scene «${p.scene}» is not an end and has no choice: the game would stop there`
    case 'noEnd': return pt ? 'nenhum fim se alcança a partir do começo' : 'no end can be reached from the start'
    case 'clock': return pt ? `o relógio «${p.value}» não é uma hora (HH:MM)` : `the clock «${p.value}» is not a time (HH:MM)`
  }
}
