"""Story ``s-memory-mcp-hardening`` — validate + harden the DNA Cloud **memory**
MCP tools (recall / remember / consolidate), the substrate of the memory
co-pillar (``adr-dna-cloud-memory``).

Three properties are proven here, mirroring ``test_mcp_quota.py`` /
``test_mcp_auth.py``:

1. **Tenant isolation** — a tenant's ``recall`` never returns another tenant's
   memories; ``remember`` writes ONLY to the caller's tenant overlay; the shared
   base (no-tenant) memory stays visible to everyone. Proven at the pure-impl
   level (data layer, no server) so it holds regardless of auth/transport.

2. **memory_mode gating** — the FINER read-vs-write split WITHIN the ``memory``
   feature family, read from the ``Tier`` spec (``memory_mode``): ``read`` grants
   recall only; ``write`` (remember/consolidate) needs ``memory_mode='write'``.
   Free=read, Pro=write — same code, different DATA (zero hardcode). Proven pure
   (``enforce_memory_mode``) and end-to-end over a real token + seeded Tier docs.

3. **Cross-client sanity** — the tools are transport-agnostic: two SEPARATE MCP
   client connections authenticating as the SAME tenant share the SAME memory
   (Claude Code writes, Cursor recalls) — the ADR's "zero cross-client leak" AND
   "any client authenticating as the tenant shares the same memory".

The CRITICAL invariant (inherited from the quota guard): memory_mode is enforced
ONLY with a token present — the OSS/stdio path (``auth=None``) is untouched.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna_cli import _mcp_quota as Q

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"


# ── 1. memory_mode — pure enforcement (caps are DATA, read from a Tier spec) ─


def _free_spec() -> dict:
    """A Free-tier ``spec`` — memory IS in the family list (the coarse gate opens)
    but ``memory_mode`` is ``read`` (the finer gate: recall only)."""
    return {
        "tier_id": "free",
        "calls_per_day": 1000,
        "rate_per_sec": 100,
        "feature_families": ["definitions", "sdlc", "memory"],
        "memory_mode": "read",
    }


def _pro_spec() -> dict:
    return {
        "tier_id": "pro",
        "calls_per_day": 10000,
        "rate_per_sec": 100,
        "feature_families": ["definitions", "sdlc", "memory", "emit"],
        "memory_mode": "write",
    }


def test_read_tier_allows_recall():
    # read op needs rank(read)=1; free grants read=1 → allowed.
    Q.enforce_memory_mode(caps=_free_spec(), tier="free", op="read")


def test_read_tier_denies_write():
    # write op needs rank(write)=2; free grants read=1 → denied.
    with pytest.raises(Q.MemoryModeError, match="write"):
        Q.enforce_memory_mode(caps=_free_spec(), tier="free", op="write")


def test_write_tier_allows_write():
    Q.enforce_memory_mode(caps=_pro_spec(), tier="pro", op="write")
    Q.enforce_memory_mode(caps=_pro_spec(), tier="pro", op="read")


def test_free_vs_pro_same_code_different_data():
    """SAME code, DIFFERENT data: Pro's ``memory_mode='write'`` allows a write where
    Free's ``memory_mode='read'`` denies it — the split is driven by the Tier spec,
    never a literal."""
    Q.enforce_memory_mode(caps=_pro_spec(), tier="pro", op="write")
    with pytest.raises(Q.MemoryModeError):
        Q.enforce_memory_mode(caps=_free_spec(), tier="free", op="write")


def test_mode_none_denies_all():
    caps = dict(_free_spec(), memory_mode="none")
    with pytest.raises(Q.MemoryModeError):
        Q.enforce_memory_mode(caps=caps, tier="none-tier", op="read")
    with pytest.raises(Q.MemoryModeError):
        Q.enforce_memory_mode(caps=caps, tier="none-tier", op="write")


def test_missing_mode_fails_closed():
    # A configured tier that omits memory_mode → default none → any op denied.
    caps = {"tier_id": "x", "feature_families": ["memory"]}
    with pytest.raises(Q.MemoryModeError):
        Q.enforce_memory_mode(caps=caps, tier="x", op="read")


def test_empty_caps_enforce_nothing():
    # Unconfigured / OSS source → empty spec → no-op (mirrors enforce_quota).
    Q.enforce_memory_mode(caps={}, tier="free", op="write")
    Q.enforce_memory_mode(caps={}, tier="free", op="read")


# ── 2. tenant isolation — pure impl (data layer, no server/auth/transport) ──


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope, wired via DNA_BASE_DIR."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def test_remember_recall_are_tenant_isolated(dna_dir):
    """Two tenants write memories under the SAME scope; each ``recall`` sees ONLY
    its own tenant's memory — never the other's. The core co-pillar invariant."""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.remember_impl(
            live, "ACME secret roadmap pivot alpha", scope=_SCOPE, tenant="acme")
        await M.remember_impl(
            live, "GLOBEX secret roadmap pivot beta", scope=_SCOPE, tenant="globex")
        acme = await M.recall_impl(live, "secret roadmap pivot", scope=_SCOPE,
                                   tenant="acme", k=10)
        globex = await M.recall_impl(live, "secret roadmap pivot", scope=_SCOPE,
                                     tenant="globex", k=10)
        return acme, globex

    acme, globex = asyncio.run(scenario())
    acme_names = {h["name"] for h in acme["hits"]}
    globex_names = {h["name"] for h in globex["hits"]}
    # each tenant sees its OWN memory ...
    assert any("acme" in n for n in acme_names), acme_names
    assert any("globex" in n for n in globex_names), globex_names
    # ... and NEITHER sees the other's (zero cross-tenant leak).
    assert not (acme_names & globex_names)
    assert not any("globex" in n for n in acme_names)
    assert not any("acme" in n for n in globex_names)


def test_base_memory_is_shared_across_tenants(dna_dir):
    """A no-tenant (base) ``remember`` — the SDLC-board / OSS path — is the SHARED
    product memory: visible to the no-tenant recall AND to every tenant's recall.
    (Base is the shared floor; only per-tenant overlays are isolated.)"""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        out = await M.remember_impl(
            live, "BASE shared knowledge gamma", scope=_SCOPE, tenant=None)
        base = await M.recall_impl(live, "shared knowledge", scope=_SCOPE, k=10)
        tenant = await M.recall_impl(
            live, "shared knowledge", scope=_SCOPE, tenant="acme", k=10)
        return out, base, tenant

    out, base, tenant = asyncio.run(scenario())
    assert out["name"] in {h["name"] for h in base["hits"]}
    assert out["name"] in {h["name"] for h in tenant["hits"]}


# ── 3. integration — memory_mode over a real token + seeded Tier docs ───────
#
# These need fastmcp (server + token context) — each ``importorskip``s it, like
# the other MCP suites. The pure + impl tests above run regardless.


def _tier_doc(tier_id: str, *, families: list[str], memory_mode: str,
              calls_per_day: int = 10000, rate_per_sec: int = 100) -> dict:
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
        },
    }


async def _seed_tiers(dna_dir) -> None:
    """Seed Free (memory + memory_mode=read) + Pro (memory + memory_mode=write) so
    ``kernel.tier`` resolves them. Free KEEPS ``memory`` in its families so the
    family gate PASSES — proving it is ``memory_mode`` (not the family gate) that
    denies a Free write."""
    from dna_cli import _mcp_server as M

    live = await M.boot_live(base_dir=str(dna_dir))
    await live.kernel.write_document(
        "_lib", "Tier", "free",
        _tier_doc("free", families=["definitions", "sdlc", "memory"],
                  memory_mode="read"))
    await live.kernel.write_document(
        "_lib", "Tier", "pro",
        _tier_doc("pro", families=["definitions", "sdlc", "memory", "emit"],
                  memory_mode="write"))


def _reset_store() -> None:
    Q.DEFAULT_STORE.reset()


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


def test_read_tier_recall_ok_but_remember_denied(dna_dir, http_server):
    """A Free (memory_mode=read) token: ``recall`` is allowed (read), but
    ``remember`` is DENIED — and NOT by the family gate (memory IS in Free's
    families) but by ``memory_mode`` (the write refinement)."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            # read op → allowed on a read tier.
            res = await client.call_tool("recall", {"query": "anything", "scope": _SCOPE})
            assert "hits" in res.structured_content
            # write op → denied by memory_mode (message names write/memory_mode).
            with pytest.raises(Exception) as ei:  # noqa: PT011 — ToolError/McpError
                await client.call_tool(
                    "remember", {"summary": "should be gated by memory_mode",
                                 "scope": _SCOPE})
            msg = str(ei.value).lower()
            assert "memory_mode" in msg or "write" in msg

    with http_server(server) as url:
        asyncio.run(go(url))


