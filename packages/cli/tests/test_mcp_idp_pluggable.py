"""Story ``s-mcp-idp-pluggable`` — the **pluggable N-provider IdP layer**.

A serious IdP always exposes JWKS + OIDC discovery, so a provider is a **block of
config, not code**. This suite proves the layer on both levels:

1. **Pure core (no server)** — ``parse_auth_providers`` turns an
   ``auth.providers[]`` mapping into validated :class:`ProviderConfig`s: per-type
   ``tenant_claim`` defaults (Entra=``tid``, Clerk/WorkOS=``org_id``), JWKS derived
   from the issuer, the Entra ``common`` relaxed-issuer / audience-boundary rule,
   and fail-loud validation. Plus the pure issuer→provider router.

2. **End-to-end multi-provider over real JWT + HTTP** — TWO emulated OIDC issuers
   (``RSAKeyPair``, distinct issuers/audiences/**tenant-claim keys**) configured as
   two providers hit the SAME server: a token from provider A (tenant via claim
   ``tenant``) and one from provider B (tenant via claim ``org``) each resolve to
   the RIGHT tenant; a token from an UNconfigured issuer is denied; cross-tenant is
   denied; and PRM (RFC 9728) advertises BOTH issuers. Same config, N providers.

The **real Entra** login→token→server check is DEFERRED to the owner's ``azd up``
(a ``requires_azure`` skip records the step) — no Azure credential is needed here.
"""
from __future__ import annotations

import asyncio
import os
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

_ISS_A = "https://idp-a.test/"
_AUD_A = "dna-a"
_ISS_B = "https://idp-b.test/"
_AUD_B = "dna-b"


# ── pure core: a provider is a config block ────────────────────────────────


def test_entra_defaults_tid_and_derives_jwks_and_relaxes_common():
    (p,) = A.parse_auth_providers({"providers": [{
        "type": "entra",
        "issuer": "https://login.microsoftonline.com/common/v2.0",
        "audience": "app-123",
    }]})
    assert p.tenant_claim == "tid"                                   # Entra default
    assert p.jwks_uri == "https://login.microsoftonline.com/common/discovery/v2.0/keys"
    assert A.verifier_issuer(p) is None                              # common → audience-only


def test_entra_per_tenant_issuer_stays_strict():
    (p,) = A.parse_auth_providers({"providers": [{
        "type": "entra",
        "issuer": "https://login.microsoftonline.com/tid-abc/v2.0",
        "audience": "app-123",
    }]})
    assert A.verifier_issuer(p) == "https://login.microsoftonline.com/tid-abc/v2.0"
    assert p.jwks_uri == "https://login.microsoftonline.com/tid-abc/discovery/v2.0/keys"


def test_clerk_and_workos_default_org_id_claim():
    provs = A.parse_auth_providers({"providers": [
        {"type": "clerk", "issuer": "https://clerk.acme.dev"},
        {"type": "workos", "issuer": "https://api.workos.com", "audience": "x"},
    ]})
    assert [p.tenant_claim for p in provs] == ["org_id", "org_id"]
    assert provs[0].jwks_uri == "https://clerk.acme.dev/.well-known/jwks.json"


def test_generic_oidc_requires_tenant_claim():
    with pytest.raises(ValueError, match="tenant_claim.*required"):
        A.parse_auth_providers({"providers": [
            {"type": "oidc", "issuer": "https://idp.example.com", "audience": "a"},
        ]})
    # named → accepted, and honored.
    (p,) = A.parse_auth_providers({"providers": [
        {"type": "oidc", "issuer": "https://idp.example.com", "audience": "a",
         "tenant_claim": "org"},
    ]})
    assert p.tenant_claim == "org"


def test_explicit_jwks_uri_overrides_derivation():
    (p,) = A.parse_auth_providers({"providers": [
        {"type": "oidc", "issuer": "https://idp.example.com", "audience": "a",
         "tenant_claim": "org", "jwks_uri": "https://keys.example.com/jwks"},
    ]})
    assert p.jwks_uri == "https://keys.example.com/jwks"


def test_scope_prefix_is_per_provider():
    (p,) = A.parse_auth_providers({"providers": [
        {"type": "oidc", "issuer": "https://i", "tenant_claim": "org",
         "public_key": "PEM", "scope_prefix": "org:"},
    ]})
    assert p.scope_prefix == "org:"


