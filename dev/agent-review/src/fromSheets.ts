// The workbook back: what a person filled in Excel — lines in «Declared», a decision (and its scope and why) in
// «Patterns» — as changes to the review file, each with a short key (d1, d2… for declared, p1… for decisions) so the
// person takes the ones they keep. Sheets and columns are found by their name in either language.
import type { Cast, Decision, Declared } from './cast'
import type { SheetKey } from './workbook'
import { SHEET_WORDS } from './words'

export interface SheetRows { name: string; rows: string[][] }
export type Change =
  | { key: string; kind: 'declared'; op: 'add' | 'set' | 'remove'; before?: Declared; after?: Declared }
  | { key: string; kind: 'decision'; op: 'add' | 'set' | 'remove'; before?: Decision; after?: Decision }

const norm = (s: unknown) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toLowerCase()
const both = Object.values(SHEET_WORDS)
/** The sheet of `key`, by its name in either language. */
const sheetOf = (sheets: SheetRows[], key: SheetKey) => sheets.find((s) => both.some((w) => norm(w[key]) === norm(s.name)))
/** A row's cell by its column's title in either language. */
function reader(s: SheetRows | undefined, ...fields: (keyof (typeof SHEET_WORDS)['en'])[]) {
  const cols = fields.map((f) => s?.rows[0]?.findIndex((t) => both.some((w) => norm(w[f]) === norm(t))) ?? -1)
  return (row: string[]) => cols.map((c) => (c < 0 ? '' : String(row[c] ?? '').trim()))
}
/** «aceito», «accepted» → accepted; «plataforma», «platform» → platform. */
const wordOf = <T extends string>(text: string, pairs: [T, keyof (typeof SHEET_WORDS)['en']][]) => pairs.find(([, f]) => both.some((w) => norm(w[f]) === norm(text)))?.[0]
const filled = (rows: string[][]) => rows.slice(1).filter((r) => r.some((c) => String(c ?? '').trim()))
const same = (a: object | undefined, b: object | undefined) => JSON.stringify(a) === JSON.stringify(b)

/** `typeNames`: the profile's types (id → name), so a scope «tipo:<name>» comes back as type:<id>. */
export function fromSheets(cast: Cast, sheets: SheetRows[], typeNames: Record<string, string> = {}): { changes: Change[]; problems: string[] } {
  const changes: Change[] = []
  const problems: string[] = []

  const ds = sheetOf(sheets, 'declared')
  if (ds) {
    const read = reader(ds, 'agent', 'key', 'value', 'source')
    const now: Declared[] = []
    filled(ds.rows).forEach((row, i) => {
      const [agent, key, value, source] = read(row)
      // the sheet's own column titles say what is missing
      if (!agent || !key) problems.push(`${ds.name}, ${i + 2}: «${read(ds.rows[0])[agent ? 1 : 0]}» ?`)
      else now.push({ agent, key, value, source })
    })
    const id = (d: Declared) => `${d.agent} ${d.key}`
    let n = 0
    for (const d of now) {
      const before = cast.declared.find((x) => id(x) === id(d))
      if (!before) changes.push({ key: `d${++n}`, kind: 'declared', op: 'add', after: d })
      else if (!same(before, d)) changes.push({ key: `d${++n}`, kind: 'declared', op: 'set', before, after: d })
    }
    for (const before of cast.declared) if (!now.some((d) => id(d) === id(before))) changes.push({ key: `d${++n}`, kind: 'declared', op: 'remove', before })
  }

  const ps = sheetOf(sheets, 'patterns')
  if (ps) {
    const read = reader(ps, 'key', 'scope', 'decision', 'why')
    let n = 0
    for (const row of filled(ps.rows)) {
      const [key, scopeText, decisionText, why] = read(row)
      if (!key) continue
      const before = cast.decisions.find((d) => d.key === key)
      if (!decisionText) {
        if (before) changes.push({ key: `p${++n}`, kind: 'decision', op: 'remove', before })
        continue
      }
      const status = wordOf(decisionText, [['accepted', 'accept'], ['rejected', 'reject']])
      // «tipo:orientação», «type:guidance»: a type by its name or id
      const typed = /^(tipo|type)\s*:\s*(.+)$/i.exec(scopeText)
      const typeId = typed ? Object.entries(typeNames).find(([id, name]) => norm(name) === norm(typed[2]) || norm(id) === norm(typed[2]))?.[0] : undefined
      const scope = typed ? (typeId ? (`type:${typeId}` as const) : undefined) : wordOf(scopeText, [['platform', 'platform'], ['specialist', 'specialist'], ['orchestrator', 'orchestrator']])
      if (!status) problems.push(`${ps.name}, ${key}: «${decisionText}» — ${both.map((w) => `${w.accept}/${w.reject}`).join(', ')}`)
      else if (!scope) problems.push(`${ps.name}, ${key}: «${scopeText}» — ${both.map((w) => `${w.platform}/${w.specialist}/${w.orchestrator}`).join(', ')}`)
      else {
        const after: Decision = { key, status, scope, why }
        if (!before) changes.push({ key: `p${++n}`, kind: 'decision', op: 'add', after })
        else if (!same(before, after)) changes.push({ key: `p${++n}`, kind: 'decision', op: 'set', before, after })
      }
    }
    // a decision about a key that is not in the sheet (no longer a pattern) is kept: the sheet says nothing about it
  }
  return { changes, problems }
}

/** The cast with the changes whose keys were taken. */
export function applyChanges(cast: Cast, changes: Change[], keys: string[]): Cast {
  const next: Cast = { ...cast, declared: [...cast.declared], decisions: [...cast.decisions] }
  for (const c of changes.filter((x) => keys.includes(x.key))) {
    if (c.kind === 'declared') {
      const id = (d: Declared) => `${d.agent} ${d.key}`
      const at = c.before ? next.declared.findIndex((d) => id(d) === id(c.before!)) : -1
      if (c.op === 'add') next.declared.push(c.after!)
      else if (c.op === 'set') next.declared[at] = c.after!
      else next.declared.splice(at, 1)
    } else {
      const at = c.before ? next.decisions.findIndex((d) => d.key === c.before!.key) : -1
      if (c.op === 'add') next.decisions.push(c.after!)
      else if (c.op === 'set') next.decisions[at] = c.after!
      else next.decisions.splice(at, 1)
    }
  }
  return next
}
