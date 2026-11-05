// visual-explainer/mount: every [data-visual-explainer] block on the page becomes an explainer — the ones there now and the ones that
// appear later (a Markdown preview redrawn while you type, a docs site moving between pages). A block holds its text
// (the text syntax, JSON, or a Mermaid diagram) in a .visual-explainer-source element, which stays readable until the explainer
// replaces it. visual-explainer/markdown writes these blocks from ```visual-explainer and ```visual-explainer-mermaid fences (and ```chalk-talk, ```chalk-mermaid, from before).
// Spec 2026-10-30 (VS Code e sites de documentação).
import type { Scene } from '@engine/recipe'
import type { Theme } from '@engine/renderer'
import { ChalkTextError, ensureStyles, mountExplainer, readRecipe } from './embed.js'
import type { Mounted } from './explainer'

// [data-chalk-talk] is the block of before DNA (a page rendered with the chalk-talk package): it still mounts
const BLOCK = '[data-visual-explainer], [data-chalk-talk]'
const mounted = new Map<HTMLElement, Mounted | null>()

/** The page's light or dark, as VS Code, Docusaurus (data-theme) or the system say: a light page gets DNA's business
 *  look (the explainer's «Hand-drawn» switches to the paper), a dark one the chalkboard — there is no dark business look. */
function theme(): Theme {
  const body = document.body.classList
  const page = document.documentElement.dataset.theme
  if (body.contains('vscode-dark') || body.contains('vscode-high-contrast')) return 'chalkboard'
  if (body.contains('vscode-light') || page === 'light') return 'business'
  if (page === 'dark') return 'chalkboard'
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'chalkboard' : 'business'
}

async function read(block: HTMLElement, source: string): Promise<Scene> {
  if ((block.dataset.visualExplainer ?? block.dataset.chalkTalk) !== 'mermaid') return readRecipe(source)
  const { readMermaid } = await import('./embed-mermaid.js')
  return readMermaid(source, { locale: navigator.language.toLowerCase().startsWith('pt') ? 'pt-BR' : 'en-US' })
}

/** «Expand»: the whole explainer in a dialog over the page. */
function expand(scene: Scene) {
  const dialog = document.createElement('dialog')
  dialog.className = 'visual-explainer-dialog'
  const close = document.createElement('button')
  close.type = 'button'
  close.className = 'visual-explainer-close'
  close.setAttribute('aria-label', 'Close')
  close.textContent = '×'
  const box = document.createElement('div')
  dialog.append(close, box)
  document.body.append(dialog)
  let explainer: Mounted | undefined
  close.addEventListener('click', () => dialog.close())
  dialog.addEventListener('close', () => {
    explainer?.destroy()
    dialog.remove()
  })
  dialog.showModal()
  void mountExplainer(box, scene, { theme: theme() }).then((m) => (explainer = m))
}

async function mountBlock(block: HTMLElement) {
  mounted.set(block, null)
  ensureStyles()
  const holder = block.querySelector<HTMLElement>('.visual-explainer-source, .chalk-talk-source')
  const source = holder?.textContent ?? ''
  const root = document.createElement('div')
  try {
    const scene = await read(block, source)
    if (!block.isConnected) return
    block.append(root)
    mounted.set(block, await mountExplainer(root, scene, { compact: true, theme: theme(), onExpand: () => expand(scene) }))
    if (holder) holder.hidden = true
  } catch (e) {
    // The mistake where the explainer would be: the line it is on, when the text syntax knows it.
    const box = document.createElement('div')
    box.className = 'visual-explainer-error'
    const title = document.createElement('b')
    title.textContent = 'visual-explainer'
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
  for (const [block, explainer] of mounted) {
    if (block.isConnected) continue
    explainer?.destroy()
    mounted.delete(block)
  }
  for (const block of root.querySelectorAll<HTMLElement>(BLOCK)) if (!mounted.has(block)) void mountBlock(block)
}

/** Mounts what is on the page now and keeps watching for blocks that appear (once per page). */
export function watch() {
  const w = window as unknown as { __visualExplainerWatching?: boolean }
  if (w.__visualExplainerWatching) return
  w.__visualExplainerWatching = true
  const go = () => {
    mountAll()
    new MutationObserver(() => mountAll()).observe(document.body, { childList: true, subtree: true })
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go)
  else go()
}
