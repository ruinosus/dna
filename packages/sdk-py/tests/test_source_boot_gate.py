"""s-dna-source-conformance-kit — kernel.source() boot gate.

A malformed source used to pass ``kernel.source(src)`` silently and blow
up deep inside the first load. The gate fails loud AT BOOT, naming the
missing members and pointing at docs/PORT-CONTRACT.md + the public
conformance kit. Names-only by design (runtime_checkable semantics);
behavior is the kit's job.
"""
from __future__ import annotations

import logging

import pytest

from dna.kernel import Kernel
from dna.kernel.errors import SourceRegistrationError
from dna.kernel.protocols import (
    SOURCE_PORT_CORE_MEMBERS,
    SOURCE_PORT_FALLBACK_MEMBERS,
    missing_source_port_members,
)


class _CoreOnlySource:
    """The legitimate minimum: core surface, no granular/query methods
    (the kernel serves those via fallbacks)."""

    supports_readers = False

    async def load_bootstrap_docs(self, scope, *, tenant=None):
        return []

    async def load_all(self, scope, readers=None):
        return []

    async def resolve_ref(self, scope, ref):
        return ref

    async def load_layer(self, scope, layer_id, layer_value, readers=None):
        return []

    async def close(self):
        return None


def test_real_adapter_passes_gate(tmp_path):
    from dna.adapters.filesystem.writable import FilesystemWritableSource

    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    assert k._source is not None


def test_missing_core_member_fails_loud_and_didactic():
    class _Broken:
        """No load_all, no close — not a source at all."""
        supports_readers = False

        async def load_bootstrap_docs(self, scope, *, tenant=None):
            return []

    k = Kernel()
    with pytest.raises(SourceRegistrationError) as ei:
        k.source(_Broken())
    msg = str(ei.value)
    assert "load_all" in msg and "close" in msg          # names the gaps
    assert "PORT-CONTRACT.md" in msg                     # points at the doc
    assert "source_conformance_suite" in msg             # points at the kit
    assert "NAMES only" in msg                           # scope of the check
    assert k._source is None, "a rejected source must NOT be registered"


def test_core_only_source_accepted_with_fallback_warning(caplog):
    k = Kernel()
    with caplog.at_level(logging.WARNING, logger="dna.kernel.protocols"):
        k.source(_CoreOnlySource())
    assert k._source is not None
    warned = " ".join(r.getMessage() for r in caplog.records)
    assert "query" in warned and "fallback" in warned


def test_async_adapter_over_sync_core_source_passes_gate():
    """Wrappers are validated as the object handed to the kernel — the
    transparent proxy mirrors the wrapped source's (sync) core surface."""
    from dna.adapters.async_adapter import AsyncSourceAdapter

    class _SyncCore:
        supports_readers = False

        def load_bootstrap_docs(self, scope, *, tenant=None):
            return []

        def load_all(self, scope, readers=None):
            return []

        def resolve_ref(self, scope, ref):
            return ref

        def load_layer(self, scope, layer_id, layer_value, readers=None):
            return []

        def close(self):
            return None

    k = Kernel()
    k.source(AsyncSourceAdapter(_SyncCore()))
    assert k._source is not None


def test_async_adapter_over_incomplete_source_rejected():
    """The proxy never invents surface: wrapping something that isn't a
    source doesn't sneak it past the gate."""
    from dna.adapters.async_adapter import AsyncSourceAdapter

    class _NotASource:
        def load_all(self, scope, readers=None):
            return []

    k = Kernel()
    with pytest.raises(SourceRegistrationError, match="close"):
        k.source(AsyncSourceAdapter(_NotASource()))


def test_missing_member_helper_partitions_core_vs_fallback():
    core, fallback = missing_source_port_members(_CoreOnlySource())
    assert core == []
    assert set(fallback) == set(SOURCE_PORT_FALLBACK_MEMBERS)
    assert set(SOURCE_PORT_CORE_MEMBERS) & set(SOURCE_PORT_FALLBACK_MEMBERS) == set()


def test_all_in_repo_adapters_pass_gate(tmp_path):
    """The gate must accept every real adapter (harness source_factory
    builds these) — regression guard for consumers."""
    from dna.adapters.filesystem.composite import CompositeFilesystemSource
    from dna.adapters.filesystem.source import FilesystemSource
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    sources = [
        FilesystemSource(tmp_path),
        FilesystemWritableSource(str(tmp_path)),
        CompositeFilesystemSource(tmp_path),
        SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'gate.db'}"),
        SqlAlchemySource("postgresql+asyncpg://u:p@nowhere.invalid/db"),
    ]
    for src in sources:
        k = Kernel()
        k.source(src)
        assert k._source is src, type(src).__name__
