"""Story ``s-dna-cloud-quota-enforcement`` — the DNA Cloud **quota guard**.

The plan/tier twin of the auth↔tenancy bridge: a token's *plan* claim → a
``Tier``; every MCP tool call is metered + rate-limited + feature-gated against
that tier's caps — and the caps come from the ``Tier`` Kind ``spec`` (via
``kernel.tier``), never a literal in code.

Three layers, mirroring ``test_mcp_auth.py``:

1. **Pure tier resolution** (``_mcp_auth.tier_from_token`` / ``resolve_tier``) —
   claim beats scope; the Free floor (missing tier is Free, never denied, never
   unlimited). No server.
2. **Pure enforcement** (``_mcp_quota.enforce_quota``) — family gate, daily quota,
   rate limit, and the null-cap = unlimited rule — all read from a ``spec`` dict, so
   Free vs Pro behave differently from the SAME code (caps are data).
3. **Integration over a real token context** — a Free-plan token meters (the cap+1
   call is denied), a read-only tier gates a write family, and an UNauthenticated
   server (``auth=None``) meters NOTHING (calls sail past the cap). The Free/Pro
   Tier docs are seeded into the kernel ``_lib`` so ``kernel.tier`` resolves them.

The CRITICAL invariant proven here: quota is enforced ONLY with a token present.
No token (stdio / local / ``auth=None``) → identity, unlimited — the OSS path is
untouched, exactly like the tenant bridge.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna_cli import _mcp_auth as A
from dna_cli import _mcp_quota as Q


# ── 1. pure tier resolution (no server) ────────────────────────────────────


def test_tier_from_token_reads_claim():
    assert A.tier_from_token({"plan": "pro"}, []) == "pro"


def test_tier_from_token_reads_scope():
    assert A.tier_from_token({}, ["dna.read", "plan:pro"]) == "pro"


def test_tier_from_token_claim_wins_over_scope():
    assert A.tier_from_token({"plan": "enterprise"}, ["plan:pro"]) == "enterprise"


def test_tier_from_token_none_when_absent():
    assert A.tier_from_token({"sub": "u1"}, ["dna.read"]) is None


def test_resolve_tier_no_token_is_default():
    assert A.resolve_tier(token_present=False, token_tier=None) == "free"
    assert A.resolve_tier(token_present=False, token_tier="pro") == "free"


def test_resolve_tier_token_no_tier_is_free_floor():
    # Authenticated but un-planned → the Free floor, NEVER denied, NEVER unlimited.
    assert A.resolve_tier(token_present=True, token_tier=None) == "free"


def test_resolve_tier_token_with_tier():
    assert A.resolve_tier(token_present=True, token_tier="pro") == "pro"


def test_resolve_tier_never_raises_custom_default():
    assert A.resolve_tier(token_present=True, token_tier=None, default="starter") == "starter"


# ── 2. pure enforcement — caps are DATA (read from a Tier spec dict) ────────


def _free_spec() -> dict:
    """A Free-tier ``spec`` — the exact shape ``kernel.tier`` returns under
    ``row['spec']`` (see test_cloud_tier_kind.py)."""
    return {
        "tier_id": "free",
        "calls_per_day": 2,
        "rate_per_sec": 100,  # high so the daily cap is what bites in quota tests
        "max_tenants": 1,
        "feature_families": ["definitions", "sdlc", "memory"],
        "memory_mode": "read",
    }


def _pro_spec() -> dict:
    return {
        "tier_id": "pro",
        "calls_per_day": 10000,
        "rate_per_sec": 100,
        "max_tenants": 50,
        "feature_families": ["definitions", "sdlc", "memory", "emit"],
        "memory_mode": "write",
    }


def _store() -> Q.InProcQuotaStore:
    return Q.InProcQuotaStore()


def test_family_not_in_tier_raises():
    # Free does not unlock the `emit` family → 403-semantics denial.
    with pytest.raises(Q.FeatureNotInPlanError, match="emit"):
        Q.enforce_quota(caps=_free_spec(), tenant="acme", tier="free",
                        family="emit", store=_store())


def test_family_in_tier_passes():
    # `memory` IS in Free's families → allowed.
    Q.enforce_quota(caps=_free_spec(), tenant="acme", tier="free",
                    family="memory", store=_store())


def test_pro_unlocks_emit_where_free_does_not():
    """SAME code, DIFFERENT data: Pro unlocks `emit`, Free does not — proving the
    gate is driven by the Tier spec, not a literal."""
    store = _store()
    # Pro: emit allowed.
    Q.enforce_quota(caps=_pro_spec(), tenant="acme", tier="pro",
                    family="emit", store=store)
    # Free: emit denied.
    with pytest.raises(Q.FeatureNotInPlanError):
        Q.enforce_quota(caps=_free_spec(), tenant="acme", tier="free",
                        family="emit", store=_store())


def test_over_calls_per_day_raises_on_cap_plus_one():
    store = _store()
    caps = _free_spec()  # calls_per_day = 2
    # calls 1 and 2 pass; the 3rd (cap + 1) is denied.
    Q.enforce_quota(caps=caps, tenant="acme", tier="free", family="memory", store=store)
    Q.enforce_quota(caps=caps, tenant="acme", tier="free", family="memory", store=store)
    with pytest.raises(Q.OverQuotaError, match="quota"):
        Q.enforce_quota(caps=caps, tenant="acme", tier="free", family="memory", store=store)


def test_over_rate_per_sec_raises():
    store = _store()
    caps = dict(_free_spec())
    caps["rate_per_sec"] = 2
    caps["calls_per_day"] = None  # isolate the rate limit
    # 2 calls in the window pass; the 3rd exceeds rate_per_sec=2.
    Q.enforce_quota(caps=caps, tenant="acme", tier="free", family="memory", store=store)
    Q.enforce_quota(caps=caps, tenant="acme", tier="free", family="memory", store=store)
    with pytest.raises(Q.OverQuotaError, match="rate"):
        Q.enforce_quota(caps=caps, tenant="acme", tier="free", family="memory", store=store)


def test_null_caps_are_unlimited():
    store = _store()
    caps = {"feature_families": [], "calls_per_day": None, "rate_per_sec": None}
    # No family list, no daily cap, no rate cap → never raises, however many calls.
    for _ in range(50):
        Q.enforce_quota(caps=caps, tenant="acme", tier="unlimited",
                        family="anything", store=store)


def test_empty_caps_enforce_nothing():
    # An unconfigured / OSS source → empty spec → no-op (never blocks).
    store = _store()
    for _ in range(10):
        Q.enforce_quota(caps={}, tenant=None, tier="free", family="emit", store=store)


def test_tenant_and_tier_meter_independently():
    """The metering key is tenant::tier — two tenants on the same tier do NOT
    share a counter."""
    store = _store()
    caps = _free_spec()  # calls_per_day = 2
    # acme uses its 2 calls.
    Q.enforce_quota(caps=caps, tenant="acme", tier="free", family="memory", store=store)
    Q.enforce_quota(caps=caps, tenant="acme", tier="free", family="memory", store=store)
    # globex still has a fresh budget.
    Q.enforce_quota(caps=caps, tenant="globex", tier="free", family="memory", store=store)
    Q.enforce_quota(caps=caps, tenant="globex", tier="free", family="memory", store=store)
    # both now exhausted.
    with pytest.raises(Q.OverQuotaError):
        Q.enforce_quota(caps=caps, tenant="acme", tier="free", family="memory", store=store)
    with pytest.raises(Q.OverQuotaError):
        Q.enforce_quota(caps=caps, tenant="globex", tier="free", family="memory", store=store)


# ── 2b. the metering key + store selection (no server, no database) ────────


def test_quota_key_round_trips():
    """Compose → decompose is the identity, including the structured tenants
    personal memory uses (``personal:google:<sub>`` carries single colons, so a
    naive split on the FIRST ':' would shred it)."""
    for tenant, tier in [
        ("acme", "free"),
        ("personal:oid-123", "pro"),
        ("personal:google:sub-9", "pro"),
        ("personal:workos:user_42", "free"),
    ]:
        assert Q.split_quota_key(Q.quota_key(tenant, tier)) == (tenant, tier)


def test_quota_key_maps_a_tenantless_call_to_the_dash_partition():
    assert Q.quota_key(None, "free") == "-::free"
    assert Q.split_quota_key("-::free") == ("-", "free")


def test_inproc_calls_on_reads_back_what_it_counted():
    """The billing read, in-process: sums a tenant's tiers, isolates tenants."""
    store = Q.InProcQuotaStore()
    store.incr_day(Q.quota_key("acme", "free"))
    store.incr_day(Q.quota_key("acme", "free"))
    store.incr_day(Q.quota_key("acme", "pro"))  # upgraded mid-day
    store.incr_day(Q.quota_key("globex", "pro"))

    assert store.calls_on("acme") == 3  # summed ACROSS tiers — the bill is per tenant
    assert store.calls_on("globex") == 1
    assert store.calls_on("nobody") == 0


