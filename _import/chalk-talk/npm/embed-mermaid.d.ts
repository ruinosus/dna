// chalk-talk/embed-mermaid: a Mermaid flowchart with `%% # chapter` / `%% > narration` comments as a chalk-talk recipe.
import type { Scene } from './embed.js'
export function readMermaid(source: string, options?: { locale?: string }): Promise<Scene>
