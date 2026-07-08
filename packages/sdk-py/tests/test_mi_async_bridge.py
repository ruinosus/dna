"""Tests for the MI async bridge (Story s-mi-async-bridge, f-mi-class-extinction).

Verifies:
  1. ``mi.all_async(kind)`` returns list[Document] via ``await kernel.query``
  2. ``mi.one_async(kind, name)`` returns Document | None via
     ``await kernel.get_document``
  3. Sync ``mi.all()`` and ``mi.one()`` emit DeprecationWarning
  4. Bootstrap kinds short-circuit (no kernel.query call)
  5. Lazy-cache fast-path on subsequent calls
"""
from __future__ import annotations

import warnings
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from dna.kernel.document import Document
from dna.kernel.instance import ManifestInstance


def _doc(kind: str, name: str) -> Document:
    return Document(
        api_version="v1", kind=kind, name=name,
        metadata={"name": name}, spec={},
    )


def _fake_kernel(query_rows: list[dict], get_row: dict | None = None) -> SimpleNamespace:
    """Fake kernel exposing query (async generator) + get_document (coro) +
    _parse_doc (sync)."""

    async def _query(scope, kind, **kw):
        for r in query_rows:
            yield r

    async def _get_document(scope, kind, name, **kw):
        return get_row

    def _parse_doc(raw, origin="local"):
        if not raw:
            return None
        meta = raw.get("metadata", {})
        return Document(
            api_version=raw.get("apiVersion", "v1"),
            kind=raw["kind"],
            name=meta.get("name", ""),
            metadata=meta,
            spec=raw.get("spec", {}),
        )

    k = SimpleNamespace()
    k.query = _query
    k.get_document = _get_document
    k._parse_doc = _parse_doc
    return k


@pytest.mark.asyncio
async def test_all_async_delegates_to_kernel_query():
    kernel = _fake_kernel(
        query_rows=[
            {"kind": "Story", "metadata": {"name": "s-a"}, "spec": {}},
            {"kind": "Story", "metadata": {"name": "s-b"}, "spec": {}},
        ],
    )
    mi = ManifestInstance(
        scope="test", documents=[], kinds={}, kernel=kernel, lazy=True,
    )
    result = await mi.all_async("Story")
    assert len(result) == 2
    assert {d.name for d in result} == {"s-a", "s-b"}


@pytest.mark.asyncio
async def test_one_async_delegates_to_kernel_get_document():
    kernel = _fake_kernel(
        query_rows=[],
        get_row={"kind": "Story", "metadata": {"name": "s-x"}, "spec": {}},
    )
    mi = ManifestInstance(
        scope="test", documents=[], kinds={}, kernel=kernel, lazy=True,
    )
    doc = await mi.one_async("Story", "s-x")
    assert doc is not None
    assert doc.name == "s-x"


@pytest.mark.asyncio
async def test_one_async_returns_none_when_not_found():
    kernel = _fake_kernel(query_rows=[], get_row=None)
    mi = ManifestInstance(
        scope="test", documents=[], kinds={}, kernel=kernel, lazy=True,
    )
    doc = await mi.one_async("Story", "missing")
    assert doc is None


@pytest.mark.asyncio
async def test_all_async_bootstrap_kinds_short_circuit():
    """Genome/KindDefinition/LayerPolicy are in self._documents — no
    kernel.query call should happen."""
    bootstrap = [_doc("Genome", "test-pkg")]
    kernel = MagicMock()
    kernel.query = AsyncMock()  # would fail if called
    mi = ManifestInstance(
        scope="test", documents=bootstrap, kinds={}, kernel=kernel, lazy=True,
    )
    result = await mi.all_async("Genome")
    assert len(result) == 1
    assert result[0].name == "test-pkg"
    kernel.query.assert_not_called()


@pytest.mark.asyncio
async def test_all_async_lazy_cache_hit():
    """Second call to all_async hits the lazy cache, no second kernel.query."""
    rows = [{"kind": "Story", "metadata": {"name": "s-a"}, "spec": {}}]
    call_count = {"n": 0}

    async def _query(scope, kind, **kw):
        call_count["n"] += 1
        for r in rows:
            yield r

    def _parse_doc(raw, origin="local"):
        return Document(
            api_version="v1", kind=raw["kind"],
            name=raw["metadata"]["name"],
            metadata=raw["metadata"], spec=raw["spec"],
        )

    kernel = SimpleNamespace(query=_query, _parse_doc=_parse_doc)
    mi = ManifestInstance(
        scope="test", documents=[], kinds={}, kernel=kernel, lazy=True,
    )
    await mi.all_async("Story")
    await mi.all_async("Story")
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_all_async_eager_mode_walks_self_documents():
    """Eager-mode MI never queries kernel — walks self._documents."""
    docs = [_doc("Story", "s-a"), _doc("Story", "s-b"), _doc("Feature", "f-x")]
    kernel = MagicMock()
    kernel.query = AsyncMock()
    mi = ManifestInstance(
        scope="test", documents=docs, kinds={}, kernel=kernel, lazy=False,
    )
    result = await mi.all_async("Story")
    assert len(result) == 2
    kernel.query.assert_not_called()


def test_sync_all_emits_deprecation_warning():
    """Sync mi.all() emits DeprecationWarning pointing at the blessed
    surface (s-blessed-query-surface)."""
    mi = ManifestInstance(scope="t", documents=[], kinds={}, lazy=False)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        mi.all("Story")
    assert any(
        issubclass(item.category, DeprecationWarning)
        and "all()" in str(item.message)
        and "mi.documents" in str(item.message)
        and "kernel.query" in str(item.message)
        for item in w
    ), f"expected DeprecationWarning for mi.all(); got {[str(x.message) for x in w]}"


def test_sync_one_emits_deprecation_warning():
    """Sync mi.one() emits DeprecationWarning pointing at the blessed
    surface (s-blessed-query-surface)."""
    mi = ManifestInstance(scope="t", documents=[], kinds={}, lazy=False)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        mi.one("Story", "s-a")
    assert any(
        issubclass(item.category, DeprecationWarning)
        and "one()" in str(item.message)
        and "mi.documents" in str(item.message)
        and "kernel.get_document" in str(item.message)
        for item in w
    ), f"expected DeprecationWarning for mi.one(); got {[str(x.message) for x in w]}"


def test_deprecation_message_states_removal_release():
    """Warning message must state the removal release (1.0) so callers
    know the shim's lifetime (s-blessed-query-surface)."""
    mi = ManifestInstance(scope="t", documents=[], kinds={}, lazy=False)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        mi.all("Story")
    msgs = [str(item.message) for item in w if issubclass(item.category, DeprecationWarning)]
    assert any("will be removed in 1.0" in m for m in msgs)
