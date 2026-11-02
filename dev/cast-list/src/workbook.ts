// The comparison as a workbook: Summary, Matrix (a row per fact, a column per agent: ● has it, × is off a pattern,
// ◐ declared), Patterns (with Scope, Decision and Why to fill in), Off pattern, Gaps, Conflicts, Cast, Evidence (file
// and line of every fact), Declared (to fill in) — and Not understood, when something was not. Sheets of rows the
// platform's xlsx writer turns into an .xlsx; fromSheets reads Patterns and Declared back.
import type { Sheet as LibSheet, Value } from '@lib/ways/workbook'
import { xlsx } from '@lib/ways/xlsx'
import type { Cast } from './cast'
import type { Result } from './compare'
import { DIMENSIONS, dimensionOf, labelOf, type Dimension, type Lang } from './labels'
import { groupPatterns, type Look } from './review'
import { SHEET_WORDS } from './words'

export type SheetKey = 'summary' | 'matrix' | 'patterns' | 'off' | 'gaps' | 'conflicts' | 'agents' | 'evidence' | 'declared' | 'unknown'
/** A sheet of rows; the xlsx writer reads its name, columns, rows and header. */
export interface Sheet extends Omit<LibSheet, 'key'> { key: SheetKey }
/** The .xlsx of these sheets (the platform's writer: its own `key` names only the platform's sheets). */
export const workbookFile = (sheets: Sheet[]): Uint8Array => xlsx(sheets as unknown as LibSheet[])

const HEAD = { bold: true, fill: 'E8EEF7' }
const HAS = { v: '●', fill: 'DDF3E6', center: true }
const OFF = { v: '×', fill: 'FFD5CC', center: true, bold: true }
const SAID = { v: '◐', fill: 'FFF3C4', center: true }
const ORDER = Object.keys(DIMENSIONS) as Dimension[]

