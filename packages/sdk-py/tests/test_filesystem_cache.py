"""Integration tests for FilesystemCache — real files, real readers.

Proves: store, has, load_all with bundle detection (SKILL.md, SOUL.md readers).
"""
from __future__ import annotations

import pytest
from pathlib import Path

import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.kernel.protocols import CacheItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cache(tmp_path):
    """FilesystemCache rooted at tmp_path/.dna-cache/."""
    # FilesystemCache resolves base_dir.parent / ".dna-cache"
    # So we create a dummy subdir as the "base_dir" argument
    base = tmp_path / "project" / ".dna"
    base.mkdir(parents=True)
    return FilesystemCache(str(base))


def _create_skill_bundle(tmp_path, name: str, content: str = "# Skill") -> Path:
    """Create a minimal SKILL.md bundle directory."""
    bundle = tmp_path / f"skill-{name}"
    bundle.mkdir(parents=True)
    (bundle / "SKILL.md").write_text(content)
    return bundle


def _create_yaml_doc(tmp_path, name: str, kind: str = "Agent") -> Path:
    """Create a directory containing a YAML document."""
    doc_dir = tmp_path / f"doc-{name}"
    doc_dir.mkdir(parents=True)
    doc = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": kind,
        "metadata": {"name": name},
        "spec": {"instruction": f"I am {name}."},
    }
    (doc_dir / f"{name}.yaml").write_text(yaml.dump(doc))
    return doc_dir


# ---------------------------------------------------------------------------
# has()
# ---------------------------------------------------------------------------


class TestHas:
    @pytest.mark.asyncio
    async def test_missing_key(self, cache):
        assert await cache.has("my-scope", "nonexistent-key") is False

    @pytest.mark.asyncio
    async def test_existing_key(self, cache, tmp_path):
        bundle = _create_skill_bundle(tmp_path, "test-skill")
        await cache.store("my-scope", "dep-key", [
            CacheItem(name="test-skill", kind="Skill", content_path=bundle),
        ])
        assert await cache.has("my-scope", "dep-key") is True

    @pytest.mark.asyncio
    async def test_different_scope(self, cache, tmp_path):
        bundle = _create_skill_bundle(tmp_path, "s")
        await cache.store("scope-a", "key", [CacheItem(name="s", kind="Skill", content_path=bundle)])
        assert await cache.has("scope-a", "key") is True
        assert await cache.has("scope-b", "key") is False


# ---------------------------------------------------------------------------
# store()
# ---------------------------------------------------------------------------


class TestStore:
    @pytest.mark.asyncio
    async def test_store_single_item(self, cache, tmp_path):
        bundle = _create_skill_bundle(tmp_path, "my-skill", "# My Skill Content")
        await cache.store("test", "dep-1", [
            CacheItem(name="my-skill", kind="Skill", content_path=bundle),
        ])
        assert await cache.has("test", "dep-1") is True

    @pytest.mark.asyncio
    async def test_store_multiple_items(self, cache, tmp_path):
        b1 = _create_skill_bundle(tmp_path, "s1")
        b2 = _create_skill_bundle(tmp_path, "s2")
        await cache.store("test", "dep-multi", [
            CacheItem(name="s1", kind="Skill", content_path=b1),
            CacheItem(name="s2", kind="Skill", content_path=b2),
        ])
        assert await cache.has("test", "dep-multi") is True

    @pytest.mark.asyncio
    async def test_store_overwrites_existing(self, cache, tmp_path):
        b1 = _create_skill_bundle(tmp_path, "orig", "# Original")
        await cache.store("test", "key", [CacheItem(name="orig", kind="Skill", content_path=b1)])

        b2 = _create_skill_bundle(tmp_path, "orig-v2", "# Updated")
        # Store under same name to overwrite
        await cache.store("test", "key", [CacheItem(name="orig", kind="Skill", content_path=b2)])

        assert await cache.has("test", "key") is True

    @pytest.mark.asyncio
    async def test_store_without_kind_stores_flat(self, cache, tmp_path):
        bundle = _create_yaml_doc(tmp_path, "flat-item")
        await cache.store("test", "flat-dep", [
            CacheItem(name="flat-item", kind="", content_path=bundle),
        ])
        assert await cache.has("test", "flat-dep") is True


# ---------------------------------------------------------------------------
# load_all()
# ---------------------------------------------------------------------------


class TestLoadAll:
    @pytest.mark.asyncio
    async def test_empty_scope(self, cache):
        docs = await cache.load_all("nonexistent-scope")
        assert docs == []

    @pytest.mark.asyncio
    async def test_load_yaml_documents(self, cache, tmp_path):
        doc_dir = _create_yaml_doc(tmp_path, "agent-a")
        await cache.store("test", "dep-yaml", [
            CacheItem(name="agent-a", kind="", content_path=doc_dir),
        ])
        docs = await cache.load_all("test")
        assert len(docs) >= 1
        names = [d.get("metadata", {}).get("name") for d in docs]
        assert "agent-a" in names

    @pytest.mark.asyncio
    async def test_load_with_skill_reader(self, cache, tmp_path):
        """When a SKILL.md reader is provided, it detects and reads skill bundles."""
        from dna.extensions.agentskills import AgentSkillsExtension
        from dna.kernel import Kernel

        # Get real reader from extension
        k = Kernel()
        k.load(AgentSkillsExtension())
        readers = k._readers

        bundle = _create_skill_bundle(tmp_path, "cached-skill", "# Cached Skill\nDo stuff.")
        await cache.store("test", "dep-skills", [
            CacheItem(name="cached-skill", kind="Skill", content_path=bundle),
        ])

        docs = await cache.load_all("test", readers=readers)
        skill_docs = [d for d in docs if d.get("kind") == "Skill"]
        assert len(skill_docs) >= 1
        assert any(d["metadata"]["name"] == "cached-skill" for d in skill_docs)

    @pytest.mark.asyncio
    async def test_load_multiple_deps_combined(self, cache, tmp_path):
        b1 = _create_yaml_doc(tmp_path, "a1", "Agent")
        b2 = _create_yaml_doc(tmp_path, "a2", "Agent")
        await cache.store("test", "dep-1", [CacheItem(name="a1", kind="", content_path=b1)])
        await cache.store("test", "dep-2", [CacheItem(name="a2", kind="", content_path=b2)])

        docs = await cache.load_all("test")
        names = [d.get("metadata", {}).get("name") for d in docs]
        assert "a1" in names
        assert "a2" in names
