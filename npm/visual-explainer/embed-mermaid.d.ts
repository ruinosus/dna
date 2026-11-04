// visual-explainer/embed-mermaid: a Mermaid flowchart with `%% # chapter` / `%% > narration` comments as a visual-explainer recipe.
import type { Scene } from './embed.js'
export function readMermaid(source: string, options?: { locale?: string }): Promise<Scene>
