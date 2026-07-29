"""``actor_label`` — who an action is recorded as.

Measured in production, 2026-07-29: every uploaded artifact recorded
``uploaded_by: null``. Nothing failed. The membership check on the very same
identity had already passed, so the write went through and the record was
simply anonymous — a provenance field that exists to say WHO, saying nothing.

The cause was reading ONLY ``oid``. A portal session can carry a verified email
and no durable subject (the membership it matches may be email-bound), and an
``oid``-only read yields ``None`` for exactly those callers. Email-first is not
a preference: it is the order this repo already settled on for the same
question (``invite_member_impl`` records ``invited_by`` that way, and the MCP
face's ``actor_from_context`` documents why — a human reading a record wants a
person, not a subject id).
"""
from __future__ import annotations

from dna.application.runtime import actor_label
from dna.tenancy.resolution import Identity


def test_an_identity_with_no_oid_is_still_named():
    """The production case. Read only ``oid`` again and this dies."""
    assert actor_label(Identity(email="barna@dnacloud.io")) == "barna@dnacloud.io"


def test_email_wins_over_the_subject_id():
    """Both present — a human reading the record gets the person."""
    assert actor_label(Identity(oid="oid-1", email="barna@dnacloud.io")) == "barna@dnacloud.io"


def test_a_subject_with_no_email_is_still_named():
    """A service token has no email and is not anonymous."""
    assert actor_label(Identity(oid="oid-1")) == "oid-1"


def test_a_verified_but_anonymous_caller_stays_empty():
    """Neither field: a real state. Better empty than filled with a channel
    name — recording the transport as the actor is the conflation the MCP
    face's UNIDENTIFIED_* constants exist to end."""
    assert actor_label(Identity()) is None
    assert actor_label(None) is None
