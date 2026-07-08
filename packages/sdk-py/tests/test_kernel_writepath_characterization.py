"""CHARACTERIZATION — pins current behavior for kernel decomposition Fases 2-5;
if this breaks during an extraction, the extraction changed observable behavior.

Block 1 of the kernel-decomposition spec (2026-07-08-kernel-decomposition-design)
= the write/delete pipeline (``write_document`` / ``_write_document_inner`` /
``delete_document``, ~454 loc) that Fase 2 moves into ``WritePipeline``. This
suite is the safety net Fase 2 runs BEFORE and AFTER the move: identical green =
equivalence.

What this suite ADDS on top of the already-rich write-path coverage (it does
NOT re-assert those — it references them):
  - ``test_kernel_invalidate_modes``       → the scope/doc/none tiers.
  - ``test_kernel_record_plane_writes``    → record-plane demotion + parity.
  - ``test_write_path_despecialize``       → veto priority/idempotency, bitemporal
                                             LessonLearned, Genome catalog-drop.
  - ``test_write_document_prompt_budget``  → voice-UA instruction_token_cap veto.
  - ``test_version_retention``             → VERSION_CHURN_KINDS retention kwarg.
  - ``test_kernel_tenant_phase1``          → TENANTED/GLOBAL/layer back-compat.
  - ``test_kind_name_collision``           → i-195 apiVersion-resolved demotion.

The genuine GAP this suite closes: NO existing test snapshots the FULL ORDERED
event sequence of the pipeline (pre_save veto → save → granular-invalidate →
catalog-invalidate → base-drop → invalidate → fire-observers → post_save). That
exact ordering is load-bearing (spec Risk #1) and is precisely what a mechanical
extraction can silently reorder. We pin it here with a single event-recording
spy, across the mode × catalog × skip_hooks × delete matrix.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dna.kernel import Kernel
from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import StorageDescriptor, TenantScope

# pytest puts tests/ on sys.path → import the canonical fake source directly.
from test_kernel_invalidate_modes import _FakeWritableSource


# ── Fixture Kinds (deterministic, no extension load) ──────────────────────

class _CompKind(KindBase):
    """Composition-plane Kind → 'scope' invalidate mode is NOT demoted."""
    api_version = "char.io/v1"
    kind = "CompThing"
    alias = "char-compthing"
    storage = StorageDescriptor.yaml("compthings")
    # plane defaults to 'composition'


class _CatalogKind(KindBase):
    """Composition-plane catalog-identity Kind → triggers catalog-cache drop."""
    api_version = "char.io/v1"
    kind = "CatalogThing"
    alias = "char-catalogthing"
    storage = StorageDescriptor.yaml("catalogthings")
    is_catalog_identity = True


class _RecordKind(KindBase):
    """Record-plane Kind → 'scope' is demoted to 'doc'."""
    api_version = "char.io/v1"
    kind = "RecordThing"
    alias = "char-recordthing"
    storage = StorageDescriptor.yaml("recordthings")
    plane = "record"


class _TenantedKind(KindBase):
    api_version = "char.io/v1"
    kind = "TenantedThing"
    alias = "char-tenantedthing"
    storage = StorageDescriptor.yaml("tenantedthings")
    scope = TenantScope.TENANTED


class _GlobalKind(KindBase):
    api_version = "char.io/v1"
    kind = "GlobalThing"
    alias = "char-globalthing"
    storage = StorageDescriptor.yaml("globalthings")
    scope = TenantScope.GLOBAL


def _wire(*kinds) -> tuple[Kernel, _FakeWritableSource, MagicMock]:
    src = _FakeWritableSource()
    k = Kernel()
    k._source = src  # type: ignore[assignment]
    for kc in kinds:
        k.kind(kc())
    k._kcache._base = {"scope-x": MagicMock(name="mi")}
    holder = MagicMock()
    holder.scope = "scope-x"
    holder.reload = MagicMock()
    holder.reload_async = AsyncMock()
    k.register_holder(holder)
    return k, src, holder


def _record_pipeline_events(k: Kernel, src: _FakeWritableSource) -> list[str]:
    """Wrap every pipeline side-effect so we can assert the EXACT order."""
    events: list[str] = []

    # 1. pre_save veto — the integrity gate (fires even on skip_hooks).
    k.on_veto("pre_save", lambda _c: events.append("pre_save_veto"))

    # 2. adapter persist.
    orig_save = src.save_document
    async def _save(*a, **kw):  # noqa: ANN002, ANN003
        events.append("save_document")
        return await orig_save(*a, **kw)
    src.save_document = _save  # type: ignore[assignment]

    orig_delete = src.delete_document
    async def _delete(*a, **kw):  # noqa: ANN002, ANN003
        events.append("delete_document")
        return await orig_delete(*a, **kw)
    src.delete_document = _delete  # type: ignore[assignment]

    # 3. granular L2 invalidate.
    orig_gran = k._invalidate_granular_cache
    def _gran(scope, *, kind=None, name=None):  # noqa: ANN001
        events.append("granular_invalidate")
        return orig_gran(scope, kind=kind, name=name)
    k._invalidate_granular_cache = _gran  # type: ignore[assignment]

    # 4. catalog-cache drop (only for is_catalog_identity Kinds).
    orig_cat = k._invalidate_catalog_cache
    def _cat(tenant=None):  # noqa: ANN001
        events.append("catalog_invalidate")
        return orig_cat(tenant)
    k._invalidate_catalog_cache = _cat  # type: ignore[assignment]

    # 5. base-instance cache drop.
    orig_drop = k._kcache.base_drop
    def _drop(scope):  # noqa: ANN001
        events.append("base_drop")
        return orig_drop(scope)
    k._kcache.base_drop = _drop  # type: ignore[assignment]

    # 6. holder-reload + observer fan-out.
    orig_inv = k.invalidate
    def _inv(**kw):  # noqa: ANN003
        events.append("invalidate")
        return orig_inv(**kw)
    k.invalidate = _inv  # type: ignore[assignment]

    # 7. cross-process write observers (ALWAYS fire).
    orig_fire = k._fire_write_observers
    def _fire(scope, kind, name, op, **kw):  # noqa: ANN001, ANN003
        events.append(f"fire_observers:{op}")
        return orig_fire(scope, kind, name, op, **kw)
    k._fire_write_observers = _fire  # type: ignore[assignment]

    # 8. post_save / post_delete (skipped when skip_hooks=True).
    k.on("post_save", lambda _c: events.append("post_save"))
    k.on("post_delete", lambda _c: events.append("post_delete"))
    return events


def _raw(kind: str, name: str) -> dict:
    return {"apiVersion": "char.io/v1", "kind": kind,
            "metadata": {"name": name}, "spec": {"v": 1}}


# ── 1. The full ordered pipeline (the load-bearing sequence) ──────────────

@pytest.mark.asyncio
async def test_write_scope_mode_full_event_order():
    """Composition-plane write, invalidate_mode=scope, base layer, hooks on.
    Pins the canonical order the WritePipeline extraction must reproduce."""
    k, src, _h = _wire(_CompKind)
    events = _record_pipeline_events(k, src)

    await k.write_document("scope-x", "CompThing", "c1", _raw("CompThing", "c1"))

    assert events == [
        "pre_save_veto",      # integrity gate — BEFORE persist
        "save_document",      # adapter persist
        "granular_invalidate",
        "base_drop",          # scope mode only, base layer only
        "invalidate",         # holder.reload + observer fan-out
        "fire_observers:write",  # always
        "post_save",          # not skip_hooks
    ]


@pytest.mark.asyncio
async def test_write_catalog_identity_inserts_catalog_invalidate():
    """A catalog-identity Kind adds ONE step (catalog_invalidate) right after
    the granular drop — keyed off KindPort.is_catalog_identity, not a name."""
    k, src, _h = _wire(_CatalogKind)
    events = _record_pipeline_events(k, src)

    await k.write_document("scope-x", "CatalogThing", "cc", _raw("CatalogThing", "cc"))

    assert events == [
        "pre_save_veto",
        "save_document",
        "granular_invalidate",
        "catalog_invalidate",  # <-- inserted vs the non-catalog case
        "base_drop",
        "invalidate",
        "fire_observers:write",
        "post_save",
    ]


@pytest.mark.asyncio
async def test_write_doc_mode_skips_scope_steps_but_keeps_observers_and_post_save():
    k, src, _h = _wire(_CompKind)
    events = _record_pipeline_events(k, src)

    await k.write_document(
        "scope-x", "CompThing", "c1", _raw("CompThing", "c1"),
        invalidate_mode="doc",
    )

    assert events == [
        "pre_save_veto",
        "save_document",
        "granular_invalidate",   # doc mode keeps the L2 drop...
        # ...but NOT base_drop / invalidate (no scope rebuild)
        "fire_observers:write",
        "post_save",
    ]


@pytest.mark.asyncio
async def test_write_none_mode_skips_all_invalidation_keeps_observers_and_post_save():
    k, src, _h = _wire(_CompKind)
    events = _record_pipeline_events(k, src)

    await k.write_document(
        "scope-x", "CompThing", "c1", _raw("CompThing", "c1"),
        invalidate_mode="none",
    )

    assert events == [
        "pre_save_veto",
        "save_document",
        # no granular / catalog / base_drop / invalidate in mode=none
        "fire_observers:write",  # observers still fire — channel contract
        "post_save",
    ]


@pytest.mark.asyncio
async def test_write_skip_hooks_still_fires_veto_and_observers_but_drops_post_save():
    """skip_hooks silences ONLY post_save. The pre_save veto (integrity gate)
    and the observer fan-out both still fire (spec Risk #1)."""
    k, src, _h = _wire(_CompKind)
    events = _record_pipeline_events(k, src)

    await k.write_document(
        "scope-x", "CompThing", "c1", _raw("CompThing", "c1"),
        skip_hooks=True,
    )

    assert "pre_save_veto" in events
    assert "fire_observers:write" in events
    assert "post_save" not in events
    # order among the ones that DID fire is unchanged
    assert events == [
        "pre_save_veto",
        "save_document",
        "granular_invalidate",
        "base_drop",
        "invalidate",
        "fire_observers:write",
    ]


# ── 2. Veto blocks persist (ordering: veto strictly before save) ──────────

@pytest.mark.asyncio
async def test_veto_raise_aborts_before_persist():
    k, src, _h = _wire(_CompKind)
    events = _record_pipeline_events(k, src)

    def guard(ctx):
        if ctx.kind == "CompThing":
            raise PermissionError("blocked")
    k.on_veto("pre_save", guard, key="char.block")

    with pytest.raises(PermissionError):
        await k.write_document("scope-x", "CompThing", "c1", _raw("CompThing", "c1"))

    # nothing past the veto ran — no persist, no invalidation, no observers
    assert src.save_calls == []
    assert "save_document" not in events


# ── 3. Record-plane demotion (scope → doc), incl. i-195 apiVersion path ───

@pytest.mark.asyncio
async def test_record_plane_demotes_scope_to_doc():
    """A record-plane Kind written with the default invalidate_mode='scope'
    is demoted to 'doc' — no base_drop / invalidate, but granular + observers
    + post_save still run."""
    k, src, _h = _wire(_RecordKind)
    events = _record_pipeline_events(k, src)

    await k.write_document("scope-x", "RecordThing", "r1", _raw("RecordThing", "r1"))

    assert events == [
        "pre_save_veto",
        "save_document",
        "granular_invalidate",
        "fire_observers:write",
        "post_save",
    ]


@pytest.mark.asyncio
async def test_record_plane_demotion_resolves_plane_from_raw_apiversion():
    """i-195: the demotion resolves the plane from the doc's OWN apiVersion,
    so a record-plane write is demoted even though the bare name could be
    ambiguous. Here the raw carries char.io/v1 → RecordThing (record)."""
    k, src, holder = _wire(_RecordKind)

    await k.write_document("scope-x", "RecordThing", "r1", _raw("RecordThing", "r1"))

    # demoted → base cache intact, holder never reloaded
    assert "scope-x" in k._kcache._base
    assert not holder.reload.called and not holder.reload_async.called


# ── 4. delete_document — no pre_save veto, mirrors invalidation tiers ──────

@pytest.mark.asyncio
async def test_delete_scope_mode_event_order_has_no_pre_save_veto():
    """delete has NO pre_save veto gate (only writes do) — pinning this so an
    extraction doesn't accidentally add/remove one. post_delete honors
    skip_hooks; observers always fire."""
    k, src, _h = _wire(_CompKind)
    events = _record_pipeline_events(k, src)

    await k.delete_document("scope-x", "CompThing", "c1")

    assert events == [
        "delete_document",
        "granular_invalidate",
        "base_drop",
        "invalidate",
        "fire_observers:delete",
        "post_delete",
    ]
    assert "pre_save_veto" not in events


@pytest.mark.asyncio
async def test_delete_skip_hooks_drops_post_delete_keeps_observers():
    k, src, _h = _wire(_CompKind)
    events = _record_pipeline_events(k, src)

    await k.delete_document("scope-x", "CompThing", "c1", skip_hooks=True)

    assert "fire_observers:delete" in events
    assert "post_delete" not in events


# ── 5. Tenant resolution funnel (TENANTED / GLOBAL / layer back-compat) ────

@pytest.mark.asyncio
async def test_tenanted_kind_requires_tenant():
    from dna.kernel.protocols import TenantRequired
    k, _src, _h = _wire(_TenantedKind)
    with pytest.raises(TenantRequired):
        await k.write_document(
            "scope-x", "TenantedThing", "t1", _raw("TenantedThing", "t1"),
        )


@pytest.mark.asyncio
async def test_tenanted_kind_accepts_explicit_tenant():
    k, src, _h = _wire(_TenantedKind)
    await k.write_document(
        "scope-x", "TenantedThing", "t1", _raw("TenantedThing", "t1"),
        tenant="acme",
    )
    # tenant folded through to the adapter (legacy fake → layer=('tenant','acme'))
    last = src.save_calls[-1]
    assert last[3] == "acme" or last[4] == ("tenant", "acme")


@pytest.mark.asyncio
async def test_global_kind_rejects_tenant():
    from dna.kernel.protocols import TenantNotAllowed
    k, _src, _h = _wire(_GlobalKind)
    with pytest.raises(TenantNotAllowed):
        await k.write_document(
            "scope-x", "GlobalThing", "g1", _raw("GlobalThing", "g1"),
            tenant="acme",
        )


@pytest.mark.asyncio
async def test_layer_tenant_backcompat_emits_deprecation_and_folds_to_tenant():
    import warnings
    k, src, _h = _wire(_TenantedKind)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        await k.write_document(
            "scope-x", "TenantedThing", "t1", _raw("TenantedThing", "t1"),
            layer=("tenant", "acme"),
        )
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    # layer=('tenant',X) promoted to tenant=X → adapter sees acme
    last = src.save_calls[-1]
    assert last[3] == "acme" or last[4] == ("tenant", "acme")


# ── 6. Guardrails at the pipeline boundary (mode validation) ──────────────

@pytest.mark.asyncio
async def test_invalid_invalidate_mode_raises_before_any_effect():
    k, src, _h = _wire(_CompKind)
    with pytest.raises(ValueError, match="invalidate_mode"):
        await k.write_document(
            "scope-x", "CompThing", "c1", _raw("CompThing", "c1"),
            invalidate_mode="bogus",
        )
    assert src.save_calls == []
