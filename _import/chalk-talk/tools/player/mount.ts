// chalk-talk/mount: every [data-chalk-talk] block on the page becomes a lesson — the ones there now and the ones that
// appear later (a Markdown preview redrawn while you type, a docs site moving between pages). A block holds its text
// (the text syntax, JSON, or a Mermaid diagram) in a .chalk-talk-source element, which stays readable until the lesson
// replaces it. chalk-talk/markdown writes these blocks from ```chalk-talk and ```chalk-mermaid fences.
// Spec 2026-10-30 (VS Code e sites de documentação).
import type { Scene } from '@engine/recipe'
import type { Theme } from '@engine/renderer'
import { ChalkTextError, ensureStyles, mountLesson, readRecipe } from './embed.js'
import type { Mounted } from './lesson'

const BLOCK = '[data-chalk-talk]'
const mounted = new Map<HTMLElement, Mounted | null>()

/** The page's light or dark, as VS Code, Docusaurus (data-theme) or the system say. */
function theme(): Theme {
  const body = document.body.classList
  const page = document.documentElement.dataset.theme
  if (body.contains('vscode-dark') || body.contains('vscode-high-contrast')) return 'chalkboard'
  if (body.contains('vscode-light') || page === 'light') return 'paper'
  if (page === 'dark') return 'chalkboard'
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'chalkboard' : 'paper'
}

async function read(block: HTMLElement, source: string): Promise<Scene> {
  if (block.dataset.chalkTalk !== 'mermaid') return readRecipe(source)
  const { readMermaid } = await import('./embed-mermaid.js')
  return readMermaid(source, { locale: navigator.language.toLowerCase().startsWith('pt') ? 'pt-BR' : 'en-US' })
}

/** «Expand»: the whole lesson in a dialog over the page. */
function expand(scene: Scene) {
  const dialog = document.createElement('dialog')
  dialog.className = 'chalk-talk-dialog'
  const close = document.createElement('button')
  close.type = 'button'
  close.className = 'chalk-talk-close'
  close.setAttribute('aria-label', 'Close')
  close.textContent = '×'
  const box = document.createElement('div')
  dialog.append(close, box)
  document.body.append(dialog)
  let lesson: Mounted | undefined
  close.addEventListener('click', () => dialog.close())
  dialog.addEventListener('close', () => {
    lesson?.destroy()
    dialog.remove()
  })
  dialog.showModal()
  void mountLesson(box, scene, { theme: theme() }).then((m) => (lesson = m))
}

async function mountBlock(block: HTMLElement) {
  mounted.set(block, null)
  ensureStyles()
  const holder = block.querySelector<HTMLElement>('.chalk-talk-source')
  const source = holder?.textContent ?? ''
  const root = document.createElement('div')
  try {
    const scene = await read(block, source)
    if (!block.isConnected) return
    block.append(root)
    mounted.set(block, await mountLesson(root, scene, { compact: true, theme: theme(), onExpand: () => expand(scene) }))
    if (holder) holder.hidden = true
  } catch (e) {
    // The mistake where the lesson would be: the line it is on, when the text syntax knows it.
    const box = document.createElement('div')
    box.className = 'chalk-talk-error'
    const title = document.createElement('b')
    title.textContent = 'chalk-talk'
    box.append(title, ` · ${(e as Error).message}`)
    if (e instanceof ChalkTextError) {
      const line = source.split('\n')[e.line - 1]
      if (line?.trim()) {
        const code = document.createElement('code')
        code.textContent = line
        box.append(code)
      }
    }
    block.prepend(box)
  }
}

/** Mounts the blocks inside `root` not mounted yet, and lets go of the ones no longer on the page. */
export function mountAll(root: ParentNode = document) {
  for (const [block, lesson] of mounted) {
    if (block.isConnected) continue
    lesson?.destroy()
    mounted.delete(block)
  }
  for (const block of root.querySelectorAll<HTMLElement>(BLOCK)) if (!mounted.has(block)) void mountBlock(block)
}

/** Mounts what is on the page now and keeps watching for blocks that appear (once per page). */
export function watch() {
  const w = window as unknown as { __chalkTalkWatching?: boolean }
  if (w.__chalkTalkWatching) return
  w.__chalkTalkWatching = true
  const go = () => {
    mountAll()
    new MutationObserver(() => mountAll()).observe(document.body, { childList: true, subtree: true })
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go)
  else go()
}
