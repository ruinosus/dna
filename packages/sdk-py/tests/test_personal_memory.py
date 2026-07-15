"""Personal / private per-user memory — core seam + partition round-trip.

Covers ``s-personal-memory-partition`` + ``s-personal-memory-namespace-guard``:

* the pure resolver (:func:`dna.memory.personal.resolve_memory_tenant`) — the
  ADR §5 decision (workspace default, personal→``personal:<oid>``, fail-closed);
* the reserved-scheme helpers + the ``validate_tenant_slug`` namespace
  reservation (INV-PERSONAL layer 3) + the ``allow_personal`` write bypass;
* a real FS round-trip proving the personal partition keys on ``personal:<oid>``
  with ZERO schema migration (reuses the existing tenant path segment), and that
  a workspace-bound read cannot see it.

The security-critical INV-PERSONAL suite is in ``test_personal_memory_privacy``.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.protocols import InvalidTenantSlug, validate_tenant_slug
from dna.memory import remember
from dna.memory.personal import (
    PERSONAL_TENANT_PREFIX,
    PersonalIdentityRequired,
    PersonalOverrideRejected,
    assert_no_personal_override,
    is_personal_tenant,
    personal_tenant,
    resolve_memory_tenant,
    tenant_scheme,
)

from dna.adapters.filesystem.writable import FilesystemWritableSource

_OID_A = "11111111-1111-1111-1111-aaaaaaaaaaaa"
_OID_B = "22222222-2222-2222-2222-bbbbbbbbbbbb"
_WORKSPACE = "99999999-9999-9999-9999-cccccccccccc"


# ─────────────────────── pure core: the resolver ───────────────────────


def test_personal_tenant_builds_reserved_value():
    assert personal_tenant(_OID_A) == f"{PERSONAL_TENANT_PREFIX}{_OID_A}"
    assert personal_tenant(_OID_A) == f"personal:{_OID_A}"


def test_personal_tenant_rejects_blank_identity():
    for blank in ("", "   ", None):
        with pytest.raises(PersonalIdentityRequired):
            personal_tenant(blank)  # type: ignore[arg-type]


def test_is_personal_tenant_and_scheme():
    assert is_personal_tenant(personal_tenant(_OID_A)) is True
    assert is_personal_tenant(_WORKSPACE) is False
    assert is_personal_tenant("") is False
    assert is_personal_tenant(None) is False
    assert tenant_scheme(personal_tenant(_OID_A)) == "personal"
    assert tenant_scheme(_WORKSPACE) is None  # a GUID carries no ':' scheme


def test_resolve_memory_tenant_workspace_is_identity():
    # workspace (default) → the workspace tenant unchanged (oid ignored).
    assert resolve_memory_tenant(
        memory_scope="workspace", oid=_OID_A, workspace_tenant=_WORKSPACE
    ) == _WORKSPACE
    assert resolve_memory_tenant(
        memory_scope="workspace", oid=None, workspace_tenant=None
    ) is None


def test_resolve_memory_tenant_personal_maps_to_oid_partition():
    # personal → personal:<oid>, WORKSPACE-INDEPENDENT (workspace_tenant ignored).
    for ws in (None, _WORKSPACE, "some-other-workspace"):
        assert resolve_memory_tenant(
            memory_scope="personal", oid=_OID_A, workspace_tenant=ws
        ) == personal_tenant(_OID_A)


def test_resolve_memory_tenant_personal_fails_closed_without_identity():
    for missing in (None, "", "   "):
        with pytest.raises(PersonalIdentityRequired):
            resolve_memory_tenant(
                memory_scope="personal", oid=missing, workspace_tenant=_WORKSPACE
            )


def test_assert_no_personal_override():
    assert_no_personal_override(None)          # no-op
    assert_no_personal_override(_WORKSPACE)     # no-op
    with pytest.raises(PersonalOverrideRejected):
        assert_no_personal_override(personal_tenant(_OID_B))


# ─────────────── namespace reservation (INV-PERSONAL layer 3) ───────────────


def test_validate_tenant_slug_reserves_personal_scheme():
    # A workspace/tenant can never be NAMED with the reserved personal: scheme.
    with pytest.raises(InvalidTenantSlug):
        validate_tenant_slug("personal:whatever")
    with pytest.raises(InvalidTenantSlug):
        validate_tenant_slug(personal_tenant(_OID_A))


def test_validate_tenant_slug_allows_personal_for_authorized_write():
    # The authorized personal-memory write path passes allow_personal=True.
    validate_tenant_slug(personal_tenant(_OID_A), allow_personal=True)  # no raise


def test_validate_tenant_slug_still_accepts_ordinary_tenants():
    validate_tenant_slug(_WORKSPACE)  # a GUID workspace id — unchanged
    validate_tenant_slug("acme")
    validate_tenant_slug(None)


def test_with_tenant_rejects_personal_without_authorization():
    k = Kernel()
    with pytest.raises(InvalidTenantSlug):
        k.with_tenant(personal_tenant(_OID_A))
    # authorized bind is fine + carries the flag downstream.
    bound = k.with_tenant(personal_tenant(_OID_A), allow_personal=True)
    assert bound.tenant == personal_tenant(_OID_A)
    assert bound._allow_personal is True


# ─────────────────── FS round-trip: partition by personal:<oid> ─────────────


def _ll(summary: str) -> dict:
    return {
        "area": "Feature/personal",
        "surface_when": ["feature_touched"],
        "source_refs": ["s-personal-memory"],
        "affect": "triumph",
        "affect_reason": "a concrete reason long enough for the affect validator ok",
        "summary": summary,
    }


@pytest.fixture
def kernel(tmp_path):
    base = tmp_path / "src"
    base.mkdir()
    (base / "_lib").mkdir()  # the shared base scope exists (as it does in prod)
    k = Kernel.auto()
    src = FilesystemWritableSource(base_dir=str(base))
    k.source(src)
    src.set_kernel(k)
    return k


@pytest.mark.asyncio
async def test_personal_write_keys_on_personal_partition_zero_migration(kernel, tmp_path):
    # Write a personal memory for oid=A via the authorized personal binding.
    await remember(
        kernel, "_lib", kind="LessonLearned", name="rem-priv",
        spec=_ll("my private cron misread note"),
        tenant=personal_tenant(_OID_A), index=False,
    )
    # It lands under the reserved tenant partition (existing FS path segment, the
    # ':' percent-encoded on disk for portability — zero schema migration).
    hit = await kernel.get_document(
        "_lib", "LessonLearned", "rem-priv", tenant=personal_tenant(_OID_A)
    )
    assert hit is not None
    assert hit["spec"]["summary"] == "my private cron misread note"
    # On disk it is a real, isolated tenant directory.
    tenants_dir = tmp_path / "src" / "tenants"
    dirs = {p.name for p in tenants_dir.iterdir()} if tenants_dir.exists() else set()
    assert any(d.startswith("personal") for d in dirs), dirs


@pytest.mark.asyncio
async def test_workspace_read_cannot_see_personal(kernel):
    await remember(
        kernel, "_lib", kind="LessonLearned", name="rem-priv",
        spec=_ll("private"), tenant=personal_tenant(_OID_A), index=False,
    )
    # A workspace-bound query (tenant IN ('', <workspace_id>)) provably excludes
    # personal:* — the union predicate cannot name it.
    ws_docs = [
        d async for d in kernel.query("_lib", "LessonLearned", tenant=_WORKSPACE)
    ]
    assert all(
        (d.get("metadata") or {}).get("name") != "rem-priv" for d in ws_docs
    )