def test_write_tier_remember_ok(dna_dir, http_server):
    """A Pro (memory_mode=write) token: ``remember`` is allowed and lands in the
    caller's tenant overlay (round-trips through a subsequent recall)."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="pro")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            out = await client.call_tool(
                "remember", {"summary": "pro write: the co-pillar memory lands",
                             "scope": _SCOPE})
            assert out.structured_content["kind"] == "Engram"
            mem = await client.call_tool(
                "recall", {"query": "co-pillar memory", "scope": _SCOPE})
            assert mem.structured_content["hits"]

    with http_server(server) as url:
        asyncio.run(go(url))


def test_cross_client_same_tenant_shares_memory(dna_dir, http_server):
    """Cross-client sanity: two SEPARATE client connections authenticating as the
    SAME tenant (e.g. Claude Code then Cursor) share the SAME memory — one writes,
    the other recalls it. Transport/connection-agnostic, tenant-bound."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="pro")  # write tier + same tenant for both.

    async def go(url):
        # connection #1 (client A, e.g. Claude Code) writes ...
        async with Client(url, auth=BearerAuth(token)) as client_a:
            await client_a.call_tool(
                "remember",
                {"summary": "cross-client capture: portable across every tool",
                 "scope": _SCOPE})
        # ... a DISTINCT connection #2 (client B, e.g. Cursor) recalls it — same
        # tenant token, so it shares the same memory. One event loop keeps the
        # server's source pool loop-consistent (see boot_live); the two `async
        # with` blocks are still two separate MCP client sessions.
        async with Client(url, auth=BearerAuth(token)) as client_b:
            return (await client_b.call_tool(
                "recall", {"query": "cross-client capture", "scope": _SCOPE}
            )).structured_content

    with http_server(server) as url:
        recalled = asyncio.run(go(url))

    names = [h["name"] for h in recalled["hits"]]
    assert any("cross-client" in n for n in names), names


