"""RecordSearchProvider conformance kit (s-record-search-sqlite).

The behavioral contract EVERY ``RecordSearchProvider`` implementation must
satisfy — the search-plane sibling of ``source_conformance_suite``. The
sqlite-vec provider runs it today; a future pgvector provider runs the SAME kit
(that's the point: one contract, many stores).

Consumption contract
--------------------

``record_search_conformance_suite(factory)`` returns a list of
:class:`RecordSearchCase`. Each ``case.run()`` builds a FRESH provider via
``factory`` (isolation between cases), indexes the canonical fixture through the
provider's OWN ``index`` surface, runs its assertions, and always awaits the
factory-provided cleanup.

``factory`` is an async callable returning ``(provider, cleanup)`` where
``cleanup`` is an async zero-arg callable or ``None``. The provider must expose
async ``index(records)`` / ``search(*, scope, query_text, kind, k, tenant)`` /
``delete(ids)``. The factory owns environment setup (temp dirs, a kernel wired
with the deterministic ``FakeEmbeddingProvider`` so the kit runs offline).

The cases assert only on the provider's PUBLIC behavior (relative ranking,
filtering, overlay shadowing, k-limit, idempotence) — never on internal storage
— so they are store-agnostic. Ranking assertions use the fake hash embedder,
under which similarity tracks token overlap: they check RELATIVE order (the doc
sharing the query's vocabulary outranks one that shares none), never absolute
scores, so they hold for a real embedder too.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

#: The scope every conformance fixture lives in.
FIXTURE_SCOPE = "search-conformance-kit"

ProviderCleanup = Callable[[], Awaitable[None]]
ProviderFactory = Callable[[], Awaitable[tuple[Any, "ProviderCleanup | None"]]]


class SearchCaseNotApplicable(unittest.SkipTest):
    """Raised when a provider doesn't support an optional surface a case needs
    (e.g. no ``delete``). pytest/unittest report it as a skip."""


def fixture_records() -> list[dict[str, Any]]:
    """Canonical fixture: three Stories with disjoint vocabularies + a Genome.

    Each doc's text is a distinct token cloud so the fake hash embedder gives a
    clean relevance signal: a query drawn from one doc's vocabulary ranks that
    doc above the others (which share no tokens with the query).
    """
    return [
        {"scope": FIXTURE_SCOPE, "kind": "Story", "name": "s-memory",
         "title": "Memory recall",
         "text": "memory similarity vector embedding recall cognitive ecphory"},
        {"scope": FIXTURE_SCOPE, "kind": "Story", "name": "s-banana",
         "title": "Banana smoothie",
         "text": "banana tropical yellow fruit smoothie breakfast"},
        {"scope": FIXTURE_SCOPE, "kind": "Story", "name": "s-fusion",
         "title": "Hybrid fusion",
         "text": "hybrid search fusion reciprocal rank bm25 dense lexical"},
        {"scope": FIXTURE_SCOPE, "kind": "Genome", "name": "g-root",
         "title": "Root genome",
         "text": "root genome package catalog identity"},
    ]


async def _index_fixture(provider: Any) -> None:
    await provider.index([dict(r) for r in fixture_records()])


def _names(hits: list[dict[str, Any]]) -> list[str]:
    return [h["name"] for h in hits]


def _require(provider: Any, method: str) -> None:
    if not callable(getattr(provider, method, None)):
        raise SearchCaseNotApplicable(
            f"{type(provider).__name__} has no {method}() — case not applicable."
        )


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------

async def _case_index_search_round_trip(provider: Any) -> None:
    await _index_fixture(provider)
    hits = await provider.search(
        scope=FIXTURE_SCOPE, query_text="memory recall cognitive", k=10,
    )
    assert hits, "search returned nothing after indexing"
    assert hits[0]["name"] == "s-memory", (
        f"the doc sharing the query vocabulary must rank first, got {_names(hits)}"
    )
    for h in hits:  # port's guaranteed hit shape
        assert {"scope", "kind", "name", "score"} <= set(h), (
            f"hit missing guaranteed keys: {h}"
        )
        assert h["scope"] == FIXTURE_SCOPE


async def _case_rrf_orders_by_relevance(provider: Any) -> None:
    await _index_fixture(provider)
    hits = await provider.search(
        scope=FIXTURE_SCOPE, query_text="banana fruit smoothie", k=10,
    )
    assert hits and hits[0]["name"] == "s-banana", (
        f"lexical+dense both point at s-banana; RRF must rank it first, "
        f"got {_names(hits)}"
    )
    ranks = {h["name"]: i for i, h in enumerate(hits)}
    if "s-memory" in ranks:
        assert ranks["s-banana"] < ranks["s-memory"], (
            "the relevant doc must outrank an unrelated one"
        )


async def _case_kind_filter(provider: Any) -> None:
    await _index_fixture(provider)
    hits = await provider.search(
        scope=FIXTURE_SCOPE, query_text="root genome catalog",
        kind="Genome", k=10,
    )
    assert hits, "kind-filtered search found nothing"
    assert all(h["kind"] == "Genome" for h in hits), (
        f"kind filter leaked other kinds: {[(h['kind'], h['name']) for h in hits]}"
    )
    assert "g-root" in _names(hits)


async def _case_k_limit(provider: Any) -> None:
    await _index_fixture(provider)
    hits = await provider.search(
        scope=FIXTURE_SCOPE, query_text="memory banana fusion genome", k=2,
    )
    assert len(hits) <= 2, f"k=2 must cap results, got {len(hits)}"


async def _case_empty_query(provider: Any) -> None:
    await _index_fixture(provider)
    for q in ("", "   "):
        hits = await provider.search(scope=FIXTURE_SCOPE, query_text=q, k=10)
        assert hits == [], f"empty query must return no hits, got {_names(hits)}"


async def _case_idempotent_index(provider: Any) -> None:
    """Re-indexing unchanged text is a no-op (hash-skip) and does not duplicate
    a doc in the results."""
    await _index_fixture(provider)
    await _index_fixture(provider)  # second pass must not duplicate
    hits = await provider.search(
        scope=FIXTURE_SCOPE, query_text="memory recall", k=10,
    )
    memory_hits = [h for h in hits if h["name"] == "s-memory"]
    assert len(memory_hits) == 1, (
        f"re-index duplicated the doc: {len(memory_hits)} copies of s-memory"
    )


async def _case_delete_removes(provider: Any) -> None:
    _require(provider, "delete")
    await _index_fixture(provider)
    await provider.delete([
        {"scope": FIXTURE_SCOPE, "kind": "Story", "name": "s-banana"},
    ])
    hits = await provider.search(
        scope=FIXTURE_SCOPE, query_text="banana fruit smoothie", k=10,
    )
    assert "s-banana" not in _names(hits), (
        f"deleted doc still returned: {_names(hits)}"
    )


async def _case_tenant_overlay_shadows_base(provider: Any) -> None:
    _require(provider, "index")
    await _index_fixture(provider)
    # Overlay the base s-memory with a tenant-specific variant sharing the
    # query vocabulary (so it also ranks) but a distinct snippet marker.
    await provider.index([{
        "scope": FIXTURE_SCOPE, "kind": "Story", "name": "s-memory",
        "tenant": "acme", "title": "Memory recall (acme)",
        "text": "memory similarity recall acme overlay variant tenant-specific",
    }])

    base = await provider.search(
        scope=FIXTURE_SCOPE, query_text="memory recall", kind="Story",
        k=10, tenant="",
    )
    over = await provider.search(
        scope=FIXTURE_SCOPE, query_text="memory recall", kind="Story",
        k=10, tenant="acme",
    )
    # Overlay never leaks into base; base still present.
    assert "s-memory" in _names(base)
    base_hit = next(h for h in base if h["name"] == "s-memory")
    assert "acme" not in (base_hit.get("title") or "").lower(), (
        "tenant overlay leaked into a base-tenant search"
    )
    # Tenant read shadows base with EXACTLY ONE row for the shared (kind,name).
    over_memory = [h for h in over if h["name"] == "s-memory"]
    assert len(over_memory) == 1, (
        f"overlay must shadow base (one s-memory), got {len(over_memory)}"
    )
    assert "acme" in (over_memory[0].get("title") or "").lower(), (
        "tenant search must return the overlay variant, not the base"
    )


_CASES: list[tuple[str, str, Callable[[Any], Any]]] = [
    ("index_search_round_trip", "always", _case_index_search_round_trip),
    ("rrf_orders_by_relevance", "always", _case_rrf_orders_by_relevance),
    ("kind_filter", "always", _case_kind_filter),
    ("k_limit", "always", _case_k_limit),
    ("empty_query_returns_empty", "always", _case_empty_query),
    ("idempotent_index", "always", _case_idempotent_index),
    ("delete_removes", "delete()", _case_delete_removes),
    ("tenant_overlay_shadows_base", "index() tenant", _case_tenant_overlay_shadows_base),
]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecordSearchCase:
    """One runnable conformance case bound to a provider factory."""

    name: str
    requires: str
    factory: ProviderFactory
    _fn: Callable[[Any], Any]

    async def run(self) -> None:
        built = await self.factory()
        provider, cleanup = built if isinstance(built, tuple) else (built, None)
        try:
            await self._fn(provider)
        finally:
            if cleanup is not None:
                await cleanup()
            close = getattr(provider, "close", None)
            if callable(close):
                try:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
                except Exception:  # noqa: BLE001
                    pass

    def __repr__(self) -> str:
        return f"RecordSearchCase({self.name})"


def record_search_conformance_suite(
    factory: ProviderFactory,
) -> list[RecordSearchCase]:
    """THE public conformance suite for RecordSearchProvider adapters.

    Args:
        factory: async zero-arg callable returning ``(provider, cleanup)``.
            Called once PER CASE (fresh provider each time). The factory wires
            a kernel with the deterministic ``FakeEmbeddingProvider`` so the
            suite runs fully offline.

    Returns:
        list of :class:`RecordSearchCase` — parametrize in pytest and
        ``await case.run()``.
    """
    return [
        RecordSearchCase(name=name, requires=requires, factory=factory, _fn=fn)
        for name, requires, fn in _CASES
    ]


@dataclass
class RecordSearchReport:
    passed: list[str]
    failed: list[tuple[str, str]]
    skipped: list[tuple[str, str]]

    @property
    def ok(self) -> bool:
        return not self.failed

    def raise_if_failed(self) -> None:
        if self.failed:
            lines = "\n".join(f"  - {n}: {e}" for n, e in self.failed)
            raise AssertionError(
                f"record-search conformance failed {len(self.failed)} case(s):\n{lines}"
            )


async def run_record_search_conformance(
    factory: ProviderFactory,
) -> RecordSearchReport:
    """Run the whole suite programmatically (scripts, CI without pytest)."""
    report = RecordSearchReport(passed=[], failed=[], skipped=[])
    for case in record_search_conformance_suite(factory):
        try:
            await case.run()
        except SearchCaseNotApplicable as skip:
            report.skipped.append((case.name, str(skip)))
        except Exception as exc:  # noqa: BLE001
            report.failed.append((case.name, f"{type(exc).__name__}: {exc}"))
        else:
            report.passed.append(case.name)
    return report
