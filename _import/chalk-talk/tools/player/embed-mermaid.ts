// chalk-talk/embed-mermaid (npm): a Mermaid flowchart (with `%% # chapter` and `%% > narration`) turned into a recipe in
// the browser. Apart from chalk-talk/embed because it is large (it carries Mermaid).
import { parseMermaidToExcalidraw } from '@excalidraw/mermaid-to-excalidraw'
import mermaid from 'mermaid'
import { mermaidToScene } from '@engine/mermaid'
import { validateScene, type Scene } from '@engine/recipe'

let ready = false
// Mermaid's own parser draws the kinds the converter gives only as a picture (pie, gantt, mindmap…).
const diagram = (s: string) => {
  if (!ready) mermaid.initialize({ startOnLoad: false })
  ready = true
  return mermaid.mermaidAPI.getDiagramFromText(s) as never
}

export async function readMermaid(source: string, opts: { locale?: string } = {}): Promise<Scene> {
  return validateScene(await mermaidToScene(source, parseMermaidToExcalidraw, { ...opts, diagram }))
}
