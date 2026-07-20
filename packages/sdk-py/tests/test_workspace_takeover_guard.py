"""The ANTI-TAKEOVER property of workspace owner-bootstrap, pinned on its own.

Why this file exists (and why it is not folded into
``packages/cli/tests/test_workspace_owner_rest.py``):

``assert_may_bootstrap_workspace`` used to enforce two rules through a single
equality (``identity.tid == workspace_id``). One of them — zero-migration — was
REMOVED by product decision **D5** (a workspace gets its own generated id;
``tid`` becomes a mere fact of authentication). The other — anti-takeover — had
to survive that change untouched.

**It did. D5 has now landed, and this file is the receipt.** Every assertion
below is byte-identical to what it was before the change; only the SETUP moved,
from "the caller's tid" to "the caller's memberships". That is exactly the
contract the original header demanded:

* **in a separate file**, so a rewrite of the zero-migration tests cannot take
  them along by accident;
* **unit-level**, calling the guard directly — no FastAPI, no fixture, nothing
  that a REST refactor can move out from under them;
* **phrased as security properties, not as mechanism.** Each assertion states
  what must remain true of the SYSTEM. D5 changed *how* the guard decides; it
  did not change *these answers*. A test here that needs its assertion (not
  merely its setup) rewritten is a signal that D5 opened a hole.

The post-D5 rule the guard implements: **you may bootstrap a workspace iff you
already hold an ACTIVE membership in it.** Creation is a separate, explicit act
(``create_workspace_impl``) that mints the id server-side — so there is no
unclaimed-but-nameable id left to race for. Takeover is now prevented by
construction; this file proves the *denial* half still answers the same way.
"""
from __future__ import annotations

import pytest

from dna.application.runtime import (
    WorkspaceForbidden,
    assert_may_bootstrap_workspace,
)
from dna.tenancy import Identity, Membership

_WS = "ws-legitimate-owner"


def _grant(workspace_id: str, *, oid: str, email: str, status: str = "active",
           role: str = "owner") -> Membership:
    return Membership(
        workspace_id=workspace_id,
        identity_email=email,
        identity_oid=oid,
        role=role,
        status=status,
    )


_OWNER = Identity(oid="oid-owner", email="owner@org.com", tid="org-legit")
_OWNER_GRANTS = [_grant(_WS, oid="oid-owner", email="owner@org.com")]


# ── the legitimate path (so the denials below are not vacuous) ──────────────


def test_the_entitled_caller_is_allowed_through():
    """Baseline. Without this, every denial test could pass on a guard that
    denies EVERYTHING — the classic vacuous-security-test failure.

    Post-D5 setup: entitlement is an ACTIVE membership, not a tid. Note the
    owner's ``tid`` is now deliberately DIFFERENT from the workspace id — the
    happy path must not secretly still depend on the old equality."""
    assert_may_bootstrap_workspace(_OWNER, _WS, _OWNER_GRANTS)


# ── SECURITY: these answers must survive D5 ─────────────────────────────────


def test_a_stranger_cannot_claim_a_workspace_that_is_not_theirs():
    """THE property. A verified identity from another org must never seize a
    workspace by racing its legitimate owner to the bootstrap.

    If D5 makes this test pass only after you weaken the assertion, D5 opened a
    takeover hole. The setup may change (a generated id is not a ``tid``); the
    answer — 403 — may not."""
    attacker = Identity(oid="oid-evil", email="evil@evil.com", tid="org-evil")
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(attacker, _WS, _OWNER_GRANTS)


def test_an_identity_with_no_tenant_provenance_is_denied():
    """Fail-CLOSED on a missing claim. An identity that carries no ``tid`` at all
    must not fall through to 'allowed' — absence of evidence is not entitlement.

    Under D5 the analogue is an identity carrying no membership and no creation
    intent; the answer stays 403."""
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(
            Identity(oid="oid-x", email="x@org.com", tid=None), _WS, _OWNER_GRANTS
        )


def test_an_empty_tenant_claim_is_denied_not_treated_as_wildcard():
    """An empty string is a common way for a claim to arrive 'present but
    useless'. It must be denied, never treated as 'matches anything'."""
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(
            Identity(oid="oid-x", email="x@org.com", tid=""), _WS, _OWNER_GRANTS
        )


def test_no_memberships_at_all_is_denied_fail_closed():
    """The guard's DEFAULT must deny. A caller (or a future refactor) that omits
    the memberships argument entirely must not be waved through — absence of
    evidence is not entitlement, and a fail-OPEN default here would be a
    one-argument takeover."""
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(_OWNER, _WS)
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(_OWNER, _WS, [])


def test_a_pending_invite_does_not_entitle_bootstrap():
    """Post-D5 the entitlement is an ACTIVE grant. A ``pending`` invite — the
    state anyone can be put into by an unrelated workspace's admin — must not
    authorize a bootstrap. Fail-closed on lifecycle, not just on identity."""
    invitee = Identity(oid="oid-inv", email="inv@org.com", tid="org-x")
    pending = [_grant(_WS, oid=None, email="inv@org.com", status="pending")]
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(invitee, _WS, pending)


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
    normalization cannot land quietly.

    Post-D5 the compared value moved — it is now the membership's
    ``workspace_id``, not the caller's ``tid``. So the attacker here is a
    legitimate owner OF A DIFFERENT, near-identically-named workspace. Same
    exact-match requirement, same answer."""
    attacker = Identity(oid="oid-evil", email="evil@evil.com", tid="org-evil")
    neighbour = [_grant(near_miss, oid="oid-evil", email="evil@evil.com")]
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(attacker, _WS, neighbour)


def test_denial_names_the_caller_not_just_the_target():
    """The 403 must be diagnosable. An operator reading the log needs to see
    WHOSE request was rejected, not only which workspace was defended.

    (The caller's ``tid`` is still printed — as provenance. It is reported and
    never consulted; that distinction is the whole of D5.)"""
    attacker = Identity(oid="oid-evil", email="evil@evil.com", tid="org-evil")
    with pytest.raises(WorkspaceForbidden) as exc:
        assert_may_bootstrap_workspace(attacker, _WS, _OWNER_GRANTS)
    assert "org-evil" in str(exc.value)
    assert _WS in str(exc.value)


# ── D5: the guard no longer couples entitlement to `tid` ────────────────────
#
# The old ``test_d5_tripwire_the_guard_still_couples_identity_to_tid`` lived here
# and asserted the very thing D5 removes. It was marked "delete this test as part
# of the D5 change" and has been deleted. What replaces it is its INVERSE: proof
# that the coupling is really gone, so it cannot creep back in.


def test_entitlement_ignores_tid_entirely():
    """The D5 property, stated positively.

    A matching ``tid`` grants NOTHING (top half) and a mismatched ``tid`` costs
    NOTHING (bottom half). If someone re-introduces a tid comparison "as a belt
    and braces", one of these two halves goes red."""
    # tid == the workspace id, but no membership → still denied. The old guard
    # would have ALLOWED this; that is precisely the rule that died.
    tid_matcher = Identity(oid="oid-a", email="a@org.com", tid=_WS)
    with pytest.raises(WorkspaceForbidden):
        assert_may_bootstrap_workspace(tid_matcher, _WS, _OWNER_GRANTS)

    # tid completely unrelated (and absent), but an active membership → allowed.
    # The old guard would have DENIED this; cross-org owners are the point of
    # Model B.
    for tid in ("some-other-azure-org", None, ""):
        member = Identity(oid="oid-owner", email="owner@org.com", tid=tid)
        assert_may_bootstrap_workspace(member, _WS, _OWNER_GRANTS)
