# python/tests/test_sync_engine.py
"""Tests for the SyncEngine module."""
import os

import pytest
import pytest_asyncio

from dna.sync.hash import document_hash
from dna.sync.snapshot import SyncSnapshot
from dna.sync.diff import compute_diff, SyncItem


class TestDocumentHash:
    def test_deterministic(self):
        raw = {"kind": "Skill", "name": "test", "spec": {"description": "hello"}}
        h1 = document_hash(raw)
        h2 = document_hash(raw)
        assert h1 == h2

    def test_key_order_independent(self):
        raw_a = {"kind": "Skill", "name": "test", "spec": {"a": 1, "b": 2}}
        raw_b = {"spec": {"b": 2, "a": 1}, "name": "test", "kind": "Skill"}
        assert document_hash(raw_a) == document_hash(raw_b)

    def test_different_content_different_hash(self):
        raw_a = {"kind": "Skill", "name": "test", "spec": {"description": "hello"}}
        raw_b = {"kind": "Skill", "name": "test", "spec": {"description": "world"}}
        assert document_hash(raw_a) != document_hash(raw_b)

    def test_compatible_with_lockfile(self):
        """Hash should match the lockfile's SHA-256 computation."""
        import hashlib, json
        raw = {"kind": "Skill", "name": "test"}
        expected = hashlib.sha256(
            json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        assert document_hash(raw) == expected


class TestSyncSnapshot:
    @pytest.mark.asyncio
    async def test_empty_snapshot(self, tmp_path):
        path = tmp_path / ".dna.sync"
        snap = await SyncSnapshot.load(str(path))
        assert snap.scope is None
        assert snap.documents == {}

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path):
        path = tmp_path / ".dna.sync"
        snap = SyncSnapshot(
            scope="open-swe",
            documents={
                ("Skill", "pr-review"): "abc123",
                ("Agent", "swe-agent"): "def456",
            },
        )
        await snap.save(str(path))
        assert path.exists()

        loaded = await SyncSnapshot.load(str(path))
        assert loaded.scope == "open-swe"
        assert loaded.documents[("Skill", "pr-review")] == "abc123"
        assert loaded.documents[("Agent", "swe-agent")] == "def456"

    @pytest.mark.asyncio
    async def test_update_hashes(self, tmp_path):
        path = tmp_path / ".dna.sync"
        snap = SyncSnapshot(scope="test", documents={("Skill", "a"): "old"})
        snap.documents[("Skill", "a")] = "new"
        snap.documents[("Skill", "b")] = "added"
        await snap.save(str(path))

        loaded = await SyncSnapshot.load(str(path))
        assert loaded.documents[("Skill", "a")] == "new"
        assert loaded.documents[("Skill", "b")] == "added"


class TestComputeDiff:
    def test_no_changes(self):
        snapshot = {("Skill", "a"): "hash1"}
        side_a = {("Skill", "a"): "hash1"}
        side_b = {("Skill", "a"): "hash1"}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.skipped) == 1
        assert len(result.pushed) == 0
        assert len(result.pulled) == 0
        assert len(result.conflicts) == 0

    def test_push_a_changed(self):
        snapshot = {("Skill", "a"): "old"}
        side_a = {("Skill", "a"): "new"}
        side_b = {("Skill", "a"): "old"}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.pushed) == 1
        assert result.pushed[0].kind == "Skill"
        assert result.pushed[0].name == "a"

    def test_pull_b_changed(self):
        snapshot = {("Skill", "a"): "old"}
        side_a = {("Skill", "a"): "old"}
        side_b = {("Skill", "a"): "new"}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.pulled) == 1

    def test_conflict_both_changed(self):
        snapshot = {("Skill", "a"): "old"}
        side_a = {("Skill", "a"): "new_a"}
        side_b = {("Skill", "a"): "new_b"}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.conflicts) == 1

    def test_new_in_a(self):
        snapshot = {}
        side_a = {("Skill", "new"): "hash1"}
        side_b = {}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.pushed) == 1

    def test_new_in_b(self):
        snapshot = {}
        side_a = {}
        side_b = {("Skill", "new"): "hash1"}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.pulled) == 1

    def test_deleted_from_a(self):
        snapshot = {("Skill", "a"): "hash1"}
        side_a = {}
        side_b = {("Skill", "a"): "hash1"}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.pushed) == 1
        assert result.pushed[0].action == "delete_b"

    def test_deleted_from_b(self):
        snapshot = {("Skill", "a"): "hash1"}
        side_a = {("Skill", "a"): "hash1"}
        side_b = {}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.pulled) == 1
        assert result.pulled[0].action == "delete_a"

    def test_delete_modify_conflict(self):
        snapshot = {("Skill", "a"): "old"}
        side_a = {}
        side_b = {("Skill", "a"): "modified"}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.conflicts) == 1

    def test_both_deleted(self):
        snapshot = {("Skill", "a"): "old"}
        side_a = {}
        side_b = {}
        result = compute_diff(snapshot, side_a, side_b)
        assert len(result.skipped) == 0
        assert len(result.pushed) == 0
        # Should just be removed from snapshot silently


