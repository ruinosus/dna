"""F2.5 two-planes Task 1: ManifestInstance.all/one(_async) delegate
plane="record" kinds to the kernel record-plane reads (query/get_document).

Records never come from the MI materialization — even when the eager build
happened to load them (pre-Task-2) the MI must answer record reads through
the kernel, so every legacy reader stays correct once Task 2 excludes
records from the build.

DECISÃO (plan, review r1): sync record reads from INSIDE the running event
loop RAISE (via ``_run_sync_helper``'s loud-failure contract) — no eager
fallback. Pinned here.
"""
import pytest
from unittest.mock import MagicMock

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


def _raw(kind, name, **spec):
    return {"apiVersion": "test.io/v1", "kind": kind,
            "metadata": {"name": name}, "spec": spec}


class _RecordAwareSource(_FakeWritableSource):
    """load_all returns BOTH planes (pre-Task-2 build still materializes
    records); query/load_one answer record reads and CAPTURE the calls so
    tests can assert the MI delegated instead of serving from memory."""

    def __init__(self) -> None:
        super().__init__()
        self.records = [
            _raw("StoryLike", "s-1", title="One"),
            _raw("StoryLike", "s-2", title="Two"),
        ]
        self.compositions = [_raw("AgentLike", "a-1")]
        self.query_calls: list[tuple] = []
        self.load_one_calls: list[tuple] = []

    async def load_all(self, scope, readers=None):
        return [dict(r) for r in self.records + self.compositions]

    async def query(
        self, scope, kind, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant=None,
    ):
        self.query_calls.append((scope, kind, tenant))
        for r in self.records:
            if r["kind"] == kind:
                yield dict(r)

    async def load_one(self, scope, kind, name, *, readers=None, tenant=None):
        self.load_one_calls.append((scope, kind, name, tenant))
        for r in self.records:
            if r["kind"] == kind and r["metadata"]["name"] == name:
                return dict(r)
        return None


def _wire():
    src = _RecordAwareSource()
    k = Kernel()
    k._source = src  # type: ignore[assignment]
    k.kind(_StoryLike())
    k.kind(_AgentLike())
    raw_docs = [dict(r) for r in src.records + src.compositions]
    mi = k.build(raw_docs, "scope-x")
    return k, src, mi


# ---------- sync delegation (off-loop callers: CLI, to_thread) ----------

def test_all_record_kind_delegates_to_kernel_query():
    _k, src, mi = _wire()
    with pytest.warns(DeprecationWarning):
        stories = mi.all("StoryLike")
    assert {d.name for d in stories} == {"s-1", "s-2"}
    assert any(c[1] == "StoryLike" for c in src.query_calls), (
        "mi.all(record) must delegate to kernel.query_list_sync → source.query"
    )


def test_one_record_kind_delegates_to_kernel_get_document():
    _k, src, mi = _wire()
    with pytest.warns(DeprecationWarning):
        doc = mi.one("StoryLike", "s-1")
    assert doc is not None and doc.spec["title"] == "One"
    assert any(c[1] == "StoryLike" and c[2] == "s-1" for c in src.load_one_calls), (
        "mi.one(record) must delegate to kernel.get_document_sync → source.load_one"
    )


def test_all_composition_kind_served_from_materialization():
    _k, src, mi = _wire()
    with pytest.warns(DeprecationWarning):
        agents = mi.all("AgentLike")
    assert {d.name for d in agents} == {"a-1"}
    assert not any(c[1] == "AgentLike" for c in src.query_calls), (
        "composition kinds keep the in-memory eager path — no source.query"
    )


def test_one_composition_kind_served_from_materialization():
    _k, src, mi = _wire()
    with pytest.warns(DeprecationWarning):
        doc = mi.one("AgentLike", "a-1")
    assert doc is not None
    assert not any(c[1] == "AgentLike" for c in src.load_one_calls)


# ---------- async delegation ----------

@pytest.mark.asyncio
async def test_all_async_record_kind_delegates_with_tenant():
    _k, src, mi = _wire()
    stories = await mi.all_async("StoryLike", tenant="acme")
    assert {d.name for d in stories} == {"s-1", "s-2"}
    assert ("scope-x", "StoryLike", "acme") in src.query_calls, (
        "mi.all_async(record, tenant=) must delegate to kernel.query with tenant"
    )


@pytest.mark.asyncio
async def test_all_async_record_kind_delegates_even_without_tenant():
    """Pre-F2.5 the eager MI served same-tenant all_async from memory; for
    records that path is gone — delegation always."""
    _k, src, mi = _wire()
    stories = await mi.all_async("StoryLike")
    assert {d.name for d in stories} == {"s-1", "s-2"}
    assert any(c[1] == "StoryLike" for c in src.query_calls)


@pytest.mark.asyncio
async def test_one_async_record_kind_delegates():
    _k, src, mi = _wire()
    doc = await mi.one_async("StoryLike", "s-2")
    assert doc is not None and doc.spec["title"] == "Two"
    assert any(c[1] == "StoryLike" and c[2] == "s-2" for c in src.load_one_calls)


