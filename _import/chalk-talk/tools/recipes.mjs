// The example recipes the tools draw (the gallery, the snapshots), in any of the skill's forms: JSON, text (.chalk) or a
// Mermaid flowchart (.mmd) — read with the skill's own contract and converter.
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { parseChalk, PROP_ALIASES, PROP_NAMES, validateScene } from '../skills/chalk-talk/scripts/contract.mjs'

const PROPS = [...PROP_NAMES, ...Object.keys(PROP_ALIASES)]

/** Every recipe file in `dir`, as { file, scene } (file without its extension). */
export async function recipesIn(dir) {
  const out = []
  for (const f of readdirSync(dir).filter((f) => /\.(json|chalk|mmd)$/.test(f)).sort()) {
    const text = readFileSync(join(dir, f), 'utf8')
    const raw = f.endsWith('.json') ? JSON.parse(text)
      : f.endsWith('.chalk') ? parseChalk(text, PROPS)
        : await (await import('../skills/chalk-talk/scripts/mermaid.mjs')).fromMermaid(text)
    out.push({ file: f.replace(/\.[^.]+$/, ''), source: f, scene: validateScene(raw) })
  }
  return out
}
