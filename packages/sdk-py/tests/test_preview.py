"""Tests for the kernel-level preview API: generic_spec_dump fallback +
cross-document find_consumers scan. Per-extension preview() tests live
alongside their extension files (test_extensions_preview.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from dna.kernel.preview import (
    PreviewBlock,
    find_consumers,
    generic_spec_dump,
)


@dataclass
class FakeDoc:
    kind: str
    name: str
    spec: dict
    api_version: str = "test/v1"
    metadata: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {"name": self.name}


# Known dep-field conventions for the mock. In the real kernel this
# knowledge lives in KindPort.dep_filters(); here we replicate just
# enough so the find_consumers tests exercise the iter_doc_deps path.
_MOCK_DEP_FIELDS: dict[str, dict[str, str]] = {
    "Agent": {
        "skills": "Skill",
        "guardrails": "Guardrail",
        "tools": "Tool",
        "soul": "Soul",
        "personas": "Persona",
        "use_cases": "UseCase",
    },
}


class FakeInstance:
    def __init__(self, docs: list[FakeDoc]) -> None:
        self.documents = docs

    def one(self, kind: str, name: str) -> Any:
        for d in self.documents:
            if d.kind == kind and d.name == name:
                return d
        return None

    def all(self, kind: str) -> list:
        return [d for d in self.documents if d.kind == kind]

    def iter_doc_deps(self, doc: Any) -> list[dict[str, Any]]:
        field_map = _MOCK_DEP_FIELDS.get(doc.kind, {})
        spec = doc.spec if isinstance(doc.spec, dict) else {}
        out: list[dict[str, Any]] = []
        for label, target_kind in field_map.items():
            val = spec.get(label)
            names: list[str] = []
            if isinstance(val, list):
                names = [str(v) for v in val]
            elif isinstance(val, str) and val:
                names = [val]
            out.append({"label": label, "target_kind": target_kind, "names": names})
        return out


# ── generic_spec_dump ──────────────────────────────────────────────────────


class TestGenericSpecDump:
    def test_returns_empty_block_when_spec_is_empty(self) -> None:
        doc = FakeDoc(kind="Mystery", name="thing", spec={})
        blocks = generic_spec_dump(doc)
        assert len(blocks) == 1
        assert blocks[0].kind == "empty"
        assert "empty" in blocks[0].title.lower()

    def test_returns_one_code_block_when_spec_has_content(self) -> None:
        doc = FakeDoc(
            kind="Mystery",
            name="thing",
            spec={"foo": 1, "bar": ["a", "b"]},
        )
        blocks = generic_spec_dump(doc)
        assert len(blocks) == 1
        assert blocks[0].kind == "code"
        assert blocks[0].language == "json"
        assert '"foo"' in (blocks[0].body or "")
        assert '"bar"' in (blocks[0].body or "")


# ── find_consumers ─────────────────────────────────────────────────────────


class TestFindConsumers:
    def test_returns_empty_when_nothing_references(self) -> None:
        target = FakeDoc(kind="Skill", name="lonely", spec={})
        consumers = find_consumers(
            FakeInstance([target]),  # type: ignore[arg-type]
            {"kind": "Skill", "name": "lonely"},
        )
        assert consumers == []

    def test_finds_agent_via_skills_collection(self) -> None:
        skill = FakeDoc(kind="Skill", name="feedback-tone", spec={})
        agent = FakeDoc(
            kind="Agent",
            name="coach",
            spec={"skills": ["feedback-tone"]},
        )
        consumers = find_consumers(
            FakeInstance([skill, agent]),  # type: ignore[arg-type]
            {"kind": "Skill", "name": "feedback-tone"},
        )
        assert consumers == [{"kind": "Agent", "name": "coach"}]

    def test_finds_agent_via_soul_scalar(self) -> None:
        soul = FakeDoc(kind="Soul", name="brad", spec={})
        agent = FakeDoc(
            kind="Agent", name="coach", spec={"soul": "brad"}
        )
        consumers = find_consumers(
            FakeInstance([soul, agent]),  # type: ignore[arg-type]
            {"kind": "Soul", "name": "brad"},
        )
        assert len(consumers) == 1

    def test_finds_agent_via_guardrails_collection(self) -> None:
        g = FakeDoc(kind="Guardrail", name="no-pii", spec={})
        agent = FakeDoc(
            kind="Agent",
            name="coach",
            spec={"guardrails": ["no-pii"]},
        )
        consumers = find_consumers(
            FakeInstance([g, agent]),  # type: ignore[arg-type]
            {"kind": "Guardrail", "name": "no-pii"},
        )
        assert len(consumers) == 1

    def test_does_not_return_target_itself(self) -> None:
        skill = FakeDoc(kind="Skill", name="feedback-tone", spec={})
        consumers = find_consumers(
            FakeInstance([skill]),  # type: ignore[arg-type]
            {"kind": "Skill", "name": "feedback-tone"},
        )
        assert consumers == []

    def test_returns_multiple_consumers(self) -> None:
        skill = FakeDoc(kind="Skill", name="concise", spec={})
        a = FakeDoc(kind="Agent", name="coach", spec={"skills": ["concise"]})
        b = FakeDoc(
            kind="Agent",
            name="mentor",
            spec={"skills": ["concise", "kind"]},
        )
        consumers = find_consumers(
            FakeInstance([skill, a, b]),  # type: ignore[arg-type]
            {"kind": "Skill", "name": "concise"},
        )
        assert len(consumers) == 2
