// Tables from outside the folder, with no model: a spreadsheet the team already keeps, the Power Platform admin
// center's inventory download, an export of Application Insights. The column that says which agent a row is about is
// found by its values (a schema name, a folder, a display name), not by its title. What a row declares becomes the
// changes --from proposes (d1, d2…); what fired becomes the telemetry of the run.
import type { Cast, Declared } from './cast'
import type { Fired } from './compare'
import type { Change, SheetRows } from './fromSheets'
import { normal } from './telemetry'

export type Table = SheetRows
interface Who { id: string; schemaName?: string; displayName?: string }

/** A CSV as rows of text: UTF-8 with or without a BOM, «,» or «;» (the one the first line has more of), quotes with
 * «""» inside, and lines that end in \n or \r\n. */
export function readCsv(text: string, name: string): Table {
  const s = text.replace(/^﻿/, '')
  const first = s.slice(0, s.search(/\r?\n|$/))
  const count = (c: string) => first.split('"').filter((_, i) => i % 2 === 0).join('').split(c).length
  const sep = count(';') > count(',') ? ';' : ','
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < s.length; i++) {
    const c = s[i]
    if (quoted) {
      if (c === '"' && s[i + 1] === '"') cell += s[++i]
      else if (c === '"') quoted = false
      else cell += c
    } else if (c === '"') quoted = true
    else if (c === sep) {
      row.push(cell)
      cell = ''
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && s[i + 1] === '\n') i++
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else cell += c
  }
  if (cell || row.length) rows.push([...row, cell])
  return { name, rows }
}

/** Which agent of the folder a value names: its schema name, its folder or its display name, with no case, accents or
 * separators. */
export function matcher(agents: Who[]): (value: string) => string | undefined {
  const by = new Map<string, string>()
  for (const a of agents) for (const n of [a.schemaName, a.id, a.displayName]) if (n && normal(n)) by.set(normal(n), a.id)
  return (value) => by.get(normal(value))
}

type Column = { at: number } | { problem: 'none' | 'tie' | 'header'; titles: string[] }
/** The column of the agent: the one `given` names, or the one whose values name the most agents of the folder (at least
 * two, or the one there is). */
export function agentColumn(t: Table, match: (v: string) => string | undefined, agents: number, given?: string): Column {
  const head = t.rows[0] ?? []
  if (given) {
    const at = head.findIndex((h) => normal(h) === normal(given))
    return at >= 0 ? { at } : { problem: 'header', titles: head }
  }
  const named = head.map((_, c) => new Set(t.rows.slice(1).map((r) => match(r[c] ?? '')).filter(Boolean)).size)
  const most = Math.max(0, ...named)
  const best = named.flatMap((n, c) => (n === most ? [c] : []))
  if (most < Math.min(2, agents)) return { problem: 'none', titles: head }
  // two columns that name the same agent on every row (the inventory's name and schema name) are one answer
  const agree = t.rows.slice(1).every((r) => new Set(best.map((c) => match(r[c] ?? '')).filter(Boolean)).size <= 1)
  if (best.length > 1 && !agree) return { problem: 'tie', titles: best.map((c) => head[c]) }
  return { at: best[0] }
}

// the words a spreadsheet uses for the facts agent-review knows by name: the team that answers for it (declared:team, the
// team spreadsheet's «Dono»), the owner of record (declared:owner, the inventory's Owner) and the KPI (declared:kpi)
const ALIASES: Record<string, string> = { dono: 'team', responsavel: 'team', equipe: 'team', time: 'team', squad: 'team', proprietario: 'owner', 'owner-name': 'owner', indicador: 'kpi', kpis: 'kpi' }
/** «Linha de base» → linha-de-base, «Dono» → owner: the key of what a column declares. */
export const slug = (title: string) => {
  const s = title.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return ALIASES[s] ?? s
}
const TYPE = new Set(['itemtype', 'tipodoitem', 'tipo', 'type'])
const AGENT_TYPES = new Set(['agent', 'agente', 'agents', 'agentes', 'copilotstudioagent', 'microsoftcopilotstudio/agents'])

