"""Narrow role-Protocols the kernel's collaborators depend on — the death of the
implicit god-interface (``s-kernel-decomp-f1``, épico ``e-kernel-decomposition``).

Before this module, the ~7 kernel collaborators that hold a back-ref
(``self._k = kernel``) typed it as the WHOLE ``Kernel`` (~35 private members /
117 methods) even though each consumes a *median of 4-5* members. That back-ref
was a god-interface pushed one layer down: any collaborator could touch anything,
so none was unit-testable in isolation and the coupling was total.

This module defines **role-Protocols** — cohesive slices of the kernel surface,
each listing ONLY members that ≥1 collaborator consumes — plus one **composite
host Protocol per collaborator** (`*Host`) built by multiple-inheritance of the
roles it needs. Each collaborator's ``__init__`` now declares its narrow ``*Host``
instead of ``Kernel``. There is **zero runtime change**: the ``Kernel`` (and its
``with_tenant`` shallow copy) satisfies every Protocol *structurally*, so the
kernel still passes ``self`` when it wires each collaborator.

The boundary is frozen mechanically by ``tests/test_kernel_collaborator_ports.py``
(``FakeKernelSlice`` guard): each collaborator is exercised with a fake exposing
ONLY its ``*Host`` surface — reach for a member outside the contract and the fake
raises ``AttributeError``. Widening a back-ref now requires widening a Protocol in
code review (anti-cosmetic-decomposition guard, spec §3.1 / anti-goal §5.3).

Roles (member → which of the 7 back-ref collaborators consume it, per Apêndice B):

- ``KindLookup``    — kind identity / plane / storage / alias / generic-rw wiring.
- ``DocStore``      — source read + parse + granular-doc cache + sync↔async bridge.
- ``InheritanceCtx``— inheritance constants + catalog + base-instance cache + chain.
- ``WriteOps``      — the two write entry points (composition_resolver writes back).
- ``InstanceBuildCtx`` — extra MI-assembly internals (instance_builder only).
- ``LayerObserverCtx`` — the Phase-17 reverse-dep observer graph (composition_resolver).
- ``InvalidationHost``  — batch/observer/holder state + kcache (invalidation only).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover — typing-only, no runtime import cost
    import asyncio

    from dna.kernel.document import Document
    from dna.kernel.boot.cache import KernelCache
    from dna.kernel.protocols import (
        CachePort,
        KindPort,
        ReaderPort,
        ResolverPort,
        SourcePort,
        StorageDescriptor,
        WriterPort,
    )


# ---------------------------------------------------------------------------
# Role-Protocols — cohesive slices, each member consumed by ≥1 collaborator
# ---------------------------------------------------------------------------


@runtime_checkable
class KindLookup(Protocol):
    """Registered-Kind identity, plane, storage descriptor, alias, and the
    lazy generic reader/writer wiring. Consumed by instance_builder,
    composition_resolver, bundle_io, source_sync, layer_policy (``_alias_for``)."""

    _kinds: "dict[tuple[str, str], KindPort]"

    def kind_plane(self, kind: str, *, api_version: str | None = None) -> str: ...

    def storage_for_kind(self, kind_name: str) -> "StorageDescriptor | None": ...

    def _alias_for(self, kind: str) -> str: ...

    def _ensure_generic_readers_writers(self) -> None: ...


@runtime_checkable
class DocStore(Protocol):
    """Doc reading surface: the source port, reader/writer lists, the tenant
    binding, the sync↔async bridge loop, the doc parser, and the granular-doc
    LRU. Consumed by instance_builder, query_engine, composition_resolver,
    bundle_io, source_sync."""

    _source: "SourcePort | None"
    _readers: "list[ReaderPort]"
    _writers: "list[WriterPort]"
    tenant: str | None
    _main_loop: "asyncio.AbstractEventLoop | None"

    def _parse_doc(self, raw: dict[str, Any], origin: str = "local") -> "Document": ...

    async def _granular_doc_cached(
        self, key: tuple[str, str, str, str]
    ) -> dict[str, Any] | None: ...


@runtime_checkable
class InheritanceCtx(Protocol):
    """Scope-inheritance constants + catalog scope set + base-instance cache +
    resolution-chain compute. Consumed by instance_builder, query_engine,
    composition_resolver, layer_policy."""

    _INHERIT_PARENT_SCOPE: str
    _INHERITABLE_KINDS: "frozenset[str]"
    _NON_OVERLAYABLE_KINDS: "frozenset[str]"

    def _base_instance_cached(self, scope: str) -> Any: ...

    async def _base_instance_cached_async(self, scope: str) -> Any: ...

    async def _catalog_scopes(
        self, tenant: str | None, *, exclude: set[str] | None = None
    ) -> list[tuple[str, str | None]]: ...

    async def _compute_resolution_chain(
        self, scope: str, tenant: str | None
    ) -> list: ...


@runtime_checkable
class WriteOps(Protocol):
    """The write entry points. Consumed by composition_resolver (writes the
    materialized composition back). Future write-side collaborators (Phase 2+
    ``WritePipeline``) compose this role rather than re-holding the whole kernel."""

    async def write_document(
        self,
        scope: str,
        kind: str,
        name: str,
        raw: dict,
        author: str | None = None,
        skip_hooks: bool = False,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        invalidate_mode: str = "scope",
        write_class: str = "substantive",
    ) -> str | None: ...

    async def write_bundle_entry_async(
        self,
        scope: str,
        kind: str,
        name: str,
        entry: str,
        content: bytes | str,
        *,
        tenant: str | None = None,
    ) -> None: ...


@runtime_checkable
class InstanceBuildCtx(Protocol):
    """MI-assembly internals beyond the shared roles: the CachePort, the
    CompositionProfile list, the ResolverPort map, and the two lazy-registration
    hooks. Consumed ONLY by instance_builder (the widest collaborator — building
    a ManifestInstance genuinely crosses much of the kernel)."""

    _cache: "CachePort | None"
    _profiles: list
    _resolvers: "dict[str, ResolverPort]"

    def _register_kind_definitions(self, all_raws: list[dict[str, Any]]) -> bool: ...

    def _register_custom_kinds(self, manifest: dict[str, Any]) -> None: ...


@runtime_checkable
class LayerObserverCtx(Protocol):
    """The Phase-17 reverse-dependency observer graph used for cross-scope
    surgical invalidation. Populated by composition_resolver.resolve_document;
    drained by InvalidationController.invalidate_internal.

    ``_layer_observers: dict`` is a LAZY member (created on first
    ``resolve_document``, read via ``getattr(k, "_layer_observers", None)``), so
    it is NOT a required Protocol attribute — a fresh kernel lacks it. Only the
    LRU bound below is always present (class constant)."""

    _LAYER_OBSERVERS_MAX: int


@runtime_checkable
class InvalidationHost(Protocol):
    """Cache-coherence state the InvalidationController fans out over. All state
    stays on the kernel (preserves ``with_tenant`` shallow-copy semantics); the
    controller is stateless and reaches it through this narrow host — NOT the
    whole kernel. Consumed ONLY by invalidation.

    Required (always present): the four below. The controller ALSO touches three
    LAZY members — ``_write_observers``, ``_holders``, ``_layer_observers`` —
    each read defensively via ``getattr(k, name, default)`` (they are created on
    first ``on_write`` / ``register_holder`` / ``resolve_document``). Because the
    getattr-with-default tolerates their absence, they are intentionally NOT
    required Protocol attributes."""

    _SCHEMA_INVALIDATING_KINDS: "frozenset[str]"
    _batch_mode_depth: int
    _batch_pending: list
    _kcache: "KernelCache"


# ---------------------------------------------------------------------------
# Composite host Protocols — one per back-ref collaborator (multiple-inheritance
# of the roles it consumes). This is the type each ``__init__`` now declares.
# ---------------------------------------------------------------------------


@runtime_checkable
class InstanceBuilderHost(
    KindLookup, DocStore, InheritanceCtx, InstanceBuildCtx, Protocol
):
    """instance_builder — 16 members across kind-lookup, doc-read, inheritance,
    and MI-assembly internals. The widest back-ref (MI build crosses the kernel)."""


@runtime_checkable
class QueryEngineHost(DocStore, InheritanceCtx, Protocol):
    """query_engine — read push-down: doc-read surface + inheritance fallback."""


@runtime_checkable
class RecordQuery(Protocol):
    """The public record-query push-down. A cohesive slice consumed by the
    read-only Fase-5 satellites (search / catalog / registry / composition
    summary) that scan records through the kernel's ``query`` facade rather
    than re-implementing source push-down. ``query`` is an async generator."""

    def query(self, scope: str, kind: str, **kw: Any) -> Any: ...


@runtime_checkable
class CompositionResolverHost(
    KindLookup, DocStore, InheritanceCtx, WriteOps, LayerObserverCtx, Protocol
):
    """composition_resolver — resolves + persists compositions, and registers
    reverse-dep observers for cross-scope invalidation."""


@runtime_checkable
class BundleIOHost(KindLookup, DocStore, Protocol):
    """bundle_io — bundle-entry + document (de)serialization I/O."""


@runtime_checkable
class SourceSyncHost(KindLookup, DocStore, Protocol):
    """source_sync — digest/diff/push over the source (s-sync-s1..s5)."""


@runtime_checkable
class LayerPolicyHost(KindLookup, InheritanceCtx, Protocol):
    """layer_policy — LOCKED/RESTRICTED/OPEN enforcement over the base MI."""


__all__ = [
    "KindLookup",
    "DocStore",
    "InheritanceCtx",
    "WriteOps",
    "InstanceBuildCtx",
    "LayerObserverCtx",
    "InvalidationHost",
    "RecordQuery",
    "InstanceBuilderHost",
    "QueryEngineHost",
    "CompositionResolverHost",
    "BundleIOHost",
    "SourceSyncHost",
    "LayerPolicyHost",
    "RegistryAccessorHost",
    "SearchEngineHost",
    "CatalogCacheHost",
    "SourceFacadeHost",
]


@runtime_checkable
class RegistryHost(Protocol):
    """The narrow slice of the Kernel the KindRegistry's registration funnel
    needs (``s-kernel-decomp-f3-kindregistry``). The ``_kinds`` dict itself is
    OWNED by the registry — not reached through the host; this host is only the
    fan-out surface registration touches on the wider kernel: the hook registry
    (``kinddef_conflict`` / ``parse_error`` events), the ``_readers`` list (the
    2-phase-load rescan return gate), the generic reader/writer wiring, and the
    ``_generics_resolved`` flag it flips on every successful register. Every
    member is a genuine registration dependency; widening it is a code-review
    event (spec §3.1 / anti-goal §5.3).

    ``_loading_ext_owner`` (the per-``load()`` alias-owner context) is a LAZY
    member — set only inside ``kernel.load()`` and read via
    ``getattr(host, "_loading_ext_owner", None)`` — so it is intentionally NOT a
    required Protocol attribute (a kernel outside a load() call lacks it)."""

    hooks: Any
    _readers: list
    _generics_resolved: bool

    def _ensure_generic_readers_writers(self) -> None: ...


class WriteHost(Protocol):
    """The narrow slice of the Kernel the WritePipeline needs — Kind identity,
    the writable source guard, layer-policy, hooks, and the invalidation /
    observer / post-hook fan-out. Every member here is a genuine write-path
    dependency; widening this Protocol is a code-review event (spec §3.1)."""

    hooks: Any
    tenant: str | None
    _kcache: Any

    def _kind_scope(
        self, kind: str, *, api_version: str | None = ...,
    ) -> "TenantScope | None": ...

    def kind_port_for(
        self, kind: str, *, api_version: str | None = ...,
    ) -> "KindPort | None": ...

    def _require_writable_source(self) -> "WritableSourcePort": ...

    async def _check_layer_policy_async(
        self, scope: str, kind: str, name: str, raw: dict,
        layer: tuple[str, str],
    ) -> None: ...

    def _invalidate_granular_cache(
        self, scope: str, *, kind: str | None = ..., name: str | None = ...,
    ) -> None: ...

    def _invalidate_catalog_cache(self, tenant: str | None = ...) -> None: ...

    def invalidate(
        self, *, scope: str, tenant: str = ..., kind: str, name: str, op: str,
    ) -> None: ...

    def _fire_write_observers(
        self, scope: str, kind: str, name: str, op: str, tenant: str = ...,
    ) -> None: ...


# ---------------------------------------------------------------------------
# Fase 5 satellite hosts — read-only, fail-soft leaf extractions
# (``s-kernel-decomp-f5-satellites``). Each is a narrow slice; the kernel keeps
# the public method as a thin facade delegating to the collaborator.
# ---------------------------------------------------------------------------


@runtime_checkable
class RegistryAccessorHost(RecordQuery, Protocol):
    """RegistryAccessor — the three GLOBAL ``_lib``-direct registry reads
    (``model_profile`` / ``voice_policy`` / ``embedding_profile``). Needs only
    the ``query`` push-down; the ``_lib`` scope constants live on the accessor."""


@runtime_checkable
class SearchEngineHost(RecordQuery, Protocol):
    """SearchEngine — record ``search`` + lexical fallback. Reads the tenant
    binding (for the effective-tenant auto-stamp) and the registered provider +
    its failure-warning damper. The provider/damper STATE stays on the kernel
    (shared/per-copy exactly as before); the engine reaches it through the host."""

    tenant: str | None
    _search_provider: Any
    _search_provider_warned: bool


@runtime_checkable
class CatalogCacheHost(RecordQuery, Protocol):
    """CatalogCache — the Catalog-tier scope set (Phase 3b, i-112). The cache
    dict (``_catalog_cache``) is OWNED by the kernel (shared by identity across
    ``with_tenant`` copies — spec Risk #3, pinned by
    ``test_kernel_catalog_tenant_characterization``); the collaborator only
    reads/writes it through the host, keeping per-tenant KEYS the isolation
    boundary. Scans Genomes via ``query`` + reads the tenant lockfile via
    ``source_metadata``."""

    _INHERIT_PARENT_SCOPE: str
    _GRANULAR_DOC_TTL: float
    _catalog_cache: "dict[str | None, tuple[float, list[tuple[str, str | None]]]]"

    async def list_scopes_async(self) -> list[str]: ...

    def source_metadata(self) -> dict: ...


@runtime_checkable
class SourceFacadeHost(Protocol):
    """SourceFacade — read-only source-adapter introspection (``source_type`` /
    ``list_scopes_async`` / ``source_metadata``). Needs only the source port."""

    _source: "SourcePort | None"
