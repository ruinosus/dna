"""P2 Task 7 — per-family identity resolution at the MCP auth edge.

The dual-lane personal-memory key is keyed on a SERVER-DERIVED identity + its
provider family: Entra tokens → the ``oid`` claim → bare ``personal:<oid>``;
Google tokens → the ``sub`` claim → ``personal:google:<sub>``. The family is read
from the ``_dna_provider_family`` stamp the composite verifier writes. Everything
stays fail-closed (no identity ⇒ ``PersonalIdentityRequired``).
"""
from __future__ import annotations

import pytest

from dna_cli._mcp_auth import (
    identity_claim_for_family,
    personal_key_family,
)


# ── pure helpers ────────────────────────────────────────────────────────────

def test_key_family_maps_provider_stamp():
    assert personal_key_family({"_dna_provider_family": "microsoft"}) == "entra"
    assert personal_key_family({"_dna_provider_family": "google"}) == "google"
    # absent / unknown → back-compat single-lane "entra"
    assert personal_key_family({}) == "entra"
    assert personal_key_family({"_dna_provider_family": "clerk"}) == "entra"
    assert personal_key_family(None) == "entra"


def test_identity_claim_per_family():
    assert identity_claim_for_family({"oid": "o1"}, key_family="entra") == "o1"
    assert identity_claim_for_family({"sub": "s1"}, key_family="google") == "s1"
    # wrong-lane claim missing → None (then the caller fails closed)
    assert identity_claim_for_family({"oid": "o1"}, key_family="google") is None
    assert identity_claim_for_family({"sub": "s1"}, key_family="entra") is None


# ── context-bound resolution (fake token) ───────────────────────────────────

class _FakeToken:
    def __init__(self, claims: dict):
        self.claims = claims


@pytest.fixture
def patch_token(monkeypatch):
    """Install a fake ``get_access_token`` returning a token with given claims."""
    import fastmcp.server.dependencies as deps

    def _install(claims: dict | None):
        monkeypatch.setattr(
            deps, "get_access_token",
            lambda: (None if claims is None else _FakeToken(claims)),
        )
    return _install


def test_family_from_context_entra_vs_google(patch_token):
    from dna_cli._mcp_auth import enforce_personal_family_from_context

    patch_token({"_dna_provider_family": "google", "sub": "s1"})
    assert enforce_personal_family_from_context() == "google"
    patch_token({"_dna_provider_family": "microsoft", "oid": "o1"})
    assert enforce_personal_family_from_context() == "entra"
    patch_token(None)  # no token → offline default
    assert enforce_personal_family_from_context() == "entra"


def test_oid_from_context_reads_sub_for_google(patch_token):
    from dna_cli._mcp_auth import enforce_oid_from_context

    patch_token({"_dna_provider_family": "google", "sub": "google-sub-123"})
    assert enforce_oid_from_context() == "google-sub-123"
    patch_token({"_dna_provider_family": "microsoft", "oid": "entra-oid-456"})
    assert enforce_oid_from_context() == "entra-oid-456"


def test_google_token_without_sub_fails_closed(patch_token):
    from dna.memory.personal import PersonalIdentityRequired
    from dna_cli._mcp_auth import enforce_oid_from_context

    patch_token({"_dna_provider_family": "google"})  # no sub, no env
    import os
    os.environ.pop("DNA_PERSONAL_ID", None)
    with pytest.raises(PersonalIdentityRequired):
        enforce_oid_from_context()


def test_end_to_end_partition_google_vs_entra():
    """The full key both lanes produce (the value a memory op runs against)."""
    from dna.memory.personal import resolve_memory_tenant

    assert resolve_memory_tenant(
        memory_scope="personal", oid="google-sub", workspace_tenant=None, family="google",
    ) == "personal:google:google-sub"
    assert resolve_memory_tenant(
        memory_scope="personal", oid="entra-oid", workspace_tenant=None, family="entra",
    ) == "personal:entra-oid"
