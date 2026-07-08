"""Postgres bundle round-trip tests (Phase 8 PR2).

Verifies that PostgresSource correctly stores and retrieves bundle kinds
(e.g. Skill with SKILL.md + scripts/) via the dna_bundle_entries table,
and that flat docs (Agent) don't populate that table.

Requires DATABASE_URL env var pointing at a running PostgreSQL instance.
    DATABASE_URL=postgresql://user:pass@localhost/dna_test pytest -k test_postgres_bundle
"""
from __future__ import annotations

import os
import pytest
import pytest_asyncio

from dna.extensions.agentskills import SkillReader, SkillWriter
from dna.kernel.bundle_handle import DictBundleHandle

# Skip entire module if no DATABASE_URL
pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.asyncio(loop_scope="module"),
]


# i-128: async fixture MUST be @pytest_asyncio.fixture — pytest-asyncio 1.x
# strict mode errors on async fixtures declared with plain @pytest.fixture
# (PytestRemovedIn9Warning → error). Mirrors test_postgres_source_count.py.
@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def source():
    """PostgresSource wired with Skill reader + writer, fresh schema."""
    import asyncpg
    from dna.adapters.postgres import PostgresSource

    dsn = os.environ["DATABASE_URL"]
    schema = "dna_test_bundle_v3"

    # Clean up schema from previous runs
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    pool = await asyncpg.create_pool(dsn)
    src = PostgresSource(
        pool, schema=schema,
        writers=[SkillWriter()],
        readers=[SkillReader()],
    )
    await src.init()

    # Seed a minimal Module
    module_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": "test-mod"},
        "spec": {"default_agent": "bot"},
    }
    await src.save_document("test-mod", "Genome", "test-mod", module_raw)
    await src.publish("test-mod", "Genome", "test-mod")

    yield src

    await src.close()
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.close()


def _make_skill_raw(name: str, instruction: str = "Do stuff.") -> dict:
    return {
        "apiVersion": "agentskills.io/v1",
        "kind": "Skill",
        "metadata": {"name": name},
        "spec": {
            "instruction": instruction,
            "scripts": {"run.py": "print('hello')\n"},
        },
    }


# ---------------------------------------------------------------------------
# 1. Round-trip Skill bundle
# ---------------------------------------------------------------------------

class TestSkillBundleRoundTripPostgres:
    async def test_write_and_load_all_returns_skill(self, source):
        """save_document(Skill) → publish → load_all returns parsed Skill dict."""
        raw = _make_skill_raw("pg-skill")
        await source.save_document("test-mod", "Skill", "pg-skill", raw)
        await source.publish("test-mod", "Skill", "pg-skill")

        # Direct-source usage (no kernel attached): the memoized
        # (scope, tenant) view from _load_view is invalidated by the
        # kernel's on_write observer in prod — here we must drop it by
        # hand or load_all serves the pre-save snapshot (i-128).
        source.invalidate_view("test-mod")
        docs = await source.load_all("test-mod")
        skill_docs = [d for d in docs if d.get("kind") == "Skill"]
        assert any(d["metadata"]["name"] == "pg-skill" for d in skill_docs)

    async def test_scripts_dir_preserved(self, source):
        """scripts/ subdirectory is stored in bundle_entries and recovered on load."""
        raw = _make_skill_raw("pg-scripted-skill", "Run something.")
        await source.save_document("test-mod", "Skill", "pg-scripted-skill", raw)
        await source.publish("test-mod", "Skill", "pg-scripted-skill")

        # See note in test_write_and_load_all_returns_skill (i-128).
        source.invalidate_view("test-mod")
        docs = await source.load_all("test-mod")
        skill = next(
            d for d in docs
            if d.get("metadata", {}).get("name") == "pg-scripted-skill"
        )
        assert "scripts" in skill["spec"]
        assert "run.py" in skill["spec"]["scripts"]
        assert "hello" in skill["spec"]["scripts"]["run.py"]

    async def test_bundle_entries_row_persisted(self, source):
        """dna_bundle_entries table has rows for the Skill bundle after save."""
        raw = _make_skill_raw("pg-entry-check")
        await source.save_document("test-mod", "Skill", "pg-entry-check", raw)

        entries = await source._load_bundle_entries("test-mod", "Skill", "pg-entry-check")
        assert "SKILL.md" in entries
        assert "scripts/run.py" in entries


# ---------------------------------------------------------------------------
# 2. DictBundleHandle → SkillReader directly
# ---------------------------------------------------------------------------

class TestDictBundleHandleWithSkillReaderPostgres:
    async def test_reader_round_trips_via_handle(self, source):
        """Build DictBundleHandle from stored entries → SkillReader.read() works."""
        raw = _make_skill_raw("pg-handle-skill", "Handle test.")
        await source.save_document("test-mod", "Skill", "pg-handle-skill", raw)

        entries = await source._load_bundle_entries("test-mod", "Skill", "pg-handle-skill")
        assert entries, "No bundle entries stored"

        handle = DictBundleHandle("pg-handle-skill", entries)
        reader = SkillReader()
        assert reader.detect(handle), "Reader did not detect SKILL.md"

        parsed = reader.read(handle)
        assert parsed["kind"] == "Skill"
        assert parsed["metadata"]["name"] == "pg-handle-skill"
        assert "Handle test." in parsed["spec"]["instruction"]


# ---------------------------------------------------------------------------
# 3. delete_document wipes bundle entries
# ---------------------------------------------------------------------------

class TestDeleteWipesEntriesPostgres:
    async def test_delete_removes_bundle_entries(self, source):
        """After delete_document, dna_bundle_entries has 0 rows for that doc."""
        raw = _make_skill_raw("pg-to-delete")
        await source.save_document("test-mod", "Skill", "pg-to-delete", raw)
        await source.publish("test-mod", "Skill", "pg-to-delete")

        entries_before = await source._load_bundle_entries("test-mod", "Skill", "pg-to-delete")
        assert len(entries_before) > 0, "Expected bundle entries before delete"

        await source.delete_document("test-mod", "Skill", "pg-to-delete")

        entries_after = await source._load_bundle_entries("test-mod", "Skill", "pg-to-delete")
        assert len(entries_after) == 0, "Bundle entries not wiped after delete"


# ---------------------------------------------------------------------------
# 4. Flat docs don't populate dna_bundle_entries
# ---------------------------------------------------------------------------

class TestFlatDocNoEntriesPostgres:
    async def test_agent_has_no_bundle_entries(self, source):
        """Agent (flat YAML) must not create rows in dna_bundle_entries."""
        agent_raw = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "pg-flat-bot"},
            "spec": {"instruction": "I am flat."},
        }
        await source.save_document("test-mod", "Agent", "pg-flat-bot", agent_raw)

        entries = await source._load_bundle_entries("test-mod", "Agent", "pg-flat-bot")
        assert len(entries) == 0, "Flat doc should have zero bundle entries"
