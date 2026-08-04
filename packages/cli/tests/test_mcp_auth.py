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


# ── i-073: the PRM must advertise the AS identifier VERBATIM ───────────────
#
# RFC 8414 §3.3 makes the client compare the `issuer` the authorization server
# publishes against the identifier it was given, by EXACT STRING equality. FastMCP
# types `authorization_servers` as `list[AnyHttpUrl]`, and pydantic normalizes a
# bare-host URL — `https://host` becomes `https://host/`. A door configured with
# `https://as.example` therefore advertised `https://as.example/`, which disagrees
# with the `issuer` that same AS publishes, and a strict client silently walks away
# ("consent succeeds, then not a single request reaches the server").
#
# Verbatim means VERBATIM — not "strip trailing slashes": an identifier configured
# WITH a path or WITH a trailing slash must round-trip byte-identical too.

_AS_BARE = "https://as-bare.example"          # pydantic would append "/"
_AS_SLASHED = "https://as-slashed.example/"   # already slashed — must stay slashed
_AS_PATHED = "https://as-pathed.example/tenant/x"  # path — must stay intact


def test_prm_advertises_authorization_servers_verbatim(dna_dir, http_server, free_port):
    """The serialized PRM body carries each configured authorization-server
    identifier byte for byte — no pydantic canonicalization, in either direction."""
    import httpx

    verifier, _ = _verifier_and_tokens()
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    provider = A.resource_server(
        verifier,
        base_url=base_url,
        authorization_servers=[_AS_BARE, _AS_SLASHED, _AS_PATHED],
        scopes_supported=["openid", "profile"],
    )
    server = M.build_server(base_dir=str(dna_dir), auth=provider)

    with http_server(server, port=port):
        resp = httpx.get(
            f"{base_url}/.well-known/oauth-protected-resource/mcp", timeout=10
        )
    assert resp.status_code == 200, resp.text
    meta = resp.json()
    # The assertion is on the SERIALIZED body — a Python-object check would pass
    # against the bug, because the coercion happens at serialization time.
    assert meta["authorization_servers"] == [_AS_BARE, _AS_SLASHED, _AS_PATHED]
    # …and the raw bytes really do carry the un-slashed identifier.
    assert f'"{_AS_BARE}"' in resp.text
    # Every OTHER field of the document is untouched by the fix.
    assert meta["resource"] == f"{base_url}/mcp"
    assert meta["scopes_supported"] == ["openid", "profile"]
    assert meta["bearer_methods_supported"] == ["header"]


def test_prm_route_still_answers_cors_preflight(dna_dir, http_server, free_port):
    """The wrapper sits in the ASGI path of the PRM route, so the non-JSON
    responses it also carries (the CORS preflight FastMCP mounts on the same
    route) must pass through untouched."""
    import httpx

    verifier, _ = _verifier_and_tokens()
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    provider = A.resource_server(
        verifier, base_url=base_url, authorization_servers=[_AS_BARE]
    )
    server = M.build_server(base_dir=str(dna_dir), auth=provider)

    with http_server(server, port=port):
        resp = httpx.options(
            f"{base_url}/.well-known/oauth-protected-resource/mcp",
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "GET",
            },
            timeout=10,
        )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("access-control-allow-origin") == "*"


def _prm_body(provider, *, mcp_path: str = "/mcp") -> dict:
    """GET the provider's PRM document in-process (no socket) and return the
    parsed body — the serialized bytes, not a Python model."""
    import httpx
    from starlette.applications import Starlette

    routes = provider.get_routes(mcp_path)
    prm = [r for r in routes if r.path.startswith("/.well-known/oauth-protected-resource")]
    assert len(prm) == 1, [r.path for r in routes]
    transport = httpx.ASGITransport(app=Starlette(routes=routes))

    async def go():
        async with httpx.AsyncClient(
            transport=transport, base_url="http://door.test"
        ) as client:
            resp = await client.get(prm[0].path)
            assert resp.status_code == 200, resp.text
            return resp.json()

    return asyncio.run(go())


