"""Story ``s-ws-invite-create`` / ``s-ws-invite-accept`` — the invite/accept WRITE
impls end-to-end over a real (filesystem) source.

The pure decision is proven in ``sdk-py/tests/test_workspace_invite.py`` (+ the TS
twin). Here we prove the PERSISTENCE + RBAC WIRING against a live kernel: an
Owner invites a partner from another org (pending grant, oid unbound); a non-Owner
is denied; the partner's VERIFIED sign-in binds the oid + flips active; and the
anti-impersonation invariants hold on the write path — an unverified email binds
nothing, and a grant already bound to one oid cannot be re-bound by another.

Uses the committed ``examples/emitting-to-a-runtime`` concierge scope copied to a
tmp dir so the GLOBAL ``_lib`` WorkspaceMembership docs can be written.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna.application import (
    WorkspaceForbidden,
    accept_invites_impl,
    invite_member_impl,
    list_workspace_members_impl,
)
from dna_cli import _mcp_server as M

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WS = "ws-partner"  # a workspace id (NOT a company name — brand-guard clean).


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _run(dna_dir, coro_factory):
    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        return await coro_factory(live)

    return asyncio.run(go())


async def _seed_owner(live):
    """An active, oid-bound Owner grant for alice in ws-partner."""
    name = f"{_WS}--alice-at-a-com"
    await live.kernel.write_document(
        "_lib", "WorkspaceMembership", name,
        {
            "apiVersion": "github.com/ruinosus/dna/tenant/v1",
            "kind": "WorkspaceMembership",
            "metadata": {"name": name},
            "spec": {
                "workspace_id": _WS, "identity_email": "alice@a.com",
                "identity_oid": "oid-alice", "identity_tid": "org-a",
                "role": "owner", "status": "active",
            },
        },
    )


_OWNER_CLAIMS = {"oid": "oid-alice", "email": "alice@a.com", "tid": "org-a"}
# The partner from another org (email handle before first sign-in).
_PARTNER_EMAIL = "partner@partner-org.com"


# ── invite (s-ws-invite-create) ────────────────────────────────────────────


def test_owner_can_invite_creates_pending(dna_dir):
    async def go(live):
        await _seed_owner(live)
        res = await invite_member_impl(
            live, _WS, _PARTNER_EMAIL, "member", actor_claims=_OWNER_CLAIMS
        )
        assert res["invite"]["status"] == "pending"
        assert res["invite"]["bound"] is False
        assert res["invite"]["invited_by"] == "alice@a.com"
        # It is readable as a pending grant.
        members = await list_workspace_members_impl(live, _WS, actor_claims=_OWNER_CLAIMS)
        rows = {m["identity_email"]: m for m in members["members"]}
        assert rows[_PARTNER_EMAIL]["status"] == "pending"
        assert rows[_PARTNER_EMAIL]["bound"] is False
        return res

    _run(dna_dir, go)


def test_non_owner_cannot_invite(dna_dir):
    async def go(live):
        await _seed_owner(live)
        # An identity with NO grant in ws-partner is denied (fail-closed).
        with pytest.raises(WorkspaceForbidden, match="cannot manage members"):
            await invite_member_impl(
                live, _WS, _PARTNER_EMAIL, "member",
                actor_claims={"oid": "oid-nobody", "email": "nobody@x.com"},
            )
    _run(dna_dir, go)


def test_only_owner_may_invite_owner(dna_dir):
    async def go(live):
        # Seed an ADMIN (not owner).
        name = f"{_WS}--admin-at-a-com"
        await live.kernel.write_document(
            "_lib", "WorkspaceMembership", name,
            {"apiVersion": "github.com/ruinosus/dna/tenant/v1", "kind": "WorkspaceMembership",
             "metadata": {"name": name},
             "spec": {"workspace_id": _WS, "identity_email": "admin@a.com",
                      "identity_oid": "oid-admin", "role": "admin", "status": "active"}},
        )
        with pytest.raises(WorkspaceForbidden, match="only an Owner may grant the Owner role"):
            await invite_member_impl(
                live, _WS, _PARTNER_EMAIL, "owner",
                actor_claims={"oid": "oid-admin", "email": "admin@a.com"},
            )
        # But an admin CAN invite a member.
        res = await invite_member_impl(
            live, _WS, _PARTNER_EMAIL, "member",
            actor_claims={"oid": "oid-admin", "email": "admin@a.com"},
        )
        assert res["invite"]["role"] == "member"
    _run(dna_dir, go)


def test_list_requires_owner_or_admin(dna_dir):
    async def go(live):
        await _seed_owner(live)
        with pytest.raises(WorkspaceForbidden):
            await list_workspace_members_impl(
                live, _WS, actor_claims={"oid": "oid-x", "email": "x@x.com"}
            )
    _run(dna_dir, go)


# ── accept (s-ws-invite-accept) — the cross-org join + security ─────────────


def test_verified_signin_binds_and_activates(dna_dir):
    async def go(live):
        await _seed_owner(live)
        await invite_member_impl(live, _WS, _PARTNER_EMAIL, "member", actor_claims=_OWNER_CLAIMS)
        # The partner signs in from THEIR org — verified email + oid + provenance tid.
        res = await accept_invites_impl(live, {
            "oid": "oid-partner", "email": _PARTNER_EMAIL,
            "email_verified": True, "tid": "org-partner",
        })
        assert res["accepted"] == [{"workspace_id": _WS, "role": "member", "activated": True}]
        # The grant is now active + bound to the partner's oid (provenance tid recorded).
        members = await list_workspace_members_impl(live, _WS, actor_claims=_OWNER_CLAIMS)
        row = {m["identity_email"]: m for m in members["members"]}[_PARTNER_EMAIL]
        assert row["status"] == "active"
        assert row["bound"] is True
        # And it now authorizes the partner's own reads (resolves to ws-partner).
        from dna.tenancy import resolve_workspace, Membership
        grants = await live.kernel.workspace_memberships()
        ms = [Membership.from_spec(g["spec"]) for g in grants]
        from dna.tenancy import identity_from_token
        ident = identity_from_token({"oid": "oid-partner", "email": _PARTNER_EMAIL})
        assert resolve_workspace(token_present=True, identity=ident, requested=None, memberships=ms) == _WS
    _run(dna_dir, go)


def test_unverified_email_cannot_accept(dna_dir):
    async def go(live):
        await _seed_owner(live)
        await invite_member_impl(live, _WS, _PARTNER_EMAIL, "member", actor_claims=_OWNER_CLAIMS)
        # No email_verified, no preferred_username → not verified → binds NOTHING.
        res = await accept_invites_impl(live, {"oid": "oid-partner", "email": _PARTNER_EMAIL})
        assert res["accepted"] == []
        members = await list_workspace_members_impl(live, _WS, actor_claims=_OWNER_CLAIMS)
        row = {m["identity_email"]: m for m in members["members"]}[_PARTNER_EMAIL]
        assert row["status"] == "pending" and row["bound"] is False
    _run(dna_dir, go)


def test_bound_grant_not_hijackable_by_other_oid(dna_dir):
    async def go(live):
        await _seed_owner(live)
        await invite_member_impl(live, _WS, _PARTNER_EMAIL, "member", actor_claims=_OWNER_CLAIMS)
        # Legit partner accepts and binds their oid.
        await accept_invites_impl(live, {
            "oid": "oid-partner", "email": _PARTNER_EMAIL, "email_verified": True, "tid": "org-partner",
        })
        # An ATTACKER with the SAME verified email but a DIFFERENT oid tries to accept.
        res = await accept_invites_impl(live, {
            "oid": "oid-ATTACKER", "email": _PARTNER_EMAIL, "email_verified": True, "tid": "org-evil",
        })
        assert res["accepted"] == []  # the bound grant is NOT rebindable.
        # The grant remains bound to the original oid.
        grants = await live.kernel.workspace_memberships()
        row = {g["spec"]["identity_email"]: g["spec"] for g in grants}[_PARTNER_EMAIL]
        assert row["identity_oid"] == "oid-partner"
    _run(dna_dir, go)
