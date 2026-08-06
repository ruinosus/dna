# Source capabilities — the optional slices

A source adapter's **mandatory** contract is `WritableSourcePort`. Everything a store might additionally be able to do — keep versions, hold drafts, resolve overlays, store bundle entries — is a separate, opt-in Protocol here.

These exist so the kernel never has to ask `hasattr(source, ...)`. That matters more than it sounds: the kernel needs to know what your store *cannot* do **before** it reads, so a face can refuse honestly instead of serving a confident empty answer. Read [what your declaration turns on](capabilities.md#what-your-declaration-turns-on) before you implement any of them.

!!! info "Generated from the source"

    Names, signatures and docstrings are parsed out of `packages/sdk-py/dna`
    by `scripts/gen_ports_docs.py`. The prose around each contract is
    hand-written in `scripts/ports_prose.py`, and the generator **fails**
    if a port has none — so a new port cannot ship undocumented.

## BundleEntryReadable

`dna.kernel.capabilities.BundleEntryReadable` · `@runtime_checkable` · :material-power-plug: **extension point**

**Mandatory in practice.** The adapter guide lists it alongside `WritableSourcePort` and `KernelAttachable` as what every adapter implements, and the port-contract test asserts it of all of them.

!!! quote "From the source"

    Source adapter capability: fetch a single bundle entry by name.

    The kernel uses this to read large binary payloads (graph.json,
    tree.json, ...) without rehydrating the whole bundle through the
    Reader pipeline. Implementing adapters store bundle entries in
    their backing store (filesystem dir, ``dna_bundle_entries`` SQL
    table) and serve byte payloads directly.

    Implementations may be sync (``-> bytes``) or async
    (``-> Awaitable[bytes]``). The kernel's
    ``Kernel.fetch_bundle_entry`` and
    ``Kernel.fetch_bundle_entry_async`` handle both shapes via
    ``inspect.isawaitable`` on the return value.

    Tenant overlay routing: when ``tenant`` is provided and the
    adapter supports it, the tenant-scoped copy is preferred over
    the base layer (see FilesystemWritableSource and SqlAlchemySource
    impls for the canonical 2-step lookup).

    Raises:
      - ``FileNotFoundError`` when the bundle or entry is absent
        (after the tenant overlay → base layer fallback).

    The ``kind`` kwarg is the kind name (e.g. ``"GraphifyArtifact"``)
    that owns the bundle. It's optional for backwards compatibility
    — adapters that don't need it (e.g. filesystem, where each
    container is a directory namespace) may ignore it. SQL adapters
    use it to disambiguate between two bundles that share the same
    ``name`` in the same scope but live in different containers
    (e.g. a ``Skill`` and a ``Persona`` both named ``"foo"``).
    Without ``kind``, SQL adapters fall back to a name+entry-only
    match and accept the rare collision risk documented in
    ``SqlAlchemySource.fetch_bundle_entry``.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `fetch_bundle_entry` | <code>def fetch_bundle_entry(self, scope: str, container: str, name: str, entry: str, *, tenant: str \| None=None, kind: str \| None=None) -> bytes \| Awaitable[bytes]</code> |  |
| `list_bundle_entries` | <code>def list_bundle_entries(self, scope: str, container: str, name: str, *, tenant: str \| None=None, only_tenant: bool=False, kind: str \| None=None) -> list[str] \| Awaitable[list[str]]</code> | List entry paths for a bundle. Composed = tenant overlay ∪ base (tenant rows shadow base by path). ``only_tenant`` returns just the tenant's own override rows. Empty list when the bundle is absent. |

**Swap it when** — Always. Treat this as part of the floor, not as optional.

**The minimum that works** — `fetch_bundle_entry` and `list_bundle_entries`. Both may be sync or async — the kernel awaits what is awaitable, so the filesystem adapter returns bytes directly and the SQL ones return coroutines, and both are conformant.

**What it lights up** — Declared as `bundle_read`. The production gate is an `isinstance(source, BundleEntryReadable)` in `dna.kernel.bundle.io`, **not** the flag — skip the Protocol and every bundle read raises `NotImplementedError` naming this Protocol, which is at least a good error message.

**How you prove it** — `source_conformance_suite` case `bundle_entry_round_trip`.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## BundleEntryWritable

