"""Story ``s-ws-invite-create`` / ``s-ws-invite-accept`` — the pure Model B
invite/accept policy (``dna.tenancy.invites``).

Two layers, mirroring ``test_workspace_resolution.py``:

1. **Shared parity fixtures** — every case in
   ``tests/parity-fixtures/workspace-invite/cases.json`` runs here AND in the TS
   twin (``packages/sdk-ts/tests/workspace-invite.test.ts``); the SAME cases →
   the SAME outcomes gate Py↔TS behavioral parity.
2. **Python-side security unit coverage** — the anti-impersonation edges spelled
   out hard: a wrong oid cannot accept, an oid-bound grant is not hijackable, an
   unverified email is denied. A bug here is a cross-org breach, so the deny paths
   are asserted as strongly as the golden.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from dna.tenancy.invites import (
    bindable_invites_for,
    can_invite,
    plan_accept,
    role_in_workspace,
    verified_email_from_claims,
)
from dna.tenancy.resolution import Identity, Membership

_FIXTURES = (
    pathlib.Path(__file__).resolve().parents[3]
    / "tests" / "parity-fixtures" / "workspace-invite" / "cases.json"
)


def _load() -> dict:
    return json.loads(_FIXTURES.read_text(encoding="utf-8"))


def _identity(raw: dict | None) -> Identity | None:
    if raw is None:
        return None
    return Identity(oid=raw.get("oid"), email=raw.get("email"), tid=raw.get("tid"))


def _memberships(raw: list[dict]) -> list[Membership]:
    return [Membership.from_spec(spec) for spec in raw]


# ── the shared parity fixtures (the Py↔TS guard) ───────────────────────────


@pytest.mark.parametrize(
    "case", _load()["authorize"], ids=lambda c: c["id"]
)
def test_parity_authorize(case: dict):
    identity = _identity(case["identity"])
    memberships = _memberships(case["memberships"])
    role = role_in_workspace(identity, case["workspace_id"], memberships)
    assert role == case["expect"]["role"], f"{case['id']}: role {role!r}"
    assert can_invite(role) == case["expect"]["can_invite"], case["id"]


@pytest.mark.parametrize("case", _load()["accept"], ids=lambda c: c["id"])
def test_parity_accept(case: dict):
    memberships = _memberships(case["memberships"])
    results = plan_accept(case["claims"], memberships)
    got = [{"workspace_id": r.workspace_id, "activated": r.activated} for r in results]
    assert got == case["expect"]["bound"], f"{case['id']}: bound {got!r}"


def test_fixtures_are_nonempty():
    data = _load()
    assert len(data["authorize"]) >= 5
    assert len(data["accept"]) >= 8


# ── verified_email_from_claims: the accept security gate ───────────────────


def test_verified_email_requires_email_verified_flag():
    # A bare email with no email_verified is NOT verified → None (fail-closed).
    assert verified_email_from_claims({"email": "a@x.com"}) is None
    assert verified_email_from_claims({"email": "a@x.com", "email_verified": False}) is None
    # email_verified truthy (bool or common JWT string forms) → normalized email.
    assert verified_email_from_claims({"email": "A@X.com", "email_verified": True}) == "a@x.com"
    assert verified_email_from_claims({"email": "a@x.com", "email_verified": "true"}) == "a@x.com"


def test_verified_email_trusts_entra_upn():
    # preferred_username / upn are the verified UPN — trusted without a flag.
    assert verified_email_from_claims({"preferred_username": "P@X.com"}) == "p@x.com"
    assert verified_email_from_claims({"upn": "U@X.com"}) == "u@x.com"


def test_verified_email_none_when_no_usable_claim():
    assert verified_email_from_claims({}) is None
    assert verified_email_from_claims(None) is None


# ── role_in_workspace + can_invite ─────────────────────────────────────────


def _m(**kw) -> Membership:
    base = dict(
        workspace_id="ws", identity_email=None, identity_oid=None,
        role="member", status="active",
    )
    base.update(kw)
    return Membership(**base)


def test_role_only_for_active_matching_grant():
    ident = Identity(oid="oid-1", email="a@x.com")
    ms = [_m(workspace_id="ws-a", identity_oid="oid-1", role="admin")]
    assert role_in_workspace(ident, "ws-a", ms) == "admin"
    # a pending grant confers no role.
    ms_pending = [_m(workspace_id="ws-a", identity_oid="oid-1", role="owner", status="pending")]
    assert role_in_workspace(ident, "ws-a", ms_pending) is None
    assert can_invite(None) is False


def test_role_is_per_workspace():
    ident = Identity(oid="oid-1", email="a@x.com")
    ms = [_m(workspace_id="ws-b", identity_oid="oid-1", role="owner")]
    assert role_in_workspace(ident, "ws-a", ms) is None  # owner of ws-b, not ws-a


# ── bindable_invites_for: the anti-impersonation core ──────────────────────


def test_bound_grant_is_not_hijackable_by_different_oid():
    # A grant already bound to oid-partner cannot be rebound by oid-attacker,
    # even with the SAME verified email — the crux security invariant.
    ms = [_m(
        workspace_id="ws-a", identity_email="partner@p.com",
        identity_oid="oid-partner", role="member", status="active",
    )]
    attacker = Identity(oid="oid-attacker", email="partner@p.com")
    assert bindable_invites_for(attacker, "partner@p.com", ms) == []


def test_unverified_identity_cannot_bind():
    ms = [_m(workspace_id="ws-a", identity_email="partner@p.com",
             identity_oid=None, status="pending")]
    partner = Identity(oid="oid-partner", email="partner@p.com")
    # verified_email None → nothing bound.
    assert bindable_invites_for(partner, None, ms) == []


def test_no_oid_cannot_bind():
    ms = [_m(workspace_id="ws-a", identity_email="partner@p.com",
             identity_oid=None, status="pending")]
    no_oid = Identity(oid=None, email="partner@p.com")
    assert bindable_invites_for(no_oid, "partner@p.com", ms) == []


def test_binds_all_pending_for_the_email():
    ms = [
        _m(workspace_id="ws-a", identity_email="partner@p.com", identity_oid=None, status="pending"),
        _m(workspace_id="ws-b", identity_email="partner@p.com", identity_oid=None, status="pending"),
        _m(workspace_id="ws-c", identity_email="other@p.com", identity_oid=None, status="pending"),
    ]
    partner = Identity(oid="oid-partner", email="partner@p.com")
    got = [m.workspace_id for m in bindable_invites_for(partner, "partner@p.com", ms)]
    assert got == ["ws-a", "ws-b"]
