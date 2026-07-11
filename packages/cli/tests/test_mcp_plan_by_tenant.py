"""Story ``s-dna-cloud-plan-by-tenant`` — the billing→enforcement **bridge**.

The MCP quota guard resolves a request's Tier from THREE sources, in order:

    token `plan` claim  →  TenantPlan store (Stripe-written)  →  Free floor

so enforcement follows billing state (which dna-cloud's Stripe webhook writes into
the ``TenantPlan`` Kind) even when the token itself carries no plan claim — while
a token that DOES carry an explicit ``plan`` claim still wins (the store is not
consulted). The OSS SDK only READS the TenantPlan; no Stripe code lives here.

Two layers:

1. **Pure** (``_mcp_auth``) — a plan-less token has no explicit claim
   (``tier_from_token`` is None), so the guard knows to consult the store; an
   explicit-claim token short-circuits it.
2. **Integration over a real token context** — a plan-less ``acme`` token with a
   ``TenantPlan(acme→pro)`` seeded resolves to **pro** caps (many calls sail past
   the tight Free cap); with NO TenantPlan it falls to **free** (the 3rd call is
   denied); an explicit ``plan=free`` claim is metered as free EVEN WHEN
   ``TenantPlan(acme→pro)`` exists (proving the claim wins / the store is skipped).

The Tier + TenantPlan docs are seeded into the kernel ``_lib`` so
``kernel.tier`` / ``kernel.tenant_plan`` resolve them.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna_cli import _mcp_auth as A
from dna_cli import _mcp_quota as Q


# ── 1. pure — a plan-less token has no explicit claim ──────────────────────


def test_plan_less_token_has_no_explicit_claim():
    # No plan claim, no plan scope → tier_from_token is None → the guard will
    # consult the TenantPlan store (keyed by tenant) before the Free floor.
    assert A.tier_from_token({"tenant": "acme"}, ["dna.read"]) is None


def test_explicit_plan_claim_is_seen():
    assert A.tier_from_token({"tenant": "acme", "plan": "pro"}, []) == "pro"


# ── 2. integration — over a real token context + seeded Tier/TenantPlan ─────
#
# Needs fastmcp (the server + token context) — ``importorskip``s it, exactly like
# the other MCP suites. The pure tests above run regardless.

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"


def _tier_doc(tier_id: str, *, calls_per_day: int | None, families: list[str],
              memory_mode: str, rate_per_sec: int = 100) -> dict:
    """A Tier doc — caps live HERE (the doc), never in code."""
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "Tier",
        "metadata": {"name": tier_id},
        "spec": {
            "tier_id": tier_id,
            "display_name": tier_id.title(),
            "price_usd_month": 0,
            "calls_per_day": calls_per_day,
            "rate_per_sec": rate_per_sec,
            "max_tenants": 1,
            "feature_families": families,
            "memory_mode": memory_mode,
            "aliases": [],
        },
    }


def _tenant_plan_doc(tenant: str, tier_id: str) -> dict:
    """A TenantPlan doc — the tenant→Tier assignment dna-cloud's Stripe webhook
    writes (the OSS SDK only reads it)."""
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "TenantPlan",
        "metadata": {"name": tenant},
        "spec": {"tenant": tenant, "tier_id": tier_id, "source": "stripe",
                 "status": "active"},
    }


async def _seed(dna_dir, *, tenant_plan: tuple[str, str] | None) -> None:
    """Seed a tight Free + a roomy Pro Tier into ``_lib`` (so the resolved tier is
    observable by which cap bites), plus optionally a TenantPlan assignment."""
    from dna_cli import _mcp_server as M

    live = await M.boot_live(base_dir=str(dna_dir))
    await live.kernel.write_document(
        "_lib", "Tier", "free",
        _tier_doc("free", calls_per_day=2,
                  families=["definitions", "sdlc", "memory"], memory_mode="read"),
    )
    await live.kernel.write_document(
        "_lib", "Tier", "pro",
        _tier_doc("pro", calls_per_day=10000,
                  families=["definitions", "sdlc", "memory", "emit"],
                  memory_mode="write"),
    )
    if tenant_plan is not None:
        tenant, tier_id = tenant_plan
        await live.kernel.write_document(
            "_lib", "TenantPlan", tenant, _tenant_plan_doc(tenant, tier_id),
        )


def _reset_store() -> None:
    Q.DEFAULT_STORE._day_counts.clear()  # type: ignore[attr-defined]
    Q.DEFAULT_STORE._calls.clear()  # type: ignore[attr-defined]


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    _reset_store()
    return dst


def _verifier_and_mint():
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER, audience=_AUDIENCE)

    def mint(*, tenant: str | None, plan: str | None):
        claims: dict = {}
        if tenant:
            claims["tenant"] = tenant
        if plan:
            claims["plan"] = plan
        return kp.create_token(
            issuer=_ISSUER, audience=_AUDIENCE, subject="user-1",
            scopes=["dna.read"], additional_claims=claims,
        )

    return verifier, mint


def test_plan_less_token_resolves_to_store_tier(dna_dir, http_server):
    """A plan-less ``acme`` token WITH a ``TenantPlan(acme→pro)`` seeded → the
    guard resolves **pro** caps (calls_per_day=10000), so 5 calls (> the Free cap
    of 2) all pass. This is the bridge: enforcement follows the Stripe-written
    assignment even though the token carries no plan claim."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    asyncio.run(_seed(dna_dir, tenant_plan=("acme", "pro")))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan=None)  # NO plan claim

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for _ in range(5):  # far past the Free cap of 2 → proves pro
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE

    with http_server(server) as url:
        asyncio.run(go(url))


def test_plan_less_token_no_store_falls_to_free(dna_dir, http_server):
    """A plan-less ``acme`` token with NO TenantPlan → the Free floor
    (calls_per_day=2), so the 3rd metered call is denied. Proves the fallback
    order bottoms out at Free when the store is empty."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    asyncio.run(_seed(dna_dir, tenant_plan=None))  # no TenantPlan
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan=None)

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for _ in range(2):  # within the Free cap of 2
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE
            with pytest.raises(Exception) as ei:  # noqa: PT011 — ToolError/McpError
                await client.call_tool("list_stories", {"scope": _SCOPE})
            assert "quota" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))


def test_explicit_plan_claim_wins_over_store(dna_dir, http_server):
    """A token WITH an explicit ``plan=free`` claim is metered as **free** EVEN
    when a ``TenantPlan(acme→pro)`` exists — the claim wins and the store is NOT
    consulted. Proven by the Free cap (2) biting on the 3rd call; had the store
    been consulted, pro (10000) would let it through."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    asyncio.run(_seed(dna_dir, tenant_plan=("acme", "pro")))  # store says pro …
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")  # … but the claim says free

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for _ in range(2):
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool("list_stories", {"scope": _SCOPE})
            assert "quota" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))
