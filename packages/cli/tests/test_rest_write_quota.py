"""i-042 — plan gates on the REST **write path** (`dna api serve`).

Before this, the REST face had ZERO metering: the axes the Pro plan sells
(``memory_mode`` write, ``calls_per_day``) were enforced only on the MCP
channel — a Free workspace writing through the web surface was never gated.
The fix is NOT a second policy: the REST write routes call the SAME shared
core (``dna_cli._mcp_quota.enforce_plan``) the MCP ``_guard`` runs.

Property set (each pins one clause of the contract):

* **auth=none is NEVER gated** — the OSS/self-host hard rule, even with
  restrictive Tier docs seeded (the anti-vacuity baseline: the same seed DOES
  deny under token auth, so passing here is a real exemption, not absence of
  enforcement).
* **Free blocked on write / Pro allowed** — under BOTH relevant auth modes
  (``token``: the portal's trusted service bearer + `tenant` param; ``config``:
  verified JWT). Tier resolution is claim → workspace → account → AccountPlan
  → Free floor (the plan is keyed on the BILLING ACCOUNT — two hops), and an
  explicit plan claim WINS over the store (MCP parity).
* **calls_per_day counts REST writes and refuses above the cap** — and the
  denied call is NOT counted (i-050 inherited through the shared core).
* **REST reads do NOT consume quota** — the deliberate channel divergence
  (a dashboard render fans into several GETs; navigation must not burn the
  customer's cap). Writes still meter after any number of reads.
* **personal import is gated per-identity** — the REST twin of the MCP
  ``_personal_guard``: metered on the ``personal:<oid>`` partition, tier from
  the verified token's plan claim, a read-only tier's import refused with
  NOTHING written.
* **one shared core** — the parity guard: monkeypatching
  ``dna_cli._mcp_quota.enforce_plan`` with a sentinel re-routes BOTH faces,
  so a duplicated/diverging copy of the policy in either face dies here.
* **DNA_QUOTA_REQUIRE_TIERS fail-closed reaches REST** (i-051) — an empty Tier
  registry refuses the metered write (503) instead of serving it uncapped,
  while auth=none stays structurally out of the flag's reach.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _mcp_quota as Q  # noqa: E402
from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_TOKEN = "portal-shared-token-mvp"  # a fake shared token, NOT a real secret.
_WS = "acme"  # the workspace the portal vouches via ?tenant=
_ACCT = "entra-org:acct-acme"  # the BILLING ACCOUNT that owns _WS

_ALICE = {"oid": "oid-alice", "email": "alice@a.com"}


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope, wired via DNA_BASE_DIR, with the
    metering env fully neutral (no DSN, no fail-closed flag, no plan claims)."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_QUOTA_DSN", raising=False)
    monkeypatch.delenv(Q.REQUIRE_TIERS_ENV, raising=False)
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    return dst


# ── seeding (docs are the source of truth — caps NEVER live in test logic) ──


def _tier_doc(tier_id: str, *, memory_mode: str, calls_per_day: int | None = 1000,
              rate_per_sec: int = 1000) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "PricingPlan",
        "metadata": {"name": tier_id},
        "spec": {
            "tier_id": tier_id,
            "display_name": tier_id.title(),
            "price_usd_month": 0,
            "calls_per_day": calls_per_day,
            "rate_per_sec": rate_per_sec,
            "max_tenants": 1,
            "feature_families": ["definitions", "sdlc", "memory"],
            "memory_mode": memory_mode,
            "aliases": [],
        },
    }


def _plan_docs(workspace_id: str, account_id: str, tier_id: str) -> list[tuple[str, str, dict]]:
    """The TWO docs the account-keyed bridge reads: the ``Workspace`` naming its
    billing account (hop 1) and the ``AccountPlan`` assigning that account a
    tier (hop 2). Replaces the retired per-workspace WorkspacePlan seed."""
    return [
        ("Workspace", workspace_id, {
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
        }),
        ("PlanBinding", account_id, {
            "apiVersion": "github.com/ruinosus/dna/cloud/v1",
            "kind": "PlanBinding",
            "metadata": {"name": account_id},
            "spec": {"account_id": account_id, "tier_id": tier_id,
                     "source": "stripe", "status": "active"},
        }),
    ]


def _seed(dna_dir, *docs: tuple[str, str, dict]) -> None:
    """Write ``(kind, name, doc)`` rows into ``_lib`` on a fresh loop; the
    filesystem source persists, so the app under test reads them back."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        for kind, name, doc in docs:
            await live.kernel.write_document("_lib", kind, name, doc)

    asyncio.run(go())


