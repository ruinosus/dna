"""``workspace_membership_name`` — the name IS the uniqueness key.

Found in production, 2026-07-29: one human holding TWO active ``owner`` grants
in one workspace. One named from their email, one named ``…--workos-user-01kx…``
— built from an ACCOUNT id (``workos-user:<sub>``) instead.

Nothing complained when it happened, because a wrong handle does not fail a
write: it produces a DIFFERENT name, and a different name is a different
instance. The design's own promise — "an invite, a re-invite and the accept-bind
all converge on the ONE doc, never a duplicate" — stopped being true silently.

The cost surfaced far from the cause. Revoking that person removed one grant
and left the other, so "removed" removed nothing and the UI said it worked.

These tests pin the refusal, so the next such caller fails where the stack
still names it.
"""
from __future__ import annotations

import pytest

from dna.tenancy import workspace_membership_name


def test_an_email_composes_the_documented_key():
    assert workspace_membership_name("ws-1", "Alice@Acme.com") == "ws-1--alice-at-acme-com"


def test_the_same_identity_always_converges_on_one_name():
    """The property the whole design rests on: invite, re-invite and
    accept-bind must all address the SAME instance."""
    a = workspace_membership_name("ws-1", "alice@acme.com")
    b = workspace_membership_name("ws-1", "  ALICE@acme.com  ")
    assert a == b


@pytest.mark.parametrize(
    "handle",
    [
        "user_01KXV762MWW3J7X90A36PQ5DV0",   # a WorkOS subject
        "workos-user:user_01KXV762",         # the account-namespace form
        "oid-1234",
        "",
        "   ",
    ],
)
def test_a_handle_that_is_not_an_email_is_refused(handle):
    """Remove the guard and this dies — and production regains a path that
    mints a parallel grant instead of reporting a bug."""
    with pytest.raises(ValueError, match="expects an EMAIL"):
        workspace_membership_name("ws-1", handle)


def test_the_refusal_says_WHY_it_matters():
    """A caller reading `invalid input` learns nothing. The message has to
    carry the consequence, because the consequence is not guessable from the
    call site: a wrong handle breaks REVOCATION, three months later."""
    with pytest.raises(ValueError) as exc:
        workspace_membership_name("ws-1", "user_01KX")
    assert "second" in str(exc.value).lower()
    assert "revocation" in str(exc.value).lower()
