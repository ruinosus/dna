// Feature 2: /sim runs a recipe at once, with no model turn, and prints the median
// and the p10 to p90 range of each metric. The same numbers reach Claude as context.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import { check, diagLines, knobText, runMetrics } from './core'
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
    const r = await runMetrics(() => $.clock.now(), c, seeds, BUDGET_MS)
    const at = await $.clock.now()
    await update($, last, () => ({ path: doc.path as string, src: doc.src as string, at }))

    const knobs = c.model.knobOrder.map((k: string) => `${k}=${knobText(c.model.knobs[k], k in sets ? sets[k]! : c.model.knobs[k].init)}`)
    const head = `${c.model.name} · ${r.done} run${r.done === 1 ? '' : 's'} · ${r.ms} ms` + (knobs.length ? ` · ${knobs.join(', ')}` : '')
    const notes = [
      ...(r.done < r.total ? [`stopped after ${r.done} of ${r.total} runs to stay within the time limit`] : []),
      ...(unknown.length ? [`ignored unknown controls: ${unknown.join(', ')}`] : []),
      ...c.warnings.map(d => `warn ${d.text}`),
    ]
    const text = [head, '  metric                             median           (p10 to p90)', ...r.rows, ...notes.map(n => '  ' + n)].join('\n')
    return { text, context: [`The person ran /sim on ${doc.path}. Results:\n${text}`] }
  })
}
