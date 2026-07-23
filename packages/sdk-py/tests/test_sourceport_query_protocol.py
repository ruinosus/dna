"""Tests for SourcePort.query() Protocol + the load_all fallback.

Story s-sourceport-query-protocol (Feature f-source-as-query, Epic
e-production-viable-kernel). s-sourceport-contract-cleanup moved the
fallback OUT of the Protocol body into
``dna.kernel.query.fallback.query_via_load_all`` (the Protocol
declares signatures only). These tests verify (a) the Protocol surface
is correct and (b) the fallback semantics match what concrete adapters
MUST also satisfy.

Adapter-specific tests live in their own Stories
(s-postgres-source-query-impl etc.). The s-source-query-parity-tests
Story will collapse this file into a shared suite once 2+ adapters
ship their impls.
"""
from __future__ import annotations

import inspect
from typing import Any

import pytest

from dna.kernel.query.fallback import query_via_load_all
from dna.kernel.protocols import (
    SourcePort,
    QueryError,
    QueryFilter,
    QueryProjection,
    QueryOrder,
    _resolve_field_path,
    _match_filter,
    _project_doc,
    _apply_order_by,
)


# ---------------------------------------------------------------------------
# Protocol surface
# ---------------------------------------------------------------------------

def test_query_method_is_declared_on_protocol():
    """Static contract: SourcePort exposes ``query``."""
    assert hasattr(SourcePort, "query")
    assert inspect.iscoroutinefunction(SourcePort.query) or inspect.isasyncgenfunction(SourcePort.query)


