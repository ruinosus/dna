"""Tests for SqliteSource — CRUD, versioning, drafts, layers.

GAP-16: SQLite layer support — validates load_layer, save_layer_document,
delete_layer_document, and list_layers.
"""
from __future__ import annotations

import json
import pytest
import pytest_asyncio
from pathlib import Path

from dna.adapters.sqlite import SqliteSource


@pytest_asyncio.fixture
async def source(tmp_path):
    db = tmp_path / "test.db"
    src = SqliteSource(str(db))
    await src.connect()
    # Seed a module
    module_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": "test-mod", "description": "Test"},
        "spec": {"default_agent": "bot"},
    }
    await src.save_document("test-mod", "Genome", "test-mod", module_raw)
    await src.publish("test-mod", "Genome", "test-mod")
    yield src
    await src.close()


# ── Basic CRUD ──

class TestBasicCRUD:
    @pytest.mark.asyncio
    async def test_load_bootstrap_docs(self, source):
        from dna.kernel.protocols import package_doc_for_scope
        m = await package_doc_for_scope(source, "test-mod")
        assert m is not None
        assert m["kind"] == "Genome"
        assert m["metadata"]["name"] == "test-mod"

    @pytest.mark.asyncio
    async def test_load_bootstrap_docs_missing(self, source):
        from dna.kernel.protocols import package_doc_for_scope
        m = await package_doc_for_scope(source, "nope")
        assert m is None

    @pytest.mark.asyncio
    async def test_save_and_load(self, source):
        agent = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "bot"}, "spec": {"instruction": "Be helpful"},
        }
        await source.save_document("test-mod", "Agent", "bot", agent)
        await source.publish("test-mod", "Agent", "bot")

        docs = await source.load_all("test-mod")
        names = [d["metadata"]["name"] for d in docs]
        assert "bot" in names

    @pytest.mark.asyncio
    async def test_delete(self, source):
        agent = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "temp"}, "spec": {},
        }
        await source.save_document("test-mod", "Agent", "temp", agent)
        await source.publish("test-mod", "Agent", "temp")
        await source.delete_document("test-mod", "Agent", "temp")
        docs = await source.load_all("test-mod")
        assert all(d["metadata"]["name"] != "temp" for d in docs)

    @pytest.mark.asyncio
    async def test_delete_missing_raises(self, source):
        with pytest.raises(ValueError, match="not_found"):
            await source.delete_document("test-mod", "Skill", "ghost")


# ── Versioning ──

class TestVersioning:
    @pytest.mark.asyncio
    async def test_multiple_versions(self, source):
        for i in range(3):
            await source.save_document("test-mod", "Skill", "s1", {
                "apiVersion": "agentskills.io/v1", "kind": "Skill",
                "metadata": {"name": "s1"}, "spec": {"instruction": f"v{i+1}"},
            })
        versions = await source.list_versions("test-mod", "Skill", "s1")
        assert len(versions) == 3
        assert versions[0]["version"] == 3  # DESC order

    @pytest.mark.asyncio
    async def test_get_version(self, source):
        await source.save_document("test-mod", "Skill", "s1", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "s1"}, "spec": {"instruction": "hello"},
        })
        v = await source.get_version("test-mod", "Skill", "s1", "1")
        assert v["content"]["spec"]["instruction"] == "hello"

    @pytest.mark.asyncio
    async def test_get_version_missing(self, source):
        with pytest.raises(ValueError, match="version_not_found"):
            await source.get_version("test-mod", "Skill", "s1", "999")

    @pytest.mark.asyncio
    async def test_publish_no_draft_raises(self, source):
        with pytest.raises(ValueError, match="no_draft"):
            await source.publish("test-mod", "Skill", "ghost")


# ── Drafts ──

class TestDrafts:
    @pytest.mark.asyncio
    async def test_draft_not_in_load_all(self, source):
        await source.save_document("test-mod", "Skill", "draft-skill", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "draft-skill"}, "spec": {},
        })
        # Draft is saved but NOT published
        docs = await source.load_all("test-mod")
        assert all(d["metadata"]["name"] != "draft-skill" for d in docs)

    @pytest.mark.asyncio
    async def test_load_drafts(self, source):
        await source.save_document("test-mod", "Skill", "d1", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "d1"}, "spec": {},
        })
        drafts = await source.load_drafts("test-mod")
        assert len(drafts) >= 1
        assert any(d["name"] == "d1" for d in drafts)


