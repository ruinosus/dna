# Internal seams — not extension points

These are Protocols, and they are not for you.

They exist because the kernel was decomposed into collaborators (instance builder, query engine, write pipeline, …) and each collaborator's back-reference to the kernel was published as a narrow, typed slice instead of passing the whole kernel around. That keeps the decomposition honest and testable — a collaborator can only reach what its slice names.

They are listed here for one reason: **invisible is worse than "this is not for you"**. If you go looking for the extension point and find twenty-two Protocols nobody explains, you cannot tell the seams from the scaffolding. Now you can. Implementing one of these means substituting a piece of the kernel for itself, which is a fork, not an extension.

!!! info "Generated from the source"

    Names, signatures and docstrings are parsed out of `packages/sdk-py/dna`
    by `scripts/gen_ports_docs.py`. The prose around each contract is
    hand-written in `scripts/ports_prose.py`, and the generator **fails**
    if a port has none — so a new port cannot ship undocumented.

## BundleIOHost

`dna.kernel.collaborator_ports.BundleIOHost` · `@runtime_checkable` · :material-lock: internal seam

Composes [`KindLookup`](#kindlookup), [`DocStore`](#docstore).

Bundle-entry and instance (de)serialization I/O.

!!! quote "From the source"

    bundle_io — bundle-entry + instance (de)serialization I/O.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No members of its own — it is the union of the Protocols above._

## CatalogCacheHost

`dna.kernel.collaborator_ports.CatalogCacheHost` · `@runtime_checkable` · :material-lock: internal seam

Composes [`RecordQuery`](#recordquery).

The catalog-tier scope set. The cache dict is owned by the kernel and shared by identity.

!!! quote "From the source"

    CatalogCache — the Catalog-tier scope set (Phase 3b, i-112). The cache
    dict (``_catalog_cache``) is OWNED by the kernel (shared by identity across
    ``with_tenant`` copies — spec Risk #3, pinned by
    ``test_kernel_catalog_tenant_characterization``); the collaborator only
    reads/writes it through the host, keeping per-tenant KEYS the isolation
    boundary. Scans Genomes via ``query`` + reads the tenant lockfile via
    ``source_metadata``.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `list_scopes_async` | <code>async def list_scopes_async(self) -> list[str]</code> |  |
| `source_metadata` | <code>def source_metadata(self) -> dict</code> |  |

## CompositionResolverHost

`dna.kernel.collaborator_ports.CompositionResolverHost` · `@runtime_checkable` · :material-lock: internal seam

Composes [`KindLookup`](#kindlookup), [`DocStore`](#docstore), [`InheritanceCtx`](#inheritancectx), [`WriteOps`](#writeops), [`LayerObserverCtx`](#layerobserverctx).

Resolves and persists compositions, and registers the reverse-dependency observers cross-scope invalidation walks.

!!! quote "From the source"

    composition_resolver — resolves + persists compositions, and registers
    reverse-dep observers for cross-scope invalidation.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No members of its own — it is the union of the Protocols above._

## DocStore

`dna.kernel.collaborator_ports.DocStore` · `@runtime_checkable` · :material-lock: internal seam

The source port, reader/writer lists, the tenant binding, the sync↔async bridge and the granular-instance cache, as one slice.

!!! quote "From the source"

    Doc reading surface: the source port, reader/writer lists, the tenant
    binding, the sync↔async bridge loop, the doc parser, and the granular-doc
    LRU. Consumed by instance_builder, query_engine, composition_resolver,
    bundle_io, source_sync.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `_parse_doc` | <code>def _parse_doc(self, raw: dict[str, Any], origin: str='local') -> 'Instance'</code> |  |
| `_granular_doc_cached` | <code>async def _granular_doc_cached(self, key: tuple[str, str, str, str]) -> dict[str, Any] \| None</code> |  |

## InheritanceCtx

`dna.kernel.collaborator_ports.InheritanceCtx` · `@runtime_checkable` · :material-lock: internal seam

Scope-inheritance constants, the catalog scope set, the base-instance cache and the resolution-chain computation.

!!! quote "From the source"

    Scope-inheritance constants + catalog scope set + base-instance cache +
    resolution-chain compute. Consumed by instance_builder, query_engine,
    composition_resolver, layer_policy.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `_base_instance_cached` | <code>def _base_instance_cached(self, scope: str) -> Any</code> |  |
| `_base_instance_cached_async` | <code>async def _base_instance_cached_async(self, scope: str) -> Any</code> |  |
| `_catalog_scopes` | <code>async def _catalog_scopes(self, tenant: str \| None, *, exclude: set[str] \| None=None) -> list[tuple[str, str \| None]]</code> |  |
| `_compute_resolution_chain` | <code>async def _compute_resolution_chain(self, scope: str, tenant: str \| None) -> list</code> |  |

## InstanceBuildCtx

`dna.kernel.collaborator_ports.InstanceBuildCtx` · `@runtime_checkable` · :material-lock: internal seam

The cache port, composition profiles, the resolver map and the two lazy-registration hooks used while assembling a manifest instance.

!!! quote "From the source"

    MI-assembly internals beyond the shared roles: the CachePort, the
    CompositionProfile list, the ResolverPort map, and the two lazy-registration
    hooks. Consumed ONLY by instance_builder (the widest collaborator — building
    a ManifestInstance genuinely crosses much of the kernel).

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `_register_kind_definitions` | <code>def _register_kind_definitions(self, all_raws: list[dict[str, Any]], *, scope: str \| None=..., inherited_from: str \| None=...) -> bool</code> |  |
| `_register_custom_kinds` | <code>def _register_custom_kinds(self, manifest: dict[str, Any], *, scope: str \| None=...) -> None</code> |  |

## InstanceBuilderHost

`dna.kernel.collaborator_ports.InstanceBuilderHost` · `@runtime_checkable` · :material-lock: internal seam

Composes [`KindLookup`](#kindlookup), [`DocStore`](#docstore), [`InheritanceCtx`](#inheritancectx), [`InstanceBuildCtx`](#instancebuildctx).

The widest back-reference in the kernel — sixteen members across Kind lookup, instance reading, inheritance and assembly, because building a manifest instance crosses the whole kernel.

!!! quote "From the source"

    instance_builder — 16 members across kind-lookup, doc-read, inheritance,
    and MI-assembly internals. The widest back-ref (MI build crosses the kernel).

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No members of its own — it is the union of the Protocols above._

## InvalidationHost

`dna.kernel.collaborator_ports.InvalidationHost` · `@runtime_checkable` · :material-lock: internal seam

The cache-coherence state the invalidation controller fans out over. All of it stays on the kernel so `with_tenant`'s shallow-copy semantics survive.

!!! quote "From the source"

    Cache-coherence state the InvalidationController fans out over. All state
    stays on the kernel (preserves ``with_tenant`` shallow-copy semantics); the
    controller is stateless and reaches it through this narrow host — NOT the
    whole kernel. Consumed ONLY by invalidation.

    Required (always present): the four below. The controller ALSO touches three
    LAZY members — ``_write_observers``, ``_holders``, ``_layer_observers`` —
    each read defensively via ``getattr(k, name, default)`` (they are created on
    first ``on_write`` / ``register_holder`` / ``resolve_instance``). Because the
    getattr-with-default tolerates their absence, they are intentionally NOT
    required Protocol attributes.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No methods: this Protocol is satisfied by **attributes**, not calls (see the source docstring above)._

## KindLike

`dna.kernel.resource.KindLike` · `@runtime_checkable` · :material-lock: internal seam

The smallest slice of a Kind that `Resource.deps()` needs, so dependency resolution does not depend on the whole `KindPort`.

!!! quote "From the source"

    Minimal Kind interface needed by Resource.deps().

**Not an extension point.** A typing-only narrowing of `KindPort`. Any Kind you write already satisfies it — implementing it separately would mean writing a Kind that is not a Kind. If you are here to add a Kind, [`KindPort`](kinds.md#kindport) is the port you want.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `dep_filters` | <code>def dep_filters(self) -> dict[str, str] \| None</code> |  |

## KindLookup

`dna.kernel.collaborator_ports.KindLookup` · `@runtime_checkable` · :material-lock: internal seam

Registered-Kind identity, plane, storage descriptor, alias and port lookup.

!!! quote "From the source"

    Registered-Kind identity, plane, storage descriptor, alias, port lookup,
    and the lazy generic reader/writer wiring. Consumed by instance_builder,
    composition_resolver, bundle_io, source_sync, layer_policy (``_alias_for``
    plus ``kind_port_for``, to read the Kind's ``OVERLAYABLE_FIELDS``).

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `kinds_for_scope` | <code>def kinds_for_scope(self, scope: str \| None) -> 'dict[tuple[str, str], KindPort]'</code> |  |
| `kind_plane` | <code>def kind_plane(self, kind: str, *, api_version: str \| None=None, scope: str \| None=...) -> str</code> |  |
| `kind_port_for` | <code>def kind_port_for(self, kind: str, *, api_version: str \| None=None, scope: str \| None=...) -> 'KindPort \| None'</code> |  |
| `storage_for_kind` | <code>def storage_for_kind(self, kind_name: str, *, api_version: str \| None=..., scope: str \| None=...) -> 'StorageDescriptor \| None'</code> |  |
| `_alias_for` | <code>def _alias_for(self, kind: str) -> str</code> |  |
| `_ensure_generic_readers_writers` | <code>def _ensure_generic_readers_writers(self) -> None</code> |  |

## LayerObserverCtx

`dna.kernel.collaborator_ports.LayerObserverCtx` · `@runtime_checkable` · :material-lock: internal seam

The reverse-dependency graph used for cross-scope surgical invalidation. Attribute-shaped, so it declares no methods.

!!! quote "From the source"

    The Phase-17 reverse-dependency observer graph used for cross-scope
    surgical invalidation. Populated by composition_resolver.resolve_instance;
    drained by InvalidationController.invalidate_internal.

    ``_layer_observers: dict`` is a LAZY member (created on first
    ``resolve_instance``, read via ``getattr(k, "_layer_observers", None)``), so
    it is NOT a required Protocol attribute — a fresh kernel lacks it. Only the
    LRU bound below is always present (class constant).

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No methods: this Protocol is satisfied by **attributes**, not calls (see the source docstring above)._

## LayerPolicyHost

`dna.kernel.collaborator_ports.LayerPolicyHost` · `@runtime_checkable` · :material-lock: internal seam

Composes [`KindLookup`](#kindlookup), [`InheritanceCtx`](#inheritancectx).

`LOCKED` / `RESTRICTED` / `OPEN` enforcement over the base manifest instance.

!!! quote "From the source"

    layer_policy — LOCKED/RESTRICTED/OPEN enforcement over the base MI.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No members of its own — it is the union of the Protocols above._

## NamespaceGateHost

`dna.kernel.collaborator_ports.NamespaceGateHost` · `@runtime_checkable` · :material-lock: internal seam

The write-time namespace-ownership check: three members, one per question the verdict has to answer.

!!! quote "From the source"

    NamespaceOwnershipGate — the write-time namespace-ownership check (i-080
    item 1). Three members, one per question the verdict needs answered: which
    namespaces are RESERVED (derived from the live registry, never a list), who
    CLAIMS the target namespace (the ``_lib`` KindNamespace registry), and who
    the scope declares as its owner when the write carries no tenant
    (``Genome.spec.owner_tenant`` on the base instance — the same read the
    LayerPolicy check already makes).

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `kind_ports` | <code>def kind_ports(self) -> 'list[KindPort]'</code> |  |
| `kind_namespaces` | <code>async def kind_namespaces(self) -> list[dict[str, Any]]</code> |  |
| `_base_instance_cached_async` | <code>async def _base_instance_cached_async(self, scope: str) -> Any</code> |  |

## QueryEngineHost

`dna.kernel.collaborator_ports.QueryEngineHost` · `@runtime_checkable` · :material-lock: internal seam

Composes [`DocStore`](#docstore), [`InheritanceCtx`](#inheritancectx).

Read push-down: the instance-reading surface plus the inheritance fallback.

!!! quote "From the source"

    query_engine — read push-down: doc-read surface + inheritance fallback.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No members of its own — it is the union of the Protocols above._

## RecordQuery

`dna.kernel.collaborator_ports.RecordQuery` · `@runtime_checkable` · :material-lock: internal seam

The record-query push-down shared by the read-only satellites (search, catalog, registry, composition summary). Public in the sense that it is a cohesive slice — not in the sense that you implement it.

!!! quote "From the source"

    The public record-query push-down. A cohesive slice consumed by the
    read-only Fase-5 satellites (search / catalog / registry / composition
    summary) that scan records through the kernel's ``query`` facade rather
    than re-implementing source push-down. ``query`` is an async generator.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `query` | <code>def query(self, scope: str, kind: str, **kw: Any) -> Any</code> |  |

## RegistryAccessorHost

`dna.kernel.collaborator_ports.RegistryAccessorHost` · `@runtime_checkable` · :material-lock: internal seam

Composes [`RecordQuery`](#recordquery).

The registry accessor's three global reads — model profile, voice policy, embedding profile.

!!! quote "From the source"

    RegistryAccessor — the three GLOBAL ``_lib``-direct registry reads
    (``model_profile`` / ``voice_policy`` / ``embedding_profile``). Needs only
    the ``query`` push-down; the ``_lib`` scope constants live on the accessor.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No members of its own — it is the union of the Protocols above._

## RegistryHost

`dna.kernel.collaborator_ports.RegistryHost` · `@runtime_checkable` · :material-lock: internal seam

The narrow slice the Kind registry's registration funnel needs. The registry dict itself is owned by the kernel.

!!! quote "From the source"

    The narrow slice of the Kernel the KindRegistry's registration funnel
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
    required Protocol attribute (a kernel outside a load() call lacks it).

    ``_writers`` joined this contract with the UNregistration path (i-080 item
    3): a Kind that is dropped must take its auto-synthesized
    ``GenericBundleWriter`` with it, or the next registration of the same Kind
    name is skipped by the "already has a writer" check in
    ``_ensure_generic_readers_writers`` and the stale writer keeps claiming it.
    It is the exact mirror of the ``_readers`` membership already here.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `_ensure_generic_readers_writers` | <code>def _ensure_generic_readers_writers(self) -> None</code> |  |

## SearchEngineHost

`dna.kernel.collaborator_ports.SearchEngineHost` · `@runtime_checkable` · :material-lock: internal seam

Composes [`RecordQuery`](#recordquery).

Record search plus the lexical fallback, the tenant binding, and the registered provider.

!!! quote "From the source"

    SearchEngine — record ``search`` + lexical fallback. Reads the tenant
    binding (for the effective-tenant auto-stamp) and the registered provider +
    its failure-warning damper. The provider/damper STATE stays on the kernel
    (shared/per-copy exactly as before); the engine reaches it through the host.

    ``reranker`` (i-103) is reached the same way, but as a PROPERTY rather than
    an underscored field: an absent reranker is a normal, expected state — not a
    missing collaborator — so the engine asks what is registered and does
    nothing at all when the answer is ``None``.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No members of its own — it is the union of the Protocols above._

## SourceFacadeHost

`dna.kernel.collaborator_ports.SourceFacadeHost` · `@runtime_checkable` · :material-lock: internal seam

Read-only source-adapter introspection — source type, scope list, metadata. Attribute-shaped, so it declares no methods.

!!! quote "From the source"

    SourceFacade — read-only source-adapter introspection (``source_type`` /
    ``list_scopes_async`` / ``source_metadata``). Needs only the source port.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No methods: this Protocol is satisfied by **attributes**, not calls (see the source docstring above)._

## SourceSyncHost

`dna.kernel.collaborator_ports.SourceSyncHost` · `@runtime_checkable` · :material-lock: internal seam

Composes [`KindLookup`](#kindlookup), [`DocStore`](#docstore).

Digest, diff and push over the source.

!!! quote "From the source"

    source_sync — digest/diff/push over the source (s-sync-s1..s5).

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

_No members of its own — it is the union of the Protocols above._

## WriteHost

`dna.kernel.collaborator_ports.WriteHost` · typing-only (not `@runtime_checkable`) · :material-lock: internal seam

Kind identity, the writable-source guard, layer policy, hooks, and the invalidation/observer fan-out.

!!! quote "From the source"

    The narrow slice of the Kernel the WritePipeline needs — Kind identity,
    the writable source guard, layer-policy, hooks, and the invalidation /
    observer / post-hook fan-out. Every member here is a genuine write-path
    dependency; widening this Protocol is a code-review event (spec §3.1).

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `_kind_scope` | <code>def _kind_scope(self, kind: str, *, api_version: str \| None=..., scope: str \| None=...) -> 'TenantScope \| None'</code> |  |
| `kind_port_for` | <code>def kind_port_for(self, kind: str, *, api_version: str \| None=..., scope: str \| None=...) -> 'KindPort \| None'</code> |  |
| `_require_writable_source` | <code>def _require_writable_source(self) -> 'WritableSourcePort'</code> |  |
| `_check_layer_policy_async` | <code>async def _check_layer_policy_async(self, scope: str, kind: str, name: str, raw: dict, layer: tuple[str, str]) -> None</code> |  |
| `_check_namespace_ownership_async` | <code>async def _check_namespace_ownership_async(self, scope: str, kind: str, name: str, raw: dict, *, tenant: str \| None) -> None</code> |  |
| `_invalidate_granular_cache` | <code>def _invalidate_granular_cache(self, scope: str, *, kind: str \| None=..., name: str \| None=...) -> None</code> |  |
| `_invalidate_catalog_cache` | <code>def _invalidate_catalog_cache(self, tenant: str \| None=...) -> None</code> |  |
| `invalidate` | <code>def invalidate(self, *, scope: str, tenant: str=..., kind: str, name: str, op: str) -> None</code> |  |
| `_fire_write_observers` | <code>def _fire_write_observers(self, scope: str, kind: str, name: str, op: str, tenant: str=...) -> None</code> |  |

## WriteOps

`dna.kernel.collaborator_ports.WriteOps` · `@runtime_checkable` · :material-lock: internal seam

The two write entry points a collaborator may reach.

!!! quote "From the source"

    The write entry points. Consumed by composition_resolver (writes the
    materialized composition back). Future write-side collaborators (Phase 2+
    ``WritePipeline``) compose this role rather than re-holding the whole kernel.

**Not an extension point.** A back-reference from one kernel collaborator to the narrow slice of the kernel it is allowed to reach. Published as a Protocol so the slice is typed and enforceable, not so anybody outside the kernel implements it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `write_instance` | <code>async def write_instance(self, scope: str, kind: str, name: str, raw: dict, author: str \| None=None, skip_hooks: bool=False, *, tenant: str \| None=None, layer: tuple[str, str] \| None=None, invalidate_mode: str='scope', write_class: str='substantive') -> str \| None</code> |  |
| `write_bundle_entry_async` | <code>async def write_bundle_entry_async(self, scope: str, kind: str, name: str, entry: str, content: bytes \| str, *, tenant: str \| None=None) -> None</code> |  |