export function workbookOf(r: Result, looks: Look[], cast: Cast, lang: Lang = 'en'): Sheet[] {
  const w = SHEET_WORDS[lang]
  const sheet = (key: SheetKey, titles: [string, number][], rows: Value[][]): Sheet => ({
    key, name: w[key], header: true, columns: titles.map(([title, width]) => ({ title, width })), rows: [titles.map(([v]) => ({ v, ...HEAD })), ...rows],
  })
  const role = (id: string) => w[r.roles[id]]
  const scope = (s: string) => w[s as 'platform']
  const label = (k: string) => labelOf(k, lang, r.names)
  // the orchestrators first, then the specialists, each by name
  const agents = [...r.agents].sort((a, b) => (a.role === b.role ? a.id.localeCompare(b.id) : a.role === 'orchestrator' ? -1 : 1))
  const keys = [...new Set([...agents.flatMap((a) => Object.keys(a.facts)), ...r.patterns.map((p) => p.key)])]
    .sort((a, b) => ORDER.indexOf(dimensionOf(a)) - ORDER.indexOf(dimensionOf(b)) || a.localeCompare(b))
  const off = new Set(r.offPattern.map((o) => `${o.agent} ${o.key}`))
  const n = (role: string) => r.agents.filter((a) => a.role === role).length

  const summary: Sheet = {
    key: 'summary', name: w.summary, header: false, columns: [{ title: '', width: 28 }, { title: '', width: 100 }],
    rows: [
      [{ v: r.name ?? w.title, bold: true }, ''],
      [{ v: w.privacy, color: 'B42318' }, ''],
      [w.count.agents, r.agents.length], [w.count.orchestrators, n('orchestrator')], [w.count.specialists, n('specialist')],
      [w.count.patterns, r.patterns.length], [w.count.off, new Set(r.offPattern.map((o) => o.agent)).size], [w.count.gaps, r.gaps.length],
      [w.count.conflicts, r.conflicts.length], [w.count.solos, looks.filter((l) => l.key === 'solo').length],
      ['', ''],
      [{ v: looks.length ? w.look : w.nothing, bold: true }, ''],
      ...looks.map((l): Value[] => ['', { v: l[lang], wrap: true }]),
    ],
  }
  const matrix = sheet('matrix', [[w.dimension, 18], [w.fact, 40], [w.key, 34], ...agents.map((a): [string, number] => [a.id, 14])],
    keys.map((k) => [DIMENSIONS[dimensionOf(k)][lang], label(k), k, ...agents.map((a): Value => (k in a.facts ? (k.startsWith('declared:') ? SAID : HAS) : off.has(`${a.id} ${k}`) ? OFF : ''))]))
  const { look, everyone } = groupPatterns(r)
  const patterns = sheet('patterns', [[w.key, 34], [w.fact, 40], [w.scope, 14], [w.role, 14], [w.share, 10], [w.have, 50], [w.lack, 40], [w.decision, 12], [w.why, 50]],
    [...look, ...everyone].map((p) => {
      const lacking = r.offPattern.filter((o) => o.key === p.key).map((o) => o.agent)
      return [p.key, label(p.key), scope(p.scope), w[p.role], `${Math.round(p.share * 100)}%`, p.agents.join(', '), lacking.join(', '),
        p.decision ? w[p.decision.status === 'accepted' ? 'accept' : 'reject'] : '', p.decision?.why ?? '']
    }))
  const offSheet = sheet('off', [[w.agent, 24], [w.role, 14], [w.missing, 44], [w.key, 34], [w.scope, 14], [w.accepted, 14]],
    r.offPattern.map((o) => [o.agent, role(o.agent), label(o.key), o.key, scope(o.scope), r.patterns.find((p) => p.key === o.key)?.decision?.status === 'accepted' ? w.yes : '']))
  const gaps = sheet('gaps', [[w.rule, 16], [w.says, 50], [w.role, 14], [w.notMet, 60]], r.gaps.map((g) => [g.rule.id, g.rule.says, g.rule.role ? w[g.rule.role] : '', g.agents.join(', ')]))
  const conflicts = sheet('conflicts', [[w.agent, 24], [w.fact, 40], [w.key, 34], [w.declared, 20], [w.source, 40], [w.inYaml, 12]],
    r.conflicts.map((c) => [c.agent, label(c.key), c.key, c.declared, c.source, c.observed ? w.yes : w.no]))
  const cast_ = sheet('agents', [[w.agent, 24], [w.name, 32], [w.role, 14], [w.facts, 8], [w.off, 44], [w.alone, 44], [w.children, 24], [w.unknown, 12]],
    agents.map((a) => [a.id, a.displayName ?? '', w[a.role], Object.keys(a.facts).length,
      r.offPattern.filter((o) => o.agent === a.id).map((o) => label(o.key)).join('; '),
      r.solos.filter((s) => s.agents[0] === a.id).map((s) => label(s.key)).join('; '),
      a.children.map((c) => c.name).join(', '), r.unknown.filter((u) => u.agent === a.id).length || '']))
  const evidence = sheet('evidence', [[w.agent, 30], [w.fact, 40], [w.key, 34], [w.file, 50], [w.line, 8]],
    agents.flatMap((a) => [{ who: a.id, facts: a.facts }, ...a.children.map((c) => ({ who: `${a.id} › ${c.name}`, facts: c.facts }))])
      .flatMap(({ who, facts }) => Object.entries(facts).sort(([x], [y]) => x.localeCompare(y)).flatMap(([k, sources]) => sources.map((s): Value[] => [who, label(k), k, s.file, s.line ?? '']))))
  const declared = sheet('declared', [[w.agent, 24], [w.key, 34], [w.value, 40], [w.source, 40]], cast.declared.map((d) => [d.agent, d.key, d.value, d.source]))
  const sheets = [summary, matrix, patterns, offSheet, gaps, conflicts, cast_, evidence, declared]
  if (r.unknown.length) sheets.push(sheet('unknown', [[w.agent, 24], [w.file, 50], [w.why, 40], [w.kind, 24]], r.unknown.map((u) => [u.agent, u.file, w.why_[u.why], u.kind ?? ''])))
  return sheets
}
