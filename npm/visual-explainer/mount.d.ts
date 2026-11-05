// visual-explainer/mount: [data-visual-explainer] blocks become explainers (visual-explainer/markdown writes them).
/** Mounts the blocks inside `root` not mounted yet, and lets go of the ones no longer on the page. */
export function mountAll(root?: ParentNode): void
/** Mounts what is on the page now and keeps watching for blocks that appear (once per page). */
export function watch(): void
