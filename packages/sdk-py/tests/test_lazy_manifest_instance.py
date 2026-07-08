"""Tests for LazyManifestInstance — Marco B core.

Story s-lazy-manifest-instance-class (Feature f-lazy-manifest-instance,
Epic e-production-viable-kernel).

Three test classes:
  - **Construction**: lazy mode wires correctly, bootstrap docs only.
  - **Lazy access**: one() / all() delegate to kernel without forcing
    full materialization.
  - **Back-compat**: eager mode (lazy=False) behavior unchanged; the
    documents property still works; access in lazy mode warns +
    materializes.
"""
from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

from dna.kernel.document import Document
from dna.kernel.instance import ManifestInstance


def _doc(kind: str, name: str, **spec) -> Document:
    """Build a Document with minimum required shape."""
    raw = {
        "apiVersion": "github.com/ruinosus/dna/test/v1",
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }
    return Document.from_raw(raw)


def _bootstrap_docs():
    return [
        _doc("Genome", "demo", owner="platform"),
        _doc("KindDefinition", "Custom", spec={}),
        _doc("LayerPolicy", "tenant", policies={}),
    ]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_eager_mode(self):
        """Without lazy=True, behaves exactly as before."""
        mi = ManifestInstance(
            scope="demo",
            documents=[_doc("Story", "s-a")],
            kinds={},
        )
        assert mi._lazy is False
        assert mi._lazy_full_loaded is True
        # documents accessible without warning
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            docs = mi.documents
        assert len(docs) == 1

    def test_lazy_mode_keeps_only_bootstrap(self):
        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            lazy=True,
        )
        assert mi._lazy is True
        assert mi._lazy_full_loaded is False
        # Bootstrap visible via internal access
        assert len(mi._documents) == 3


# ---------------------------------------------------------------------------
# Lazy access
# ---------------------------------------------------------------------------


class TestLazyAccess:
    @pytest.mark.asyncio
    async def test_one_hits_bootstrap_directly(self):
        """Bootstrap kinds are served from the in-memory list — no
        kernel call."""
        kernel = MagicMock()
        kernel.get_document = MagicMock(side_effect=AssertionError("should not be called"))
        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            kernel=kernel,
            lazy=True,
        )
        doc = mi.one("Genome", "demo")
        assert doc is not None
        assert doc.kind == "Genome"

    @pytest.mark.asyncio
    async def test_all_hits_bootstrap_directly(self):
        kernel = MagicMock()
        kernel.query = MagicMock(side_effect=AssertionError("should not be called"))
        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            kernel=kernel,
            lazy=True,
        )
        pkgs = mi.all("Genome")
        assert len(pkgs) == 1
        assert pkgs[0].name == "demo"

    @pytest.mark.asyncio
    async def test_one_non_bootstrap_delegates_to_kernel_get(self):
        """Non-bootstrap kind: lazy MI delegates to kernel.get_document_sync.

        s-miholder-transient / F8.7: lazy ``one()`` routes through the
        sync wrapper ``kernel.get_document_sync`` (loop-safe) which
        returns an already-parsed Document — not raw + _parse_doc.
        """
        target_doc = Document.from_raw({
            "apiVersion": "github.com/ruinosus/dna/test/v1",
            "kind": "Story",
            "metadata": {"name": "s-foo"},
            "spec": {"title": "Hello"},
        })

        def _get_document_sync(scope, kind, name, *, tenant=None):
            assert scope == "demo"
            assert kind == "Story"
            assert name == "s-foo"
            return target_doc

        kernel = MagicMock()
        kernel.get_document_sync = _get_document_sync

        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            kernel=kernel,
            lazy=True,
        )
        doc = mi.one("Story", "s-foo")
        assert doc is not None
        assert doc.kind == "Story"
        assert doc.spec["title"] == "Hello"

    @pytest.mark.asyncio
    async def test_all_non_bootstrap_delegates_to_kernel_query(self):
        rows = [
            {"apiVersion": "github.com/ruinosus/dna/test/v1", "kind": "Story",
             "metadata": {"name": f"s-{i}"}, "spec": {"priority": i}}
            for i in range(3)
        ]

        def _query_list_sync(scope, kind, **kwargs):
            return [Document.from_raw(r) for r in rows]

        kernel = MagicMock()
        # Story s-miholder-transient: mi._lazy_load_kind now uses
        # kernel.query_list_sync (sync wrapper that routes via
        # _run_sync_helper for asyncpg pool safety). Mock that surface.
        kernel.query_list_sync = _query_list_sync

        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            kernel=kernel,
            lazy=True,
        )
        stories = mi.all("Story")
        assert len(stories) == 3
        assert {s.name for s in stories} == {"s-0", "s-1", "s-2"}

    @pytest.mark.asyncio
    async def test_all_non_bootstrap_caches_kind(self):
        """Second call for same kind hits the in-mi cache, not kernel."""
        call_count = {"n": 0}

        def _query_list_sync(scope, kind, **kwargs):
            call_count["n"] += 1
            return [Document.from_raw({
                "apiVersion": "github.com/ruinosus/dna/test/v1", "kind": "Story",
                "metadata": {"name": "s-a"}, "spec": {},
            })]

        kernel = MagicMock()
        kernel.query_list_sync = _query_list_sync

        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            kernel=kernel,
            lazy=True,
        )
        mi.all("Story")
        mi.all("Story")
        mi.all("Story")
        assert call_count["n"] == 1

    @pytest.mark.asyncio
    async def test_one_returns_none_when_kernel_returns_none(self):
        def _get_document_sync(scope, kind, name, *, tenant=None):
            return None

        kernel = MagicMock()
        kernel.get_document_sync = _get_document_sync

        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            kernel=kernel,
            lazy=True,
        )
        assert mi.one("Story", "nonexistent") is None


