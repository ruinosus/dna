"""Story ``s-ws-invite-rest`` + ``s-ws-res-rest-config`` — the workspace-invite
REST surface and the Model B ``--auth config`` token→identity→workspace binding.

Drives the real FastAPI app in-process via ``TestClient`` against the committed
concierge example (copied to tmp so GLOBAL ``_lib`` WorkspaceMembership docs can be
written).

Proven here:
* ``POST /v1/workspaces/{id}/invites`` creates a pending grant; RBAC 403s a
  non-Owner; ``GET .../members`` lists (Owner/Admin only); ``POST
  /v1/workspaces/accept`` binds a verified invitee.
* ``--auth config`` binds the workspace from membership: 401 (no/bad token), the
  ``tenant`` query param is OVERWRITTEN with the identity's workspace, a forged
  cross-workspace ``tenant`` is 403, and the ``accept`` route is EXEMPT from the
  membership bind (a still-pending invitee can reach it).
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402
from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WS = "ws-partner"
_PARTNER_EMAIL = "partner@partner-org.com"
_OWNER = {"oid": "oid-alice", "email": "alice@a.com", "tid": "org-a"}


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _seed_grant(dna_dir, ws, email, oid, role, status="active"):
    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        name = f"{ws}--{email.replace('@', '-at-').replace('.', '-')}"
        await live.kernel.write_document(
            "_lib", "WorkspaceMembership", name,
            {"apiVersion": "github.com/ruinosus/dna/tenant/v1", "kind": "WorkspaceMembership",
             "metadata": {"name": name},
             "spec": {"workspace_id": ws, "identity_email": email, "identity_oid": oid,
                      "identity_tid": "org-x", "role": role, "status": status}},
        )
    asyncio.run(go())


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


# ── s-ws-invite-rest: the endpoints under --auth none (trusted portal) ──────


def test_invite_list_accept_flow(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _client(dna_dir) as c:
        # Owner invites the partner (actor claims passed by the trusted portal).
        r = c.post(f"/v1/workspaces/{_WS}/invites",
                   json={"email": _PARTNER_EMAIL, "role": "member", "actor": _OWNER})
        assert r.status_code == 201, r.text
        assert r.json()["invite"]["status"] == "pending"

        # Owner lists members.
        r = c.get(f"/v1/workspaces/{_WS}/members",
                  params={"actor_oid": "oid-alice", "actor_email": "alice@a.com"})
        assert r.status_code == 200
        rows = {m["identity_email"]: m for m in r.json()["members"]}
        assert rows[_PARTNER_EMAIL]["status"] == "pending"

        # The partner accepts (verified email claims).
        r = c.post("/v1/workspaces/accept",
                   json={"claims": {"oid": "oid-partner", "email": _PARTNER_EMAIL,
                                    "email_verified": True, "tid": "org-partner"}})
        assert r.status_code == 200
        assert r.json()["accepted"] == [
            {"workspace_id": _WS, "role": "member", "activated": True}
        ]


def test_invite_non_owner_forbidden(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/invites",
                   json={"email": _PARTNER_EMAIL, "role": "member",
                         "actor": {"oid": "oid-nobody", "email": "nobody@x.com"}})
        assert r.status_code == 403


def test_invite_unknown_role_422(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/invites",
                   json={"email": _PARTNER_EMAIL, "role": "sudo", "actor": _OWNER})
        assert r.status_code == 422


def test_accept_unverified_email_binds_nothing(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _client(dna_dir) as c:
        c.post(f"/v1/workspaces/{_WS}/invites",
               json={"email": _PARTNER_EMAIL, "role": "member", "actor": _OWNER})
        # No email_verified → not verified → nothing accepted.
        r = c.post("/v1/workspaces/accept",
                   json={"claims": {"oid": "oid-partner", "email": _PARTNER_EMAIL}})
        assert r.status_code == 200 and r.json()["accepted"] == []


# ── s-ws-res-rest-config: the token→identity→workspace binding ──────────────


class _FakeAccess:
    def __init__(self, claims):
        self.claims = claims


class _FakeVerifier:
    """A stand-in for the N-provider composite: the bearer string is a KEY into a
    claims table. An unknown token verifies to None (→ 401)."""

    def __init__(self, table):
        self._table = table

    async def verify_token(self, token):
        claims = self._table.get(token)
        return _FakeAccess(claims) if claims is not None else None


def _config_client(dna_dir, table) -> TestClient:
    return TestClient(R.build_app(
        base_dir=str(dna_dir), scope=_SCOPE, auth="config",
        verifier=_FakeVerifier(table),
    ))


def test_config_missing_token_401(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _config_client(dna_dir, {}) as c:
        assert c.get("/v1/memories").status_code == 401


def test_config_bad_token_401(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _config_client(dna_dir, {"good": _OWNER}) as c:
        r = c.get("/v1/memories", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401


def test_config_binds_tenant_from_membership(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _config_client(dna_dir, {"alice": _OWNER}) as c:
        # No tenant param → the middleware binds it to alice's sole workspace.
        r = c.get("/v1/memories", headers={"Authorization": "Bearer alice"})
        assert r.status_code == 200
        assert r.json()["tenant"] == _WS


def test_config_forged_cross_workspace_tenant_403(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _config_client(dna_dir, {"alice": _OWNER}) as c:
        # alice forges tenant=ws-evil (a workspace she is not a member of) → deny.
        r = c.get("/v1/memories", params={"tenant": "ws-evil"},
                  headers={"Authorization": "Bearer alice"})
        assert r.status_code == 403


def test_config_no_membership_403(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _config_client(dna_dir, {"stranger": {"oid": "oid-str", "email": "str@x.com"}}) as c:
        r = c.get("/v1/memories", headers={"Authorization": "Bearer stranger"})
        assert r.status_code == 403


def test_config_accept_route_is_exempt_from_bind(dna_dir):
    # The invitee is still PENDING (no active membership) — the accept route must be
    # reachable (exempt from the workspace bind) so they CAN accept.
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    async def invite():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        from dna.application import invite_member_impl
        await invite_member_impl(live, _WS, _PARTNER_EMAIL, "member", actor_claims=_OWNER)
    asyncio.run(invite())

    partner_claims = {"oid": "oid-partner", "email": _PARTNER_EMAIL,
                      "email_verified": True, "tid": "org-partner"}
    with _config_client(dna_dir, {"partner": partner_claims}) as c:
        r = c.post("/v1/workspaces/accept", headers={"Authorization": "Bearer partner"})
        assert r.status_code == 200, r.text
        assert r.json()["accepted"] == [
            {"workspace_id": _WS, "role": "member", "activated": True}
        ]


def test_config_invite_uses_verified_identity_as_actor(dna_dir):
    _seed_grant(dna_dir, _WS, "alice@a.com", "oid-alice", "owner")
    with _config_client(dna_dir, {"alice": _OWNER}) as c:
        # No `actor` in the body — the actor is the verified token identity.
        r = c.post(f"/v1/workspaces/{_WS}/invites",
                   headers={"Authorization": "Bearer alice"},
                   json={"email": _PARTNER_EMAIL, "role": "member"})
        assert r.status_code == 201, r.text
        assert r.json()["invite"]["invited_by"] == "alice@a.com"
