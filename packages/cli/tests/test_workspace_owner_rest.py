"""Story ``s-ws-provision-owner-endpoint`` + ``s-ws-revoke-endpoint`` (feature
``f-ws-owner-provision``, issue ``i-033``) — the workspace owner-bootstrap +
revoke REST surface.

Drives the real FastAPI app in-process via ``TestClient`` against the committed
concierge example (copied to tmp so GLOBAL ``_lib`` Workspace/WorkspaceMembership
docs can be written).

The SECURITY-critical behaviors, gated end-to-end through the HTTP face:
* provision-owner is **idempotent** (re-call = no-op returning the membership) and
  **zero-migration** (creates the ``Workspace`` with id == the verified ``tid``);
  the created grant is **bound to the verified identity** (oid + email);
* a caller whose ``tid`` != the path workspace id is **403** (anti cross-tenant
  takeover); a later different user does NOT auto-escalate to owner;
* revoke: Owner/Admin removes a member; a **non-owner is 403**; the **last owner
  cannot be revoked (409)**; an unknown target is **404**.
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

# The founder: workspace id == the verified tid (the zero-migration invariant).
_WS = "ws-founder-tid"
_FOUNDER = {"oid": "oid-founder", "email": "founder@partner-org.com", "tid": _WS,
            "email_verified": True}


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


def _seed_grant(dna_dir, ws, email, oid, role, status="active"):
    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        name = f"{ws}--{email.replace('@', '-at-').replace('.', '-')}"
        await live.kernel.write_document(
            "_lib", "WorkspaceMembership", name,
            {"apiVersion": "github.com/ruinosus/dna/tenant/v1", "kind": "WorkspaceMembership",
             "metadata": {"name": name},
             "spec": {"workspace_id": ws, "identity_email": email, "identity_oid": oid,
                      "identity_tid": ws, "role": role, "status": status}},
        )
    asyncio.run(go())


# ── s-ws-provision-owner-endpoint ──────────────────────────────────────────


def test_provision_makes_first_user_owner_and_is_idempotent(dna_dir):
    with _client(dna_dir) as c:
        # First login: no membership → becomes owner, workspace created.
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": _FOUNDER})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["provisioned"] is True
        assert body["workspace_created"] is True
        m = body["membership"]
        # verified-identity binding: oid + email from the claims, owner + active.
        assert m["identity_email"] == "founder@partner-org.com"
        assert m["identity_oid"] == "oid-founder"
        assert m["role"] == "owner"
        assert m["status"] == "active"
        assert m["bound"] is True

        # Re-call (every dashboard load): no-op, returns the SAME membership.
        r2 = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": _FOUNDER})
        assert r2.status_code == 201, r2.text
        b2 = r2.json()
        assert b2["provisioned"] is False
        assert b2["reason"] == "already_member"
        assert b2["workspace_created"] is False
        assert b2["membership"]["identity_oid"] == "oid-founder"


def test_provision_zero_migration_workspace_id_equals_tid(dna_dir):
    with _client(dna_dir) as c:
        c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": _FOUNDER})
        # The Workspace doc was created with id == the path == the verified tid, so
        # every row keyed tenant==tid is already this workspace's data.
        async def read_ws():
            live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
            return await live.kernel.get_document("_lib", "Workspace", _WS)
        ws = asyncio.run(read_ws())
        assert ws is not None
        assert ws["spec"]["workspace_id"] == _WS == _FOUNDER["tid"]
        assert ws["spec"]["created_by"] == "founder@partner-org.com"


def test_provision_then_members_panel_shows_owner(dna_dir):
    # The end-to-end fix: after provisioning, the Members panel (403 before) works.
    with _client(dna_dir) as c:
        c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": _FOUNDER})
        r = c.get(f"/v1/workspaces/{_WS}/members",
                  params={"actor_oid": "oid-founder", "actor_email": "founder@partner-org.com"})
        assert r.status_code == 200, r.text
        rows = {m["identity_email"]: m for m in r.json()["members"]}
        assert rows["founder@partner-org.com"]["role"] == "owner"


def test_provision_cross_tid_is_forbidden(dna_dir):
    # An identity whose tid != the path workspace id cannot bootstrap ownership of
    # it — the anti cross-tenant takeover guard.
    attacker = {"oid": "oid-evil", "email": "evil@evil.com", "tid": "org-evil"}
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": attacker})
        assert r.status_code == 403, r.text


def test_provision_later_user_does_not_auto_escalate(dna_dir):
    # The founder owns the workspace; a colleague from the SAME azure org (tid ==
    # workspace id) who calls provision does NOT become a second owner.
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    colleague = {"oid": "oid-colleague", "email": "colleague@partner-org.com", "tid": _WS}
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": colleague})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["provisioned"] is False
        assert body["reason"] == "owner_exists"
        assert body["membership"] is None


def test_provision_requires_oid_and_email(dna_dir):
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner",
                   json={"claims": {"tid": _WS}})  # no oid/email
        assert r.status_code == 400, r.text


# ── s-ws-provision under --auth config (verified claims win over the body) ──


class _FakeAccess:
    def __init__(self, claims):
        self.claims = claims


class _FakeVerifier:
    def __init__(self, table):
        self._table = table

    async def verify_token(self, token):
        claims = self._table.get(token)
        return _FakeAccess(claims) if claims is not None else None


def test_provision_config_uses_verified_identity_not_body(dna_dir):
    # Under --auth config the caller cannot forge claims in the body: the verified
    # token identity is used (and it is EXEMPT from the membership bind, so a user
    # with no membership yet can still bootstrap).
    with TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, auth="config",
                                verifier=_FakeVerifier({"founder": _FOUNDER}))) as c:
        forged = {"oid": "oid-evil", "email": "evil@evil.com", "tid": _WS}
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner",
                   headers={"Authorization": "Bearer founder"},
                   json={"claims": forged})
        assert r.status_code == 201, r.text
        # The membership is the VERIFIED founder, not the forged body identity.
        assert r.json()["membership"]["identity_oid"] == "oid-founder"


# ── s-ws-revoke-endpoint (issue i-033) ─────────────────────────────────────


def test_revoke_owner_removes_member(dna_dir):
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    _seed_grant(dna_dir, _WS, "mem@partner-org.com", "oid-mem", "member")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/members/revoke",
                   json={"target_email": "mem@partner-org.com", "actor": _FOUNDER})
        assert r.status_code == 200, r.text
        assert r.json()["revoked"] is True
        assert r.json()["target"]["identity_email"] == "mem@partner-org.com"
        # Gone from the members list.
        m = c.get(f"/v1/workspaces/{_WS}/members",
                  params={"actor_oid": "oid-founder", "actor_email": "founder@partner-org.com"})
        assert "mem@partner-org.com" not in {x["identity_email"] for x in m.json()["members"]}


def test_revoke_by_oid(dna_dir):
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    _seed_grant(dna_dir, _WS, "mem@partner-org.com", "oid-mem", "member")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/members/revoke",
                   json={"target_oid": "oid-mem", "actor": _FOUNDER})
        assert r.status_code == 200, r.text


def test_revoke_pending_invite(dna_dir):
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    _seed_grant(dna_dir, _WS, "inv@partner-org.com", None, "member", status="pending")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/members/revoke",
                   json={"target_email": "inv@partner-org.com", "actor": _FOUNDER})
        assert r.status_code == 200, r.text


def test_revoke_non_owner_forbidden(dna_dir):
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    _seed_grant(dna_dir, _WS, "mem@partner-org.com", "oid-mem", "member")
    with _client(dna_dir) as c:
        # A member actor cannot revoke anyone.
        r = c.post(f"/v1/workspaces/{_WS}/members/revoke",
                   json={"target_email": "founder@partner-org.com",
                         "actor": {"oid": "oid-mem", "email": "mem@partner-org.com"}})
        assert r.status_code == 403, r.text


def test_revoke_last_owner_denied(dna_dir):
    # The sole owner cannot be revoked — the workspace must never be orphaned.
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    _seed_grant(dna_dir, _WS, "mem@partner-org.com", "oid-mem", "member")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/members/revoke",
                   json={"target_email": "founder@partner-org.com", "actor": _FOUNDER})
        assert r.status_code == 409, r.text
        assert "last remaining owner" in r.json()["detail"]


def test_revoke_one_of_two_owners_allowed(dna_dir):
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    _seed_grant(dna_dir, _WS, "co@partner-org.com", "oid-co", "owner")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/members/revoke",
                   json={"target_email": "co@partner-org.com", "actor": _FOUNDER})
        assert r.status_code == 200, r.text


def test_revoke_unknown_target_404(dna_dir):
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/members/revoke",
                   json={"target_email": "ghost@partner-org.com", "actor": _FOUNDER})
        assert r.status_code == 404, r.text


def test_revoke_missing_target_400(dna_dir):
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/members/revoke", json={"actor": _FOUNDER})
        assert r.status_code == 400, r.text
