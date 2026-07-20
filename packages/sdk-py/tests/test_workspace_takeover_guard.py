"""The ANTI-TAKEOVER property of workspace owner-bootstrap, pinned on its own.

Why this file exists (and why it is not folded into
``packages/cli/tests/test_workspace_owner_rest.py``):

``assert_may_bootstrap_workspace`` enforces two rules through a single equality
(``identity.tid == workspace_id``). One of them — zero-migration — is scheduled
to be REMOVED by product decision **D5** (a workspace gets its own generated id;
``tid`` becomes a mere fact of authentication). The other — anti-takeover — must
survive that change untouched.

Before this module, the only coverage of the guard's DENIAL branch in the whole
repo was ``test_workspace_owner_rest.py::test_provision_cross_tid_is_forbidden``,
sitting **25 lines** from ``test_provision_zero_migration_workspace_id_equals_tid``
— a test D5 *requires* someone to delete. Rewriting that file wholesale (the
natural way to do the D5 work) would have taken the takeover protection with it
and nothing would have gone red.

So these tests are deliberately:

* **in a separate file**, so a rewrite of the zero-migration tests cannot take
  them along by accident;
* **unit-level**, calling the guard directly — no FastAPI, no fixture, nothing
  that a REST refactor can move out from under them;
* **phrased as security properties, not as mechanism.** Each assertion states
  what must remain true of the SYSTEM. D5 will change *how* the guard decides;
  it must not change *these answers*. A test here that needs its assertion (not
  merely its setup) rewritten is a signal that D5 opened a hole.
"""
from __future__ import annotations

import pytest

from dna.application.runtime import (
    WorkspaceForbidden,
    assert_may_bootstrap_workspace,
)
from dna.tenancy import Identity

_WS = "ws-legitimate-owner"


# ── the legitimate path (so the denials below are not vacuous) ──────────────


def test_the_entitled_caller_is_allowed_through():
    """Baseline. Without this, every denial test could pass on a guard that
    denies EVERYTHING — the classic vacuous-security-test failure."""
    assert_may_bootstrap_workspace(
        Identity(oid="oid-owner", email="owner@org.com", tid=_WS), _WS
    )


# ── SECURITY: these answers must survive D5 ─────────────────────────────────


def test_a_stranger_cannot_claim_a_workspace_that_is_not_theirs():
    """THE property. A verified identity from another org must never seize a
    workspace by racing its legitimate owner to the bootstrap.

    If D5 makes this test pass only after you weaken the assertion, D5 opened a
    takeover hole. The setup may change (a generated id is not a ``tid``); the
    answer — 403 — may not."""
    attacker = Identity(oid="oid-evil", email="evil@evil.com", tid="org-evil")
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(attacker, _WS)


def test_an_identity_with_no_tenant_provenance_is_denied():
    """Fail-CLOSED on a missing claim. An identity that carries no ``tid`` at all
    must not fall through to 'allowed' — absence of evidence is not entitlement.

    Under D5 the analogue is an identity carrying no membership and no creation
    intent; the answer stays 403."""
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(
            Identity(oid="oid-x", email="x@org.com", tid=None), _WS
        )


def test_an_empty_tenant_claim_is_denied_not_treated_as_wildcard():
    """An empty string is a common way for a claim to arrive 'present but
    useless'. It must be denied, never treated as 'matches anything'."""
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(
            Identity(oid="oid-x", email="x@org.com", tid=""), _WS
        )


@pytest.mark.parametrize(
    "near_miss",
    [
        _WS + "-extra",          # suffix
        "prefix-" + _WS,         # prefix
        _WS[:-1],                # truncation
        _WS.upper(),             # case
        " " + _WS,               # leading whitespace
        _WS + " ",               # trailing whitespace
    ],
    ids=["suffix", "prefix", "truncated", "case", "lead-space", "trail-space"],
)
def test_matching_is_exact_and_near_misses_are_denied(near_miss):
    """No substring, prefix, case-insensitive or whitespace-tolerant matching.

    Each of these is a real-world way a loose comparison gets introduced (a
    ``startswith``, a ``.lower()``, a forgotten ``.strip()``), and each would
    turn the guard into a takeover vector. Pinned so a future 'lenient'
    normalization cannot land quietly."""
    attacker = Identity(oid="oid-evil", email="evil@evil.com", tid=near_miss)
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(attacker, _WS)


def test_denial_names_the_caller_not_just_the_target():
    """The 403 must be diagnosable. An operator reading the log needs to see
    WHOSE tid was rejected, not only which workspace was defended."""
    attacker = Identity(oid="oid-evil", email="evil@evil.com", tid="org-evil")
    with pytest.raises(WorkspaceForbidden) as exc:
        assert_may_bootstrap_workspace(attacker, _WS)
    assert "org-evil" in str(exc.value)
    assert _WS in str(exc.value)


# ── the D5 tripwire ─────────────────────────────────────────────────────────


def test_d5_tripwire_the_guard_still_couples_identity_to_tid():
    """DELIBERATE DETECTOR — this one is SUPPOSED to fail when D5 lands.

    It asserts the thing D5 removes: that entitlement is decided by ``tid``
    equality. When you make workspaces carry generated ids, this test breaks —
    and that break is your reminder to go re-read
    ``assert_may_bootstrap_workspace``'s docstring and give Rule 2 (anti-takeover)
    an implementation of its OWN, rather than deleting it along with Rule 1.

    Delete this test as part of the D5 change. Do NOT delete the tests above it."""
    legit = Identity(oid="oid-owner", email="owner@org.com", tid=_WS)
    assert_may_bootstrap_workspace(legit, _WS)

    # The same identity cannot bootstrap a DIFFERENT workspace — today because
    # entitlement IS tid equality, not because of any membership check.
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(legit, "ws-some-other-generated-id")
