"""Query/count fallback over ``load_all`` — the kernel-side helpers.

s-sourceport-contract-cleanup: these bodies used to live INSIDE the
``SourcePort`` Protocol as ~100 lines of concrete "default" implementation,
including a ``getattr(self, "_kernel", None)`` reach-back through which a
port grabbed the mediator's live readers. The Protocol now declares
signatures only; the behavior lives here:

- :func:`query_via_load_all` — the in-memory query core (load_all +
  filter/order/page/project in Python). ``readers`` is an EXPLICIT
  parameter: the caller decides which readers apply (the kernel passes
  its live ``_readers``; the FS adapter passes its kernel-attached view).
- :func:`count_via_query` — aggregation riding ``source.query`` (native
  push-down when the adapter has one). Used by the FS adapters and as the
  parity oracle for the SQL adapter's native count.
- :func:`count_via_load_all` — aggregation for sources with NO native
  ``query`` at all (the kernel's legacy-source path).

Who calls what:
  - ``QueryEngine`` consults ``source_capabilities(src).query_pushdown``;
    True → ``src.query``/``src.count``, False → these helpers.
  - Adapters whose query IS the in-memory core (FilesystemSource) call
    :func:`query_via_load_all` directly with their own readers.

The pure per-row helpers (``_match_filter``/``_project_doc``/
``_apply_order_by``/``_resolve_field_path``) stay in ``protocols.py`` —
they are shared vocabulary for adapters' native push-down paths too.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from dna.kernel.protocols import (
    QueryFilter,
    QueryOrder,
    QueryProjection,
    _apply_order_by,
    _match_filter,
    _project_doc,
    _resolve_field_path,
)


async def query_via_load_all(
    source: Any, scope: str, kind: str, *,
    filter: QueryFilter | None = None,
    projection: QueryProjection | None = None,
    limit: int | None = None,
    offset: int | None = None,
    order_by: QueryOrder | None = None,
    tenant: str | None = None,
    readers: list | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """In-memory query core: ``source.load_all`` + Python filter /
    order / page / project. Correct but O(scope_size) per call —
    adapters with native push-down don't ride this.

    ``readers`` must be provided by the caller when bundle-format kinds
    (Agent, Skill, Soul, …) should be visible — without readers,
    ``load_all`` misses every bundle on FS-backed sources. (This
    replaces the old Protocol-default's ``getattr(self, "_kernel")``
    reach-back for the kernel's live readers.)
    """
    _readers = list(readers or [])
    if tenant is None:
        raw_docs = await source.load_all(scope, readers=_readers)
    else:
        base = await source.load_all(scope, readers=_readers)
        # Pass readers so bundle-format kinds in the tenant overlay dir
        # are detected — query(tenant=X) must not silently drop bundles
        # stored under tenants/<X>/scopes/<scope>/.
        overlay = await source.load_layer(
            scope, "tenant", tenant, readers=_readers,
        )
        # Overlay shadows base on (kind, metadata.name).
        shadow_keys = {
            (d.get("kind"), (d.get("metadata") or {}).get("name"))
            for d in overlay
        }
        merged = [
            d for d in base
            if (d.get("kind"), (d.get("metadata") or {}).get("name")) not in shadow_keys
        ]
        merged.extend(overlay)
        raw_docs = merged

    # Filter by kind first (cheap).
    kind_docs = [d for d in raw_docs if d.get("kind") == kind]

    if filter:
        kind_docs = [d for d in kind_docs if _match_filter(d, filter)]

    if order_by:
        kind_docs = _apply_order_by(kind_docs, order_by)

    start = offset or 0
    end = (start + limit) if limit is not None else None
    page = kind_docs[start:end]

    for doc in page:
        if projection:
            yield _project_doc(doc, projection)
        else:
            yield doc


def _count_projection(group_by: str | None) -> list[str]:
    """Trim the payload: only the group_by field (or just name) needs to
    travel. ``group_by="name"`` normalizes to ``metadata.name`` so the
    projected row keeps the metadata shape that
    ``_resolve_field_path(row, "name")`` resolves through (projection
    always re-adds top-level ``name`` too)."""
    return [
        "metadata.name" if group_by == "name" else group_by
    ] if group_by else ["name"]


async def _aggregate(
    rows: AsyncIterator[dict[str, Any]], group_by: str | None,
) -> dict[str, Any]:
    """Shared Counter aggregation for the two count fallbacks. Groups
    ordered by count DESC, then key ASC with None LAST — matches the PG
    ``ORDER BY count DESC, key ASC`` (NULLS LAST) and the spirit of
    i-121 (None never first)."""
    from collections import Counter
    total = 0
    counter: Counter = Counter()
    async for row in rows:
        total += 1
        if group_by is not None:
            v = _resolve_field_path(row, group_by)
            counter[v if v is None or isinstance(v, (str, int, float, bool)) else str(v)] += 1
    groups = None
    if group_by is not None:
        groups = [
            {"key": k, "count": c}
            for k, c in sorted(
                counter.items(),
                key=lambda kv: (-kv[1], kv[0] is None, str(kv[0])),
            )
        ]
    return {"total": total, "groups": groups}


async def count_via_query(
    source: Any, scope: str, kind: str, *,
    filter: QueryFilter | None = None,
    group_by: str | None = None,
    tenant: str | None = None,
) -> dict[str, Any]:
    """Aggregation riding ``source.query`` (two-planes F2, spec D2):
    total docs matching ``filter``, optionally grouped by a field_path.
    The query gets a trimmed projection so long-lived paths don't haul
    full docs. Returns ``{"total": int, "groups": [...] | None}``."""
    return await _aggregate(
        source.query(
            scope, kind, filter=filter, tenant=tenant,
            projection=_count_projection(group_by),
        ),
        group_by,
    )


async def count_via_load_all(
    source: Any, scope: str, kind: str, *,
    filter: QueryFilter | None = None,
    group_by: str | None = None,
    tenant: str | None = None,
    readers: list | None = None,
) -> dict[str, Any]:
    """Aggregation for sources with no native ``query`` at all — rides
    :func:`query_via_load_all`. The kernel's legacy-source count path."""
    return await _aggregate(
        query_via_load_all(
            source, scope, kind, filter=filter, tenant=tenant,
            projection=_count_projection(group_by), readers=readers,
        ),
        group_by,
    )