def test_workos_lane_advertises_the_authkit_domain_verbatim(monkeypatch):
    """The live regression (i-073): the consumer lane's AuthKit domain is a BARE
    host, and the AS itself publishes that exact string as its `issuer` — so the
    PRM must not append a slash to it."""
    domain = "https://tenant-slug.authkit.app"
    monkeypatch.setenv("DNA_MCP_WORKOS_AUTHKIT_DOMAIN", domain)
    monkeypatch.setenv("DNA_MCP_WORKOS_RESOURCE_URL", "https://door.test/consumer")
    monkeypatch.setenv("DNA_MCP_WORKOS_AUDIENCE", "client_test")
    monkeypatch.delenv("DNA_MCP_WORKOS_SCOPES_SUPPORTED", raising=False)

    meta = _prm_body(A.workos_provider_from_env(), mcp_path="/consumer")
    assert meta["authorization_servers"] == [domain]
    # offline_access entrou por medição (04/08): sem refresh_token a sessão
    # de cliente MCP morre nos 300s do access token do AuthKit.
    assert meta["scopes_supported"] == ["openid", "profile", "email", "offline_access"]


def test_build_auth_from_config_advertises_issuers_verbatim(monkeypatch):
    """The `--auth config` (multi-provider) path funnels through the same seam —
    every provider's issuer reaches PRM byte-identical."""
    monkeypatch.delenv("DNA_MCP_SCOPES_SUPPORTED", raising=False)
    provs = [
        A.ProviderConfig(
            type="oidc", tenant_claim="org_id",
            issuer=_AS_BARE, audience="dna-mcp",
            jwks_uri=f"{_AS_BARE}/.well-known/jwks.json",
        )
    ]
    provider = A.build_auth_from_config(
        provs, resource_url="https://door.test", authorization_servers=[_AS_BARE]
    )
    assert _prm_body(provider)["authorization_servers"] == [_AS_BARE]


# ── o JWKS vem da DESCOBERTA, não de uma convenção ──────────────────────────


def test_jwks_uri_vem_do_que_o_servidor_anuncia(monkeypatch):
    """O `jwks_uri` derivado tem de ser o que o SERVIDOR publica.

    O caso real que motivou isto: o WorkOS AuthKit anuncia
    `<issuer>/oauth2/jwks`, e a convenção `<issuer>/.well-known/jwks.json`
    responde 404. O verificador não achava a chave e recusava TODO token — sem
    erro de configuração, sem erro de rede, sem mensagem. A porta respondia 401
    contra um token perfeito.

    A asserção é sobre o VALOR ANUNCIADO, não sobre uma string que eu escolhi:
    um teste que checasse `endswith("/oauth2/jwks")` passaria com a convenção
    trocada por outra convenção, que é o mesmo defeito com outro nome.
    """
    anunciado = "https://idp.test/caminho/que/ninguem/adivinharia/jwks"
    monkeypatch.setattr(A, "_jwks_uri_anunciado", lambda issuer, **_: anunciado)
    assert A._derive_jwks_uri("workos", "https://idp.test") == anunciado


def test_a_convencao_sobrevive_quando_a_descoberta_nao_responde(monkeypatch):
    """Sem metadados alcançáveis, a convenção ainda faz o provedor subir.

    Um IdP que não fala descoberta — ou que está momentaneamente fora — não pode
    derrubar o boot: a convenção é um palpite pior que a descoberta e melhor que
    desistir.
    """
    monkeypatch.setattr(A, "_jwks_uri_anunciado", lambda issuer, **_: None)
    assert (
        A._derive_jwks_uri("oidc", "https://idp.test")
        == "https://idp.test/.well-known/jwks.json"
    )
    assert (
        A._derive_jwks_uri("entra", "https://login.microsoftonline.com/t/v2.0")
        == "https://login.microsoftonline.com/t/discovery/v2.0/keys"
    )


def test_um_jwks_uri_explicito_nao_dispara_descoberta(monkeypatch):
    """Configuração explícita vence — e nem chega a perguntar ao servidor."""
    def _explode(*_a, **_k):  # pragma: no cover - falha o teste se chamada
        raise AssertionError("a descoberta não devia ser consultada")

    monkeypatch.setattr(A, "_jwks_uri_anunciado", _explode)
    provs = A.parse_auth_providers(
        {"providers": [
            {"type": "oidc", "tenant_claim": "org_id", "issuer": "https://idp.test",
             "audience": "a", "jwks_uri": "https://idp.test/chaves"}
        ]}
    )
    assert provs[0].jwks_uri == "https://idp.test/chaves"
