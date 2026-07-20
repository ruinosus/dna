"""Story ``s-ws-provision-owner-endpoint`` / ``s-ws-revoke-endpoint`` — the pure
Model B workspace-ownership policy (``dna.tenancy.ownership``).

Two layers, mirroring ``test_workspace_invite.py``:

1. **Golden fixtures** — every case in
   ``tests/golden-fixtures/workspace-ownership/cases.json`` runs here: the same
   cases must always produce the same ownership outcomes.
2. **Python-side security unit coverage** — the two crown-jewel invariants spelled
   out hard: the LAST active owner can never be revoked (no orphaned workspace),
   and a non-Owner/Admin can revoke nobody (RBAC). A bug here is a workspace
   takeover or lock-out, so the deny paths are asserted as strongly as the golden.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from dna.tenancy.ownership import (
    active_owners,
    can_revoke_role,
    has_active_owner,
    is_last_active_owner,
    plan_revoke,
)
from dna.tenancy.resolution import Membership

_FIXTURES = (
    pathlib.Path(__file__).resolve().parents[3]
    / "tests" / "golden-fixtures" / "workspace-ownership" / "cases.json"
)


def _load() -> dict:
    return json.loads(_FIXTURES.read_text(encoding="utf-8"))


def _memberships(raw: list[dict]) -> list[Membership]:
    return [Membership.from_spec(spec) for spec in raw]


# ── the shared parity fixtures (the Py↔TS guard) ───────────────────────────


@pytest.mark.parametrize("case", _load()["owners"], ids=lambda c: c["id"])
def test_parity_owners(case: dict):
    memberships = _memberships(case["memberships"])
    owners = active_owners(case["workspace_id"], memberships)
    emails = [m.identity_email for m in owners]
    assert emails == case["expect"]["owners"], f"{case['id']}: owners {emails!r}"
    assert (
        has_active_owner(case["workspace_id"], memberships)
        == case["expect"]["has_active_owner"]
    ), case["id"]


@pytest.mark.parametrize("case", _load()["revoke"], ids=lambda c: c["id"])
def test_parity_revoke(case: dict):
    memberships = _memberships(case["memberships"])
    target = Membership.from_spec(case["target"]) if case["target"] else None
    decision = plan_revoke(
        case["actor_role"], target, case["workspace_id"], memberships
    )
    assert decision.allowed == case["expect"]["allowed"], case["id"]
    assert decision.reason == case["expect"]["reason"], case["id"]


def test_fixtures_are_nonempty():
    data = _load()
    assert len(data["owners"]) >= 5
    assert len(data["revoke"]) >= 6


# ── ownership unit coverage ────────────────────────────────────────────────


def _m(**kw) -> Membership:
    base = dict(
        workspace_id="ws", identity_email=None, identity_oid=None,
        role="member", status="active",
    )
    base.update(kw)
    return Membership(**base)


def test_pending_owner_is_not_an_active_owner():
    ms = [_m(workspace_id="ws-a", identity_email="o@a.com", role="owner", status="pending")]
    assert active_owners("ws-a", ms) == []
    assert has_active_owner("ws-a", ms) is False


def test_unbound_active_seed_owner_counts():
    # The F1 founder seed: active owner, oid still null — it IS an owner.
    ms = [_m(workspace_id="ws-a", identity_email="f@a.com", identity_oid=None,
             role="owner", status="active")]
    assert has_active_owner("ws-a", ms) is True


# ── the last-owner invariant (the crown jewel) ─────────────────────────────


def test_last_owner_cannot_be_revoked():
    owner = _m(workspace_id="ws-a", identity_email="o@a.com", identity_oid="oid-o", role="owner")
    ms = [owner, _m(workspace_id="ws-a", identity_email="m@a.com", identity_oid="oid-m")]
    assert is_last_active_owner("ws-a", owner, ms) is True
    assert plan_revoke("owner", owner, "ws-a", ms).reason == "last_owner"


def test_one_of_two_owners_is_revocable():
    a = _m(workspace_id="ws-a", identity_email="a@a.com", identity_oid="oid-a", role="owner")
    b = _m(workspace_id="ws-a", identity_email="b@a.com", identity_oid="oid-b", role="owner")
    assert is_last_active_owner("ws-a", a, [a, b]) is False
    assert plan_revoke("owner", a, "ws-a", [a, b]).allowed is True


def test_last_owner_match_survives_target_rebuilt_from_spec():
    # The impl rebuilds the target from a spec dict, so identity is by subject
    # (oid/email), not object identity — the guard must still fire.
    owner = _m(workspace_id="ws-a", identity_email="O@a.com", identity_oid="oid-o", role="owner")
    rebuilt = Membership.from_spec({
        "workspace_id": "ws-a", "identity_email": "o@a.com", "identity_oid": "oid-o",
        "role": "owner", "status": "active",
    })
    assert is_last_active_owner("ws-a", rebuilt, [owner]) is True


# ── RBAC: only Owner/Admin may revoke ──────────────────────────────────────


def test_non_owner_admin_cannot_revoke():
    assert can_revoke_role("member") is False
    assert can_revoke_role("guest") is False
    assert can_revoke_role(None) is False
    assert can_revoke_role("owner") is True
    assert can_revoke_role("admin") is True
    target = _m(workspace_id="ws-a", identity_email="m@a.com", role="member")
    assert plan_revoke("member", target, "ws-a", [target]).reason == "not_authorized"


def test_rbac_denies_before_revealing_target_existence():
    # A member actor is denied even when the target does not exist — RBAC first,
    # so an unauthorized caller cannot probe membership (no existence oracle).
    assert plan_revoke("member", None, "ws-a", []).reason == "not_authorized"


def test_missing_target_is_not_found_for_authorized_actor():
    assert plan_revoke("owner", None, "ws-a", []).reason == "not_found"
