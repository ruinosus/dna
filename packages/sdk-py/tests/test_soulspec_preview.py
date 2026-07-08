"""Per-extension preview tests for the Soul kind."""
from __future__ import annotations

from dataclasses import dataclass

from dna.extensions.soulspec import SoulKind


@dataclass
class FakeDoc:
    kind: str
    name: str
    spec: dict
    api_version: str = "soulspec.org/v1"


class TestSoulPreview:
    def setup_method(self) -> None:
        self.kp = SoulKind()

    def test_stacks_all_four_blocks_when_present(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="Soul",
                name="brad",
                spec={
                    "soul_content": "I am brad",
                    "style_content": "concise",
                    "soul_json": {"specVersion": "0.4", "name": "brad"},
                    "agents_content": "## Workflow",
                },
            )
        )
        assert len(blocks) == 4
        assert blocks[0].title == "SOUL.md"
        assert blocks[1].title == "STYLE.md"
        assert blocks[2].title == "soul.json"
        assert blocks[2].kind == "code"
        assert blocks[2].language == "json"
        assert "AGENTS.md" in blocks[3].title

    def test_only_emits_present_blocks(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(kind="Soul", name="brad", spec={"soul_content": "just a soul"})
        )
        assert len(blocks) == 1
        assert blocks[0].title == "SOUL.md"

    def test_returns_empty_block_when_nothing_present(self) -> None:
        blocks = self.kp.preview(FakeDoc(kind="Soul", name="brad", spec={}))
        assert len(blocks) == 1
        assert blocks[0].kind == "empty"
