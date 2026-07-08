/**
 * Visualization module — barrel re-export.
 *
 * Standalone functions that operate on ManifestInstance, extracted from
 * the class to keep the kernel focused on query/prompt/composition.
 */

export {
  dependencyTreeMermaid,
  compositionFlowchartMermaid,
  c4ComponentMermaid,
  erDiagramMermaid,
  erModel,
  mindmapMermaid,
  pieChartMermaid,
  quadrantMermaid,
  timelineMermaid,
  sankeyMermaid,
  kindCatalogMermaid,
  exportDiagramsMd,
} from "./mermaid.js";

export { healthReport, impact } from "./health.js";

export { matrix, matrixMarkdown } from "./matrix.js";

export { asciiTree } from "./ascii.js";
