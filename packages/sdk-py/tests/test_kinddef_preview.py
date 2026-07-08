"""Per-extension preview tests for the KindDefinition kind."""
from __future__ import annotations

from dataclasses import dataclass

from dna.extensions.kinddef import KindDefinitionKind


@dataclass
class FakeDoc:
    kind: str
    name: str
    spec: dict
    api_version: str = "github.com/ruinosus/dna/core/v1"


class TestKindDefinitionPreview:
    def setup_method(self) -> None:
        self.kp = KindDefinitionKind()

    def test_renders_target_alias_schema_storage(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="KindDefinition",
                name="meeting",
                spec={
                    "target_kind": "Meeting",
                    "target_api_version": "user.local/v1",
                    "alias": "user-meeting",
                    "origin": "user.local",
                    "is_root": False,
                    "prompt_target": False,
                    "flatten_in_context": False,
                    "schema": {
                        "type": "object",
                        "required": ["title"],
                        "properties": {"title": {"type": "string"}},
                    },
                    "storage": {"type": "yaml", "container": "meetings"},
                    "docs": "Reunião com título e participantes.",
                },
            )
        )
        assert blocks[0].kind == "fields"
        labels = [f["label"] for f in blocks[0].fields]
        assert "target_kind" in labels
        assert "alias" in labels
        assert "schema" in labels
        assert "storage" in labels
        assert "docs" in labels
