// visual-explainer/markdown: ```visual-explainer and ```chalk-mermaid fences as <div data-visual-explainer> blocks for visual-explainer/mount.
export function fenceKind(info: string | null | undefined): 'text' | 'mermaid' | undefined
export function blockHtml(kind: 'text' | 'mermaid', source: string): string
/** markdown-it plugin: md.use(markdownItVisualExplainer). */
export function markdownItVisualExplainer<T>(md: T): T
/** remark plugin (unified, MDX, Docusaurus): remarkPlugins: [remarkVisualExplainer]. */
export function remarkVisualExplainer(): (tree: unknown) => void
