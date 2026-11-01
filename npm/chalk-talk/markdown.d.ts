// chalk-talk/markdown: ```chalk-talk and ```chalk-mermaid fences as <div data-chalk-talk> blocks for chalk-talk/mount.
export function fenceKind(info: string | null | undefined): 'text' | 'mermaid' | undefined
export function blockHtml(kind: 'text' | 'mermaid', source: string): string
/** markdown-it plugin: md.use(markdownItChalkTalk). */
export function markdownItChalkTalk<T>(md: T): T
/** remark plugin (unified, MDX, Docusaurus): remarkPlugins: [remarkChalkTalk]. */
export function remarkChalkTalk(): (tree: unknown) => void
