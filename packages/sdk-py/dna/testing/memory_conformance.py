"""Memory conformance kit (s-memory-conformance-kit).

The behavioral contract of DNA's memory — the memory-plane sibling of
``source_conformance_suite`` / ``record_search_conformance_suite``, and the
named follow-up of the semantic-recall story (s-memory-semantic-recall): the
search plane had a public kit, memory did not.

Two suites, two audiences:

* :func:`memory_conformance_suite` — the KERNEL-BOUND battery over the four
  memory verbs (``remember`` / ``recall`` / ``forget`` / ``consolidate`` +
  ``backfill_index``). For adapter authors: hand it a factory that builds a
  kernel wired with YOUR writable source (and, optionally, YOUR
  ``RecordSearchProvider`` / ``EmbeddingPort``) and it proves the memory
  lifecycle holds over your stack — roundtrip, determinism, semantic on/off,
  bi-temporal forget, reconsolidation, idempotent consolidate, monotonic
  decay, idempotent lazy backfill. Capability-aware: cases that need a search
  provider skip cleanly when none is registered (and vice versa), mirroring
  the source kit's capability philosophy.

* :func:`memory_scoring_conformance_suite` — the PURE scoring battery
  (no kernel, no IO) over the deterministic core the verbs compose: ecphory
  weights + threshold, deterministic ordering, the semantic hook, RRF fusion,
  Ebbinghaus decay, bi-temporal fail-open. For anyone evolving the scoring
  (regression pin) or shipping a custom embedder (the two embedder-driven
  cases assert RELATIVE similarity, search-kit style, so they hold for a real
  model too). This suite is twinned 1:1 in TypeScript
  (``memoryScoringConformanceSuite`` in ``dna-sdk/testing``) — same case
  names, same assertions. The verb suite has NO TS twin because the verbs are
  Py-only by declared boundary (the TS SDK ships the pure core only).

Consumption contract (same shape as the sibling kits)
-----------------------------------------------------

``memory_conformance_suite(factory)`` returns a list of
:class:`MemoryConformanceCase`. Each ``case.run()`` builds a FRESH kernel via
``factory`` (isolation between cases), drives the PUBLIC verb surface only,
and always awaits the factory-provided cleanup.

``factory`` is an async zero-arg callable returning ``(kernel, cleanup)``
where ``cleanup`` is an async zero-arg callable or ``None``. The kernel must
have a WRITABLE source; register a ``RecordSearchProvider`` on it to exercise
the hybrid/semantic cases. Determinism cases require a deterministic embedder
— the kernel's default ``FakeEmbeddingProvider`` floor qualifies (so the
whole suite runs offline), and so does any real embedder that is
deterministic for identical input.

Every timestamp in the kit is SIMULATED (the verbs' ``now=`` parameter);
nothing depends on the wall clock.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from dna.memory import (
    DEFAULT_DECAY_POLICY,
    EngramRef,
    backfill_index,
    consolidate,
    cosine_similarity,
    currently_valid,
    ebbinghaus_retention,
    ecphory_rank,
    engram_text,
    forget,
    fuse_semantic_recall,
    recall,
    recall_bump,
    remember,
    semantic_scores_from_vectors,
)
from dna.memory.policy import DEFAULT_RECALL_POLICY

#: The scope every memory-conformance fixture lives in.
MEMORY_FIXTURE_SCOPE = "memory-conformance-kit"

#: Simulated clock anchors — the kit never reads the wall clock.
KIT_NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
_CREATED_AT = "2026-07-01T00:00:00+00:00"

_AFFECT_REASON = (
    "a concrete reason long enough for the affect validator to accept it in full"
)

KernelCleanup = Callable[[], Awaitable[None]]
KernelFactory = Callable[[], Awaitable[tuple[Any, "KernelCleanup | None"]]]

#: Async ``texts -> vectors`` — the shape the scoring suite drives.
EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]
EmbedderCleanup = Callable[[], Awaitable[None]]
EmbedderFactory = Callable[[], Awaitable[tuple[Any, "EmbedderCleanup | None"]]]


class MemoryCaseNotApplicable(unittest.SkipTest):
    """Raised when the factory's kernel doesn't have the capability a case
    needs (e.g. no search provider). pytest/unittest report it as a skip."""


def fixture_memories() -> list[dict[str, Any]]:
    """Canonical fixture: three LessonLearned engrams with disjoint
    vocabularies (clean relevance signal under the fake hash embedder AND any
    real one — relative assertions only), same affect (no affect-boost skew),
    numeric confidence (so reconsolidation's bump is observable), and a fixed
    ``created_at`` (fully simulated time)."""
    def _ll(name: str, area: str, summary: str) -> dict[str, Any]:
        return {
            "kind": "LessonLearned",
            "name": name,
            "spec": {
                "area": area,
                "surface_when": ["feature_touched"],
                "source_refs": ["s-memory-conformance-kit"],
                "affect": "wistful",
                "affect_reason": _AFFECT_REASON,
                "summary": summary,
                "confidence_score": 3.0,
                "created_at": _CREATED_AT,
            },
        }

    return [
        _ll("rem-memory", "Feature/memory",
            "vector embedding recall cognitive memory ecphory"),
        _ll("rem-banana", "Feature/food",
            "banana tropical yellow fruit smoothie breakfast"),
        _ll("rem-fusion", "Feature/search",
            "hybrid search fusion reciprocal rank lexical dense"),
    ]


async def _seed(kernel: Any, *, now: datetime = KIT_NOW) -> bool:
    """Remember the canonical fixture. Returns True when the kernel indexed
    the writes (i.e. a search provider is registered) — the kit's PUBLIC
    capability probe (``remember`` reports ``indexed``)."""
    indexed = False
    for m in fixture_memories():
        out = await remember(
            kernel, MEMORY_FIXTURE_SCOPE,
            kind=m["kind"], name=m["name"], spec=m["spec"], now=now,
        )
        indexed = bool(out["indexed"])
    return indexed


def _names(hits: list[dict[str, Any]]) -> list[str]:
    return [h["name"] for h in hits]

def _hit(res: dict[str, Any], name: str) -> dict[str, Any]:
    for h in res["hits"]:
        if h.get("name") == name:
            return h
    raise AssertionError(f"{name} not in hits: {_names(res['hits'])}")


_FUSION_KEYS = ("rank_recall", "rank_ecphory", "score_recall", "semantic")

#: The cue drawn from rem-memory's vocabulary — ranks it first under lexical
#: BM25, dense cosine, and hybrid RRF alike (relative assertions only).
_MEMORY_QUERY = "memory recall cognitive vector"


# ---------------------------------------------------------------------------
# kernel-bound cases (the verb contract)
# ---------------------------------------------------------------------------

async def _case_remember_enriches_and_recall_finds(kernel: Any) -> None:
    """remember→recall roundtrip + deterministic enrichment. Enrichment never
    overwrites caller-provided values (stamp-if-absent contract)."""
    await _seed(kernel)
    got = await kernel.get_document(MEMORY_FIXTURE_SCOPE, "LessonLearned", "rem-memory")
    spec = got["spec"]
    assert spec.get("memory_type") in ("episodic", "semantic", "procedural"), (
        f"remember must classify memory_type, got {spec.get('memory_type')!r}"
    )
    ec = spec.get("encoding_context") or {}
    assert ec.get("area") == "Feature/memory", (
        f"encoding_context must mirror the area, got {ec!r}"
    )
    assert ec.get("time_of_day"), "encoding_context must derive time_of_day"
    assert spec.get("valid_from") == _CREATED_AT, (
        "bi-temporal valid_from must seed from created_at"
    )

    # Explicit enrichment is respected, never overwritten. Disjoint
    # vocabulary so this extra memory never competes in the ranking below.
    custom = fixture_memories()[0]["spec"] | {
        "area": "Custom/area",
        "summary": "quartz zeppelin corridor lantern",
        "memory_type": "procedural",
        "encoding_context": {"area": "Custom/area", "time_of_day": "night"},
    }
    await remember(kernel, MEMORY_FIXTURE_SCOPE, name="rem-custom", spec=custom, now=KIT_NOW)
    got = await kernel.get_document(MEMORY_FIXTURE_SCOPE, "LessonLearned", "rem-custom")
    assert got["spec"]["memory_type"] == "procedural"
    assert got["spec"]["encoding_context"]["area"] == "Custom/area"

    res = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY,
                       k=3, reconsolidate=False, now=KIT_NOW)
    assert res["hits"], "recall found nothing after remember"
    assert res["hits"][0]["name"] == "rem-memory", (
        f"the memory sharing the cue vocabulary must rank first, got {_names(res['hits'])}"
    )
    for h in res["hits"]:
        assert {"kind", "name", "score"} <= set(h), f"hit missing guaranteed keys: {h}"


async def _case_recall_is_deterministic(kernel: Any) -> None:
    """Same cue + same simulated now + reconsolidate=False + a deterministic
    embedder → identical hits, twice."""
    await _seed(kernel)
    kwargs: dict[str, Any] = dict(k=5, reconsolidate=False, now=KIT_NOW)
    r1 = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY, **kwargs)
    r2 = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY, **kwargs)
    assert r1["hits"] == r2["hits"], (
        "recall must be deterministic for identical inputs:\n"
        f"  first : {[(h['name'], h['score']) for h in r1['hits']]}\n"
        f"  second: {[(h['name'], h['score']) for h in r2['hits']]}"
    )
    assert (r1["degraded"], r1["semantic"]) == (r2["degraded"], r2["semantic"])


async def _case_semantic_off_preserves_base_shape(kernel: Any) -> None:
    """``semantic=False`` is the pre-semantic contract: no fusion annotations
    ever appear on the hits (byte-shape base), regardless of provider."""
    await _seed(kernel)
    res = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY,
                       k=5, reconsolidate=False, semantic=False, now=KIT_NOW)
    assert res["semantic"] is False
    assert res["hits"], "semantic=False must still recall (base plane)"
    for h in res["hits"]:
        leaked = [key for key in _FUSION_KEYS if key in h]
        assert not leaked, f"semantic=False leaked fusion annotations {leaked} on {h['name']}"


async def _case_semantic_fusion_activates(kernel: Any) -> None:
    """With a provider registered, auto mode turns the semantic plane on:
    ``semantic=True``, hybrid (not degraded), every hit annotated with its
    recall rank, and the vocabulary-matching hit carries the ecphory rank +
    cue↔memory cosine."""
    indexed = await _seed(kernel)
    if not indexed:
        raise MemoryCaseNotApplicable(
            "no search provider registered (remember reported indexed=False) — "
            "semantic fusion case not applicable."
        )
    res = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY,
                       k=3, reconsolidate=False, now=KIT_NOW)
    assert res["semantic"] is True, "auto mode must activate semantic with a provider"
    assert res["degraded"] is False, "provider-backed recall must not be degraded"
    for h in res["hits"]:
        assert "rank_recall" in h and "score_recall" in h, (
            f"fused hit missing recall-rank annotations: {h}"
        )
    top = _hit(res, "rem-memory")
    assert "rank_ecphory" in top, "the vocabulary match must clear the ecphory gate"
    assert float(top.get("semantic", 0.0)) > 0.0, (
        "the embedder must give positive similarity to token-overlapping text"
    )


async def _case_lexical_fallback_degrades_honestly(kernel: Any) -> None:
    """Without a provider, recall still works via the kernel's honest lexical
    fallback — degraded=True, semantic auto stays off, hits still found."""
    indexed = await _seed(kernel)
    if indexed:
        raise MemoryCaseNotApplicable(
            "a search provider is registered — the lexical-fallback branch "
            "is not exercised by this factory."
        )
    res = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY,
                       k=3, reconsolidate=False, now=KIT_NOW)
    assert res["degraded"] is True, "no provider → recall must report degraded"
    assert res["semantic"] is False, "auto mode must stay off without a provider"
    assert res["hits"] and res["hits"][0]["name"] == "rem-memory"


async def _case_forget_is_bitemporal_and_idempotent(kernel: Any) -> None:
    """forget = bi-temporal DEMOTION: sets valid_to, NEVER hard-deletes,
    drops the memory from every later recall, keeps the original valid_to on
    re-forget, and records supersession."""
    await _seed(kernel)
    out = await forget(kernel, MEMORY_FIXTURE_SCOPE, "rem-memory",
                       superseded_by="rem-new", now=KIT_NOW)
    assert out["valid_to"] and out["already_forgotten"] is False

    got = await kernel.get_document(MEMORY_FIXTURE_SCOPE, "LessonLearned", "rem-memory")
    assert got is not None, "forget must NEVER hard-delete (auditable, revivable)"
    assert got["spec"]["valid_to"] == out["valid_to"]
    assert got["spec"]["superseded_by_memory"] == "rem-new"

    res = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY,
                       k=5, reconsolidate=False, now=KIT_NOW)
    assert "rem-memory" not in _names(res["hits"]), (
        "a forgotten memory must never resurface in default recall"
    )

    again = await forget(kernel, MEMORY_FIXTURE_SCOPE, "rem-memory", now=KIT_NOW)
    assert again["already_forgotten"] is True
    assert again["valid_to"] == out["valid_to"], (
        "re-forget must keep the ORIGINAL valid_to (idempotence)"
    )


async def _case_reconsolidation_reinforces_surfaced(kernel: Any) -> None:
    """Surfacing a memory reinforces it (Nader light reconsolidation): cue
    appended to cues_history, surface_count bumped, confidence bumped,
    last_surfaced stamped with the SIMULATED now."""
    await _seed(kernel)
    await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY,
                 k=1, actor="memory-conformance-kit", now=KIT_NOW)
    got = await kernel.get_document(MEMORY_FIXTURE_SCOPE, "LessonLearned", "rem-memory")
    spec = got["spec"]
    assert spec["surface_count"] == 1
    assert len(spec["cues_history"]) == 1
    entry = spec["cues_history"][0]
    assert entry["actor"] == "memory-conformance-kit"
    assert entry["cue"] == _MEMORY_QUERY
    assert spec["last_surfaced"] == KIT_NOW.isoformat(timespec="seconds")
    assert abs(float(spec["confidence_score"]) - 3.05) < 1e-9, (
        f"numeric confidence must bump by 0.05, got {spec['confidence_score']}"
    )


async def _case_consolidate_reports_then_archives_idempotently(kernel: Any) -> None:
    """The deterministic consolidation pass: report-only never archives;
    apply=True soft-forgets (bi-temporal, never deletes); a later pass no
    longer evaluates the already-invalidated memory (idempotence)."""
    await _seed(kernel)
    # Age rem-banana through the PUBLIC surface: surface it long ago so its
    # Ebbinghaus retention at 'later' is far below the stale floor.
    ancient = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
    await recall(kernel, MEMORY_FIXTURE_SCOPE, "banana tropical smoothie",
                 k=1, actor="kit", now=ancient)
    later = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

    report = await consolidate(kernel, MEMORY_FIXTURE_SCOPE, apply=False, now=later)
    stale_names = [s["name"] for s in report["stale"]]
    assert "rem-banana" in stale_names, f"aged memory must be stale, got {stale_names}"
    assert "rem-memory" not in stale_names and "rem-fusion" not in stale_names
    assert report["archived"] == 0, "report-only must not archive"
    got = await kernel.get_document(MEMORY_FIXTURE_SCOPE, "LessonLearned", "rem-banana")
    assert not got["spec"].get("valid_to"), "report-only must not touch valid_to"

    report2 = await consolidate(kernel, MEMORY_FIXTURE_SCOPE, apply=True, now=later)
    assert report2["archived"] == len(report2["stale"]) >= 1
    got = await kernel.get_document(MEMORY_FIXTURE_SCOPE, "LessonLearned", "rem-banana")
    assert got is not None and got["spec"].get("valid_to"), (
        "apply must soft-forget (valid_to), never delete"
    )

    even_later = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
    report3 = await consolidate(kernel, MEMORY_FIXTURE_SCOPE, apply=True, now=even_later)
    assert report3["evaluated"] == report2["evaluated"] - report2["archived"], (
        "an archived memory must drop out of later consolidation passes"
    )
    assert report3["stale"] == [] and report3["archived"] == 0, (
        "consolidate must be idempotent once the stale set is archived"
    )


async def _case_retention_decays_monotonically(kernel: Any) -> None:
    """Ebbinghaus over SIMULATED time: after a memory is surfaced at t0, its
    recall-reported retention strictly decreases as now advances."""
    await _seed(kernel)
    t0 = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)
    await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY, k=1, now=t0)  # last_surfaced = t0

    r1 = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY,
                      k=5, reconsolidate=False, now=t1)
    r2 = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY,
                      k=5, reconsolidate=False, now=t2)
    ret1 = float(_hit(r1, "rem-memory")["retention"])
    ret2 = float(_hit(r2, "rem-memory")["retention"])
    assert ret1 < 1.0, f"a surfaced memory must have decayed retention, got {ret1}"
    assert ret2 < ret1, f"retention must be monotonic in time: {ret2} !< {ret1}"


async def _case_backfill_index_is_idempotent(kernel: Any) -> None:
    """The lazy migration story: a memory written with ``index=False`` (or
    before any provider existed) is (re)indexed on demand; the second pass is
    a no-op by text hash; recall then finds it hybrid."""
    m = fixture_memories()[0]
    out = await remember(kernel, MEMORY_FIXTURE_SCOPE, name=m["name"],
                         spec=m["spec"], index=False, now=KIT_NOW)
    assert out["indexed"] is False
    first = await backfill_index(kernel, MEMORY_FIXTURE_SCOPE)
    if first == 0:
        raise MemoryCaseNotApplicable(
            "no search provider registered (backfill_index returned 0) — "
            "backfill case not applicable."
        )
    assert first >= 1
    second = await backfill_index(kernel, MEMORY_FIXTURE_SCOPE)
    assert second == 0, f"backfill must be idempotent by text hash, re-embedded {second}"
    res = await recall(kernel, MEMORY_FIXTURE_SCOPE, _MEMORY_QUERY,
                       k=3, reconsolidate=False, now=KIT_NOW)
    assert res["degraded"] is False and res["hits"][0]["name"] == m["name"]


_CASES: list[tuple[str, str, Callable[[Any], Any]]] = [
    ("remember_enriches_and_recall_finds", "always", _case_remember_enriches_and_recall_finds),
    ("recall_is_deterministic", "always", _case_recall_is_deterministic),
    ("semantic_off_preserves_base_shape", "always", _case_semantic_off_preserves_base_shape),
    ("semantic_fusion_activates", "search provider", _case_semantic_fusion_activates),
    ("lexical_fallback_degrades_honestly", "no search provider", _case_lexical_fallback_degrades_honestly),
    ("forget_is_bitemporal_and_idempotent", "always", _case_forget_is_bitemporal_and_idempotent),
    ("reconsolidation_reinforces_surfaced", "always", _case_reconsolidation_reinforces_surfaced),
    ("consolidate_reports_then_archives_idempotently", "always", _case_consolidate_reports_then_archives_idempotently),
    ("retention_decays_monotonically", "always", _case_retention_decays_monotonically),
    ("backfill_index_is_idempotent", "search provider", _case_backfill_index_is_idempotent),
]


# ---------------------------------------------------------------------------
# public API — kernel-bound suite
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryConformanceCase:
    """One runnable conformance case bound to a kernel factory."""

    name: str
    requires: str
    factory: KernelFactory
    _fn: Callable[[Any], Any]

    async def run(self) -> None:
        built = await self.factory()
        kernel, cleanup = built if isinstance(built, tuple) else (built, None)
        try:
            await self._fn(kernel)
        finally:
            if cleanup is not None:
                await cleanup()

    def __repr__(self) -> str:
        return f"MemoryConformanceCase({self.name})"


def memory_conformance_suite(factory: KernelFactory) -> list[MemoryConformanceCase]:
    """THE public conformance suite for the memory verbs over a custom stack.

    Args:
        factory: async zero-arg callable returning ``(kernel, cleanup)``.
            Called once PER CASE (fresh kernel each time). The kernel needs a
            writable source; register your ``RecordSearchProvider`` /
            ``EmbeddingPort`` on it to exercise the hybrid + semantic cases
            (they skip cleanly otherwise).

    Returns:
        list of :class:`MemoryConformanceCase` — parametrize in pytest and
        ``await case.run()``.
    """
    return [
        MemoryConformanceCase(name=name, requires=requires, factory=factory, _fn=fn)
        for name, requires, fn in _CASES
    ]


@dataclass
class MemoryConformanceReport:
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
                f"memory conformance failed {len(self.failed)} case(s):\n{lines}"
            )


async def run_memory_conformance(factory: KernelFactory) -> MemoryConformanceReport:
    """Run the whole verb suite programmatically (scripts, CI without pytest)."""
    report = MemoryConformanceReport(passed=[], failed=[], skipped=[])
    for case in memory_conformance_suite(factory):
        try:
            await case.run()
        except MemoryCaseNotApplicable as skip:
            report.skipped.append((case.name, str(skip)))
        except Exception as exc:  # noqa: BLE001
            report.failed.append((case.name, f"{type(exc).__name__}: {exc}"))
        else:
            report.passed.append(case.name)
    return report


# ---------------------------------------------------------------------------
# pure scoring suite (Py↔TS twinned — same case names as the TS kit)
# ---------------------------------------------------------------------------

async def _default_embed(texts: list[str]) -> list[list[float]]:
    from dna.kernel.embedding import fake_embed_one
    return [fake_embed_one(t) for t in texts]


def _paraphrase_engrams() -> list[EngramRef]:
    """Target/decoy pair: the query is a PARAPHRASE of the target (no shared
    phrase, no token-subset — the cue-match paths score it 0 + novelty) and
    unrelated to the decoy. Never-recalled engrams, so Semon's novelty boost
    applies to both equally (the decoy still stays under the gate)."""
    return [
        EngramRef("rem-target", {
            "area": "Feature/kernel",
            "summary": "deep-copy before mutating documents",
            "created_at": _CREATED_AT,
        }),
        EngramRef("rem-decoy", {
            "area": "Feature/ops",
            "summary": "safely archive old reports nightly",
            "created_at": _CREATED_AT,
        }),
    ]


_PARAPHRASE_QUERY = "mutating documents safely"


async def _scoring_cosine_tracks_similarity(embed: EmbedFn) -> None:
    """The embedder contract the memory plane needs: identical text is
    maximally similar; a paraphrase is closer than unrelated text. RELATIVE
    assertions only — they hold for the fake floor and any real model."""
    texts = [
        "deep copy before mutating documents",
        "mutating documents safely",
        "banana tropical smoothie breakfast",
    ]
    vecs = await embed(texts)
    self_cos = cosine_similarity(vecs[0], (await embed([texts[0]]))[0])
    assert self_cos > 1.0 - 1e-6, f"identical text must be maximally similar, got {self_cos}"
    para = cosine_similarity(vecs[0], vecs[1])
    unrelated = cosine_similarity(vecs[0], vecs[2])
    assert para > unrelated, (
        f"paraphrase must be closer than unrelated text: {para} !> {unrelated}"
    )


async def _scoring_ecphory_weights_and_threshold(embed: EmbedFn) -> None:
    """Exact weight/threshold arithmetic with INJECTED semantic scores
    (embedder-independent): area exact-match = content_weight; the semantic
    Path 3 = cosine_weight × cos; primary is the MAX of the paths; a score
    under direct_threshold is gated out."""
    pol = DEFAULT_RECALL_POLICY
    old_cue = [{"at": "2020-01-01T00:00:00+00:00", "cue": "old", "actor": "kit"}]
    e_area = EngramRef("rem-area", {
        "area": "kernel cache mutation", "summary": "",
        "created_at": _CREATED_AT, "cues_history": old_cue,
    })
    e_sem = EngramRef("rem-sem", {
        "area": "Feature/elsewhere", "summary": "totally unrelated words entirely",
        "created_at": _CREATED_AT, "cues_history": old_cue,
    })
    e_below = EngramRef("rem-below", {
        "area": "Feature/nowhere", "summary": "different disjoint vocabulary again",
        "created_at": _CREATED_AT, "cues_history": old_cue,
    })
    sem = {"rem-sem": 0.8, "rem-below": 0.4}
    ranked = ecphory_rank(
        [e_area, e_sem, e_below], "kernel cache mutation", sem, now=KIT_NOW,
    )
    by_name = {s.engram.name: s for s in ranked}
    assert set(by_name) == {"rem-area", "rem-sem"}, (
        f"0.61×0.4 < direct_threshold must gate rem-below out, got {sorted(by_name)}"
    )
    assert abs(by_name["rem-area"].score - pol.content_weight) < 1e-9, (
        f"exact area match must score content_weight, got {by_name['rem-area'].score}"
    )
    assert by_name["rem-area"].matched_dims[0] == "area"
    assert abs(by_name["rem-sem"].score - pol.cosine_weight * 0.8) < 1e-9, (
        f"Path 3 must blend cosine_weight × cos, got {by_name['rem-sem'].score}"
    )
    assert by_name["rem-sem"].matched_dims[0].startswith("semantic~")


async def _scoring_ecphory_deterministic_ordering(embed: EmbedFn) -> None:
    """Ties break by name ascending; a rerun is identical (fully
    deterministic, the Py↔TS parity precondition)."""
    old_cue = [{"at": "2020-01-01T00:00:00+00:00", "cue": "old", "actor": "kit"}]
    spec = {"area": "kernel cache mutation", "summary": "",
            "created_at": _CREATED_AT, "cues_history": old_cue}
    engrams = [EngramRef("rem-b", dict(spec)), EngramRef("rem-a", dict(spec))]
    first = ecphory_rank(engrams, "kernel cache mutation", None, now=KIT_NOW)
    assert [s.engram.name for s in first] == ["rem-a", "rem-b"], (
        "equal scores must order by name ascending"
    )
    second = ecphory_rank(engrams, "kernel cache mutation", None, now=KIT_NOW)
    assert [(s.engram.name, s.score) for s in first] == \
           [(s.engram.name, s.score) for s in second], "rerun must be identical"


async def _scoring_semantic_hook_lifts_paraphrase(embed: EmbedFn) -> None:
    """The semantic-recall gate: the cue-match paths score a paraphrase 0 (no
    shared phrase/token-subset), so WITHOUT semantic scores nothing surfaces;
    WITH embedder-derived scores the target clears the threshold — and always
    outranks the decoy."""
    engrams = _paraphrase_engrams()
    without = ecphory_rank(engrams, _PARAPHRASE_QUERY, None, now=KIT_NOW)
    assert [s.engram.name for s in without] == [], (
        "the cue-match paths must NOT find a paraphrase on their own"
    )
    vecs = await embed([_PARAPHRASE_QUERY] + [engram_text(e.spec) for e in engrams])
    sem = semantic_scores_from_vectors([e.name for e in engrams], vecs[1:], vecs[0])
    ranked = ecphory_rank(engrams, _PARAPHRASE_QUERY, sem, now=KIT_NOW)
    names = [s.engram.name for s in ranked]
    assert "rem-target" in names, (
        f"the embedder's paraphrase similarity must lift the target over the "
        f"ecphory threshold (cos×{DEFAULT_RECALL_POLICY.cosine_weight} ≥ "
        f"{DEFAULT_RECALL_POLICY.direct_threshold}); got {names} from cosines {sem}"
    )
    if "rem-decoy" in names:
        assert names.index("rem-target") < names.index("rem-decoy"), (
            f"the paraphrase target must outrank the decoy: {names}"
        )


async def _scoring_fusion_preserves_and_annotates(embed: EmbedFn) -> None:
    """RRF fusion invariants, exact: no candidate ever disappears (a
    below-threshold hit rides its recall rank), fused score is the sum of
    reciprocal-rank contributions, and hits carry both ranks + the cosine."""
    engrams = _paraphrase_engrams()
    hits = [
        {"kind": "LessonLearned", "name": "rem-decoy", "score": 0.048},
        {"kind": "LessonLearned", "name": "rem-target", "score": 0.033},
    ]
    sem = {"rem-target": 0.9}
    fused = fuse_semantic_recall(hits, engrams, _PARAPHRASE_QUERY, sem, now=KIT_NOW)
    assert [h["name"] for h in fused] == ["rem-target", "rem-decoy"], (
        f"fusion must promote the semantic match, got {[h['name'] for h in fused]}"
    )
    target, decoy = fused
    # RRF (k=60): target = 1/(60+2) [recall #2] + 1/(60+1) [ecphory #1].
    assert abs(target["score"] - (1 / 62 + 1 / 61)) < 1e-12
    assert (target["rank_recall"], target["rank_ecphory"]) == (2, 1)
    assert abs(target["score_recall"] - 0.033) < 1e-12
    assert abs(target["semantic"] - 0.9) < 1e-12
    # The decoy is under the ecphory gate: recall rank only, never dropped.
    assert abs(decoy["score"] - 1 / 61) < 1e-12
    assert decoy["rank_recall"] == 1 and "rank_ecphory" not in decoy
    assert fuse_semantic_recall([], engrams, _PARAPHRASE_QUERY, sem, now=KIT_NOW) == []


async def _scoring_decay_retention_monotonic(embed: EmbedFn) -> None:
    """Ebbinghaus: R(never recalled) = 1; R strictly decreases with elapsed
    days; the spacing-effect bump never exceeds max_stability_days."""
    assert ebbinghaus_retention(10.0, None) == 1.0
    assert ebbinghaus_retention(10.0, 0.0) == 1.0
    r1, r5, r50 = (ebbinghaus_retention(10.0, d) for d in (1.0, 5.0, 50.0))
    assert 1.0 > r1 > r5 > r50 > 0.0, f"retention must decay monotonically: {(r1, r5, r50)}"
    cap = DEFAULT_DECAY_POLICY.max_stability_days
    assert recall_bump(cap - 1.0, 0.001) <= cap, "the spacing bump must respect the cap"
    assert recall_bump(10.0, 1.0) > 10.0, "a recall must strengthen the engram"


async def _scoring_bitemporal_fail_open(embed: EmbedFn) -> None:
    """Bi-temporal validity: unset/future valid_to → valid; past → invalid;
    an unparseable timestamp NEVER hides a memory (fail-open)."""
    assert currently_valid(None, now=KIT_NOW) is True
    assert currently_valid("", now=KIT_NOW) is True
    assert currently_valid("2026-07-09T00:00:00+00:00", now=KIT_NOW) is False
    assert currently_valid("2026-07-11T00:00:00+00:00", now=KIT_NOW) is True
    assert currently_valid("not-a-timestamp", now=KIT_NOW) is True


_SCORING_CASES: list[tuple[str, str, Callable[[EmbedFn], Any]]] = [
    ("cosine_tracks_similarity", "embedder", _scoring_cosine_tracks_similarity),
    ("ecphory_weights_and_threshold", "pure", _scoring_ecphory_weights_and_threshold),
    ("ecphory_deterministic_ordering", "pure", _scoring_ecphory_deterministic_ordering),
    ("semantic_hook_lifts_paraphrase", "embedder", _scoring_semantic_hook_lifts_paraphrase),
    ("fusion_preserves_and_annotates", "pure", _scoring_fusion_preserves_and_annotates),
    ("decay_retention_monotonic", "pure", _scoring_decay_retention_monotonic),
    ("bitemporal_fail_open", "pure", _scoring_bitemporal_fail_open),
]


def _as_embed_fn(embedder: Any) -> EmbedFn:
    """Normalize an embedder (an ``EmbeddingPort``-shaped object with async
    ``embed(texts)``, or a bare async callable) to the ``EmbedFn`` shape."""
    embed = getattr(embedder, "embed", None)
    if callable(embed):
        return embed
    if callable(embedder):
        return embedder
    raise TypeError(
        f"embedder must expose async embed(texts) or be callable, got {type(embedder)!r}"
    )


@dataclass(frozen=True)
class MemoryScoringCase:
    """One runnable pure-scoring case, optionally bound to an embedder factory."""

    name: str
    requires: str
    embedder_factory: "EmbedderFactory | None"
    _fn: Callable[[EmbedFn], Any]

    async def run(self) -> None:
        if self.embedder_factory is None:
            await self._fn(_default_embed)
            return
        built = await self.embedder_factory()
        embedder, cleanup = built if isinstance(built, tuple) else (built, None)
        try:
            await self._fn(_as_embed_fn(embedder))
        finally:
            if cleanup is not None:
                await cleanup()

    def __repr__(self) -> str:
        return f"MemoryScoringCase({self.name})"


def memory_scoring_conformance_suite(
    embedder_factory: "EmbedderFactory | None" = None,
) -> list[MemoryScoringCase]:
    """THE public conformance suite for the pure memory-scoring core.

    Twinned 1:1 with the TypeScript ``memoryScoringConformanceSuite`` (same
    case names, same assertions) — the parity guarantee for anyone evolving
    the scoring, and the behavioral contract for a custom embedder.

    Args:
        embedder_factory: optional async zero-arg callable returning
            ``(embedder, cleanup)`` where ``embedder`` exposes async
            ``embed(texts) -> vectors`` (an ``EmbeddingPort`` works as-is).
            ``None`` (default) runs against the deterministic fake floor —
            fully offline. The two embedder-driven cases assert RELATIVE
            similarity only, so a real model passes too; note that
            ``semantic_hook_lifts_paraphrase`` honestly requires the embedder
            to score an easy paraphrase above the ecphory gate
            (``cos ≥ (direct_threshold − novelty_boost) / cosine_weight``
            ≈ 0.41) — an embedder that can't clear it cannot power semantic
            recall.

    Returns:
        list of :class:`MemoryScoringCase` — parametrize in pytest and
        ``await case.run()``.
    """
    return [
        MemoryScoringCase(
            name=name, requires=requires,
            embedder_factory=embedder_factory, _fn=fn,
        )
        for name, requires, fn in _SCORING_CASES
    ]


async def run_memory_scoring_conformance(
    embedder_factory: "EmbedderFactory | None" = None,
) -> MemoryConformanceReport:
    """Run the whole scoring suite programmatically (scripts, CI without pytest)."""
    report = MemoryConformanceReport(passed=[], failed=[], skipped=[])
    for case in memory_scoring_conformance_suite(embedder_factory):
        try:
            await case.run()
        except MemoryCaseNotApplicable as skip:
            report.skipped.append((case.name, str(skip)))
        except Exception as exc:  # noqa: BLE001
            report.failed.append((case.name, f"{type(exc).__name__}: {exc}"))
        else:
            report.passed.append(case.name)
    return report


__all__ = [
    "KIT_NOW",
    "MEMORY_FIXTURE_SCOPE",
    "MemoryCaseNotApplicable",
    "MemoryConformanceCase",
    "MemoryConformanceReport",
    "MemoryScoringCase",
    "fixture_memories",
    "memory_conformance_suite",
    "memory_scoring_conformance_suite",
    "run_memory_conformance",
    "run_memory_scoring_conformance",
]
