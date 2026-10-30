// chalk-talk/embed-mermaid (npm): a Mermaid flowchart (with `%% # chapter` and `%% > narration`) turned into a recipe in
// the browser. Apart from chalk-talk/embed because it is large (it carries Mermaid).
import { parseMermaidToExcalidraw } from '@excalidraw/mermaid-to-excalidraw'
import { mermaidToScene } from '@engine/mermaid'
import { validateScene, type Scene } from '@engine/recipe'

export async function readMermaid(source: string, opts: { locale?: string } = {}): Promise<Scene> {
  return validateScene(await mermaidToScene(source, parseMermaidToExcalidraw, opts))
}
