"""QueryEngine — the kernel's read surface (query push-down + get_document +
the two sync wrappers), extracted from the Kernel god-object
(kernel-decompose-continue).

Behavior-preserving: ``query`` (Marco-A push-down with tenant binding, origin
filter, and scope-inheritance chain), ``get_document`` (cached read-one with V1
parent fallback), ``query_list_sync`` / ``get_document_sync`` (sync wrappers that
parse ``Document`` objects) move verbatim; the kernel keeps all four as thin
delegators (they're heavily used — Studio list views, CLI, workers, agent
routes — all unchanged). A STATELESS back-ref collaborator: it reads per-kernel
state (``tenant``, ``_source``, ``_main_loop``, the granular cache, the
resolution chain) through the back-ref, so ``with_tenant`` MUST rebind it to the
shallow copy (it reads ``k.tenant`` for the tenant auto-stamp).
"""
from __future__ import annotations

import logging

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import QueryEngineHost
    from dna.kernel.document import Document

# F2 D2 — shape returned by ``count()``:
# ``{"total": int, "groups": list[{"key": Any, "count": int}] | None}``.
# Groups ordered by count DESC, key ASC with None last.
CountResult = dict



logger = logging.getLogger(__name__)
class QueryEngine:
    """The kernel's read surface. One per kernel; back-ref to it."""

    def __init__(self, kernel: "QueryEngineHost") -> None:
        self._k = kernel

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

        Wrappeia ``source.query`` adicionando:
          - Tenant binding auto-stamp: quando ``Kernel.tenant`` é setado
            (multi-tenant binding via ``Kernel(tenant=...)``) e ``tenant``
            kwarg é None, usa o tenant binding. ``tenant`` explícito
            overrides (Stripe Connect pattern, igual ao write_document).
          - Assertion de source registrado.
          - Cross-scope ``scopes=`` (F2.4): itera os scopes com queries
            LOCAIS (``origin="local"``, sem chain de herança/catalog) e
            CONCATENA sem dedup — records de scopes distintos são docs
            distintos. Mutuamente exclusivo com um ``scope`` posicional
            divergente: ``scopes`` ganha (o posicional é ignorado).
            ``limit``/``offset`` aplicam POR scope (cada query local
            recebe os kwargs intactos).

        Não usa o L2 cache (granular doc/list cache) porque cada (filter,
        projection, order, limit, offset) tem combinação única — cache
        hit rate seria baixíssimo e o custo de memória alto. Single
        SELECT no Postgres em <10ms já é o caminho rápido; HTTP layer
        adiciona seu próprio cache se precisar.

        Args:
            scope, kind, filter, projection, limit, offset, order_by, tenant:
                idem ``SourcePort.query``. Veja docstring lá pra shape
                de filter/projection/order_by.

        Returns:
            AsyncIterator[dict] — rows do source.query, projetadas se
            ``projection`` setado.

        Examples:
            # Studio list view: 50 in-progress Stories
            rows = [r async for r in kernel.query(
                "dna-development", "Story",
                filter={"status": "in-progress"},
                projection=["name", "spec.title", "spec.feature"],
                order_by=["-spec.updated_at"],
                limit=50,
            )]

            # Tenant-aware: union base + overlay
            rows = [r async for r in kernel.query(
                "hr-screening", "Agent", tenant="acme",
            )]
        """
        k = self._k
        assert k._source, "No source registered. Call kernel.source(src) first."
        # s-sourceport-contract-cleanup: consult the DECLARED capabilities.
        # Sources with native query push-down get called directly (the 3
        # in-repo adapters); legacy/external sources without one are served
        # by the kernel-side load_all fallback — which gets the kernel's
        # LIVE readers explicitly (this replaces the old Protocol-default's
        # ``getattr(self, "_kernel")`` reach-back).
        from dna.kernel.capabilities import source_capabilities
        from dna.kernel.query_fallback import query_via_load_all
        _pushdown = source_capabilities(k._source).query_pushdown

        def _source_query(sc: str, tn: str | None):
            if _pushdown:
                return k._source.query(
                    sc, kind,
                    filter=filter, projection=projection,
                    limit=limit, offset=offset, order_by=order_by,
                    tenant=tn,
                )
            return query_via_load_all(
                k._source, sc, kind,
                filter=filter, projection=projection,
                limit=limit, offset=offset, order_by=order_by,
                tenant=tn, readers=list(k._readers),
            )
        # F2.4 cross-scope: local-only per-scope queries, concat no dedup.
        # Recursion rebinds tenant per call (passes the raw kwarg through).
        if scopes is not None:
            for sc in scopes:
                async for row in self.query(
                    sc, kind,
                    filter=filter, projection=projection,
                    limit=limit, offset=offset, order_by=order_by,
                    tenant=tenant, origin="local",
                ):
                    yield row
            return
        # Tenant binding: kwarg > Kernel.tenant > None.
        effective_tenant = tenant if tenant is not None else k.tenant
        # Phase 17 (s-comp-f5-query-origin-filter, 2026-05-28):
        # `origin` filter — "local" yields only docs from the requested
        # scope; "inherited" only parent docs; "all" union (default,
        # back-compat). When inheritance is disabled by composition_rules,
        # only local is emitted regardless of origin.
        origin_norm = (origin or "all").lower()
        # Compute chain via Phase 17 resolver (transitive) — fallback to
        # V1 _INHERIT_PARENT_SCOPE when no Genome declares parent_scope.
        if kind in k._INHERITABLE_KINDS and scope != k._INHERIT_PARENT_SCOPE:
            chain = await k._compute_resolution_chain(scope, None)
            # chain = [(scope, None), (parent, None), ...]
            parent_scopes = [s for s, _ in chain if s != scope]
        else:
            parent_scopes = []
        # Phase 3b ch2 (i-112): one SHARED dedup set across all three passes
        # (local → catalog → parent) so precedence is Local > Catalog > Base.
        # The first contributor of a name wins; later passes skip it. The local
        # pass ALWAYS populates it (even when not emitting, e.g. origin=inherited
        # /installed need local names to dedup the later passes).
        seen_names: set[str] = set()
        # Local pass — emit when origin in {all, local}. Always collect names.
        local_emits = origin_norm in {"all", "local"}
        async for row in _source_query(scope, effective_tenant):
            meta = row.get("metadata") if isinstance(row, dict) else None
            row_name = (
                (meta.get("name") if isinstance(meta, dict) else None)
                or (row.get("name") if isinstance(row, dict) else None)
            )
            if row_name:
                seen_names.add(row_name)
            if local_emits:
                yield row
        # Catalog pass (Phase 3b ch2) — the installed/Catalog tier, BETWEEN
        # local and parent so it wins over Base but loses to Local. Emit when
        # origin in {all, installed}. Guarded on inheritable Kinds (same gate as
        # the parent pass) — non-inheritable Kinds never inherit OR catalog-merge.
        if (
            origin_norm in {"all", "installed"}
            and kind in k._INHERITABLE_KINDS
            and scope != k._INHERIT_PARENT_SCOPE
        ):
            try:
                catalog_scopes = await k._catalog_scopes(
                    effective_tenant or None, exclude={scope},
                )
            except Exception as e:  # noqa: BLE001
                # fail-soft: never crash a query — _catalog_scopes warns on
                # compute failure; this catches anything past it (debug: query
                # hot path).
                logger.debug(
                    "query: catalog pass skipped for scope=%r kind=%r: %s",
                    scope, kind, e,
                )
                catalog_scopes = []
            for cat_scope, cat_tenant in catalog_scopes:
                # Per-scope fail-soft, exactly like the parent pass.
                try:
                    cat_rows = [
                        row async for row in _source_query(cat_scope, cat_tenant)
                    ]
                except Exception as e:  # noqa: BLE001
                    # fail-soft: per-catalog-scope, exactly like the parent
                    # pass — one broken package scope drops out (logged).
                    logger.debug(
                        "query: catalog scope %r failed for kind %r: %s",
                        cat_scope, kind, e,
                    )
                    continue
                for row in cat_rows:
                    meta = row.get("metadata") if isinstance(row, dict) else None
                    row_name = (
                        (meta.get("name") if isinstance(meta, dict) else None)
                        or (row.get("name") if isinstance(row, dict) else None)
                    )
                    if row_name and row_name in seen_names:
                        continue  # Local already claimed it → Local wins.
                    if row_name:
                        seen_names.add(row_name)
                    yield row
        # Parent pass(es) — emit when origin in {all, inherited} and chain has
        # parents. Reads the SHARED seen_names (now holding local + catalog
        # names) → Base loses to both.
        if origin_norm in {"all", "inherited"}:
            for parent in parent_scopes:
                # Inheritance is fail-soft: a parent scope that doesn't exist on
                # the source (e.g. `_lib` absent in a minimal deploy/test)
                # contributes NO inherited docs rather than raising. With the
                # denylist default (s-platform-inherit-by-default) far more Kinds
                # trigger this parent pass, so it must never crash on a missing
                # parent. Materialize guarded, then yield (don't wrap the yield).
                try:
                    parent_rows = [
                        row async for row in _source_query(parent, effective_tenant)
                    ]
                except Exception as e:  # noqa: BLE001
                    # fail-soft: a missing/broken parent contributes NO
                    # inherited docs rather than raising (see comment above) —
                    # logged at debug (hot path under inherit-by-default).
                    logger.debug(
                        "query: parent scope %r failed for kind %r: %s",
                        parent, kind, e,
                    )
                    continue
                for row in parent_rows:
                    meta = row.get("metadata") if isinstance(row, dict) else None
                    row_name = (
                        (meta.get("name") if isinstance(meta, dict) else None)
                        or (row.get("name") if isinstance(row, dict) else None)
                    )
                    if row_name and row_name in seen_names:
                        continue
                    if row_name:
                        seen_names.add(row_name)
                    yield row

    async def count(
        self, scope: str, kind: str, *,
        filter: dict | None = None,
        group_by: str | None = None,
        tenant: str | None = None,
        scopes: list[str] | None = None,
    ) -> CountResult:
        """F2 D2 — kernel-level aggregation count, push-down delegado a
        ``source.count`` (PG nativo; FS/SQLite via protocol-default).

        Tenant binding igual ao ``query`` (kwarg > ``Kernel.tenant`` >
        None). SEM ``origin``/chain de propósito: records são por-scope —
        herança/origin NÃO se aplica a count (decisão da spec D5: views
        derivadas que precisem de herança fazem código por cima de
        ``kernel.query``).

        Cross-scope ``scopes=`` (F2.4): 1 ``source.count`` por scope;
        ``total`` SOMADO e ``groups`` MERGEADOS por key (re-ordenados por
        count DESC, key ASC com None por último — mesmo desempate do
        protocol-default). ``scopes`` ganha de um ``scope`` posicional
        divergente.

        Returns:
            ``CountResult`` — ``{"total": int, "groups": [...] | None}``.
        """
        k = self._k
        assert k._source, "No source registered. Call kernel.source(src) first."
        from dna.kernel.capabilities import source_capabilities
        from dna.kernel.query_fallback import count_via_load_all
        _pushdown = source_capabilities(k._source).query_pushdown
        effective_tenant = tenant if tenant is not None else k.tenant
        target_scopes = list(scopes) if scopes is not None else [scope]
        total = 0
        merged: dict[Any, int] = {}
        for sc in target_scopes:
            if _pushdown:
                res = await k._source.count(
                    sc, kind,
                    filter=filter, group_by=group_by, tenant=effective_tenant,
                )
            else:
                res = await count_via_load_all(
                    k._source, sc, kind,
                    filter=filter, group_by=group_by, tenant=effective_tenant,
                    readers=list(k._readers),
                )
            total += int(res.get("total") or 0)
            for g in (res.get("groups") or ()):
                key = g.get("key")
                merged[key] = merged.get(key, 0) + int(g.get("count") or 0)
        groups = None
        if group_by is not None:
            groups = [
                {"key": key, "count": cnt}
                for key, cnt in sorted(
                    merged.items(),
                    key=lambda kv: (-kv[1], kv[0] is None, str(kv[0])),
                )
            ]
        return {"total": total, "groups": groups}

    async def get_document(
        self, scope: str, kind: str, name: str, *,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """Carrega UM doc por (scope, kind, name). Retorna raw dict ou None.

        Custo ~5ms PG / ~3ms SQLite / ~20ms FS. LRU cache bounded em
        2000 entries com TTL 60s. Cache invalidado per-doc pelo
        kernel.write_document.

        Scope-level inheritance (Story s-platform-agent-fallback,
        2026-05-28): kinds em ``_INHERITABLE_KINDS`` herdam de
        ``_INHERIT_PARENT_SCOPE`` quando não existem localmente. Override
        local ganha sempre. Custo do fallback: 1 cache lookup adicional
        no miss (mesma TTL).
        """
        k = self._k
        assert k._source, "No source registered."
        key = (scope, kind, name, tenant or "")
        result = await k._granular_doc_cached(key)
        if result is not None:
            return result
        if (
            kind in k._INHERITABLE_KINDS
            and scope != k._INHERIT_PARENT_SCOPE
        ):
            # Walk the DECLARED parent chain (``Genome.spec.parent_scope``,
            # transitively) — the SAME ``compute_resolution_chain`` the
            # query/resolve paths use (i-058). The V1 fallback keeps the
            # chain ending at ``_INHERIT_PARENT_SCOPE``, so a scope with no
            # declared parent probes exactly the single ``_lib`` hop it
            # always did. First hit in chain order wins (local already
            # missed above; a nearer parent beats a farther one).
            try:
                chain = await k._compute_resolution_chain(scope, None)
            except Exception as e:  # noqa: BLE001
                # fail-soft: an unreadable chain degrades to the V1
                # single-hop parent — logged at debug (hot path).
                logger.debug(
                    "get_document: resolution chain failed for %r "
                    "(falling back to %r): %s",
                    scope, k._INHERIT_PARENT_SCOPE, e,
                )
                chain = [(scope, None), (k._INHERIT_PARENT_SCOPE, None)]
            for parent, _t in chain:
                if parent == scope:
                    continue
                fallback_key = (parent, kind, name, tenant or "")
                # Fail-soft: a missing parent scope (`_lib` absent) means no
                # inherited doc, not an error (s-platform-inherit-by-default —
                # the denylist default routes many more Kinds through here).
                try:
                    hit = await k._granular_doc_cached(fallback_key)
                except Exception as e:  # noqa: BLE001
                    # fail-soft: missing parent scope → no inherited doc, not
                    # an error (see comment above) — logged at debug (hot path).
                    logger.debug(
                        "get_document: parent fallback failed for %r: %s",
                        fallback_key, e,
                    )
                    continue
                if hit is not None:
                    return hit
            return None
        return None

    def query_list_sync(
        self, scope: str, kind: str, *,
        filter: dict | None = None,
        tenant: str | None = None,
    ) -> list["Document"]:
        """Sync wrapper around ``self.query(scope, kind)`` returning a list
        of parsed ``Document`` objects (drop-in for ``mi.all(kind)``).

        f-mi-class-extinction (s-tools-mi-kill, 2026-05-14): for sync
        callers (LangGraph tool executors, CLI, worker bootstrap) that
        can't await. Uses ``_run_sync_helper`` so the asyncpg pool's
        event-loop binding is honored (via ``self._main_loop`` when
        registered) or a fresh loop is spun up otherwise.

        Returns parsed ``Document`` objects (with ``.kind``, ``.name``,
        ``.spec``, ``.metadata``) for back-compat with code that
        iterates the result like ``for d in mi.all(...): d.spec``.

        Prefer ``[d async for d in self.query(...)]`` from async
        contexts — those yield raw dicts, which is cheaper and what
        ``kernel.query`` natively returns.
        """
        from dna.kernel import _run_sync_helper
        from dna.kernel.document import Document
        k = self._k

        async def _collect() -> list[Document]:
            out: list[Document] = []
            async for raw in self.query(
                scope, kind, filter=filter, tenant=tenant,
            ):
                doc = k._parse_doc(raw, origin="local")
                if doc is not None:
                    out.append(doc)
            return out
        coro = _collect()
        try:
            return _run_sync_helper(coro, loop=k._main_loop)
        except BaseException:
            coro.close()
            raise

    def get_document_sync(
        self, scope: str, kind: str, name: str, *,
        tenant: str | None = None,
    ) -> "Document | None":
        """Sync wrapper around ``self.get_document`` returning a parsed
        ``Document`` (drop-in for ``mi.one(kind, name)``).
        """
        from dna.kernel import _run_sync_helper
        from dna.kernel.document import Document
        k = self._k

        async def _g() -> Document | None:
            raw = await self.get_document(scope, kind, name, tenant=tenant)
            if raw is None:
                return None
            return k._parse_doc(raw, origin="local")
        coro = _g()
        try:
            return _run_sync_helper(coro, loop=k._main_loop)
        except BaseException:
            coro.close()
            raise
