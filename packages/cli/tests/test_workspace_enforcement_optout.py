"""Issue ``i-074`` / story ``s-workspace-enforcement-opt-out`` — the GLUE half of
the workspace-enforcement switch, on both doors.

The pure policy (mode reading, the boot line, the metering key) is proven in
``sdk-py/tests/test_workspace_enforcement.py``. Here we prove the WIRING:

* **default = enforce** — every one of the three membership denials still fires
  when the knob is unset. This is the assertion the whole feature rests on: a
  regression here silently opens a multi-tenant deployment.
* **open** — those same three denials become a fall-through to the *unverified*
  selector, on the MCP bridge and on the REST middleware alike.
* **still enforced** — token verification, the contradictory-selector refusal,
  and metering. The end-to-end cases prove metering keeps biting AND that two
  membership-less identities never share a budget.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna.tenancy import WORKSPACE_ENFORCEMENT_ENV, OPEN
from dna_cli import _mcp_auth as A


# ── fakes (same shape as test_workspace_glue.py) ───────────────────────────


class _FakeKernel:
    def __init__(self, grants):
        self._grants = grants

    async def workspace_memberships(self):
        return self._grants


class _FakeLive:
    def __init__(self, grants):
        self.kernel = _FakeKernel(grants)


def _run(coro):
    return asyncio.run(coro)


def _grant(ws: str, email: str, oid: str, status: str = "active") -> dict:
    return {"spec": {"workspace_id": ws, "identity_email": email,
                     "identity_oid": oid, "role": "owner", "status": status}}


_ALICE = {"oid": "oid-alice", "email": "alice@a.com", "tid": "org-a"}
_CAROL = {"oid": "oid-carol", "email": "carol@nowhere.com"}

#: alice is a member of ws-a; nobody else is a member of anything.
_GRANTS_ONE = [_grant("ws-a", "alice@a.com", "oid-alice")]
#: alice belongs to TWO workspaces — the "named none" ambiguity.
_GRANTS_TWO = [_grant("ws-a", "alice@a.com", "oid-alice"),
               _grant("ws-b", "alice@a.com", "oid-alice")]


@pytest.fixture
def as_identity(monkeypatch):
    """Stub the live token so the bridge sees a synthetic verified identity."""
    def _install(claims: dict):
        from dna.tenancy.resolution import identity_from_token

        monkeypatch.setattr(A, "token_present_in_context", lambda: True)
        monkeypatch.setattr(A, "identity_from_context",
                            lambda: identity_from_token(claims))
        monkeypatch.setattr(A, "workspace_selector_from_context", lambda: None)
    return _install


@pytest.fixture
def enforcement_open(monkeypatch):
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)


@pytest.fixture(autouse=True)
def _default_is_unset(monkeypatch):
    """Every test starts from the shipped default — no knob at all."""
    monkeypatch.delenv(WORKSPACE_ENFORCEMENT_ENV, raising=False)


# ── 1. DEFAULT: all three denial paths still fire (the load-bearing test) ───


def test_default_denies_no_membership(as_identity):
    from dna.tenancy import CrossWorkspaceError

    as_identity(_CAROL)
    with pytest.raises(CrossWorkspaceError, match="no active workspace membership"):
        _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_ONE), None))


def test_default_denies_a_workspace_the_identity_is_not_in(as_identity):
    from dna.tenancy import CrossWorkspaceError

    as_identity(_ALICE)
    with pytest.raises(CrossWorkspaceError, match="not an active member"):
        _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_ONE), "ws-b"))


def test_default_denies_ambiguous_multi_membership(as_identity):
    from dna.tenancy import CrossWorkspaceError

    as_identity(_ALICE)
    with pytest.raises(CrossWorkspaceError, match="named none"):
        _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_TWO), None))


@pytest.mark.parametrize("raw", ["", "0", "false", "off", "opem", "true", "1"])
def test_a_falsey_or_misspelt_value_still_denies(as_identity, monkeypatch, raw):
    """The knob is not a boolean — no spelling but ``open`` opens anything."""
    from dna.tenancy import CrossWorkspaceError

    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, raw)
    as_identity(_CAROL)
    with pytest.raises(CrossWorkspaceError):
        _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_ONE), None))


# ── 2. OPEN: the same three denials fall through instead ────────────────────


def test_open_serves_an_identity_with_no_membership(as_identity, enforcement_open):
    as_identity(_CAROL)
    assert _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_ONE), None)) is None


def test_open_takes_a_named_selector_at_face_value(as_identity, enforcement_open):
    as_identity(_CAROL)
    got = _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_ONE), "ws-a"))
    assert got == "ws-a"


def test_open_neutralizes_the_not_a_member_denial(as_identity, enforcement_open):
    as_identity(_ALICE)
    assert _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_ONE), "ws-b")) == "ws-b"


def test_open_neutralizes_the_ambiguous_denial(as_identity, enforcement_open):
    as_identity(_ALICE)
    assert _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_TWO), None)) is None


def test_open_still_resolves_a_real_membership(as_identity, enforcement_open):
    """Only the DENIAL is disarmed — resolution still runs, so an identity that
    unambiguously belongs somewhere keeps its workspace (and therefore its
    account's plan). Nothing has to be flipped back when memberships appear."""
    as_identity(_ALICE)
    assert _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_ONE), None)) == "ws-a"


