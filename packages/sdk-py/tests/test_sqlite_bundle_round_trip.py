"""SQLite bundle round-trip tests (Phase 8 PR2).

Verifies that SqliteSource correctly stores and retrieves bundle kinds
(e.g. Skill with SKILL.md + scripts/) via the dna_bundle_entries table,
and that flat docs (Agent) don't populate that table.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from dna.adapters.sqlite import SqliteSource
from dna.extensions.agentskills import SkillReader, SkillWriter
from dna.kernel.bundle_handle import DictBundleHandle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def source(tmp_path):
    """SqliteSource wired with Skill reader + writer."""
    db = tmp_path / "test_bundle.db"
    src = SqliteSource(
        str(db),
        writers=[SkillWriter()],
        readers=[SkillReader()],
    )
    await src.connect()
    # Seed a minimal Module so scope is valid
    module_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": "test-mod"},
        "spec": {"default_agent": "bot"},
    }
    await src.save_document("test-mod", "Genome", "test-mod", module_raw)
    await src.publish("test-mod", "Genome", "test-mod")
    yield src
    await src.close()


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

class TestSkillBundleRoundTrip:
    @pytest.mark.asyncio
    async def test_write_and_load_all_returns_skill(self, source):
        """save_document(Skill) → publish → load_all returns parsed Skill dict."""
        raw = _make_skill_raw("my-skill")
        await source.save_document("test-mod", "Skill", "my-skill", raw)
        await source.publish("test-mod", "Skill", "my-skill")

        docs = await source.load_all("test-mod")
        skill_docs = [d for d in docs if d.get("kind") == "Skill"]
        assert len(skill_docs) == 1

        skill = skill_docs[0]
        assert skill["metadata"]["name"] == "my-skill"
        assert "Do stuff." in skill["spec"]["instruction"]

    @pytest.mark.asyncio
    async def test_scripts_dir_preserved(self, source):
        """scripts/ subdirectory is stored in bundle_entries and recovered on load."""
        raw = _make_skill_raw("scripted-skill", "Run something.")
        await source.save_document("test-mod", "Skill", "scripted-skill", raw)
        await source.publish("test-mod", "Skill", "scripted-skill")

        docs = await source.load_all("test-mod")
        skill = next(d for d in docs if d.get("metadata", {}).get("name") == "scripted-skill")
        assert "scripts" in skill["spec"]
        assert "run.py" in skill["spec"]["scripts"]
        assert "hello" in skill["spec"]["scripts"]["run.py"]

    @pytest.mark.asyncio
    async def test_bundle_entries_row_persisted(self, source, tmp_path):
        """dna_bundle_entries table has rows for the Skill bundle after save."""
        raw = _make_skill_raw("entry-check-skill")
        await source.save_document("test-mod", "Skill", "entry-check-skill", raw)
        # Directly query the table to verify rows exist
        entries = await source._load_bundle_entries("test-mod", "Skill", "entry-check-skill")
        assert "SKILL.md" in entries
        assert "scripts/run.py" in entries


# ---------------------------------------------------------------------------
# 2. DictBundleHandle → SkillReader directly
# ---------------------------------------------------------------------------

class TestDictBundleHandleWithSkillReader:
    @pytest.mark.asyncio
    async def test_reader_round_trips_via_handle(self, source):
        """Build DictBundleHandle from stored entries → SkillReader.read() works."""
        raw = _make_skill_raw("handle-skill", "Handle test.")
        await source.save_document("test-mod", "Skill", "handle-skill", raw)

        entries = await source._load_bundle_entries("test-mod", "Skill", "handle-skill")
        assert entries, "No bundle entries stored"

        handle = DictBundleHandle("handle-skill", entries)
        reader = SkillReader()
        assert reader.detect(handle), "Reader did not detect SKILL.md"

        parsed = reader.read(handle)
        assert parsed["kind"] == "Skill"
        assert parsed["metadata"]["name"] == "handle-skill"
        assert "Handle test." in parsed["spec"]["instruction"]


# ---------------------------------------------------------------------------
# 3. delete_document wipes bundle entries
# ---------------------------------------------------------------------------

class TestDeleteWipesEntries:
    @pytest.mark.asyncio
    async def test_delete_removes_bundle_entries(self, source):
        """After delete_document, bundle_entries table has 0 rows for that doc."""
        raw = _make_skill_raw("to-delete-skill")
        await source.save_document("test-mod", "Skill", "to-delete-skill", raw)
        await source.publish("test-mod", "Skill", "to-delete-skill")

        entries_before = await source._load_bundle_entries("test-mod", "Skill", "to-delete-skill")
        assert len(entries_before) > 0, "Expected bundle entries before delete"

        await source.delete_document("test-mod", "Skill", "to-delete-skill")

        entries_after = await source._load_bundle_entries("test-mod", "Skill", "to-delete-skill")
        assert len(entries_after) == 0, "Bundle entries not wiped after delete"


# ---------------------------------------------------------------------------
# 4. Flat docs don't populate bundle_entries
# ---------------------------------------------------------------------------

class TestFlatDocNoEntries:
    @pytest.mark.asyncio
    async def test_agent_has_no_bundle_entries(self, source):
        """Agent (flat YAML) must not create rows in bundle_entries."""
        agent_raw = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "flat-bot"},
            "spec": {"instruction": "I am flat."},
        }
        await source.save_document("test-mod", "Agent", "flat-bot", agent_raw)

        entries = await source._load_bundle_entries("test-mod", "Agent", "flat-bot")
        assert len(entries) == 0, "Flat doc should have zero bundle entries"
