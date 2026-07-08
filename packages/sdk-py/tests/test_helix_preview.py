"""Per-extension preview tests for the helix kinds (Module / Agent /
Actor / UseCase / Tool)."""
from __future__ import annotations

from dataclasses import dataclass

from dna.extensions.helix import (
    ActorKind,
    GenomeKind,
    ToolKind,
    UseCaseKind,
    AgentKind,
)


@dataclass
class FakeDoc:
    kind: str
    name: str
    spec: dict
    api_version: str = "test/v1"


class TestAgentPreview:
    def setup_method(self) -> None:
        self.kp = AgentKind()

    def test_renders_template_and_metadata(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="Agent",
                name="coach",
                spec={
                    "instruction": "{{soul_content}}\n\nyou are coach",
                    "model": "gpt-4o-mini",
                    "soul": "wise",
                    "skills": ["concise", "kind"],
                },
            )
        )
        assert len(blocks) == 2
        assert blocks[0].kind == "markdown"
        assert "{{soul_content}}" in (blocks[0].body or "")
        assert blocks[1].kind == "fields"
        labels = [f["label"] for f in blocks[1].fields]
        assert "model" in labels
        assert "soul" in labels
        assert "skills" in labels

    def test_empty_when_no_content(self) -> None:
        blocks = self.kp.preview(FakeDoc(kind="Agent", name="blank", spec={}))
        assert blocks[0].kind == "empty"


class TestToolPreview:
    def setup_method(self) -> None:
        self.kp = ToolKind()

    def test_renders_fields(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="Tool",
                name="slack-send",
                spec={
                    "type": "http",
                    "endpoint": "https://slack.com/api/chat.postMessage",
                    "method": "POST",
                    "input_schema": {"type": "object", "required": ["channel"]},
                    "read_only": False,
                },
            )
        )
        assert blocks[0].kind == "fields"
        labels = [f["label"] for f in blocks[0].fields]
        assert "type" in labels
        assert "endpoint" in labels
        assert "input_schema" in labels


class TestActorPreview:
    def test_renders_role_goals_pain_points(self) -> None:
        kp = ActorKind()
        blocks = kp.preview(
            FakeDoc(
                kind="Actor",
                name="customer",
                spec={
                    "role": "End user",
                    "actor_type": "human",
                    "goals": ["resolve issue quickly", "feel heard"],
                    "pain_points": ["long wait times"],
                },
            )
        )
        assert blocks[0].kind == "fields"
        labels = [f["label"] for f in blocks[0].fields]
        assert "role" in labels
        assert "goals" in labels
        assert "pain_points" in labels


class TestUseCasePreview:
    def test_renders_main_flow_numbered(self) -> None:
        kp = UseCaseKind()
        blocks = kp.preview(
            FakeDoc(
                kind="UseCase",
                name="onboard",
                spec={
                    "primary_actor": "customer",
                    "main_flow": ["sign up", "verify email", "select plan"],
                    "success_criteria": ["account active", "plan billed"],
                },
            )
        )
        flow = next(f for f in blocks[0].fields if f["label"] == "main_flow")
        assert "1. sign up" in flow["value"]


# Phase 16 — TestModulePreview removed. GenomeKind preview behavior is
# covered in tests/test_package_layerpolicy_kinds.py::TestGenomeKindPreview.
# The legacy test asserted ``"agents" in labels`` but the
# bill-of-materials arrays were dropped from GenomeSpec.