def test_query_signature_is_correct():
    sig = inspect.signature(SourcePort.query)
    params = sig.parameters
    assert "scope" in params
    assert "kind" in params
    assert params["filter"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["filter"].default is None
    assert params["projection"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["limit"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["offset"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["order_by"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["tenant"].kind == inspect.Parameter.KEYWORD_ONLY


def test_query_types_are_exported():
    """The four query type aliases + QueryError ship from the same module."""
    # No assertion on identity — just that imports succeed (covered by
    # the import at the top of this file). This sentinel guards against
    # accidental removal.
    assert QueryFilter is dict[str, Any] or repr(QueryFilter).startswith("dict")
    assert QueryProjection is list[str] or repr(QueryProjection).startswith("list")
    assert QueryOrder is list[str] or repr(QueryOrder).startswith("list")
    assert issubclass(QueryError, ValueError)


# ---------------------------------------------------------------------------
# Field path resolver
# ---------------------------------------------------------------------------

class TestResolveFieldPath:
    def test_name_short_resolves_to_metadata_name(self):
        doc = {"kind": "Story", "metadata": {"name": "s-foo"}, "spec": {"name": "WRONG"}}
        assert _resolve_field_path(doc, "name") == "s-foo"

    def test_kind_resolves_to_top_level(self):
        doc = {"kind": "Story", "metadata": {"name": "s-a"}}
        assert _resolve_field_path(doc, "kind") == "Story"

    def test_unprefixed_path_resolves_under_spec(self):
        doc = {"spec": {"status": "todo", "feature": "f-foo"}}
        assert _resolve_field_path(doc, "status") == "todo"
        assert _resolve_field_path(doc, "feature") == "f-foo"

    def test_explicit_spec_prefix(self):
        doc = {"spec": {"nested": {"deep": "value"}}}
        assert _resolve_field_path(doc, "spec.nested.deep") == "value"

    def test_missing_segment_returns_none(self):
        doc = {"spec": {"a": 1}}
        assert _resolve_field_path(doc, "b") is None
        assert _resolve_field_path(doc, "a.x") is None

    def test_metadata_prefix(self):
        doc = {"metadata": {"name": "x", "labels": ["a", "b"]}}
        assert _resolve_field_path(doc, "metadata.labels") == ["a", "b"]


# ---------------------------------------------------------------------------
# Filter matcher
# ---------------------------------------------------------------------------

class TestMatchFilter:
    def test_shorthand_eq(self):
        doc = {"spec": {"status": "in-progress"}}
        assert _match_filter(doc, {"status": "in-progress"})
        assert not _match_filter(doc, {"status": "done"})

    def test_explicit_eq_op(self):
        doc = {"spec": {"status": "in-progress"}}
        assert _match_filter(doc, {"status": {"eq": "in-progress"}})

    def test_in_operator(self):
        doc = {"spec": {"status": "in-progress"}}
        assert _match_filter(doc, {"status": {"in": ["todo", "in-progress"]}})
        assert not _match_filter(doc, {"status": {"in": ["done", "cancelled"]}})

    def test_like_with_percent_wildcard(self):
        doc = {"spec": {"title": "kernel performance fix"}}
        assert _match_filter(doc, {"title": {"like": "%kernel%"}})
        assert not _match_filter(doc, {"title": {"like": "%nonexistent%"}})

    def test_gt_lt_operators(self):
        doc = {"spec": {"priority": 5}}
        assert _match_filter(doc, {"priority": {"gt": 3}})
        assert _match_filter(doc, {"priority": {"lt": 10}})
        assert not _match_filter(doc, {"priority": {"gt": 5}})  # strict
        assert _match_filter(doc, {"priority": {"gte": 5}})  # inclusive
        assert _match_filter(doc, {"priority": {"lte": 5}})

    def test_unknown_operator_raises_query_error(self):
        doc = {"spec": {"status": "x"}}
        with pytest.raises(QueryError, match="unknown query operator"):
            _match_filter(doc, {"status": {"regex": ".*"}})

    def test_and_semantics_multiple_keys(self):
        doc = {"spec": {"status": "in-progress", "feature": "f-foo"}}
        assert _match_filter(doc, {"status": "in-progress", "feature": "f-foo"})
        assert not _match_filter(doc, {"status": "in-progress", "feature": "f-bar"})

    def test_missing_field_does_not_match_eq(self):
        doc = {"spec": {"other": "x"}}
        assert not _match_filter(doc, {"status": "in-progress"})

    def test_neq_operator(self):
        doc = {"spec": {"status": "done"}}
        assert _match_filter(doc, {"status": {"neq": "in-progress"}})
        assert not _match_filter(doc, {"status": {"neq": "done"}})


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

class TestProjectDoc:
    def test_name_always_included(self):
        doc = {"kind": "Story", "metadata": {"name": "s-foo"}, "spec": {"title": "T", "status": "x"}}
        out = _project_doc(doc, ["spec.title"])
        assert out["name"] == "s-foo"
        assert out["spec"]["title"] == "T"

    def test_unprefixed_resolves_under_spec(self):
        doc = {"kind": "Story", "metadata": {"name": "s-a"}, "spec": {"status": "todo"}}
        out = _project_doc(doc, ["status"])
        assert out["spec"]["status"] == "todo"

    def test_excluded_fields_not_present(self):
        doc = {"kind": "Story", "metadata": {"name": "s-a"},
               "spec": {"title": "T", "status": "x", "description": "BIG_PAYLOAD"}}
        out = _project_doc(doc, ["spec.title", "spec.status"])
        assert "description" not in out.get("spec", {})

    def test_missing_field_omitted(self):
        doc = {"metadata": {"name": "s-a"}, "spec": {}}
        out = _project_doc(doc, ["spec.title"])
        assert "title" not in out.get("spec", {})

    def test_kind_projection_works(self):
        doc = {"kind": "Story", "metadata": {"name": "s-a"}, "spec": {}}
        out = _project_doc(doc, ["kind"])
        assert out["kind"] == "Story"


# ---------------------------------------------------------------------------
# Order_by
# ---------------------------------------------------------------------------

class TestApplyOrderBy:
    def test_ascending_default(self):
        rows = [
            {"metadata": {"name": "b"}, "spec": {"updated_at": "2026-05-12"}},
            {"metadata": {"name": "a"}, "spec": {"updated_at": "2026-05-10"}},
            {"metadata": {"name": "c"}, "spec": {"updated_at": "2026-05-14"}},
        ]
        ordered = _apply_order_by(rows, ["spec.updated_at"])
        names = [r["metadata"]["name"] for r in ordered]
        assert names == ["a", "b", "c"]

    def test_descending_with_dash_prefix(self):
        rows = [
            {"metadata": {"name": "b"}, "spec": {"updated_at": "2026-05-12"}},
            {"metadata": {"name": "a"}, "spec": {"updated_at": "2026-05-10"}},
            {"metadata": {"name": "c"}, "spec": {"updated_at": "2026-05-14"}},
        ]
        ordered = _apply_order_by(rows, ["-spec.updated_at"])
        names = [r["metadata"]["name"] for r in ordered]
        assert names == ["c", "b", "a"]

    def test_none_values_last(self):
        rows = [
            {"metadata": {"name": "has"}, "spec": {"updated_at": "2026-05-12"}},
            {"metadata": {"name": "none"}, "spec": {}},
        ]
        ordered = _apply_order_by(rows, ["spec.updated_at"])
        names = [r["metadata"]["name"] for r in ordered]
        assert names == ["has", "none"]


# ---------------------------------------------------------------------------
# Load-all fallback (kernel-side helper — was the Protocol body)
# ---------------------------------------------------------------------------

class _FakeSource:
    """Minimal SourcePort with load_all + load_layer. Used to exercise
    the Protocol's default `query` fallback."""

    def __init__(self, base_docs, overlay_docs=None):
        self._base = list(base_docs)
        self._overlay = list(overlay_docs or [])

    async def load_all(self, scope, readers=None):
        return list(self._base)

    async def load_layer(self, scope, layer_id, layer_value, readers=None):
        return list(self._overlay)


def _doc(kind, name, **spec):
    return {"kind": kind, "metadata": {"name": name}, "spec": spec}


@pytest.mark.asyncio
async def test_fallback_filters_by_kind():
    src = _FakeSource([
        _doc("Story", "s-a", status="todo"),
        _doc("Feature", "f-a"),
        _doc("Story", "s-b", status="done"),
    ])
    rows = [r async for r in query_via_load_all(src, "scope-x", "Story")]
    names = sorted(r["metadata"]["name"] for r in rows)
    assert names == ["s-a", "s-b"]


@pytest.mark.asyncio
async def test_fallback_applies_filter():
    src = _FakeSource([
        _doc("Story", "s-a", status="todo"),
        _doc("Story", "s-b", status="done"),
        _doc("Story", "s-c", status="todo"),
    ])
    rows = [r async for r in query_via_load_all(src, "x", "Story", filter={"status": "todo"})]
    names = sorted(r["metadata"]["name"] for r in rows)
    assert names == ["s-a", "s-c"]


@pytest.mark.asyncio
async def test_fallback_applies_projection():
    src = _FakeSource([
        _doc("Story", "s-a", title="Story A", status="todo", description="LONG_BODY"),
    ])
    rows = [r async for r in query_via_load_all(
        src, "x", "Story", projection=["spec.title", "spec.status"],
    )]
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "s-a"
    assert r["spec"]["title"] == "Story A"
    assert r["spec"]["status"] == "todo"
    assert "description" not in r.get("spec", {})


@pytest.mark.asyncio
async def test_fallback_applies_limit_offset():
    src = _FakeSource([_doc("Story", f"s-{i}", priority=i) for i in range(10)])
    rows = [r async for r in query_via_load_all(
        src, "x", "Story", limit=3, offset=2, order_by=["spec.priority"],
    )]
    assert [r["spec"]["priority"] for r in rows] == [2, 3, 4]


@pytest.mark.asyncio
async def test_fallback_applies_order_by_desc():
    src = _FakeSource([_doc("Story", f"s-{i}", priority=i) for i in range(5)])
    rows = [r async for r in query_via_load_all(
        src, "x", "Story", order_by=["-spec.priority"],
    )]
    priorities = [r["spec"]["priority"] for r in rows]
    assert priorities == [4, 3, 2, 1, 0]


@pytest.mark.asyncio
async def test_fallback_tenant_overlay_shadows_base():
    base = [_doc("Story", "s-shared", title="base"), _doc("Story", "s-only-base", title="x")]
    overlay = [_doc("Story", "s-shared", title="overlay"), _doc("Story", "s-only-overlay", title="y")]
    src = _FakeSource(base, overlay)
    rows = [r async for r in query_via_load_all(src, "x", "Story", tenant="acme")]
    by_name = {r["metadata"]["name"]: r for r in rows}
    assert by_name["s-shared"]["spec"]["title"] == "overlay"
    assert "s-only-base" in by_name
    assert "s-only-overlay" in by_name


@pytest.mark.asyncio
async def test_fallback_unknown_operator_raises():
    src = _FakeSource([_doc("Story", "s-a", status="todo")])
    with pytest.raises(QueryError):
        [_ async for _ in query_via_load_all(
            src, "x", "Story", filter={"status": {"regex": ".*"}},
        )]


@pytest.mark.asyncio
async def test_fallback_returns_full_raw_without_projection():
    src = _FakeSource([_doc("Story", "s-a", status="todo", description="X")])
    rows = [r async for r in query_via_load_all(src, "x", "Story")]
    assert rows[0]["spec"]["description"] == "X"
    assert rows[0]["kind"] == "Story"


@pytest.mark.asyncio
async def test_order_by_desc_nulls_last_parity_with_pg():
    """i-121: None deve ordenar POR ÚLTIMO também em DESC (paridade com
    o PG `DESC NULLS LAST`). Hoje o flag (v is None) com reverse=True
    inverte e None vai pra frente."""
    rows = [
        {"metadata": {"name": "null1"}, "spec": {}},
        {"metadata": {"name": "new"}, "spec": {"updated_at": "2026-06-10"}},
        {"metadata": {"name": "old"}, "spec": {"updated_at": "2026-06-01"}},
        {"metadata": {"name": "null2"}, "spec": {}},
    ]
    from dna.kernel.protocols import _apply_order_by
    out = _apply_order_by(rows, ["-spec.updated_at"])
    names = [(r.get("metadata") or {}).get("name") for r in out]
    assert names[:2] == ["new", "old"]
    assert set(names[2:]) == {"null1", "null2"}  # Nones SEMPRE no fim
