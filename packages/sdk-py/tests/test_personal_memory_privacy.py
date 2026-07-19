"""INV-PERSONAL — the security-critical privacy invariant (ADR-personal-memory §7).

    > A personal memory written by identity X (oid=X) is NEVER readable by
    > identity Y (oid≠X), nor by ANY workspace-scoped query — including a
    > workspace owner's or admin's. There is no override. Fail-closed.

This suite proves the invariant holds by all FOUR independent, layered mechanisms
(``s-personal-memory-privacy-invariant``). It is the security core of the
feature — if any check here regresses, personal memory has a hole:

1. **server-derived oid** — a caller can never NAME another identity's partition;
   the oid is resolved server-side (proven at the resolver / surface seams).
2. **physically disjoint partition + union predicate** — a workspace request
   filters ``tenant IN ('', <workspace_id>)`` and PROVABLY cannot return a
   ``personal:*`` row; user Y's personal recall (``personal:Y``) never sees X's.
3. **reserved namespace at the validator** — no Workspace can be named to alias a
   personal partition.
4. **raw personal-tenant override rejection** — a caller passing a raw
   ``tenant=personal:<victim>`` is DENIED.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.protocols import InvalidTenantSlug, validate_tenant_slug
from dna.memory import consolidate, recall, remember
from dna.memory.personal import (
    PersonalOverrideRejected,
    assert_no_personal_override,
    personal_tenant,
)
from dna.application.runtime import _resolve_memory_target

from dna.adapters.filesystem.writable import FilesystemWritableSource

_OID_A = "aaaaaaaa-0000-0000-0000-000000000001"
_OID_B = "bbbbbbbb-0000-0000-0000-000000000002"
_WORKSPACE = "cccccccc-0000-0000-0000-000000000003"
_SCOPE = "_lib"


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
    (base / _SCOPE).mkdir()  # the shared base scope exists (as it does in prod)
    k = Kernel.auto()
    src = FilesystemWritableSource(base_dir=str(base))
    k.source(src)
    src.set_kernel(k)
    return k


async def _names(res_or_docs) -> set[str]:
    if isinstance(res_or_docs, dict):
        return {h.get("name") for h in res_or_docs.get("hits", [])}
    return {(d.get("metadata") or {}).get("name") for d in res_or_docs}


# ── check 1: X's personal memory is invisible to a workspace query ──────────


@pytest.mark.asyncio
async def test_personal_never_visible_to_workspace(kernel):
    await remember(
        kernel, _SCOPE, kind="Engram", name="rem-secret",
        spec=_ll("my private secret memory"),
        tenant=personal_tenant(_OID_A), index=False,
    )
    # A workspace recall (the owner/admin runs it) → 0 hits.
    ws = await recall(
        kernel, _SCOPE, "private secret", tenant=_WORKSPACE, reconsolidate=False,
    )
    assert "rem-secret" not in await _names(ws)
    # The raw union predicate at query level, too: tenant IN ('', workspace).
    ws_docs = [d async for d in kernel.query(_SCOPE, "Engram", tenant=_WORKSPACE)]
    assert "rem-secret" not in await _names(ws_docs)
    # base ('' ) query — the shared defaults — also excludes it.
    base_docs = [d async for d in kernel.query(_SCOPE, "Engram", tenant=None)]
    assert "rem-secret" not in await _names(base_docs)


# ── check 2: X's personal memory is invisible to a DIFFERENT identity Y ─────


@pytest.mark.asyncio
async def test_personal_isolated_between_identities(kernel):
    await remember(
        kernel, _SCOPE, kind="Engram", name="rem-a-only",
        spec=_ll("A private note"), tenant=personal_tenant(_OID_A), index=False,
    )
    # Y (oid=B) recalls their OWN personal partition → 0 hits.
    as_b = await recall(
        kernel, _SCOPE, "private note", tenant=personal_tenant(_OID_B),
        reconsolidate=False,
    )
    assert "rem-a-only" not in await _names(as_b)
    # A recalls A's partition → the hit IS there.
    as_a = await recall(
        kernel, _SCOPE, "private note", tenant=personal_tenant(_OID_A),
        reconsolidate=False,
    )
    assert "rem-a-only" in await _names(as_a)


# ── check 3: reserved namespace — no workspace can alias a personal partition ─


def test_validate_tenant_slug_rejects_personal_workspace_name():
    with pytest.raises(InvalidTenantSlug):
        validate_tenant_slug(f"personal:{_OID_A}")
    with pytest.raises(InvalidTenantSlug):
        validate_tenant_slug("personal:whatever")


# ── check 4: raw personal-tenant override is DENIED ─────────────────────────


def test_raw_personal_override_denied_at_surface_seam():
    # A workspace-scoped memory op with a raw tenant=personal:<victim> is denied.
    with pytest.raises(PersonalOverrideRejected):
        assert_no_personal_override(personal_tenant(_OID_A))


def test_resolve_memory_target_rejects_workspace_personal_override():
    class _Live:
        base_scope = _SCOPE

        def default_scope(self, tenant):
            return _SCOPE

    # memory_scope=workspace + a forged personal tenant → denied (layer 4).
    with pytest.raises(PersonalOverrideRejected):
        _resolve_memory_target(
            _Live(), None, personal_tenant(_OID_A), "workspace", None,
        )
    # memory_scope=personal derives the tenant server-side from the oid — the
    # workspace_tenant is ignored, so no victim partition can be named.
    sc, tn = _resolve_memory_target(_Live(), None, _WORKSPACE, "personal", _OID_B)
    assert tn == personal_tenant(_OID_B)
    assert sc == _SCOPE


# ── check 5: consolidate over a personal partition touches ONLY it ──────────


@pytest.mark.asyncio
async def test_consolidate_personal_partition_isolated(kernel):
    await remember(
        kernel, _SCOPE, kind="Engram", name="rem-a",
        spec=_ll("A memory"), tenant=personal_tenant(_OID_A), index=False,
    )
    await remember(
        kernel, _SCOPE, kind="Engram", name="rem-ws",
        spec=_ll("workspace memory"), tenant=_WORKSPACE, index=False,
    )
    # Consolidate A's personal partition: evaluates ONLY A's memory, never the
    # workspace one (disjoint partitions never cross-contaminate).
    report = await consolidate(kernel, _SCOPE, tenant=personal_tenant(_OID_A))
    assert report["evaluated"] == 1
    # A workspace consolidate evaluates only the workspace memory.
    ws_report = await consolidate(kernel, _SCOPE, tenant=_WORKSPACE)
    assert ws_report["evaluated"] == 1
