"""Optional capability Protocols for source/cache/etc adapters.

H2 — Replaces the ``hasattr(self._source, "fetch_bundle_entry")`` pattern
in the kernel (and equivalent leaks) with discoverable, type-checkable
``isinstance(source, BundleEntryReadable)`` checks.

Why these are separate from the core ``SourcePort`` Protocol:

  - The core Protocols (SourcePort, WritableSourcePort, CachePort, ...)
    define the **mandatory** contract every adapter must implement.
  - These capability Protocols define **optional** features — adapters
    can declare support by structurally matching the signature, OR
    omit the methods entirely without breaking the core contract.
  - Discoverable: a developer authoring a custom adapter sees the
    available capabilities by importing this module, instead of
    grepping the kernel source for ``hasattr`` calls.

All Protocols here are ``runtime_checkable`` so ``isinstance(x, Cap)``
works at runtime (Python's structural-typing semantics for Protocol).

Adding a new capability:
  1. Define ``MyCapability(Protocol)`` with ``@runtime_checkable`` and
     the method signature.
  2. Replace any ``hasattr(adapter, "method")`` in the kernel/harness
     with ``isinstance(adapter, MyCapability)``.
  3. Document the capability in `docs/PORT-CONTRACT.md`.
  4. Cover it in ``python/tests/test_port_contract.py`` so adapters
     either implement it or get explicitly skipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Protocol, runtime_checkable


@runtime_checkable
class BundleEntryReadable(Protocol):
    """Source adapter capability: fetch a single bundle entry by name.

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
    """

    def fetch_bundle_entry(
        self,
        scope: str,
        container: str,
        name: str,
        entry: str,
        *,
        tenant: str | None = None,
        kind: str | None = None,
    ) -> bytes | Awaitable[bytes]: ...


@runtime_checkable
class BundleEntryWritable(Protocol):
    """Source adapter capability: persist a single bundle entry payload.

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
    the doc index — see ``WritableSourcePort.write_document``. A
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
    """

    def write_bundle_entry(
        self,
        scope: str,
        container: str,
        name: str,
        entry: str,
        content: bytes,
        *,
        tenant: str | None = None,
        kind: str | None = None,
    ) -> None | Awaitable[None]: ...


@runtime_checkable
class Versionable(Protocol):
    """Source adapter capability: per-Kind semver versioning.

    Backs the catalog versioning flow (Phase 10): a Kind that's
    ``Versionable`` supports ``get_version(scope, kind, name,
    version_id)`` and ``list_versions(...)``. The harness REST
    surface checks for this capability via ``isinstance`` to
    decide whether to expose the ``/catalog/{owner}/{name}/versions``
    endpoint (501 otherwise).

    The production adapters (FilesystemWritableSource and
    SqlAlchemySource on both dialects) implement this. Custom adapters
    that don't track per-doc versions can omit and the harness
    will degrade gracefully with a 501 response.
    """

    async def get_version(
        self, scope: str, kind: str, name: str, version_id: str,
    ) -> dict: ...


@runtime_checkable
class Draftable(Protocol):
    """Source adapter capability: draft/publish lifecycle.

    A ``Draftable`` source keeps unpublished drafts (``load_drafts``)
    and can promote a draft to the live document (``publish``). All 3
    production adapters implement this — the old ``capabilities()``
    dicts that reported ``drafts: False`` for the filesystem were
    lying; ``isinstance(src, Draftable)`` reports the truth.
    """

    async def load_drafts(self, scope: str) -> list[dict]: ...

    async def publish(self, scope: str, kind: str, name: str) -> str: ...


@runtime_checkable
class Layered(Protocol):
    """Source adapter capability: layer (overlay) resolution.

    A ``Layered`` source can resolve a document from a specific layer
    via ``load_layer`` — the method the Composition Engine consults
    for overlay/inheritance reads. sqlite/postgres and the composite
    filesystem router implement it; the flat filesystem writable does
    not (it can list layer values but not resolve them).
    """

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        kind: str, name: str,
    ) -> dict | None: ...


@dataclass(frozen=True)
class SourceCapabilities:
    """Typed, uniformly-sync view of what a source adapter supports.

    Replaces the per-adapter ``dict`` of magic-strings whose keys AND
    sync/async shape drifted between FS/SQLite/Postgres (and which lied
    — FS claimed ``versions: False`` while implementing ``get_version``).

    s-sourceport-contract-cleanup: adapters now DECLARE this explicitly
    (each ``capabilities()`` returns a literal). The kernel consults the
    declaration — never ``hasattr``/``inspect`` — via
    :func:`source_capabilities`. :func:`derive_capabilities` (reflection)
    survives as (a) the conformance-test oracle that keeps declarations
    honest, and (b) the deprecated fallback for external adapters that
    don't declare yet.

    ``source`` is a human-readable adapter label (``"sqlite"``,
    ``"postgres"``, ``"filesystem"``, ``"composite-filesystem"``).

    Fields added by s-sourceport-contract-cleanup (default to the
    conservative ``False``/empty so pre-existing constructors keep
    working):

    - ``granular_list`` / ``granular_one`` — implements the L1 granular
      reads ``list_doc_refs`` / ``load_one`` (the section protocols.py
      used to mark "IMPLEMENTAÇÕES OPCIONAIS — Kernel checa via hasattr").
      Independent flags on purpose (external sources may ship only one);
      the ``granular`` property is the AND of both.
    - ``query_pushdown`` — implements ``query``/``count`` natively
      (entry points exist; FS is "native but in-memory"). When False
      the kernel serves queries via its load_all fallback
      (``dna.kernel.query_fallback``).
    - ``tenant_layer_writes`` — writes accept BOTH first-class
      ``tenant`` and ``layer`` kwargs (the modern Phase-2 contract).
    - ``write_kwargs`` / ``delete_kwargs`` — exactly which optional
      kwargs ``save_document`` / ``delete_document`` accept. Replaces
      the runtime ``inspect.signature`` probe in
      :func:`write_kwarg_support`.
    """

    source: str
    drafts: bool
    versions: bool
    layers: bool
    bundle_read: bool
    bundle_write: bool
    kernel_attachable: bool
    # s-sourceport-contract-cleanup — explicit contract declaration.
    # ``granular_list``/``granular_one`` are independent on purpose: the old
    # kernel hasattr checks probed ``list_doc_refs`` and ``load_one``
    # separately, and external/mock sources legitimately implement only one.
    # In-repo adapters declare both (see the ``granular`` property).
    granular_list: bool = False   # implements list_doc_refs
    granular_one: bool = False    # implements load_one
    query_pushdown: bool = False
    tenant_layer_writes: bool = False
    write_kwargs: frozenset[str] = frozenset()
    delete_kwargs: frozenset[str] = frozenset()

    @property
    def granular(self) -> bool:
        """The full L1 granular read pair (``list_doc_refs`` + ``load_one``)."""
        return self.granular_list and self.granular_one


# The full optional-kwarg vocabulary of the WritableSourcePort write methods.
# ``write_kwargs``/``delete_kwargs`` declarations are validated against these
# by the conformance test (an adapter can't declare a kwarg that isn't part
# of the port contract).
SAVE_OPTIONAL_KWARGS = frozenset(
    {"author", "tenant", "layer", "write_class", "version_retention"}
)
DELETE_OPTIONAL_KWARGS = frozenset({"tenant", "layer"})


def _probe_params(source: object, method_name: str) -> set[str]:
    """Parameter names of a bound method — reflection, used ONLY by the
    deprecated :func:`derive_capabilities` fallback / conformance oracle."""
    import inspect

    method = getattr(source, method_name, None)
    if method is None:
        return set()
    try:
        return set(inspect.signature(method).parameters)
    except (TypeError, ValueError):
        return set()


def _has_own_query(source: object) -> bool:
    """True when ``source`` implements ``query`` itself (not the bodyless
    ``SourcePort.query`` Protocol stub inherited by explicit subclassers)."""
    qm = getattr(source, "query", None)
    if not callable(qm):
        return False
    from dna.kernel.protocols import SourcePort  # local: avoid cycle

    fn = getattr(qm, "__func__", qm)
    return fn is not SourcePort.query


def _has_method(source: object, name: str) -> bool:
    """Dynamic method-presence probe. Deliberately ``getattr`` (NOT
    ``isinstance`` against the capability Protocols): since Python 3.12,
    runtime Protocol checks use ``inspect.getattr_static``, which is blind
    to ``__getattr__``-based proxies (``AsyncSourceAdapter``). Dynamic
    getattr sees the surface the kernel will actually call — for plain
    adapter classes the two probes are equivalent."""
    return callable(getattr(source, name, None))


def derive_capabilities(source: object, *, label: str) -> SourceCapabilities:
    """Build a :class:`SourceCapabilities` for ``source`` by introspecting
    which capability-Protocol methods it exposes + probing write signatures.

    s-sourceport-contract-cleanup: this is now the *oracle*, not the
    production path — in-repo adapters declare literals and the
    conformance test asserts declaration == derivation. External
    adapters that don't declare get this via the deprecated fallback in
    :func:`source_capabilities`. ``label`` is the adapter's display name.
    """
    save_params = _probe_params(source, "save_document")
    delete_params = _probe_params(source, "delete_document")
    write_kwargs = frozenset(SAVE_OPTIONAL_KWARGS & save_params)
    delete_kwargs = frozenset(DELETE_OPTIONAL_KWARGS & delete_params)
    return SourceCapabilities(
        source=label,
        drafts=_has_method(source, "load_drafts") and _has_method(source, "publish"),
        versions=_has_method(source, "get_version"),
        layers=_has_method(source, "load_layer"),
        bundle_read=_has_method(source, "fetch_bundle_entry"),
        bundle_write=_has_method(source, "write_bundle_entry"),
        kernel_attachable=_has_method(source, "attach_kernel"),
        granular_list=_has_method(source, "list_doc_refs"),
        granular_one=_has_method(source, "load_one"),
        query_pushdown=_has_own_query(source),
        tenant_layer_writes=("tenant" in write_kwargs and "layer" in write_kwargs),
        write_kwargs=write_kwargs,
        delete_kwargs=delete_kwargs,
    )


_SOURCE_CAPS_CACHE_ATTR = "_dna_source_capabilities"
# Warn once per adapter class, not once per instance/call.
_WARNED_UNDECLARED: set[type] = set()


def source_capabilities(source: object) -> SourceCapabilities:
    """THE kernel-side accessor for a source's capabilities.

    Resolution order (memoized per instance):

    1. The adapter's own sync ``capabilities()`` returning a
       :class:`SourceCapabilities` — the explicit declaration.
    2. DEPRECATED fallback: :func:`derive_capabilities` reflection, with
       a ``DeprecationWarning`` pointing at the migration. Keeps external
       adapters that predate s-sourceport-contract-cleanup working.

    The kernel MUST consult this instead of ``hasattr``/``getattr``/
    ``inspect.signature`` on sources.
    """
    cached = getattr(source, _SOURCE_CAPS_CACHE_ATTR, None)
    if isinstance(cached, SourceCapabilities):
        return cached

    import inspect

    caps: SourceCapabilities | None = None
    fn = getattr(source, "capabilities", None)
    if callable(fn) and not inspect.iscoroutinefunction(fn):
        try:
            declared = fn()
        except Exception:  # noqa: BLE001 — a broken declaration degrades to derive
            declared = None
        if isinstance(declared, SourceCapabilities):
            caps = declared
    if caps is None:
        cls = type(source)
        if cls not in _WARNED_UNDECLARED:
            _WARNED_UNDECLARED.add(cls)
            import warnings

            warnings.warn(
                f"{cls.__name__} does not declare SourceCapabilities via a sync "
                f"capabilities() method; deriving via reflection (deprecated, "
                f"s-sourceport-contract-cleanup). Declare an explicit "
                f"SourceCapabilities on the adapter to silence this.",
                DeprecationWarning,
                stacklevel=2,
            )
        caps = derive_capabilities(source, label=cls.__name__)
    try:
        setattr(source, _SOURCE_CAPS_CACHE_ATTR, caps)
    except (AttributeError, TypeError):
        pass  # __slots__ / frozen source — recompute next time, still correct
    return caps


@runtime_checkable
class KernelAttachable(Protocol):
    """Source adapter capability: accept post-init kernel wiring.

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
    """

    def attach_kernel(self, kernel: object) -> None: ...


@runtime_checkable
class TenantAware(Protocol):
    """Source adapter capability: ``save_document``/``delete_document`` accept a
    first-class ``tenant`` kwarg (the modern WritableSourcePort write contract,
    Phase 2). All 3 production adapters satisfy it.

    NOTE: ``runtime_checkable`` ``isinstance`` only checks that the *methods*
    exist, NOT that they accept a ``tenant`` keyword — Protocols can't express a
    kwarg-level capability. So this Protocol documents the contract + serves
    static checking, while the kernel's runtime branch that decides whether to
    pass ``tenant=`` uses :func:`write_kwarg_support` (a memoized signature
    probe) instead. Don't ``isinstance(src, TenantAware)`` to gate the tenant
    kwarg — it would be True for any source with a ``save_document`` at all.
    """

    async def save_document(
        self, scope: str, kind: str, name: str, raw: dict, *,
        tenant: str | None = ...,
    ) -> str: ...

    async def delete_document(
        self, scope: str, kind: str, name: str, *,
        tenant: str | None = ...,
    ) -> None: ...


@runtime_checkable
class LayerAware(Protocol):
    """Source adapter capability: writes accept a ``layer`` overlay kwarg.

    Same ``runtime_checkable`` caveat as :class:`TenantAware` — use
    :func:`write_kwarg_support` for the runtime kwarg decision; this Protocol is
    for documentation + static typing.
    """

    async def save_document(
        self, scope: str, kind: str, name: str, raw: dict, *,
        layer: tuple[str, str] | None = ...,
    ) -> str: ...


@dataclass(frozen=True)
class WriteKwargSupport:
    """Which optional keyword args a source's write methods accept.

    Kwarg-level capabilities (``tenant``/``author``/``layer``) can't be detected
    with ``isinstance`` against a ``runtime_checkable`` Protocol (those ignore
    signatures), so the kernel probes the bound methods' signatures — but ONCE
    per source, memoized via :func:`write_kwarg_support`, not on every write.
    """

    author: bool          # save_document accepts `author`
    tenant: bool          # save_document accepts `tenant`
    layer_save: bool      # save_document accepts `layer`
    layer_delete: bool    # delete_document accepts `layer`
    tenant_delete: bool   # delete_document accepts `tenant`
    write_class: bool     # save_document accepts `write_class` (s-buswrite-class-substantive-cue)
    version_retention: bool  # save_document accepts `version_retention` (s-version-prune-record-plane-churn)


_WRITE_KWARG_CACHE_ATTR = "_dna_write_kwarg_support"


def write_kwarg_support(source: object) -> WriteKwargSupport:
    """Return (memoized) which optional write kwargs ``source`` accepts.

    s-sourceport-contract-cleanup: this is now a READ of the adapter's
    declared :class:`SourceCapabilities` (``write_kwargs`` /
    ``delete_kwargs``), not an ``inspect.signature`` probe. The public
    signature + memoization attr are kept intact for existing importers.
    Adapters that don't declare capabilities still work: the underlying
    :func:`source_capabilities` falls back to reflection-derivation with
    a ``DeprecationWarning``.
    """
    cached = getattr(source, _WRITE_KWARG_CACHE_ATTR, None)
    if isinstance(cached, WriteKwargSupport):
        return cached

    caps = source_capabilities(source)
    support = WriteKwargSupport(
        author="author" in caps.write_kwargs,
        tenant="tenant" in caps.write_kwargs,
        layer_save="layer" in caps.write_kwargs,
        layer_delete="layer" in caps.delete_kwargs,
        tenant_delete="tenant" in caps.delete_kwargs,
        write_class="write_class" in caps.write_kwargs,
        version_retention="version_retention" in caps.write_kwargs,
    )
    try:
        setattr(source, _WRITE_KWARG_CACHE_ATTR, support)
    except (AttributeError, TypeError):
        pass  # __slots__ / frozen source — recompute next time, still correct
    return support