`dna.kernel.capabilities.BundleEntryWritable` · `@runtime_checkable` · :material-power-plug: **extension point**

The write half of the pair above. Same rules, same gate.

!!! quote "From the source"

    Source adapter capability: persist a single bundle entry payload.

    Write twin of ``BundleEntryReadable`` — used by tools and HTTP
    handlers that need to put a binary payload (PNG/JPG/JSON blob)
    into a bundle's storage WITHOUT going through the WriterPort
    serialize pipeline (which only emits text entries).

    Source-agnostic by design: the kernel's
    ``Kernel.write_bundle_entry_async`` dispatches to this method on
    the active source, so callers can switch between FS / SQLite /
    Postgres without rewriting the binary persistence path. Adapters
    bound their own atomicity guarantees — Postgres uses a single
    transaction with the doc write; filesystem writes the file
    directly under the bundle dir; SQLite uses a single sqlite
    transaction.

    Tenant scoping: writes MUST honor the active tenant just like
    the doc index — see ``WritableSourcePort.write_instance``. A
    mismatch produces orphan bundle rows that the delete path can't
    reach (bug observed 2026-05-21 with generate_image hardcoding
    ``tenant=''``).

    Args:
      - scope: scope identifier
      - container: Kind name owning the bundle (e.g. "ImagePrompt")
      - name: doc name (e.g. "img-iu-dna-overview-kernel")
      - entry: entry path within the bundle (e.g. "output.png")
      - content: raw bytes
      - tenant: active tenant; pass through from the caller's context

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `write_bundle_entry` | <code>def write_bundle_entry(self, scope: str, container: str, name: str, entry: str, content: bytes, *, tenant: str \| None=None, kind: str \| None=None) -> None \| Awaitable[None]</code> |  |
| `delete_bundle_entry` | <code>def delete_bundle_entry(self, scope: str, container: str, name: str, entry: str, *, tenant: str \| None=None, kind: str \| None=None) -> bool \| Awaitable[bool]</code> | Delete ONE entry row for ``tenant`` (base sentinel '' when None). Returns True if a row existed. Reverting a tenant fork deletes the tenant row so the base entry composes through again. |

**Swap it when** — Whenever your source is writable at all.

**The minimum that works** — `write_bundle_entry` and `delete_bundle_entry`; sync or async.

**What it lights up** — Declared as `bundle_write`; gated in production by `isinstance` in `dna.kernel.bundle.io`. Skip it and bundle writes raise, naming the Protocol.

**How you prove it** — `source_conformance_suite` case `bundle_entry_round_trip`.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## Draftable

`dna.kernel.capabilities.Draftable` · `@runtime_checkable` · :material-power-plug: **extension point**

Instances that exist before they are live.

!!! quote "From the source"

    Source adapter capability: draft/publish lifecycle.

    A ``Draftable`` source keeps unpublished drafts (``load_drafts``)
    and can promote a draft to the live instance (``publish``). All 3
    production adapters implement this — the old ``capabilities()``
    dicts that reported ``drafts: False`` for the filesystem were
    lying; ``isinstance(src, Draftable)`` reports the truth.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `load_drafts` | <code>async def load_drafts(self, scope: str) -> list[dict]</code> |  |
| `publish` | <code>async def publish(self, scope: str, kind: str, name: str) -> str</code> |  |

**Swap it when** — Your store can hold an unpublished instance that reads do not see. If publishing is a no-op for you (as on the filesystem), declare `drafts=False`.

**The minimum that works** — `load_drafts` **and** `publish` — the probe requires both.

**What it lights up** — The `drafts` flag and the draft lifecycle across the faces. Undeclared, everything written is immediately live.

**How you prove it** — `source_conformance_suite` case `drafts_lifecycle`.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## KernelAttachable

`dna.kernel.capabilities.KernelAttachable` · `@runtime_checkable` · :material-power-plug: **extension point**

**Mandatory.** The kernel hands itself to the adapter once wiring is done, so the adapter can reach the Kind registry it needs to interpret what it is storing.

