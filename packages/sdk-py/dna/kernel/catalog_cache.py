"""CatalogCache — the Catalog-tier scope set + its TTL cache, extracted from the
Kernel god-object (``s-kernel-decomp-f5-satellites``, Phase 3b ch1 / i-112).

The Catalog scope set for a tenant = mandatory platform packages
(``owner_tenant is None ∧ spec.mandatory``, universal, tenant=None) ∪ the
tenant's lockfile installs, deduped + sorted. It is cached per tenant with a
60s TTL backstop; the authoritative refresh is the explicit invalidation on
Genome writes + the install path.

CRITICAL — cache identity (spec Risk #3, pinned by
``test_kernel_catalog_tenant_characterization``): the cache DICT
(``_catalog_cache``) is OWNED by the kernel and SHARED by identity across every
``with_tenant`` shallow copy — isolation is by tenant KEY, not by a per-copy
dict. This collaborator is STATELESS: it holds NO cache, only the compute +
read-through logic, reaching the kernel-owned dict through the host. Extracting
the state here would break the shared-dict contract, so it deliberately does not.

Behavior-preserving: ``_catalog_scopes`` / ``_compute_catalog_scopes`` /
``_invalidate_catalog_cache`` move here verbatim; the kernel keeps all three as
thin delegators (write_document + routes/catalog.py call them). Fail-soft: any
scan/lockfile error → ``[]`` cached for the TTL (a Catalog glitch must never
crash a resolution). A back-ref collaborator that queries through ``k`` (whose
``query`` auto-stamps ``k.tenant``), so ``with_tenant`` rebinds it to the copy.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import CatalogCacheHost

logger = logging.getLogger(__name__)


class CatalogCache:
    """The Catalog-tier scope resolver. STATELESS — the cache dict lives on the
    kernel (shared across with_tenant copies); one collaborator, back-ref to it."""

    def __init__(self, kernel: "CatalogCacheHost") -> None:
        self._k = kernel

    async def catalog_scopes(
        self, tenant: "str | None", *, exclude: set[str] | None = None,
    ) -> list[tuple[str, "str | None"]]:
        """The ordered Catalog scope set for ``tenant`` (cached, fail-soft).

        Returns ``[(scope, target_tenant), ...]`` = mandatory platform packages
        (``owner_tenant is None ∧ spec.mandatory``, universal, tenant=None) ∪
        the tenant's lockfile installs, deduped + sorted (see
        ``resolve_catalog_scopes``). ``exclude`` drops the scope being resolved;
        the base/``_lib`` scope is always excluded.

        Cached per tenant with TTL ``_GRANULAR_DOC_TTL`` (60s) — a backstop; the
        authoritative refresh is the explicit ``invalidate`` on Genome writes
        (``write_document``) and the install path (``routes/catalog.py`` writes
        the lockfile directly). The ``exclude`` set is applied AFTER the cache
        (the cached value holds every Catalog scope; per-call exclusion is cheap
        and keeps the cache key tenant-only).

        Fail-soft: any error in the scan/lockfile read → ``[]`` (a Catalog
        glitch must never crash a resolution).
        """
        host = self._k
        base_exclude = {host._INHERIT_PARENT_SCOPE}
        call_exclude = base_exclude | (exclude or set())

        cached = host._catalog_cache.get(tenant)
        if cached is not None:
            stamped_at, scopes = cached
            if (time.monotonic() - stamped_at) < host._GRANULAR_DOC_TTL:
                return [s for s in scopes if s[0] not in call_exclude]

        try:
            scopes_all = await self._compute_catalog_scopes(tenant, base_exclude)
        except Exception as e:  # noqa: BLE001
            # fail-soft: a Catalog glitch must never crash resolution — but
            # the empty result is CACHED for the TTL (catalog packages vanish
            # from every resolve for up to 60s), so the failure logs loud.
            logger.warning(
                "_catalog_scopes: compute failed for tenant=%r (caching empty "
                "catalog for TTL): %s", tenant, e,
            )
            scopes_all = []
        host._catalog_cache[tenant] = (time.monotonic(), scopes_all)
        return [s for s in scopes_all if s[0] not in call_exclude]

    async def _compute_catalog_scopes(
        self, tenant: "str | None", base_exclude: set[str],
    ) -> list[tuple[str, "str | None"]]:
        """Uncached data-gathering for ``catalog_scopes`` — scan every Genome
        across all scopes + read the tenant lockfile, then delegate to the pure
        ``resolve_catalog_scopes``. The base scope is excluded here so the cached
        value never carries it."""
        from dna.kernel.catalog_tier import resolve_catalog_scopes
        from dna.kernel.module_lock import (
            load_lockfile, resolve_lockfile_root,
        )

        host = self._k
        # 1) every Genome doc across all scopes — mirror routes/catalog.py.
        pkgs: list[Any] = []
        scopes = await host.list_scopes_async()
        for scope in scopes:
            try:
                async for row in host.query(scope, "Genome", tenant=tenant):
                    meta = row.get("metadata") if isinstance(row, dict) else None
                    name = (
                        (meta.get("name") if isinstance(meta, dict) else None)
                        or (row.get("name") if isinstance(row, dict) else None)
                    )
                    if not name:
                        continue
                    pkgs.append(type("_P", (), {
                        "name": name,
                        "spec": dict(row.get("spec") or {})
                        if isinstance(row, dict) else {},
                    })())
            except Exception as e:  # noqa: BLE001
                # fail-soft: best-effort per scope — a broken scope drops out
                # of the catalog scan instead of failing every resolve.
                logger.debug(
                    "_compute_catalog_scopes: Genome query failed for "
                    "scope %r: %s", scope, e,
                )
                continue

        # 2) tenant lockfile installs (GenomeEntry list).
        installed: list[Any] = []
        if tenant:
            try:
                lock_root = resolve_lockfile_root(
                    host.source_metadata().get("base_dir"),
                )
                lock = load_lockfile(lock_root, tenant)
                installed = list(lock.packages)
            except Exception as e:  # noqa: BLE001
                # fail-soft: an unreadable/corrupt tenant lockfile must not
                # crash resolution — but it silently uninstalls every catalog
                # package for the tenant, so it logs loud.
                logger.warning(
                    "_compute_catalog_scopes: tenant lockfile read failed for "
                    "tenant=%r (treating as no installs): %s", tenant, e,
                )
                installed = []

        return resolve_catalog_scopes(pkgs, installed, exclude=base_exclude)

    def invalidate(self, tenant: "str | None" = None) -> None:
        """Drop the Catalog scope cache — one tenant, or ALL when ``tenant`` is
        ``None`` (a Genome write changes the mandatory set for EVERY tenant, so
        ``write_document(kind=Genome)`` calls this with no arg). The install
        path passes the specific tenant whose lockfile it just wrote. Mutates the
        kernel-owned shared dict in place (identity preserved)."""
        cache = self._k._catalog_cache
        if tenant is None:
            cache.clear()
        else:
            cache.pop(tenant, None)