def _seed_tiers(dna_dir, *, free_cpd: int | None = 1000,
                pro_cpd: int | None = 1000) -> None:
    """The canonical product shape: Free = memory READ-only, Pro = write."""
    _seed(
        dna_dir,
        ("PricingPlan", "free", _tier_doc("free", memory_mode="read", calls_per_day=free_cpd)),
        ("PricingPlan", "pro", _tier_doc("pro", memory_mode="write", calls_per_day=pro_cpd)),
    )


def _seed_memory(dna_dir, summary: str, *, tenant: str | None) -> dict:
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.remember_impl(live, summary, scope=_SCOPE, tenant=tenant)

    return asyncio.run(go())


# ── clients ─────────────────────────────────────────────────────────────────


def _token_client(dna_dir, store) -> TestClient:
    return TestClient(R.build_app(
        base_dir=str(dna_dir), scope=_SCOPE, auth="token", token=_TOKEN,
        quota_store=store,
    ))


class _FakeAccess:
    def __init__(self, claims):
        self.claims = claims


class _FakeVerifier:
    """Bearer string → claims table; unknown token → None (→ 401)."""

    def __init__(self, table):
        self._table = table

    async def verify_token(self, token):
        claims = self._table.get(token)
        return _FakeAccess(claims) if claims is not None else None


def _config_client(dna_dir, store, table) -> TestClient:
    return TestClient(R.build_app(
        base_dir=str(dna_dir), scope=_SCOPE, auth="config",
        verifier=_FakeVerifier(table), quota_store=store,
    ))


def _auth(token=_TOKEN):
    return {"Authorization": f"Bearer {token}"}


def _post_memory(c, *, tenant=_WS, headers=None, summary="quota probe memory"):
    params = {"scope": _SCOPE}
    if tenant is not None:
        params["tenant"] = tenant
    return c.post("/v1/memories", params=params,
                  json={"summary": summary}, headers=headers or {})


# ── auth=none: the OSS/self-host path is structurally exempt ────────────────


def test_auth_none_write_never_gated_even_with_restrictive_tiers(dna_dir):
    """The anti-vacuity baseline: the SAME Tier seed that denies a Free write
    under token auth (test below) does nothing under ``--auth none`` — the gate
    is exempted by auth mode, not passing by accident of an empty registry."""
    _seed_tiers(dna_dir)  # free = read-only: would 403 a metered caller.
    store = Q.InProcQuotaStore()
    with TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE,
                                quota_store=store)) as c:
        r = _post_memory(c)
        assert r.status_code == 201, r.text
        # And nothing was metered: the local write is invisible to any counter.
        assert store.calls_on(_WS) == 0


def test_auth_none_untouched_by_require_tiers_flag(dna_dir, monkeypatch):
    """i-051's fail-closed flag can never leak enforcement into the local path."""
    monkeypatch.setenv(Q.REQUIRE_TIERS_ENV, "1")  # no Tier docs seeded at all.
    with TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE,
                                quota_store=Q.InProcQuotaStore())) as c:
        assert _post_memory(c).status_code == 201


# ── auth=token (the portal's trusted service bearer + vouched tenant) ───────


def test_token_free_write_blocked_and_denial_costs_nothing(dna_dir):
    """No account / no AccountPlan → the Free floor → memory_mode='read' → the
    write is 403 and the denied call never reaches the billed counter (i-050)."""
    _seed_tiers(dna_dir)
    store = Q.InProcQuotaStore()
    with _token_client(dna_dir, store) as c:
        r = _post_memory(c, headers=_auth())
        assert r.status_code == 403, r.text
        assert "memory_mode" in r.json()["detail"]
        assert store.calls_on(_WS) == 0
        # The refused write really wrote nothing.
        r = c.get("/v1/memories", params={"scope": _SCOPE, "tenant": _WS},
                  headers=_auth())
        assert all("quota probe" not in (m["summary"] or "")
                   for m in r.json()["memories"])


def test_token_pro_write_allowed_and_counted(dna_dir):
    """AccountPlan(acct→pro) — the Stripe-written bridge, resolved through the
    workspace's ``account_id`` — unlocks the write, and the successful write is
    still metered against the WORKSPACE (usage attribution is unchanged)."""
    _seed_tiers(dna_dir)
    _seed(dna_dir, *_plan_docs(_WS, _ACCT, "pro"))
    store = Q.InProcQuotaStore()
    with _token_client(dna_dir, store) as c:
        r = _post_memory(c, headers=_auth())
        assert r.status_code == 201, r.text
        assert store.calls_on(_WS) == 1


