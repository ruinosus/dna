"""Story ``s-mcp-oauth-auth`` — FastMCP OAuth/JWT auth + the DNA tenancy BRIDGE.

Two layers, both proven here:

1. **The bridge (pure policy)** — ``dna_cli._mcp_auth`` maps a verified token's
   claims/scopes → a DNA tenant and enforces it (identity when unauthenticated;
   cross-tenant and tenant-less authenticated requests denied). Unit-tested with
   no server.

2. **End-to-end over real JWT + HTTP** — a ``JWTVerifier`` (FastMCP's built-in
   Resource Server) guards the Streamable-HTTP server; two RSA-signed tokens
   (tenant ``acme`` vs ``globex``) hit the SAME ``compose_prompt`` tool and get
   composition scoped by their token's tenant; a token asking for another tenant
   is denied; a token with no tenant claim is denied; and the server advertises
   Protected Resource Metadata (RFC 9728). The test JWT provider is in-process
   (RSAKeyPair) — no external IdP.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")

from dna_cli import _mcp_auth as A  # noqa: E402
from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_AGENT = "concierge"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"


# ── the bridge: pure policy (no server) ───────────────────────────────────


def test_tenant_from_token_reads_claim():
    assert A.tenant_from_token({"tenant": "acme"}, []) == "acme"


def test_tenant_from_token_reads_scope():
    assert A.tenant_from_token({}, ["dna.read", "tenant:globex"]) == "globex"


def test_tenant_from_token_claim_wins_over_scope():
    assert A.tenant_from_token({"tenant": "acme"}, ["tenant:globex"]) == "acme"


def test_tenant_from_token_none_when_absent():
    assert A.tenant_from_token({"sub": "u1"}, ["dna.read"]) is None


def test_resolve_tenant_no_auth_is_passthrough():
    # No token (stdio / local) → the caller's tenant is untouched (MVP behavior).
    assert A.resolve_tenant(token_present=False, token_tenant=None, requested="acme") == "acme"
    assert A.resolve_tenant(token_present=False, token_tenant=None, requested=None) is None


def test_resolve_tenant_injects_token_tenant():
    # Authenticated, caller omits tenant → the token's tenant is used.
    assert A.resolve_tenant(token_present=True, token_tenant="acme", requested=None) == "acme"
    # caller passes the SAME tenant → allowed.
    assert A.resolve_tenant(token_present=True, token_tenant="acme", requested="acme") == "acme"


def test_resolve_tenant_denies_cross_tenant():
    with pytest.raises(A.CrossTenantError, match="cross-tenant"):
        A.resolve_tenant(token_present=True, token_tenant="acme", requested="globex")


def test_resolve_tenant_denies_tokenless_tenant():
    with pytest.raises(A.CrossTenantError, match="no tenant"):
        A.resolve_tenant(token_present=True, token_tenant=None, requested=None)


def test_jwt_provider_from_env_requires_key_source(monkeypatch):
    monkeypatch.delenv("DNA_MCP_JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("DNA_MCP_JWKS_URI", raising=False)
    with pytest.raises(RuntimeError, match="key source"):
        A.jwt_provider_from_env()


def test_jwt_provider_from_env_builds_verifier(monkeypatch):
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    monkeypatch.setenv("DNA_MCP_JWT_PUBLIC_KEY", kp.public_key)
    monkeypatch.setenv("DNA_MCP_JWT_ISSUER", _ISSUER)
    monkeypatch.setenv("DNA_MCP_JWT_AUDIENCE", _AUDIENCE)
    prov = A.jwt_provider_from_env()
    assert isinstance(prov, JWTVerifier)


# ── scopes_supported: advertise the OAuth scope in PRM (RFC 9728) ──────────
#
# The deployed MCP (`--auth jwt`) must advertise WHICH OAuth scope to request in
# its Protected-Resource-Metadata, or an MCP client (VS Code) reaches the IdP with
# no scope to ask for and stalls. `DNA_MCP_SCOPES_SUPPORTED` (comma-separated env)
# flows into the `RemoteAuthProvider`'s `scopes_supported` (PRM advertisement) but
# NOT into the verifier's `required_scopes` — the Azure full-vs-short nuance
# (PrefectHQ/fastmcp#3002): advertise the FULL `api://…/user_impersonation`, while
# the token's `scp` claim carries the SHORT `user_impersonation`.


def test_scopes_supported_from_env_parses_csv(monkeypatch):
    monkeypatch.delenv("DNA_MCP_SCOPES_SUPPORTED", raising=False)
    assert A.scopes_supported_from_env() is None
    monkeypatch.setenv("DNA_MCP_SCOPES_SUPPORTED", " api://x/user_impersonation , dna.read ")
    assert A.scopes_supported_from_env() == ["api://x/user_impersonation", "dna.read"]
    monkeypatch.setenv("DNA_MCP_SCOPES_SUPPORTED", "  , ")
    assert A.scopes_supported_from_env() is None


def test_jwt_provider_from_env_advertises_scopes_in_prm(monkeypatch):
    """The single-env-provider (`--auth jwt`) path: with a resource URL + auth
    server + `DNA_MCP_SCOPES_SUPPORTED`, the scope reaches the RemoteAuthProvider's
    PRM advertisement (`_scopes_supported`) — and NOT `required_scopes` (advertise,
    don't hard-require: the full-vs-short-form mismatch would reject valid tokens)."""
    from fastmcp.server.auth.providers.jwt import RSAKeyPair

    kp = RSAKeyPair.generate()
    scope = "api://dna-mcp-dnacloud/user_impersonation"
    monkeypatch.setenv("DNA_MCP_JWT_PUBLIC_KEY", kp.public_key)
    monkeypatch.setenv("DNA_MCP_JWT_ISSUER", _ISSUER)
    monkeypatch.setenv("DNA_MCP_JWT_AUDIENCE", _AUDIENCE)
    monkeypatch.setenv("DNA_MCP_RESOURCE_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("DNA_MCP_AUTH_SERVERS", _ISSUER)
    monkeypatch.setenv("DNA_MCP_SCOPES_SUPPORTED", scope)

    prov = A.jwt_provider_from_env()
    assert prov._scopes_supported == [scope]
    # advertise, don't require — the token's short `scp` must not be rejected.
    assert list(getattr(prov, "required_scopes", []) or []) == []


def test_jwt_provider_from_env_no_scopes_when_env_unset(monkeypatch):
    """Without `DNA_MCP_SCOPES_SUPPORTED`, PRM advertises no scope (unchanged
    behavior) — the env is the only source, never a hard-coded default."""
    from fastmcp.server.auth.providers.jwt import RSAKeyPair

    kp = RSAKeyPair.generate()
    monkeypatch.setenv("DNA_MCP_JWT_PUBLIC_KEY", kp.public_key)
    monkeypatch.setenv("DNA_MCP_JWT_ISSUER", _ISSUER)
    monkeypatch.setenv("DNA_MCP_JWT_AUDIENCE", _AUDIENCE)
    monkeypatch.setenv("DNA_MCP_RESOURCE_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("DNA_MCP_AUTH_SERVERS", _ISSUER)
    monkeypatch.delenv("DNA_MCP_SCOPES_SUPPORTED", raising=False)

    prov = A.jwt_provider_from_env()
    assert not getattr(prov, "_scopes_supported", None)


def test_build_auth_from_config_advertises_env_scopes(monkeypatch):
    """The multi-provider (`--auth config`) path: an explicit arg wins, else the
    env `DNA_MCP_SCOPES_SUPPORTED` flows into the RemoteAuthProvider's PRM."""
    provs = [
        A.ProviderConfig(
            type="entra", tenant_claim="tid",
            issuer="https://login.microsoftonline.com/common/v2.0",
            audience="api://dna-mcp-dnacloud",
            jwks_uri="https://login.microsoftonline.com/common/discovery/v2.0/keys",
        )
    ]
    scope = "api://dna-mcp-dnacloud/user_impersonation"
    monkeypatch.setenv("DNA_MCP_SCOPES_SUPPORTED", scope)
    prov = A.build_auth_from_config(
        provs, resource_url="http://127.0.0.1:9999",
        authorization_servers=["https://login.microsoftonline.com/common/v2.0"],
    )
    assert prov._scopes_supported == [scope]
    assert list(getattr(prov, "required_scopes", []) or []) == []

    # an explicit arg overrides the env.
    prov2 = A.build_auth_from_config(
        provs, resource_url="http://127.0.0.1:9999",
        authorization_servers=["https://login.microsoftonline.com/common/v2.0"],
        scopes_supported=["dna.read"],
    )
    assert prov2._scopes_supported == ["dna.read"]


# ── end-to-end: real JWT + HTTP + tenant-scoped composition ───────────────


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


_SENTINEL = "ACME-ONLY escalation: page the on-call SRE before answering."


def _seed_acme_overlay(dna_dir):
    """Write a per-tenant (acme) overlay of the concierge Agent so a tenant-scoped
    compose returns different content than the base — the isolation is observable."""
    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        overlay = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": _AGENT},
            "spec": {
                "instruction": _SENTINEL,
                "layout": "persona-first",
                "soul": "helpdesk-host",
                "guardrails": ["grounded-citation"],
                "tools": ["kb-search"],
                "model": "azure/gpt-4o",
            },
        }
        await live.kernel.with_tenant("acme").write_document(_SCOPE, "Agent", _AGENT, overlay)

    asyncio.run(go())


def _verifier_and_tokens():
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER, audience=_AUDIENCE)

    def mint(tenant: str | None):
        claims = {"tenant": tenant} if tenant else {}
        return kp.create_token(
            issuer=_ISSUER, audience=_AUDIENCE, subject="user-1",
            scopes=["dna.read"], additional_claims=claims,
        )

    return verifier, mint


def test_compose_prompt_is_tenant_scoped_by_token(dna_dir, http_server):
    """Two tokens (acme vs globex) → the SAME compose_prompt tool returns
    composition scoped by the token's tenant. acme sees its overlay; globex does
    not. Neither passes a `tenant` argument — the scoping comes from the token."""
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    _seed_acme_overlay(dna_dir)
    verifier, mint = _verifier_and_tokens()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token_acme, token_globex = mint("acme"), mint("globex")

    async def compose(url, token):
        async with Client(url, auth=BearerAuth(token)) as client:
            res = await client.call_tool("compose_prompt", {"agent": _AGENT, "scope": _SCOPE})
            return res.structured_content

    with http_server(server) as url:
        acme = asyncio.run(compose(url, token_acme))
        globex = asyncio.run(compose(url, token_globex))

    # acme's token composes acme's overlay; globex's does NOT — isolation proven.
    assert acme["tenant"] == "acme"
    assert _SENTINEL in acme["prompt"]
    assert globex["tenant"] == "globex"
    assert _SENTINEL not in globex["prompt"]
    # both still compose the shared Soul persona.
    assert "Helpdesk Concierge" in acme["prompt"]
    assert "Helpdesk Concierge" in globex["prompt"]


def test_cross_tenant_request_denied(dna_dir, http_server):
    """An acme token that explicitly asks for tenant=globex is DENIED (the bridge
    refuses to compose another tenant's resource)."""
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    verifier, mint = _verifier_and_tokens()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token_acme = mint("acme")

    async def go(url):
        async with Client(url, auth=BearerAuth(token_acme)) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011 — client raises ToolError/McpError
                await client.call_tool(
                    "compose_prompt",
                    {"agent": _AGENT, "scope": _SCOPE, "tenant": "globex"},
                )
            assert "tenant" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))