def test_open_leaves_the_no_grants_legacy_path_alone(as_identity, enforcement_open,
                                                     monkeypatch):
    """A source with NO grants never reached the membership boundary in the first
    place — the knob must not change that branch."""
    as_identity(_ALICE)
    monkeypatch.setattr(A, "enforce_tenant_from_context", lambda r: "legacy-tenant")
    assert _run(A.enforce_workspace_from_context(_FakeLive([]), "req")) == "legacy-tenant"


def test_open_still_refuses_contradictory_selectors(monkeypatch, enforcement_open):
    """Not a membership decision: the URL path and the tool arg name DIFFERENT
    workspaces. Refusing to guess stays right with the boundary open."""
    from dna.tenancy.resolution import identity_from_token

    monkeypatch.setattr(A, "token_present_in_context", lambda: True)
    monkeypatch.setattr(A, "identity_from_context", lambda: identity_from_token(_ALICE))
    monkeypatch.setattr(A, "workspace_selector_from_context", lambda: "ws-path")
    with pytest.raises(A.CrossTenantError, match="conflicting workspace selectors"):
        _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_ONE), "ws-arg"))


def test_open_never_touches_the_unauthenticated_path(monkeypatch, enforcement_open):
    monkeypatch.setattr(A, "token_present_in_context", lambda: False)
    assert _run(A.enforce_workspace_from_context(_FakeLive(_GRANTS_ONE), "x")) == "x"


# ── 3. metering — the whole point of "só registra os chamados" ──────────────


def test_metering_key_from_context_reads_the_live_token(monkeypatch):
    from dna.tenancy import unenforced_metering_key

    class _Tok:
        claims = dict(_CAROL)

    import fastmcp.server.dependencies as deps
    monkeypatch.setattr(deps, "get_access_token", lambda: _Tok())
    assert A.unenforced_metering_key_from_context() == unenforced_metering_key(_CAROL)


def test_metering_key_from_context_refuses_a_subjectless_token(monkeypatch):
    from dna.tenancy import UnmeterableIdentityError

    class _Tok:
        claims = {"email": "ghost@x.com"}

    import fastmcp.server.dependencies as deps
    monkeypatch.setattr(deps, "get_access_token", lambda: _Tok())
    with pytest.raises(UnmeterableIdentityError):
        A.unenforced_metering_key_from_context()


# ── 4. end-to-end over the real MCP door (the operator's actual scenario) ───

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the 'fastmcp' extra")

from dna_cli import _mcp_quota as Q  # noqa: E402
from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_EXAMPLE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_AGENT = "concierge"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_EXAMPLE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    Q.DEFAULT_STORE.reset()
    return dst


