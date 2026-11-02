// The profile's markers over the agents' texts — a fact `text:<id>` where the pattern is found, or `text:<id>=<value>`
// with the value it captured — and two built in: the domain of each link in the instructions
// (`text:link-domain:<host>`) and an e-mail (`text:email`). The findings: agents of a role that set the same marker in
// different ways («unify?»), and an agent that sets it more than once («which one holds?»). Text, not meaning.
import type { AgentFacts, Facts, Text } from './extract'
import type { Marker, Role } from './profile'

export type MarkerFinding =
  | { kind: 'values'; marker: Marker; role: Role; byValue: Record<string, string[]> }
  | { kind: 'twice'; marker: Marker; agent: string; values: string[] }

const URL = /https?:\/\/([^\s/)\]>"'«»]+)/gi
const EMAIL = /[\w.+-]+@[\w-]+(\.[\w-]+)+/g
const lineAt = (t: Text, index: number) => t.line + (t.text.slice(0, index).match(/\n/g)?.length ?? 0)
const clean = (v: string) => v.toLowerCase().replace(/\s+/g, ' ').trim()

/** The markers' facts of each agent, and the values each set per marker (in the order found, without repeats). */
export function markersOf(agents: AgentFacts[], markers: Marker[]): { facts: Record<string, Facts>; values: Record<string, Record<string, string[]>> } {
  const facts: Record<string, Facts> = {}
  const values: Record<string, Record<string, string[]>> = {}
  for (const a of agents) {
    const f: Facts = (facts[a.id] = {})
    const v: Record<string, string[]> = (values[a.id] = {})
    const add = (key: string, t: Text, index: number) => (f[key] ??= []).push({ file: t.file, line: lineAt(t, index) })
    for (const t of a.texts) {
      for (const m of markers.filter((x) => x.in === 'all' || x.in === t.source)) {
        for (const hit of t.text.matchAll(new RegExp(m.pattern, 'gi'))) {
          if (!m.value) {
            add(`text:${m.id}`, t, hit.index!)
            continue
          }
          const value = clean(m.value.replace(/\$(\d)/g, (_, n: string) => hit[Number(n)] ?? ''))
          if (!value) continue
          add(`text:${m.id}=${value}`, t, hit.index!)
          if (!(v[m.id] ??= []).includes(value)) v[m.id].push(value)
        }
      }
      if (t.source !== 'instructions') continue
      for (const hit of t.text.matchAll(URL)) add(`text:link-domain:${hit[1].toLowerCase().replace(/[.,;:]+$/, '')}`, t, hit.index!)
      for (const hit of t.text.matchAll(EMAIL)) add('text:email', t, hit.index!)
    }
    // a key seen twice in the same place is one fact
    for (const [k, s] of Object.entries(f)) f[k] = s.filter((x, i) => s.findIndex((y) => y.file === x.file && y.line === x.line) === i)
  }
  return { facts, values }
}

/** Agents of a role that set a marker with a value in more than one way; an agent that sets it twice. */
export function markerFindings(values: Record<string, Record<string, string[]>>, markers: Marker[], roles: Record<string, Role>): MarkerFinding[] {
  const out: MarkerFinding[] = []
  for (const m of markers.filter((x) => x.value)) {
    for (const role of ['specialist', 'orchestrator'] as Role[]) {
      const byValue: Record<string, string[]> = {}
      for (const [agent, v] of Object.entries(values)) if (roles[agent] === role) for (const value of v[m.id] ?? []) (byValue[value] ??= []).push(agent)
      if (Object.keys(byValue).length > 1) out.push({ kind: 'values', marker: m, role, byValue })
    }
    for (const [agent, v] of Object.entries(values)) if ((v[m.id] ?? []).length > 1) out.push({ kind: 'twice', marker: m, agent, values: v[m.id] })
  }
  return out
}
