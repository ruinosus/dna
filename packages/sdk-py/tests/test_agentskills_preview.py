"""Per-extension preview tests for the Skill kind."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dna.extensions.agentskills import SkillKind


@dataclass
class FakeDoc:
    kind: str
    name: str
    spec: dict
    api_version: str = "agentskills.io/v1"


class TestSkillPreview:
    def setup_method(self) -> None:
        self.kp = SkillKind()

    def test_returns_markdown_block_when_instruction_set(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="Skill",
                name="feedback-tone",
                spec={"instruction": "# Feedback tone\n\nbe kind and direct."},
            )
        )
        assert len(blocks) == 1
        assert blocks[0].kind == "markdown"
        assert blocks[0].title == "SKILL.md"
        assert "be kind" in (blocks[0].body or "")

    def test_returns_empty_block_when_instruction_missing(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(kind="Skill", name="blank", spec={})
        )
        assert len(blocks) == 1
        assert blocks[0].kind == "empty"
