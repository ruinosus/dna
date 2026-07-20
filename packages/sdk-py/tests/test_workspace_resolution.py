"""Story ``s-ws-res-lookup`` / ``s-ws-res-parity`` — the pure Model B workspace
resolver (``dna.tenancy.resolution``).

Two layers:

1. **Golden fixtures** — every case in
   ``tests/golden-fixtures/workspace-resolution/cases.json`` is executed here:
   the same cases must always produce the same resolution outcomes.
2. **Python-side unit coverage** — the identity/membership matching helpers and
   the fail-closed edges, at the granularity the fixtures don't spell out.

The resolver is the crown-jewel authorization decision: a bug here is a
cross-workspace data leak, so the deny paths are asserted as hard as the golden.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from dna.tenancy.resolution import (
    CrossWorkspaceError,
    Identity,
    Membership,
    active_workspaces_for,
    identity_from_token,
    membership_matches_identity,
    normalize_email,
    resolve_workspace,
    workspace_for_identity,
)

_FIXTURES = (
    pathlib.Path(__file__).resolve().parents[3]
    / "tests" / "golden-fixtures" / "workspace-resolution" / "cases.json"
)


# ── the shared parity fixtures (the Py↔TS guard) ───────────────────────────


def _load_cases() -> list[dict]:
    data = json.loads(_FIXTURES.read_text(encoding="utf-8"))
    return data["cases"]


def _identity(raw: dict | None) -> Identity | None:
    if raw is None:
        return None
    return Identity(oid=raw.get("oid"), email=raw.get("email"), tid=raw.get("tid"))


def _memberships(raw: list[dict]) -> list[Membership]:
    return [Membership.from_spec(spec) for spec in raw]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_parity_fixture(case: dict):
    identity = _identity(case["identity"])
    memberships = _memberships(case["memberships"])
    expect = case["expect"]

    if "deny" in expect:
        with pytest.raises(CrossWorkspaceError) as ei:
            resolve_workspace(
                token_present=case["token_present"],
                identity=identity,
                requested=case["requested"],
                memberships=memberships,
            )
        assert expect["deny"] in str(ei.value), (
            f"{case['id']}: expected deny substring {expect['deny']!r} in {ei.value!r}"
        )
    else:
        got = resolve_workspace(
            token_present=case["token_present"],
            identity=identity,
            requested=case["requested"],
            memberships=memberships,
        )
        assert got == expect["workspace"], f"{case['id']}: got {got!r}"


def test_fixtures_are_nonempty():
    # Guard the guard: a truncated/empty fixture file must not silently pass.
    assert len(_load_cases()) >= 10


# ── identity_from_token: verified claims only ──────────────────────────────


def test_identity_from_token_reads_entra_claims():
    ident = identity_from_token(
        {"oid": "abc", "email": "A@B.com", "tid": "org-1", "sub": "ignored"}
    )
    assert ident.oid == "abc"
    assert ident.email == "A@B.com"  # preserved as-is; matching case-folds.
    assert ident.tid == "org-1"


def test_identity_from_token_email_fallback_order():
    # No `email` → falls back to preferred_username, then upn.
    assert identity_from_token({"preferred_username": "p@x.com"}).email == "p@x.com"
    assert identity_from_token({"upn": "u@x.com"}).email == "u@x.com"
    # `email` wins when present.
    assert identity_from_token({"email": "e@x.com", "upn": "u@x.com"}).email == "e@x.com"


def test_identity_from_token_missing_claims_are_none():
    ident = identity_from_token({})
    assert ident.oid is None and ident.email is None and ident.tid is None
    assert identity_from_token(None).oid is None


def test_normalize_email():
    assert normalize_email("  Foo@Bar.COM ") == "foo@bar.com"
    assert normalize_email(None) == ""
    assert normalize_email("") == ""


# ── membership_matches_identity: the oid-durable, email-handle rule ─────────


def _m(**kw) -> Membership:
    base = dict(
        workspace_id="ws", identity_email=None, identity_oid=None,
        role="member", status="active",
    )
    base.update(kw)
    return Membership(**base)


def test_match_bound_grant_on_oid():
    m = _m(identity_oid="oid-1", identity_email="a@x.com")
    assert membership_matches_identity(m, Identity(oid="oid-1", email="a@x.com"))
    # different oid, same email → NO match (bound grants are oid-only).
    assert not membership_matches_identity(m, Identity(oid="oid-2", email="a@x.com"))


def test_match_unbound_active_grant_on_verified_email():
    m = _m(identity_oid=None, identity_email="Founder@X.com")
    # case-insensitive verified-email match (the F1 seed contract).
    assert membership_matches_identity(m, Identity(oid="oid-new", email="founder@x.com"))
    # different email → no match.
    assert not membership_matches_identity(m, Identity(oid="oid-new", email="other@x.com"))


def test_pending_never_matches():
    m = _m(identity_oid="oid-1", identity_email="a@x.com", status="pending")
    assert not membership_matches_identity(m, Identity(oid="oid-1", email="a@x.com"))


def test_active_workspaces_dedup_and_order():
    ident = Identity(oid="oid-1", email="a@x.com")
    ms = [
        _m(workspace_id="ws-a", identity_oid="oid-1"),
        _m(workspace_id="ws-b", identity_oid="oid-1"),
        _m(workspace_id="ws-a", identity_oid="oid-1"),  # dup
        _m(workspace_id="ws-c", identity_oid="oid-OTHER"),  # not this identity
    ]
    assert active_workspaces_for(ident, ms) == ["ws-a", "ws-b"]


# ── workspace_for_identity: the fail-closed ladder ─────────────────────────


def test_deny_when_no_membership():
    with pytest.raises(CrossWorkspaceError, match="no active workspace membership"):
        workspace_for_identity(
            identity=Identity(oid="x"), requested_workspace=None, memberships=[]
        )


def test_deny_cross_workspace_requested():
    ms = [_m(workspace_id="ws-a", identity_oid="oid-1")]
    with pytest.raises(CrossWorkspaceError, match="not an active member"):
        workspace_for_identity(
            identity=Identity(oid="oid-1", email="a@x.com"),
            requested_workspace="ws-b",
            memberships=ms,
        )


def test_stdio_passthrough_ignores_memberships():
    # No token → requested passes through even if memberships would deny.
    assert resolve_workspace(
        token_present=False, identity=None, requested="whatever", memberships=[]
    ) == "whatever"
