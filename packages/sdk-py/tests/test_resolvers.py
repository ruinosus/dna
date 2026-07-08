"""Tests for v3 resolvers — Local, GitHub, HTTP, Registry.

GAP-12/13: HTTP + Registry resolvers with mock HTTP.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from dna.kernel.protocols import ResolveError
from dna.adapters.resolvers import (
    HelixResolver, LocalResolver, GitHubResolver, HttpResolver, RegistryResolver,
)


BASE_DIR = Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"
MARKET_DEMO = Path(__file__).parent.parent.parent.parent / "scopes" / "market-integration" / ".dna" / "market-demo"


# ── LocalResolver ──

class TestLocalResolver:
    def test_cache_key(self):
        r = LocalResolver()
        key = r.cache_key("local:../shared/.dna/shared")
        assert key.startswith("local-")
        assert "/" not in key

    @pytest.mark.asyncio
    async def test_resolve_existing(self):
        if not MARKET_DEMO.exists():
            pytest.skip("market-demo fixture not available")
        r = LocalResolver()
        dep = {"items": [{"kind": "Skill", "names": ["brainstorming"]}]}
        items = await r.resolve(f"local:{MARKET_DEMO}", dep)
        assert len(items) >= 1
        names = [i.name for i in items]
        assert "brainstorming" in names

    @pytest.mark.asyncio
    async def test_resolve_missing_path(self):
        r = LocalResolver()
        items = await r.resolve("local:/nonexistent/path", {})
        assert items == []

    @pytest.mark.asyncio
    async def test_resolve_all(self):
        if not MARKET_DEMO.exists():
            pytest.skip("market-demo fixture not available")
        r = LocalResolver()
        items = await r.resolve(f"local:{MARKET_DEMO}", {})
        assert len(items) > 5


# ── GitHubResolver ──

class TestGitHubResolver:
    def test_cache_key(self):
        r = GitHubResolver()
        key = r.cache_key("github:anthropics/skills@main")
        assert key.startswith("github-")

    @pytest.mark.asyncio
    async def test_invalid_uri_raises(self):
        r = GitHubResolver()
        with pytest.raises(ResolveError, match="Invalid github URI"):
            await r.resolve("github:", {})


# ── HttpResolver ──

class TestHttpResolver:
    def test_cache_key(self):
        r = HttpResolver()
        key = r.cache_key("https://example.com/skills")
        assert key.startswith("http-")
        assert len(key) <= 120

    def test_cache_key_truncation(self):
        r = HttpResolver()
        long_url = "https://example.com/" + "a" * 200
        key = r.cache_key(long_url)
        assert len(key) <= 120

    @pytest.mark.asyncio
    async def test_resolve_bundle_mode(self, tmp_path):
        """Bundle mode: GET returns JSON array of raw dicts."""
        bundle = [
            {"kind": "Skill", "metadata": {"name": "s1"}, "spec": {"instruction": "Do X"}},
            {"kind": "Skill", "metadata": {"name": "s2"}, "spec": {"instruction": "Do Y"}},
        ]

        r = HttpResolver()
        with patch.object(r, "_fetch_json") as mock:
            mock.side_effect = [
                ResolveError("no index"),
                bundle,
            ]
            items = await r.resolve("https://example.com/skills", {})

        assert len(items) == 2
        names = {i.name for i in items}
        assert names == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_resolve_index_mode(self, tmp_path):
        """Index mode: GET /index.json → list, then fetch each."""
        index = [
            {"kind": "Skill", "name": "s1", "path": "skills/s1.json"},
        ]
        raw_s1 = {"kind": "Skill", "metadata": {"name": "s1"}, "spec": {"instruction": "Do X"}}

        r = HttpResolver()
        with patch.object(r, "_fetch_json") as mock:
            mock.side_effect = [index, raw_s1]
            items = await r.resolve("https://example.com/v1", {})

        assert len(items) == 1
        assert items[0].name == "s1"

    @pytest.mark.asyncio
    async def test_resolve_with_filter(self):
        """Only requested items are resolved."""
        bundle = [
            {"kind": "Skill", "metadata": {"name": "s1"}, "spec": {}},
            {"kind": "Skill", "metadata": {"name": "s2"}, "spec": {}},
            {"kind": "Soul", "metadata": {"name": "brad"}, "spec": {}},
        ]

        r = HttpResolver()
        dep = {"items": [{"kind": "Skill", "names": ["s1"]}]}
        with patch.object(r, "_fetch_json") as mock:
            mock.side_effect = [ResolveError("no index"), bundle]
            items = await r.resolve("https://example.com/skills", dep)

        assert len(items) == 1
        assert items[0].name == "s1"

    @pytest.mark.asyncio
    async def test_resolve_all_of_kind(self):
        """Empty names = import all of that kind."""
        bundle = [
            {"kind": "Skill", "metadata": {"name": "s1"}, "spec": {}},
            {"kind": "Skill", "metadata": {"name": "s2"}, "spec": {}},
            {"kind": "Soul", "metadata": {"name": "brad"}, "spec": {}},
        ]

        r = HttpResolver()
        dep = {"items": [{"kind": "Skill"}]}
        with patch.object(r, "_fetch_json") as mock:
            mock.side_effect = [ResolveError("no index"), bundle]
            items = await r.resolve("https://example.com", dep)

        assert len(items) == 2
        assert {i.name for i in items} == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_both_modes_fail_raises(self):
        """Both index and bundle mode fail → ResolveError."""
        r = HttpResolver()
        with patch.object(r, "_fetch_json") as mock:
            mock.side_effect = [
                ResolveError("index failed"),
                ResolveError("bundle failed"),
            ]
            with pytest.raises(ResolveError, match="HTTP resolve failed"):
                await r.resolve("https://example.com/bad", {})

    def test_custom_headers(self):
        """Custom headers are passed to requests."""
        r = HttpResolver(headers={"Authorization": "Bearer token123"})
        assert r._headers["Authorization"] == "Bearer token123"

    def test_matches_request(self):
        assert HttpResolver._matches_request("Skill", "s1", {"Skill": ["s1", "s2"]})
        assert not HttpResolver._matches_request("Skill", "s3", {"Skill": ["s1", "s2"]})
        assert HttpResolver._matches_request("Skill", "anything", {"Skill": []})
        assert not HttpResolver._matches_request("Soul", "brad", {"Skill": []})


# ── RegistryResolver ──

class TestRegistryResolver:
    def test_cache_key(self):
        r = RegistryResolver()
        key = r.cache_key("registry:@anthropic/skills")
        assert key.startswith("registry-")

    @pytest.mark.asyncio
    async def test_no_url_raises(self):
        r = RegistryResolver()
        with pytest.raises(ResolveError, match="DNA_REGISTRY_URL"):
            await r.resolve("registry:@org/pkg", {})

    @pytest.mark.asyncio
    async def test_resolve_delegates_to_http(self):
        """RegistryResolver constructs URL and delegates to HttpResolver."""
        r = RegistryResolver(registry_url="https://registry.example.com")

        bundle = [
            {"kind": "Skill", "metadata": {"name": "s1"}, "spec": {}},
        ]

        with patch("dna.adapters.resolvers.http.HttpResolver._fetch_json") as mock:
            mock.side_effect = [ResolveError("no index"), bundle]
            items = await r.resolve("registry:@anthropic/skills", {})

        assert len(items) == 1
        assert items[0].name == "s1"
        calls = mock.call_args_list
        assert any("registry.example.com/packages/@anthropic/skills" in str(c) for c in calls)

    def test_env_variable(self, monkeypatch):
        """Registry URL from environment variable."""
        monkeypatch.setenv("DNA_REGISTRY_URL", "https://reg.test.com")
        r = RegistryResolver()
        assert r._url == "https://reg.test.com"


# ── HelixResolver ──

class TestHelixResolver:
    def test_cache_key(self):
        r = HelixResolver()
        key = r.cache_key("helix:shared-module/skills")
        assert key.startswith("helix-")

    @pytest.mark.asyncio
    async def test_no_url_raises(self):
        r = HelixResolver()
        with pytest.raises(ResolveError, match="HELIX_API_URL"):
            await r.resolve("helix:mod/skills", {})

    def test_env_config(self, monkeypatch):
        monkeypatch.setenv("HELIX_API_URL", "https://helix.test.com")
        monkeypatch.setenv("HELIX_API_KEY", "key123")
        monkeypatch.setenv("HELIX_LICENSE_ID", "lic")
        monkeypatch.setenv("HELIX_NAMESPACE_ID", "ns")
        r = HelixResolver()
        cfg = r._get_config()
        assert cfg["url"] == "https://helix.test.com"
        assert cfg["key"] == "key123"

    def test_explicit_config(self):
        r = HelixResolver(api_url="https://x.com", api_key="k")
        cfg = r._get_config()
        assert cfg["url"] == "https://x.com"


# ── Typed error subclasses ──

class TestTypedErrors:
    def test_resolve_not_found_is_resolve_error(self):
        from dna.kernel.protocols import ResolveNotFoundError
        e = ResolveNotFoundError("gone")
        assert isinstance(e, ResolveError)

    def test_resolve_auth_is_resolve_error(self):
        from dna.kernel.protocols import ResolveAuthError
        e = ResolveAuthError("denied")
        assert isinstance(e, ResolveError)

    def test_resolve_network_is_resolve_error(self):
        from dna.kernel.protocols import ResolveNetworkError
        e = ResolveNetworkError("timeout")
        assert isinstance(e, ResolveError)


# ── Kernel.quick registers resolvers ──

class TestKernelResolverWiring:
    def test_quick_registers_all_resolvers(self):
        from dna.kernel import Kernel
        k = Kernel()
        from dna.adapters.filesystem import FilesystemCache, FilesystemSource
        k.source(FilesystemSource(str(BASE_DIR)))
        k.cache(FilesystemCache(str(BASE_DIR)))
        k.resolver("local", LocalResolver())
        k.resolver("github", GitHubResolver())
        k.resolver("http", HttpResolver())
        k.resolver("https", HttpResolver())
        k.resolver("registry", RegistryResolver())
        k.resolver("helix", HelixResolver())

        assert "local" in k._resolvers
        assert "github" in k._resolvers
        assert "http" in k._resolvers
        assert "https" in k._resolvers
        assert "registry" in k._resolvers
        assert "helix" in k._resolvers
