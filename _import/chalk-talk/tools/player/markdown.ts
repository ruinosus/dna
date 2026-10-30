// chalk-talk/markdown: ```chalk-talk (the text syntax or JSON) and ```chalk-mermaid (a Mermaid diagram) fences become
// <div data-chalk-talk> blocks that chalk-talk/mount turns into lessons. The text goes inside as it is, readable until
// the lesson replaces it; reading it happens in the browser. Plain Node, no dependency.
// Spec 2026-10-30 (VS Code e sites de documentação).

const FENCES: Record<string, 'text' | 'mermaid'> = { 'chalk-talk': 'text', 'chalk-mermaid': 'mermaid' }

/** The kind of block a fence's info string asks for, or undefined for any other fence. */
export function fenceKind(info: string | null | undefined): 'text' | 'mermaid' | undefined {
  return FENCES[(info ?? '').trim().split(/\s+/)[0]]
}

const escape = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)

/** The block's HTML. */
export function blockHtml(kind: 'text' | 'mermaid', source: string): string {
  return `<div class="chalk-talk-block" data-chalk-talk="${kind}"><div class="chalk-talk-source" style="white-space:pre-wrap;font-family:monospace">${escape(source)}</div></div>\n`
}

interface MarkdownIt {
  renderer: { rules: Record<string, ((tokens: { info: string; content: string }[], idx: number, options: unknown, env: unknown, self: { renderToken(tokens: unknown[], idx: number, options: unknown): string }) => string) | undefined> }
}

/** markdown-it plugin (VS Code's Markdown preview, and anything built on markdown-it). */
export function markdownItChalkTalk(md: MarkdownIt) {
  const fence = md.renderer.rules.fence
  md.renderer.rules.fence = (tokens, idx, options, env, self) => {
    const kind = fenceKind(tokens[idx].info)
    if (kind) return blockHtml(kind, tokens[idx].content)
    return fence ? fence(tokens, idx, options, env, self) : self.renderToken(tokens as unknown[], idx, options)
  }
  return md
}

interface MdNode { type: string; lang?: string | null; meta?: string | null; value?: string; children?: MdNode[]; data?: Record<string, unknown> }

/** remark plugin (Docusaurus, MDX, unified): the fence becomes the block through hName/hProperties, so it works with
 * remark-rehype and with MDX alike. */
export function remarkChalkTalk() {
  const walk = (node: MdNode) => {
    if (node.type === 'code') {
      const kind = fenceKind(node.lang)
      if (kind) {
        node.data = {
          hName: 'div',
          hProperties: { className: ['chalk-talk-block'], dataChalkTalk: kind },
          hChildren: [{ type: 'element', tagName: 'div', properties: { className: ['chalk-talk-source'], style: 'white-space:pre-wrap;font-family:monospace' }, children: [{ type: 'text', value: node.value ?? '' }] }],
        }
      }
    }
    for (const child of node.children ?? []) walk(child)
  }
  return (tree: MdNode) => walk(tree)
}
