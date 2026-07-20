"""Story ``s-ws-provision-owner-endpoint`` + ``s-ws-revoke-endpoint`` (feature
``f-ws-owner-provision``, issue ``i-033``) — the workspace owner-reconcile +
revoke REST surface, **as reshaped by decision D5**.

Drives the real FastAPI app in-process via ``TestClient`` against the committed
concierge example (copied to tmp so GLOBAL ``_lib`` Workspace/WorkspaceMembership
docs can be written).

**What D5 changed here.** This file used to open with "zero-migration (creates
the ``Workspace`` with id == the verified ``tid``)". That is gone: a workspace id
is now MINTED BY THE SERVER at ``POST /v1/workspaces`` and a ``tid`` is a fact of
authentication that authorizes nothing. ``provision-owner`` consequently creates
nothing at all — it degraded to the idempotent sign-in reconcile, which requires
an ACTIVE membership.

The SECURITY-critical behaviors, gated end-to-end through the HTTP face — the
ANSWERS below are the same as before D5, only their reasons moved:

* a caller with no active membership in the path workspace is **403** (anti
  cross-tenant takeover — this used to be phrased "tid != path id");
* a later different user does NOT auto-escalate to owner;
* provision-owner is **idempotent** (re-call = no-op returning the membership),
  and the grant it returns is **bound to the verified identity** (oid + email);
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

# A workspace id in the POST-D5 shape: generated, opaque, and deliberately
# UNRELATED to any Azure tenant id. The founder's ``tid`` below is a different
# string on purpose — if any of these tests starts depending on them matching,
# the old coupling has crept back.
_WS = "ws-mfrggzdfmztwq2lknnwg23th"
_FOUNDER = {"oid": "oid-founder", "email": "founder@partner-org.com",
            "tid": "8e1f0a44-azure-org-of-the-founder", "email_verified": True}


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
                      "identity_tid": "some-azure-org", "role": role, "status": status}},
        )
    asyncio.run(go())


# ── s-ws-provision-owner-endpoint (post-D5: reconcile, never create) ────────


def test_provision_is_an_idempotent_noop_for_an_existing_member(dna_dir):
    # REPLACES test_provision_makes_first_user_owner_and_is_idempotent. The
    # "makes first user owner" half moved to POST /v1/workspaces (D5); what is
    # left is the every-dashboard-load reconcile, which must stay safe to spam.
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    with _client(dna_dir) as c:
        for _ in range(2):
            r = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": _FOUNDER})
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["provisioned"] is False
            assert body["reason"] == "already_member"
            m = body["membership"]
            # verified-identity binding: oid + email from the grant, owner + active.
            assert m["identity_email"] == "founder@partner-org.com"
            assert m["identity_oid"] == "oid-founder"
            assert m["role"] == "owner"
            assert m["status"] == "active"
            assert m["bound"] is True


def test_provision_cannot_create_a_workspace_at_all(dna_dir):
    # REPLACES test_provision_zero_migration_workspace_id_equals_tid — the
    # detector D5 was always going to break. The equality it asserted
    # (`workspace_id == tid`) no longer exists; what matters now is the STRONGER
    # statement that this route cannot bring a workspace into being at all.
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": _FOUNDER})
        assert r.status_code == 403, r.text

    async def read_ws():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        try:
            return await live.kernel.get_document("_lib", "Workspace", _WS)
        except FileNotFoundError:
            return None  # `_lib` never even came into existence
    assert asyncio.run(read_ws()) is None  # nothing was written


def test_provision_ignores_the_tid_entirely(dna_dir):
    # The positive statement of D5 at the HTTP edge. A member whose tid has
    # nothing to do with the workspace id is served; a non-member whose tid EQUALS
    # the workspace id is refused. Under the pre-D5 guard both answers inverted.
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": _FOUNDER})
        assert r.status_code == 201, r.text

        tid_matcher = {"oid": "oid-x", "email": "x@evil.com", "tid": _WS}
        r2 = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": tid_matcher})
        assert r2.status_code == 403, r2.text


def test_provision_then_members_panel_shows_owner(dna_dir):
    # The end-to-end path: create the workspace (the act D5 introduced), then the
    # Members panel works and provision is a harmless no-op on top.
    with _client(dna_dir) as c:
        created = c.post("/v1/workspaces",
                         json={"name": "Partner Labs", "claims": _FOUNDER})
        assert created.status_code == 201, created.text
        ws = created.json()["workspace_id"]

        assert c.post(f"/v1/workspaces/{ws}/provision-owner",
                      json={"claims": _FOUNDER}).status_code == 201
        r = c.get(f"/v1/workspaces/{ws}/members",
                  params={"actor_oid": "oid-founder", "actor_email": "founder@partner-org.com"})
        assert r.status_code == 200, r.text
        rows = {m["identity_email"]: m for m in r.json()["members"]}
        assert rows["founder@partner-org.com"]["role"] == "owner"


def test_provision_by_a_stranger_is_forbidden(dna_dir):
    # SECURITY — the anti cross-tenant takeover guard, formerly
    # test_provision_cross_tid_is_forbidden. The REASON moved from "your tid does
    # not match the path id" to "you hold no active membership here". The ANSWER
    # is unchanged and is not permitted to change: 403.
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    attacker = {"oid": "oid-evil", "email": "evil@evil.com", "tid": "org-evil"}
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": attacker})
        assert r.status_code == 403, r.text


def test_provision_later_user_does_not_auto_escalate(dna_dir):
    # SECURITY. The founder owns the workspace; a colleague who was never invited
    # calls provision and does NOT become a second owner.
    #
    # The answer got STRONGER under D5, not weaker: pre-D5 the colleague passed the
    # guard (same tid) and got a 201 `owner_exists` no-op; now they are 403'd before
    # anything is revealed. The property under test — "a later user does not
    # auto-escalate" — is asserted directly below, on the membership list, so it
    # cannot be satisfied by the status code alone.
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    colleague = {"oid": "oid-colleague", "email": "colleague@partner-org.com",
                 "tid": _FOUNDER["tid"]}
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": colleague})
        assert r.status_code == 403, r.text

        members = c.get(f"/v1/workspaces/{_WS}/members",
                        params={"actor_oid": "oid-founder",
                                "actor_email": "founder@partner-org.com"}).json()["members"]
        owners = [m["identity_email"] for m in members if m["role"] == "owner"]
        assert owners == ["founder@partner-org.com"]
        assert "colleague@partner-org.com" not in {m["identity_email"] for m in members}


def test_provision_requires_oid_and_email(dna_dir):
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner",
                   json={"claims": {"tid": _WS}})  # no oid/email
        assert r.status_code == 400, r.text


def test_provision_backfills_a_missing_workspace_doc_for_an_owner(dna_dir):
    # The repair path: a grant seeded without its Workspace identity doc (the F1
    # seed shape, or a create that crashed between its two writes) is completed on
    # the owner's next sign-in. Gated on the OWNER grant, so it can never mint a
    # workspace for someone who does not already own one.
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
    with _client(dna_dir) as c:
        r = c.post(f"/v1/workspaces/{_WS}/provision-owner", json={"claims": _FOUNDER})
        assert r.status_code == 201, r.text
        assert r.json()["workspace_created"] is True

    async def read_ws():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        return await live.kernel.get_document("_lib", "Workspace", _WS)
    ws = asyncio.run(read_ws())
    assert ws is not None
    assert ws["spec"]["workspace_id"] == _WS
    assert ws["spec"]["created_by"] == "founder@partner-org.com"


# ── D5 back-compat: the founder's tid-shaped workspace id still works ───────


_LEGACY_WS = "c5b891f7-65c2-4417-a5af-22cab24dc1d5"  # once the founder's Azure tid


def test_a_workspace_whose_id_happens_to_be_a_tid_still_works(dna_dir):
    """The founder's live workspace was seeded with his Azure ``tid`` as its id.
    After D5 it must keep working — and NOT because anything special-cases it, but
    because a ``tid`` is now just another opaque string. Nothing in the request
    below mentions a tid; the id is carried as a path segment like any other."""
    _seed_grant(dna_dir, _LEGACY_WS, "jefferson@example.com", None, "owner")
    founder = {"oid": "oid-jb", "email": "jefferson@example.com",
               "tid": "a-completely-different-azure-org"}
    with _client(dna_dir) as c:
        # Sign-in reconcile: the unbound-but-active seed grant matches on the
        # verified email, so he is entitled — his tid is never consulted.
        r = c.post(f"/v1/workspaces/{_LEGACY_WS}/provision-owner", json={"claims": founder})
        assert r.status_code == 201, r.text
        assert r.json()["reason"] == "already_member"

        # It enumerates, and it is his.
        listed = c.get("/v1/workspaces", params={"actor_oid": "oid-jb",
                                                 "actor_email": "jefferson@example.com"})
        assert listed.status_code == 200, listed.text
        assert [w["workspace_id"] for w in listed.json()["workspaces"]] == [_LEGACY_WS]

        # And a project can be created inside it.
        p = c.post("/v1/projects", json={"workspace_id": _LEGACY_WS,
                                         "name": "Legacy Project", "claims": founder})
        assert p.status_code == 201, p.text
        assert p.json()["project"]["workspace_id"] == _LEGACY_WS

        # A stranger is still refused it — the id being tid-shaped grants nobody
        # anything, not even the identity whose tid it once was.
        impostor = {"oid": "oid-evil", "email": "evil@evil.com", "tid": _LEGACY_WS}
        assert c.post(f"/v1/workspaces/{_LEGACY_WS}/provision-owner",
                      json={"claims": impostor}).status_code == 403


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
    # token identity is used (and it is EXEMPT from the membership bind, so the
    # route's own guard is the only thing deciding).
    _seed_grant(dna_dir, _WS, "founder@partner-org.com", "oid-founder", "owner")
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
