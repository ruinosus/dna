"""Tests for R2-fix — Kernel.write_document(invalidate_mode=...).

Three tiers:
- scope (default): full Phase-15.1 invalidate (drop _kcache._base + holder.reload).
- doc: only invalidate L2 granular cache for (scope, kind, name). Skip mi rebuild.
- none: skip all invalidation. _fire_write_observers still fires (channel contract).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dna.kernel import Kernel


class _FakeWritableSource:
    """Duck-typed WritableSourcePort for tests. Implements every protocol
    method so @runtime_checkable isinstance passes."""

    def __init__(self) -> None:
        self.save_calls: list[tuple] = []
        self.delete_calls: list[tuple] = []

    async def save_document(
        self, scope, kind, name, raw,
        author=None, *, tenant=None, layer=None,
    ) -> str:
        self.save_calls.append((scope, kind, name, tenant, layer))
        return "v1"

    async def delete_document(
        self, scope, kind, name, *, tenant=None, layer=None,
    ) -> None:
        self.delete_calls.append((scope, kind, name, tenant, layer))

    @property
    def supports_readers(self):
        return False

    async def load_bootstrap_docs(self, scope, *, tenant=None):
        return []

    async def load_all(self, scope, readers=None):
        return []

    async def load_layer(self, scope, layer_id, layer_value, readers=None):
        return []

    async def resolve_ref(self, scope, ref):
        return ref

    async def list_doc_refs(self, scope, *, kind=None, tenant=None):
        return []

    async def load_one(self, scope, kind, name, *, readers=None, tenant=None):
        return None

    async def query(
        self, scope, kind, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant=None,
    ):
        if False:
            yield {}  # async generator marker

    async def count(self, scope, kind, *, filter=None, group_by=None, tenant=None):
        # F2 — count is a SourcePort member now; runtime_checkable
        # isinstance(WritableSourcePort) requires it on the fake.
        return {"total": 0, "groups": None}

    async def list_scopes(self):
        return []

    async def close(self):
        return None

    async def save_manifest(self, scope, manifest):
        return "v1"

    async def list_versions(self, scope, kind, name):
        return []

    async def get_version(self, scope, kind, name, version_id):
        return {}

    async def publish(self, scope, kind, name):
        return "v1"

    async def load_drafts(self, scope):
        return []

    async def capabilities(self):
        return {}


def _wire_mock_kernel():
    """Build a Kernel with concrete source + mock holder so we can observe
    which invalidation paths fire."""
    src = _FakeWritableSource()

    k = Kernel()
    # Bypass kernel.source() Protocol check — runtime_checkable looks at
    # method names but Pyright complains about static structural typing.
    k._source = src  # type: ignore[assignment]

    # Seed the base instance cache + a holder
    k._kcache._base = {"scope-x": MagicMock(name="mi")}
    holder = MagicMock()
    holder.scope = "scope-x"
    holder.reload = MagicMock()
    holder.reload_async = AsyncMock()
    k.register_holder(holder)

    return k, src, holder


def _track_granular_invalidate(k):
    """Stub _invalidate_granular_cache so we can detect when (and with what
    kwargs) the L2 cache is dropped."""
    granular_calls: list[tuple] = []
    orig = k._invalidate_granular_cache

    def _spy(scope, *, kind=None, name=None):
        granular_calls.append((scope, kind, name))
        return orig(scope, kind=kind, name=name)
    k._invalidate_granular_cache = _spy
    return granular_calls


def _track_fire_observers(k):
    """Track _fire_write_observers — should fire in ALL modes."""
    fire_calls: list[tuple] = []
    orig = k._fire_write_observers

    def _spy(scope, kind, name, op, **kw):
        fire_calls.append((scope, kind, name, op))
        return orig(scope, kind, name, op, **kw)
    k._fire_write_observers = _spy
    return fire_calls


# ---------- mode="scope" (default, back-compat) ----------

@pytest.mark.asyncio
async def test_scope_mode_drops_base_cache_and_calls_holder_reload():
    k, _src, holder = _wire_mock_kernel()
    assert "scope-x" in k._kcache._base  # precondition

    await k.write_document(
        "scope-x", "Agent", "talent-screener",
        {"kind": "Agent", "metadata": {"name": "talent-screener"}, "spec": {}},
    )

    # Default mode = scope → base_instance_cache dropped
    assert "scope-x" not in k._kcache._base
    # Default mode = scope → holder.reload (or reload_async) was scheduled
    # The invalidate path uses reload_async when in a running loop, reload
    # when not. We're in pytest-asyncio so reload_async should fire.
    assert holder.reload_async.called or holder.reload.called


@pytest.mark.asyncio
async def test_scope_mode_invalidates_granular_cache():
    k, _src, _holder = _wire_mock_kernel()
    granular = _track_granular_invalidate(k)

    await k.write_document(
        "scope-x", "Engram", "rem-foo",
        {"kind": "Engram", "metadata": {"name": "rem-foo"}, "spec": {}},
    )

    assert ("scope-x", "Engram", "rem-foo") in granular


# ---------- mode="doc" (new — R2-fix happy path) ----------

@pytest.mark.asyncio
async def test_doc_mode_does_NOT_drop_base_cache():
    k, _src, _holder = _wire_mock_kernel()
    cached_mi = k._kcache._base["scope-x"]

    await k.write_document(
        "scope-x", "Engram", "rem-sidecar",
        {"kind": "Engram", "metadata": {"name": "rem-sidecar"}, "spec": {}},
        invalidate_mode="doc",
    )

    # mi cache must remain — sidecar writes don't invalidate sibling docs
    assert k._kcache._base["scope-x"] is cached_mi


@pytest.mark.asyncio
async def test_doc_mode_does_NOT_trigger_holder_reload():
    k, _src, holder = _wire_mock_kernel()

    await k.write_document(
        "scope-x", "WorkflowEvent", "je-foo",
        {"kind": "WorkflowEvent", "metadata": {"name": "je-foo"}, "spec": {}},
        invalidate_mode="doc",
    )

    # No reload call — hooks no longer rebuild mi on sidecar writes
    assert not holder.reload.called
    assert not holder.reload_async.called


@pytest.mark.asyncio
async def test_doc_mode_DOES_invalidate_granular_cache():
    """doc mode still invalidates the granular L2 cache so /docs/{kind}/{name}
    reads see the fresh content."""
    k, _src, _holder = _wire_mock_kernel()
    granular = _track_granular_invalidate(k)

    await k.write_document(
        "scope-x", "Engram", "rem-foo",
        {"kind": "Engram", "metadata": {"name": "rem-foo"}, "spec": {}},
        invalidate_mode="doc",
    )

    assert ("scope-x", "Engram", "rem-foo") in granular


# ---------- mode="none" (test-only) ----------

@pytest.mark.asyncio
async def test_none_mode_skips_all_invalidation():
    k, _src, holder = _wire_mock_kernel()
    cached_mi = k._kcache._base["scope-x"]
    granular = _track_granular_invalidate(k)

    await k.write_document(
        "scope-x", "Engram", "rem-foo",
        {"kind": "Engram", "metadata": {"name": "rem-foo"}, "spec": {}},
        invalidate_mode="none",
    )

    assert k._kcache._base["scope-x"] is cached_mi
    assert not holder.reload.called
    assert not holder.reload_async.called
    assert granular == [], "L2 granular cache must NOT be invalidated in mode=none"


# ---------- observers fire in ALL modes ----------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["scope", "doc", "none"])
async def test_write_observers_fire_in_all_modes(mode):
    k, _src, _holder = _wire_mock_kernel()
    fire = _track_fire_observers(k)

    await k.write_document(
        "scope-x", "Engram", "rem-foo",
        {"kind": "Engram", "metadata": {"name": "rem-foo"}, "spec": {}},
        invalidate_mode=mode,
    )

    # _fire_write_observers fires regardless of invalidate_mode — that's
    # the cross-process / SSE delivery contract.
    assert ("scope-x", "Engram", "rem-foo", "write") in fire


# ---------- validation ----------

@pytest.mark.asyncio
async def test_invalid_mode_raises():
    k, _src, _holder = _wire_mock_kernel()
    with pytest.raises(ValueError, match="invalidate_mode"):
        await k.write_document(
            "scope-x", "Engram", "rem-foo",
            {"kind": "Engram", "metadata": {"name": "rem-foo"}, "spec": {}},
            invalidate_mode="bogus",
        )


# ---------- delete_document parity ----------

@pytest.mark.asyncio
async def test_delete_doc_mode_skips_holder_reload():
    k, _src, holder = _wire_mock_kernel()
    cached_mi = k._kcache._base["scope-x"]

    await k.delete_document(
        "scope-x", "Engram", "rem-foo", invalidate_mode="doc",
    )

    # delete with mode=doc does not invalidate the full mi
    assert k._kcache._base["scope-x"] is cached_mi
    assert not holder.reload.called
    assert not holder.reload_async.called


@pytest.mark.asyncio
async def test_delete_invalid_mode_raises():
    k, _src, _holder = _wire_mock_kernel()
    with pytest.raises(ValueError, match="invalidate_mode"):
        await k.delete_document(
            "scope-x", "Engram", "rem-foo", invalidate_mode="bogus",
        )
