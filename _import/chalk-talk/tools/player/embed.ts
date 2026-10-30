// chalk-talk/embed (npm): a lesson mounted inside any element — an Obsidian note, a docs page, an app. The engine, the
// lesson and its fonts and styles are inside; the styles go on the page once, under .chalk-talk.
import { validateScene, type Scene } from '@engine/recipe'
import { PROP_ALIASES, PROP_NAMES } from '@engine/props'
import { ChalkTextError, parseChalk } from '@engine/text'
import type { Theme } from '@engine/renderer'
import { mountLesson as mount, stillLesson as still, type LessonOptions, type Mounted } from './lesson'

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

/** The faces and the lesson's styles, once per page. */
export function ensureStyles(doc: Document = document) {
  if (doc.getElementById('chalk-talk-styles')) return
  const style = doc.createElement('style')
  style.id = 'chalk-talk-styles'
  style.textContent = __CHALK_EMBED__.fonts + '\n' + __CHALK_EMBED__.css
  doc.head.append(style)
}

/** Takes the styles away again (a plugin being turned off). */
export function removeStyles(doc: Document = document) {
  doc.getElementById('chalk-talk-styles')?.remove()
}

export function mountLesson(root: HTMLElement, scene: Scene, opts: Omit<LessonOptions, 'faces'> = {}): Promise<Mounted> {
  ensureStyles(root.ownerDocument)
  return mount(root, scene, { faces: __CHALK_EMBED__.fonts, ...opts })
}

export function stillLesson(root: HTMLElement, scene: Scene, theme?: Theme): Promise<void> {
  ensureStyles(root.ownerDocument)
  return still(root, scene, theme)
}
