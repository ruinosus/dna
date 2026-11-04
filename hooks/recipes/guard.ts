// The recipes' guard: every recipe of a skill Claude writes or edits — a way of working, a service blueprint, an
// incident drill, a chalk-talk lesson — is checked first by that skill's own script (its --check, or chalk-talk's build
// with no review), on a copy of the new text in a folder of its own, and refused with the script's messages when it
// breaks its format, so Claude fixes it and writes again. The .sim recipes have their own guard (hooks/box-office/).
// Anything else passes untouched. It fails open, in its own code: if the check cannot run (no node, a timeout), the
// write goes through.
import type { EngineInterface, On } from 'claude-code'

import { PLUGIN, afterEdit } from './text'

type Recipe = { what: string; skill: string; args: (file: string, out: string) => string[] }
const RECIPES: { test: RegExp; recipe: Recipe }[] = [
  { test: /\.way\.ya?ml$/i, recipe: { what: 'way of working', skill: 'gates-and-handoffs', args: (f) => [f, '--check'] } },
  { test: /\.blueprint\.ya?ml$/i, recipe: { what: 'service blueprint', skill: 'service-blueprint', args: (f) => [f, '--check'] } },
  { test: /\.drill\.ya?ml$/i, recipe: { what: 'incident drill', skill: 'dress-rehearsal', args: (f) => [f, '--check'] } },
  { test: /\.chalk$/i, recipe: { what: 'chalk-talk lesson', skill: 'chalk-talk', args: (f, out) => [f, out, '--no-review'] } },
  { test: /\.json$/i, recipe: { what: 'chalk-talk lesson', skill: 'chalk-talk', args: (f, out) => [f, out, '--no-review'] } },
]

/** The recipe a file is, by its name — and, for a .json, only a chalk-talk recipe (a title and steps), never any JSON. */
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

const base = (p: string) => p.split('/').pop() || 'recipe'

/** Runs the skill's own check on `text`, as a file of the same name in a folder of its own; the problems, or none. */
async function problems($: EngineInterface, path: string, text: string, r: Recipe): Promise<string[] | undefined> {
  const tmp = (await $.env.get('TMPDIR')) ?? '/tmp'
  const dir = `${tmp.replace(/\/$/, '')}/house-lights-guard-${Math.round(await $.clock.now())}-${Math.random().toString(36).slice(2, 8)}`
  const file = `${dir}/${base(path)}`
  try {
    await $.fs.write(file, text)
    const build = `${$.plugin.root}/skills/${r.skill}/scripts/build.mjs`
    const run = await $.process.run(['node', build, ...r.args(file, `${dir}/out.html`)], { timeoutMs: 7000 })
    if (run.exitCode === 0) return []
    if (run.exitCode !== 1) return undefined // bad arguments or another failure: not the recipe's fault
    const lines = `${run.stderr}\n${run.stdout}`.split('\n').map((l) => l.trimEnd()).filter((l) => /^✗|^\s+\S/.test(l) && !/^✗ \d+ check/.test(l))
    return lines.length ? lines.map((l) => l.split(dir + '/').join('')) : [`${base(path)}: the check refused it (exit 1)`]
  } finally {
    await $.process.run(['rm', '-rf', dir]).catch(() => undefined)
  }
}

async function judge($: EngineInterface, path: string, text: string, go: () => Promise<any>) {
  const r = recipeOf(path, text)
  if (!r) return go()
  const found = await problems($, path, text, r).catch(() => undefined)
  if (!found || !found.length) return go()
  return {
    deny: `${PLUGIN}: ${path} is not a valid ${r.what} yet (${r.skill}'s check). Fix these and write it again:\n${found.join('\n')}`,
  }
}

export function recipesGuard(on: On) {
  on('tool.call', { tool: 'Write' }, async ($, e, next) => judge($, e.file_path, e.content, () => next(e)))
  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    if (!RECIPES.some((r) => r.test.test(e.file_path))) return next(e)
    const after = await afterEdit($, e).catch(() => undefined)
    return after === undefined ? next(e) : judge($, e.file_path, after, () => next(e))
  })
}