!!! quote "From the source"

    Source adapter capability: accept post-init kernel wiring.

    H2 unification: ``Kernel.auto(source=...)`` previously had a
    hardcoded ``isinstance(source, FilesystemWritableSource)`` check
    that wired ``source._writers`` and ``source.set_kernel(k)``. SQLite
    and Postgres sources required the same wiring but only got it via
    the runtime source factory — leaving direct
    ``Kernel.auto(source=SqlAlchemySource(...))`` callers with a
    half-broken kernel that silently dropped bundle writes.

    Adapters now declare attachability by implementing
    ``attach_kernel(kernel)``. The kernel calls this method on every
    source it accepts — uniformly. Implementations install the
    kernel's ``_writers``, ``_readers``, and (optionally) a back-ref
    to the kernel itself for the source's save path to consult
    ``storage_for_kind``.

    The contract: attach is idempotent. Calling twice with the same
    kernel produces the same wired state.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `attach_kernel` | <code>def attach_kernel(self, kernel: object) -> None</code> |  |

**Swap it when** — Always. The port-contract test asserts every adapter implements it.

**The minimum that works** — `attach_kernel(kernel)`, and it **must be idempotent** — it can be called more than once, and a non-idempotent implementation corrupts state in ways that surface far from the cause.

**What it lights up** — Declared as `kernel_attachable`; gated by `isinstance` at boot. Uniquely on this page the failure is **fail-soft** — boot logs a warning and continues, so a missing `attach_kernel` shows up later as an adapter that cannot resolve Kinds rather than as a boot error. Do not rely on boot to tell you.

**How you prove it** — `packages/sdk-py/tests/test_port_contract.py` asserts it of every adapter; the kit's `port_surface` case covers the shape.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## LayerAware

`dna.kernel.capabilities.LayerAware` · `@runtime_checkable` · :material-power-plug: **extension point**

The `layer=` twin of `TenantAware`, with the identical caveat.

!!! quote "From the source"

    Source adapter capability: writes accept a ``layer`` overlay kwarg.

    Same ``runtime_checkable`` caveat as :class:`TenantAware` — use
    :func:`write_kwarg_support` for the runtime kwarg decision; this Protocol is
    for documentation + static typing.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `save_instance` | <code>async def save_instance(self, scope: str, kind: str, name: str, raw: dict, *, layer: tuple[str, str] \| None=...) -> str</code> |  |

**Swap it when** — Same as `TenantAware` — you want the contract expressed in types.

**The minimum that works** — `save_instance` accepting `layer=`, plus the matching `write_kwargs` entry.

**What it lights up** — The layer half of `tenant_layer_writes`. Same trap: use `write_kwarg_support`, not `isinstance`.

**How you prove it** — `source_conformance_suite` case `declared_write_kwargs_accepted`.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## Layered

`dna.kernel.capabilities.Layered` · `@runtime_checkable` · :material-power-plug: **extension point**

Resolving an instance through an overlay — the mechanism behind tenancy and per-customer forks.

!!! quote "From the source"

    Source adapter capability: layer (overlay) resolution.

    A ``Layered`` source can resolve an instance from a specific layer
    via ``load_layer`` — the method the Composition Engine consults
    for overlay/inheritance reads. sqlite/postgres and the composite
    filesystem router implement it; the flat filesystem writable does
    not (it can list layer values but not resolve them).

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `load_layer` | <code>async def load_layer(self, scope: str, layer_id: str, layer_value: str, kind: str, name: str) -> dict \| None</code> |  |

**Swap it when** — Your store can key an instance by an overlay dimension as well as by name.

**The minimum that works** — `load_layer`, returning `None` for an unknown layer rather than raising.

**What it lights up** — The `layers` flag and the overlay engine. ⚠️ The known divergence to inherit or fix: the SQLite dialect's `instances` primary key omits `tenant`, so an overlay publish clobbers the base row. It is a `strict=True` xfail in both the matrix and the conformance kit's `_KNOWN` divergence table. Postgres passes with identical logic — this is schema debt, not a design limit — so if your store can key by tenant, key by tenant.

**How you prove it** — `source_conformance_suite` case `tenant_overlay_shadows_base`, and the matrix's `test_tenant_overlay_shadows_base` row.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## TenantAware

`dna.kernel.capabilities.TenantAware` · `@runtime_checkable` · :material-power-plug: **extension point**

Documentation and static typing. Read the warning — this Protocol is the one place on this page where `isinstance` is the **wrong** tool, and the source says so itself.

