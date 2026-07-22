"""Story ``s-account-scoped-plan`` (was ``s-ws-plan-stripe``) — the
billing→enforcement **bridge**, re-keyed on the BILLING ACCOUNT.

**The product decision under test:** a subscription belongs to a billing
ACCOUNT, and one plan covers every workspace that account owns. Creating a
second workspace is not a second charge.

The MCP quota guard therefore resolves a request's Tier from THREE sources, in
order::

    token `plan` claim  →  AccountPlan store (Stripe-written)  →  Free floor

with the middle step taking TWO hops — ``workspace → Workspace.account_id →
AccountPlan`` — so enforcement follows the account's billing state even when the
token carries no plan claim, while a token that DOES carry an explicit ``plan``
claim still wins (the store is not consulted). The OSS SDK only READS the
AccountPlan; no Stripe code lives here.

Why the two hops instead of one: the previous model keyed the plan on the
WORKSPACE, which forced the biller to fan out one doc per workspace — and
workspace enumeration is by MEMBERSHIP, not ownership, so that fan-out would
have handed a paid tier to workspaces the account never bought.

The tenancy dimension the guard passes in is the workspace id F2 resolves
(identity→membership). With no WorkspaceMembership grants seeded here, F2 falls
back to the legacy tid tenancy, so the token's ``tenant`` claim (``acme``) IS the
resolved workspace id — and the ``Workspace`` doc seeded for it carries the
``account_id`` the plan is keyed on.

Three layers:

1. **Pure** (``_mcp_auth``) — a plan-less token has no explicit claim
   (``tier_from_token`` is None), so the guard knows to consult the store; an
   explicit-claim token short-circuits it.
2. **Integration over a real token context** — a plan-less ``acme`` token whose
   workspace belongs to an account holding ``AccountPlan(pro)`` resolves to
   **pro** caps; with no plan (or no account) it falls to **free**; an explicit
   ``plan=free`` claim is metered as free EVEN WHEN the account holds pro.
3. **Money invariants** — a workspace with NO ``account_id`` gets Free even
   though a paid plan exists in the same store; and one account's plan never
   reaches another account's workspace.

The Tier / Workspace / AccountPlan docs are seeded into the kernel ``_lib`` so
``kernel.tier`` / ``kernel.account_for_workspace`` / ``kernel.account_plan``
resolve them.
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
    # consult the WorkspacePlan store (keyed by workspace) before the Free floor.
    assert A.tier_from_token({"tenant": "acme"}, ["dna.read"]) is None


def test_explicit_plan_claim_is_seen():
    assert A.tier_from_token({"tenant": "acme", "plan": "pro"}, []) == "pro"


# ── 2. integration — over a real token context + seeded Tier/WorkspacePlan ──
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


def _account_plan_doc(account_id: str, tier_id: str) -> dict:
    """An AccountPlan doc — the ACCOUNT→Tier assignment dna-cloud's Stripe
    webhook writes (the OSS SDK only reads it). ONE of these covers every
    workspace whose ``account_id`` matches."""
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "AccountPlan",
        "metadata": {"name": account_id},
        "spec": {"account_id": account_id, "tier_id": tier_id,
                 "source": "stripe", "status": "active"},
    }


def _workspace_doc(workspace_id: str, account_id: str | None) -> dict:
    """A Workspace doc naming the BILLING ACCOUNT that owns it — the first hop of
    the guard's resolution. ``account_id=None`` is the fail-closed case."""
    return {
        "apiVersion": "github.com/ruinosus/dna/tenant/v1",
        "kind": "Workspace",
        "metadata": {"name": workspace_id},
        "spec": {
            "workspace_id": workspace_id,
            "name": workspace_id,
            "slug": workspace_id,
            "created_by": "founder@example.com",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_id": account_id,
        },
    }


async def _seed(
    dna_dir,
    *,
    account_plan: tuple[str, str] | None,
    workspaces: tuple[tuple[str, str | None], ...] = (("acme", "acct-acme"),),
) -> None:
    """Seed a tight Free + a roomy Pro Tier into ``_lib`` (so the resolved tier is
    observable by which cap bites), the ``Workspace``→account mapping(s), and
    optionally an AccountPlan assignment."""
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
    for workspace_id, account_id in workspaces:
        await live.kernel.write_document(
            "_lib", "Workspace", workspace_id,
            _workspace_doc(workspace_id, account_id),
        )
    if account_plan is not None:
        account_id, tier_id = account_plan
        await live.kernel.write_document(
            "_lib", "AccountPlan", account_id,
            _account_plan_doc(account_id, tier_id),
        )


def _reset_store() -> None:
    Q.DEFAULT_STORE.reset()


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


# ── helpers for the integration cases ───────────────────────────────────────


def _client_bits():
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    return Client, BearerAuth, M