def _seed(dna_dir, *, calls_per_day: int | None = None):
    """One ACTIVE grant (so Model B is engaged at all) and, optionally, a Free
    PricingPlan with a tight daily cap so metering is OBSERVABLE."""
    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        await live.kernel.write_instance(
            "_lib", "WorkspaceMembership", "ws-a--alice-at-a-com",
            {
                "apiVersion": "github.com/ruinosus/dna/tenant/v1",
                "kind": "WorkspaceMembership",
                "metadata": {"name": "ws-a--alice-at-a-com"},
                "spec": {"workspace_id": "ws-a", "identity_email": "alice@a.com",
                         "identity_oid": "oid-alice", "role": "owner",
                         "status": "active"},
            },
        )
        if calls_per_day is not None:
            await live.kernel.write_instance(
                "_lib", "PricingPlan", "free",
                {
                    "apiVersion": "github.com/ruinosus/dna/cloud/v1",
                    "kind": "PricingPlan",
                    "metadata": {"name": "free"},
                    "spec": {"tier_id": "free", "display_name": "Free",
                             "price_usd_month": 0,
                             "calls_per_day": calls_per_day, "rate_per_sec": 100,
                             "max_tenants": 1,
                             "feature_families": ["definitions", "sdlc", "memory"],
                             "memory_mode": "read", "aliases": []},
                },
            )
    asyncio.run(go())


def _verifier_and_mint():
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER, audience=_AUDIENCE)

    def mint(oid: str, email: str):
        return kp.create_token(
            issuer=_ISSUER, audience=_AUDIENCE, subject=oid, scopes=["dna.read"],
            additional_claims={"oid": oid, "email": email, "tid": "org-a"},
        )
    return verifier, mint


async def _list_agents(url, token):
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    async with Client(url, auth=BearerAuth(token)) as client:
        res = await client.call_tool("list_agents", {})
        return res.structured_content


def test_e2e_default_denies_the_operator(dna_dir, http_server, monkeypatch):
    """Today's behaviour, restated end-to-end: the sole operator, with no grant
    of their own, gets nothing."""
    _seed(dna_dir)
    verifier, mint = _verifier_and_mint()
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", "ws-a")
    server = M.build_server(base_dir=str(dna_dir), scope=_SCOPE, auth=verifier)
    with http_server(server) as url:
        with pytest.raises(Exception) as ei:  # noqa: PT011
            asyncio.run(_list_agents(url, mint("oid-carol", "carol@nowhere.com")))
        assert "no active workspace membership" in str(ei.value).lower()


def test_e2e_open_serves_the_operator(dna_dir, http_server, monkeypatch):
    """The whole point: with the boundary open, the membership-less operator
    reaches the registry."""
    _seed(dna_dir)
    verifier, mint = _verifier_and_mint()
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", "ws-a")
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    server = M.build_server(base_dir=str(dna_dir), scope=_SCOPE, auth=verifier)
    with http_server(server) as url:
        out = asyncio.run(_list_agents(url, mint("oid-carol", "carol@nowhere.com")))
        assert _AGENT in [a["name"] for a in out["agents"]]


def test_e2e_open_still_meters_every_call_per_identity(
    dna_dir, http_server, monkeypatch
):
    """"Só registra os chamados" — proven by the cap biting, and proven to be
    keyed on the IDENTITY by a second membership-less caller still having their
    own budget after the first is exhausted."""
    _seed(dna_dir, calls_per_day=1)
    verifier, mint = _verifier_and_mint()
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", "ws-a")
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    server = M.build_server(base_dir=str(dna_dir), scope=_SCOPE, auth=verifier)
    carol = mint("oid-carol", "carol@nowhere.com")
    dave = mint("oid-dave", "dave@nowhere.com")
    with http_server(server) as url:
        asyncio.run(_list_agents(url, carol))          # 1st — counted.
        with pytest.raises(Exception) as ei:           # noqa: PT011 — 2nd — capped.
            asyncio.run(_list_agents(url, carol))
        assert "quota" in str(ei.value).lower()
        # dave's budget is untouched — the meter never pooled the two.
        asyncio.run(_list_agents(url, dave))