# ── 4. list_memories / forget — pure impl (data layer, no server/auth) ──────
#
# The DNA Cloud memory dashboard calls these two tool names for its memory LIST
# + DELETE. They mirror recall/remember: tenant-aware query + tenant-scoped
# delete, so the same #83 isolation invariant holds at the data layer.


def test_list_memories_returns_tenant_memories(dna_dir):
    """``list_memories`` returns the tenant's own memories with the dashboard's
    fields (name/summary/area/tags/affect/created_at)."""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.remember_impl(
            live, "ACME onboarding lesson delta", scope=_SCOPE, tenant="acme",
            area="onboarding", tags=["a", "b"])
        return await M.list_memories_impl(live, scope=_SCOPE, tenant="acme")

    out = asyncio.run(scenario())
    assert out["scope"] == _SCOPE
    mine = [m for m in out["memories"] if "acme-onboarding" in m["name"]]
    assert mine, out["memories"]
    m = mine[0]
    assert m["summary"] == "ACME onboarding lesson delta"
    assert m["area"] == "onboarding"
    assert set(m["tags"]) == {"a", "b"}
    # every projected memory carries the dashboard's field set.
    for entry in out["memories"]:
        assert set(entry) == {"name", "summary", "area", "tags", "affect", "created_at"}


def test_list_memories_is_tenant_isolated(dna_dir):
    """Tenant A's ``list_memories`` never returns tenant B's memory; the shared
    base memory is visible to both (per #83)."""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.remember_impl(live, "ACME private list epsilon", scope=_SCOPE, tenant="acme")
        await M.remember_impl(live, "GLOBEX private list zeta", scope=_SCOPE, tenant="globex")
        await M.remember_impl(live, "BASE shared list eta", scope=_SCOPE, tenant=None)
        acme = await M.list_memories_impl(live, scope=_SCOPE, tenant="acme")
        globex = await M.list_memories_impl(live, scope=_SCOPE, tenant="globex")
        return acme, globex

    acme, globex = asyncio.run(scenario())
    acme_names = {m["name"] for m in acme["memories"]}
    globex_names = {m["name"] for m in globex["memories"]}
    assert any("acme-private-list" in n for n in acme_names), acme_names
    assert any("globex-private-list" in n for n in globex_names), globex_names
    # zero cross-tenant leak ...
    assert not any("globex" in n for n in acme_names)
    assert not any("acme" in n for n in globex_names)
    # ... but the shared base memory is visible to BOTH tenants.
    assert any("base-shared-list" in n for n in acme_names), acme_names
    assert any("base-shared-list" in n for n in globex_names), globex_names


def test_forget_deletes_own_memory(dna_dir):
    """``forget`` deletes a memory from the tenant's overlay; a subsequent
    ``list_memories``/``recall`` no longer returns it."""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        out = await M.remember_impl(
            live, "ACME forgettable memory theta", scope=_SCOPE, tenant="acme")
        name = out["name"]
        before = await M.list_memories_impl(live, scope=_SCOPE, tenant="acme")
        res = await M.forget_impl(live, name, scope=_SCOPE, tenant="acme")
        after = await M.list_memories_impl(live, scope=_SCOPE, tenant="acme")
        recalled = await M.recall_impl(
            live, "forgettable memory", scope=_SCOPE, tenant="acme", k=10)
        return name, res, before, after, recalled

    name, res, before, after, recalled = asyncio.run(scenario())
    assert res == {"kind": "Engram", "name": name, "forgotten": True}
    assert name in {m["name"] for m in before["memories"]}
    assert name not in {m["name"] for m in after["memories"]}
    assert name not in {h["name"] for h in recalled["hits"]}


