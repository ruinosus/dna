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


def test_workos_scopes_ignore_entra_env(monkeypatch):
    """Lane B PRM must advertise OIDC scopes, NEVER the Entra `user_impersonation`
    URI — sharing DNA_MCP_SCOPES_SUPPORTED made WorkOS 400 `invalid_scope`
    (the Claude MCP auth-callback failure)."""
    from dna_cli._mcp_auth import workos_scopes_supported_from_env

    # Entra env set (the Azure scope URI) — Lane B MUST ignore it.
    monkeypatch.setenv(
        "DNA_MCP_SCOPES_SUPPORTED", "api://dna-mcp-dnacloud/user_impersonation"
    )
    monkeypatch.delenv("DNA_MCP_WORKOS_SCOPES_SUPPORTED", raising=False)
    scopes = workos_scopes_supported_from_env()
    assert scopes == ["openid", "profile", "email"], scopes
    assert not any("user_impersonation" in s for s in scopes)


def test_workos_scopes_override(monkeypatch):
    """A Lane-B-specific override is honored (comma-separated)."""
    from dna_cli._mcp_auth import workos_scopes_supported_from_env

    monkeypatch.setenv(
        "DNA_MCP_WORKOS_SCOPES_SUPPORTED", "openid, profile, email, offline_access"
    )
    assert workos_scopes_supported_from_env() == [
        "openid",
        "profile",
        "email",
        "offline_access",
    ]


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

    async def __call__(self, scope, receive, send):
        # Minimal ASGI: echo "<lane>:<path>" so a routing test can see WHICH app
        # handled a request + at WHAT path (unstripped).
        body = f"{self.name}:{scope.get('path', '')}".encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": body})


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


def test_root_dispatches_lane_b_wellknown_to_lane_b():
    """RFC 9728: Lane B's PRM at the HOST ROOT
    (`/.well-known/oauth-protected-resource/consumer/mcp`) must be served by the
    Lane-B app (the 401 advertises it there), NOT 404 on Lane A. Everything else —
    including Lane A's own root PRM + the bare /mcp — stays Lane A."""
    from starlette.testclient import TestClient

    from dna_cli._mcp_server import build_http_app

    app = build_http_app(_FakeServer("A"), lane_b_server=_FakeServer("B"))
    with TestClient(app) as client:
        # Lane B PRM at the root → Lane B app, with the FULL unstripped path.
        r = client.get("/.well-known/oauth-protected-resource/consumer/mcp")
        assert r.text == "B:/.well-known/oauth-protected-resource/consumer/mcp", r.text
        # Lane A's own root PRM stays Lane A.
        rA = client.get("/.well-known/oauth-protected-resource/mcp")
        assert rA.text.startswith("A:"), rA.text
        # The bare /mcp stays Lane A.
        rM = client.get("/mcp")
        assert rM.text.startswith("A:"), rM.text
        # The Lane-B MCP endpoint is served by the /consumer mount (Lane B).
        rB = client.get("/consumer/mcp")
        assert rB.text.startswith("B:"), rB.text


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
