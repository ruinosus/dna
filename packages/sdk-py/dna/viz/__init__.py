"""Visualization module — barrel re-export.

Standalone functions that operate on ManifestInstance, extracted from
the class to keep the kernel focused on query/prompt/composition.
"""

from dna.viz.mermaid import (
    dependency_tree_mermaid,
    composition_flowchart_mermaid,
    c4_component_mermaid,
    er_diagram_mermaid,
    mindmap_mermaid,
    pie_chart_mermaid,
    quadrant_mermaid,
    timeline_mermaid,
    sankey_mermaid,
    kind_catalog_mermaid,
    export_diagrams_md,
)

from dna.viz.health import health_report, impact

from dna.viz.matrix import matrix, matrix_markdown

from dna.viz.ascii import ascii_tree

__all__ = [
    "dependency_tree_mermaid",
    "composition_flowchart_mermaid",
    "c4_component_mermaid",
    "er_diagram_mermaid",
    "mindmap_mermaid",
    "pie_chart_mermaid",
    "quadrant_mermaid",
    "timeline_mermaid",
    "sankey_mermaid",
    "kind_catalog_mermaid",
    "export_diagrams_md",
    "health_report",
    "impact",
    "matrix",
    "matrix_markdown",
    "ascii_tree",
]
