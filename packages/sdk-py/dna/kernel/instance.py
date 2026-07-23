"""ManifestInstance v3 — public API for querying manifest documents.

Provides query (all/one/root), navigation (get/describe/list_kinds/summary),
prompt building (build_prompt with template cascade), and layer resolution.

Namespace API (Chunk 2 extraction):
- ``mi.prompt.build()``       — PromptBuilder
- ``mi.composition.validate()`` — CompositionEngine
- ``mi.nav.describe()``       — Navigator
- ``mi.lock.generate()``      — LockManager

Old methods are preserved as one-line delegates; both APIs return identical
results.  Implementation lives in the namespace classes.
"""
from __future__ import annotations

import logging
from functools import cached_property
from typing import Any, TYPE_CHECKING

from dna.kernel.document import Document
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import CompositionResult, KindPort, SourcePort

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dna.kernel.prompt.builder import PromptBuilder, PromptExplanation
    from dna.kernel.composition_resolver import CompositionEngine
    from dna.kernel.navigator import Navigator
    from dna.kernel.lock.manager import LockManager
    from dna.kernel.lock import Lockfile
    from dna.kernel.reports import ReportBuilder


class ManifestInstance:
    """Facade over a loaded manifest scope.

    Marco B (s-lazy-manifest-instance-class, 2026-05-14): supports a
    LAZY mode where the constructor only receives bootstrap docs
    (Genome + KindDefinition + LayerPolicy + UA index ~30 docs)
    instead of the full scope (often 1500+). In lazy mode:

      - ``one(kind, name)``  → delegates to ``kernel.get_document``
                                (L2 cached, ~5ms).
      - ``all(kind)``        → delegates to ``kernel.query``
                                (~10ms indexed).
      - ``documents``        → triggers ``_ensure_loaded()`` which
                                materializes the full scope. Emits a
                                DeprecationWarning when called in lazy
                                mode — callers should use one/all or
                                kernel.query directly.

    Bootstrap kinds (always eager) keep ``mi.root``, ``mi.kind_for``,
    namespace getters (``mi.composition``, ``mi.nav``) functional
    cheaply. Heavy operations like ``mi.summary()`` /
    ``mi.composition.validate()`` that iterate the full scope still
    force the materialization, but that's the explicit ask.

    To enable lazy mode: pass ``lazy=True`` to the constructor (the
    Kernel does this when ``DNA_LAZY_MI=1``). When ``lazy=False``
    (default), ``ManifestInstance`` behaves exactly as before — full
    back-compat for tests, agent paths, and external callers.
    """

    # Bootstrap kinds — always eager-loaded in the documents list.
    # These are needed by mi.root, mi.kind_for, and the prompt builder
    # before any lazy lookup happens.
    _BOOTSTRAP_KINDS = frozenset({"Genome", "KindDefinition", "LayerPolicy"})

    def __init__(
        self,
        scope: str,
        documents: list[Document],
        kinds: dict[tuple[str, str], KindPort],
        source: SourcePort | None = None,
        resolve_errors: list[str] | None = None,
        kernel: Any = None,
        profiles: list | None = None,
        lazy: bool = False,
    ) -> None:
        self.scope = scope
        self._documents = documents
        self._kinds = kinds
        self._source = source
        self._kernel = kernel
        self.resolve_errors = resolve_errors or []
        self._profiles: list = profiles or []
        # Lazy state
        self._lazy = lazy
        self._lazy_full_loaded = not lazy
        self._lazy_kind_cache: dict[str, list[Document]] = {}

        # Lazy namespace caches
        self._prompt_builder: PromptBuilder | None = None
        self._composition_engine: CompositionEngine | None = None
        self._navigator: Navigator | None = None
        self._lock_manager: LockManager | None = None
        self._report_builder: ReportBuilder | None = None

    @property
    def documents(self) -> list[Document]:
        """Materialized list of all docs. In lazy mode, accessing this
        triggers a full load (the only way to honor list semantics).
        Prefer ``one(kind, name)`` or ``all(kind)`` which stay lazy.

        Emits a DeprecationWarning in lazy mode the first time the
        full set is materialized.
        """
        if self._lazy and not self._lazy_full_loaded:
            import warnings
            warnings.warn(
                f"ManifestInstance.documents accessed in lazy mode for "
                f"scope={self.scope!r} — forcing full scope load. "
                f"Prefer `await kernel.query(scope, kind)` / "
                f"`await kernel.get_document(scope, kind, name)` which "
                f"stay lazy and indexed. To force eager loading at "
                f"construct time, pass lazy=False to "
                f"Kernel.instance_async.",
                DeprecationWarning, stacklevel=2,
            )
            self._materialize_full()
        return self._documents

    @documents.setter
    def documents(self, value: list[Document]) -> None:
        """Allow internal code to replace the documents list (used by
        ``apply_hooks`` and ``_materialize_full``)."""
        self._documents = value
        self._lazy_full_loaded = True

    def _materialize_full(self) -> None:
        """Block-load the full scope when lazy mode bumps into a
        full-iteration API. Idempotent.

        Decisão declarada (two-planes F2.5 Task 2): este caminho lazy
        ainda materializa RECORDS (load_all sem filtro de plane) —
        inconsistente com o build eager (InstanceBuilder.build exclui
        records). Aceito: o lazy mode é legado e o ratchet não o
        exercita; alinhar é follow-up ("Fora deste plano") se o lazy
        mode sobreviver à s-mi-class-death.
        """
        if self._lazy_full_loaded:
            return
        if self._kernel is None or self._source is None:
            # No kernel/source — can't lazy-load. Already at whatever
            # the constructor was given.
            self._lazy_full_loaded = True
            return
        # Use the source.load_all for parity with non-lazy
        # ManifestInstance — same parsing, same readers.
        #
        # Story s-mi-class-death (2026-05-14): replaced the
        # ThreadPoolExecutor + asyncio.run trap that orphaned the
        # asyncpg pool's event-loop binding (same bug that
        # _lazy_load_kind hit). Now uses _run_sync_helper which
        # dispatches via run_coroutine_threadsafe to the kernel's
        # registered main loop — pool stays loop-bound.
        from dna.kernel import _run_sync_helper
        readers = list(getattr(self._kernel, "_readers", []))

        async def _load():
            return await self._source.load_all(self.scope, readers=readers)

        raw_docs = _run_sync_helper(
            _load(), loop=getattr(self._kernel, "_main_loop", None),
        )

        # Parse raw docs into Documents — reuse the kernel's parsing.
        # Parse raw → Document via the kernel's own parser (preserves
        # typed dispatch + hook emission for parse_error).
        _parse = getattr(self._kernel, "_parse_doc", None)
        parsed = [_parse(r) for r in raw_docs] if _parse else []
        # Keep bootstrap docs from constructor (they may have come
        # from a different code path), merge with newly-loaded ones,
        # deduping by (kind, name).
        existing_keys = {(d.kind, d.name) for d in self._documents}
        merged = list(self._documents)
        for d in parsed:
            if (d.kind, d.name) not in existing_keys:
                merged.append(d)
        self._documents = merged
        self._lazy_full_loaded = True

    # -- Namespace properties --------------------------------------------------

    @property
    def prompt(self) -> PromptBuilder:
        """Namespace: ``mi.prompt.build()``."""
        if self._prompt_builder is None:
            from dna.kernel.prompt.builder import PromptBuilder
            self._prompt_builder = PromptBuilder(self)
        return self._prompt_builder

    @property
    def composition(self) -> CompositionEngine:
        """Namespace: ``mi.composition.validate()``."""
        if self._composition_engine is None:
            from dna.kernel.composition_resolver import CompositionEngine
            self._composition_engine = CompositionEngine(self)
        return self._composition_engine

    @property
    def nav(self) -> Navigator:
        """Namespace: ``mi.nav.describe()`` / ``summary()`` / ``inventory()``."""
        if self._navigator is None:
            from dna.kernel.navigator import Navigator
            self._navigator = Navigator(self)
        return self._navigator

    @property
    def lock(self) -> LockManager:
        """Namespace: ``mi.lock.generate()``."""
        if self._lock_manager is None:
            from dna.kernel.lock.manager import LockManager
            self._lock_manager = LockManager(self)
        return self._lock_manager

    @property
    def reports(self) -> ReportBuilder:
        """Namespace: ``mi.reports.eval_summary()`` / ``findings_summary()``."""
        if self._report_builder is None:
            from dna.kernel.reports import ReportBuilder
            self._report_builder = ReportBuilder(self)
        return self._report_builder

    def profile_for(self, doc: Any):
        """Find the CompositionProfile for a doc's kind (via alias)."""
        from dna.kernel.composition_resolver import profile_for_orchestrator
        kp = self._kinds.get((doc.api_version, doc.kind))
        if not kp:
            return None
        return profile_for_orchestrator(self._profiles, getattr(kp, "alias", ""))

    # -- Query ----------------------------------------------------------------

    def _is_record_kind(self, kind: str) -> bool:
        """two-planes F2.5 — records nunca vêm da materialização; a MI
        delega leituras de plane="record" pro kernel (query/get_document),
        então leitores não-migrados continuam corretos (o ratchet os
        encolhe por perf). Kernels sem ``kind_plane`` (mocks/embedders
        legados) caem no caminho legado (composition)."""
        if self._kernel is None:
            return False
        plane_fn = getattr(self._kernel, "kind_plane", None)
        if not callable(plane_fn):
            return False
        return plane_fn(kind) == "record"

    def all(self, kind: str) -> list[Document]:
        """Return all docs of ``kind`` — DEPRECATED, will be removed in 1.0.

        s-blessed-query-surface: the blessed query surface is
        ``mi.documents`` (in-memory, filter by ``d.kind``) plus
        ``kernel.query(scope, kind)`` for indexed / record-plane reads.
        This method survives as a warning shim until 1.0.
        """
        import warnings
        warnings.warn(
            "ManifestInstance.all() is deprecated and will be removed in "
            "1.0 — filter mi.documents (e.g. `[d for d in mi.documents "
            "if d.kind == kind]`) or use `await kernel.query(scope, kind)` "
            "for indexed/record-plane reads.",
            DeprecationWarning, stacklevel=2,
        )
        return self._all(kind)

    def _all(self, kind: str) -> list[Document]:
        """Internal, non-warning twin of :py:meth:`all` — used by the
        SDK's own collaborators (``apply_hooks``, ``ReportBuilder``,
        ``get``). External callers use the blessed surface
        (``mi.documents`` / ``kernel.query``); see ``all()``.

        Lazy mode: when the kind isn't already materialized (bootstrap
        kinds are always present), delegate to ``kernel.query`` and
        cache. Cached entries are dropped by ``apply_hooks`` /
        ``_materialize_full``.

        Eager mode: walks ``self.documents`` (back-compat, O(N)).
        """
        # two-planes F2.5 — plane="record" reads ALWAYS delegate to the
        # kernel record plane (never the materialization, which excludes
        # records post-Task-2). Sync-on-loop callers RAISE via the
        # _run_sync_helper contract — no eager fallback by design (it
        # would be silent-empty); migrate those call-sites to
        # `await kernel.query`.
        if self._is_record_kind(kind):
            return self._kernel.query_list_sync(
                self.scope, kind, tenant=getattr(self, "_tenant", None),
            )
        if self._lazy and not self._lazy_full_loaded:
            # Bootstrap kinds live in self._documents from boot.
            if kind in self._BOOTSTRAP_KINDS:
                return [d for d in self._documents if d.kind == kind]
            # Cached?
            cached = self._lazy_kind_cache.get(kind)
            if cached is not None:
                return cached
            # Materialize via kernel.query (single-kind, full raw rows).
            docs = self._lazy_load_kind(kind)
            self._lazy_kind_cache[kind] = docs
            return docs
        return [d for d in self._documents if d.kind == kind]

    async def all_async(self, kind: str, *, tenant: str | None = None) -> list[Document]:
        """Async-native variant of ``all()`` — bridge for callers
        migrating to ``await kernel.query(scope, kind)``.

        f-mi-class-extinction (Story s-mi-async-bridge, 2026-05-14):
        new API that callers should target during the MI sweep. Returns
        the same list[Document] shape as sync ``all()`` but uses
        ``await kernel.query`` end-to-end — no thread, no asyncio.run,
        no loop-mismatch with asyncpg pools.

        Bootstrap kinds (Genome, KindDefinition, LayerPolicy) are
        served from the in-memory ``self._documents`` (no query).
        Lazy-cached kinds (already materialized by a previous call)
        are served from ``self._lazy_kind_cache``.

        **Tenant note:** does not auto-apply tenant overlay from this
        MI's resolved layer context. Callers that need tenant filtering
        should pass tenant via ``kernel.query(..., tenant=...)``
        directly. The MI overlay-merge is applied at doc content level
        and is observable via this method only when the underlying
        layer storage already filters by tenant (Postgres adapter does).
        """
        # two-planes F2.5 — record kinds delegate straight to kernel.query;
        # never served from (nor cached into) the materialization. NB: no
        # _lazy_kind_cache for records — record writes don't invalidate the
        # MI, so a cache here would serve stale data forever.
        if self._is_record_kind(kind):
            effective_tenant = (
                tenant if tenant is not None else getattr(self, "_tenant", None)
            )
            raw_rows = [
                r async for r in self._kernel.query(
                    self.scope, kind, tenant=effective_tenant,
                )
            ]
            _parse = getattr(self._kernel, "_parse_doc", None)
            if _parse is None:
                return []
            return [d for d in (_parse(r) for r in raw_rows) if d is not None]
        # Bootstrap kinds — already in self._documents from boot.
        if kind in self._BOOTSTRAP_KINDS:
            return [d for d in self._documents if d.kind == kind]
        # Eager-loaded MI — walk in-memory list ONLY if the requested
        # tenant matches this MI's resolved tenant. The eager MI was
        # built with one layer context (``self._tenant``); cross-tenant
        # reads must go through ``kernel.query`` so the source adapter
        # unions base + tenant overlay storage. Without this fallback,
        # an eager base MI (``_tenant=None``) silently drops tenant=X
        # kwargs and reports zero docs even when the overlay table has
        # rows — the bug behind "no EvalRuns visible" with PG source.
        _eager_tenant_fallback = False
        if not self._lazy:
            mi_tenant = getattr(self, "_tenant", None)
            if tenant is None or tenant == mi_tenant:
                return [d for d in self._documents if d.kind == kind]
            # Fall through to kernel.query with the requested tenant.
            # Skip lazy_kind_cache (keyed by kind only — would alias
            # results across tenants in cross-tenant reads).
            _eager_tenant_fallback = True
        # Lazy mode: lazy-cache hit?
        if not _eager_tenant_fallback:
            cached = self._lazy_kind_cache.get(kind)
            if cached is not None:
                return cached
        # Otherwise: kernel.query.
        # Story s-resolve-layers-direct: tenant kwarg takes precedence,
        # then falls back to self._tenant (stamped at MI construction
        # when created with layers={"tenant": X}). Allows callers to
        # bypass the resolve_async overlay-MI pattern entirely:
        #     await holder.mi.all_async("Story", tenant="acme")
        # is equivalent to:
        #     mi = await holder.mi.resolve_async({"tenant": "acme"})
        #     await mi.all_async("Story")
        if self._kernel is None:
            return []
        effective_tenant = tenant if tenant is not None else getattr(self, "_tenant", None)
        raw_rows = []
        async for r in self._kernel.query(self.scope, kind, tenant=effective_tenant):
            raw_rows.append(r)
        _parse = getattr(self._kernel, "_parse_doc", None)
        docs = [_parse(r) for r in raw_rows if _parse(r) is not None] if _parse else []
        # Cache for subsequent calls (sync and async share the cache).
        # Skip caching when this was a cross-tenant eager fallback —
        # the cache key is (kind) only, so two different tenants would
        # alias each other. Lazy mode caches normally.
        if not _eager_tenant_fallback:
            self._lazy_kind_cache[kind] = docs
        return docs

    def _lazy_load_kind(self, kind: str) -> list[Document]:
        """Load docs of a single kind via kernel.query_list_sync.

        Story s-miholder-transient (2026-05-14): replaces the prior
        ThreadPoolExecutor + asyncio.run trap that orphaned the
        asyncpg pool's event-loop binding. Now uses
        ``kernel.query_list_sync`` which routes through
        ``_run_sync_helper(coro, loop=kernel._main_loop)``.

        Story s-resolve-layers-direct (2026-05-14): passes ``self._tenant``
        (stamped at MI construction when layers={"tenant": T}) so
        kernel.query applies the tenant overlay.
        """
        if self._kernel is None:
            return []
        tenant = getattr(self, "_tenant", None)
        try:
            return self._kernel.query_list_sync(self.scope, kind, tenant=tenant)
        except Exception as e:  # noqa: BLE001
            # fail-soft: lazy read path — a broken kernel query degrades to
            # "no docs of this kind" instead of failing the whole MI walk.
            logger.debug(
                "mi.all(%r): kernel query failed for scope %r: %s",
                kind, self.scope, e,
            )
            return []

    def all_where(self, predicate) -> list[Document]:
        """Return all documents whose registered KindPort satisfies a
        predicate. Forces full materialization in lazy mode (cross-kind
        walk requires the whole scope).
        """
        if self._lazy and not self._lazy_full_loaded:
            self._materialize_full()
        result = []
        for d in self._documents:
            kp = self._kinds.get((d.api_version, d.kind))
            if kp and predicate(kp):
                result.append(d)
        return result

    async def one_async(self, kind: str, name: str, *, tenant: str | None = None) -> Document | None:
        """Async-native variant of ``one()`` — bridge for callers
        migrating to ``await kernel.get_document(scope, kind, name)``.

        f-mi-class-extinction (Story s-mi-async-bridge, 2026-05-14):
        new API that callers should target during the MI sweep. Same
        return shape as sync ``one()``. Bootstrap kinds + lazy-cached
        kinds short-circuit; otherwise delegates to
        ``await kernel.get_document`` (L2 cached).
        """
        # two-planes F2.5 — record kinds delegate straight to
        # kernel.get_document; never served from the materialization.
        if self._is_record_kind(kind):
            effective_tenant = (
                tenant if tenant is not None else getattr(self, "_tenant", None)
            )
            raw = await self._kernel.get_document(
                self.scope, kind, name, tenant=effective_tenant,
            )
            if raw is None:
                return None
            _parse = getattr(self._kernel, "_parse_doc", None)
            return _parse(raw) if _parse else None
        # Bootstrap fast-path — only safe when the requested tenant
        # matches this MI's resolved tenant (eager MI may have docs
        # for one tenant context only).
        mi_tenant = getattr(self, "_tenant", None)
        if tenant is None or tenant == mi_tenant:
            for d in self._documents:
                if d.kind == kind and d.name == name:
                    return d
            # Lazy-cache fast-path (same tenant context).
            cached = self._lazy_kind_cache.get(kind)
            if cached is not None:
                for d in cached:
                    if d.name == name:
                        return d
                # s-platform-resources-inherit (2026-05-28): igual mi.one
                # — fall through pra kernel.get_document quando o Kind é
                # inheritable e o scope local não é o parent. Sem isso,
                # lazy_kind_cache=[] mata o fallback.
                inheritable = getattr(self._kernel, "_INHERITABLE_KINDS", frozenset())
                parent_scope = getattr(self._kernel, "_INHERIT_PARENT_SCOPE", None)
                if not (kind in inheritable and parent_scope and self.scope != parent_scope):
                    return None
            # Eager-mode MI: full walk already done; not found.
            if not self._lazy:
                return None
        # Cross-tenant read OR lazy-mode uncached: kernel.get_document.
        # Story s-resolve-layers-direct: tenant kwarg wins over
        # self._tenant (MI construction context). Lets callers ask
        # ``await holder.mi.one_async("X", "y", tenant="acme")`` instead
        # of resolving an overlay MI first.
        if self._kernel is None:
            return None
        effective_tenant = tenant if tenant is not None else getattr(self, "_tenant", None)
        raw = await self._kernel.get_document(
            self.scope, kind, name, tenant=effective_tenant,
        )
        if raw is None:
            return None
        _parse = getattr(self._kernel, "_parse_doc", None)
        return _parse(raw) if _parse else None

    def one(self, kind: str, name: str) -> Document | None:
        """Lookup single doc by (kind, name) — DEPRECATED, will be
        removed in 1.0.

        s-blessed-query-surface: the blessed query surface is
        ``mi.documents`` (in-memory, search by ``d.kind``/``d.name``)
        plus ``kernel.get_document(scope, kind, name)`` for indexed /
        record-plane reads. This method survives as a warning shim
        until 1.0.
        """
        import warnings
        warnings.warn(
            "ManifestInstance.one() is deprecated and will be removed in "
            "1.0 — search mi.documents (e.g. `next((d for d in "
            "mi.documents if d.kind == kind and d.name == name), None)`) "
            "or use `await kernel.get_document(scope, kind, name)` for "
            "indexed/record-plane reads.",
            DeprecationWarning, stacklevel=2,
        )
        return self._one(kind, name)

    def _one(self, kind: str, name: str) -> Document | None:
        """Internal, non-warning twin of :py:meth:`one` — used by the
        SDK's own collaborators (``read_spec``/``read_metadata``).
        External callers use the blessed surface (``mi.documents`` /
        ``kernel.get_document``); see ``one()``.

        Lazy mode: hits bootstrap docs first (in-memory), then delegates
        to ``kernel.get_document`` (L2-cached, ~5ms) — never forces
        full materialization.

        Eager mode: walks ``self._documents`` (back-compat).
        """
        # two-planes F2.5 — record reads delegate to the kernel record
        # plane (see ``all`` — same contract: sync-on-loop RAISES, no
        # eager fallback; migrate to `await kernel.get_document`).
        if self._is_record_kind(kind):
            return self._kernel.get_document_sync(
                self.scope, kind, name, tenant=getattr(self, "_tenant", None),
            )
        if self._lazy and not self._lazy_full_loaded:
            # Bootstrap fast-path.
            for d in self._documents:
                if d.kind == kind and d.name == name:
                    return d
            # Per-kind cache fast-path (already-materialized kind).
            cached = self._lazy_kind_cache.get(kind)
            if cached is not None:
                for d in cached:
                    if d.name == name:
                        return d
                # s-platform-resources-inherit (2026-05-28): NÃO retornar
                # None aqui — fall through pro kernel.get_document_sync que
                # honra `_INHERITABLE_KINDS`. Bug pré-fix: scope local
                # tinha lazy_kind_cache[LottieAsset]=[] (vazio) → mi.one
                # retornava None sem nunca tentar parent scope inheritance.
                inheritable = getattr(self._kernel, "_INHERITABLE_KINDS", frozenset())
                parent_scope = getattr(self._kernel, "_INHERIT_PARENT_SCOPE", None)
                if not (kind in inheritable and parent_scope and self.scope != parent_scope):
                    return None
            # Kernel single-doc lookup.
            if self._kernel is None:
                return None

            tenant = getattr(self, "_tenant", None)
            # F8.7 cleanup — route through kernel.get_document_sync so
            # we honor the registered main loop. The previous direct
            # ``asyncio.run`` here created a fresh loop per call; the
            # asyncpg pool is loop-bound, so reads from this fresh loop
            # raised ConnectionDoesNotExistError("connection was closed
            # in the middle of operation") on every insights ask /
            # narrative add-decision invocation. Issue was the same
            # `_run_sync_helper` already calls out — just was bypassed
            # in this path. Returns the parsed Document, but callers
            # of mi.one expect Document (with .kind/.spec) so it's a
            # drop-in replacement.
            getter = getattr(self._kernel, "get_document_sync", None)
            if getter is not None:
                return getter(self.scope, kind, name, tenant=tenant)
            # Legacy fallback (kernels without get_document_sync).
            import asyncio
            async def _g():
                return await self._kernel.get_document(
                    self.scope, kind, name, tenant=tenant,
                )
            try:
                asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    raw = ex.submit(asyncio.run, _g()).result(timeout=30)
            except RuntimeError:
                raw = asyncio.run(_g())

            if raw is None:
                return None
            _parse = getattr(self._kernel, "_parse_doc", None)
            if _parse is None:
                return None
            return _parse(raw)

        # Eager mode: walk self._documents.
        # NB: inheritance fallback (s-platform-resources-inherit, 2026-05-28)
        # NÃO acontece aqui — `mi.one` é sync e chamar `get_document_sync`
        # do dentro de um event loop quebra. Async callers DEVEM usar
        # `mi.one_async`, que desce pro `kernel.get_document` + inheritance.
        # Caller sync: aceita que docs herdados sumam no eager mode.
        for d in self._documents:
            if d.kind == kind and d.name == name:
                return d
        return None

    def read_spec(self, kind: str, name: str, field: str, *, default: Any = None) -> Any:
        """Read a single field from ``document.spec``."""
        doc = self._one(kind, name)
        if doc is None:
            raise KeyError(f"{kind}/{name}: document not found in manifest")
        return doc.spec.get(field, default)

    def read_metadata(self, kind: str, name: str, field: str, *, default: Any = None) -> Any:
        """Same contract as ``read_spec`` but reads from ``document.metadata``."""
        doc = self._one(kind, name)
        if doc is None:
            raise KeyError(f"{kind}/{name}: document not found in manifest")
        return doc.metadata.get(field, default)

    def read_spec_list(self, kind: str, name: str, field: str) -> list:
        """Read a list-typed spec field, returning [] when missing or None."""
        val = self.read_spec(kind, name, field, default=None)
        if val is None:
            return []
        if not isinstance(val, list):
            raise TypeError(
                f"{kind}/{name}.spec.{field}: expected list, got {type(val).__name__}"
            )
        return val

    @cached_property
    def root(self) -> Document | None:
        """The manifest's root document (the Genome), or None when the
        scope has no doc whose KindPort is marked ``is_root``."""
        # Phase 16 — Genome is the canonical root Kind. ModuleKind
        # class is gone; legacy ``kind: Module`` docs no longer parse.
        for d in self.documents:
            kp = self._kinds.get((d.api_version, d.kind))
            if kp and kp.is_root:
                return d
        return None

    def default_agent(self) -> Document | None:
        """The agent Document the root Genome names as its default
        (``spec.default_agent`` via the root KindPort), or None when
        there is no root or no such agent."""
        root = self.root
        if not root:
            return None
        kp = self._kinds.get((root.api_version, root.kind))
        if not kp:
            return None
        agent_name = kp.get_default_agent_name(root)
        if not agent_name:
            return None
        return self._find_agent(agent_name)

    # -- Composition validation (delegates to CompositionEngine) ---------------

    @cached_property
    def composition_result(self) -> CompositionResult:
        """Validate cross-kind references. Returns resolved + missing + warnings."""
        return self.composition.validate()

    # -- Navigation (delegates to Navigator + CompositionEngine) ---------------

    def list_kinds(self) -> list[str]:
        """Sorted list of the distinct Kind names present in this
        manifest's loaded documents."""
        return sorted(set(d.kind for d in self.documents))

    def render_doc(self, kind: str, name: str) -> list[PreviewBlock]:
        """Polymorphic per-kind preview."""
        return self.nav.render_doc(kind, name)

    def consumers_of(self, kind: str, name: str) -> list[dict[str, str]]:
        """Walk the manifest and return every doc that references this one."""
        return self.composition.consumers_of(kind, name)

    def _is_root_doc(self, doc: Any) -> bool:
        """True when the doc's KindPort is marked as the manifest root."""
        kp = self._kinds.get((doc.api_version, doc.kind))
        return bool(getattr(kp, "is_root", False))

    def is_root_doc(self, doc: Any) -> bool:
        """Public alias for _is_root_doc — part of the blessed public surface."""
        return self._is_root_doc(doc)

    def kind_for(self, kind: str) -> Any | None:
        """Return the KindPort registered for ``kind`` (by kind name), or None."""
        for (_api, kn), kp in self._kinds.items():
            if kn == kind:
                return kp
        return None

    def kind_for_alias(self, alias: str) -> Any | None:
        """Return the KindPort whose ``alias`` matches, or None."""
        for kp in self._kinds.values():
            if getattr(kp, "alias", None) == alias:
                return kp
        return None

    def iter_doc_deps(self, doc: Any) -> list[dict[str, Any]]:
        """Iterate a document's declared dep_filters dynamically."""
        return self.composition.iter_doc_deps(doc)

    def get(self, kind: str | None = None) -> list[dict[str, Any]]:
        """List documents as light ``{kind, name, apiVersion}`` dicts —
        all of them, or only those of ``kind``. For full Documents use
        ``documents`` / ``all()`` instead."""
        docs = self.documents if kind is None else self._all(kind)
        return [
            {"kind": d.kind, "name": d.name, "apiVersion": d.api_version}
            for d in docs
        ]

    def describe(self, kind: str, name: str) -> str:
        """Human-readable description of one document (metadata, spec
        highlights, relationships) — delegates to the Navigator."""
        return self.nav.describe(kind, name)

    def summary(self) -> str:
        """Plain-text overview of the manifest (scope + the documents
        loaded, grouped by kind) — delegates to the Navigator."""
        return self.nav.summary()

    def inventory(self) -> dict[str, Any]:
        """Structured inventory of everything loaded in this manifest."""
        return self.nav.inventory()

    def dependency_tree(self) -> dict[str, Any]:
        """Build a dependency tree for every document that has dep_filters."""
        return self.composition.dependency_tree()

    # -- Ref resolution -------------------------------------------------------

    def ref(self, value: str) -> str:
        """Resolve a file reference via source, or return value as-is.

        Sync entry-point. Use this from CLI / tests / sync workers
        whose top-level entry is ``asyncio.run``. Async callers MUST
        use :py:meth:`ref_async` — running this from inside an event
        loop with a postgres source orphans the asyncpg pool.
        """
        if not value:
            return ""
        if len(value) > 255 or "\n" in value:
            return value
        if self._source and ("/" in value or value.endswith((".md", ".txt", ".yaml"))):
            from dna.kernel import _run_sync_helper
            kernel_loop = getattr(self._kernel, "_main_loop", None)
            resolved = _run_sync_helper(
                self._source.resolve_ref(self.scope, value),
                loop=kernel_loop,
            )
            if resolved:
                return resolved
        return value

    async def ref_async(self, value: str) -> str:
        """Async variant of :py:meth:`ref`.

        Use from inside the harness event loop (lifespan, request
        handlers, async middleware). Awaits ``source.resolve_ref``
        directly on the caller's loop, which is the same loop that
        owns the asyncpg pool — no cross-loop dispatch needed.
        """
        if not value:
            return ""
        if len(value) > 255 or "\n" in value:
            return value
        if self._source and ("/" in value or value.endswith((".md", ".txt", ".yaml"))):
            resolved = await self._source.resolve_ref(self.scope, value)
            if resolved:
                return resolved
        return value

    # -- Prompt (delegates to PromptBuilder) -----------------------------------

    def build_prompt(
        self,
        agent: str | None = None,
        context: dict[str, Any] | None = None,
        enabled_skills: list[str] | None = None,
        enabled_guardrails: list[str] | None = None,
        enabled_slots: dict[str, list[str]] | None = None,
    ) -> str:
        """Build system prompt via template cascade.

        Sync — uses ``_run_sync_helper`` to await source ``ref()``
        coroutines. Callers inside an async event loop must use
        ``build_prompt_async`` to avoid the "called from inside a
        running loop" guard.
        """
        return self.prompt.build(
            agent=agent,
            context=context,
            enabled_skills=enabled_skills,
            enabled_guardrails=enabled_guardrails,
            enabled_slots=enabled_slots,
        )

    async def build_prompt_async(
        self,
        agent: str | None = None,
        context: dict[str, Any] | None = None,
        enabled_skills: list[str] | None = None,
        enabled_guardrails: list[str] | None = None,
        enabled_slots: dict[str, list[str]] | None = None,
    ) -> str:
        """Async variant of :py:meth:`build_prompt`. Use from
        inside an async caller (test, middleware, etc.) so the
        ``ref_async`` path keeps the source pool's loop binding
        intact."""
        return await self.prompt.build_async(
            agent=agent,
            context=context,
            enabled_skills=enabled_skills,
            enabled_guardrails=enabled_guardrails,
            enabled_slots=enabled_slots,
        )

    def explain_prompt(
        self,
        agent: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        enabled_skills: list[str] | None = None,
        enabled_guardrails: list[str] | None = None,
        enabled_slots: dict[str, list[str]] | None = None,
        tenant: str | None = None,
    ) -> "PromptExplanation":
        """Compose *agent* AND return per-section provenance.

        The ``prompt`` field is byte-identical to :py:meth:`build_prompt`;
        ``sections`` attributes each composed section (instruction, soul,
        skills, guardrails) to its source artifact, hash, version, and
        layer/overlay origin. Sync — see :py:meth:`build_prompt`.
        """
        return self.prompt.explain(
            agent=agent,
            context=context,
            enabled_skills=enabled_skills,
            enabled_guardrails=enabled_guardrails,
            enabled_slots=enabled_slots,
            tenant=tenant,
        )

    async def explain_prompt_async(
        self,
        agent: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        enabled_skills: list[str] | None = None,
        enabled_guardrails: list[str] | None = None,
        enabled_slots: dict[str, list[str]] | None = None,
        tenant: str | None = None,
    ) -> "PromptExplanation":
        """Async variant of :py:meth:`explain_prompt`."""
        return await self.prompt.explain_async(
            agent=agent,
            context=context,
            enabled_skills=enabled_skills,
            enabled_guardrails=enabled_guardrails,
            enabled_slots=enabled_slots,
            tenant=tenant,
        )

    def _build_context(
        self,
        agent_doc: Document,
        extra: dict[str, Any] | None,
        enabled_slots: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """Compatibility shim — delegates to PromptBuilder._build_context()."""
        return self.prompt._build_context(agent_doc, extra, enabled_slots)

    def find_agent(self, name: str) -> Document | None:
        """Find the best prompt-target document matching *name*.

        Considers prompt_target_priority when multiple kinds match.
        Public API — use this instead of _find_agent().
        """
        return self._find_agent(name)

    def _find_agent(self, name: str) -> Document | None:
        """Internal — kept for backwards compat."""
        best: Document | None = None
        best_priority = -1
        for d in self.documents:
            kp = self._kinds.get((d.api_version, d.kind))
            if kp and kp.is_prompt_target and d.name == name:
                priority = getattr(kp, "prompt_target_priority", 0)
                if priority > best_priority:
                    best = d
                    best_priority = priority
        return best

    # -- Layers ---------------------------------------------------------------

    def resolve(self, layers: dict[str, str] | None = None) -> ManifestInstance:
        """Apply layer overlays (sync). Delegates to Kernel.resolve_layers().

        Memoizes per-layers so repeated ``mi.resolve({"tenant": X})`` calls
        from request handlers reuse the same merged instance instead of
        re-reading every doc from disk. Cache lives on the base ``mi``;
        ``MIHolder.reload()`` swaps the base instance, which discards
        this cache transparently.

        From inside an event loop, prefer `await mi.resolve_async(layers)`
        — the sync path falls back to a ThreadPool/asyncio.run dance
        that orphans pool-based source adapters.
        """
        if not layers:
            return self
        if self._kernel:
            cache = getattr(self, "_resolved_cache", None)
            if cache is None:
                cache = self._resolved_cache = {}
            key = frozenset(layers.items())
            if key not in cache:
                cache[key] = self._kernel.resolve_layers(self, layers)
            return cache[key]
        return self

    async def resolve_async(
        self, layers: dict[str, str] | None = None,
    ) -> ManifestInstance:
        """Async variant of `resolve`. Use from inside an event loop
        (request handlers, lifespan, EventBus consumer) so the source
        pool stays tied to the caller's loop.
        """
        if not layers:
            return self
        if self._kernel:
            cache = getattr(self, "_resolved_cache", None)
            if cache is None:
                cache = self._resolved_cache = {}
            key = frozenset(layers.items())
            if key not in cache:
                cache[key] = await self._kernel.resolve_layers_async(self, layers)
            return cache[key]
        return self

    # -- Lock (delegates to LockManager) ---------------------------------------

    # -- Declarative Hooks ----------------------------------------------------

    def apply_hooks(self) -> None:
        """Auto-register Hook documents on the kernel's HookRegistry."""
        if not self._kernel or not hasattr(self._kernel, "hooks"):
            return

        hooks = self._all("Hook")
        for doc in hooks:
            spec = doc.spec
            target = spec.get("target", "")
            hook_type = spec.get("type", "middleware")
            action = spec.get("action", "inject_fields")

            if hook_type == "middleware" and target:
                if action == "inject_fields":
                    fields = spec.get("fields", {})
                    if fields:
                        def make_injector(f):
                            def injector(ctx):
                                context = ctx.data.get("context", {})
                                context.update(f)
                                ctx.data["context"] = context
                                return ctx
                            return injector
                        self._kernel.hooks.use(target, make_injector(dict(fields)))
                elif action == "script":
                    body = spec.get("body", "").strip()
                    if body:
                        try:
                            ns: dict[str, Any] = {}
                            exec(f"_hook_fn = {body}", ns)  # noqa: S102
                            fn = ns.get("_hook_fn")
                            if callable(fn):
                                self._kernel.hooks.use(target, fn)
                        except Exception as e:
                            import warnings
                            warnings.warn(f"Hook {doc.name}: script compilation failed: {e}")

            elif hook_type == "event" and target:
                if action == "log":
                    def make_logger(hook_name):
                        def logger(ctx):
                            import logging
                            logging.getLogger("dna.hooks").info(
                                "[Hook:%s] %s agent=%s scope=%s",
                                hook_name, target, ctx.agent, ctx.scope,
                            )
                        return logger
                    self._kernel.hooks.on(target, make_logger(doc.name))
                elif action == "script":
                    body = spec.get("body", "").strip()
                    if body:
                        try:
                            ns_ev: dict[str, Any] = {}
                            exec(f"_hook_fn = {body}", ns_ev)  # noqa: S102
                            fn_ev = ns_ev.get("_hook_fn")
                            if callable(fn_ev):
                                self._kernel.hooks.on(target, fn_ev)
                        except Exception as e:
                            import warnings
                            warnings.warn(f"Hook {doc.name}: script compilation failed: {e}")

        # -- SafetyPolicy input enforcement -----------------------------------
        policies = self._all("SafetyPolicy")
        for doc in policies:
            spec = doc.spec
            scope = spec.get("scope", "both")
            action = spec.get("action", "mask")
            rules = spec.get("rules", [])

            if scope in ("input", "both") and isinstance(rules, list) and rules:
                from dna.safety.scanner import ScannerPipeline

                pipeline = ScannerPipeline(rules)

                def make_safety_middleware(p: Any, a: str):  # noqa: E501
                    def middleware(ctx: Any) -> Any:
                        context = ctx.data.get("context", {})
                        for key, val in list(context.items()):
                            if isinstance(val, str):
                                try:
                                    context[key] = p.apply(val, a)
                                except Exception as e:  # noqa: BLE001
                                    # fail-soft (fail-OPEN by design): a
                                    # scanner bug must not take prompt build
                                    # down — but the value passes UNMASKED,
                                    # so the miss logs loud, never silent.
                                    logger.warning(
                                        "SafetyPolicy scanner failed for "
                                        "context[%r] — value passed "
                                        "unmasked: %s", key, e,
                                    )
                        ctx.data["context"] = context
                        return ctx
                    return middleware

                self._kernel.hooks.use(
                    "pre_build_prompt", make_safety_middleware(pipeline, action)
                )

    # -- Lock (delegates to LockManager) ---------------------------------------

    def generate_lock(self) -> "Lockfile":
        """Generate lockfile with SHA256 per document."""
        return self.lock.generate()