def test_token_delete_is_a_gated_write(dna_dir):
    """DELETE is the write face of the memory surface (the MCP twin is
    ``forget``): Free-blocked with the doc intact, Pro-allowed."""
    _seed_tiers(dna_dir)
    seeded = _seed_memory(dna_dir, "victim memory for delete gate", tenant=_WS)
    name = seeded["name"]
    store = Q.InProcQuotaStore()
    with _token_client(dna_dir, store) as c:
        r = c.delete(f"/v1/memories/{name}",
                     params={"scope": _SCOPE, "tenant": _WS}, headers=_auth())
        assert r.status_code == 403
        # The memory survived the refused delete.
        r = c.get("/v1/memories", params={"scope": _SCOPE, "tenant": _WS},
                  headers=_auth())
        assert name in [m["name"] for m in r.json()["memories"]]
    _seed(dna_dir, *_plan_docs(_WS, _ACCT, "pro"))
    with _token_client(dna_dir, store) as c:
        r = c.delete(f"/v1/memories/{name}",
                     params={"scope": _SCOPE, "tenant": _WS}, headers=_auth())
        assert r.status_code == 200, r.text


def test_daily_cap_counts_writes_and_refuses_above_without_counting(dna_dir):
    """calls_per_day bites the REST write path: cap=2 admits exactly two
    writes; the third is 429 and — i-050, inherited through the shared core —
    the denial is NOT counted, twice over."""
    _seed_tiers(dna_dir, pro_cpd=2)
    _seed(dna_dir, *_plan_docs(_WS, _ACCT, "pro"))
    store = Q.InProcQuotaStore()
    with _token_client(dna_dir, store) as c:
        assert _post_memory(c, headers=_auth(), summary="first write ok").status_code == 201
        assert _post_memory(c, headers=_auth(), summary="second write ok").status_code == 201
        r = _post_memory(c, headers=_auth(), summary="third over the cap")
        assert r.status_code == 429
        assert "quota" in r.json()["detail"]
        assert store.calls_on(_WS) == 2  # the denied call is invisible.
        assert _post_memory(c, headers=_auth(), summary="fourth too").status_code == 429
        assert store.calls_on(_WS) == 2


def test_reads_do_not_consume_quota(dna_dir):
    """The channel decision: REST READS are not metered (a dashboard render
    fans into several GETs — navigation must never burn the customer's cap),
    while writes still meter after any number of reads."""
    _seed_tiers(dna_dir, pro_cpd=2)
    _seed(dna_dir, *_plan_docs(_WS, _ACCT, "pro"))
    store = Q.InProcQuotaStore()
    with _token_client(dna_dir, store) as c:
        for _ in range(5):  # far past the cap of 2, if reads counted.
            assert c.get("/v1/memories", params={"scope": _SCOPE, "tenant": _WS},
                         headers=_auth()).status_code == 200
            assert c.get("/v1/memories/search",
                         params={"scope": _SCOPE, "tenant": _WS, "q": "probe"},
                         headers=_auth()).status_code == 200
        assert store.calls_on(_WS) == 0
        # The full write budget is still available.
        assert _post_memory(c, headers=_auth()).status_code == 201
        assert store.calls_on(_WS) == 1


# ── auth=config (verified JWT; legacy tenant passthrough — no workspaces) ───


def test_config_free_blocked_then_account_plan_unlocks(dna_dir):
    """Same property under the verified-identity mode: no plan → Free floor →
    403; the Stripe-written AccountPlan (reached through the workspace's
    account) flips the SAME request to 201."""
    _seed_tiers(dna_dir)
    store = Q.InProcQuotaStore()
    table = {"alice": _ALICE}
    with _config_client(dna_dir, store, table) as c:
        assert _post_memory(c, headers=_auth("alice")).status_code == 403
    _seed(dna_dir, *_plan_docs(_WS, _ACCT, "pro"))
    with _config_client(dna_dir, store, table) as c:
        assert _post_memory(c, headers=_auth("alice")).status_code == 201, \
            "AccountPlan(acct→pro) must unlock the config-auth write"


def test_config_explicit_plan_claim_wins_over_store(dna_dir):
    """MCP parity, pinned on REST: a token that CARRIES a plan claim is metered
    on that claim — the AccountPlan store is not consulted (same order:
    claim → store → Free floor)."""
    _seed_tiers(dna_dir)
    _seed(dna_dir, *_plan_docs(_WS, _ACCT, "pro"))  # store says pro…
    store = Q.InProcQuotaStore()
    table = {"bob": {"oid": "oid-bob", "email": "bob@b.com", "plan": "free"}}
    with _config_client(dna_dir, store, table) as c:
        r = _post_memory(c, headers=_auth("bob"))
        assert r.status_code == 403  # …but the explicit free claim wins.
        assert "memory_mode" in r.json()["detail"]