@pytest.mark.asyncio
async def test_all_async_record_results_not_cached_in_mi():
    """Record writes never invalidate the MI — caching record reads in
    _lazy_kind_cache would serve stale data forever. Two calls = two queries."""
    _k, src, mi = _wire()
    await mi.all_async("StoryLike")
    await mi.all_async("StoryLike")
    # NB: kernel.query fires a local pass + inheritance parent pass per
    # call — count only the local-scope source queries (1 per all_async).
    assert sum(
        1 for c in src.query_calls if c[0] == "scope-x" and c[1] == "StoryLike"
    ) == 2
    assert "StoryLike" not in mi._lazy_kind_cache


# ---------- sync-on-loop raises (plan DECISÃO — no eager fallback) ----------

@pytest.mark.asyncio
async def test_sync_record_read_inside_loop_raises():
    """Sync record read on the event-loop thread must RAISE loudly (the
    _run_sync_helper contract) — these call-sites must migrate to await
    kernel.query/get_document; an eager fallback would be silent-empty
    post-exclusion (worse)."""
    _k, _src, mi = _wire()
    with pytest.warns(DeprecationWarning):
        with pytest.raises(RuntimeError, match="_run_sync_helper"):
            mi.one("StoryLike", "s-1")
    with pytest.warns(DeprecationWarning):
        with pytest.raises(RuntimeError, match="_run_sync_helper"):
            mi.all("StoryLike")


# ---------- eager MI _tenant stamping (review C2) ----------

class _NoOpCache:
    async def has(self, scope, key):
        return True

    async def load_all(self, scope, readers=None):
        return []

    async def store(self, scope, key, items):
        pass


def _wire_instance_kernel():
    """Kernel wired for the FULL instance_async path (source + cache)."""
    src = _RecordAwareSource()
    k = Kernel()
    k._source = src  # type: ignore[assignment]
    k._cache = _NoOpCache()  # type: ignore[assignment]
    k.kind(_StoryLike())
    k.kind(_AgentLike())
    return k, src


@pytest.mark.asyncio
async def test_eager_instance_tenant_layer_stamps_mi_tenant():
    """Review C2: the EAGER build (the default) must stamp ``mi._tenant``
    exactly like the lazy path does — otherwise the record-delegation
    branches read tenant=None and tenant-overlay records go invisible."""
    k, _src = _wire_instance_kernel()
    mi = await k.instance_async("scope-x", layers={"tenant": "acme"})
    assert getattr(mi, "_lazy", False) is False, "test must exercise the eager build"
    assert getattr(mi, "_tenant", None) == "acme"


@pytest.mark.asyncio
async def test_eager_instance_tenant_flows_to_delegated_record_reads():
    """Delegated record read WITHOUT an explicit tenant kwarg must carry
    the MI's request tenant down to the source query."""
    k, src = _wire_instance_kernel()
    mi = await k.instance_async("scope-x", layers={"tenant": "acme"})
    stories = await mi.all_async("StoryLike")  # no tenant kwarg
    assert {d.name for d in stories} == {"s-1", "s-2"}
    assert ("scope-x", "StoryLike", "acme") in src.query_calls, (
        "mi.all_async(record) must pass the MI request tenant to source.query"
    )


@pytest.mark.asyncio
async def test_eager_instance_base_sentinel_keeps_tenant_none():
    """The ``__base__`` sentinel means no-overlay — must NOT be stamped as
    a tenant (lazy=False bypasses the base-MI short-circuit so the real
    eager build path is exercised)."""
    k, _src = _wire_instance_kernel()
    mi = await k.instance_async(
        "scope-x", layers={"tenant": "__base__"}, lazy=False,
    )
    assert getattr(mi, "_tenant", None) is None


def test_build_with_tenant_layers_stamps_mi_tenant():
    """kernel.build (pure-compute eager constructor) stamps _tenant from
    the layers dict directly."""
    src = _RecordAwareSource()
    k = Kernel()
    k._source = src  # type: ignore[assignment]
    k.kind(_StoryLike())
    k.kind(_AgentLike())
    raw_docs = [dict(r) for r in src.records + src.compositions]
    mi = k.build(raw_docs, "scope-x", layers={"tenant": "acme"})
    assert getattr(mi, "_tenant", None) == "acme"
    mi_base = k.build(raw_docs, "scope-x", layers={"tenant": "__base__"})
    assert getattr(mi_base, "_tenant", None) is None


# ---------- mock-kernel kernels without kind_plane stay composition ----------

def test_kernel_without_kind_plane_keeps_legacy_path():
    """Kernels that don't expose kind_plane (mocks, legacy embedders) must
    never trip the record branch."""
    from dna.kernel.document import Document
    from dna.kernel.instance import ManifestInstance
    kernel = MagicMock(spec=[])  # no kind_plane attribute at all
    doc = Document.from_raw(_raw("StoryLike", "s-x"))
    mi = ManifestInstance(scope="demo", documents=[doc], kinds={}, kernel=kernel)
    with pytest.warns(DeprecationWarning):
        assert mi.all("StoryLike") == [doc]