export interface Imported { changes: Change[]; /** Rows of agents that are not in the folder. */ unmatched: { line: number; value: string }[]; problem?: Extract<Column, { problem: string }> }

/** What a table declares about the agents of the folder, as changes to the cast file: a column becomes
 * declared:<column>, its source the file and the line. Rows of what is not an agent (the inventory's apps and flows) are
 * left out; a value already in the cast file is no change; nothing is removed. */
export function declaredFrom(t: Table, agents: Who[], cast: Cast, o: { file: string; lang: 'en' | 'pt'; agentColumn?: string }): Imported {
  const match = matcher(agents)
  const col = agentColumn(t, match, agents.length, o.agentColumn)
  if (!('at' in col)) return { changes: [], unmatched: [], problem: col }
  const head = t.rows[0]
  const type = head.findIndex((h) => TYPE.has(normal(h)))
  const where = (line: number) => `${o.file}${t.name ? ` › ${t.name}` : ''} › ${o.lang === 'pt' ? 'linha' : 'line'} ${line}`
  const now = new Map<string, Declared>()
  const unmatched: Imported['unmatched'] = []
  t.rows.slice(1).forEach((row, i) => {
    if (!row.some((c) => c.trim())) return
    if (type >= 0 && row[type]?.trim() && !AGENT_TYPES.has(normal(row[type]))) return
    const value = (row[col.at] ?? '').trim()
    const agent = match(value)
    if (!agent) return unmatched.push({ line: i + 2, value })
    head.forEach((h, c) => {
      const v = (row[c] ?? '').trim()
      // the agent's own column, and any other that names the same agent (the inventory's schema name), say who, not what
      if (c === col.at || c === type || !v || !slug(h) || match(v) === agent) return
      now.set(`${agent} ${slug(h)}`, { agent, key: slug(h), value: v, source: where(i + 2) })
    })
  })
  const changes: Change[] = []
  let n = 0
  for (const d of now.values()) {
    const before = cast.declared.find((x) => x.agent === d.agent && x.key === d.key)
    if (!before) changes.push({ key: `d${++n}`, kind: 'declared', op: 'add', after: d })
    else if (before.value !== d.value || before.source !== d.source) changes.push({ key: `d${++n}`, kind: 'declared', op: 'set', before, after: d })
  }
  return { changes, unmatched }
}

/** The changes of several tables as one list: where two say the same key of the same agent, the later one holds; the keys
 * are numbered again (d1, d2…), the same on every run with the same tables. */
export function mergeDeclared(changes: Change[]): Change[] {
  const last = new Map<string, Change>()
  for (const c of changes) if (c.kind === 'declared' && c.after) last.set(`${c.after.agent} ${c.after.key}`, c)
  return [...last.values()].map((c, i) => ({ ...c, key: `d${i + 1}` }))
}

const EVENT = new Set(['evento', 'event', 'eventname', 'name', 'nome'])
const COUNT = new Set(['vezes', 'count', 'contagem', 'times', 'total'])

/** What fired, from an export of Application Insights: the agent (by its values), the event and the times (a column
 * named so, or 1 a row). Rows of agents not in the folder are left out. */
export function firedFrom(t: Table, agents: Who[], o: { file: string; days: number; agentColumn?: string }): Fired | { problem: Extract<Column, { problem: string }> | { problem: 'event'; titles: string[] } } {
  const match = matcher(agents)
  const col = agentColumn(t, match, agents.length, o.agentColumn)
  if (!('at' in col)) return { problem: col }
  const head = t.rows[0]
  const event = head.findIndex((h, c) => c !== col.at && EVENT.has(normal(h)))
  if (event < 0) return { problem: { problem: 'event', titles: head } }
  const times = head.findIndex((h) => COUNT.has(normal(h)))
  const rows: Fired['rows'] = []
  t.rows.slice(1).forEach((row, i) => {
    const agent = match(row[col.at] ?? '')
    const name = (row[event] ?? '').trim()
    if (!agent || !name) return
    const count = times >= 0 ? Number((row[times] ?? '').replace(/[^\d]/g, '')) || 0 : 1
    rows.push({ agent, event: name, count, line: i + 2 })
  })
  return { days: o.days, file: o.file, rows }
}
