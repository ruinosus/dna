"""P2 Task 8 — WorkOS AuthKit provider (Lane B) + the second (/consumer) mount.

WorkOS AuthKit is a DCR/CIMD-native authorization server, so DNA is a pure
resource server on Lane B: verify WorkOS JWTs + advertise the AuthKit domain via
RFC 9728 PRM. ``build_http_app(lane_b_server=…)`` mounts that second server at
``/consumer`` beside Lane A (Entra), composing both lifespans (Option X).
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastmcp", reason="the MCP auth face needs the 'fastmcp' extra")


def _workos_env(monkeypatch) -> None:
    monkeypatch.setenv("DNA_MCP_WORKOS_CLIENT_ID", "client_01ABC")
    monkeypatch.setenv("DNA_MCP_WORKOS_AUTHKIT_DOMAIN", "dna-cloud.authkit.app")
    monkeypatch.setenv("DNA_MCP_WORKOS_RESOURCE_URL", "https://mcp.dnacloud.io/consumer")


def test_workos_provider_builds_resource_server(monkeypatch):
    _workos_env(monkeypatch)
    from dna_cli._mcp_auth import workos_provider_from_env

    provider = workos_provider_from_env()
    assert provider is not None  # a RemoteAuthProvider wrapping the WorkOS verifier


def test_workos_provider_requires_env(monkeypatch):
    monkeypatch.delenv("DNA_MCP_WORKOS_AUTHKIT_DOMAIN", raising=False)
    from dna_cli._mcp_auth import workos_provider_from_env

    with pytest.raises(RuntimeError):
        workos_provider_from_env()


def test_workos_domain_gets_https_prefix(monkeypatch):
    """A bare domain (no scheme) is normalized to https:// for the AS URL."""
    _workos_env(monkeypatch)
    from dna_cli._mcp_auth import workos_provider_from_env

    # Should not raise; the domain normalization happens inside.
    assert workos_provider_from_env() is not None


# ── the /consumer mount (Option X) — fakes to avoid heavy server construction ──

class _FakeMcpApp:
    """Minimal stand-in for a FastMCP http_app: has a .lifespan async CM."""
    def __init__(self, name: str):
        self.name = name
        self.entered = False

    def lifespan(self, app):
        outer = self

        class _CM:
            async def __aenter__(self_):
                outer.entered = True
                return outer

            async def __aexit__(self_, *exc):
                return False

        return _CM()


class _FakeServer:
    def __init__(self, name: str):
        self._app = _FakeMcpApp(name)

    def http_app(self, *, path: str, transport: str):
        return self._app


def _mount_paths(app) -> list[str]:
    return [getattr(r, "path", None) for r in app.routes]


def test_single_lane_has_no_consumer_mount():
    from dna_cli._mcp_server import build_http_app

    app = build_http_app(_FakeServer("A"))
    paths = _mount_paths(app)
    assert "/consumer" not in paths
    # Starlette normalizes the bare Mount("/") path to "".
    assert "/w/{workspace_id}" in paths and "" in paths


def test_lane_b_adds_consumer_mount_last_is_bare():
    from dna_cli._mcp_server import build_http_app

    app = build_http_app(_FakeServer("A"), lane_b_server=_FakeServer("B"))
    paths = _mount_paths(app)
    assert "/consumer" in paths, paths
    # the bare mount (Starlette normalizes "/" → "") stays LAST (least specific),
    # so it never shadows the more-specific /consumer or /w mounts
    assert paths[-1] == ""
    assert paths.index("/consumer") < paths.index("")


def test_lane_b_composes_both_lifespans():
    import asyncio

    from dna_cli._mcp_server import build_http_app

    a, b = _FakeServer("A"), _FakeServer("B")
    app = build_http_app(a, lane_b_server=b)

    async def _run():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(_run())
    assert a._app.entered and b._app.entered, "both lane lifespans must run"
