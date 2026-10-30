// chalk-talk/embed: one lesson mounted inside an element. The recipe format: https://github.com/ruinosus/chalk-talk
export type Theme = 'paper' | 'chalkboard'
/** A checked recipe (what readRecipe returns). */
export interface Scene { id: string; title: string; width: number; height: number; theme?: Theme; locale?: string; steps: unknown[]; [key: string]: unknown }
export interface Mounted { destroy(): void }
export interface LessonOptions {
  /** Button language; the browser's by default. */
  lang?: 'en' | 'pt'
  /** The lesson inside a note: chapters, Values and Expand on top, the bar below; opens on chapter 1, drawn and still. */
  compact?: boolean
  /** The theme when the recipe has none. */
  theme?: Theme
  /** 'document': arrow keys and Space work anywhere on the page; otherwise only while the focus is in the lesson. */
  keys?: 'document' | 'self'
  /** Shows «Expand», which calls this. */
  onExpand?: () => void
}
/** A mistake in the text syntax, with its line. */
export class ChalkTextError extends Error { line: number }
/** JSON when the text starts with "{", the text syntax otherwise; throws ChalkTextError or the contract's Error. */
export function readRecipe(source: string): Scene
export function mountLesson(root: HTMLElement, scene: Scene, options?: LessonOptions): Promise<Mounted>
/** The whole drawing at once, still (an exported PDF, a printed page). */
export function stillLesson(root: HTMLElement, scene: Scene, theme?: Theme): Promise<void>
export function ensureStyles(doc?: Document): void
export function removeStyles(doc?: Document): void
