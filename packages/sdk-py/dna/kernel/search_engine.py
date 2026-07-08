"""SearchEngine — the record ``search`` facade + lexical fallback extracted from
the Kernel god-object (``s-kernel-decomp-f5-satellites``).

Two-planes F2 (D2): a registered ``RecordSearchProvider`` gives real semantic
search (pgvector/RRF, ``degraded=False``); with no provider — or on any provider
error — the engine degrades to an HONEST lexical token-match scan over
``query()`` (``degraded=True``), never similarity. Search is a READ: it degrades,
it never raises.

Behavior-preserving extraction: ``search`` + ``_lexical_search`` move here
verbatim; the kernel keeps both as thin delegators (the public ``search`` is
called from CLI/Studio/agent routes). The provider + its failure-warning damper
(``_search_provider`` / ``_search_provider_warned``) stay KERNEL state — the
kernel keeps ``record_search_provider`` as the registration entry point, and the
engine reads/writes the damper through the host — so the exact ``with_tenant``
sharing semantics are preserved (``_search_provider`` shared by reference,
``_search_provider_warned`` copied by value per shallow copy). A STATELESS
back-ref collaborator that reads ``k.tenant`` (effective-tenant auto-stamp), so
``with_tenant`` rebinds it to the copy.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import SearchEngineHost

logger = logging.getLogger(__name__)


class SearchEngine:
    """The kernel's record-search surface. One per kernel; back-ref to it."""

    def __init__(self, kernel: "SearchEngineHost") -> None:
        self._k = kernel

    async def search(
        self, scope: str, query_text: str, *,
        kind: str | None = None, k: int = 10, tenant: str | None = None,
    ) -> dict[str, Any]:
        """Public record search (F2 D2). Provider registered → semantic
        (pgvector/RRF, degraded=False). No provider OR provider error →
        lexical token-match fallback over query() (degraded=True; requires
        ``kind`` — without it returns empty degraded). Tenant binding igual
        ao query(): kwarg > ``Kernel.tenant``."""
        host = self._k
        effective_tenant = tenant if tenant is not None else (host.tenant or "")
        prov = host._search_provider
        if prov is not None:
            try:
                hits = await prov.search(
                    scope=scope, query_text=query_text, kind=kind,
                    k=k, tenant=effective_tenant or "",
                )
                host._search_provider_warned = False  # episode over
                return {"hits": hits, "degraded": False}
            except Exception:  # noqa: BLE001 — search é leitura; degrada, nunca quebra
                # Damped: full traceback ONCE per failure episode (a broken
                # provider would otherwise spam a warning per request);
                # repeats at debug until a successful call resets.
                if not host._search_provider_warned:
                    host._search_provider_warned = True
                    logger.warning(
                        "[kernel] search provider failed; lexical fallback "
                        "(further failures logged at debug until recovery)",
                        exc_info=True,
                    )
                else:
                    logger.debug(
                        "[kernel] search provider still failing; lexical fallback",
                        exc_info=True,
                    )
        return {
            "hits": await self._lexical_search(
                scope, query_text, kind=kind, k=k,
                tenant=effective_tenant or None,
            ),
            "degraded": True,
        }

    async def _lexical_search(
        self, scope: str, query_text: str, *,
        kind: str | None = None, k: int = 10, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Degraded fallback for ``search()`` — honest DEV lexical scan,
        NOT similarity (two-planes F2).

        Matches by token-set over the STRING VALUES of each doc's spec
        (recursive walk; never substring over serialized JSON —
        ``json.dumps`` Py and ``JSON.stringify`` TS diverge in separators
        and would break parity). Requires ``kind`` (records are scanned
        per-kind); without it there is nothing safe to scan → empty.
        Score = query tokens present ÷ total query tokens.
        """
        if not kind:
            return []
        q_tokens = query_text.lower().split()
        if not q_tokens:
            return []

        def _spec_tokens(node: Any, out: set[str]) -> None:
            if isinstance(node, str):
                out.update(node.lower().split())
            elif isinstance(node, dict):
                for v in node.values():
                    _spec_tokens(v, out)
            elif isinstance(node, (list, tuple)):
                for v in node:
                    _spec_tokens(v, out)

        hits: list[dict[str, Any]] = []
        async for row in self._k.query(scope, kind, tenant=tenant, limit=500):
            tokens: set[str] = set()
            _spec_tokens(row.get("spec") or {}, tokens)
            score = sum(1 for t in q_tokens if t in tokens) / len(q_tokens)
            if score > 0:
                name = (row.get("metadata") or {}).get("name") or row.get("name") or ""
                hits.append(
                    {"scope": scope, "kind": kind, "name": name, "score": score},
                )
        hits.sort(key=lambda h: -h["score"])
        return hits[:k]
