// The recipes' guard: every recipe of a skill Claude writes or edits — a way of working, a service blueprint, an
// incident drill, a visual-explainer lesson, an solution solution (its own format only: the pieces are checked by
// /solution) — is checked first by that skill's own script (its --check, or visual-explainer's build
// with no review), on a copy of the new text in a folder of its own, and refused with the script's messages when it
// breaks its format, so Claude fixes it and writes again. A way or a blueprint that passes is kept for the preview pane
// (hooks/previews/), which opens on the first one written in a session. The .sim recipes have their own guard
// (hooks/process-simulation/). Anything else passes untouched. It fails open, in its own code: if the check cannot run (no
// node, a timeout), the write goes through.
import { atom, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import { PREVIEW_PANE } from '../previews/draw'
import { problemLines, runOnCopy } from './run'
import { PLUGIN, afterEdit } from './text'

const recipe = atom({ plugin: 'dna', key: 'recipe' } as const, null, { shape: 'recipe-1' })

export type Kind = 'way' | 'blueprint'
type Recipe = { what: string; skill: string; kind?: Kind; args: (file: string, dir: string) => string[] }
const RECIPES: { test: RegExp; recipe: Recipe }[] = [
  { test: /\.way\.ya?ml$/i, recipe: { what: 'way of working', skill: 'way-of-working', kind: 'way', args: (f) => [f, '--check', '--json'] } },
  { test: /\.blueprint\.ya?ml$/i, recipe: { what: 'service blueprint', skill: 'service-blueprint', kind: 'blueprint', args: (f) => [f, '--check', '--json'] } },
  { test: /\.drill\.ya?ml$/i, recipe: { what: 'incident drill', skill: 'incident-drill', args: (f) => [f, '--check'] } },
  { test: /\.solution\.ya?ml$/i, recipe: { what: 'solution', skill: 'solution', args: (f) => [f, '--check', '--format'] } },
  { test: /\.chalk$/i, recipe: { what: 'visual-explainer lesson', skill: 'visual-explainer', args: (f, dir) => [f, `${dir}/out.html`, '--no-review'] } },
  { test: /\.json$/i, recipe: { what: 'visual-explainer lesson', skill: 'visual-explainer', args: (f, dir) => [f, `${dir}/out.html`, '--no-review'] } },
]

/** The recipe a file is, by its name — and, for a .json, only a visual-explainer recipe (a title and steps), never any JSON. */
export function recipeOf(path: string, text: string): Recipe | undefined {
  const hit = RECIPES.find((r) => r.test.test(path))
  if (!hit) return undefined
  if (/\.json$/i.test(path)) {
    try {
      const j = JSON.parse(text)
      if (!j || typeof j !== 'object' || typeof j.title !== 'string' || !Array.isArray(j.steps)) return undefined
    } catch {
      return undefined // not JSON yet: not a recipe we can tell
    }
  }
  return hit.recipe
}

export type Checked = { problems: string[]; read?: unknown }
/** The skill's own check of `text`: its problems, and for a way or a blueprint what it read; undefined if it cannot run. */
export async function checkRecipe($: EngineInterface, path: string, text: string, r: Recipe): Promise<Checked | undefined> {
  const ran = await runOnCopy($, r.skill, path, text, r.args)
  if (ran.exitCode === 1) return { problems: problemLines(ran, path) }
  if (ran.exitCode !== 0) return undefined // bad arguments or another failure: not the recipe's fault
  if (!r.kind) return { problems: [] }
  try {
    return { problems: [], read: JSON.parse(ran.stdout) }
  } catch {
    return { problems: [] }
  }
}

let opened = false
/** Keeps what was read for the preview pane, and opens it the first time in a session. */
export async function showRecipe($: EngineInterface, path: string, kind: Kind, read: unknown) {
  const at = await $.clock.now()
  await update($, recipe, () => ({ path, kind, read, at }))
  if (!opened) {
    opened = true
    void $.ui.open({ id: PREVIEW_PANE, title: kind === 'way' ? 'Way of working' : 'Service blueprint' })
  }
}

async function judge($: EngineInterface, path: string, text: string, go: () => Promise<any>) {
  const r = recipeOf(path, text)
  if (!r) return go()
  const checked = await checkRecipe($, path, text, r).catch(() => undefined)
  if (checked?.problems.length) {
    return { deny: `${PLUGIN}: ${path} is not a valid ${r.what} yet (${r.skill}'s check). Fix these and write it again:\n${checked.problems.join('\n')}` }
  }
  const ran = await go()
  if (r.kind && checked?.read && ran && ran.deny === undefined && ran.isError !== true) await showRecipe($, path, r.kind, checked.read).catch(() => undefined)
  return ran
}

export function recipesGuard(on: On) {
  on('tool.call', { tool: 'Write' }, async ($, e, next) => judge($, e.file_path, e.content, () => next(e)))
  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    if (!RECIPES.some((r) => r.test.test(e.file_path))) return next(e)
    const after = await afterEdit($, e).catch(() => undefined)
    return after === undefined ? next(e) : judge($, e.file_path, after, () => next(e))
  })
}