!!! quote "From the source"

    Source adapter capability: ``save_instance``/``delete_instance`` accept a
    first-class ``tenant`` kwarg (the modern WritableSourcePort write contract,
    Phase 2). All 3 production adapters satisfy it.

    NOTE: ``runtime_checkable`` ``isinstance`` only checks that the *methods*
    exist, NOT that they accept a ``tenant`` keyword — Protocols can't express a
    kwarg-level capability. So this Protocol instances the contract + serves
    static checking, while the kernel's runtime branch that decides whether to
    pass ``tenant=`` uses :func:`write_kwarg_support` (a memoized signature
    probe) instead. Don't ``isinstance(src, TenantAware)`` to gate the tenant
    kwarg — it would be True for any source with a ``save_instance`` at all.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `save_instance` | <code>async def save_instance(self, scope: str, kind: str, name: str, raw: dict, *, tenant: str \| None=...) -> str</code> |  |
| `delete_instance` | <code>async def delete_instance(self, scope: str, kind: str, name: str, *, tenant: str \| None=...) -> None</code> |  |

**Swap it when** — You are writing a source adapter and want your editor and type-checker to hold you to the modern write contract. Declare the *behaviour* through `capabilities().write_kwargs`, which is what the kernel actually reads.

**The minimum that works** — `save_instance` / `delete_instance` accepting `tenant=`, and `"tenant"` present in your declared `write_kwargs` / `delete_kwargs`.

**What it lights up** — The `tenant_layer_writes` flag and the tenant kwarg being passed at all. ⚠️ **Never gate on `isinstance(src, TenantAware)`.** A `runtime_checkable` Protocol checks that methods *exist*, never that they accept a keyword — so that check is `True` for any source with a `save_instance` at all, including ones that would reject the kwarg. The kernel uses `write_kwarg_support(src)`, a memoized signature probe, and so should you.

**How you prove it** — `source_conformance_suite` case `declared_write_kwargs_accepted`, which checks your declaration against what your signatures really take.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## Versionable

`dna.kernel.capabilities.Versionable` · `@runtime_checkable` · :material-power-plug: **extension point**

Your store can return a specific published version of an instance. Worth reading the caveat below before you declare it.

!!! quote "From the source"

    Source adapter capability: per-Kind semver versioning.

    Backs the catalog versioning flow: an adapter that is ``Versionable``
    supports ``get_version(scope, kind, name, version_id)`` and
    ``list_versions(...)``.

    The runtime gate is the DECLARED ``SourceCapabilities.versions`` flag,
    not an ``isinstance`` against this Protocol — there is no such check
    anywhere in the tree. Implement the Protocol for static typing and for
    the reader; declare the flag for the kernel.

    ⚠️ ``versions`` says version rows are READABLE and nothing more. The
    filesystem adapter declares it while keeping no history at all
    (``list_versions`` returns ``[]``), which is precisely why answering
    "what did you believe at T?" had to become its OWN flag
    (:attr:`SourceCapabilities.as_of_reads`) rather than riding on this
    one. Do not widen this docstring's promise again: an earlier version
    of it claimed an ``isinstance`` check and a
    ``/catalog/{owner}/{name}/versions`` endpoint, and neither existed.

    The production adapters (FilesystemWritableSource and SqlAlchemySource
    on both dialects) implement this. An adapter that does not track
    per-instance versions declares ``versions=False`` and the faces refuse
    the version reads rather than inventing an answer.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `get_version` | <code>async def get_version(self, scope: str, kind: str, name: str, version_id: str) -> dict</code> |  |

**Swap it when** — Your store keeps version rows and can hand back a past one by id. If it does not, do not declare `versions` — see the trap.

**The minimum that works** — `get_version`.

**What it lights up** — The `versions` flag, which says **version rows are readable** and nothing more. ⚠️ It does *not* mean history exists: the filesystem adapter declares `versions=True` and `list_versions` returns `[]`. That gap is exactly why the ability to answer *what did you believe at time T* became a **separate** flag, `as_of_reads` — a store that cannot reconstruct the past must let the face raise `AsOfUnsupported` (REST **501**) rather than serve today's instance under yesterday's timestamp. And when history existed but was pruned, that is `AsOfTruncated` (REST **410**), never a `LookupError`: *the instance did not exist yet* is an answer, and must not render the same as *I no longer hold the record*.

