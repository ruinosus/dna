"""Kernel v3 — Mediator connecting 5 ports."""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, overload

if TYPE_CHECKING:  # typed hook-name vocabulary (s-dna-typed-hook-names)
    from dna.kernel.hooks import HookName

from dna.kernel.document import Document
from dna.kernel.errors import (
    ExtensionLoadError, KindRegistrationError, ReaderRegistrationError,
    WriterRegistrationError,
)
from dna.kernel.kind_registry import (
    # _load_kind_docs moved into the KindRegistry module with the registration
    # funnel (s-kernel-decomp-f3-kindregistry); re-exported here so the historical
    # ``from dna.kernel import _load_kind_docs`` importer keeps working.
    _load_kind_docs,  # noqa: F401
)
from dna.kernel.protocols import (
    CachePort, DEFAULT_BASE_SCOPE, Extension,
    EXTENSIONS_ENTRY_POINT_GROUP,  # noqa: F401 — re-exported for historical `from dna.kernel import EXTENSIONS_ENTRY_POINT_GROUP` importers (boot recipe moved to kernel_bootstrap, s-kernel-decomp-f4)
    ExtensionHost,  # noqa: F401 — re-exported registration-time host slice (s-dna-extension-host-contract)
    KindPort,
    KindPresentation,  # noqa: F401 — re-exported optional presentation capability (s-dna-kindport-descriptor-schema)
    ReaderPort,
    ResolverPort, SourcePort, StorageDescriptor, StoragePattern,
    SYSTEM_SCOPE, Template, ToolDefinition, WritableSourcePort, WriterPort,
)
from dna.kernel.instance import ManifestInstance  # noqa: F401 — used in deferred-eval annotations
from dna.kernel.templates import OnConflict

logger = logging.getLogger(__name__)


class NotWritableError(RuntimeError):
    """Raised when write_document / delete_document is called but no
    WritableSourcePort is registered on the Kernel."""


class KindRetiredError(ValueError):
    """Raised when write_document targets a Kind listed in
    ``Kernel._REMOVED_KINDS``. Reads of legacy docs still succeed
    (parsed as untyped Document), but new writes are blocked so the
    catalog doesn't accrue more orphans of a retired Kind."""


@dataclass(frozen=True)
class PreviewResult:
    """Return value of Kernel.preview_document().

    target: Path for filesystem sources, synthetic URL for others
        (e.g. "sqlite://<scope>/<kind>/<name>").
    files: list of {"relativePath": str, "content": str} — the exact
        bytes that would be written.
    exists_already: True iff the target document is already present
        on disk / in the adapter. UIs use this to render "create" vs
        "overwrite" affordances. Optimistic concurrency (if_match) is
        deferred per 2026-04-04-kernel-write-path-design Out-of-Scope.
    """
    target: str | Path
    files: list[dict]
    exists_already: bool


__all__ = ["NotWritableError", "PreviewResult"]


def _run_sync_helper(coro_or_value, *, loop: asyncio.AbstractEventLoop | None = None):
    """Run async coroutine from sync context safely, or return sync value as-is.

    Resolution order:
    1. If ``coro_or_value`` is not awaitable → pass-through.
    2. If ``loop`` is passed AND it's running AND it's NOT the current
       loop → ``run_coroutine_threadsafe(coro, loop).result()``. Proper
       cross-thread dispatch. The asyncpg pool is loop-bound, so coros
       must run on the loop that created the pool.
    3. Else if no running loop in this thread → ``asyncio.run`` (CLI/tests).
    4. Else (running loop in current thread, OR ``loop is current``,
       OR no registered loop) → raise. The previous fallback
       (ThreadPool + ``asyncio.run`` per call) silently corrupted
       asyncpg pool state — each call got a fresh loop the loop-bound
       pool couldn't talk to. The right fix is for the caller to
       either ``await`` the coro directly (use the ``*_async`` variant
       — e.g. ``mi.prompt.build_async``, ``instance.ref_async``,
       ``MIHolder.reload_async``) or pass ``loop=kernel._main_loop``
       from a worker thread. Failing loud beats silent breakage.
    """
    import inspect
    if not inspect.isawaitable(coro_or_value):
        return coro_or_value
    try:
        current = asyncio.get_running_loop()
    except RuntimeError:
        current = None
    # Case 1 — different loop, running: dispatch cross-thread via threadsafe
    if loop is not None and loop.is_running() and loop is not current:
        return asyncio.run_coroutine_threadsafe(coro_or_value, loop).result()
    # Case 2 — registered main loop NOT running, but exists + not closed:
    # this is the CLI between-runs state. Drive the coro on THAT loop via
    # `run_until_complete` instead of `asyncio.run` (which would create a
    # fresh loop that the source pool — bound to `loop` — can't talk to).
    # Fixes "another operation in progress" on bundle writes triggered
    # by apply → holder.reload() → instance() → _run_sync_helper.
    # Issue/i-sync-async-loop-mismatch.
    if loop is not None and not loop.is_closed() and current is None:
        return loop.run_until_complete(coro_or_value)
    # Case 3 — no registered loop, no running loop in current thread:
    # safe to spin up a fresh asyncio.run. Used by tests + bare scripts.
    if current is None:
        return asyncio.run(coro_or_value)
    raise RuntimeError(
        "_run_sync_helper called from inside a running event loop without "
        "a usable cross-thread dispatch path. Fix the caller: either "
        "await the coro directly via the *_async variant (e.g. "
        "`mi.prompt.build_async`, `instance.ref_async`, "
        "`MIHolder.reload_async`), or pass `loop=kernel._main_loop` "
        "from a worker thread."
    )


# s-version-prune-record-plane-churn — version snapshots to retain for the
# machine-CHURN Kinds: docs rewritten in place thousands of times by autopilot
# (engrafia rewrites the SAME LessonLearned 6613×; Remembrance/Canvas/VibeSession
# similar), drowning the meaningful authored history. NOT keyed on plane — many
# record-plane Kinds (Story/Spec/ADR/Feature) are AUTHORED and keep FULL history,
# while churny ones (Canvas/VibeSession) aren't even record-plane. Curated set,
# like DEFAULT_NON_INHERITABLE_KINDS_V1; a Kind may also self-declare
# ``version_retention`` to opt in. Authored Kinds keep full history (None).
VERSION_CHURN_RETENTION = 3
VERSION_CHURN_KINDS: frozenset[str] = frozenset({
    "LessonLearned", "Remembrance", "Canvas", "VibeSession", "InsightReport",
})


class _DenylistInheritable:
    """Membership-only set for scope-level inheritance (s-platform-inherit-by-default).

    `kind in kernel._INHERITABLE_KINDS` is True for EVERY Kind except the
    per-scope ledger + structural denylist — i.e. `_lib` inheritance is the
    default and scopes/tenants specialize by overriding locally. Kept as the
    `_INHERITABLE_KINDS` attribute so the ~14 existing membership call-sites
    (kernel/instance/docs-service/docs-route) and the TS twin stay unchanged.
    Intentionally NOT iterable — there's no finite "inheritable" list anymore.
    """

    __slots__ = ("_deny",)

    def __init__(self, denylist: frozenset[str]) -> None:
        self._deny = denylist

    def __contains__(self, kind: object) -> bool:
        return kind not in self._deny

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"_DenylistInheritable(deny={sorted(self._deny)})"