def test_store_from_env_selects_in_process_without_a_postgres_dsn():
    """No DSN → the in-process store. The legitimate local / self-host default."""
    assert Q.store_from_env({}) is Q.DEFAULT_STORE
    # A non-Postgres source is not a durable store either.
    assert Q.store_from_env({"DNA_SOURCE_URL": "file:///tmp/x/.dna"}) is Q.DEFAULT_STORE
    assert Q.store_from_env({"DNA_SOURCE_URL": "sqlite:///x.db"}) is Q.DEFAULT_STORE


def test_store_from_env_selects_the_durable_store_for_a_postgres_source():
    """The hosted shape: a Postgres ``DNA_SOURCE_URL`` alone is enough — the
    counter lives in the same database its migration ran against, so DNA Cloud
    gets durable metering with no new configuration."""
    pytest.importorskip("sqlalchemy")
    for url in (
        "postgresql://u:p@h/db",
        "postgres://u:p@h/db",
        "postgresql+asyncpg://u:p@h/db",
    ):
        store = Q.store_from_env({"DNA_SOURCE_URL": url})
        assert isinstance(store, Q.PostgresQuotaStore)

    # An explicit DNA_QUOTA_DSN wins over the source URL.
    store = Q.store_from_env({
        "DNA_SOURCE_URL": "file:///tmp/x/.dna",
        "DNA_QUOTA_DSN": "postgresql://u:p@h/db",
        "DNA_QUOTA_SCHEMA": "billing",
    })
    assert isinstance(store, Q.PostgresQuotaStore)
    assert store._qualified == "billing.dna_quota_counters"