# fail-loud validation ------------------------------------------------------


def test_no_auth_section_fails_loud():
    with pytest.raises(ValueError, match="auth.providers"):
        A.parse_auth_providers(None)


def test_empty_providers_fails_loud():
    with pytest.raises(ValueError, match="non-empty list"):
        A.parse_auth_providers({"providers": []})


def test_provider_without_type_fails_loud():
    with pytest.raises(ValueError, match="`type` is required"):
        A.parse_auth_providers({"providers": [{"issuer": "https://i"}]})


def test_unknown_provider_type_fails_loud():
    with pytest.raises(ValueError, match="unknown provider type"):
        A.parse_auth_providers({"providers": [{"type": "banana", "issuer": "https://i"}]})


def test_no_key_source_fails_loud():
    with pytest.raises(ValueError, match="no key source"):
        A.parse_auth_providers({"providers": [{"type": "oidc", "tenant_claim": "org"}]})


def test_entra_multitenant_needs_audience():
    with pytest.raises(ValueError, match="needs an\n?\\s*`?audience"):
        A.parse_auth_providers({"providers": [{
            "type": "entra",
            "issuer": "https://login.microsoftonline.com/organizations/v2.0",
        }]})


# pure issuer→provider router ----------------------------------------------


def test_select_provider_for_issuer_exact_and_entra_common():
    provs = A.parse_auth_providers({"providers": [
        {"type": "oidc", "issuer": _ISS_B, "audience": _AUD_B, "tenant_claim": "org"},
        {"type": "entra", "issuer": "https://login.microsoftonline.com/common/v2.0",
         "audience": "app"},
    ]})
    assert A.select_provider_for_issuer(provs, _ISS_B).type == "oidc"      # exact
    # Entra `common` mints a per-tenant issuer — routed by host.
    real = "https://login.microsoftonline.com/REAL-TID/v2.0"
    assert A.select_provider_for_issuer(provs, real).type == "entra"
    assert A.select_provider_for_issuer(provs, "https://nope.example.com") is None


# ── config.yaml carries the auth section (opaque passthrough) ──────────────


def test_dna_config_passthrough_and_providers_from_config(tmp_path, monkeypatch):
    from dna.config import load_config

    (tmp_path / "dna.config.yaml").write_text(
        "source: file://.dna\n"
        "auth:\n"
        "  providers:\n"
        "    - type: entra\n"
        "      issuer: https://login.microsoftonline.com/common/v2.0\n"
        "      audience: app-123\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "dna.config.yaml")
    assert cfg is not None and isinstance(cfg.auth, dict)          # opaque passthrough
    monkeypatch.chdir(tmp_path)
    (p,) = A.providers_from_config()
    assert p.type == "entra" and p.tenant_claim == "tid"


def test_providers_from_config_requires_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="needs a dna.config.yaml"):
        A.providers_from_config()


# ── end-to-end: TWO emulated providers, one server ─────────────────────────


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _two_providers_and_mints():
    """Build two emulated OIDC IdPs (distinct issuers/audiences/**claim keys**),
    configured as two providers through the SAME config path (public_key inline —
    no network JWKS). Provider A reads tenant from claim ``tenant``; provider B
    from claim ``org``. Return (providers, mintA, mintB, mint_unconfigured)."""
    from fastmcp.server.auth.providers.jwt import RSAKeyPair

    kp_a, kp_b, kp_x = (RSAKeyPair.generate() for _ in range(3))
    providers = A.parse_auth_providers({"providers": [
        {"type": "oidc", "issuer": _ISS_A, "audience": _AUD_A,
         "tenant_claim": "tenant", "public_key": kp_a.public_key},
        {"type": "oidc", "issuer": _ISS_B, "audience": _AUD_B,
         "tenant_claim": "org", "public_key": kp_b.public_key},
    ]})

    def mint_a(tenant):
        return kp_a.create_token(issuer=_ISS_A, audience=_AUD_A, subject="ua",
                                 scopes=["dna.read"], additional_claims={"tenant": tenant})

    def mint_b(org):
        return kp_b.create_token(issuer=_ISS_B, audience=_AUD_B, subject="ub",
                                 scopes=["dna.read"], additional_claims={"org": org})

    def mint_unconfigured():
        # signed by a key/issuer NO configured provider knows.
        return kp_x.create_token(issuer="https://rogue.test/", audience="rogue",
                                 subject="ux", scopes=["dna.read"],
                                 additional_claims={"tenant": "acme"})

    return providers, mint_a, mint_b, mint_unconfigured


