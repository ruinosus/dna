// What the three features share: the plugin's state, the recipe check and the runs.
import type { PreviewLang } from '../../types'
import { BO, SIMLANG } from './sim-core.js'
import type { Diag } from './sim-core.js'

// The state belongs to dna: the same name in each atom (guard.ts, command.ts, preview.tsx: the scan needs
// them literal, per file) and in types/index.d.ts.
export const PLUGIN = 'dna'
export const PANE = 'process-simulation-preview'


export type Checked = {
  ok: boolean
  lang: string
  errors: Diag[]
  warnings: Diag[]
  model: any
  plan: any
  flows: any
}

export const isSim = (path: string) => /\.sim$/i.test(path)

export function initialKnobs(model: any, overrides: Record<string, number> = {}) {
  const k: Record<string, number> = {}
  for (const name of model.knobOrder) k[name] = name in overrides ? overrides[name] : model.knobs[name].init
  return k
}

export function check(src: string, overrides: Record<string, number> = {}): Checked {
  const r = SIMLANG.parse(src)
  const diags: Diag[] = r.diags.slice()
  let plan: any = null
  let flows: any = null
  if (r.ok) {
    plan = SIMLANG.compile(r.model, initialKnobs(r.model, overrides))
    flows = SIMLANG.flows(r.model, plan)
    for (const x of flows.endless) diags.push({ sev: 'warn', text: SIMLANG.fmtMsg('endless', { x }, r.model.lang) })
    for (const ld of flows.loads) {
      if (ld.load > 1.001) {
        const step = plan.steps[ld.steps[0]].name
        diags.push({ sev: 'warn', text: SIMLANG.fmtMsg('unstable', { x: step, v: Math.round(ld.load * 100) + '%' }, r.model.lang) })
      }
    }
  }
  return {
    ok: r.ok,
    lang: r.model.lang,
    errors: diags.filter(d => d.sev === 'error'),
    warnings: diags.filter(d => d.sev !== 'error'),
    model: r.model,
    plan,
    flows,
  }
}

export function seedsFor(model: any, plan: any, n?: number): number[] {
  const expected = plan.statedPerMin * plan.openFrac * plan.horizon
  const count = n ?? (expected > 200000 ? 2 : expected > 50000 ? 3 : 5)
  return Array.from({ length: count }, (_, i) => model.seed * 1009 + i * 7919 + 1)
}

export function runOne(plan: any, seed: number) {
  const sim = new BO.Sim(plan, seed, {})
  sim.runUntil(plan.horizon)
  return sim.results()
}

export const metricValue = (m: any, res: any): number => BO.metric(m, res)
export const quant = (sorted: number[], p: number): number => BO.quant(sorted, p)

export function label(model: any, id: string, locale: PreviewLang): string {
  const L = model.labels || {}
  return (L[locale] && L[locale][id]) || (L.en && L.en[id]) || String(id).replace(/_/g, ' ')
}

export function fmtDuration(min: number): string {
  if (min < 1) return `${Math.round(min * 60)} s`
  if (min < 90) return `${min < 10 ? min.toFixed(1) : Math.round(min)} min`
  if (min < 48 * 60) return `${(min / 60).toFixed(1)} h`
  return `${(min / 1440).toFixed(1)} days`
}

export function fmtMetric(m: any, v: number, currency: string): string {
  if (m.kind === 'count') return Math.round(v).toLocaleString('en-US')
  if (m.kind === 'share' || m.kind === 'util') return `${(v * 100).toFixed(1)}%`
  if (m.kind === 'wait') return fmtDuration(v)
  if (m.kind === 'queue') return v < 10 ? v.toFixed(1) : Math.round(v).toLocaleString('en-US')
  return `${currency} ${Math.round(v).toLocaleString('en-US')}`
}

export function metricName(m: any): string {
  if (m.kind === 'count') return `count end ${m.x}`
  if (m.kind === 'share') return `share end ${m.x}`
  if (m.kind === 'wait') return `wait p${m.pn} at ${m.x}`
  if (m.kind === 'queue') return `queue ${m.x}`
  if (m.kind === 'util') return `utilization ${m.x}`
  return `cost per ${m.perName}`
}

export function diagLines(c: Checked): string[] {
  return [...c.errors.map(d => `error  ${d.text}`), ...c.warnings.map(d => `warn   ${d.text}`)]
}

export type Ran = { rows: string[]; done: number; total: number; ms: number }

/** Runs a checked recipe over its seeds, within the time budget, and gives a line per metric: the median and the p10 to
 * p90 range. /simulate and the preview's controls both run through here. */
export async function runMetrics(now: () => Promise<number>, c: Checked, seeds?: number, budgetMs = 7000): Promise<Ran> {
  const list = seedsFor(c.model, c.plan, seeds)
  const started = await now()
  const values: number[][] = c.model.shows.map(() => [])
  let done = 0
  for (const s of list) {
    const res = runOne(c.plan, s)
    c.model.shows.forEach((m: any, i: number) => values[i]?.push(metricValue(m, res)))
    done++
    if ((await now()) - started > budgetMs) break
  }
  const rows = c.model.shows.map((m: any, i: number) => {
    const v = (values[i] ?? []).sort((a, b) => a - b)
    const f = (x: number) => fmtMetric(m, x, c.plan.currency)
    return `  ${metricName(m).padEnd(34)} ${f(quant(v, 0.5)).padStart(14)}   (${f(quant(v, 0.1))} to ${f(quant(v, 0.9))})`
  })
  return { rows, done, total: list.length, ms: Math.round((await now()) - started) }
}

/** A control's value one step up or down: a tenth of its range (5 points for a share), whole for a count, kept in range. */
export function stepKnob(K: { min: number; max: number; pct: boolean }, v: number, dir: 1 | -1): number {
  const step = K.pct ? 0.05 : Math.max(1, Math.round((K.max - K.min) / 10))
  const next = Math.min(K.max, Math.max(K.min, v + dir * step))
  return K.pct ? Math.round(next * 100) / 100 : next
}

export const knobText = (K: { pct: boolean }, v: number) => (K.pct ? `${Math.round(v * 100)}%` : String(v))
