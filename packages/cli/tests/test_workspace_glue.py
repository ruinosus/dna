"""Story ``s-ws-res-mcp-auth`` — the FastMCP+kernel GLUE around the pure resolver
(``dna_cli._mcp_auth.enforce_workspace_from_context`` / ``identity_from_context``).

The pure policy is proven in ``sdk-py/tests/test_workspace_resolution.py`` (+ the
TS twin). Here we prove the WIRING: no token → passthrough; a token but a source
with NO WorkspaceMembership grants → the LEGACY tid tenancy (OSS / pre-Model-B
unchanged); a token + configured grants → the membership resolution engages
(and the tid stops being the key). We stub the FastMCP token + the kernel's
``workspace_memberships`` so the glue is unit-testable with no server.
"""
from __future__ import annotations

import asyncio

import pytest

from dna_cli import _mcp_auth as A


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


def _patch_token(monkeypatch, present: bool, claims: dict | None = None):
    """Stub ``token_present_in_context`` + ``identity_from_context`` so the glue
    sees a synthetic token (no fastmcp needed)."""
    monkeypatch.setattr(A, "token_present_in_context", lambda: present)
    if present:
        from dna.tenancy.resolution import identity_from_token
        monkeypatch.setattr(
            A, "identity_from_context", lambda: identity_from_token(claims or {})
        )
    else:
        monkeypatch.setattr(A, "identity_from_context", lambda: None)


def test_no_token_passthrough(monkeypatch):
    _patch_token(monkeypatch, present=False)
    live = _FakeLive(grants=[])
    assert _run(A.enforce_workspace_from_context(live, "whatever")) == "whatever"
    assert _run(A.enforce_workspace_from_context(live, None)) is None


def test_no_grants_falls_back_to_legacy_tid(monkeypatch):
    """Token present but the source configured NO WorkspaceMembership grants →
    the legacy tid tenancy runs unchanged (we stub enforce_tenant_from_context to
    prove it is the path taken)."""
    _patch_token(monkeypatch, present=True, claims={"oid": "o1", "email": "a@x.com"})
    called = {}

    def _legacy(requested):
        called["requested"] = requested
        return "legacy-tenant"

    monkeypatch.setattr(A, "enforce_tenant_from_context", _legacy)
    live = _FakeLive(grants=[])  # nothing configured → OSS / pre-Model-B.
    assert _run(A.enforce_workspace_from_context(live, "req")) == "legacy-tenant"
    assert called["requested"] == "req"


def test_configured_grants_engage_membership_resolution(monkeypatch):
    """With grants configured, resolution is by MEMBERSHIP — the tid is ignored.
    The token's tid says 'org-evil' but alice's active grant puts her in ws-a."""
    _patch_token(
        monkeypatch, present=True,
        claims={"oid": "oid-alice", "email": "alice@a.com", "tid": "org-evil"},
    )
    # If the legacy path were taken it would return the tid — assert it is NOT.
    monkeypatch.setattr(A, "enforce_tenant_from_context", lambda r: "org-evil")
    grants = [
        {"spec": {"workspace_id": "ws-a", "identity_email": "alice@a.com",
                  "identity_oid": "oid-alice", "role": "owner", "status": "active"}},
    ]
    live = _FakeLive(grants=grants)
    assert _run(A.enforce_workspace_from_context(live, None)) == "ws-a"


def test_configured_grants_deny_non_member(monkeypatch):
    from dna.tenancy.resolution import CrossWorkspaceError

    _patch_token(
        monkeypatch, present=True,
        claims={"oid": "oid-nobody", "email": "nobody@x.com"},
    )
    grants = [
        {"spec": {"workspace_id": "ws-a", "identity_email": "alice@a.com",
                  "identity_oid": "oid-alice", "role": "owner", "status": "active"}},
    ]
    live = _FakeLive(grants=grants)
    with pytest.raises(CrossWorkspaceError, match="no active workspace membership"):
        _run(A.enforce_workspace_from_context(live, None))
