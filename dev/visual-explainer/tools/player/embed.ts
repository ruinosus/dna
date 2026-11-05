// visual-explainer/embed (npm): an explainer mounted inside any element — an Obsidian note, a docs page, an app. The engine, the
// explainer and its fonts and styles are inside; the styles go on the page once, under .visual-explainer.
import { validateScene, type Scene } from '@engine/recipe'
import { PROP_ALIASES, PROP_NAMES } from '@engine/props'
import { ChalkTextError, parseChalk } from '@engine/text'
import type { Theme } from '@engine/renderer'
import { mountExplainer as mount, stillExplainer as still, type ExplainerOptions, type Mounted } from './explainer'

declare const __CHALK_EMBED__: { css: string; fonts: string }

export { ChalkTextError }
export type { Scene, Theme, Mounted }

const PROPS = [...PROP_NAMES, ...Object.keys(PROP_ALIASES)]

/** A recipe from a block's text: JSON when it starts with "{", the text syntax otherwise. Throws ChalkTextError (with
 * the line) or the contract's Error. */
export function readRecipe(source: string): Scene {
  const text = source.trim()
  return validateScene(text.startsWith('{') ? JSON.parse(text) : parseChalk(text, PROPS))
}

/** The faces and the explainer's styles, once per page. */
export function ensureStyles(doc: Document = document) {
  if (doc.getElementById('visual-explainer-styles')) return
  const style = doc.createElement('style')
  style.id = 'visual-explainer-styles'
  style.textContent = __CHALK_EMBED__.fonts + '\n' + __CHALK_EMBED__.css
  doc.head.append(style)
}

/** Takes the styles away again (a plugin being turned off). */
export function removeStyles(doc: Document = document) {
  doc.getElementById('visual-explainer-styles')?.remove()
}

export function mountExplainer(root: HTMLElement, scene: Scene, opts: Omit<ExplainerOptions, 'faces'> = {}): Promise<Mounted> {
  ensureStyles(root.ownerDocument)
  return mount(root, scene, { faces: __CHALK_EMBED__.fonts, ...opts })
}

export function stillExplainer(root: HTMLElement, scene: Scene, theme?: Theme): Promise<void> {
  ensureStyles(root.ownerDocument)
  return still(root, scene, theme)
}

/** DNA 2.2.0: the names before, for a page that still calls them. */
export { mountExplainer as mountLesson, stillExplainer as stillLesson }
