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


# ── the CONSUMER lane reaches the resolver at all (i-072) ──────────────────
#
# The glue's own half of the bug: `identity_from_context()` called
# `identity_from_token(claims)` with no provider context, so a WorkOS/AuthKit
# access token (durable subject in `sub`, no `oid`, no `email`) arrived at the
# resolver as Identity(oid=None, email=None) and EVERY metered tool call on that
# door was denied. These tests drive the REAL `identity_from_context` (not the
# stub `_patch_token` installs) over a fake FastMCP token.

#: A WorkOS/AuthKit ACCESS token as issued — plus the family stamp the composite
#: verifier (and `workos_provider_from_env`) writes onto the verified claims.
_AUTHKIT_CLAIMS = {
    "iss": "https://api.workos.com/user_management/client_x",
    "sub": "user_01JQGLUEWORKOSUSER",
    "org_id": "org_01JQGLUE",
    "sid": "session_01JQGLUE",
    "_dna_provider_family": "workos",
}


class _FakeToken:
    def __init__(self, claims: dict):
        self.claims = claims


@pytest.fixture
def patch_access_token(monkeypatch):
    """Install a fake ``get_access_token`` (the REAL identity_from_context runs)."""
    import fastmcp.server.dependencies as deps

    def _install(claims: dict | None):
        monkeypatch.setattr(
            deps, "get_access_token",
            lambda: (None if claims is None else _FakeToken(claims)),
        )
    return _install


def test_identity_from_context_reads_the_consumer_lane_subject(patch_access_token):
    patch_access_token(_AUTHKIT_CLAIMS)
    ident = A.identity_from_context()
    assert ident.oid == "user_01JQGLUEWORKOSUSER"
    assert ident.email is None  # an access token carries none — and needs none.


def test_identity_from_context_entra_is_unchanged(patch_access_token):
    patch_access_token({"oid": "oid-alice", "email": "alice@a.com", "tid": "org-a",
                        "sub": "pairwise-and-ignored"})
    ident = A.identity_from_context()
    assert (ident.oid, ident.email, ident.tid) == ("oid-alice", "alice@a.com", "org-a")


def test_identity_from_context_no_token(patch_access_token):
    patch_access_token(None)
    assert A.identity_from_context() is None


def test_consumer_lane_resolves_its_workspace_end_to_end(
    monkeypatch, patch_access_token
):
    """The whole seam every metered tool passes through (`_guard` → `_workspace`
    → `enforce_workspace_from_context`), with a real WorkOS token."""
    monkeypatch.setattr(A, "token_present_in_context", lambda: True)
    monkeypatch.setattr(A, "workspace_selector_from_context", lambda: None)
    patch_access_token(_AUTHKIT_CLAIMS)
    grants = [
        {"spec": {"workspace_id": "ws-consumer",
                  "identity_email": "consumer@example.com",
                  "identity_oid": "user_01JQGLUEWORKOSUSER",
                  "role": "owner", "status": "active"}},
    ]
    assert _run(A.enforce_workspace_from_context(_FakeLive(grants), None)) == "ws-consumer"


def test_consumer_lane_still_denies_a_stranger(monkeypatch, patch_access_token):
    from dna.tenancy.resolution import CrossWorkspaceError

    monkeypatch.setattr(A, "token_present_in_context", lambda: True)
    monkeypatch.setattr(A, "workspace_selector_from_context", lambda: None)
    patch_access_token(_AUTHKIT_CLAIMS)
    grants = [
        {"spec": {"workspace_id": "ws-a", "identity_email": "alice@a.com",
                  "identity_oid": "user_SOMEONE_ELSE", "role": "owner",
                  "status": "active"}},
    ]
    with pytest.raises(CrossWorkspaceError, match="no active workspace membership"):
        _run(A.enforce_workspace_from_context(_FakeLive(grants), None))
