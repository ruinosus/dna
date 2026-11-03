// The evaluations of Copilot Studio's Evaluate tab, exported as CSV — «Evaluate <agent name> <date>.csv» (or the same
// in kebab-case, «evaluate-<agent-name>-<date>.csv»), a row per
// test, `result_1` (and `_2`, `_3`… for more methods) Pass or Fail. Only the counts are kept: who, when, how many
// passed, by method. What was asked, answered and explained is the client's conversation, and is never read into an
// output.
import type { AgentFacts } from './extract'
import { matcher, type Table } from './tables'

export interface EvalSet { agent: string; file: string; date?: string; total: number; passed: number; methods: { name: string; passed: number; total: number }[] }
export interface Evals { sets: EvalSet[]; unknown: { file: string; why: 'who' | 'format' }[] }

const base = (f: string) => f.split(/[\\/]/).pop() ?? f
/** Who and when, from the file's name: «Evaluate Bodega Azul - Pedidos 2026-10-30.csv» or
 * «evaluate-bodega-azul-pedidos-2026-10-30.csv» (a copy's « (1)» left out). */
function nameOf(file: string): { who: string; date?: string } {
  const s = base(file).replace(/\.csv$/i, '').replace(/\s*\(\d+\)$/, '').replace(/^Evaluate[\s_-]+/i, '')
  const m = /^(.*?)[\s_-]+(\d{4}-\d{2}-\d{2}|\d{1,2}[-_.]\d{1,2}[-_.]\d{2,4}|\d{8})$/.exec(s)
  return m ? { who: m[1], date: m[2] } : { who: s }
}

export function evalsFrom(files: { name: string; table: Table }[], agents: { id: string; schemaName?: string; displayName?: string }[]): Evals {
  const match = matcher(agents)
  const out: Evals = { sets: [], unknown: [] }
  for (const { name, table } of files) {
    const { who, date } = nameOf(name)
    const agent = match(who)
    if (!agent) {
      out.unknown.push({ file: name, why: 'who' })
      continue
    }
    const head = table.rows[0] ?? []
    // the methods: result_N, with testMethodType_N naming it
    const ns = head.flatMap((h) => /^result_(\d+)$/i.exec(h.trim())?.[1] ?? []).map(Number).sort((a, b) => a - b)
    if (!ns.length) {
      out.unknown.push({ file: name, why: 'format' })
      continue
    }
    const col = (t: string) => head.findIndex((h) => h.trim().toLowerCase() === t.toLowerCase())
    const rows = table.rows.slice(1).filter((r) => r.some((c) => c.trim()))
    const pass = (r: string[], n: number) => (r[col(`result_${n}`)] ?? '').trim().toLowerCase() === 'pass'
    const methods = ns.map((n) => {
      const named = rows.map((r) => (r[col(`testMethodType_${n}`)] ?? '').trim()).find(Boolean)
      return { name: named || `#${n}`, passed: rows.filter((r) => pass(r, n)).length, total: rows.length }
    })
    out.sets.push({ agent, file: name, ...(date ? { date } : {}), total: rows.length, passed: rows.filter((r) => ns.every((n) => pass(r, n))).length, methods })
  }
  return out
}

/** The agents with `eval:run` for each one that has an evaluation, the file as its source (a rule `has: "eval:*"`). */
export function withEvals(found: AgentFacts[], sets: EvalSet[]): AgentFacts[] {
  return found.map((a) => {
    const mine = sets.filter((s) => s.agent === a.id)
    return mine.length ? { ...a, facts: { ...a.facts, 'eval:run': mine.map((s) => ({ file: s.file, line: 1 })) } } : a
  })
}
