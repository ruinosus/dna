"""Decision B — a workspace reaches a second scope through a ROW, not a rule.

``scope_is_bound`` allowed an authenticated, workspace-resolved caller exactly
``default_scope(workspace)``. That is the right default and it stays the default;
what it made unreachable is the legitimate case of one person whose hosted door
binds them to workspace A while board B is also theirs. The only lever was a
process-wide env var applying to the CREDENTIAL, not the workspace.

The permission is now data, and the two properties that matter are tested here:

1. **Nothing is derived.** The binder checks MEMBERSHIP against the rows — no
   prefix rule, no "same account" inference, no wildcard. A leak therefore has to
   be a row somebody wrote, which can be listed, diffed and revoked; not a rule
   nobody can see.
2. **No grant = today, exactly.** A deployment that writes no rows behaves
   byte-for-byte as it did.
"""
from __future__ import annotations

import pytest

from dna.application.live import SCOPE_GRANT_ALL, LiveDna
from dna.application.runtime import (
    grant_workspace_scope_impl,
    list_workspace_scope_grants_impl,
    revoke_workspace_scope_impl,
    workspace_granted_scopes,
)


class _Kernel:
    """The narrow kernel surface the grant impls touch."""

    def __init__(self, docs=None, fail_query=False):
        self.docs: dict[str, dict] = dict(docs or {})
        self.fail_query = fail_query

    async def query(self, scope, kind, **kw):
        if self.fail_query:
            raise RuntimeError("_lib is unreadable")
        for raw in list(self.docs.values()):
            if raw.get("kind") == kind:
                yield raw

    async def get_document(self, scope, kind, name):
        return self.docs.get(name)

    async def write_document(self, scope, kind, name, raw, **kw):
        self.docs[name] = raw


def _live(kernel):
    return LiveDna(
        base_scope="dna-development", kernel=kernel, provider=None,
        vendor_workspace="ws-vendor",
    )


# ── the binder: membership, never derivation ────────────────────────────────


def test_without_a_grant_a_workspace_reaches_only_its_own_scope():
    live = _live(_Kernel())
    assert live.scope_is_bound("tenant-ws-a", "ws-a", authenticated=True) is True
    assert live.scope_is_bound("tenant-ws-b", "ws-a", authenticated=True) is False
    assert live.scope_is_bound("dna-development", "ws-a", authenticated=True) is False


def test_a_grant_opens_exactly_the_scope_it_names():
    live = _live(_Kernel())
    granted = frozenset({"dna-development"})
    assert live.scope_is_bound(
        "dna-development", "ws-a", authenticated=True, granted_scopes=granted,
    ) is True
    # ...and nothing else. Not a sibling, not a prefix, not the vendor's.
    assert live.scope_is_bound(
        "dna-development-staging", "ws-a", authenticated=True,
        granted_scopes=granted,
    ) is False
    assert live.scope_is_bound(
        "tenant-ws-b", "ws-a", authenticated=True, granted_scopes=granted,
    ) is False


def test_the_wildcard_sentinel_is_not_honoured_for_a_workspace():
    """``*`` is an operator's process-level opt-out for a workspace-LESS service
    credential. In a per-workspace DATA row it would put an unbounded reach one
    typo away, so this path treats it as a scope literally named ``*``."""
    live = _live(_Kernel())
    assert live.scope_is_bound(
        "some-other-scope", "ws-a", authenticated=True,
        granted_scopes=frozenset({SCOPE_GRANT_ALL}),
    ) is False
    # The workspace-LESS regime still honours it — that behavior is unchanged.
    assert live.scope_is_bound(
        "some-other-scope", None, authenticated=True,
        granted_scopes=frozenset({SCOPE_GRANT_ALL}),
    ) is True


def test_an_unauthenticated_caller_is_unaffected():
    live = _live(_Kernel())
    assert live.scope_is_bound("anything", "ws-a", authenticated=False) is True


# ── the rows ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_grant_then_read_then_revoke():
    live = _live(_Kernel())
    assert await workspace_granted_scopes(live, "ws-a") == frozenset()

    out = await grant_workspace_scope_impl(
        live, workspace_id="ws-a", scope="dna-development",
        reason="the founder's own board", granted_by="founder@example.test",
    )
    assert out["status"] == "active"
    assert await workspace_granted_scopes(live, "ws-a") == frozenset(
        {"dna-development"}
    )
    # ...and it grants NOBODY else.
    assert await workspace_granted_scopes(live, "ws-b") == frozenset()

    await revoke_workspace_scope_impl(
        live, workspace_id="ws-a", scope="dna-development")
    assert await workspace_granted_scopes(live, "ws-a") == frozenset()

    # The row SURVIVES the revoke — the evidence that access once existed is
    # the half of an audit trail that matters after an incident.
    listing = await list_workspace_scope_grants_impl(live, workspace_id="ws-a")
    assert listing["count"] == 1
    assert listing["grants"][0]["status"] == "revoked"
    assert listing["grants"][0]["revoked_at"]
    assert listing["grants"][0]["reason"] == "the founder's own board"


@pytest.mark.asyncio
async def test_granting_the_wildcard_is_refused_by_name():
    live = _live(_Kernel())
    with pytest.raises(ValueError, match="not a grantable scope"):
        await grant_workspace_scope_impl(
            live, workspace_id="ws-a", scope=SCOPE_GRANT_ALL)


@pytest.mark.asyncio
async def test_granting_a_workspace_its_own_scope_is_refused():
    """A row recording a permission nothing consults is noise in the audit."""
    live = _live(_Kernel())
    with pytest.raises(ValueError, match="already reaches"):
        await grant_workspace_scope_impl(
            live, workspace_id="ws-a", scope="tenant-ws-a")


@pytest.mark.asyncio
async def test_revoking_a_grant_that_never_existed_says_so():
    live = _live(_Kernel())
    with pytest.raises(LookupError, match="never"):
        await revoke_workspace_scope_impl(
            live, workspace_id="ws-a", scope="somewhere")


@pytest.mark.asyncio
async def test_an_unreadable_grant_store_grants_nothing():
    """Fail CLOSED: a grant that cannot be read is not a grant. The caller still
    has its own scope, so nothing is lost by refusing to guess."""
    live = _live(_Kernel(fail_query=True))
    assert await workspace_granted_scopes(live, "ws-a") == frozenset()


@pytest.mark.asyncio
async def test_end_to_end_the_grant_is_what_flips_the_binder():
    """THE proof: same call, denied then allowed, with one row in between."""
    live = _live(_Kernel())
    assert live.scope_is_bound(
        "dna-development", "ws-a", authenticated=True,
        granted_scopes=await workspace_granted_scopes(live, "ws-a"),
    ) is False

    await grant_workspace_scope_impl(
        live, workspace_id="ws-a", scope="dna-development")

    assert live.scope_is_bound(
        "dna-development", "ws-a", authenticated=True,
        granted_scopes=await workspace_granted_scopes(live, "ws-a"),
    ) is True
