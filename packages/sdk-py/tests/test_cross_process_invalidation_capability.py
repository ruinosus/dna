"""s-sqlite-cross-process-invalidation — adapters declare, via a typed flag,
whether they propagate writes across processes. Postgres does (outbox +
LISTEN/NOTIFY, Phase 15.1); SQLite + filesystem do not, so multi-process
deployments on them would serve stale data — the flag makes that explicit and
introspectable (the source_factory turns it into a loud boot warning / refusal).
"""
from __future__ import annotations

import tempfile


def test_sqlite_declares_no_cross_process_invalidation():
    from dna.adapters.sqlite.source import SqliteSource
    assert SqliteSource.supports_cross_process_invalidation is False


def test_filesystem_declares_no_cross_process_invalidation():
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    src = FilesystemWritableSource(base_dir=tempfile.mkdtemp())
    assert src.supports_cross_process_invalidation is False


def test_postgres_declares_cross_process_invalidation():
    # Class attribute — no live database needed.
    from dna.adapters.postgres.source import PostgresSource
    assert PostgresSource.supports_cross_process_invalidation is True
