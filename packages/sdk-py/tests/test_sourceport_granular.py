"""Tests for SourcePort.list_doc_refs + load_one — L1 granular access.

Story s-sourceport-granular-protocol (f-source-granular-access).

Cobre os 3 adapters (PG/SQLite/Filesystem):
- list_doc_refs retorna (kind, name) tuples, filtrable por kind
- load_one retorna 1 doc + bundle entries, ou None se ausente
- tenant overlay: tenant shadows base; tenant=None = base only
- Round-trip: write → list_doc_refs vê → load_one retorna

PG adapter exige Postgres rodando em :5434. Skipped if DNA_PG_TEST_URL
não está setado.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from dna.adapters.filesystem.source import FilesystemSource
from dna.adapters.sqlalchemy_ import SqlAlchemySource


# Same env-name fallback chain as the requires_postgres marker gate
# (tests/conftest.py) — the marker passes when ANY of these is set, so the
# test must accept any of them too (s-public-ci: CI sets DATABASE_URL).
PG_TEST_URL = (
    os.environ.get("DNA_PG_TEST_URL")
    or os.environ.get("DNA_PG_TEST_DSN")
    or os.environ.get("DATABASE_URL")
)
pg_skip = pytest.mark.requires_postgres


# ─── Filesystem adapter ────────────────────────────────────────────────

class TestFilesystemGranular:
    @pytest.mark.asyncio
    async def test_list_doc_refs_returns_tuples(self, tmp_path):
        scope = "test-scope"
        scope_dir = tmp_path / scope
        scope_dir.mkdir()
        # 2 docs as flat YAMLs.
        (scope_dir / "a.yaml").write_text(
            "kind: Story\nmetadata:\n  name: s-a\nspec: {}\n",
        )
        (scope_dir / "b.yaml").write_text(
            "kind: Feature\nmetadata:\n  name: f-b\nspec: {}\n",
        )

        src = FilesystemSource(str(tmp_path))
        refs = await src.list_doc_refs(scope)
        assert ("Story", "s-a") in refs
        assert ("Feature", "f-b") in refs
        assert len(refs) == 2

    @pytest.mark.asyncio
    async def test_list_doc_refs_filter_by_kind(self, tmp_path):
        scope = "test-scope"
        scope_dir = tmp_path / scope
        scope_dir.mkdir()
        (scope_dir / "a.yaml").write_text(
            "kind: Story\nmetadata:\n  name: s-a\nspec: {}\n",
        )
        (scope_dir / "b.yaml").write_text(
            "kind: Feature\nmetadata:\n  name: f-b\nspec: {}\n",
        )

        src = FilesystemSource(str(tmp_path))
        refs = await src.list_doc_refs(scope, kind="Story")
        assert refs == [("Story", "s-a")]

    @pytest.mark.asyncio
    async def test_load_one_returns_doc_or_none(self, tmp_path):
        scope = "test-scope"
        scope_dir = tmp_path / scope
        scope_dir.mkdir()
        (scope_dir / "a.yaml").write_text(
            "kind: Story\nmetadata:\n  name: s-a\nspec:\n  title: hello\n",
        )

        src = FilesystemSource(str(tmp_path))
        doc = await src.load_one(scope, "Story", "s-a")
        assert doc is not None
        assert doc["kind"] == "Story"
        assert doc["spec"]["title"] == "hello"

        missing = await src.load_one(scope, "Story", "not-here")
        assert missing is None


# ─── SQLite adapter ────────────────────────────────────────────────────

class TestSqliteGranular:
    """SqlAlchemySource[sqlite] é writable diretamente (save_document) —
    mesma superfície nas duas dialetos."""

    @pytest.mark.asyncio
    async def test_list_doc_refs_after_write(self, tmp_path):
        db_path = tmp_path / "test.db"
        src = SqlAlchemySource(f"sqlite+aiosqlite:///{db_path}")
        await src.connect()
        # save_document auto-publishes (save is the publish point); the
        # explicit publish below is a harmless no-op re-promotion.
        await src.save_document("scope-x", "Story", "s-1", {
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
            "kind": "Story",
            "metadata": {"name": "s-1"},
            "spec": {"title": "first"},
        })
        await src.publish("scope-x", "Story", "s-1")
        await src.save_document("scope-x", "Feature", "f-1", {
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
            "kind": "Feature",
            "metadata": {"name": "f-1"},
            "spec": {"title": "feat"},
        })
        await src.publish("scope-x", "Feature", "f-1")

        refs = await src.list_doc_refs("scope-x")
        assert ("Story", "s-1") in refs
        assert ("Feature", "f-1") in refs

        only_stories = await src.list_doc_refs("scope-x", kind="Story")
        assert only_stories == [("Story", "s-1")]

    @pytest.mark.asyncio
    async def test_load_one_round_trip(self, tmp_path):
        db_path = tmp_path / "test.db"
        src = SqlAlchemySource(f"sqlite+aiosqlite:///{db_path}")
        await src.connect()
        raw = {
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
            "kind": "Story",
            "metadata": {"name": "s-rt"},
            "spec": {"title": "round-trip"},
        }
        await src.save_document("scope-y", "Story", "s-rt", raw)
        await src.publish("scope-y", "Story", "s-rt")

        doc = await src.load_one("scope-y", "Story", "s-rt")
        assert doc is not None
        assert doc["kind"] == "Story"
        assert doc["spec"]["title"] == "round-trip"

        missing = await src.load_one("scope-y", "Story", "not-here")
        assert missing is None


# ─── Postgres adapter ──────────────────────────────────────────────────

@pg_skip
class TestPostgresGranular:
    """Hits a real PG via DNA_PG_TEST_URL. Tests use unique scope slug
    per test to avoid pollution."""

    @pytest.mark.asyncio
    async def test_list_doc_refs_basic(self):
        import secrets
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        scope = f"test-{secrets.token_hex(4)}"
        sa_url = PG_TEST_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        src = SqlAlchemySource(sa_url)
        await src.connect()
        try:
            await src.save_document(scope, "Story", "s-1", {
                "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
                "kind": "Story",
                "metadata": {"name": "s-1"},
                "spec": {"title": "pg test"},
            })
            refs = await src.list_doc_refs(scope)
            assert ("Story", "s-1") in refs
        finally:
            try:
                await src.delete_document(scope, "Story", "s-1")
            except Exception:  # noqa: BLE001
                pass
            await src.close()

    @pytest.mark.asyncio
    async def test_load_one_round_trip(self):
        import secrets
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        scope = f"test-{secrets.token_hex(4)}"
        sa_url = PG_TEST_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        src = SqlAlchemySource(sa_url)
        await src.connect()
        try:
            raw = {
                "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
                "kind": "Story",
                "metadata": {"name": "s-pg-rt"},
                "spec": {"title": "round-trip-pg"},
            }
            await src.save_document(scope, "Story", "s-pg-rt", raw)
            doc = await src.load_one(scope, "Story", "s-pg-rt")
            assert doc is not None
            assert doc["spec"]["title"] == "round-trip-pg"

            missing = await src.load_one(scope, "Story", "no-such")
            assert missing is None
        finally:
            try:
                await src.delete_document(scope, "Story", "s-pg-rt")
            except Exception:  # noqa: BLE001
                pass
            await src.close()