def _compose_tenant(url, token):
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    async def go():
        async with Client(url, auth=BearerAuth(token)) as client:
            res = await client.call_tool(
                "compose_prompt", {"agent": _AGENT, "scope": _SCOPE})
            return res.structured_content

    return asyncio.run(go())


def test_two_providers_each_resolve_their_own_tenant(dna_dir, http_server):
    """The SAME server, two providers: a provider-A token (claim ``tenant=acme``)
    and a provider-B token (claim ``org=globex``) each compose scoped to the RIGHT
    tenant — proving claim→tenant is PER PROVIDER, from ONE config."""
    providers, mint_a, mint_b, _ = _two_providers_and_mints()
    server = M.build_server(base_dir=str(dna_dir), auth=A.build_auth_from_config(providers))

    with http_server(server) as url:
        a = _compose_tenant(url, mint_a("acme"))
        b = _compose_tenant(url, mint_b("globex"))

    assert a["tenant"] == "acme"      # provider A: read from the `tenant` claim
    assert b["tenant"] == "globex"    # provider B: read from the `org` claim


def test_unconfigured_issuer_denied(dna_dir, http_server):
    """A well-formed token signed by an issuer NO provider is configured for is
    rejected — the composite router accepts only configured issuers."""
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    providers, _, _, mint_rogue = _two_providers_and_mints()
    server = M.build_server(base_dir=str(dna_dir), auth=A.build_auth_from_config(providers))

    async def go(url):
        with pytest.raises(Exception):  # noqa: PT011 — 401 at initialize
            async with Client(url, auth=BearerAuth(mint_rogue())) as client:
                await client.list_tools()

    with http_server(server) as url:
        asyncio.run(go(url))


def test_cross_tenant_denied_multi_provider(dna_dir, http_server):
    """A provider-A token (tenant=acme) that explicitly asks for tenant=other is
    denied — the fail-closed policy holds under the multi-provider layer."""
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    providers, mint_a, _, _ = _two_providers_and_mints()
    server = M.build_server(base_dir=str(dna_dir), auth=A.build_auth_from_config(providers))

    async def go(url):
        async with Client(url, auth=BearerAuth(mint_a("acme"))) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool(
                    "compose_prompt",
                    {"agent": _AGENT, "scope": _SCOPE, "tenant": "other"})
            assert "tenant" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))


def test_prm_advertises_all_provider_issuers(dna_dir, http_server, free_port):
    """Wrapped as a Resource Server, the multi-provider layer advertises PRM
    (RFC 9728) listing EVERY configured provider's issuer as an authorization
    server — one discovery document, N providers."""
    import httpx

    providers, _, _, _ = _two_providers_and_mints()
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    auth = A.build_auth_from_config(providers, resource_url=base_url)
    server = M.build_server(base_dir=str(dna_dir), auth=auth)

    with http_server(server, port=port):
        resp = httpx.get(
            f"{base_url}/.well-known/oauth-protected-resource/mcp", timeout=10)
        assert resp.status_code == 200, resp.text
        servers = resp.json()["authorization_servers"]
    assert any(_ISS_A.rstrip("/") in s for s in servers)
    assert any(_ISS_B.rstrip("/") in s for s in servers)


# ── the real Entra loop — DEFERRED to the owner's `azd up` ─────────────────


@pytest.mark.skipif(
    not os.environ.get("DNA_MCP_ENTRA_E2E"),
    reason="real Entra login→token→server is validated on the owner's `azd up` "
           "(set DNA_MCP_ENTRA_E2E + Azure app creds to run it here)",
)
def test_entra_end_to_end_real_login():  # pragma: no cover — owner runs on azd up
    """Placeholder for the REAL Entra check: an Azure-issued token (login →
    access token for the DNA app registration) verified by an ``entra`` provider,
    its ``tid`` mapped to the DNA tenant. Deferred to `azd up` — see the
    Multi-provider auth guide's Entra + azd-up step. No Azure credential here."""
    raise AssertionError("run under `azd up` with a real Entra app registration")
