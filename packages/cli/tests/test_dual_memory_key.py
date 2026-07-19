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


# ── s-consumer-lane-memory-key — the WorkOS/Lane-B fix ──────────────────────
#
# Production symptom this section proves fixed: a consumer (WorkOS AuthKit /
# Gmail signup) authenticated request was denied personal memory with
# "carries no verified identity (claim 'oid')" — because (1)
# ``workos_provider_from_env()`` (the env-driven Lane B provider) never stamped
# the ``_dna_provider_family`` marker at all, and (2) ``_PROVIDER_FAMILY`` had no
# ``"workos"`` entry for the config-driven path either. Both are fixed below; the
# ``sub`` claim WorkOS issues is the **WorkOS user id** (``user_...``), never a
# Google subject — see ``identity_claim_for_family``'s docstring for the founder
# decision and its consequence (partitions live in WorkOS's id namespace).

class _FakeAccess:
    """Stand-in for FastMCP's ``AccessToken`` — the only shape the stamping
    wrapper touches is a mutable ``.claims`` mapping."""

    def __init__(self, claims: dict):
        self.claims = claims


def _workos_lane_b_env(monkeypatch) -> None:
    monkeypatch.setenv("DNA_MCP_WORKOS_CLIENT_ID", "client_01ABC")
    monkeypatch.setenv("DNA_MCP_WORKOS_AUTHKIT_DOMAIN", "dna-cloud.authkit.app")
    monkeypatch.setenv("DNA_MCP_WORKOS_RESOURCE_URL", "https://mcp.dnacloud.io/consumer")


def test_workos_env_lane_stamps_google_family_and_resolves_personal_memory(monkeypatch):
    """The env-driven Lane B path (``workos_provider_from_env``): a verified WorkOS
    token must come back stamped ``_dna_provider_family=google`` and resolve to
    ``personal:google:<workos-sub>`` — NOT denied."""
    import asyncio

    from dna.memory.personal import resolve_memory_tenant
    from dna_cli import _mcp_auth as A

    class _FakeJWTVerifier:
        # Mimics the real JWTVerifier's `.required_scopes` attribute — resource_server
        # -> RemoteAuthProvider.__init__ reads it off whatever verifier it is handed
        # (wrapped or not), so a fake missing it would fail for the WRONG reason.
        required_scopes: list[str] | None = None

        def __init__(self, **kwargs):
            pass

        async def verify_token(self, token):
            # A real WorkOS AuthKit access token's `sub` is the WorkOS user id.
            return _FakeAccess({"sub": "user_01ABCXYZDEF", "email": "consumer@gmail.com"})

    monkeypatch.setattr(
        "fastmcp.server.auth.providers.jwt.JWTVerifier", _FakeJWTVerifier
    )
    _workos_lane_b_env(monkeypatch)

    provider = A.workos_provider_from_env()
    access = asyncio.run(provider.token_verifier.verify_token("fake-bearer"))

    # 1. the stamp is present and correct (the core of the fix).
    assert access.claims[A._DNA_PROVIDER_FAMILY_MARKER] == "google"

    # 2. personal memory resolves the SAME way the composite verifier's stamp
    #    already made Entra work — no PersonalIdentityRequired.
    key_family = A.personal_key_family(access.claims)
    assert key_family == "google"
    oid = A.identity_claim_for_family(access.claims, key_family=key_family)
    assert oid == "user_01ABCXYZDEF"
    tenant = resolve_memory_tenant(
        memory_scope="personal", oid=oid, workspace_tenant=None, family=key_family,
    )
    assert tenant == "personal:google:user_01ABCXYZDEF"


def test_entra_token_still_resolves_bare_personal_partition_no_regression():
    """The composite (config-driven) Entra path is untouched by this fix — an
    Entra token still resolves the bare ``personal:<oid>`` (decision D6)."""
    from dna.memory.personal import resolve_memory_tenant
    from dna_cli import _mcp_auth as A

    claims = {A._DNA_PROVIDER_FAMILY_MARKER: "microsoft", "oid": "entra-oid-456"}
    key_family = A.personal_key_family(claims)
    assert key_family == "entra"
    oid = A.identity_claim_for_family(claims, key_family=key_family)
    assert oid == "entra-oid-456"
    tenant = resolve_memory_tenant(
        memory_scope="personal", oid=oid, workspace_tenant=None, family=key_family,
    )
    assert tenant == "personal:entra-oid-456"


def test_workos_and_entra_partitions_never_collide():
    """The two families are disjoint even when the raw identity strings collide —
    the namespaced ``personal:google:<id>`` shape (decision D6 kept Entra bare
    precisely so a NEW family could never silently alias an existing partition)."""
    from dna.memory.personal import resolve_memory_tenant

    same_raw_id = "abc123"
    workos_tenant = resolve_memory_tenant(
        memory_scope="personal", oid=same_raw_id, workspace_tenant=None, family="google",
    )
    entra_tenant = resolve_memory_tenant(
        memory_scope="personal", oid=same_raw_id, workspace_tenant=None, family="entra",
    )
    assert workos_tenant == "personal:google:abc123"
    assert entra_tenant == "personal:abc123"
    assert workos_tenant != entra_tenant


def test_config_driven_workos_provider_stamps_the_same_google_family(monkeypatch):
    """The config-driven path (``auth.providers[]`` with ``type: workos``) must
    resolve IDENTICALLY to the env-driven Lane B path — both go through
    ``_multi_provider_verifier`` → ``provider_family_for_type("workos")``, which
    needed the ``_PROVIDER_FAMILY["workos"] = "google"`` entry (fix part 2)."""
    import asyncio

    from dna_cli import _mcp_auth as A

    class _FakeVerifier:
        async def verify_token(self, token):
            return _FakeAccess({"sub": "user_01CFGDRIVEN"})

    # Isolate from the real JWKS/network lookup _provider_verifier would otherwise
    # need — the composite's OWN stamping logic is what this test proves.
    monkeypatch.setattr(A, "_provider_verifier", lambda pc: _FakeVerifier())

    pc = A.ProviderConfig(
        type="workos", tenant_claim="org_id",
        issuer="https://dna-cloud.authkit.app", audience="client_01ABC",
    )
    composite = A._multi_provider_verifier([pc])
    access = asyncio.run(composite.verify_token("fake-bearer"))

    assert access.claims[A._DNA_PROVIDER_FAMILY_MARKER] == "google"
    assert A.personal_key_family(access.claims) == "google"
    assert (
        A.identity_claim_for_family(access.claims, key_family="google")
        == "user_01CFGDRIVEN"
    )
