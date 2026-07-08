"""Tests for AsyncSourceAdapter — async wrapper over sync SourcePort.

GAP-17: Validates that sync methods are properly dispatched to thread pool.
"""
from __future__ import annotations

import asyncio
import pytest

from dna.adapters.async_adapter import AsyncSourceAdapter


class FakeSource:
    """Minimal sync source for testing."""

    def __init__(self):
        self.calls: list[str] = []

    def load_bootstrap_docs(self, scope, *, tenant=None):
        self.calls.append(f"load_bootstrap_docs:{scope}")
        return [{"kind": "Genome", "metadata": {"name": scope}, "spec": {}}]

    def load_all(self, scope, readers=None):
        self.calls.append(f"load_all:{scope}")
        return [{"kind": "Genome", "metadata": {"name": scope}, "spec": {}}]

    def resolve_ref(self, scope, ref):
        self.calls.append(f"resolve_ref:{scope}:{ref}")
        return f"resolved:{ref}"

    def load_layer(self, scope, layer_id, layer_value, readers=None):
        self.calls.append(f"load_layer:{scope}:{layer_id}:{layer_value}")
        return []

    def save_document(self, scope, kind, name, raw):
        self.calls.append(f"save:{scope}:{kind}:{name}")
        return "1"

    def delete_document(self, scope, kind, name):
        self.calls.append(f"delete:{scope}:{kind}:{name}")

    def publish(self, scope, kind, name):
        self.calls.append(f"publish:{scope}:{kind}:{name}")
        return "1"

    def list_scopes(self):
        self.calls.append("list_scopes")
        return ["mod-a", "mod-b"]

    def capabilities(self):
        # s-capabilities-dataclass — sync, typed SourceCapabilities (derived from
        # the Protocols this fake structurally satisfies: drafts yes, versions no).
        from dna.kernel.capabilities import derive_capabilities
        return derive_capabilities(self, label="fake")

    def load_drafts(self, scope):
        return []

    def list_versions(self, scope, kind, name):
        return []

    def custom_method(self):
        """Non-standard method — should be accessible via __getattr__."""
        return "custom_value"


@pytest.fixture
def adapter():
    return AsyncSourceAdapter(FakeSource())


class TestAsyncSourceAdapter:
    @pytest.mark.asyncio
    async def test_load_bootstrap_docs(self, adapter):
        result = await adapter.load_bootstrap_docs("test")
        assert result and result[0]["kind"] == "Genome"
        assert "load_bootstrap_docs:test" in adapter._source.calls

    @pytest.mark.asyncio
    async def test_load_all(self, adapter):
        result = await adapter.load_all("test")
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_resolve_ref(self, adapter):
        result = await adapter.resolve_ref("s", "agents/bot.md")
        assert result == "resolved:agents/bot.md"

    @pytest.mark.asyncio
    async def test_load_layer(self, adapter):
        result = await adapter.load_layer("s", "tenant", "team-a")
        assert result == []

    @pytest.mark.asyncio
    async def test_save_document(self, adapter):
        version = await adapter.save_document("s", "Skill", "s1", {"kind": "Skill"})
        assert version == "1"

    @pytest.mark.asyncio
    async def test_delete_document(self, adapter):
        await adapter.delete_document("s", "Skill", "s1")
        assert "delete:s:Skill:s1" in adapter._source.calls

    @pytest.mark.asyncio
    async def test_publish(self, adapter):
        version = await adapter.publish("s", "Skill", "s1")
        assert version == "1"

    @pytest.mark.asyncio
    async def test_list_scopes(self, adapter):
        scopes = await adapter.list_scopes()
        assert scopes == ["mod-a", "mod-b"]

    def test_capabilities(self, adapter):
        # s-capabilities-dataclass — capabilities() is sync now; the adapter is a
        # plain passthrough to the wrapped source's typed SourceCapabilities.
        caps = adapter.capabilities()
        assert caps.source == "fake"
        assert caps.drafts is True   # fake has load_drafts + publish
        assert caps.versions is False  # fake has no get_version

    @pytest.mark.asyncio
    async def test_getattr_passthrough(self, adapter):
        """Non-async attributes are accessible via __getattr__."""
        result = adapter._source.custom_method()
        assert result == "custom_value"

    @pytest.mark.asyncio
    async def test_concurrent_calls(self, adapter):
        """Multiple async calls can run concurrently without blocking."""
        results = await asyncio.gather(
            adapter.load_bootstrap_docs("a"),
            adapter.load_bootstrap_docs("b"),
            adapter.load_bootstrap_docs("c"),
        )
        assert len(results) == 3
        assert all(r[0]["kind"] == "Genome" for r in results)
