"""**The act of creation** — ``POST /v1/workspaces`` / ``GET /v1/workspaces`` /
``POST /v1/projects`` (decisions **D5** + **A1**).

Before these routes existed, DNA Cloud could not create the thing it sells: a
``Workspace`` was a by-product of signing in (its id *was* the Azure ``tid``) and
a ``Project`` only ever came from a seed script. This file pins the write path
end-to-end through the real FastAPI app.

The two properties that carry the security weight:

* **the id is minted by the server.** There is no request field for it, so a
  caller cannot name a workspace into existence — which is what replaced the old
  ``tid == workspace_id`` anti-takeover comparison. A body that smuggles one in
  is ignored, not honoured.
* **membership is the only key.** ``GET /v1/workspaces`` enumerates by ACTIVE
  membership and ``POST /v1/projects`` 403s a non-member. No ``tid`` anywhere.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402
from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"

# `email_verified` is what makes the email claim usable for accepting an invite
# (`verified_email_from_claims` is fail-closed without it).
_ALICE = {"oid": "oid-alice", "email": "alice@acme.com", "tid": "azure-org-acme",
          "email_verified": True}
_BOB = {"oid": "oid-bob", "email": "bob@globex.com", "tid": "azure-org-globex",
        "email_verified": True}

_ID_RE = re.compile(r"^ws-[a-z2-7]{24}$")


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


def _read(dna_dir, kind, name, scope="_lib"):
    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        return await live.kernel.get_document(scope, kind, name)
    return asyncio.run(go())


# ── POST /v1/workspaces ─────────────────────────────────────────────────────


def test_create_writes_the_workspace_and_its_owner_together(dna_dir):
    with _client(dna_dir) as c:
        r = c.post("/v1/workspaces", json={"name": "Acme Labs", "claims": _ALICE})
        assert r.status_code == 201, r.text
        body = r.json()
        wid = body["workspace_id"]
        assert body["name"] == "Acme Labs"
        assert body["slug"] == "acme-labs"
        assert body["created_by"] == "alice@acme.com"
        assert body["role"] == "owner"

    ws = _read(dna_dir, "Workspace", wid)
    assert ws is not None
    assert ws["spec"]["workspace_id"] == wid

    grant = _read(dna_dir, "WorkspaceMembership", f"{wid}--alice-at-acme-com")
    assert grant is not None
    spec = grant["spec"]
    assert spec["role"] == "owner"
    assert spec["status"] == "active"
    assert spec["identity_oid"] == "oid-alice"           # bound to the verified id
    assert spec["identity_tid"] == "azure-org-acme"      # provenance only


def test_the_id_is_server_minted_and_a_client_supplied_one_is_never_honoured(dna_dir):
    """THE anti-takeover property, post-D5. The old guard stopped a stranger from
    claiming a workspace by comparing tids. The new design stops them earlier: the
    id cannot be chosen at all, so there is nothing to race for.

    A body that smuggles ``workspace_id`` (and, for good measure, the fields the
    old attack would have targeted) must have NO effect on the minted id."""
    with _client(dna_dir) as c:
        r = c.post("/v1/workspaces", json={
            "name": "Acme Labs",
            "claims": _ALICE,
            "workspace_id": "ws-i-picked-this-myself",
            "id": "ws-i-picked-this-myself",
            "tid": "azure-org-acme",
        })
        assert r.status_code == 201, r.text
        wid = r.json()["workspace_id"]

    assert _ID_RE.match(wid), wid
    assert wid != "ws-i-picked-this-myself"
    assert "acme" not in wid          # not derived from the name…
    assert "alice" not in wid         # …nor the identity…
    assert "azure-org-acme" not in wid  # …nor the tid.
    assert _read(dna_dir, "Workspace", "ws-i-picked-this-myself") is None


def test_two_creations_never_share_an_id(dna_dir):
    with _client(dna_dir) as c:
        a = c.post("/v1/workspaces", json={"name": "Same Name", "claims": _ALICE})
        b = c.post("/v1/workspaces", json={"name": "Same Name", "claims": _BOB})
        assert a.json()["workspace_id"] != b.json()["workspace_id"]
        # Slug is presentation over a stable id, so a collision decorates the
        # slug — it never touches the id and never refuses the creation.
        assert {a.json()["slug"], b.json()["slug"]} == {"same-name", "same-name-2"}


def test_create_derives_the_slug_and_accepts_an_explicit_one(dna_dir):
    with _client(dna_dir) as c:
        assert c.post("/v1/workspaces", json={
            "name": "Barnabé Labs", "claims": _ALICE}).json()["slug"] == "barnabe-labs"
        assert c.post("/v1/workspaces", json={
            "name": "Whatever", "slug": "My Chosen Slug!",
            "claims": _ALICE}).json()["slug"] == "my-chosen-slug"


def test_create_falls_back_to_the_id_when_the_name_slugifies_to_nothing(dna_dir):
    with _client(dna_dir) as c:
        body = c.post("/v1/workspaces", json={"name": "日本語", "claims": _ALICE}).json()
        assert body["slug"] == body["workspace_id"]  # honest, never invented


def test_create_rejects_a_blank_name_and_an_identity_without_claims(dna_dir):
    with _client(dna_dir) as c:
        assert c.post("/v1/workspaces",
                      json={"name": "   ", "claims": _ALICE}).status_code == 400
        assert c.post("/v1/workspaces",
                      json={"name": "X", "claims": {"tid": "t"}}).status_code == 400
        assert c.post("/v1/workspaces",
                      json={"name": "X", "claims": {"email": "a@b.c"}}).status_code == 400


def test_create_needs_no_pre_existing_membership(dna_dir):
    """The bootstrap hole D5 had to leave open: a brand-new user belongs to
    nothing, so creation cannot require membership. That is safe precisely because
    the id is minted — the caller receives a workspace, never seizes one."""
    with _client(dna_dir) as c:
        assert c.post("/v1/workspaces",
                      json={"name": "First Ever", "claims": _BOB}).status_code == 201


# ── GET /v1/workspaces ──────────────────────────────────────────────────────


def test_list_enumerates_by_active_membership_only(dna_dir):
    with _client(dna_dir) as c:
        mine = c.post("/v1/workspaces", json={"name": "Alice One", "claims": _ALICE}).json()
        c.post("/v1/workspaces", json={"name": "Alice Two", "claims": _ALICE})
        theirs = c.post("/v1/workspaces", json={"name": "Bob Only", "claims": _BOB}).json()

        r = c.get("/v1/workspaces", params={"actor_oid": "oid-alice",
                                            "actor_email": "alice@acme.com"})
        assert r.status_code == 200, r.text
        rows = r.json()["workspaces"]
        assert [w["name"] for w in rows] == ["Alice One", "Alice Two"]
        assert {w["role"] for w in rows} == {"owner"}
        assert mine["workspace_id"] in {w["workspace_id"] for w in rows}
        # Bob's workspace is invisible — enumeration is by membership, full stop.
        assert theirs["workspace_id"] not in {w["workspace_id"] for w in rows}


def test_list_omits_pending_invites_and_returns_empty_for_a_stranger(dna_dir):
    with _client(dna_dir) as c:
        created = c.post("/v1/workspaces", json={"name": "Acme", "claims": _ALICE}).json()
        wid = created["workspace_id"]
        assert c.post(f"/v1/workspaces/{wid}/invites",
                      json={"email": "bob@globex.com", "role": "member",
                            "actor": _ALICE}).status_code == 201

        # Invited but not accepted → authorizes nothing, so it is not listed.
        r = c.get("/v1/workspaces", params={"actor_oid": "oid-bob",
                                            "actor_email": "bob@globex.com"})
        assert r.json()["workspaces"] == []

        # After accepting, it appears — with the granted role, not owner.
        assert c.post("/v1/workspaces/accept", json={"claims": _BOB}).status_code == 200
        rows = c.get("/v1/workspaces", params={"actor_oid": "oid-bob",
                                               "actor_email": "bob@globex.com"}).json()["workspaces"]
        assert [(w["workspace_id"], w["role"]) for w in rows] == [(wid, "member")]

        # A wholly unknown identity gets an empty list, never someone else's.
        assert c.get("/v1/workspaces", params={"actor_oid": "oid-ghost",
                                               "actor_email": "ghost@nowhere.com"}
                     ).json()["workspaces"] == []


# ── POST /v1/projects (decision A1) ─────────────────────────────────────────


def test_create_project_binds_it_to_the_workspace_and_derives_the_scope(dna_dir):
    with _client(dna_dir) as c:
        wid = c.post("/v1/workspaces",
                     json={"name": "Acme Labs", "claims": _ALICE}).json()["workspace_id"]
        r = c.post("/v1/projects", json={"workspace_id": wid,
                                         "name": "Copiloto Médico", "claims": _ALICE})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["workspace_id"] == wid
        p = body["project"]
        assert p["name"] == "Copiloto Médico"
        assert p["slug"] == "copiloto-medico"
        assert p["workspace_id"] == wid                       # A1: explicit edge
        assert p["board_scope"] == "copiloto-medico-development"  # derived
        # The write scope is derived from the workspace, never caller-supplied.
        assert body["scope"] == "concierge"

        # It reads back through the existing list route.
        listed = c.get("/v1/projects", params={"tenant": wid}).json()["projects"]
        assert [x["name"] for x in listed] == ["Copiloto Médico"]
        assert listed[0]["workspace_id"] == wid


def test_create_project_without_active_membership_is_403(dna_dir):
    with _client(dna_dir) as c:
        wid = c.post("/v1/workspaces",
                     json={"name": "Acme Labs", "claims": _ALICE}).json()["workspace_id"]
        # Bob belongs to nothing here — 403, and nothing is written.
        r = c.post("/v1/projects", json={"workspace_id": wid, "name": "Sneaky",
                                         "claims": _BOB})
        assert r.status_code == 403, r.text
        assert c.get("/v1/projects", params={"tenant": wid}).json()["projects"] == []

        # A PENDING invite is not membership either — fail-closed on lifecycle.
        c.post(f"/v1/workspaces/{wid}/invites",
               json={"email": "bob@globex.com", "role": "member", "actor": _ALICE})
        assert c.post("/v1/projects", json={"workspace_id": wid, "name": "Sneaky",
                                            "claims": _BOB}).status_code == 403

        # Accepted → allowed. A plain member may create projects.
        c.post("/v1/workspaces/accept", json={"claims": _BOB})
        assert c.post("/v1/projects", json={"workspace_id": wid, "name": "Legit",
                                            "claims": _BOB}).status_code == 201


def test_create_project_slug_is_unique_within_the_workspace(dna_dir):
    with _client(dna_dir) as c:
        a = c.post("/v1/workspaces", json={"name": "A", "claims": _ALICE}).json()["workspace_id"]
        b = c.post("/v1/workspaces", json={"name": "B", "claims": _ALICE}).json()["workspace_id"]
        s1 = c.post("/v1/projects", json={"workspace_id": a, "name": "Atlas",
                                          "claims": _ALICE}).json()["project"]["slug"]
        s2 = c.post("/v1/projects", json={"workspace_id": a, "name": "Atlas 2",
                                          "slug": "atlas",
                                          "claims": _ALICE}).json()["project"]["slug"]
        assert (s1, s2) == ("atlas", "atlas-2")
        # Uniqueness is per-workspace, not global — two workspaces may both have
        # an "atlas". The slug is scoped by the id, exactly as A1 says.
        s3 = c.post("/v1/projects", json={"workspace_id": b, "name": "Atlas",
                                          "claims": _ALICE}).json()["project"]["slug"]
        assert s3 == "atlas"


def test_create_project_rejects_a_blank_workspace_or_name(dna_dir):
    with _client(dna_dir) as c:
        wid = c.post("/v1/workspaces",
                     json={"name": "Acme", "claims": _ALICE}).json()["workspace_id"]
        assert c.post("/v1/projects", json={"workspace_id": "  ", "name": "X",
                                            "claims": _ALICE}).status_code == 400
        assert c.post("/v1/projects", json={"workspace_id": wid, "name": " ",
                                            "claims": _ALICE}).status_code == 400


# ── under --auth config: the verified token wins over the body ──────────────


class _FakeAccess:
    def __init__(self, claims):
        self.claims = claims


class _FakeVerifier:
    def __init__(self, table):
        self._table = table

    async def verify_token(self, token):
        claims = self._table.get(token)
        return _FakeAccess(claims) if claims is not None else None


def test_config_auth_creates_for_the_verified_identity_not_the_body(dna_dir):
    app = R.build_app(base_dir=str(dna_dir), scope=_SCOPE, auth="config",
                      verifier=_FakeVerifier({"alice": _ALICE, "bob": _BOB}))
    with TestClient(app) as c:
        r = c.post("/v1/workspaces", headers={"Authorization": "Bearer alice"},
                   json={"name": "Acme", "claims": _BOB})  # forged body identity
        assert r.status_code == 201, r.text
        wid = r.json()["workspace_id"]
        assert r.json()["created_by"] == "alice@acme.com"

        # Bob cannot create a project in it even with a valid token of his own —
        # POST /v1/projects is exempt from the tenant BIND, never from the check.
        assert c.post("/v1/projects", headers={"Authorization": "Bearer bob"},
                      json={"workspace_id": wid, "name": "Nope"}).status_code == 403
        # Alice can, and never had to name a `tenant` query param to do it.
        assert c.post("/v1/projects", headers={"Authorization": "Bearer alice"},
                      json={"workspace_id": wid, "name": "Yes"}).status_code == 201

        # The switcher read is scoped to the verified identity too.
        rows = c.get("/v1/workspaces", headers={"Authorization": "Bearer bob"}
                     ).json()["workspaces"]
        assert rows == []
