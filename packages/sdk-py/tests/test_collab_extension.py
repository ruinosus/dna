"""Tests for CollabExtension — Comment Kind.

Comment is descriptor-backed since s-descriptor-conversion-pattern
(``dna/extensions/collab/kinds/comment.kind.yaml``); the hand-written
``CommentKind`` class is gone, so every assertion below resolves the
registered port through the real funnel. The surface is unchanged — that is
frozen, golden-by-golden, in ``test_descriptor_pattern_equivalence.py``.
"""
from __future__ import annotations

import pytest

from dna.extensions.collab import CollabExtension
from dna.kernel import Kernel


@pytest.fixture(scope="module")
def port():
    k = Kernel()
    k.load(CollabExtension())
    kp = k.kind_port_for("Comment")
    assert kp is not None
    return kp


class TestCommentKind:
    def test_metadata(self, port):
        assert port.api_version == "github.com/ruinosus/dna/collab/v1"
        assert port.kind == "Comment"
        assert port.alias == "collab-comment"
        assert port.origin == "github.com/ruinosus/dna/collab"

    def test_storage_yaml_container(self, port):
        assert port.storage.pattern == "yaml"
        assert port.storage.container == "comments"

    def test_dep_filters_empty(self, port):
        """Comment can reference any Kind — dep_filter is empty by design."""
        assert port.dep_filters() == {}

    def test_schema_required_fields(self, port):
        schema = port.schema()
        assert set(schema["required"]) == {"target_ref", "author", "body", "type", "created_at"}

    def test_schema_type_enum(self, port):
        schema = port.schema()
        assert schema["properties"]["type"]["enum"] == ["note", "status_change", "assignment", "system"]

    def test_parse_returns_raw(self, port):
        spec = {
            "target_ref": "Finding:xyz", "author": "alice", "body": "test",
            "type": "note", "created_at": "2026-04-14T00:00:00Z",
        }
        raw = {
            "apiVersion": "github.com/ruinosus/dna/collab/v1", "kind": "Comment",
            "metadata": {"name": "c-1"}, "spec": spec,
        }
        assert port.parse(dict(raw)) == raw

    def test_summary_extracts_preview(self, port):
        doc_mock = type("D", (), {"spec": {
            "target_ref": "Finding:xyz",
            "author": "alice",
            "type": "note",
            "body": "This is a long comment text that should be truncated in the summary view because it's very long indeed"
        }})()
        s = port.summary(doc_mock)
        assert s["target_ref"] == "Finding:xyz"
        assert s["author"] == "alice"
        assert len(s["body_preview"]) <= 80


class TestCollabExtension:
    def test_registers_comment_kind(self):
        kinds = []
        fake_kernel = type("K", (), {
            "kind_from_descriptor": lambda self, raw: kinds.append(raw),
        })()
        CollabExtension().register(fake_kernel)
        assert len(kinds) == 1
        assert kinds[0]["spec"]["target_kind"] == "Comment"

    def test_extension_metadata(self):
        ext = CollabExtension()
        assert ext.name == "collab"
        assert ext.version == "1.1.0"