def test_sync_pg_url_swaps_the_async_driver_but_keeps_the_target():
    """asyncpg cannot back a synchronous port — the DSN is rewritten to the
    installed sync driver, host/database/query string untouched."""
    pytest.importorskip("psycopg2")
    out = Q.sync_pg_url("postgresql+asyncpg://u:p@h:5432/db?sslmode=require")
    assert out == "postgresql+psycopg2://u:p@h:5432/db?sslmode=require"
    assert Q.sync_pg_url("postgres://u@h/db") == "postgresql+psycopg2://u@h/db"
    with pytest.raises(ValueError, match="not a Postgres URL"):
        Q.sync_pg_url("sqlite:///x.db")


# ── 3. integration — over a real token context + seeded Tier docs ──────────
#
# These need fastmcp (the server + the token context) — each ``importorskip``s it,
# exactly like the other MCP suites. The pure tests above run regardless.

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_AGENT = "concierge"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"


def _tier_doc(tier_id: str, *, calls_per_day: int | None, families: list[str],
              memory_mode: str, rate_per_sec: int = 100,
              aliases: list[str] | None = None) -> dict:
    """A Tier doc — caps live HERE (the doc), never in code (mirror
    test_cloud_tier_kind.py)."""
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
            "aliases": aliases or [],
        },
    }


async def _seed_tiers(dna_dir, *, free_calls_per_day: int,
                      free_families: list[str]) -> None:
    """Seed Free + Pro Tier docs into the kernel ``_lib`` so ``kernel.tier``
    resolves them (the server boots its OWN kernel lazily against the same source,
    so writing through a fresh boot on this loop persists to disk)."""
    from dna_cli import _mcp_server as M

    live = await M.boot_live(base_dir=str(dna_dir))
    await live.kernel.write_document(
        "_lib", "Tier", "free",
        _tier_doc("free", calls_per_day=free_calls_per_day, families=free_families,
                  memory_mode="read"),
    )
    await live.kernel.write_document(
        "_lib", "Tier", "pro",
        _tier_doc("pro", calls_per_day=10000,
                  families=["definitions", "sdlc", "memory", "emit"],
                  memory_mode="write"),
    )


