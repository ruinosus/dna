"""P2 — family-namespaced personal partition key (dual-lane, back-compat).

Lane A (Entra) keeps the bare ``personal:<oid>`` scheme (NO migration of existing
keys — decision D6); Lane B (Google) gets ``personal:google:<sub>`` so the two
identity families can never collide in the same partition. The reserved
``personal:`` scheme still guards both.
"""
from __future__ import annotations

import pytest

from dna.memory.personal import (
    PersonalIdentityRequired,
    is_personal_tenant,
    personal_tenant,
)


def test_entra_stays_bare_backcompat():
    # No family, or family="entra" → the current bare value (zero migration).
    assert personal_tenant("oid123") == "personal:oid123"
    assert personal_tenant("oid123", family="entra") == "personal:oid123"


def test_google_is_family_namespaced():
    assert personal_tenant("sub456", family="google") == "personal:google:sub456"


def test_families_never_collide():
    assert personal_tenant("X", family="entra") != personal_tenant("X", family="google")


def test_google_partition_still_recognized_as_personal():
    assert is_personal_tenant(personal_tenant("sub456", family="google")) is True


def test_blank_identity_fails_closed_for_any_family():
    with pytest.raises(PersonalIdentityRequired):
        personal_tenant("", family="google")
    with pytest.raises(PersonalIdentityRequired):
        personal_tenant("   ", family="entra")