def test_e2e_open_still_denies_a_subjectless_token(dna_dir, http_server, monkeypatch):
    """An authenticated token with no durable subject cannot be attributed, so it
    stays denied even with the boundary open — never a shared meter."""
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    _seed(dna_dir)
    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER, audience=_AUDIENCE)
    ghost = kp.create_token(issuer=_ISSUER, audience=_AUDIENCE, subject="ghost",
                            scopes=["dna.read"],
                            additional_claims={"email": "ghost@x.com"})
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", "ws-a")
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    server = M.build_server(base_dir=str(dna_dir), scope=_SCOPE, auth=verifier)
    with http_server(server) as url:
        with pytest.raises(Exception) as ei:  # noqa: PT011
            asyncio.run(_list_agents(url, ghost))
        assert "attributed" in str(ei.value).lower()


def test_e2e_open_still_rejects_an_unverified_token(dna_dir, http_server, monkeypatch):
    """The opt-out is about the workspace boundary, NOT about authentication."""
    import httpx

    _seed(dna_dir)
    verifier, _ = _verifier_and_mint()
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", "ws-a")
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    server = M.build_server(base_dir=str(dna_dir), scope=_SCOPE, auth=verifier)
    with http_server(server) as url:
        r = httpx.post(url, headers={"Authorization": "Bearer forged",
                                     "Accept": "application/json, text/event-stream"},
                       json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert r.status_code == 401


# ── 5. the boot announcement ────────────────────────────────────────────────


def test_building_a_door_announces_the_open_boundary(dna_dir, monkeypatch, caplog):
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    with caplog.at_level("WARNING"):
        M.build_server(base_dir=str(dna_dir), scope=_SCOPE)
    assert any(WORKSPACE_ENFORCEMENT_ENV in r.message for r in caplog.records)


def test_building_a_door_is_quiet_by_default(dna_dir, caplog):
    with caplog.at_level("WARNING"):
        M.build_server(base_dir=str(dna_dir), scope=_SCOPE)
    assert not any(WORKSPACE_ENFORCEMENT_ENV in r.message for r in caplog.records)


# ── 6. the REST face shares the seam ────────────────────────────────────────

pytest.importorskip("fastapi", reason="the REST read-API needs the 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402


class _FakeAccess:
    def __init__(self, claims):
        self.claims = claims


class _FakeVerifier:
    def __init__(self, table):
        self._table = table

    async def verify_token(self, token):
        claims = self._table.get(token)
        return _FakeAccess(claims) if claims is not None else None


def _rest_client(dna_dir) -> TestClient:
    return TestClient(R.build_app(
        base_dir=str(dna_dir), scope=_SCOPE, auth="config",
        verifier=_FakeVerifier({"alice": _ALICE, "carol": _CAROL,
                                "ghost": {"email": "ghost@x.com"}}),
    ))


def _get_agents(c, token):
    return c.get("/v1/agents", params={"scope": _SCOPE},
                 headers={"Authorization": f"Bearer {token}"})


def test_rest_default_denies_no_membership(dna_dir):
    _seed(dna_dir)
    assert _get_agents(_rest_client(dna_dir), "carol").status_code == 403


def test_rest_open_serves_no_membership(dna_dir, monkeypatch):
    _seed(dna_dir)
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    r = _get_agents(_rest_client(dna_dir), "carol")
    assert r.status_code == 200, r.text
    assert _AGENT in [a["name"] for a in r.json()["agents"]]


def test_rest_open_still_denies_a_subjectless_token(dna_dir, monkeypatch):
    _seed(dna_dir)
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    assert _get_agents(_rest_client(dna_dir), "ghost").status_code == 403


def test_rest_open_still_rejects_an_unverified_token(dna_dir, monkeypatch):
    _seed(dna_dir)
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    assert _get_agents(_rest_client(dna_dir), "forged").status_code == 401


def test_rest_open_still_resolves_a_real_membership(dna_dir, monkeypatch):
    _seed(dna_dir)
    monkeypatch.setenv(WORKSPACE_ENFORCEMENT_ENV, OPEN)
    assert _get_agents(_rest_client(dna_dir), "alice").status_code == 200