**How you prove it** — `source_conformance_suite` case `versions_surface`.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## What your declaration turns on

Every capability above is declared, not sniffed. Your adapter returns one
`SourceCapabilities` literal from `capabilities()`, and the kernel consults
that declaration — never `hasattr`, never `inspect`.

That indirection is the point. It exists because the previous design was a
per-adapter dict of magic strings whose keys and sync/async shape drifted
between backends, and which **lied**: the filesystem adapter claimed
`versions: False` while implementing `get_version`. A declaration can be
checked against reality; a `hasattr` cannot.

### The declaration

```python
def capabilities(self) -> SourceCapabilities:
    return SourceCapabilities(
        source="mystore",
        drafts=False, versions=False, layers=True,
        bundle_read=True, bundle_write=True, kernel_attachable=True,
        granular_list=True, granular_one=True,
        query_pushdown=True, tenant_layer_writes=True,
        api_version_identity=True, as_of_reads=False, edge_graph=False,
        write_kwargs=frozenset({"tenant", "layer", "if_absent"}),
        delete_kwargs=frozenset({"tenant"}),
    )
```

Declare conservatively. An undeclared capability means a feature is off; an
over-declared one means the kernel hands you work you will silently drop, and
the conformance kit's `capabilities_declared_honestly` case exists to catch
exactly that before a user does.

### ⭐ Why an honest `False` is a feature, not an admission

This is the part of the port contract that is genuinely non-obvious, and it is
what separates a trustworthy adapter from a merely working one.

> **A store that cannot answer must refuse, not approximate.**

Take the reference graph. A store with no edge table does **not** return an
empty list. The kernel's own words:

!!! quote "`dna/kernel/query/graph.py`"

    A store without an edge table does not return an empty list. `[]` reads as
    "nothing points at this instance", which is a claim only a store that
    actually records edges may make; the filesystem adapter has neither a
    transaction to write edges in nor a table to write them to, so the answer
    is `GraphUnsupported` and the face says so. Serving a confident empty
    answer from a store that cannot know is the fail-open silence this codebase
    treats as a defect, not a convenience.

The same reasoning produced `as_of_reads` as a flag separate from `versions`,
and it is why these questions must be askable **before** the read rather than
discovered during it.

| You declare | Asked anyway, the face answers | Not |
|---|---|---|
| `edge_graph=False` | `GraphUnsupported` → REST **501** | `[]` |
| `as_of_reads=False` | `AsOfUnsupported` → REST **501** | today's instance under a past timestamp |
| history pruned | `AsOfTruncated` → REST **410** | `LookupError` — *"it did not exist yet"* is a different answer from *"I no longer hold the record"* |
| no `find_instances_by_id_prefix` | `InstanceIdLookupUnsupported` → REST **501** | an empty result set |
| `edges` not in `write_kwargs` | the kernel never hands you edges | your adapter silently dropping them |

Neither `GraphUnsupported` nor `InstanceIdLookupUnsupported` is a
`KernelRefusal`, and the distinction is deliberate: a refusal is a verdict on
*the request*, which the caller might appeal. These are statements about *the
deployment*. The caller's remedy is a different adapter, not a different
request.

### The three tiers

The eight Protocols on this page are not equally optional.

| Tier | Protocols | What it means |
|---|---|---|
| **Mandatory** | `KernelAttachable`, `BundleEntryReadable`, `BundleEntryWritable` | Gated by a real `isinstance` in production. The port-contract test asserts every shipped adapter implements them. Treat them as part of the floor. |
| **Optional, declaration-driven** | `Versionable`, `Draftable`, `Layered` | No `isinstance` anywhere today — the runtime gate is the corresponding flag (`versions` / `drafts` / `layers`). Implement the Protocol for typing and clarity; the flag is what actually decides. |
| **Typing only — do not gate on these** | `TenantAware`, `LayerAware` | ⚠️ `runtime_checkable` checks that a *method exists*, never that it accepts a *keyword*. `isinstance(src, TenantAware)` is `True` for any source with a `save_instance` at all. Use `write_kwarg_support(src)`. The source file warns about this in both classes. |
