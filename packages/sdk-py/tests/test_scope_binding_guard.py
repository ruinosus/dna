"""The FAIL-CLOSED property of scope binding, pinned on its own (issue ``i-034``).

Why this file exists (and why it is not folded into
``packages/cli/tests/test_workspace_scope.py``):

``LiveDna.scope_is_bound`` used to answer a single question — "does this
*resolved workspace* name its own scope?" — and returned ``True`` for everything
else, including the case where NO workspace was resolved at all. That made the
caller with the *least* proven right to any scope the only caller that skipped
the check entirely. Absence of evidence had become a right.

Issue ``i-028`` shipped the workspace half and was closed suggesting the
isolation was general; ``i-034`` recorded that it was not — the REST path the
portal actually uses (a shared SERVICE token, which resolves no workspace) was
never bound. This file pins the corrected rule so a future refactor cannot quietly
restore the fail-open:

* **in a separate file**, so a rewrite of the workspace-scope tests cannot take
  these along by accident;
* **unit-level**, calling the policy directly — no FastAPI, no fixture, nothing
  a face refactor can move out from under them;
* **phrased as security properties, not as mechanism.** Each assertion states
  what must remain true of the SYSTEM: *a credential reaches a scope only when
  something affirmatively grants it that scope.*

The rule the policy implements, in one line: **an authenticated caller is bound
— by its workspace if it resolved one, by its token's explicit grant if it did
not. Only an UNauthenticated (stdio / local / OSS self-host) caller is free**,
because there is no tenancy for it to be bound to. That last clause is not a
loophole, it is the open-core promise, and it has its own tests below.
"""
from __future__ import annotations

import pytest

from dna.application.live import SCOPE_GRANT_ALL, LiveDna, parse_scope_grants

_VENDOR = "ws-vendor"
_BASE = "dna-development"


def _live(vendor: str | None = _VENDOR) -> LiveDna:
    return LiveDna(
        base_scope=_BASE, kernel=None, provider=None, vendor_workspace=vendor
    )


# ── the legitimate paths (so the denials below are not vacuous) ─────────────


def test_the_entitled_callers_are_allowed_through():
    """Baseline. Without this, every denial below could pass on a policy that
    denies EVERYTHING — the classic vacuous-security-test failure.

    Four distinct ways to legitimately reach a scope, one per regime:
    """
    live = _live()
    # 1. naming no scope at all → resolves to the (workspace-bound) default.
    assert live.scope_is_bound(None, "ws-acme", authenticated=True) is True
    # 2. a resolved workspace naming its OWN scope.
    assert live.scope_is_bound("tenant-ws-acme", "ws-acme", authenticated=True) is True
    # 3. a workspace-less credential naming a scope EXPLICITLY granted to it.
    assert live.scope_is_bound(
        "other-scope", None, authenticated=True, granted_scopes={"other-scope"}
    ) is True
    # 4. an unauthenticated local caller — the OSS path, never capped.
    assert live.scope_is_bound("anything-at-all", None) is True


# ── SECURITY: absence of a workspace must not be a right (i-034) ────────────


def test_a_workspaceless_credential_cannot_reach_an_arbitrary_scope():
    """THE property, and the exact hole ``i-034`` reported.

    A caller that authenticated but resolved NO workspace (the portal's shared
    service token; an authenticated request on a source that configured no
    workspaces) must not thereby reach any scope it likes. Before the fix this
    returned ``True`` — not because anything granted the scope, but because there
    was no workspace to compare against.

    If this test needs its ASSERTION (not merely its setup) relaxed, the
    fail-open is back."""
    live = _live()
    assert live.scope_is_bound(
        "someone-elses-scope", None, authenticated=True
    ) is False


def test_a_workspaceless_credential_defaults_to_its_own_server_scope_only():
    """The fallback when nothing is granted must be the NARROWEST useful answer —
    the one scope the server was booted on — never 'everything'.

    A default of 'everything' is how a fail-open gets re-introduced while looking
    like a convenience."""
    live = _live()
    assert live.scope_is_bound(_BASE, None, authenticated=True) is True
    assert live.scope_is_bound("any-other", None, authenticated=True) is False


@pytest.mark.parametrize(
    "empty_grant", [None, set(), frozenset(), [], ()],
    ids=["none", "empty-set", "empty-frozenset", "empty-list", "empty-tuple"],
)
def test_an_empty_grant_is_denial_not_a_wildcard(empty_grant):
    """An empty/absent grant is a common way for config to arrive 'present but
    useless' (an unset env var, a stripped list, a typo'd key). Every one of these
    must mean 'nothing was granted', never 'no restriction configured, so allow'.

    This is the single most likely way for the i-034 fail-open to return: a
    falsy-config check written as `if grants and requested not in grants`."""
    live = _live()
    assert live.scope_is_bound(
        "unrelated-scope", None, authenticated=True, granted_scopes=empty_grant
    ) is False


def test_multiworkspace_off_does_not_excuse_a_workspaceless_credential():
    """Isolation must not be contingent on multi-workspace being switched ON.

    ``vendor_workspace`` unset is the single-tenant/OSS *storage* model; it says
    nothing about whether a SERVICE credential should roam. A policy that reads
    `not self.vendor_workspace → allow` up front re-opens the hole for every
    deployment that has not adopted Model B yet — which, per i-034, is exactly the
    deployment that was exposed."""
    live = _live(vendor=None)
    assert live.scope_is_bound("any-other", None, authenticated=True) is False


