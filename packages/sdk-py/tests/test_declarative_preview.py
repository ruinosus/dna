"""Tests for DeclarativeKindPort.preview() — generic preview derived from
the JSON schema attached to a KindDefinition. Mirrors
typescript/tests/declarative-preview.test.ts.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from dna.kernel.meta import DeclarativeKindPort


def make_port(schema: dict) -> DeclarativeKindPort:
    typed_like = SimpleNamespace(
        spec=SimpleNamespace(
            target_kind="Meeting",
            target_api_version="user.local/v1",
            alias="user-meeting",
            origin="user.local",
            is_root=False,
            prompt_target=False,
            flatten_in_context=False,
            schema=schema,
            storage={"type": "yaml", "container": "meetings"},
            dep_filters=None,
            default_agent=None,
            docs="",
        )
    )
    return DeclarativeKindPort(typed_like)


@dataclass
class FakeDoc:
    kind: str
    name: str
    spec: dict
    api_version: str = "user.local/v1"


class TestDeclarativePreview:
    def test_empty_when_schema_and_spec_empty(self) -> None:
        port = make_port({})
        blocks = port.preview(FakeDoc(kind="Meeting", name="x", spec={}))
        assert len(blocks) == 1
        assert blocks[0].kind == "empty"

    def test_short_strings_become_fields(self) -> None:
        port = make_port(
            {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string", "title": "Título"},
                    "location": {"type": "string"},
                },
            }
        )
        blocks = port.preview(
            FakeDoc(
                kind="Meeting",
                name="x",
                spec={"title": "Standup diário", "location": "Zoom"},
            )
        )
        fields_block = next(b for b in blocks if b.kind == "fields")
        labels = [f["label"] for f in fields_block.fields]
        assert "Título" in labels
        assert "location" in labels

    def test_markdown_format_becomes_standalone_block(self) -> None:
        port = make_port(
            {
                "properties": {
                    "description": {
                        "type": "string",
                        "format": "markdown",
                        "title": "Descrição",
                    }
                }
            }
        )
        blocks = port.preview(
            FakeDoc(
                kind="Meeting",
                name="x",
                spec={"description": "## Pauta\n\n- Item 1\n- Item 2"},
            )
        )
        md = next(b for b in blocks if b.kind == "markdown")
        assert md.title == "Descrição"
        assert "Pauta" in (md.body or "")

    def test_string_array_becomes_bullet_list(self) -> None:
        port = make_port(
            {
                "properties": {
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "title": "Participantes",
                    }
                }
            }
        )
        blocks = port.preview(
            FakeDoc(
                kind="Meeting",
                name="x",
                spec={"attendees": ["alice", "bob", "carol"]},
            )
        )
        fields_block = next(b for b in blocks if b.kind == "fields")
        entry = next(f for f in fields_block.fields if f["label"] == "Participantes")
        assert "• alice" in entry["value"]
        assert "• carol" in entry["value"]

    def test_enum_and_boolean_become_fields(self) -> None:
        port = make_port(
            {
                "properties": {
                    "priority": {"type": "string", "enum": ["baixa", "media", "alta"]},
                    "done": {"type": "boolean"},
                }
            }
        )
        blocks = port.preview(
            FakeDoc(kind="Meeting", name="x", spec={"priority": "alta", "done": True})
        )
        fields_block = next(b for b in blocks if b.kind == "fields")
        labels = [f["label"] for f in fields_block.fields]
        assert "priority" in labels
        assert "done" in labels
        done = next(f for f in fields_block.fields if f["label"] == "done")
        assert done["value"] == "true"

    def test_nested_objects_become_code_blocks(self) -> None:
        port = make_port(
            {"properties": {"config": {"type": "object", "title": "Config"}}}
        )
        blocks = port.preview(
            FakeDoc(
                kind="Meeting",
                name="x",
                spec={"config": {"retries": 3, "timeout": 60}},
            )
        )
        code = next(b for b in blocks if b.kind == "code")
        assert code.title == "Config"
        assert '"retries"' in (code.body or "")

    def test_required_fields_render_first(self) -> None:
        port = make_port(
            {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "notes": {"type": "string"},
                    "title": {"type": "string"},
                },
            }
        )
        blocks = port.preview(
            FakeDoc(
                kind="Meeting",
                name="x",
                spec={"title": "Sprint review", "notes": "ok"},
            )
        )
        fields_block = next(b for b in blocks if b.kind == "fields")
        labels = [f["label"] for f in fields_block.fields]
        assert labels[0] == "title"