def _reset_store() -> None:
    """These integration tests build the server WITHOUT a ``quota_store``, and with
    no Postgres DSN in the environment ``store_from_env`` selects the in-process
    ``Q.DEFAULT_STORE`` — so reset it for a clean counter per test. A test that
    wants its own isolated counter passes ``quota_store=`` instead (see
    ``test_build_server_meters_into_an_injected_store``)."""
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


def test_free_plan_meters_over_daily_quota(dna_dir, http_server):
    """A Free-plan token (calls_per_day=2, seeded from the Tier DOC) → the 3rd
    metered tool call is denied with a ToolError naming the quota."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    asyncio.run(_seed_tiers(dna_dir, free_calls_per_day=2,
                            free_families=["definitions", "sdlc", "memory"]))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            # calls 1 + 2 succeed (within the Free daily cap of 2).
            for _ in range(2):
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE
            # call 3 (cap + 1) is denied — over quota.
            with pytest.raises(Exception) as ei:  # noqa: PT011 — ToolError/McpError
                await client.call_tool("list_stories", {"scope": _SCOPE})
            assert "quota" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))


def test_build_server_meters_into_an_injected_store(dna_dir, http_server):
    """The port is REALLY swappable: a store handed to ``build_server`` is the one
    the guard spends against.

    This is the seam the durable Postgres store slots into. Before it existed,
    ``build_server`` took no store and both ``enforce_quota`` call sites fell
    through to the module singleton, so the only way to observe metering was to
    reach into ``DEFAULT_STORE``'s private dicts — the port was a port in name
    only. Asserting on the INJECTED store (and that the singleton stayed at
    zero) is what proves otherwise."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    asyncio.run(_seed_tiers(dna_dir, free_calls_per_day=10,
                            free_families=["definitions", "sdlc", "memory"]))
    verifier, mint = _verifier_and_mint()
    mine = Q.InProcQuotaStore()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier, quota_store=mine)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for _ in range(3):
                await client.call_tool("list_stories", {"scope": _SCOPE})

    with http_server(server) as url:
        asyncio.run(go(url))

    assert mine.calls_on("acme") == 3, "the injected store was not the one metered"
    assert Q.DEFAULT_STORE.calls_on("acme") == 0, (
        "the guard still fell through to the module singleton"
    )


def test_read_only_tier_gates_write_family(dna_dir, http_server):
    """A Free tier whose feature_families OMIT `memory` → a `remember` (memory
    family) call is denied by the feature gate, while `list_stories` (sdlc) still
    works. Proves per-family gating off the Tier doc."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    # Free unlocks only definitions + sdlc — memory is NOT in the plan.
    asyncio.run(_seed_tiers(dna_dir, free_calls_per_day=1000,
                            free_families=["definitions", "sdlc"]))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            # sdlc family is unlocked → passes.
            res = await client.call_tool("list_stories", {"scope": _SCOPE})
            assert res.structured_content["scope"] == _SCOPE
            # memory family is NOT in the plan → denied by the feature gate.
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool(
                    "remember", {"summary": "should be gated", "scope": _SCOPE})
            msg = str(ei.value).lower()
            assert "memory" in msg or "family" in msg

    with http_server(server) as url:
        asyncio.run(go(url))


def test_unauthenticated_server_meters_nothing(dna_dir):
    """The CRITICAL invariant: with NO auth (auth=None, stdio/local) the guard is an
    identity — NOTHING is metered, so calls sail PAST any cap. Even a Free doc with
    calls_per_day=1 does not bite an unauthenticated server."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    asyncio.run(_seed_tiers(dna_dir, free_calls_per_day=1,
                            free_families=["definitions"]))  # very tight caps
    server = M.build_server(base_dir=str(dna_dir))  # auth=None → unauthenticated

    async def go():
        async with Client(server) as client:
            # Far more calls than ANY cap — none are metered (no token present).
            for _ in range(5):
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE
            # a memory-family call also passes though Free omits `memory` — the
            # gate never runs without a token.
            out = await client.call_tool(
                "remember", {"summary": "unmetered local write", "scope": _SCOPE})
            assert out.structured_content["kind"] == "Engram"

    asyncio.run(go())
