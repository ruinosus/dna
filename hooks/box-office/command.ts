// Feature 2: /sim runs a recipe at once, with no model turn, and prints the median
// and the p10 to p90 range of each metric. The same numbers reach Claude as context.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import { check, diagLines, fmtMetric, metricName, metricValue, quant, runOne, seedsFor } from './core'
import { pathOf } from '../recipes/run'

const last = atom({ plugin: 'house-lights', key: 'last' } as const, null, { shape: 'last-1' })

const BUDGET_MS = 7000

function parseArgs(args: string) {
  const tokens = args.trim() ? args.trim().split(/\s+/) : []
  let path: string | undefined
  let seeds: number | undefined
  const sets: Record<string, number> = {}
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i]
    if (t === '--seeds') seeds = Math.max(1, Math.min(20, parseInt(tokens[++i] ?? '', 10) || 1))
    else if (t === '--set') {
      const [k, v] = String(tokens[++i] ?? '').split('=')
      if (k && v !== undefined) sets[k] = /%$/.test(v) ? parseFloat(v) / 100 : parseFloat(v)
    } else if (!path) path = t
  }
  return { path, seeds, sets }
}

async function loadRecipe($: EngineInterface, typed: string | undefined) {
  if (typed) {
    const path = await pathOf($, typed)
    const src = await $.fs.read(path).catch(() => undefined)
    return typeof src === 'string' ? { path, src } : { path, src: undefined }
  }
  const doc = await read($, last)
  return doc ? { path: doc.path, src: doc.src } : { path: undefined, src: undefined }
}

export function simCommand(on: On) {
  on('command.run', { command: 'sim' }, async ($, e) => {
    const { path, seeds, sets } = parseArgs(e.args)
    const doc = await loadRecipe($, path)
    if (!doc.path) return { text: `name a recipe, for example /sim examples/corner-cafe.sim` }
    if (doc.src === undefined) return { text: `could not read ${doc.path}` }

    const c = check(doc.src, sets)
    if (!c.ok) return { text: `${doc.path} has errors:\n` + diagLines(c).join('\n') }

    const unknown = Object.keys(sets).filter(k => !(k in c.model.knobs))
    const list = seedsFor(c.model, c.plan, seeds)
    const started = await $.clock.now()
    const values: number[][] = c.model.shows.map(() => [])
    let done = 0
    for (const s of list) {
      const res = runOne(c.plan, s)
      c.model.shows.forEach((m: any, i: number) => values[i]?.push(metricValue(m, res)))
      done++
      if ((await $.clock.now()) - started > BUDGET_MS) break
    }
    const ms = Math.round((await $.clock.now()) - started)
    const at = await $.clock.now()
    await update($, last, () => ({ path: doc.path as string, src: doc.src as string, at }))

    const knobs = c.model.knobOrder.map((k: string) => {
      const K = c.model.knobs[k]
      const v = k in sets ? sets[k] : K.init
      return `${k}=${K.pct ? Math.round(v * 100) + '%' : v}`
    })
    const rows = c.model.shows.map((m: any, i: number) => {
      const v = (values[i] ?? []).sort((a, b) => a - b)
      const f = (x: number) => fmtMetric(m, x, c.plan.currency)
      return `  ${metricName(m).padEnd(34)} ${f(quant(v, 0.5)).padStart(14)}   (${f(quant(v, 0.1))} to ${f(quant(v, 0.9))})`
    })
    const head = `${c.model.name} · ${done} run${done === 1 ? '' : 's'} · ${ms} ms` + (knobs.length ? ` · ${knobs.join(', ')}` : '')
    const notes = [
      ...(done < list.length ? [`stopped after ${done} of ${list.length} runs to stay within the time limit`] : []),
      ...(unknown.length ? [`ignored unknown controls: ${unknown.join(', ')}`] : []),
      ...c.warnings.map(d => `warn ${d.text}`),
    ]
    const text = [head, '  metric                             median           (p10 to p90)', ...rows, ...notes.map(n => '  ' + n)].join('\n')
    return { text, context: [`The person ran /sim on ${doc.path}. Results:\n${text}`] }
  })
}
