"""Story ``s-ws-res-mcp-url`` — the per-workspace MCP URL selector (ADR "Model B"
§2.2 / S2.3): a client picks its workspace by URL ``…/w/<id>/mcp``; the bare
``/mcp`` falls back to the identity's sole/default membership.

Two layers:
1. The pure ``workspace_from_mcp_path`` — path → workspace id (mount-prefix safe,
   trailing-slash tolerant, ``None`` for a bare ``/mcp``).
2. The GLUE: ``workspace_selector_from_context`` + its use in
   ``enforce_workspace_from_context`` (the path selector feeds the resolver; an
   explicit tool arg is honored; a contradictory pair is DENIED).
"""
from __future__ import annotations

import asyncio

import pytest

from dna_cli import _mcp_auth as A


# ── the pure path parser ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/w/ws-a/mcp", "ws-a"),
        ("/w/ws-a/mcp/", "ws-a"),
        ("/w/c5b891f7-65c2-4417-a5af-22cab24dc1d5/mcp", "c5b891f7-65c2-4417-a5af-22cab24dc1d5"),
        ("/mcp", None),
        ("/mcp/", None),
        ("/", None),
        ("", None),
        (None, None),
        ("/w//mcp", None),          # empty id → no selector.
        ("/w/ws-a", None),          # missing trailing mcp → not a selector.
        ("/prefix/w/ws-b/mcp", "ws-b"),  # mount-prefix safe.
    ],
)
def test_workspace_from_mcp_path(path, expected):
    assert A.workspace_from_mcp_path(path) == expected


# ── selector combination (path × explicit arg) ─────────────────────────────


def test_combine_prefers_explicit_then_path():
    assert A._combine_workspace_selectors(None, None) is None
    assert A._combine_workspace_selectors("ws-a", None) == "ws-a"   # path only
    assert A._combine_workspace_selectors(None, "ws-a") == "ws-a"   # arg only
    assert A._combine_workspace_selectors("ws-a", "ws-a") == "ws-a"  # agree


def test_combine_denies_conflicting_selectors():
    with pytest.raises(A.CrossTenantError, match="conflicting workspace selectors"):
        A._combine_workspace_selectors("ws-a", "ws-b")


# ── the glue: the path selector drives resolution ──────────────────────────


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


def _grant(ws, email, oid, role="member", status="active"):
    return {"spec": {"workspace_id": ws, "identity_email": email,
                     "identity_oid": oid, "role": role, "status": status}}


def _patch(monkeypatch, *, claims, path):
    from dna.tenancy.resolution import identity_from_token
    monkeypatch.setattr(A, "token_present_in_context", lambda: True)
    monkeypatch.setattr(A, "identity_from_context", lambda: identity_from_token(claims))
    monkeypatch.setattr(A, "workspace_selector_from_context", lambda: path)


def test_path_selector_picks_the_workspace(monkeypatch):
    # partner is an active member of BOTH ws-a and ws-b; the URL path disambiguates.
    _patch(monkeypatch, claims={"oid": "oid-p", "email": "p@x.com"}, path="ws-b")
    live = _FakeLive([
        _grant("ws-a", "p@x.com", "oid-p"),
        _grant("ws-b", "p@x.com", "oid-p"),
    ])
    assert _run(A.enforce_workspace_from_context(live, None)) == "ws-b"


def test_no_path_selector_falls_back_to_sole_membership(monkeypatch):
    _patch(monkeypatch, claims={"oid": "oid-p", "email": "p@x.com"}, path=None)
    live = _FakeLive([_grant("ws-a", "p@x.com", "oid-p")])
    assert _run(A.enforce_workspace_from_context(live, None)) == "ws-a"


def test_path_selector_for_non_member_is_denied(monkeypatch):
    from dna.tenancy.resolution import CrossWorkspaceError
    _patch(monkeypatch, claims={"oid": "oid-p", "email": "p@x.com"}, path="ws-evil")
    live = _FakeLive([_grant("ws-a", "p@x.com", "oid-p")])
    with pytest.raises(CrossWorkspaceError, match="not an active member"):
        _run(A.enforce_workspace_from_context(live, "ws-evil"))


def test_conflicting_path_and_arg_denied(monkeypatch):
    _patch(monkeypatch, claims={"oid": "oid-p", "email": "p@x.com"}, path="ws-a")
    live = _FakeLive([_grant("ws-a", "p@x.com", "oid-p")])
    with pytest.raises(A.CrossTenantError, match="conflicting workspace selectors"):
        _run(A.enforce_workspace_from_context(live, "ws-b"))