# ---------------------------------------------------------------------------
# Back-compat boundary
# ---------------------------------------------------------------------------


class TestBackCompat:
    def test_accessing_documents_in_lazy_warns(self):
        """The .documents property in lazy mode emits DeprecationWarning
        + forces full load via source.load_all.

        Sync test on purpose: the ``.documents`` property is synchronous
        and drives ``_materialize_full`` via ``_run_sync_helper``. Under
        the s-mi-class-death contract, that helper raises if called from
        inside a running event loop with no cross-thread dispatch loop.
        Running synchronously lets it reach the ``asyncio.run`` path
        (kernel._main_loop is None here)."""
        async def _load_all(scope, readers=None):
            return [{
                "apiVersion": "github.com/ruinosus/dna/test/v1", "kind": "Story",
                "metadata": {"name": "s-loaded"}, "spec": {},
            }]

        source = MagicMock()
        source.load_all = _load_all
        kernel = MagicMock()
        kernel._readers = []
        kernel._main_loop = None  # _run_sync_helper falls to asyncio.run (Case 3)
        kernel._parse_doc = lambda raw, origin="local": Document.from_raw(raw)

        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            source=source,
            kernel=kernel,
            lazy=True,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            docs = mi.documents
            # First access materializes + warns
            assert any(
                "lazy mode" in str(x.message) for x in w
            ), f"expected DeprecationWarning, got {[str(x.message) for x in w]}"

        # Now full set should include both bootstrap + loaded.
        names = {d.name for d in docs}
        assert "demo" in names  # bootstrap Genome
        assert "s-loaded" in names  # loaded via load_all

    def test_subsequent_documents_access_no_warning(self):
        """After materialization, subsequent .documents access is silent.

        Sync test on purpose — see test_accessing_documents_in_lazy_warns."""
        async def _load_all(scope, readers=None):
            return []

        source = MagicMock()
        source.load_all = _load_all
        kernel = MagicMock()
        kernel._readers = []
        kernel._main_loop = None  # _run_sync_helper falls to asyncio.run (Case 3)
        kernel._parse_doc = lambda raw, origin="local": Document.from_raw(raw)

        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            source=source,
            kernel=kernel,
            lazy=True,
        )
        # First access (warns + loads)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _ = mi.documents

        # Second access — silent
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _ = mi.documents


# ---------------------------------------------------------------------------
# All-where forces materialization (cross-kind walk)
# ---------------------------------------------------------------------------


class TestAllWhere:
    def test_all_where_forces_full_load(self):
        async def _load_all(scope, readers=None):
            return [
                {"apiVersion": "github.com/ruinosus/dna/test/v1", "kind": "Story",
                 "metadata": {"name": "s-a"}, "spec": {}},
            ]

        source = MagicMock()
        source.load_all = _load_all
        kernel = MagicMock()
        kernel._readers = []
        kernel._main_loop = None  # _run_sync_helper falls to asyncio.run (Case 3)
        kernel._parse_doc = lambda raw, origin="local": Document.from_raw(raw)

        mi = ManifestInstance(
            scope="demo",
            documents=_bootstrap_docs(),
            kinds={},
            source=source,
            kernel=kernel,
            lazy=True,
        )
        # all_where predicate doesn't filter; just confirm flow
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mi.all_where(lambda kp: True)
        # No KindPorts registered, predicate sees nothing valid
        # But the materialization happened (state flipped)
        assert mi._lazy_full_loaded is True
