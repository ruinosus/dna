// A drawing's recipe read as visual-explainer reads it — its text syntax, or JSON — and checked by its contract; a mistake in
// the text says its line. Only the contract (no renderer), so the engine stays small; the page draws with visual-explainer/embed.
// @ts-expect-error -- visual-explainer's contract (plain ESM, no types), aliased by tools/assets.mjs and the checks
import { parseChalk, PROP_ALIASES, PROP_NAMES, validateScene } from 'chalk-contract'

const PROPS: string[] = [...PROP_NAMES, ...Object.keys(PROP_ALIASES)]

export function readRecipe(source: string): unknown {
  const text = source.trim()
  return validateScene(text.startsWith('{') ? JSON.parse(text) : parseChalk(text, PROPS))
}
