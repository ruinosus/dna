"""Per-extension preview tests for the Guardrail kind."""
from __future__ import annotations

from dataclasses import dataclass

from dna.extensions.guardrails import GuardrailKind


@dataclass
class FakeDoc:
    kind: str
    name: str
    spec: dict
    api_version: str = "github.com/ruinosus/dna/v1"


class TestGuardrailPreview:
    def setup_method(self) -> None:
        self.kp = GuardrailKind()

    def test_renders_instruction_rules_and_meta(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="Guardrail",
                name="no-pii",
                spec={
                    "instruction": "Never leak personally identifiable information.",
                    "rules": ["No emails", "No phone numbers", "No addresses"],
                    "severity": "hard",
                    "scope": "both",
                },
            )
        )
        assert len(blocks) == 3
        assert blocks[0].title == "GUARDRAIL.md"
        assert blocks[1].title == "Rules"
        assert "- No emails" in (blocks[1].body or "")
        assert blocks[2].kind == "fields"
        sev = next(f for f in blocks[2].fields if f["label"] == "severity")
        assert sev["value"] == "hard"

    def test_returns_empty_block_when_nothing_set(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(kind="Guardrail", name="empty", spec={})
        )
        assert len(blocks) == 1
        assert blocks[0].kind == "empty"