def test_forget_nonexistent_is_clean_noop(dna_dir):
    """Forgetting a name that doesn't exist is a clean no-op (``forgotten:
    False``), never a crash/500."""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.forget_impl(
            live, "rem-does-not-exist-0000000000", scope=_SCOPE, tenant="acme")

    res = asyncio.run(scenario())
    assert res == {"kind": "Engram", "name": "rem-does-not-exist-0000000000",
                   "forgotten": False}


def test_forget_never_hard_deletes_base_nor_touches_other_tenant(dna_dir):
    """``forget`` is a bi-temporal DEMOTION into the caller's OWN overlay — it
    NEVER hard-deletes the shared base and NEVER reaches another tenant's overlay
    (#83). Concretely, when acme forgets a base-resolved memory it stamps a
    tombstone in ITS overlay only; the base doc itself survives (still listed for
    the no-tenant/base view AND still inherited by globex), and globex's own
    private memory is untouched. And acme forgetting globex's PRIVATE overlay doc
    is a clean no-op — acme cannot see, let alone forget, another tenant's
    overlay memory (KeyError → ``forgotten: False``)."""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        base = await M.remember_impl(live, "BASE undeletable iota", scope=_SCOPE, tenant=None)
        other = await M.remember_impl(
            live, "GLOBEX undeletable kappa", scope=_SCOPE, tenant="globex")
        # acme forgets the base-resolved memory → demoted in ACME's overlay only.
        r_base = await M.forget_impl(live, base["name"], scope=_SCOPE, tenant="acme")
        # acme tries to forget globex's PRIVATE overlay doc → cannot reach it.
        r_other = await M.forget_impl(live, other["name"], scope=_SCOPE, tenant="acme")
        base_ls = await M.list_memories_impl(live, scope=_SCOPE, tenant=None)
        globex_ls = await M.list_memories_impl(live, scope=_SCOPE, tenant="globex")
        return base, other, r_base, r_other, base_ls, globex_ls

    base, other, r_base, r_other, base_ls, globex_ls = asyncio.run(scenario())
    # acme forgetting an inherited base memory is a demotion in acme's overlay ...
    assert r_base["forgotten"] is True
    # ... but the base doc itself is NEVER hard-deleted — the shared/base view
    # still lists it, and globex still inherits it (no cross-tenant leak).
    assert base["name"] in {m["name"] for m in base_ls["memories"]}
    assert base["name"] in {m["name"] for m in globex_ls["memories"]}
    # acme CANNOT reach globex's private overlay doc → clean no-op, and globex
    # still sees its own memory untouched.
    assert r_other["forgotten"] is False
    assert other["name"] in {m["name"] for m in globex_ls["memories"]}


# ── 5. list_memories / forget — memory_mode gating (over a real token) ───────


def test_list_memories_allowed_on_read_tier(dna_dir, http_server):
    """``list_memories`` is a READ op → allowed on a Free (memory_mode=read)
    tier, like ``recall``."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            res = await client.call_tool("list_memories", {"scope": _SCOPE})
            assert "memories" in res.structured_content

    with http_server(server) as url:
        asyncio.run(go(url))


def test_forget_denied_on_read_tier(dna_dir, http_server):
    """``forget`` is a WRITE op → DENIED on a Free (memory_mode=read) tier by
    ``memory_mode`` (NOT the family gate — memory IS in Free's families)."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011 — ToolError/McpError
                await client.call_tool("forget", {"name": "rem-anything", "scope": _SCOPE})
            msg = str(ei.value).lower()
            assert "memory_mode" in msg or "write" in msg

    with http_server(server) as url:
        asyncio.run(go(url))


def test_forget_allowed_on_write_tier(dna_dir, http_server):
    """``forget`` is allowed on a Pro (memory_mode=write) tier: a remembered
    memory can be forgotten, and the forget reports ``forgotten: True``."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="pro")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            out = await client.call_tool(
                "remember", {"summary": "pro write then forget lambda", "scope": _SCOPE})
            name = out.structured_content["name"]
            res = await client.call_tool("forget", {"name": name, "scope": _SCOPE})
            assert res.structured_content == {
                "kind": "Engram", "name": name, "forgotten": True}

    with http_server(server) as url:
        asyncio.run(go(url))
