"""Per-extension preview tests for the AgentDefinition kind."""
from __future__ import annotations

from dataclasses import dataclass

from dna.extensions.agentsmd import AgentDefinitionKind


@dataclass
class FakeDoc:
    kind: str
    name: str
    spec: dict
    api_version: str = "agents.md/v1"


class TestAgentDefinitionPreview:
    def setup_method(self) -> None:
        self.kp = AgentDefinitionKind()

    def test_returns_markdown_block_when_content_set(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="AgentDefinition",
                name="main",
                spec={"content": "# Coder\n\nDoes the work."},
            )
        )
        assert len(blocks) == 1
        assert blocks[0].kind == "markdown"
        assert blocks[0].title == "AGENTS.md"
        assert "Coder" in (blocks[0].body or "")

    def test_returns_empty_block_when_content_missing(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(kind="AgentDefinition", name="blank", spec={})
        )
        assert blocks[0].kind == "empty"