import yaml as pyyaml
from dna.sync import SyncEngine
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.adapters.sqlalchemy_ import SqlAlchemySource


def _create_fs_module(base_dir: str, scope: str, docs: list[dict]) -> None:
    """Helper: write a minimal manifest + documents to filesystem."""
    scope_dir = os.path.join(base_dir, scope)
    os.makedirs(scope_dir, exist_ok=True)
    # Write manifest
    manifest = {"kind": "Genome", "name": scope, "spec": {"agents": [], "skills": []}}
    with open(os.path.join(scope_dir, "manifest.yaml"), "w") as f:
        pyyaml.dump(manifest, f)
    # Write documents
    for doc in docs:
        kind = doc["kind"]
        name = doc.get("name") or doc.get("metadata", {}).get("name")
        subdir = {"Agent": "agents", "Skill": "skills", "Guardrail": "guardrails"}.get(kind, "")
        if subdir:
            doc_dir = os.path.join(scope_dir, subdir)
            os.makedirs(doc_dir, exist_ok=True)
            with open(os.path.join(doc_dir, f"{name}.yaml"), "w") as f:
                pyyaml.dump(doc, f)


class TestSyncEngineIntegration:
    @pytest.mark.asyncio
    async def test_first_sync_pushes_all(self, tmp_path):
        """First sync with no snapshot — everything in A should be pushed to B."""
        fs_dir = str(tmp_path / "fs")
        os.makedirs(fs_dir)
        docs = [
            {"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o", "skills": []}},
        ]
        _create_fs_module(fs_dir, "test-mod", docs)

        fs = FilesystemWritableSource(fs_dir)
        db = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
        await db.connect()

        snap_path = str(tmp_path / ".dna.sync")
        engine = SyncEngine(fs, db)
        result = await engine.push("test-mod", snapshot_path=snap_path)

        assert len(result.pushed) > 0
        assert len(result.errors) == 0
        # Verify document exists in DB
        db_docs = await db.load_all("test-mod")
        agent_names = [d.get("name") for d in db_docs if d.get("kind") == "Agent"]
        assert "bot" in agent_names
        await db.close()

    @pytest.mark.asyncio
    async def test_no_changes_after_sync(self, tmp_path):
        """After push, a second sync should show no changes."""
        fs_dir = str(tmp_path / "fs")
        os.makedirs(fs_dir)
        docs = [
            {"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o", "skills": []}},
        ]
        _create_fs_module(fs_dir, "test-mod", docs)

        fs = FilesystemWritableSource(fs_dir)
        db = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
        await db.connect()

        snap_path = str(tmp_path / ".dna.sync")
        engine = SyncEngine(fs, db)
        await engine.push("test-mod", snapshot_path=snap_path)

        result2 = await engine.sync("test-mod", snapshot_path=snap_path)
        assert len(result2.pushed) == 0
        assert len(result2.pulled) == 0
        assert len(result2.skipped) > 0
        await db.close()

    @pytest.mark.asyncio
    async def test_dry_run(self, tmp_path):
        """Dry run should not write anything."""
        fs_dir = str(tmp_path / "fs")
        os.makedirs(fs_dir)
        docs = [
            {"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o", "skills": []}},
        ]
        _create_fs_module(fs_dir, "test-mod", docs)

        fs = FilesystemWritableSource(fs_dir)
        db = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
        await db.connect()

        snap_path = str(tmp_path / ".dna.sync")
        engine = SyncEngine(fs, db)
        result = await engine.push("test-mod", snapshot_path=snap_path, dry_run=True)

        assert len(result.pushed) > 0
        # DB should still be empty
        db_docs = await db.load_all("test-mod")
        assert len(db_docs) == 0
        # Snapshot should not exist
        assert not os.path.exists(snap_path)
        await db.close()

    @pytest.mark.asyncio
    async def test_conflict_detection(self, tmp_path):
        """Modify same doc on both sides → conflict."""
        fs_dir = str(tmp_path / "fs")
        os.makedirs(fs_dir)
        docs = [
            {"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o", "skills": []}},
        ]
        _create_fs_module(fs_dir, "test-mod", docs)

        fs = FilesystemWritableSource(fs_dir)
        db = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
        await db.connect()

        snap_path = str(tmp_path / ".dna.sync")
        engine = SyncEngine(fs, db)
        await engine.push("test-mod", snapshot_path=snap_path)

        # Modify on filesystem
        agent_path = os.path.join(fs_dir, "test-mod", "agents", "bot.yaml")
        modified_fs = {"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o-mini", "skills": []}}
        with open(agent_path, "w") as f:
            pyyaml.dump(modified_fs, f)

        # Modify in DB
        modified_db = {"kind": "Agent", "name": "bot", "spec": {"model": "claude-4", "skills": []}}
        await db.save_document("test-mod", "Agent", "bot", modified_db)
        await db.publish("test-mod", "Agent", "bot")

        result = await engine.sync("test-mod", snapshot_path=snap_path)
        assert len(result.conflicts) > 0
        await db.close()