def _expect_pro(dna_dir, http_server, token_tenant, *, server_auth, mint):
    """5 metered calls all pass — far past the Free cap of 2, so only the roomy
    Pro caps can explain it."""
    Client, BearerAuth, M = _client_bits()
    server = M.build_server(base_dir=str(dna_dir), auth=server_auth)
    token = mint(tenant=token_tenant, plan=None)

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for _ in range(5):
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE

    with http_server(server) as url:
        asyncio.run(go(url))


def _expect_free(dna_dir, http_server, token_tenant, *, server_auth, mint,
                 plan=None):
    """2 calls pass, the 3rd is denied — the Free cap biting is the observable
    proof that no paid tier was resolved."""
    Client, BearerAuth, M = _client_bits()
    server = M.build_server(base_dir=str(dna_dir), auth=server_auth)
    token = mint(tenant=token_tenant, plan=plan)

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for _ in range(2):
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE
            with pytest.raises(Exception) as ei:  # noqa: PT011 — ToolError/McpError
                await client.call_tool("list_stories", {"scope": _SCOPE})
            assert "quota" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))


# ── 2. the bridge resolves workspace → account → plan ───────────────────────


def test_plan_less_token_resolves_through_the_account_to_the_store_tier(
    dna_dir, http_server
):
    """A plan-less ``acme`` token, whose workspace names account ``acct-acme``,
    which holds ``AccountPlan(pro)`` → the guard resolves **pro** caps.

    This is the bridge, and both hops are exercised: the workspace does not
    carry a tier at all, so the only way to reach pro is through its account."""
    verifier, mint = _verifier_and_mint()
    asyncio.run(_seed(dna_dir, account_plan=("acct-acme", "pro")))
    _expect_pro(dna_dir, http_server, "acme", server_auth=verifier, mint=mint)


def test_plan_less_token_no_account_plan_falls_to_free(dna_dir, http_server):
    """The workspace HAS an account, but that account bought nothing → the Free
    floor. Proves the fallback order bottoms out at Free with an empty store."""
    verifier, mint = _verifier_and_mint()
    asyncio.run(_seed(dna_dir, account_plan=None))
    _expect_free(dna_dir, http_server, "acme", server_auth=verifier, mint=mint)


def test_explicit_plan_claim_wins_over_store(dna_dir, http_server):
    """A token WITH an explicit ``plan=free`` claim is metered as **free** EVEN
    when the account holds pro — the claim wins and the store is NOT consulted
    (neither hop runs). Proven by the Free cap biting on the 3rd call."""
    verifier, mint = _verifier_and_mint()
    asyncio.run(_seed(dna_dir, account_plan=("acct-acme", "pro")))
    _expect_free(dna_dir, http_server, "acme", server_auth=verifier, mint=mint,
                 plan="free")


# ── 3. the money invariants ────────────────────────────────────────────────


def test_workspace_without_an_account_gets_free_not_a_borrowed_tier(
    dna_dir, http_server
):
    """**Fail-closed.** The workspace carries NO ``account_id``, while a paid
    ``AccountPlan(pro)`` sits in the very same store.

    It must get the **Free floor** — not that plan, not any plan. "No account"
    may never soften into "some account": the store is small and the paid doc is
    the only one in it, which is exactly the shape under which a sloppy
    resolution would hand it out."""
    verifier, mint = _verifier_and_mint()
    asyncio.run(_seed(
        dna_dir,
        account_plan=("acct-acme", "pro"),
        workspaces=(("acme", None),),   # no account_id
    ))
    _expect_free(dna_dir, http_server, "acme", server_auth=verifier, mint=mint)


def test_one_accounts_plan_never_reaches_another_accounts_workspace(
    dna_dir, http_server
):
    """**Isolation.** Acme paid for Pro. The ``globex`` workspace belongs to
    ``acct-globex``, which paid for nothing — and must be metered at Free even
    though a Pro plan exists and Acme's own workspace correctly resolves to it.

    Getting this wrong is not a bug, it is revenue leaking to a non-payer."""
    verifier, mint = _verifier_and_mint()
    asyncio.run(_seed(
        dna_dir,
        account_plan=("acct-acme", "pro"),
        workspaces=(("acme", "acct-acme"), ("globex", "acct-globex")),
    ))
    # The payer's workspace resolves to pro …
    _expect_pro(dna_dir, http_server, "acme", server_auth=verifier, mint=mint)
    # … and the other account's workspace does not.
    _reset_store()
    _expect_free(dna_dir, http_server, "globex", server_auth=verifier, mint=mint)


def test_one_plan_covers_every_workspace_the_account_owns(dna_dir, http_server):
    """**The decision itself.** Acme's SECOND workspace — created after the
    purchase, with no billing write of its own — is covered by the same plan.

    Under the retired per-workspace model this workspace would have sat on Free
    until somebody remembered to fan a doc out to it."""
    verifier, mint = _verifier_and_mint()
    asyncio.run(_seed(
        dna_dir,
        account_plan=("acct-acme", "pro"),
        workspaces=(("acme", "acct-acme"), ("acme2", "acct-acme")),
    ))
    _expect_pro(dna_dir, http_server, "acme2", server_auth=verifier, mint=mint)