def test_config_import_personal_gated_per_identity(dna_dir):
    """The REST twin of the MCP ``_personal_guard``: a personal import is a
    memory WRITE metered on the identity partition. A claim-less token sits on
    the Free floor (read-only ⇒ 403, NOTHING written); a ``plan: pro`` claim
    unlocks it and the usage lands on ``personal:<oid>``, not a workspace."""
    _seed_tiers(dna_dir)
    store = Q.InProcQuotaStore()
    table = {
        "alice": _ALICE,  # no plan claim → Free floor.
        "carol": {"oid": "oid-carol", "email": "carol@c.com", "plan": "pro"},
    }
    bundle = {"@graph": [{
        "id": "mif-1", "type": "semantic", "content": "imported fact",
        "created": "2026-07-19T10:00:00Z", "title": "t",
    }]}
    with _config_client(dna_dir, store, table) as c:
        r = c.post("/v1/memories/import", params={"scope": _SCOPE},
                   json={"bundle": bundle}, headers=_auth("alice"))
        assert r.status_code == 403, r.text
        assert store.calls_on("personal:oid-alice") == 0
        r = c.post("/v1/memories/import", params={"scope": _SCOPE},
                   json={"bundle": bundle}, headers=_auth("carol"))
        assert r.status_code == 201, r.text
        assert r.json()["imported"] == 1
        assert store.calls_on("personal:oid-carol") == 1
        assert store.calls_on(_WS) == 0  # never attributed to a workspace.


# ── the parity guard: ONE shared core, not two policies ─────────────────────


def test_both_faces_route_through_the_shared_policy_core(dna_dir, monkeypatch, http_server):
    """Monkeypatching the ONE shared symbol (``_mcp_quota.enforce_plan``) with
    a sentinel re-routes BOTH faces. If either face grew its own copy of the
    policy (the divergence i-042 exists to prevent), its half of this test
    dies — the sentinel would never fire there."""
    sentinel = "SENTINEL-PARITY-i042"
    calls: list[str] = []

    async def fake_enforce_plan(kernel, **kwargs):
        calls.append(kwargs["family"])
        raise Q.OverQuotaError(sentinel)

    monkeypatch.setattr(Q, "enforce_plan", fake_enforce_plan)

    # REST face: the gate must surface the sentinel as its 429.
    with _token_client(dna_dir, Q.InProcQuotaStore()) as c:
        r = _post_memory(c, headers=_auth())
        assert r.status_code == 429
        assert sentinel in r.json()["detail"]

    # MCP face: the guard must surface the SAME sentinel as a tool error.
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    from dna_cli import _mcp_server as M

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer="https://dna.test/",
                           audience="dna-mcp")
    token = kp.create_token(issuer="https://dna.test/", audience="dna-mcp",
                            subject="u1", scopes=["dna.read"],
                            additional_claims={"tenant": _WS})
    server = M.build_server(base_dir=str(dna_dir), auth=verifier,
                            quota_store=Q.InProcQuotaStore())

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            with pytest.raises(Exception, match=sentinel):
                await client.call_tool("list_stories", {"scope": _SCOPE})

    with http_server(server) as url:
        asyncio.run(go(url))

    assert calls == ["memory", "sdlc"]  # one hit per face, zero copies.


# ── i-051 on REST: fail-closed reaches the metered write ────────────────────


def test_require_tiers_refuses_metered_rest_write(dna_dir, monkeypatch):
    """DNA_QUOTA_REQUIRE_TIERS=1 with NO Tier docs: the metered REST write is
    refused (503 — deployment broken, not a plan denial) instead of served
    uncapped. The flag OFF serves it (empty registry = OSS = enforce nothing)."""
    store = Q.InProcQuotaStore()
    monkeypatch.setenv(Q.REQUIRE_TIERS_ENV, "1")
    with _token_client(dna_dir, store) as c:
        r = _post_memory(c, headers=_auth())
        assert r.status_code == 503
        assert "tier registry" in r.json()["detail"]
    monkeypatch.delenv(Q.REQUIRE_TIERS_ENV)
    with _token_client(dna_dir, store) as c:
        assert _post_memory(c, headers=_auth()).status_code == 201