@pytest.mark.parametrize(
    "near_miss",
    [
        "granted-scope-extra",   # suffix
        "x-granted-scope",       # prefix
        "granted-scop",          # truncation
        "GRANTED-SCOPE",         # case
        " granted-scope",        # leading whitespace
        "granted-scope ",        # trailing whitespace
    ],
    ids=["suffix", "prefix", "truncated", "case", "lead-space", "trail-space"],
)
def test_grant_matching_is_exact_and_near_misses_are_denied(near_miss):
    """No substring, prefix, case-insensitive or whitespace-tolerant matching on
    the grant list.

    Each of these is a real way a loose comparison gets introduced (a
    ``startswith`` so `acme-*` "just works", a ``.lower()``, a forgotten
    ``.strip()``), and each turns an explicit grant into a wildcard for a whole
    family of neighbouring scopes."""
    live = _live()
    assert live.scope_is_bound(
        near_miss, None, authenticated=True, granted_scopes={"granted-scope"}
    ) is False


def test_the_wildcard_optout_must_be_written_out_and_nothing_else_implies_it():
    """Unrestricted access must remain something an operator TYPED.

    The sentinel works (top half) — an operator who consciously needs a
    multi-scope service credential is not blocked. But nothing else may be
    silently equivalent to it: not an empty grant, not a blank string, not the
    other characters an operator might reach for."""
    live = _live()
    assert live.scope_is_bound(
        "anything", None, authenticated=True, granted_scopes={SCOPE_GRANT_ALL}
    ) is True
    for not_a_wildcard in ("", "all", "ALL", "any", "**", "%", "*.*", ".*"):
        assert live.scope_is_bound(
            "anything", None, authenticated=True, granted_scopes={not_a_wildcard}
        ) is False, f"{not_a_wildcard!r} must not act as a wildcard"


# ── SECURITY: the workspace half must keep answering as it did (i-028) ──────


def test_a_resolved_workspace_still_cannot_read_another_workspaces_scope():
    """The i-028 property, unchanged. The fix for i-034 must not be a rewrite
    that loses the rule it was extending."""
    live = _live()
    assert live.scope_is_bound(
        "tenant-ws-globex", "ws-acme", authenticated=True
    ) is False
    assert live.scope_is_bound(_BASE, "ws-acme", authenticated=True) is False


def test_a_workspace_grant_is_not_widened_by_the_token_grant():
    """The two binders must not be an OR.

    A caller that DID resolve a workspace is bound by that workspace, full stop —
    a permissive service-token grant sitting in the environment must not become a
    back door that lets a resolved workspace read another's data. This is the
    composition bug the two-mechanism design invites."""
    live = _live()
    assert live.scope_is_bound(
        "tenant-ws-globex", "ws-acme",
        authenticated=True, granted_scopes={SCOPE_GRANT_ALL, "tenant-ws-globex"},
    ) is False


# ── OPEN CORE: the unauthenticated self-host path is never capped ───────────


def test_the_unauthenticated_local_caller_is_never_bound():
    """The open-core hard rule: ``dna`` running locally with no token at all —
    stdio, ``--auth none``, the OSS self-host — must reach any scope in its own
    source. It has no credential, no workspace and no tenancy; there is nothing
    for a binding rule to be *about*.

    This is the case that makes ``authenticated`` (rather than 'is a workspace
    present') the right axis. A fix that fails closed here would cap the kernel,
    which this project does not do."""
    for live in (_live(), _live(vendor=None)):
        for requested in (None, _BASE, "some-other-scope", "tenant-ws-globex"):
            assert live.scope_is_bound(requested, None) is True
            assert live.scope_is_bound(requested, None, authenticated=False) is True


def test_authentication_not_workspace_presence_is_what_binds():
    """Stated positively, so the axis cannot drift back.

    The SAME (scope, workspace=None) pair answers differently depending only on
    whether a credential was presented. If someone re-derives the decision from
    workspace presence 'to simplify', one of these two halves goes red."""
    live = _live()
    assert live.scope_is_bound("roam", None, authenticated=False) is True
    assert live.scope_is_bound("roam", None, authenticated=True) is False


# ── the grant parser: config must not decay into a wildcard ─────────────────


def test_blank_config_parses_to_nothing_granted_not_to_everything():
    """An unset / blank / whitespace-only env var must produce 'nothing granted'
    (which the policy reads as fail-closed), never a permissive empty-means-all."""
    for raw in (None, "", "   ", ",", " , , "):
        assert parse_scope_grants(raw) is None


def test_grant_config_parses_exactly_and_tolerantly_only_about_whitespace():
    """Operator-friendly about formatting, never about membership."""
    assert parse_scope_grants("a, b ,c") == frozenset({"a", "b", "c"})
    assert parse_scope_grants("solo") == frozenset({"solo"})
    assert parse_scope_grants(SCOPE_GRANT_ALL) == frozenset({SCOPE_GRANT_ALL})