# ── Layers (GAP-16) ──

class TestLayers:
    @pytest.mark.asyncio
    async def test_empty_layer(self, source):
        result = await source.load_layer("test-mod", "tenant", "team-a")
        assert result == []

    @pytest.mark.asyncio
    async def test_save_and_load_layer(self, source):
        overlay = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "bot"},
            "spec": {"instruction": "Team A bot — custom behavior"},
        }
        await source.save_layer_document("test-mod", "tenant", "team-a", "Agent", "bot", overlay)

        docs = await source.load_layer("test-mod", "tenant", "team-a")
        assert len(docs) == 1
        assert docs[0]["spec"]["instruction"] == "Team A bot — custom behavior"

    @pytest.mark.asyncio
    async def test_multiple_layers(self, source):
        """Different layer values are independent."""
        await source.save_layer_document("test-mod", "tenant", "team-a", "Skill", "s1", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "s1"}, "spec": {"instruction": "Team A skill"},
        })
        await source.save_layer_document("test-mod", "tenant", "team-b", "Skill", "s2", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "s2"}, "spec": {"instruction": "Team B skill"},
        })

        team_a = await source.load_layer("test-mod", "tenant", "team-a")
        team_b = await source.load_layer("test-mod", "tenant", "team-b")
        assert len(team_a) == 1
        assert len(team_b) == 1
        assert team_a[0]["metadata"]["name"] == "s1"
        assert team_b[0]["metadata"]["name"] == "s2"

    @pytest.mark.asyncio
    async def test_update_layer_document(self, source):
        """Saving to same layer+kind+name updates (UPSERT)."""
        await source.save_layer_document("test-mod", "tenant", "team-a", "Skill", "s1", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "s1"}, "spec": {"instruction": "v1"},
        })
        await source.save_layer_document("test-mod", "tenant", "team-a", "Skill", "s1", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "s1"}, "spec": {"instruction": "v2"},
        })

        docs = await source.load_layer("test-mod", "tenant", "team-a")
        assert len(docs) == 1
        assert docs[0]["spec"]["instruction"] == "v2"

    @pytest.mark.asyncio
    async def test_delete_layer_document(self, source):
        await source.save_layer_document("test-mod", "tenant", "team-a", "Skill", "s1", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "s1"}, "spec": {},
        })
        await source.delete_layer_document("test-mod", "tenant", "team-a", "Skill", "s1")
        assert await source.load_layer("test-mod", "tenant", "team-a") == []

    @pytest.mark.asyncio
    async def test_list_layers(self, source):
        await source.save_layer_document("test-mod", "tenant", "team-a", "Skill", "s1", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "s1"}, "spec": {},
        })
        await source.save_layer_document("test-mod", "tenant", "team-b", "Skill", "s2", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "s2"}, "spec": {},
        })
        layers = await source.list_layers("test-mod")
        assert len(layers) == 2
        labels = [f"{l['layer_id']}:{l['layer_value']}" for l in layers]
        assert "tenant:team-a" in labels
        assert "tenant:team-b" in labels


# ── Capabilities ──

class TestCapabilities:
    def test_has_drafts_and_versions(self, source):
        # s-capabilities-dataclass — typed SourceCapabilities; sqlite implements
        # load_layer so ``layers`` is now reported True (the old dict omitted it).
        caps = source.capabilities()
        assert caps.drafts is True
        assert caps.versions is True
        assert caps.layers is True
        assert caps.source == "sqlite"

    @pytest.mark.asyncio
    async def test_list_scopes(self, source):
        scopes = await source.list_scopes()
        assert "test-mod" in scopes


# ── Migration ──

class TestMigration:
    @pytest.mark.asyncio
    async def test_idempotent(self, tmp_path):
        """Creating SqliteSource twice on same DB doesn't fail."""
        db = tmp_path / "idempotent.db"
        s1 = SqliteSource(str(db))
        await s1.connect()
        await s1.close()
        s2 = SqliteSource(str(db))  # Should not fail
        await s2.connect()
        await s2.close()

    @pytest.mark.asyncio
    async def test_migration_2_creates_layer_table(self, tmp_path):
        db = tmp_path / "layers.db"
        src = SqliteSource(str(db))
        await src.connect()
        # Verify table exists by inserting
        await src.save_layer_document("s", "t", "v", "K", "n", {"kind": "K"})
        result = await src.load_layer("s", "t", "v")
        assert len(result) == 1
        await src.close()