def test_tokenless_tenant_denied(dna_dir, http_server):
    """A token with NO tenant claim/scope is DENIED (fail closed — an
    authenticated request without a tenant binding gets nothing)."""
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    verifier, mint = _verifier_and_tokens()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token_none = mint(None)

    async def go(url):
        async with Client(url, auth=BearerAuth(token_none)) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool("compose_prompt", {"agent": _AGENT, "scope": _SCOPE})
            assert "tenant" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))


def test_unauthenticated_request_rejected(dna_dir, http_server):
    """No bearer token at all → the Resource Server rejects the connection (the
    server is protected; a client cannot reach the tools unauthenticated)."""
    from fastmcp import Client

    verifier, _ = _verifier_and_tokens()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)

    async def go(url):
        with pytest.raises(Exception):  # noqa: PT011 — 401 during initialize
            async with Client(url) as client:
                await client.list_tools()

    with http_server(server) as url:
        asyncio.run(go(url))


def test_protected_resource_metadata_advertised(dna_dir, http_server, free_port):
    """AC2: wrapped as a Resource Server, the server advertises Protected Resource
    Metadata (RFC 9728) at the well-known endpoint, so an MCP client can discover
    how to authorize."""
    import httpx

    verifier, _ = _verifier_and_tokens()
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    provider = A.resource_server(
        verifier, base_url=base_url, authorization_servers=[_ISSUER]
    )
    server = M.build_server(base_dir=str(dna_dir), auth=provider)

    with http_server(server, port=port):
        # FastMCP mounts PRM per-resource (path-suffixed) per the MCP spec.
        resp = httpx.get(
            f"{base_url}/.well-known/oauth-protected-resource/mcp", timeout=10
        )
        assert resp.status_code == 200, resp.text
        meta = resp.json()
        # RFC 9728: the document names the resource + its authorization server(s).
        assert "resource" in meta
        assert "authorization_servers" in meta
