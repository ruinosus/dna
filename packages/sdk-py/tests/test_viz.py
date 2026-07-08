"""Tests for viz module parity — Python.

Each test verifies that the standalone viz function returns
the same result as the existing ManifestInstance method.
"""
from __future__ import annotations
from pathlib import Path

from dna import Kernel
from dna.viz.mermaid import (
    dependency_tree_mermaid,
    er_diagram_mermaid,
    mindmap_mermaid,
    pie_chart_mermaid,
    kind_catalog_mermaid,
    quadrant_mermaid,
    timeline_mermaid,
    sankey_mermaid,
    composition_flowchart_mermaid,
    c4_component_mermaid,
    export_diagrams_md,
)
from dna.viz.health import health_report, impact
from dna.viz.matrix import matrix, matrix_markdown
from dna.viz.ascii import ascii_tree


BASE_DIR = Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"


class TestVizMermaidParity:
    """Verify standalone viz functions match ManifestInstance methods."""

    def setup_method(self):
        self.mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))

    def test_dependency_tree_mermaid_parity(self):
        assert dependency_tree_mermaid(self.mi) == self.mi.dependency_tree_mermaid()

    def test_er_diagram_mermaid_parity(self):
        assert er_diagram_mermaid(self.mi) == self.mi.er_diagram_mermaid()

    def test_mindmap_mermaid_parity(self):
        assert mindmap_mermaid(self.mi) == self.mi.mindmap_mermaid()

    def test_pie_chart_mermaid_parity(self):
        assert pie_chart_mermaid(self.mi) == self.mi.pie_chart_mermaid()

    def test_kind_catalog_mermaid_parity(self):
        assert kind_catalog_mermaid(self.mi) == self.mi.kind_catalog_mermaid()

    def test_quadrant_mermaid_parity(self):
        assert quadrant_mermaid(self.mi) == self.mi.quadrant_mermaid()

    def test_timeline_mermaid_parity(self):
        assert timeline_mermaid(self.mi) == self.mi.timeline_mermaid()

    def test_sankey_mermaid_parity(self):
        assert sankey_mermaid(self.mi) == self.mi.sankey_mermaid()


class TestVizHealthParity:
    def setup_method(self):
        self.mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))

    def test_health_report_parity(self):
        assert health_report(self.mi) == self.mi.health()

    def test_impact_parity(self):
        # Find a skill to test impact on
        skills = [d for d in self.mi.documents if d.kind == "Skill"]
        if skills:
            s = skills[0]
            assert impact(self.mi, s.kind, s.name) == self.mi.impact(s.kind, s.name)


class TestVizMatrixParity:
    def setup_method(self):
        self.mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))

    def test_matrix_parity(self):
        assert matrix(self.mi) == self.mi.matrix()

    def test_matrix_markdown_parity(self):
        assert matrix_markdown(self.mi) == self.mi.matrix_markdown()


class TestVizAsciiParity:
    def setup_method(self):
        self.mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))

    def test_ascii_tree_parity(self):
        assert ascii_tree(self.mi) == self.mi.ascii_tree()


class TestVizNewFunctions:
    """Test composition_flowchart and c4_component (new functions, no MI method to compare)."""

    def setup_method(self):
        self.mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))

    def test_composition_flowchart_returns_string(self):
        result = composition_flowchart_mermaid(self.mi)
        assert isinstance(result, str)
        assert result.startswith("graph LR")

    def test_c4_component_returns_string(self):
        result = c4_component_mermaid(self.mi)
        assert isinstance(result, str)
        assert result.startswith("graph LR")

    def test_export_diagrams_md_returns_dict(self):
        result = export_diagrams_md(self.mi)
        assert isinstance(result, dict)
        assert "all-diagrams.md" in result
        assert "c4-component.md" in result
        assert "composition-flowchart.md" in result
        assert "dependency-tree.md" in result


class TestVizBarrelImport:
    """Test that barrel import works."""

    def test_barrel_import(self):
        from dna.viz import (
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
            health_report,
            impact,
            matrix,
            matrix_markdown,
            ascii_tree,
        )
        # All should be callable
        assert callable(dependency_tree_mermaid)
        assert callable(composition_flowchart_mermaid)
        assert callable(c4_component_mermaid)
        assert callable(health_report)
        assert callable(matrix)
        assert callable(ascii_tree)
