"""F1 two-planes: write/delete de plane=record nunca dispara scope-invalidate."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from dna.kernel import Kernel
from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import StorageDescriptor

# -- reuse do harness (pytest põe tests/ no sys.path; SEM prefixo tests.) --
from test_kernel_invalidate_modes import _FakeWritableSource


class _StoryLike(KindBase):
    api_version = "test.io/v1"
    kind = "StoryLike"
    alias = "test-storylike"
    storage = StorageDescriptor.yaml("storylikes")
    plane = "record"


class _AgentLike(KindBase):
    api_version = "test.io/v1"
    kind = "AgentLike"
    alias = "test-agentlike"
    storage = StorageDescriptor.yaml("agentlikes")
    # plane default = composition


def _wire():
    src = _FakeWritableSource()
    k = Kernel()
    k._source = src  # type: ignore[assignment]
    k.kind(_StoryLike())
    k.kind(_AgentLike())
    k._kcache._base = {"scope-x": MagicMock(name="mi")}
    holder = MagicMock()
    holder.scope = "scope-x"
    holder.reload = MagicMock()
    holder.reload_async = AsyncMock()
    k.register_holder(holder)
    return k, src, holder


def _raw(kind, name):
    return {"apiVersion": "test.io/v1", "kind": kind,
            "metadata": {"name": name}, "spec": {}}


@pytest.mark.asyncio
async def test_record_write_default_mode_skips_scope_invalidate():
    k, _src, holder = _wire()
    cached = k._kcache._base["scope-x"]
    await k.write_document("scope-x", "StoryLike", "s-1", _raw("StoryLike", "s-1"))
    # base instance cache NÃO foi dropado; holder NÃO recarregou
    assert k._kcache._base["scope-x"] is cached
    assert not holder.reload.called and not holder.reload_async.called


@pytest.mark.asyncio
async def test_record_write_still_fires_observers_and_post_save():
    k, _src, _holder = _wire()
    writes, saves = [], []
    k.on_write(lambda *a, **kw: writes.append(a))
    k.on("post_save", lambda ctx: saves.append(ctx))
    await k.write_document("scope-x", "StoryLike", "s-2", _raw("StoryLike", "s-2"))
    assert len(writes) == 1  # SSE/EventBus contract preserved
    assert len(saves) == 1   # sidecars/hooks contract preserved


@pytest.mark.asyncio
async def test_composition_write_unchanged():
    k, _src, holder = _wire()
    await k.write_document("scope-x", "AgentLike", "a-1", _raw("AgentLike", "a-1"))
    assert "scope-x" not in k._kcache._base          # base dropado
    assert holder.reload_async.called or holder.reload.called


@pytest.mark.asyncio
async def test_record_write_explicit_none_still_respected():
    k, _src, holder = _wire()
    await k.write_document(
        "scope-x", "StoryLike", "s-3", _raw("StoryLike", "s-3"),
        invalidate_mode="none",
    )
    assert not holder.reload.called and not holder.reload_async.called


def test_kind_plane_helper():
    k, _src, _holder = _wire()
    assert k.kind_plane("StoryLike") == "record"
    assert k.kind_plane("AgentLike") == "composition"
    assert k.kind_plane("NeverRegistered") == "composition"  # fail-safe


# ---------- Task 4: delete branch ----------

@pytest.mark.asyncio
async def test_record_delete_skips_scope_invalidate():
    k, _src, holder = _wire()
    cached = k._kcache._base["scope-x"]
    await k.write_document("scope-x", "StoryLike", "s-del", _raw("StoryLike", "s-del"))
    await k.delete_document("scope-x", "StoryLike", "s-del")
    assert k._kcache._base["scope-x"] is cached
    assert not holder.reload.called and not holder.reload_async.called


@pytest.mark.asyncio
async def test_record_delete_still_fires_observers_and_post_delete():
    k, _src, _holder = _wire()
    await k.write_document("scope-x", "StoryLike", "s-ev", _raw("StoryLike", "s-ev"))
    writes, dels = [], []
    k.on_write(lambda *a, **kw: writes.append(a))
    k.on("post_delete", lambda ctx: dels.append(ctx))
    await k.delete_document("scope-x", "StoryLike", "s-ev")
    assert len(writes) == 1   # evento de delete no canal SSE/EventBus
    assert len(dels) == 1     # sidecar de delete (limpeza embed/edges) recebe


@pytest.mark.asyncio
async def test_composition_delete_unchanged():
    k, _src, holder = _wire()
    await k.write_document("scope-x", "AgentLike", "a-del", _raw("AgentLike", "a-del"))
    holder.reload.reset_mock(); holder.reload_async.reset_mock()
    k._kcache._base["scope-x"] = MagicMock(name="mi2")
    await k.delete_document("scope-x", "AgentLike", "a-del")
    assert "scope-x" not in k._kcache._base
    assert holder.reload_async.called or holder.reload.called