class Kernel:
    """Mediator that orchestrates 5 ports + hooks to produce ManifestInstance."""

    def __init__(self, *, tenant: str | None = None) -> None:
        """Create a Kernel.

        ``tenant`` binds this kernel to a tenant — all subsequent
        write/read ops route to that tenant's storage. Use
        ``with_tenant(other)`` for per-call cross-tenant operations
        (Stripe Connect pattern). Pass ``None`` (default) for the
        unbound kernel — only GLOBAL kinds may be written; TENANTED
        kinds raise ``TenantRequired``.
        """
        from dna.kernel.protocols import validate_tenant_slug
        validate_tenant_slug(tenant)
        self.tenant: str | None = tenant

        self._source: SourcePort | None = None
        self._cache: CachePort | None = None
        self._resolvers: dict[str, ResolverPort] = {}
        self._readers: list[ReaderPort] = []
        self._writers: list[WriterPort] = []
        # s-kernel-decompose-god-object — the registered-Kind identity map +
        # lookups extracted to a collaborator (kernel-decompose-continue). The
        # ``_kinds`` property below proxies to it so the ~20 inline access sites
        # (and registration in kind()/load()/_register_*) keep mutating one dict.
        from dna.kernel.kind_registry import KindRegistry
        # s-kernel-decomp-f3-kindregistry — the registry now OWNS the
        # registration funnel (kind()/kind_from_descriptor/2-phase load); it
        # reaches the wider kernel (hooks, _readers rescan gate, generic-rw
        # wiring, _generics_resolved, alias-owner ctx) through the narrow
        # ``RegistryHost`` back-ref. Passing ``self`` here is safe even though
        # ``hooks``/``_readers`` don't exist yet — the host is read only at
        # registration time (boot), long after __init__ returns.
        self._kindreg = KindRegistry(host=self)
        # s-dna-tool-decorator-port (2026-05-24) — tool registry, analogous to
        # ``_kinds``. Populated via ``kernel.tool(td)`` — called by extensions or
        # runtime bootstrap (which stub-calls tool factories to harvest @dna_tool
        # definitions). Extracted to the ToolRegistry collaborator
        # (kernel-decompose-continue); one registry shared across with_tenant
        # copies (tools are global, not tenant-scoped).
        from dna.kernel.tool_registry import ToolRegistry
        self._toolreg = ToolRegistry()

        # s-kernel-decompose-god-object — layer-write policy enforcement
        # (LOCKED/RESTRICTED/OPEN) extracted to a collaborator
        # (kernel-decompose-continue), holding a back-ref to this kernel.
        from dna.kernel.layer_policy import LayerPolicyEnforcer
        self._layerpol = LayerPolicyEnforcer(self)

        # s-kernel-decompose-god-object — bundle-entry + document serialization
        # I/O extracted to a collaborator (kernel-decompose-continue).
        from dna.kernel.bundle_io import BundleIO
        self._bundleio = BundleIO(self)

        # s-kernel-decompose-god-object — the Composition-V2 engine (Phase 17:
        # resolution chain, composition rules, resolve/summary/personalize)
        # extracted to a collaborator (kernel-decompose-continue), back-ref to
        # this kernel. ``_layer_observers`` stays kernel state (shared with
        # _invalidate_internal); the resolver reads/writes it via the back-ref.
        from dna.kernel.composition_resolver import CompositionResolver
        self._composition = CompositionResolver(self)

        # s-kernel-decompose-god-object — cache-coherence fan-out (write-observer
        # fan-out + invalidate + batch coalescing) extracted to a STATELESS
        # collaborator (kernel-decompose-continue); all batch/observer/holder
        # state stays on the kernel (preserves with_tenant shallow-copy). The
        # kernel keeps write_document/delete_document (its mediation core).
        from dna.kernel.invalidation import InvalidationController
        self._invctl = InvalidationController(self)

        # s-kernel-decomp-f2-writepipeline — the fat document write/delete
        # execution (tenant resolution, capability-gated adapter kwargs, the
        # pre_save veto gate, save/delete persistence, and the three-tier
        # invalidation fan-out) extracted to a STATELESS back-ref collaborator.
        # The kernel keeps write_document/delete_document as thin facades (mode
        # validation, _REMOVED_KINDS block, record-plane demotion, OTel span).
        # It receives the narrow ``WriteHost`` Protocol — the kernel satisfies
        # it structurally; all side effects route THROUGH the host.
        from dna.kernel.write_pipeline import WritePipeline
        self._write_pipeline = WritePipeline(self)

        # s-kernel-decompose-god-object — ManifestInstance construction
        # (build/instance/instance_async/resolve_layers + rescan helpers)
        # extracted to a collaborator (kernel-decompose-continue), back-ref.
        from dna.kernel.instance_builder import InstanceBuilder
        self._builder = InstanceBuilder(self)
        self._profiles: list = []  # CompositionProfile objects
        self._extensions: list[Extension] = []
        self._generics_resolved = False

        from dna.kernel.hooks import HookRegistry
        self.hooks = HookRegistry()

        # Phase 15.x — registered "main" event loop for sync-from-thread
        # dispatch. Workers register their bootstrap loop here so sync
        # kernel API calls from a ThreadPoolExecutor thread (e.g. eval
        # tools running inside `asyncio.to_thread(run_eval_case, ...)`)
        # can dispatch coroutines back to the loop that owns the source
        # adapter pool — instead of spawning a fresh `asyncio.run` that
        # orphans pool resources. None = no registered loop (CLI/test
        # contexts use the legacy fallback in _run_sync_helper).
        self._main_loop: asyncio.AbstractEventLoop | None = None

        # batch_writes() context manager state. When depth > 0,
        # `invalidate()` records the touched scopes but skips holder
        # reloads + observer fan-out. On context exit, one consolidated
        # invalidation fires per touched scope. Lets CLI batch scripts
        # do N writes with 1 reload instead of N.
        self._batch_mode_depth: int = 0
        self._batch_pending: list[tuple[str, str, str, str, str]] = []

        # s-kernel-decompose-god-object — the three-tier read cache
        # (base MI + granular list/doc) extracted to a collaborator. Created
        # eagerly so ``with_tenant`` shallow copies share ONE cache (granular
        # keys carry the tenant; the base tier is pre-tenant → safe to share).
        from dna.kernel.kernel_cache import KernelCache
        self._kcache = KernelCache(
            base_max=self._BASE_INSTANCE_MAX,
            list_ttl=self._GRANULAR_LIST_TTL,
            doc_ttl=self._GRANULAR_DOC_TTL,
            doc_max=self._GRANULAR_DOC_MAX,
        )

        # s-kernel-decompose-god-object — the source-sync engine (s-sync-s1..s5:
        # digest_manifest / diff_manifests / push_scope) extracted to a
        # collaborator holding a back-ref to this kernel.
        from dna.kernel.source_sync import SourceSync
        self._sync = SourceSync(self)

        # s-kernel-decompose-god-object — the read surface (query push-down +
        # get_document + the two sync wrappers) extracted to a STATELESS back-ref
        # collaborator (kernel-decompose-continue). It reads ``tenant`` for the
        # query tenant auto-stamp, so ``with_tenant`` rebinds it to the copy.
        from dna.kernel.query_engine import QueryEngine
        self._query = QueryEngine(self)

        # Two-planes F2 (D2) — the registered RecordSearchProvider for
        # kernel.search(). None = no provider → lexical degraded fallback.
        # Shared by with_tenant shallow copies (boot-time wiring, like tools).
        # ``_search_provider_warned`` dampens the provider-failure warning:
        # full traceback ONCE per failure episode, repeats at debug; reset on
        # a successful provider call or on re-registration.
        # NOTE: only ``_search_provider`` is shared by with_tenant shallow copies;
        # ``_search_provider_warned`` is NOT shared (each shallow copy gets its
        # own bool, since copy.copy copies primitive fields by value).
        # F2.5: if route callers use with_tenant(...).search(), move this damper
        # into a shared mutable holder so suppression is consistent across copies.
        self._search_provider = None
        self._search_provider_warned: bool = False

        # Phase 3b ch1 (i-112) — the Catalog tier scope set, cached per tenant.
        # ``tenant → (stamped_at_monotonic, scopes)``. TTL = _GRANULAR_DOC_TTL
        # (60s) as a backstop; the authoritative refresh is the explicit
        # invalidation on Genome writes (write_document) + the install path
        # (routes/catalog.py writes the lockfile directly). Shared across
        # ``with_tenant`` shallow copies (keys carry the tenant — safe, like
        # the granular cache).
        self._catalog_cache: dict[
            "str | None", tuple[float, list[tuple[str, "str | None"]]]
        ] = {}

        # s-kernel-decomp-f5-satellites — the read-only leaf satellites extracted
        # to STATELESS back-ref collaborators (fail-soft, no write-path). Each
        # reads per-kernel state through its narrow ``*Host`` Protocol, so
        # ``with_tenant`` rebinds them to the shallow copy (below). The kernel
        # keeps every public method as a thin facade delegating here.
        #  - RegistryAccessor: model/voice/embedding profile _lib-direct reads.
        #  - SearchEngine: record search + lexical fallback (provider/damper
        #    state stays on the kernel — shared/per-copy exactly as before).
        #  - CatalogCache: the Catalog-tier scope set. The ``_catalog_cache`` DICT
        #    stays kernel-owned + shared by identity across with_tenant copies
        #    (spec Risk #3); the collaborator is stateless compute over it.
        #  - SourceFacade: read-only source-adapter introspection.
        from dna.kernel.registry_accessor import RegistryAccessor
        from dna.kernel.search_engine import SearchEngine
        from dna.kernel.catalog_cache import CatalogCache
        from dna.kernel.source_facade import SourceFacade
        self._registry = RegistryAccessor(self)
        self._search = SearchEngine(self)
        self._catalog = CatalogCache(self)
        self._srcfacade = SourceFacade(self)

    def register_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the long-lived event loop that owns this kernel's
        source pool. After registration, sync API calls from worker
        threads dispatch back to this loop via run_coroutine_threadsafe
        instead of spawning a new loop. Idempotent."""
        self._main_loop = loop

    def with_tenant(self, tenant: str | None) -> "Kernel":
        """Return a shallow-copy Kernel bound to ``tenant``.

        Original Kernel is unchanged — call sites can hand off the
        copy to per-request handlers without mutating shared state
        (Sanity ``client.withConfig({dataset: X})`` pattern).

        Pass ``tenant=None`` to obtain an unbound kernel (writes
        only allowed for GLOBAL kinds).
        """
        from dna.kernel.protocols import validate_tenant_slug
        validate_tenant_slug(tenant)
        import copy as _copy
        new = _copy.copy(self)  # shallow — shared source/cache/extensions/hooks
        new.tenant = tenant
        # s-kernel-decompose-god-object — the STATELESS back-ref collaborators
        # read per-kernel instance state (e.g. tenant, batch depth, holders), so
        # they must point at THIS copy, not the original. The STATE-holding ones
        # (_kcache / _toolreg / _kindreg) stay shared — their state is global
        # across tenant views. (Pre-extraction these were methods bound to the
        # copy via self; rebinding restores that exactly.)
        from dna.kernel.source_sync import SourceSync
        from dna.kernel.layer_policy import LayerPolicyEnforcer
        from dna.kernel.bundle_io import BundleIO
        from dna.kernel.composition_resolver import CompositionResolver
        from dna.kernel.invalidation import InvalidationController
        from dna.kernel.instance_builder import InstanceBuilder
        from dna.kernel.query_engine import QueryEngine
        from dna.kernel.write_pipeline import WritePipeline
        new._sync = SourceSync(new)
        new._layerpol = LayerPolicyEnforcer(new)
        new._bundleio = BundleIO(new)
        new._composition = CompositionResolver(new)
        new._invctl = InvalidationController(new)
        new._builder = InstanceBuilder(new)
        new._query = QueryEngine(new)  # reads new.tenant for the query auto-stamp
        # reads new.tenant for tenant reconciliation; points at the copy so a
        # with_tenant kernel writes with its own bound tenant.
        new._write_pipeline = WritePipeline(new)
        # s-kernel-decomp-f5-satellites — the read-only leaf collaborators read
        # per-kernel state (search reads new.tenant; registry/catalog query
        # through the copy so the tenant auto-stamp is the copy's), so they point
        # at THIS copy. The ``_catalog_cache`` DICT itself stays SHARED (copied by
        # reference above) — only the stateless compute wrapper is rebound.
        from dna.kernel.registry_accessor import RegistryAccessor
        from dna.kernel.search_engine import SearchEngine
        from dna.kernel.catalog_cache import CatalogCache
        from dna.kernel.source_facade import SourceFacade
        new._registry = RegistryAccessor(new)
        new._search = SearchEngine(new)
        new._catalog = CatalogCache(new)
        new._srcfacade = SourceFacade(new)
        return new

    @property
    def _kinds(self) -> dict[tuple[str, str], KindPort]:
        """The registered-Kind dict — proxied to ``self._kindreg`` so the inline
        access + registration sites across the kernel keep mutating one map
        (s-kernel-decompose-god-object)."""
        return self._kindreg._kinds

    def _kind_port_for(
        self, kind: str, *, api_version: str | None = None,
    ) -> KindPort | None:
        """Lookup a registered KindPort by kind name. Delegates to _kindreg."""
        return self._kindreg.port_for(kind, api_version=api_version)

    def kind_port_for(
        self, kind: str, *, api_version: str | None = None,
    ) -> KindPort | None:
        """Public lookup for a registered KindPort by kind name.

        Use from tooling that needs to consult Kind metadata
        (``is_runtime_artifact``, ``scope``, ``storage``, ...) without
        reaching into Kernel internals. Returns ``None`` if the kind
        isn't registered. Pass ``api_version=`` for exact resolution when
        the kind name is ambiguous (i-195 — e.g. the Reference pair).
        """
        return self._kindreg.port_for(kind, api_version=api_version)

    def _validate_one_kind_writer_entry(
        self,
        target: str,
        creative_slots: list[str],
        system_slots: dict[str, str],
    ) -> None:
        """Validate a SINGLE Kind-Writer target's slot↔schema contract.
        Thin delegator to ``WritePipeline.validate_one_kind_writer_entry``
        (Fase 2, s-kernel-decomp-f2-writepipeline)."""
        self._write_pipeline.validate_one_kind_writer_entry(
            target, creative_slots, system_slots,
        )

    def _validate_kind_writer(self, spec: "AgentSpec") -> None:
        """Validate a Kind-Writer Agent's slot↔schema contract at write
        time. Called via the helix ``pre_save`` veto hook
        (``ctx.kernel._validate_kind_writer``). Thin delegator to
        ``WritePipeline.validate_kind_writer`` (Fase 2)."""
        self._write_pipeline.validate_kind_writer(spec)

    def kind_plane(self, kind: str, *, api_version: str | None = None) -> str:
        """Two-planes (spec 2026-06-09): the declared plane of a Kind by
        name — 'record' or 'composition'. Unknown Kinds default to
        'composition' (fail-safe: behaves exactly as today). Pass
        ``api_version=`` for exact resolution on ambiguous names (i-195)."""
        kp = self.kind_port_for(kind, api_version=api_version)
        return getattr(kp, "plane", "composition") if kp is not None else "composition"

    def kind_ports(self) -> list[KindPort]:
        """All registered KindPorts. Order matches registration."""
        return self._kindreg.all_ports()

    def embeddable_kinds(self) -> frozenset[str]:
        """F3 D4 (spec 2026-06-10-kinds-descriptor-f3): kind names whose
        port declares ``embed_fields`` — via descriptor ``embed:`` or a
        class-level ``embed_fields`` (the KindBase parity hook for
        not-yet-migrated classes). The embeddings sidecar derives its
        eligible set from this instead of a hardcoded frozenset
        (``dna_shared.embeddings.embeddable_kinds`` unions it with the
        shrinking legacy fallback)."""
        return frozenset(
            kp.kind
            for kp in self.kind_ports()
            if getattr(kp, "embed_fields", None) is not None
        )

    def _kind_scope(self, kind: str, *, api_version: str | None = None):
        """Return the TenantScope for a registered kind, or None if unset.

        Returning None preserves Phase 1 back-compat: existing KindPorts
        that don't declare ``scope`` get permissive treatment — write
        without tenant goes to base, write with tenant goes to overlay,
        no enforcement raised. Phase 2 iterates through every Extension
        to set ``scope = TENANTED`` (or ``GLOBAL`` for Doc etc.)
        explicitly, flipping enforcement on per-Kind.
        """
        kp = self._kind_port_for(kind, api_version=api_version)
        if kp is None:
            return None
        return getattr(kp, "scope", None)

    # ``_resolve_tenant_arg`` moved to ``write_pipeline.WritePipeline`` (Fase 2,
    # s-kernel-decomp-f2-writepipeline) — it was only ever called by the two
    # write/delete bodies, which now live in the pipeline. ``_kind_scope`` stays
    # here (the pipeline reaches it via the WriteHost Protocol).

    # -- Registration ---------------------------------------------------------
    # Hook names are typed (``HookName`` Literal, s-dna-typed-hook-names) with
    # a ``str`` overload for back-compat custom names; the HookRegistry warns
    # (``UnknownHookNameWarning``) on names outside the vocabulary.

    @overload
    def use(self, hook: "HookName", fn: Any) -> None: ...
    @overload
    def use(self, hook: str, fn: Any) -> None: ...

    def use(self, hook: str, fn: Any) -> None:
        """Register middleware on a hook point (e.g., 'pre_build_prompt')."""
        self.hooks.use(hook, fn)

    @overload
    def on(self, hook: "HookName", fn: Any) -> None: ...
    @overload
    def on(self, hook: str, fn: Any) -> None: ...

    def on(self, hook: str, fn: Any) -> None:
        """Register event subscriber (e.g., 'post_save')."""
        self.hooks.on(hook, fn)

    @overload
    def on_veto(
        self, hook: "HookName", fn: Any, *,
        priority: int = ..., key: str | None = ...,
    ) -> None: ...
    @overload
    def on_veto(
        self, hook: str, fn: Any, *,
        priority: int = ..., key: str | None = ...,
    ) -> None: ...

    def on_veto(
        self, hook: str, fn: Any, *,
        priority: int = 0, key: str | None = None,
    ) -> None:
        """Register a veto listener (e.g., 'pre_save') — raising vetoes the
        operation. See ``HookRegistry.on_veto`` for priority/key semantics."""
        self.hooks.on_veto(hook, fn, priority=priority, key=key)

    def source(self, source: SourcePort) -> None:
        # s-dna-source-conformance-kit — boot gate: a malformed source used
        # to pass registration silently and fail deep inside the first load.
        # Fail loud HERE, with the missing members named. Names-only check
        # (runtime_checkable semantics); behavior is verified by the public
        # kit `dna.testing.source_conformance_suite`. Wrapper sources
        # (AsyncSourceAdapter, Composite) are validated as the object handed
        # to the kernel — which is exactly the surface the kernel calls.
        from dna.kernel.protocols import validate_source_port
        validate_source_port(source)
        self._source = source
        # s-composition-and-nav-lazy (2026-05-14): auto-attach so direct
        # kernel.source(s) callers (harness boot via rt.storage, tests,
        # CLI bootstrap) get the same wiring as Kernel.auto(source=s).
        # Without this, source._readers stays stale and bundle-aware
        # query paths (PG source.query slow-path, etc.) miss readers
        # registered later by extensions via _ensure_generic_readers_writers.
        from dna.kernel.capabilities import KernelAttachable
        if isinstance(source, KernelAttachable):
            try:
                source.attach_kernel(self)
            except Exception as e:  # noqa: BLE001
                # fail-soft: source wiring is best-effort for exotic sources,
                # but a failed attach leaves source._readers stale (bundle
                # query slow-paths miss readers) — log loud, never silent.
                logger.warning(
                    "kernel.source: attach_kernel failed for %s: %s",
                    type(source).__name__, e,
                )

    def on_write(self, callback) -> None:
        """Register a callback invoked after each successful write_document
        or delete_document. Callback signature:
            callback(scope: str, kind: str, name: str, op: Literal["write", "delete"]) -> None

        Used by long-lived holders (e.g., MIHolder) to invalidate their own
        caches when Temporal workers or other in-process writers mutate docs.

        Observers must not raise — exceptions are swallowed to avoid breaking
        the write path.

        DEPRECATED in Phase 15.1 PR4 (planned): superseded by
        ``register_holder()`` + cross-process ``KernelEventBus``. Remains
        available through PR3 for back-compat with existing wiring.
        """
        if not hasattr(self, "_write_observers"):
            self._write_observers = []
        self._write_observers.append(callback)

    def _fire_write_observers(
        self,
        scope: str,
        kind: str,
        name: str,
        op: str,
        tenant: str = "",
    ) -> None:
        """Internal: invoke all registered on_write callbacks. Swallows exceptions.

        batch_writes(): when called from inside a ``batch_writes()``
        block, fan-out is suppressed — the batch's exit handler fires
        ONE invalidate per touched scope which itself fans out via
        `_invalidate_internal` → `_fire_write_observers`. Prevents the
        write_document → invalidate → observers → reload chain from
        triggering on every single batched write.

        ``tenant`` (s-build-graph-tenant-aware, 2026-05-13): identifies
        the overlay layer of the write so subscribers can scope their
        invalidation. Older 4-arg callbacks still work via TypeError
        fallback — back-compat preserved.

        Delegates to ``self._invctl`` (s-kernel-decompose-god-object).
        """
        self._invctl.fire_write_observers(scope, kind, name, op, tenant)

    # ─── Phase 15.1 PR3 — KernelEventBus integration ───────────────────

    def register_holder(self, holder) -> None:
        """Register a long-lived MIHolder so cross-process invalidation
        events from `KernelEventBus` can reach it.

        On `kernel.invalidate(scope=..., ...)`, every registered holder
        whose `holder.scope` matches gets `holder.reload()` called.

        Idempotent: re-registering the same holder is a no-op.
        """
        if not hasattr(self, "_holders"):
            self._holders: list = []
        if holder not in self._holders:
            self._holders.append(holder)

    def unregister_holder(self, holder) -> None:
        """Unregister a holder. Idempotent — unregistering an unknown
        holder is silently ignored."""
        holders = getattr(self, "_holders", None)
        if holders and holder in holders:
            holders.remove(holder)

    def event_bus(self, bus) -> None:
        """Register a `KernelEventBus` implementation. The harness/worker
        bootstrap calls `await bus.start(kernel)` after registration.

        Registering a bus is a declarative step; it does NOT auto-start
        the bus (start needs an active event loop). Callers control
        lifecycle. Replacing a previously registered bus replaces the
        reference but does NOT stop the previous bus — callers manage
        teardown explicitly.
        """
        self._event_bus = bus

    @property
    def active_event_bus(self):
        """The KernelEventBus registered via event_bus(), or None."""
        return getattr(self, "_event_bus", None)

    def batch_writes(self):
        """Suppress per-write reload + observer fan-out for the duration
        of the block. On exit, fires ONE consolidated invalidation per
        touched scope.

        Solves the architectural problem where N sequential writes
        each triggered a full scope reload (load_all of hundreds of
        docs + bundle entries). Pre-2026-05-11 a 22-Story backfill
        cost 22 reloads × ~10s each = ~4min. With this context
        manager, same backfill = 1 reload at exit = ~10s.

        Usage:
            with kernel.batch_writes():
                kernel.write_document(scope, k, n, raw1)
                kernel.write_document(scope, k, n, raw2)
                ...
            # → exit fires one invalidate per touched scope

        Reentrant: nested ``batch_writes()`` blocks coalesce — only
        the outermost block's exit fires the consolidated invalidation.

        Caveats:
        - Reads INSIDE the block see stale MI (no reload between writes).
          For backfill loops that don't re-read what they just wrote,
          this is fine. For workflows that read-modify-write, structure
          each pair OUTSIDE the block (or accept the staleness).
        - Cross-process invalidation (EventBus → other harness instance)
          still fires per-write through the outbox; only the LOCAL
          holder reload + observer fan-out is suppressed.

        Delegates to ``self._invctl`` (s-kernel-decompose-god-object). Returns
        the controller's context manager (state stays on the kernel).
        """
        return self._invctl.batch_writes()

    def invalidate(
        self, *,
        scope: str,
        tenant: str = "",
        kind: str,
        name: str,
        op: str,
    ) -> None:
        """Invalidate all in-process caches for a (scope, tenant) tuple
        in response to a write/delete event from the EventBus.

        Idempotent — calling for the same event multiple times is safe;
        the EventBus replay logic relies on this.

        Phase 15.1 contract:
          1. Drop `_base_instance_cache[scope]` if present.
          2. For each registered holder with matching scope, call
             `holder.reload()`.
          3. Skip if `kind == "Evidence"` (preserves the audit-churn-
             avoidance rule from the legacy `_reload_on_write`; centralized
             here so future authors don't need to remember it on each
             subscription site).

        Note: tenant is currently informational. Phase 15.2 (MIHolder
        immutability + tenant-resolved view caching) consumes this so a
        tenant-specific overlay invalidation can drop only the matching
        resolved view instead of the whole holder.

        batch_writes(): when called from inside a ``batch_writes()``
        block (depth > 0), this records the event but skips the
        expensive reload + observer fan-out. The outermost block's
        exit drains the pending list with one consolidated invalidate
        per scope.

        Delegates to ``self._invctl`` (s-kernel-decompose-god-object).
        """
        self._invctl.invalidate(
            scope=scope, tenant=tenant, kind=kind, name=name, op=op,
        )

    # Kinds that affect the kernel's bootstrap state — adding/removing/
    # changing one of these requires a full MI rebuild so the registry
    # picks up the new ports / package metadata / layer policies. Every
    # other Kind write (LessonLearned, VoiceEpisode, Story, Narrative,
    # etc) only changes user data and shouldn't drop the base cache —
    # those reads go through ``kernel.get_document`` / ``kernel.query``
    # which have their own granular L2 cache.
    #
    # s-invalidate-granular (2026-05-27): previously ALL writes dropped
    # _base_instance_cache[scope] regardless of kind. This made cognitive-
    # api thrash: every VoiceEpisode write triggered NOTIFY → invalidate
    # → cache drop → next /voice/sessions rebuilt the kernel from scratch
    # (re-registering all extensions + 100+ KindDefs, spam warnings,
    # 25-30s latency). Limiting the drop to schema-changing kinds keeps
    # the cache warm across normal doc-write traffic.
    # _SCHEMA_INVALIDATING_KINDS is now a DERIVED property — the kernel reads
    # ``KindPort.is_schema_affecting`` instead of matching hardcoded Kind names
    # (s-kernel-kindport-classification-attrs). See the classification-property
    # block below (near ``_REMOVED_KINDS``).

    def _invalidate_internal(
        self, *,
        scope: str, tenant: str, kind: str, name: str, op: str,
    ) -> None:
        """Real invalidation work — bypasses batch-mode short-circuit.
        Delegates to ``self._invctl`` (s-kernel-decompose-god-object). Kept as a
        thin wrapper (called by the batch flush + any back-compat caller)."""
        self._invctl.invalidate_internal(
            scope=scope, tenant=tenant, kind=kind, name=name, op=op,
        )

    @property
    def active_source(self) -> "SourcePort | None":
        """The SourcePort registered via source() / storage(), or None.

        Read-only accessor. The setter method is `source(src)`. Named
        `active_source` to avoid collision between a method and a property
        of the same name.
        """
        return self._source

    @property
    def source_type(self) -> str:
        """Source adapter class name (empty string when no source wired) — safe
        for capability checks. Thin facade over the SourceFacade collaborator
        (s-kernel-decomp-f5-satellites)."""
        return self._srcfacade.source_type

    async def list_scopes_async(self) -> list[str]:
        """Proxy to ``source.list_scopes()`` — normalises sync (FS) vs async
        (SQLite/Postgres) adapters. Thin facade over the SourceFacade
        collaborator (s-kernel-decomp-f5-satellites)."""
        return await self._srcfacade.list_scopes_async()

    def source_metadata(self) -> dict:
        """Read-only whitelisted snapshot of source adapter metadata
        (type / dsn / schema / base_dir; private state stays in the adapter).
        Thin facade over the SourceFacade collaborator
        (s-kernel-decomp-f5-satellites)."""
        return self._srcfacade.source_metadata()

    @property
    def active_writers(self) -> tuple["WriterPort", ...]:
        """WriterPorts registered via writer(w). Read-only view — mutating
        the returned tuple has no effect on the Kernel's internal list.
        """
        return tuple(self._writers)

    @property
    def active_readers(self) -> tuple["ReaderPort", ...]:
        """ReaderPorts registered via reader(r). Read-only view — mirror of
        ``active_writers`` (s-dna-rw-roundtrip-suite: the round-trip
        conformance kit enumerates registered pairs through this surface).
        """
        return tuple(self._readers)

    def _target_locator(self, scope: str, kind: str, name: str) -> "str | Path":
        """Stable human-readable locator for a document.

        - Filesystem sources → absolute Path under <base_dir>/<scope>/<kind_dir>/<name>.
          Subdir resolution consults the kind's registered StorageDescriptor
          via storage_for_kind; falls back to ``kind.lower() + "s"`` only when
          the kind has no descriptor (defensive — every kind registered by an
          Extension ships one).
        - Other sources → "<scheme>://<scope>/<kind>/<name>" where scheme
          comes from source.url_scheme, falling back to the class name
          with the 'Source' suffix stripped.
        """
        from dna.adapters.filesystem.source import FilesystemSource

        src = self._source
        if isinstance(src, FilesystemSource):
            sd = self.storage_for_kind(kind)
            subdir = sd.container if sd and sd.container else (kind.lower() + "s")
            return src.base_dir / scope / subdir / name
        scheme = getattr(src, "url_scheme", None) \
            or type(src).__name__.lower().removesuffix("source")
        return f"{scheme}://{scope}/{kind}/{name}"

    async def _target_exists(self, scope: str, kind: str, name: str) -> bool:
        """Best-effort probe: is the target doc already present on disk/store?

        Filesystem sources check the computed path; other sources rely on
        WritableSourcePort.list_versions (non-empty = exists). Returns False
        on any adapter failure — this is a UI hint, not a correctness gate.
        """
        target = self._target_locator(scope, kind, name)
        if isinstance(target, Path):
            return target.exists()
        src = self._source
        if src is None:
            return False
        list_versions = getattr(src, "list_versions", None)
        if list_versions is None:
            return False
        try:
            versions = await list_versions(scope, kind, name)
        except (FileNotFoundError, KeyError, ValueError):
            return False
        return bool(versions)

    async def _emit_post_save(
        self, scope: str, kind: str, name: str, raw: dict,
        *,
        layer: tuple[str, str] | None = None,
    ) -> None:
        """Emit the ``post_save`` hook. Thin delegator to
        ``WritePipeline.emit_post_save`` (Fase 2,
        s-kernel-decomp-f2-writepipeline)."""
        await self._write_pipeline.emit_post_save(
            scope, kind, name, raw, layer=layer,
        )

    async def _emit_post_delete(
        self, scope: str, kind: str, name: str,
        *,
        layer: tuple[str, str] | None = None,
    ) -> None:
        """Emit the ``post_delete`` hook. Thin delegator to
        ``WritePipeline.emit_post_delete`` (Fase 2)."""
        await self._write_pipeline.emit_post_delete(
            scope, kind, name, layer=layer,
        )

    def _base_instance_cached(self, scope: str):
        """Load the base ManifestInstance (no layer resolution) with per-scope
        caching. Delegates to ``self._kcache`` (LRU-bounded at
        ``_BASE_INSTANCE_MAX``, i-036; s-kernel-decompose-god-object);
        invalidated on base writes / teardown. Policy checks hit this, not
        ``instance()`` which would re-resolve layers per call.

        ``Kernel.instance`` is sync in this codebase, so this helper is sync.

        TODO(phase-2a.0-follow-up): stale cache risk — a base ``write_document``
        that mutates ``Module.spec.layers`` (or adds a RESTRICTED doc to base)
        is invisible to subsequent layer writes until the kernel is rebuilt.
        Safe fix: ``self._kcache.base_drop(scope)`` inside ``write_document`` /
        ``delete_document`` when ``layer is None`` and the kind/name pair
        indicates a base-manifest change. Not a blocker because Studio restart
        reloads the kernel; long-lived production processes will want this fix.
        """
        hit = self._kcache.base_get(scope)
        if hit is not None:
            return hit
        mi = self.instance(scope)
        self._kcache.base_store(scope, mi)
        return mi

    def _alias_for(self, kind: str) -> str:
        """Resolve a kind name to its globally-unique alias. Delegates to
        ``self._kindreg`` (s-kernel-decompose-god-object)."""
        return self._kindreg.alias_for(kind)

    async def _check_layer_policy_async(
        self, scope: str, kind: str, name: str, raw: dict, layer: tuple[str, str],
    ) -> None:
        """Async-native policy check. Loads the base MI via the
        async path so callers running inside an event loop don't
        trip ``_run_sync_helper``'s "called from inside a running
        loop" guard. Same semantics as the sync ``_check_layer_policy``;
        see that docstring for policy mode details.

        Delegates to ``self._layerpol`` (LayerPolicyEnforcer;
        s-kernel-decompose-god-object). Only ``write_document`` calls this.
        """
        return await self._layerpol.check_async(scope, kind, name, raw, layer)

    def _check_layer_policy(
        self, scope: str, kind: str, name: str, raw: dict, layer: tuple[str, str],
    ) -> None:
        """Sync entry point for the layer-write policy check (LOCKED/RESTRICTED/
        OPEN). Delegates to ``self._layerpol`` (s-kernel-decompose-god-object).
        The async ``write_document`` path uses ``_check_layer_policy_async``."""
        return self._layerpol.check(scope, kind, name, raw, layer)

    async def _base_instance_cached_async(self, scope: str):
        """Async variant of ``_base_instance_cached``. Uses
        ``instance_async`` so callers in a running event loop don't
        trip ``_run_sync_helper``. Shares the same per-scope cache.

        IMPORTANT: must NOT call ``instance_async(scope)`` with the
        no-args signature — that path now short-circuits BACK to here
        and would loop forever. Pass ``lazy=False`` to bypass the
        short-circuit and run the real build path on cache miss.
        """
        hit = self._kcache.base_get(scope)
        if hit is not None:
            return hit
        mi = await self.instance_async(scope, lazy=False)
        self._kcache.base_store(scope, mi)
        return mi

    # Phase 16 — Kinds that are structurally never overlayable, no
    # matter what LayerPolicy / Module.spec.layers says. Identity Kinds
    # (Genome), schema-bootstrap Kinds (KindDefinition), and the
    # policy Kind itself (LayerPolicy) cannot be redefined per-tenant.
    # Allowing it would let a tenant override its own visibility,
    # version, or the rules that constrain its overlay.
    # _NON_OVERLAYABLE_KINDS is now DERIVED from ``KindPort.is_overlayable``
    # (s-kernel-kindport-classification-attrs) — see the property block below.

    # Scope-level inheritance — DENYLIST by default (s-platform-inherit-by-default,
    # 2026-06-06). `_lib` é o PADRÃO/stdlib declarativo; cada scope/tenant é
    # uma subclasse que só sobrescreve o que quiser (`class B(A)`, override local
    # ganha). Kinds herdam de `_INHERIT_PARENT_SCOPE` transparentemente em
    # `kernel.query` / `kernel.get_document` — EXCETO os Kinds intrinsecamente
    # per-scope abaixo, que NUNCA herdam (senão todo scope veria as Stories do
    # _lib, etc).
    #
    # Histórico: V1/V2 (2026-05-28) eram um ALLOWLIST (Agent, Skill, …);
    # cada novo template herdável exigia editar o set. V3 inverte pra denylist —
    # blast radius prático = o que `_lib` realmente contém (tudo template-y).
    # _NON_INHERITABLE_KINDS is now DERIVED from ``KindPort.scope_inheritable``
    # (s-kernel-kindport-classification-attrs) — see the property block below.
    # These two ledger names have NO registered KindPort (legacy doc-kinds that
    # never got a Kind class), so they cannot carry an attribute and stay an
    # explicit constant the derived set unions in.
    _LEGACY_NON_INHERITABLE: frozenset[str] = frozenset({"Milestone", "VibeSession"})
    # `kind in kernel._INHERITABLE_KINDS` continua sendo a API de membership
    # (mantém ~14 call-sites + getattr intactos); agora denylist-backed +
    # derivado dos atributos. Property block below.
    _INHERIT_PARENT_SCOPE = DEFAULT_BASE_SCOPE

    # Phase 1B (2026-05-15): Kinds retired by past refactors. Writes are
    # rejected at the kernel.write_document boundary; existing docs (if any
    # survived past migrations) are still readable but produce typed=None
    # via the graceful _parse_doc fallback. To re-enable a Kind, remove it
    # here AND re-register a KindPort in an extension.
    #
    # OracleVerdict → migrated to StatusReport (script
    #   python-harness/scripts/migrate-oracle-verdict-to-status-report.py,
    #   refactor 2026-05-11).
    # Oracle → never a registered Kind, only a UA naming convention
    #   (oracle-risk, oracle-health, ...). The 5 docs that existed were
    #   manually filed YAML stubs and got cleaned in Phase 1B.
    # CommunityItem / Command / LottiePrompt / CopilotInstructions →
    #   podado s-prune-speculative-extensions (Fase B); recovery: git history.
    #   (The community FS install channel — dna_shared.community.* +
    #   /community/discover — is a separate subsystem and lives on.)
    # Course / AcademyLesson / LessonStep / QuizQuestion / Model3DRef /
    # IntroUnit / TeachingPath / TeachingUnit / PageIndexDocument /
    # MediaItem / Sandbox → arquivados s-prune-speculative-extensions
    #   (Fase C — demo verticals; apps/academy-web + biology-cell juntos).
    #   The PECS Lesson Kind (extensions.lesson) is UNAFFECTED — it stays.
    # JobType / HookType / ScheduleType → EXTINTOS (s-automation-trio-extinction):
    #   unificados no Kind Automation; as classes + extensions foram DELETADAS
    #   e os docs de dev migrados (contagem de Kinds caiu 3). Continuam aqui
    #   APENAS como WRITE-BLOCK tombstone: escrever um kind NÃO-registrado
    #   sucede silenciosamente no writer genérico (persiste um doc órfão
    #   typed=None), então sem esta guarda alguém poderia RESSUSCITAR um
    #   JobType. O tombstone impede isso com erro limpo. LEITURA de docs
    #   legados externos (installs não migrados) segue via
    #   extensions.automation.compat (FS lê por container; PG por coluna kind;
    #   normalize converte) — o read-fallback NÃO depende de estarem aqui.
    #   Escrita nova de automação = Kind Automation.
    # RecallPolicy..AffectPalette → the 8 single-instance cognitive policy
    #   Kinds consolidated into CognitivePolicy sections
    #   (s-consolidate-cognitive-policies). See _REMOVED_KIND_NOTES.
    # ResearchProgram / ResearchExperiment → podados
    #   (s-unify-experiment-run-families / OpçãoA): o adapter autoresearch
    #   (github.com/karpathy/autoresearch) era scaffold MORTO — zero
    #   consumidores runtime (nenhum worker/activity o rodava), 1 doc órfão.
    #   As famílias *Experiment/*Run vivas (autoagent/autolab/eval-evolve) são
    #   subsistemas distintos e ficam. recovery: git history.
    _REMOVED_KINDS = frozenset({
        "OracleVerdict", "Oracle",
        "CommunityItem", "Command", "LottiePrompt", "CopilotInstructions",
        "Course", "AcademyLesson", "LessonStep", "QuizQuestion", "Model3DRef",
        "IntroUnit", "TeachingPath", "TeachingUnit", "PageIndexDocument",
        "MediaItem", "Sandbox",
        "ResearchProgram", "ResearchExperiment",
        # EXTINTOS (s-automation-trio-extinction) — classes/extensions deletadas;
        # aqui só como write-block tombstone contra ressurreição (ver nota acima).
        "JobType", "HookType", "ScheduleType",
        "RecallPolicy", "DecayPolicy", "MemoryPolicy", "AllocationPolicy",
        "PaginationPolicy", "EngramStrengthPolicy", "EmbeddingProfile",
        "AffectPalette",
    })

    #: Per-Kind migration note surfaced in the KindRetiredError message so a
    #: blocked writer learns WHERE the data went, not just that it is blocked.
    _REMOVED_KIND_NOTES: dict[str, str] = {
        "OracleVerdict": "migrated to StatusReport (refactor 2026-05-11)",
        "Oracle": "never a registered Kind — UA naming convention only",
        "JobType": (
            "EXTINTO — unificado no Kind Automation (s-automation-trio-extinction). "
            "Leia legados via extensions.automation.compat; escreva Automation "
            "(on: {type: tool, tool_name: ...})."
        ),
        "HookType": (
            "EXTINTO — unificado no Kind Automation (s-automation-trio-extinction). "
            "Leia legados via extensions.automation.compat; escreva Automation "
            "(on: {type: event, trigger: ...})."
        ),
        "ScheduleType": (
            "EXTINTO — unificado no Kind Automation (s-automation-trio-extinction). "
            "Leia legados via extensions.automation.compat; escreva Automation "
            "(on: {type: cron, cron: ...})."
        ),
        "CommunityItem": "Podado (s-prune-speculative-extensions); recovery: git history.",
        "Command": "Podado (s-prune-speculative-extensions); recovery: git history.",
        "LottiePrompt": "Podado (s-prune-speculative-extensions); recovery: git history.",
        "CopilotInstructions": "Podado (s-prune-speculative-extensions); recovery: git history.",
        "ResearchProgram": "Podado — dead autoresearch adapter "
                           "(s-unify-experiment-run-families/OpçãoA); recovery: git history.",
        "ResearchExperiment": "Podado — dead autoresearch adapter "
                              "(s-unify-experiment-run-families/OpçãoA); recovery: git history.",
        "RecallPolicy": "consolidated into CognitivePolicy.spec.recall "
                        "(s-consolidate-cognitive-policies)",
        "DecayPolicy": "consolidated into CognitivePolicy.spec.decay "
                       "(s-consolidate-cognitive-policies)",
        "MemoryPolicy": "consolidated into CognitivePolicy.spec.memory.policies[] "
                        "(s-consolidate-cognitive-policies)",
        "AllocationPolicy": "consolidated into CognitivePolicy.spec.allocation "
                            "(s-consolidate-cognitive-policies)",
        "PaginationPolicy": "consolidated into CognitivePolicy.spec.pagination "
                            "(s-consolidate-cognitive-policies)",
        "EngramStrengthPolicy": "consolidated into "
                                "CognitivePolicy.spec.engram_strength "
                                "(s-consolidate-cognitive-policies)",
        "EmbeddingProfile": "consolidated into CognitivePolicy.spec.embedding "
                            "(_lib doc only; s-consolidate-cognitive-policies)",
        "AffectPalette": "consolidated into CognitivePolicy.spec.affect.palette "
                         "(s-consolidate-cognitive-policies)",
    }

    # ── Kind classification — DERIVED from KindPort attributes ──────────────
    # s-kernel-kindport-classification-attrs: the kernel no longer hardcodes
    # Kind-name frozensets; it reads each registered Kind's declared attribute.
    # The ``kind in kernel._X`` membership API is unchanged (these are
    # properties), but the source of truth is now the Kind, not a literal list.
    def _classify_kinds(self, attr: str, *, default: bool, want: bool) -> frozenset[str]:
        """frozenset of Kind names whose ``attr`` equals ``want``. ``getattr``
        with ``default`` keeps KindPort-direct Kinds (no KindBase default) safe."""
        return frozenset(
            k
            for kp in self._kinds.values()
            if (k := getattr(kp, "kind", None)) is not None
            and getattr(kp, attr, default) == want
        )

    @property
    def _SCHEMA_INVALIDATING_KINDS(self) -> frozenset[str]:
        return self._classify_kinds("is_schema_affecting", default=False, want=True)

    # Structural bootstrap Kinds — scope identity / schema / policy. These are
    # non-overlayable AND non-inheritable BY DEFINITION (mirrors
    # resolver.BOOTSTRAP_KINDS). Unioned into the derived sets so the classification
    # is identical even on a minimal kernel that hasn't registered them yet.
    _BOOTSTRAP_KINDS: frozenset[str] = frozenset({"Genome", "KindDefinition", "LayerPolicy"})

    @property
    def _NON_OVERLAYABLE_KINDS(self) -> frozenset[str]:
        return (
            self._classify_kinds("is_overlayable", default=True, want=False)
            | self._BOOTSTRAP_KINDS
        )

    @property
    def _NON_INHERITABLE_KINDS(self) -> frozenset[str]:
        return (
            self._classify_kinds("scope_inheritable", default=True, want=False)
            | self._BOOTSTRAP_KINDS
            | self._LEGACY_NON_INHERITABLE
        )

    @property
    def _INHERITABLE_KINDS(self) -> _DenylistInheritable:
        return _DenylistInheritable(self._NON_INHERITABLE_KINDS)

    def _enforce_layer_policy_with_mi(
        self, mi_base, scope: str, kind: str, name: str, raw: dict,
        layer: tuple[str, str], *, LayerPolicy, LayerPolicyViolationError,
    ) -> None:
        """Shared policy-enforcement body — delegates to ``self._layerpol``
        (LayerPolicyEnforcer; s-kernel-decompose-god-object). Kept as a thin
        wrapper for back-compat."""
        return self._layerpol._enforce(
            mi_base, scope, kind, name, raw, layer,
            LayerPolicy=LayerPolicy,
            LayerPolicyViolationError=LayerPolicyViolationError,
        )

    async def preview_document(
        self, scope: str, kind: str, name: str, raw: dict,
    ) -> PreviewResult:
        """Pure preview — returns target, serialized files, exists_already.

        Does NOT touch disk. ``exists_already`` is a UI hint so callers
        can render "create" vs "overwrite" affordances.
        """
        payload = self.serialize_document(scope, kind, name, raw)
        target = self._target_locator(scope, kind, name)
        exists_already = await self._target_exists(scope, kind, name)
        return PreviewResult(
            target=target,
            files=payload["files"],
            exists_already=exists_already,
        )

    def _require_writable_source(self) -> "WritableSourcePort":
        if self._source is None:
            raise NotWritableError("no source registered — call kernel.source(src)")
        from dna.kernel.protocols import WritableSourcePort
        if not isinstance(self._source, WritableSourcePort):
            raise NotWritableError(
                f"{type(self._source).__name__} does not implement WritableSourcePort"
            )
        return self._source

    async def write_document(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None = None,
        skip_hooks: bool = False,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        invalidate_mode: str = "scope",
        write_class: str = "substantive",
    ) -> str | None:
        """Persist a document through the registered WritableSourcePort.

        Public facade (Fase 2, s-kernel-decomp-f2-writepipeline): this method
        owns the guardrails — ``invalidate_mode`` validation, the
        ``_REMOVED_KINDS`` block, the record-plane ``scope→doc`` demotion
        (two-planes F1, resolved from the doc's own apiVersion — i-195), and the
        OTel ``kernel.write_document`` span. The FAT execution (tenant resolve,
        capability-gated adapter kwargs, layer-policy check, the ``pre_save``
        veto gate, persist, and the ordered invalidation fan-out) lives in
        ``WritePipeline.write`` — see its docstring for the full write contract
        (tenant/layer semantics, the three invalidate tiers, the always-on
        observer fan-out).

        Returns the adapter version id (or None if the adapter is version-less).
        Emits ``post_save`` on success unless ``skip_hooks`` is True.

        Raises:
            NotWritableError — no / read-only source.
            TenantRequired — TENANTED kind without a tenant.
            TenantNotAllowed — GLOBAL kind with a tenant.
            InvalidTenantSlug — tenant has invalid characters or is reserved.
            LayerPolicyViolationError — declared policy forbids the write.
            ValueError — invalidate_mode not in {scope, doc, none}.
            KindRetiredError — Kind is in _REMOVED_KINDS (writes blocked).
        """
        if invalidate_mode not in ("scope", "doc", "none"):
            raise ValueError(
                f"invalidate_mode must be 'scope', 'doc', or 'none'; "
                f"got {invalidate_mode!r}"
            )
        if kind in self._REMOVED_KINDS:
            note = self._REMOVED_KIND_NOTES.get(kind)
            raise KindRetiredError(
                f"Kind {kind!r} was retired and cannot be written"
                + (f" — {note}. " if note else ". ")
                + "See dna.kernel.Kernel._REMOVED_KINDS for migration notes."
            )
        # Two-planes F1 (spec D3): a record write NEVER triggers the
        # scope-invalidate chain. Demote the default "scope" to "doc"
        # (O(1) granular drop only). Explicit "none" stays "none";
        # an explicit "scope" passed BY a caller is also demoted —
        # records have nothing scope-level to invalidate. Record reads
        # never pass through the MI/holder (F2.5) — no app-level
        # convergence needed.
        # i-195: resolve the plane from the doc's OWN apiVersion — bare
        # kind-name lookup is ambiguous for colliding names (the Reference
        # pair resolved the composition port and skipped this demotion).
        _raw_api_version = raw.get("apiVersion") if isinstance(raw, dict) else None
        if invalidate_mode == "scope" and self.kind_plane(
            kind, api_version=_raw_api_version,
        ) == "record":
            invalidate_mode = "doc"
        # B6 OTel span (2026-05-16) — every write through the kernel
        # gets a ``kernel.write_document`` span with dna.{scope,kind,
        # name,tenant,invalidate_mode} attrs. The SDK doesn't depend
        # on OTel (kept slim); the import is guarded so callers without
        # opentelemetry installed still work — span context becomes a
        # cheap nullcontext.
        try:
            from opentelemetry import trace as _otel_trace  # noqa: PLC0415
            _tracer = _otel_trace.get_tracer("dna.kernel")
            _span_cm = _tracer.start_as_current_span(
                "kernel.write_document",
                attributes={
                    "dna.scope": scope,
                    "dna.kind": kind,
                    "dna.name": name,
                    "dna.tenant": tenant or "",
                    "dna.invalidate_mode": invalidate_mode,
                    "dna.skip_hooks": skip_hooks,
                },
            )
        except Exception as e:  # noqa: BLE001
            # fail-soft: OTel is optional telemetry — a broken tracer must
            # never block a write. Debug (not warning): fires per write when
            # OTel is absent, which is the normal non-instrumented case.
            logger.debug("write_document: OTel span unavailable: %s", e)
            from contextlib import nullcontext as _nullcontext  # noqa: PLC0415
            _span_cm = _nullcontext()

        with _span_cm:
            return await self._write_document_inner(
                scope, kind, name, raw,
                author=author, skip_hooks=skip_hooks,
                tenant=tenant, layer=layer,
                invalidate_mode=invalidate_mode,
                write_class=write_class,
            )

    async def _write_document_inner(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None,
        skip_hooks: bool,
        *,
        tenant: str | None,
        layer: tuple[str, str] | None,
        invalidate_mode: str,
        write_class: str = "substantive",
    ) -> str | None:
        """Real write_document body — thin delegator to ``WritePipeline.write``
        (Fase 2, s-kernel-decomp-f2-writepipeline). The outer ``write_document``
        wrapper owns the OTel span + mode validation + record-plane demotion;
        the fat execution (tenant resolve, capability kwargs, pre_save veto,
        persist, the ordered invalidation fan-out) lives in the pipeline. Kept
        as a named method so callers + the write-path AST ratchet still see it."""
        return await self._write_pipeline.write(
            scope, kind, name, raw,
            author=author, skip_hooks=skip_hooks,
            tenant=tenant, layer=layer,
            invalidate_mode=invalidate_mode,
            write_class=write_class,
        )

    async def delete_document(
        self, scope: str, kind: str, name: str,
        author: str | None = None,
        skip_hooks: bool = False,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        invalidate_mode: str = "scope",
        api_version: str | None = None,
    ) -> None:
        """Delete a document through the registered WritableSourcePort.

        Tenant resolution mirrors ``write_document``. See its docstring
        for the full contract — ``invalidate_mode`` also follows the same
        semantics (scope | doc | none, default scope).
        """
        if invalidate_mode not in ("scope", "doc", "none"):
            raise ValueError(
                f"invalidate_mode must be 'scope', 'doc', or 'none'; "
                f"got {invalidate_mode!r}"
            )
        # Two-planes F1 — see write_document. i-195: deletes have no raw
        # doc, so callers that know the family pass api_version= (bare
        # falls back to the deterministic first-match — conservative:
        # over-invalidates, never under-invalidates).
        if invalidate_mode == "scope" and self.kind_plane(
            kind, api_version=api_version,
        ) == "record":
            invalidate_mode = "doc"
        # Fat delete body (tenant resolve, capability kwargs, persist, the
        # ordered invalidation fan-out) → WritePipeline (Fase 2). NO pre_save
        # veto — deletes never veto.
        await self._write_pipeline.delete(
            scope, kind, name,
            author=author, skip_hooks=skip_hooks,
            tenant=tenant, layer=layer,
            invalidate_mode=invalidate_mode,
            api_version=api_version,
        )

    def cache(self, cache: CachePort) -> None:
        self._cache = cache

    def resolver(self, scheme: str, resolver: ResolverPort) -> None:
        self._resolvers[scheme] = resolver

    def reader(self, r: ReaderPort) -> None:
        # H1 — Protocol conformance check. ReaderPort is @runtime_checkable
        # in protocols.py so isinstance catches the typo-on-detect class
        # of bug at registration time instead of in production scans.
        if not isinstance(r, ReaderPort):
            raise ReaderRegistrationError(
                f"Reader {type(r).__name__} does not satisfy ReaderPort "
                f"Protocol (missing detect/read methods or the "
                f"_owner_container member — inherit ReaderPort explicitly "
                f"to get the None default). "
                f"See dna.kernel.protocols.ReaderPort."
            )
        # Idempotent re-registration — same class is a no-op
        if any(type(existing) is type(r) for existing in self._readers):
            return
        self._readers.append(r)

    def writer(self, w: WriterPort) -> None:
        # H1 — Protocol conformance check (mirror of reader()).
        if not isinstance(w, WriterPort):
            raise WriterRegistrationError(
                f"Writer {type(w).__name__} does not satisfy WriterPort "
                f"Protocol (missing can_write/write/serialize methods — "
                f"serialize is part of the contract since "
                f"s-dna-rw-roundtrip-suite). "
                f"See dna.kernel.protocols.WriterPort."
            )
        if any(type(existing) is type(w) for existing in self._writers):
            return
        self._writers.append(w)

    def kind(self, k: KindPort) -> None:
        """Register a KindPort. Thin facade over the H1 validation funnel
        (Protocol / dup-key / dup-alias / BUNDLE-marker / plane-lint /
        i-195 name-collision + alias generation), which lives in the
        KindRegistry collaborator (s-kernel-decomp-f3-kindregistry)."""
        self._kindreg.register_kind(k)

    def kind_from_descriptor(self, raw: dict[str, Any]) -> KindPort:
        """Register a BUILTIN Kind from a ``kinds/*.kind.yaml`` descriptor
        (KindDefinition package data). Thin facade over the KindRegistry funnel
        (s-kernel-decomp-f3-kindregistry); returns the registered port."""
        return self._kindreg.register_from_descriptor(raw)

    # ─────────────────────────────────────────────────────────────────
    # Tools (s-dna-tool-decorator-port, 2026-05-24)
    # Analogous to .kind() — extensions register tool definitions via
    # ``kernel.tool(td)``. Studio + cognitive-api query via
    # ``kernel.get_tools(group=...)``. The actual execution path
    # (langchain StructuredTool → langgraph) is unaffected; we add a
    # metadata layer ON TOP, not replace.
    # ─────────────────────────────────────────────────────────────────

    @property
    def _tools(self) -> dict[str, "ToolDefinition"]:
        """Back-compat read accessor for the tool registry dict (registration
        goes through ``tool()``; this preserves any code that read the dict)."""
        return self._toolreg._tools

    def tool(self, td: ToolDefinition) -> None:
        """Register a tool definition (delegates to ``self._toolreg``)."""
        self._toolreg.register(td)

    def get_tool(self, name: str) -> "ToolDefinition | None":
        """Return a tool definition by name, or None if unknown."""
        return self._toolreg.get(name)

    def get_tools(
        self,
        *,
        group: str | None = None,
        groups: list[str] | set[str] | None = None,
    ) -> list[ToolDefinition]:
        """Return registered tool definitions, optionally filtered by group(s).
        Delegates to ``self._toolreg`` (s-kernel-decompose-god-object)."""
        return self._toolreg.get_many(group=group, groups=groups)

    def list_tool_groups(self) -> dict[str, list[str]]:
        """Reverse-build {group: [tool_names...]} from the registry."""
        return self._toolreg.groups()

    def describe_kind(self, kind_name: str) -> dict[str, Any] | None:
        """Return a summary dict for a registered kind, including resolved docs.
        Delegates to ``self._kindreg``."""
        return self._kindreg.describe(kind_name)

    def composition_profile(self, profile) -> None:
        """Register a composition profile that declares how an orchestrator
        kind connects to other kinds."""
        self._profiles.append(profile)

    def resolve_dep_filter_target(self, value: str):
        """Canonical dep_filter target resolution — alias contract +
        deprecated legacy ``kind=`` shim. Delegates to ``self._kindreg``
        (s-unify-composition-subsystems; TS twin:
        ``Kernel.resolveDepFilterTarget``)."""
        return self._kindreg.resolve_dep_filter_target(value)

    def validate_dep_filters(self) -> None:
        """s-alias-generated-not-typed — every dep_filter target of an
        EXTENSION-registered Kind must resolve to a registered alias. Thin
        facade over the KindRegistry funnel (s-kernel-decomp-f3-kindregistry);
        raises ``KindRegistrationError`` on an unknown/legacy extension target,
        warns for per-scope declarative ports. Called at the end of
        ``Kernel.auto()``; harness boots hit it too."""
        self._kindreg.validate_dep_filters()

    def load(self, ext: Extension) -> None:
        # H1 — structural check before calling register(). Catches the
        # "loaded an instance of the wrong class" bug that's invisible
        # in entry-point discovery (e.g. someone registers a Kind class
        # instead of an Extension class as the entry-point target).
        register_fn = getattr(ext, "register", None)
        if not callable(register_fn):
            raise ExtensionLoadError(
                f"Extension {type(ext).__name__} has no callable register() "
                f"method. Extensions must implement `register(self, kernel)` "
                f"per the Extension Protocol — check your entry-point target."
            )
        # s-dna-extension-host-contract — validate the WHOLE Extension
        # contract fail-loud, not just register(). name identifies the
        # extension in logs / alias-owner generation; version identifies
        # it in diagnostics. A missing/blank value was previously accepted
        # silently and surfaced later as `None` owners in aliases.
        name = getattr(ext, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise ExtensionLoadError(
                f"Extension {type(ext).__name__} has no valid `name` "
                f"(got {name!r}). Extensions must declare `name: str` "
                f"(non-empty) per the Extension Protocol."
            )
        version = getattr(ext, "version", None)
        if not isinstance(version, str) or not version.strip():
            raise ExtensionLoadError(
                f"Extension {name!r} ({type(ext).__name__}) has no valid "
                f"`version` (got {version!r}). Extensions must declare "
                f"`version: str` per the Extension Protocol."
            )
        try:
            # s-alias-generated-not-typed — owner context p/ geração de
            # alias dos Kinds registrados por esta Extension (declarado
            # 1× por extension, não por Kind).
            self._loading_ext_owner = (
                getattr(ext, "alias_owner", None)
                or getattr(ext, "name", None)
            )
            try:
                ext.register(self)
            finally:
                self._loading_ext_owner = None
            self._extensions.append(ext)
        except (KindRegistrationError, ReaderRegistrationError,
                WriterRegistrationError) as e:
            # H1 — registration validation errors should propagate
            # cleanly, not be swallowed by the broad-except below. They
            # represent a *configuration* problem (duplicate Kind, marker
            # collision, malformed reader) that the operator must fix
            # before boot can continue. The hook path is for *runtime*
            # extension errors (e.g. resolver failures), not for "your
            # extension is structurally wrong".
            logger.error(
                "Extension %s failed registration validation: %s",
                getattr(ext, "name", ext), e,
            )
            raise
        except Exception as e:
            logger.error("Extension %s failed to register: %s", getattr(ext, "name", ext), e)
            if self.hooks.has("extension_error"):
                from dna.kernel.hooks import HookContext
                self.hooks.emit("extension_error", HookContext(
                    kind="Extension", name=getattr(ext, "name", str(ext)),
                    data={"error": str(e)},
                ))
            else:
                raise

    # -- Templates (Phase 0 contract) -----------------------------------------

    def list_templates(self) -> list[Template]:
        """Aggregate ``templates()`` from every loaded extension.

        The ``templates()`` method is feature-tested via ``hasattr`` so
        extensions that predate Phase 0 (and don't declare the method)
        still work. A misbehaving extension that raises inside its
        ``templates()`` is logged as a warning but never breaks discovery
        for the other extensions.
        """
        import warnings
        out: list[Template] = []
        for ext in self._extensions:
            if not hasattr(ext, "templates"):
                continue
            try:
                out.extend(ext.templates())
            except Exception as e:
                warnings.warn(
                    f"extension {getattr(ext, 'name', ext)}.templates() raised: {e}"
                )
        return out

    def scaffold(
        self,
        template_id: str,
        target_root: Path,
        on_conflict: OnConflict = "error",
    ) -> list[Path]:
        """Materialize a template by id into ``target_root``.

        Raises ``KeyError`` if no loaded extension advertises a template
        with the given id. ``on_conflict`` is passed through to
        :func:`dna.kernel.templates.materialize`.
        """
        from dna.kernel.templates import materialize
        for t in self.list_templates():
            if t.id == template_id:
                return materialize(
                    t, target_root=target_root, on_conflict=on_conflict,
                )
        raise KeyError(f"template not found: {template_id}")

    # -- Generic reader/writer auto-registration ------------------------------

    def _ensure_generic_readers_writers(self):
        """For each BUNDLE kind without a custom Reader/Writer, auto-register generic ones."""
        if self._generics_resolved:
            return
        self._generics_resolved = True
        from dna.kernel.generic_rw import GenericBundleReader, GenericBundleWriter
        from dna.kernel.protocols import StoragePattern
        for kp in self._kinds.values():
            sd = getattr(kp, 'storage', None)
            if not sd or sd.pattern != StoragePattern.BUNDLE:
                continue
            # Check if any existing reader already handles this marker
            has_reader = any(getattr(r, '_marker', None) == sd.marker for r in self._readers)
            if not has_reader:
                self._readers.append(GenericBundleReader(sd, kp.api_version, kp.kind))
            # Check if any existing writer already handles this kind
            has_writer = any(getattr(w, '_kind', None) == kp.kind for w in self._writers)
            if not has_writer:
                self._writers.append(GenericBundleWriter(sd, kp.kind))

    # -- Kernel storage helpers -----------------------------------------------

    def container_for_kind(self, kind_name: str) -> "str | None":
        """Return the storage container directory for a kind, or None. Delegates
        to ``self._kindreg``."""
        return self._kindreg.container_for(kind_name)

    def storage_for_kind(self, kind_name: str) -> "StorageDescriptor | None":
        """Return the StorageDescriptor for a kind, or None. Delegates to
        ``self._kindreg``."""
        return self._kindreg.storage_for(kind_name)

    def fetch_bundle_entry(
        self,
        scope: str,
        kind: str,
        name: str,
        entry: str,
        *,
        tenant: str | None = None,
    ) -> bytes:
        """Phase 14w — fetch a binary entry from a bundle through the
        source adapter (port-respecting; works on filesystem today,
        SQLite/Postgres when those adapters land their impls).

        Use case: tools (and the harness REST surface) reading large
        artifacts that the kernel did NOT inline into doc.spec — most
        notably the ``graph.json`` payload of a ``GraphifyArtifact``
        bundle (Phase 14w). Resolves ``kind`` → ``container`` via the
        registered KindPort's StorageDescriptor and delegates the read
        to ``source.fetch_bundle_entry(...)``.

        Honors tenant overlay routing: when ``tenant`` is passed and
        the adapter supports it, the tenant copy is preferred over
        the base layer.

        Raises:
          - ``ValueError`` if the kind is not registered.
          - ``NotImplementedError`` if the source adapter doesn't
            implement bundle entry fetch (acceptable until SQL adapters
            ship the method).
          - ``FileNotFoundError`` if the bundle or entry is absent.

        Delegates to ``self._bundleio`` (s-kernel-decompose-god-object).
        """
        return self._bundleio.fetch_sync(scope, kind, name, entry, tenant=tenant)

    async def fetch_bundle_entry_async(
        self,
        scope: str,
        kind: str,
        name: str,
        entry: str,
        *,
        tenant: str | None = None,
    ) -> bytes:
        """Async variant of `fetch_bundle_entry`. Delegates to
        ``self._bundleio`` (s-kernel-decompose-god-object)."""
        return await self._bundleio.fetch_async(scope, kind, name, entry, tenant=tenant)

    async def write_bundle_entry_async(
        self,
        scope: str,
        kind: str,
        name: str,
        entry: str,
        content: bytes | str,
        *,
        tenant: str | None = None,
    ) -> None:
        """Persist a single bundle entry payload via the active source.

        Use this instead of touching ``kernel._source`` + ``_pool``
        directly. Source-agnostic: dispatches to whichever adapter is
        active (FS / SQLite / Postgres), so the caller doesn't need
        to know the backing store.

        The bundle entry write happens AFTER the parent doc exists
        (caller must have done ``write_document`` first). The doc
        owns the tenant identity — passing the same ``tenant`` here
        keeps the bundle row's tenant column aligned with the
        ``dna_documents`` row, so subsequent ``delete_document``
        sees and cleans both atomically.

        Bug-of-record: 2026-05-21 — multiple tools were doing
        ``INSERT INTO dna_bundle_entries`` with hardcoded
        ``tenant=''`` while the doc index had the real tenant. The
        delete couldn't find the bundle row (tenant mismatch) and
        bytes leaked. This API closes that gap.

        Raises:
          - ``ValueError`` if the kind is unknown or has no bundle
            container.
          - ``NotImplementedError`` if the source adapter doesn't
            declare ``BundleEntryWritable``.

        Delegates to ``self._bundleio`` (s-kernel-decompose-god-object).
        """
        await self._bundleio.write_async(scope, kind, name, entry, content, tenant=tenant)

    async def digest_manifest(
        self, scope: str, *, tenant: str | None = None,
        include: "Callable[[dict], bool] | None" = None,
        source: "Any | None" = None,
    ) -> "dict[tuple[str, str], str]":
        """s-sync-s2 — content map of a scope: ``{(kind, name): digest}``.

        Each digest is the Kind-aware ``canonical_digest`` (s-sync-s1) of the
        doc's authored identity, combined with a Merkle hash of its non-marker
        bundle entries (so binary assets — fonts, images — are covered too).
        Source-independent by construction: the SAME scope in two sources (FS
        git ↔ Postgres runtime) yields IDENTICAL manifests when in sync, so a
        diff is a set-diff of two manifests (no content transfer).

        ``include(raw) -> bool`` optionally filters docs (s-sync-s4 passes an
        authored-vs-generated predicate). Default: every local doc of the scope.
        ``source`` overrides the source read from (default: the registered one)
        — the kernel's Kinds drive the digest, so a manifest can be built for
        ANY source with the current Kind set (s-sync-s4 diffs two sources).

        s-kernel-decompose-god-object: delegates to ``self._sync`` (SourceSync).
        """
        return await self._sync.digest_manifest(
            scope, tenant=tenant, include=include, source=source,
        )

    @staticmethod
    def diff_manifests(
        a: "dict[tuple[str, str], str]", b: "dict[tuple[str, str], str]",
    ) -> "dict[str, list[tuple[str, str]]]":
        """s-sync-s4 — set-diff two digest manifests. Pure + O(n). Delegates to
        ``SourceSync.diff_manifests`` (s-kernel-decompose-god-object)."""
        from dna.kernel.source_sync import SourceSync
        return SourceSync.diff_manifests(a, b)

    async def push_scope(
        self, scope: str, to_source: "Any", *,
        tenant: str | None = None,
        include: "Callable[[dict], bool] | None" = None,
        dry_run: bool = False,
        prune: bool = False,
    ) -> "dict[str, list]":
        """s-sync-s5 — reconcile ``to_source`` to match THIS kernel's source
        (the source-of-truth, e.g. FS git) for ``scope``.

        Computes the minimal diff (s-sync-s4) and applies it: each added/changed
        doc is read from the current source (resolved doc + its bundle entries)
        and written to ``to_source`` via ``save_document`` — so the s-sync-s3
        atomic net persists doc + bundle entries together. ``prune`` deletes docs
        that exist only in ``to_source``. ``include`` (e.g. authored-only)
        narrows the set. ``dry_run`` returns the diff without writing.

        Returns ``{added, changed, removed, applied}`` where ``applied`` lists
        ``("write"|"delete", kind, name)``. Idempotent: a second push finds an
        empty diff and applies nothing.

        s-kernel-decompose-god-object: delegates to ``self._sync`` (SourceSync).
        """
        return await self._sync.push_scope(
            scope, to_source, tenant=tenant, include=include,
            dry_run=dry_run, prune=prune,
        )

    def kind_by_container(self, container: str) -> "str | None":
        """Return the kind name whose StorageDescriptor.container matches.
        Delegates to ``self._kindreg`` (None for empty/unregistered)."""
        return self._kindreg.by_container(container)

    def serialize_document(self, scope: str, kind: str, name: str, raw: dict) -> dict:
        """Serialize a document to files without writing. Delegates to
        ``self._bundleio`` (s-kernel-decompose-god-object)."""
        return self._bundleio.serialize(scope, kind, name, raw)

    # -- Instance creation ----------------------------------------------------

    def build(
        self,
        raw_docs: list[dict],
        scope: str,
        layers: dict[str, str] | None = None,
        layer_docs: list[dict] | None = None,
        dep_docs: list[dict] | None = None,
        resolve_errors: list[str] | None = None,
        *,
        skip_async_rescan: bool = False,
    ) -> "ManifestInstance":
        """Build ManifestInstance from pre-loaded data. Pure computation, no I/O.

        For async contexts (server), the caller loads docs via await and passes them here.
        For sync contexts (CLI), use instance() which handles the async bridging.

        ``skip_async_rescan`` (set by ``instance_async`` when it will run the
        rescan post-build): suppress the sync rescan path. Delegates to
        ``self._builder`` (s-kernel-decompose-god-object)."""
        return self._builder.build(
            raw_docs, scope, layers, layer_docs, dep_docs, resolve_errors,
            skip_async_rescan=skip_async_rescan,
        )

    # ─── L2 granular kernel API ────────────────────────────────────
    #
    # Story s-kernel-granular-api (f-source-granular-access).
    #
    # Hot path para Studio: /scopes/X/tree e /docs/Kind/Name precisam
    # apenas de metadata OU de UM doc. Não precisam reconstruir a
    # ManifestInstance inteira. Estes 2 métodos delegam aos métodos
    # granulares do SourcePort (L1) com LRU cache bounded + single-
    # flight lock pra eliminar races concorrentes.

    async def list_documents(
        self, scope: str, *, kind: str | None = None,
        tenant: str | None = None,
    ) -> list[tuple[str, str]]:
        """Lista (kind, name) de docs no scope. Filtrável por kind.

        Não constrói ManifestInstance. Custo ~10ms PG / ~5ms SQLite /
        ~30ms FS (este último cai no fallback load_all).

        Cache: per (scope, kind, tenant) com TTL 30s. Invalidado pelo
        kernel.write_document via _invalidate_granular_cache. Single-
        flight via lock — N requests concorrentes na mesma key
        compartilham a fetch.
        """
        assert self._source, "No source registered."
        key = (scope, kind or "", tenant or "")
        return await self._granular_list_cached(key)

    async def get_document(
        self, scope: str, kind: str, name: str, *,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """Carrega UM doc por (scope, kind, name). Retorna raw dict ou None.
        Delegado ao ``self._query`` (s-kernel-decompose-god-object). Cache
        bounded 2000/TTL 60s + V1 ``_INHERITABLE_KINDS`` parent fallback vivem
        lá; a API pública (Studio reads, agent routes, deps) é intacta."""
        return await self._query.get_document(scope, kind, name, tenant=tenant)

    # ────────────────────────────────────────────────────────────────
    # Composition Engine V2 (Phase 17, Story s-comp-f2-resolver,
    # 2026-05-28) — declarative cross-scope + tenant overlay resolution
    # with provenance.
    #
    # ``resolve_document`` will eventually SUPERSEDE ``get_document``
    # for inherited Kinds — V2 strips the ad-hoc ``_INHERITABLE_KINDS``
    # fallback and routes every read through the resolver chain.
    # During the transition (F2 → F10) both coexist; old callers keep
    # working via ``get_document`` which falls back to the V1 fixed
    # parent scope.
    # ────────────────────────────────────────────────────────────────

    async def _compute_resolution_chain(
        self, scope: str, tenant: str | None,
    ) -> list:
        """Walk ``Genome.spec.parent_scope`` transitively and produce the
        ordered resolution chain of ``(scope, tenant)`` pairs.

        Order is HIGHEST priority first:
          [(scope, tenant), (scope, None),
           (parent, tenant), (parent, None),
           (grandparent, tenant), (grandparent, None), ...]

        When ``tenant`` is None, only base layers are emitted per scope.

        Cycle detection via visited set. Depth capped at
        ``MAX_RESOLUTION_DEPTH``. Missing Genome or missing
        parent_scope terminates the walk.
        """
        return await self._composition.compute_resolution_chain(scope, tenant)

    async def _get_composition_rule(
        self, scope: str, kind: str,
    ) -> tuple[str, str, str]:
        """Resolve composition rule ``(scope_inheritance, merge_strategy,
        tenant_overlay)`` for ``(scope, kind)``.

        Lookup order:
          1. LayerPolicy doc of the scope with
             ``spec.composition_rules[kind]``.
          2. V1 backward-compat default — if kind ∈
             ``DEFAULT_INHERITABLE_KINDS_V1``, returns
             ``(enabled, override_full, field_level)``.
          3. Otherwise ``(disabled, override_full, none)``.

        Note: LayerPolicy itself is BOOTSTRAP — never inherits, never
        overlaid. We read it locally only.
        """
        return await self._composition.get_composition_rule(scope, kind)

    async def resolve_document(
        self, scope: str, kind: str, name: str, *,
        tenant: str | None = None,
    ):
        """Resolve a doc through the composition chain — Phase 17 primitive.

        Returns ``ResolvedDocument`` with merged doc + full provenance.

        Bootstrap Kinds (Genome, LayerPolicy, KindDefinition) bypass
        inheritance entirely — read local-only, single-layer provenance.

        For all other Kinds:
          1. Look up composition rule for ``kind`` in scope's LayerPolicy.
          2. Determine resolution chain (walking parent_scope when
             ``scope_inheritance=enabled``; just [(scope, tenant),
             (scope, None)] otherwise).
          3. For each chain layer, query source via cache.
          4. Apply merge strategy (``override_full`` or ``field_level``).
          5. Build ResolvedDocument with provenance + is_inherited.

        Cache: layer-level via ``_granular_doc_cached`` (same TTL/bound
        as ``get_document``). Resolution chain itself is recomputed each
        call (cheap — Genome walk).
        """
        return await self._composition.resolve_document(
            scope, kind, name, tenant=tenant,
        )

    async def composition_summary(
        self, scope: str, *, tenant: str | None = None,
    ) -> dict:
        """Phase 17 (s-comp-f7-composition-summary, 2026-05-28) —
        cheap aggregate of the scope's parent chain + per-Kind counts.

        Single endpoint replaces N list calls from the Sidebar. Returns:

            {
              "scope": "innovec-prod",
              "parent_chain": ["innovec-base", "_lib"],
              "resources": {
                "Agent":  {"local": 1, "inherited": 11, "total": 12},
                "LottieAsset":   {"local": 0, "inherited": 6,  "total": 6},
                ...
              },
            }

        Performance: each Kind takes 1 source.query (local-only push-down)
        + 1 source.query (parent push-down dedup) ≈ 10ms ¢. Cached
        server-side 60s via outer HTTP cache (see API route).

        NB: kept inline (NOT extracted to the CompositionResolver collaborator in
        Fase 5) because it needs the ``query`` push-down, and widening
        ``CompositionResolverHost`` with ``RecordQuery`` would break the frozen
        F1 ``FakeKernelSlice`` guard (whose composition fake exposes no ``query``).
        It is a thin aggregation over the ``query`` facade + ``_compute_resolution_chain``.
        """
        from dna.kernel.resolver import DEFAULT_INHERITABLE_KINDS_V1

        # Parent chain: derived from Genome.parent_scope + V1 fallback.
        chain = await self._compute_resolution_chain(scope, None)
        parent_chain = [s for s, _ in chain if s != scope]
        # Dedup (chain has (scope,None) pairs; collapse to unique parents).
        seen: list[str] = []
        for s in parent_chain:
            if s not in seen:
                seen.append(s)
        parent_chain = seen

        # Per-Kind counts via origin filter.
        resources: dict[str, dict[str, int]] = {}
        for kind in sorted(DEFAULT_INHERITABLE_KINDS_V1):
            local_count = 0
            inherited_count = 0
            installed_count = 0  # Phase 3b ch3 (i-112) — the Catalog tier.
            try:
                async for _ in self.query(
                    scope, kind, tenant=tenant, origin="local",
                ):
                    local_count += 1
                async for _ in self.query(
                    scope, kind, tenant=tenant, origin="inherited",
                ):
                    inherited_count += 1
                async for _ in self.query(
                    scope, kind, tenant=tenant, origin="installed",
                ):
                    installed_count += 1
            except Exception as e:  # noqa: BLE001
                # fail-soft: summary é leitura best-effort — um Kind com
                # source quebrado sai da contagem, com log.
                logger.debug(
                    "composition_summary: query failed for kind %s in %s: %s",
                    kind, scope, e,
                )
                continue
            if local_count or inherited_count or installed_count:
                resources[kind] = {
                    "local": local_count,
                    "inherited": inherited_count,
                    "installed": installed_count,
                    "total": local_count + inherited_count + installed_count,
                }

        return {
            "scope": scope,
            "parent_chain": parent_chain,
            "resources": resources,
        }

    async def personalize_document(
        self, target_scope: str, kind: str, name: str, *,
        tenant: str | None = None,
        overwrite: bool = False,
    ):
        """Phase 17 (s-comp-f6-personalize-primitive, 2026-05-28) —
        clone an inherited doc into ``target_scope`` as a local override.

        Resolves the doc via composition chain; if the effective layer
        is THIS scope (not inherited), raises ValueError. Otherwise
        clones spec + bundle entries to ``target_scope`` atomically.

        Args:
            target_scope: where the override should land.
            kind, name: doc identity.
            tenant: writes go to base layer (tenant=None) by default;
                pass a tenant slug for tenant-overlay personalization.
            overwrite: if False (default) raises when target_scope
                already has a local doc with this name.

        Returns:
            ``ResolvedDocument`` of the freshly written local copy.

        Raises:
            ValueError: doc isn't inherited / target already exists
                (without overwrite=True).
        """
        return await self._composition.personalize_document(
            target_scope, kind, name, tenant=tenant, overwrite=overwrite,
        )

    async def query(
        self, scope: str, kind: str, *,
        filter: dict | None = None,
        projection: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: list[str] | None = None,
        tenant: str | None = None,
        origin: str = "all",
        scopes: list[str] | None = None,
    ):
        """Marco A kernel-level query — push-down delegado ao source.

        Delegado ao ``self._query`` (s-kernel-decompose-god-object). Tenant
        auto-stamp (kwarg > ``Kernel.tenant`` > None), origin filter
        (local/inherited/all), a chain de scope-inheritance e o cross-scope
        ``scopes=`` (F2.4 — queries locais por scope, concat sem dedup;
        ``scopes`` ganha do ``scope`` posicional) vivem lá. Mantido como
        async generator aqui pra preservar a assinatura exata (callers
        fazem ``async for`` + ``inspect.isasyncgenfunction``). API intacta.
        """
        async for row in self._query.query(
            scope, kind,
            filter=filter, projection=projection,
            limit=limit, offset=offset, order_by=order_by,
            tenant=tenant, origin=origin, scopes=scopes,
        ):
            yield row

    async def count(
        self, scope: str, kind: str, *,
        filter: dict | None = None,
        group_by: str | None = None,
        tenant: str | None = None,
        scopes: list[str] | None = None,
    ) -> dict:
        """F2 D2 — aggregation count público ao lado de ``query``.

        Push-down ao source (PG: ``SELECT count(*) … GROUP BY`` nativo;
        FS/SQLite: protocol-default). Retorna ``CountResult``:
        ``{"total": int, "groups": [{"key", "count"}] | None}`` (groups
        por count DESC, key ASC None-last).

        SEM ``origin`` de propósito — records são por-scope; herança não
        se aplica a count (spec D5). Cross-scope via ``scopes=`` (soma
        totals + merge de groups por key; ganha do ``scope`` posicional).

        Example (Studio velocity):
            res = await kernel.count(
                "dna-development", "Story", group_by="spec.status",
            )
            # {"total": 950, "groups": [{"key": "done", "count": 700}, …]}
        """
        return await self._query.count(
            scope, kind,
            filter=filter, group_by=group_by, tenant=tenant, scopes=scopes,
        )

    def record_search_provider(self, provider) -> None:
        """Register the semantic-search provider (two-planes F2). One per
        kernel; later registration replaces (boot-time wiring) and resets
        the failure-warning damper (new provider → fresh episode)."""
        self._search_provider = provider
        self._search_provider_warned = False

    async def search(
        self, scope: str, query_text: str, *,
        kind: str | None = None, k: int = 10, tenant: str | None = None,
    ) -> dict[str, Any]:
        """Public record search (F2 D2). Provider registered → semantic
        (pgvector/RRF, degraded=False); no provider OR provider error → lexical
        token-match fallback (degraded=True). Thin facade over the SearchEngine
        collaborator (s-kernel-decomp-f5-satellites)."""
        return await self._search.search(
            scope, query_text, kind=kind, k=k, tenant=tenant,
        )

    async def _lexical_search(
        self, scope: str, query_text: str, *,
        kind: str | None = None, k: int = 10, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Degraded lexical fallback for ``search()`` — honest token-match scan,
        NOT similarity (two-planes F2). Thin facade over the SearchEngine
        collaborator (s-kernel-decomp-f5-satellites)."""
        return await self._search._lexical_search(
            scope, query_text, kind=kind, k=k, tenant=tenant,
        )

    def query_list_sync(
        self, scope: str, kind: str, *,
        filter: dict | None = None,
        tenant: str | None = None,
    ) -> list[Document]:
        """Sync wrapper around ``query`` returning parsed ``Document`` objects
        (drop-in for ``mi.all(kind)``). Delegado ao ``self._query``
        (s-kernel-decompose-god-object); ``_run_sync_helper`` + main-loop
        binding vivem lá. API intacta (CLI, workers, tool executors)."""
        return self._query.query_list_sync(scope, kind, filter=filter, tenant=tenant)

    def get_document_sync(
        self, scope: str, kind: str, name: str, *,
        tenant: str | None = None,
    ) -> Document | None:
        """Sync wrapper around ``get_document`` returning a parsed ``Document``
        (drop-in for ``mi.one(kind, name)``). Delegado ao ``self._query``
        (s-kernel-decompose-god-object). API intacta."""
        return self._query.get_document_sync(scope, kind, name, tenant=tenant)

    # ─── Internal: LRU + single-flight ──────────────────────────────

    _GRANULAR_LIST_TTL = 30.0   # seconds
    _GRANULAR_DOC_TTL = 60.0    # seconds
    _GRANULAR_DOC_MAX = 2000    # entries (LRU bound)
    _BASE_INSTANCE_MAX = 64     # scopes (LRU bound on _base_instance_cache, i-036)
    _LAYER_OBSERVERS_MAX = 4096  # reverse-dep entries (LRU bound, s-kernel-bound-layer-observers)

    async def _granular_list_cached(self, key: tuple[str, str, str]):
        """Cached ``[(kind, name)]`` for a (scope, kind, tenant) key. The
        source-load on a miss stays here (kernel owns source/readers); the
        TTL + single-flight machinery lives in ``self._kcache``
        (s-kernel-decompose-god-object)."""
        async def _load(k: tuple[str, str, str]):
            scope, kind_or_empty, tenant_or_empty = k
            kind_arg = kind_or_empty or None
            tenant_arg = tenant_or_empty or None
            # Try L1 granular method on source; fall back to load_all+filter
            source = self._source
            assert source is not None
            list_method = getattr(source, "list_doc_refs", None)
            if list_method is not None:
                return await list_method(scope, kind=kind_arg, tenant=tenant_arg)
            # Legacy adapter — fall back to mi.documents projection
            docs = await source.load_all(scope, readers=self._readers)
            value = []
            for d in docs:
                kk = d.get("kind", "")
                n = (d.get("metadata") or {}).get("name") or d.get("name", "")
                if not kk or not n:
                    continue
                if kind_arg and kk != kind_arg:
                    continue
                value.append((kk, n))
            value.sort()
            return value

        return await self._kcache.list_cached(key, _load)

    async def _granular_doc_cached(self, key: tuple[str, str, str, str]):
        """Cached raw dict for a (scope, kind, name, tenant) key. Source-load on
        a miss stays here; TTL + single-flight + LRU live in ``self._kcache``."""
        async def _load(k: tuple[str, str, str, str]):
            scope, kind, name, tenant_or_empty = k
            tenant_arg = tenant_or_empty or None
            source = self._source
            assert source is not None
            load_method = getattr(source, "load_one", None)
            if load_method is not None:
                return await load_method(
                    scope, kind, name, readers=self._readers, tenant=tenant_arg,
                )
            # Legacy adapter — fall back to load_all + find
            docs = await source.load_all(scope, readers=self._readers)
            for d in docs:
                if d.get("kind") != kind:
                    continue
                n = (d.get("metadata") or {}).get("name") or d.get("name", "")
                if n == name:
                    return d
            return None

        return await self._kcache.doc_cached(key, _load)

    def _invalidate_granular_cache(
        self, scope: str, kind: str | None = None, name: str | None = None,
    ) -> None:
        """Delegate to ``self._kcache.invalidate_granular`` (kept as a thin
        wrapper so write_document/delete_document call sites are unchanged)."""
        self._kcache.invalidate_granular(scope, kind, name)

    # ─── End L2 granular API ───────────────────────────────────────

    # ─── Catalog tier (Phase 3b ch1, i-112) ────────────────────────
    # Thin facades over the CatalogCache collaborator
    # (s-kernel-decomp-f5-satellites). The cache DICT (_catalog_cache) stays
    # kernel-owned + shared by identity across with_tenant copies (spec Risk #3,
    # pinned by test_kernel_catalog_tenant_characterization); the collaborator is
    # stateless compute over it.
    async def _catalog_scopes(
        self, tenant: "str | None", *, exclude: set[str] | None = None,
    ) -> list[tuple[str, "str | None"]]:
        """The ordered Catalog scope set for ``tenant`` (cached per tenant, TTL
        60s, fail-soft → ``[]``). ``exclude`` drops the scope being resolved; the
        base/``_lib`` scope is always excluded. Delegates to ``self._catalog``."""
        return await self._catalog.catalog_scopes(tenant, exclude=exclude)

    async def _compute_catalog_scopes(
        self, tenant: "str | None", base_exclude: set[str],
    ) -> list[tuple[str, "str | None"]]:
        """Uncached data-gathering for ``_catalog_scopes`` — Genome scan + tenant
        lockfile → pure ``resolve_catalog_scopes``. Delegates to ``self._catalog``."""
        return await self._catalog._compute_catalog_scopes(tenant, base_exclude)

    def _invalidate_catalog_cache(self, tenant: "str | None" = None) -> None:
        """Drop the Catalog scope cache — one tenant, or ALL when ``tenant`` is
        ``None`` (a Genome write changes the mandatory set for EVERY tenant).
        Mutates the kernel-owned shared dict in place; delegates to ``self._catalog``."""
        self._catalog.invalidate(tenant)

    def instance(self, scope: str, layers: dict[str, str] | None = None) -> "ManifestInstance":
        """Sync wrapper around `instance_async`. Use this from sync
        contexts (CLI, tests). From inside an event loop, prefer
        `await kernel.instance_async(scope, layers)` directly to avoid
        the asyncio.run-in-thread fallback that orphans pool-based
        adapters. Delegates to ``self._builder`` (s-kernel-decompose-god-object).
        """
        return self._builder.instance(scope, layers)

    async def instance_async(
        self, scope: str, layers: dict[str, str] | None = None,
        *, lazy: bool | None = None,
    ) -> "ManifestInstance":
        """Async-native version of `instance`. Use directly from async
        contexts (FastAPI lifespan, Temporal activities) to keep the
        source pool tied to the caller's event loop.

        Phase 9: tenant binding auto-promotes into layers so
        load_bootstrap_docs + load_layer pick up the right tenant overlay.

        Story s-miholder-transient (2026-05-14): ``lazy`` kwarg lets
        callers explicitly opt into lazy MI construction (bootstrap
        docs only; mi.all/one delegate to kernel.query). Default
        ``None`` honors ``DNA_LAZY_MI`` env var. ``True``/``False``
        override.
        """
        return await self._builder.instance_async(scope, layers, lazy=lazy)

    def resolve_layers(self, mi: "ManifestInstance", layers: dict[str, str]) -> "ManifestInstance":
        """Resolve layers on an existing MI (sync wrapper). Delegates to
        ``self._builder`` (s-kernel-decompose-god-object)."""
        return self._builder.resolve_layers(mi, layers)

    async def resolve_layers_async(
        self, mi: "ManifestInstance", layers: dict[str, str],
    ) -> "ManifestInstance":
        """Async-native layer resolver — MI.resolve_async() delegates here, then
        through ``self._builder`` (s-kernel-decompose-god-object)."""
        return await self._builder.resolve_layers_async(mi, layers)

    def _register_kind_definitions(self, all_raws: list[dict[str, Any]]) -> bool:
        """2-phase load Phase 1 — parse per-scope KindDefinition docs + register
        synthetic DeclarativeKindPorts (warn+skip on conflict). Thin facade over
        the KindRegistry funnel (s-kernel-decomp-f3-kindregistry). Returns True
        iff a NEW BUNDLE reader was added (the rescan gate)."""
        return self._kindreg.register_kind_definitions(all_raws)

    def _register_custom_kinds(self, manifest: dict[str, Any]) -> None:
        """Register dynamic Module.spec.custom_kinds. Thin facade over the
        KindRegistry funnel (s-kernel-decomp-f3-kindregistry)."""
        self._kindreg.register_custom_kinds(manifest)

    @staticmethod
    def _fill_derived_description(raw: dict[str, Any], kind_port: Any) -> None:
        """If a kind declares ``description_fallback_field`` and metadata.description
        is missing/empty, derive it from the named spec field. Mutates ``raw``."""
        field = getattr(kind_port, "description_fallback_field", None)
        if not field:
            return
        meta = raw.setdefault("metadata", {})
        if meta.get("description"):
            return
        from dna.kernel._text import derive_first_line
        text = (raw.get("spec") or {}).get(field)
        derived = derive_first_line(text)
        if derived:
            meta["description"] = derived

    def _parse_doc(self, raw: dict[str, Any], origin: str = "local") -> Document:
        av = raw.get("apiVersion", "")
        kn = raw.get("kind", "")
        name = (raw.get("metadata") or {}).get("name", "")
        kind_port = self._kinds.get((av, kn))
        typed = None
        if kind_port:
            try:
                self._fill_derived_description(raw, kind_port)
                typed = kind_port.parse(raw)
            except Exception as e:
                logger.warning("Parse error for %s/%s: %s", av, kn, e)
                # Emit parse_error event so consumers can react
                if self.hooks.has("parse_error"):
                    from dna.kernel.hooks import HookContext
                    self.hooks.emit("parse_error", HookContext(
                        kind=kn, name=name,
                        data={"error": str(e), "apiVersion": av, "raw": raw},
                    ))
        doc = Document.from_raw(raw, typed=typed)
        doc.origin = origin
        return doc

    # -- Model registry -------------------------------------------------------

    # The ModelProfile Kind is GLOBAL — it lives exclusively in the _lib
    # scope and is NOT in _INHERITABLE_KINDS (so per-scope inheritance never
    # surfaces it). This helper MUST query _lib directly, never the
    # caller's scope, to avoid silent no-op when the caller has a different
    # scope that contains zero ModelProfile docs.
    _MODEL_REGISTRY_SCOPE = SYSTEM_SCOPE

    # Fallback realtime model assumed when a voice Agent declares no
    # explicit ``spec.voice_persona.model`` — used by the write-path
    # prompt-budget guard (a ``pre_save`` veto hook registered by the
    # Helix extension: ``extensions/helix/write_guards.py``).
    # s-realtime-model-single-default: the realtime fallback the prompt-budget
    # gate caps against. Read the SAME env the voice server pins on
    # (DNA_VOICE_REALTIME_MODEL) at access-time so the kernel's cap and the
    # minted session can't drift to different realtime models. The literal is
    # the fallback only.
    _DEFAULT_REALTIME_MODEL_FALLBACK = "gpt-realtime-2"

    @property
    def _DEFAULT_REALTIME_MODEL(self) -> str:
        return os.environ.get("DNA_VOICE_REALTIME_MODEL") or self._DEFAULT_REALTIME_MODEL_FALLBACK

    async def model_profile(self, model_id_or_alias: str) -> dict | None:
        """Resolve a ModelProfile from the _lib registry by model_id, then by
        aliases[]. Returns the RAW DICT row (callers read ``profile["spec"][...]``)
        or None. _lib-direct + fail-soft. Thin facade over the RegistryAccessor
        collaborator (s-kernel-decomp-f5-satellites)."""
        return await self._registry.model_profile(model_id_or_alias)

    # VoicePolicy is GLOBAL — _lib-resident like ModelProfile. Same
    # _lib-direct lookup rationale (a per-scope query would silently
    # no-op for scopes with zero VoicePolicy docs).
    _VOICE_POLICY_SCOPE = SYSTEM_SCOPE

    async def voice_policy(self, name: str = "default") -> dict | None:
        """Resolve a VoicePolicy from the _lib registry by metadata name (falls
        back to the first policy). Returns the RAW DICT row or None. _lib-direct
        + fail-soft. Thin facade over the RegistryAccessor collaborator
        (s-kernel-decomp-f5-satellites)."""
        return await self._registry.voice_policy(name)

    # The embedding profile is GLOBAL — _lib-resident like ModelProfile /
    # VoicePolicy. The embedding model+dimension are intrinsically global (the
    # stored vectors + every query must share one embedding space), so this is
    # NOT per-scope. CognitivePolicy.recall.calibrated_for points back here.
    # s-consolidate-cognitive-policies: the standalone EmbeddingProfile Kind
    # was folded into CognitivePolicy.spec.embedding; this accessor keeps the
    # _lib-direct invariant (a scope-level CognitivePolicy CANNOT fork the
    # embedding space — its `embedding` section is never read).
    _EMBEDDING_PROFILE_SCOPE = SYSTEM_SCOPE

    async def embedding_profile(self, name: str = "default") -> dict | None:
        """Resolve the embedding profile from the _lib CognitivePolicy by name.
        Returns a RAW-DICT-shaped row whose ``spec`` is the doc's ``embedding``
        section, or None. _lib-direct + fail-soft. Thin facade over the
        RegistryAccessor collaborator (s-kernel-decomp-f5-satellites)."""
        return await self._registry.embedding_profile(name)

    # -- Quick-start ----------------------------------------------------------

    @classmethod
    def quick(cls, scope: str, base_dir: str = ".dna") -> "ManifestInstance":
        """Quick-start: a filesystem Kernel with every discoverable extension
        loaded, returning the ManifestInstance for ``scope``. Thin facade over
        ``build_quick_manifest`` (kernel decomposition, Fase 4 —
        ``s-kernel-decomp-f4-bootstrap``). ``cls`` is threaded through so a
        subclass (e.g. ``Runtime``) is what gets built."""
        from dna.kernel.kernel_bootstrap import build_quick_manifest
        return build_quick_manifest(scope, base_dir, cls=cls)

    @classmethod
    def auto(cls, source=None) -> "Kernel":
        """Create a Kernel with all discoverable extensions loaded.

        Thin facade over ``build_auto_kernel`` (kernel decomposition, Fase 4 —
        ``s-kernel-decomp-f4-bootstrap``): entry-point discovery + H8
        deterministic topo-sort boot ordering + source/cache/resolver wiring +
        ``validate_dep_filters`` gate. ``cls`` is threaded through so a subclass
        (e.g. ``Runtime``) is what gets built. See the collaborator module for
        the full recipe + rationale."""
        from dna.kernel.kernel_bootstrap import build_auto_kernel
        return build_auto_kernel(source, cls=cls)
