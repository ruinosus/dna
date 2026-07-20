"""Semantic recall (s-memory-semantic-recall) — pure core + verb wiring.

Everything runs offline with the deterministic fake embedder. Proves the three
story gates:

  (a) a paraphrase the ecphory cue-match misses IS found once embedding
      similarity feeds ``score_engram``'s Path 3 (the hook ``policy.py``
      declared "inert unless a caller feeds semantic_scores");
  (b) with no provider (or ``semantic=False``) the recall verb's hits are
      IDENTICAL to the pre-semantic behavior — golden literals pinned from the
      pre-story code;
  (c) the ranking core is pure and golden-locked (the fixture executes in
      ``tests/test_memory_scoring_golden.py``; here we cover the behavior
      directly).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dna.kernel.embedding import fake_embed_one
from dna.memory import (
    EngramRef,
    cosine_similarity,
    ecphory_rank,
    engram_text,
    fuse_semantic_recall,
    semantic_scores_from_vectors,
)

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
_REASON = "a concrete reason long enough for the affect validator to accept it in full"


# ─────────────────────────── pure helpers ───────────────────────────


def test_cosine_similarity_basics():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)
    # all-zero = "no signal" (the fake embedder's empty-text vector) → 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine_similarity([], []) == 0.0


def test_cosine_over_fake_embeddings_tracks_token_overlap():
    a = fake_embed_one("mutating documents safely")
    b = fake_embed_one("deep copy before mutating documents")
    c = fake_embed_one("banana tropical smoothie")
    assert cosine_similarity(a, b) > cosine_similarity(a, c)
    assert cosine_similarity(a, c) == 0.0  # zero token overlap → orthogonal


def test_semantic_scores_drop_nonpositive_and_first_wins():
    q = [1.0, 0.0]
    scores = semantic_scores_from_vectors(
        ["hit", "anti", "flat", "hit"],
        [[0.5, 0.5], [-1.0, 0.0], [0.0, 1.0], [1.0, 0.0]],
        q,
    )
    assert set(scores) == {"hit"}          # negative + zero dropped
    assert scores["hit"] == pytest.approx(cosine_similarity(q, [0.5, 0.5]))  # first wins


def test_engram_text_uses_semantic_fields_only():
    spec = {
        "area": "Feature/kernel", "summary": "deep-copy before mutating",
        "affect": "regret", "created_at": "2026-07-01T00:00:00+00:00",
        "affect_reason": _REASON,
    }
    text = engram_text(spec)
    assert text == "Feature/kernel deep-copy before mutating"
    assert "regret" not in text and "2026" not in text  # metadata never dilutes


# ─────────────────────────── (a) paraphrase via the semantic hook ───────────────────────────


def _target() -> EngramRef:
    return EngramRef("rem-target", {
        "area": "Feature/kernel",
        "summary": "deep-copy before mutating documents",
        "created_at": "2026-07-01T00:00:00+00:00",
    })


def _decoy() -> EngramRef:
    return EngramRef("rem-decoy", {
        "area": "Feature/ops",
        "summary": "safely archive old reports nightly",
        "created_at": "2026-07-01T00:00:00+00:00",
    })


def _fake_semantic_scores(query: str, engrams: list[EngramRef]) -> dict[str, float]:
    vectors = [fake_embed_one(engram_text(e.spec)) for e in engrams]
    return semantic_scores_from_vectors(
        [e.name for e in engrams], vectors, fake_embed_one(query),
    )


def test_paraphrase_found_only_with_semantic_scores():
    """The story's core gate: the cue-match paths (area overlap / phrase-in-
    summary) score the paraphrase below ``direct_threshold``; the embedding
    cosine blended by Path 3 lifts it over."""
    query = "mutating documents safely"  # paraphrase: not a substring, not a token-subset
    engrams = [_target(), _decoy()]

    without = ecphory_rank(engrams, query, None, now=NOW)
    assert [s.engram.name for s in without] == []  # cue-match finds NOTHING

    sem = _fake_semantic_scores(query, engrams)
    with_sem = ecphory_rank(engrams, query, sem, now=NOW)
    assert [s.engram.name for s in with_sem] == ["rem-target"]  # decoy stays under threshold
    assert with_sem[0].matched_dims[0].startswith("semantic~")


def test_fuse_semantic_recall_promotes_and_annotates():
    """Fusion promotes the semantically-close memory over a lexically-boosted
    decoy, keeps every candidate (below-threshold ones ride their recall rank),
    and annotates hits with both ranks + the cosine."""
    query = "mutating documents safely"
    engrams = [_target(), _decoy()]
    sem = _fake_semantic_scores(query, engrams)
    hits = [  # the existing recall ranking: decoy first
        {"kind": "Engram", "name": "rem-decoy", "score": 0.048},
        {"kind": "Engram", "name": "rem-target", "score": 0.033},
    ]

    fused = fuse_semantic_recall(hits, engrams, query, sem, now=NOW)
    assert [h["name"] for h in fused] == ["rem-target", "rem-decoy"]  # flip

    target, decoy = fused
    # RRF: target = 1/(60+2) [recall#2] + 1/(60+1) [ecphory#1]
    assert target["score"] == pytest.approx(1 / 62 + 1 / 61)
    assert (target["rank_recall"], target["rank_ecphory"]) == (2, 1)
    assert target["score_recall"] == pytest.approx(0.033)
    assert target["semantic"] == pytest.approx(sem["rem-target"])
    # decoy is below the ecphory threshold: recall rank only, never dropped
    assert decoy["score"] == pytest.approx(1 / 61)
    assert decoy["rank_recall"] == 1 and "rank_ecphory" not in decoy


def test_fuse_semantic_recall_empty_hits():
    assert fuse_semantic_recall([], [], "anything", {}, now=NOW) == []


# ─────────────────────────── verb wiring (kernel-bound) ───────────────────────────


def _ll(name: str, area: str, summary: str, affect: str = "wistful") -> dict:
    return {
        "kind": "Engram",
        "name": name,
        "spec": {
            "area": area, "surface_when": ["feature_touched"], "source_refs": ["s-1"],
            "affect": affect, "affect_reason": _REASON, "summary": summary,
            "created_at": "2026-07-01T00:00:00+00:00",
        },
    }


@pytest.fixture
def kernel_fs(tmp_path):
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.kernel import Kernel

    base = tmp_path / "src"
    base.mkdir()
    kernel = Kernel.auto()
    kernel.source(FilesystemWritableSource(base_dir=str(base)))
    return kernel


@pytest.fixture
def kernel_with_provider(tmp_path, kernel_fs):
    pytest.importorskip("sqlite_vec", reason="search-sqlite extra not installed")
    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider

    prov = SqliteVecRecordSearchProvider(kernel_fs, db_path=str(tmp_path / "mem.db"))
    kernel_fs.record_search_provider(prov)
    yield kernel_fs
    prov.close()


async def _seed_flip_scenario(kernel) -> None:
    from dna.memory import remember

    await remember(kernel, "demo", **_ll(
        "rem-target", "Feature/kernel", "deep-copy before mutating documents", "wistful"))
    await remember(kernel, "demo", **_ll(
        "rem-decoy", "Feature/ops", "safely archive old reports nightly", "surprise"))
    await remember(kernel, "demo", **_ll(
        "rem-noise", "Feature/food", "banana tropical smoothie recipe", "wistful"))


@pytest.mark.asyncio
async def test_recall_semantic_auto_flips_paraphrase_to_top(kernel_with_provider):
    """(a) at the verb level: semantic auto (provider present) promotes the
    paraphrased memory to #1; semantic=False keeps the affect-boosted decoy."""
    from dna.memory import recall

    kernel = kernel_with_provider
    await _seed_flip_scenario(kernel)
    query = "mutating documents safely"

    off = await recall(kernel, "demo", query, k=2, reconsolidate=False,
                       semantic=False, now=NOW)
    assert off["semantic"] is False
    assert [h["name"] for h in off["hits"]] == ["rem-decoy", "rem-target"]
    assert all("rank_recall" not in h for h in off["hits"])  # shape untouched

    on = await recall(kernel, "demo", query, k=2, reconsolidate=False, now=NOW)
    assert on["semantic"] is True and on["degraded"] is False
    assert [h["name"] for h in on["hits"]] == ["rem-target", "rem-decoy"]
    top = on["hits"][0]
    assert top["rank_ecphory"] == 1 and top["rank_recall"] == 2
    assert top["semantic"] > on["hits"][1]["semantic"]
    assert top["score_recall"] > 0.0


@pytest.mark.asyncio
async def test_recall_no_provider_golden_unchanged(kernel_fs):
    """(b) zero breaking change: without a provider, auto mode leaves the
    lexical ranking IDENTICAL to the pre-semantic verb. The literals below were
    captured by running this exact scenario on the pre-story code."""
    from dna.memory import recall, remember

    kernel = kernel_fs
    await remember(kernel, "demo", **_ll(
        "rem-cache", "Feature/kernel",
        "always deep-copy the cache before mutating kernel documents", "regret"))
    await remember(kernel, "demo", **_ll(
        "rem-banana", "Feature/food", "banana tropical yellow fruit smoothie recipe", "triumph"))
    await remember(kernel, "demo", **_ll(
        "rem-search", "Feature/search",
        "hybrid search fusion mutating rank lists deterministically", "surprise"))

    res = await recall(kernel, "demo", "mutating documents", k=5,
                       reconsolidate=False, now=NOW)
    assert res["degraded"] is True and res["semantic"] is False
    golden = [("rem-cache", 1.3), ("rem-search", 0.75)]  # pre-story capture
    assert [(h["name"], h["score"]) for h in res["hits"]] == golden
    assert all(h["retention"] == 1.0 for h in res["hits"])
    assert all("rank_recall" not in h and "semantic" not in h for h in res["hits"])


@pytest.mark.asyncio
async def test_recall_semantic_forced_without_provider(kernel_fs):
    """semantic=True works with no provider: candidates come from the lexical
    fallback, embeddings from the fake floor — offline-first all the way."""
    from dna.memory import recall, remember

    kernel = kernel_fs
    await remember(kernel, "demo", **_ll(
        "rem-target", "Feature/kernel", "deep-copy before mutating documents"))

    res = await recall(kernel, "demo", "mutating documents", k=3,
                       reconsolidate=False, semantic=True, now=NOW)
    assert res["semantic"] is True
    assert res["hits"] and res["hits"][0]["name"] == "rem-target"
    assert res["hits"][0]["rank_recall"] == 1
    assert res["hits"][0]["semantic"] > 0.0


@pytest.mark.asyncio
async def test_recall_semantic_fail_soft_on_embed_error(kernel_with_provider):
    """An embedding failure NEVER breaks recall — the base ranking survives and
    the result reports semantic=False (honest degradation)."""
    from dna.memory import recall

    kernel = kernel_with_provider
    await _seed_flip_scenario(kernel)

    class _Boom:
        dims = 384
        model_id = "boom"

        async def embed(self, texts):
            raise RuntimeError("embedder down")

    kernel.embedding_provider(_Boom())
    res = await recall(kernel, "demo", "mutating documents safely", k=2,
                       reconsolidate=False, semantic=True, now=NOW)
    assert res["semantic"] is False
    # the broken embedder also degrades the provider's dense search → lexical
    assert res["degraded"] is True
    assert [h["name"] for h in res["hits"]] == ["rem-target", "rem-decoy"]
    assert all("rank_recall" not in h for h in res["hits"])


@pytest.mark.asyncio
async def test_backfill_index_makes_pre_provider_memories_recallable(tmp_path, kernel_fs):
    """The migration story: memories written BEFORE any provider existed get
    indexed on demand (idempotent by text hash), then recall is hybrid."""
    pytest.importorskip("sqlite_vec", reason="search-sqlite extra not installed")
    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider
    from dna.memory import backfill_index, recall, remember

    kernel = kernel_fs
    # No provider yet — remember writes the doc but cannot index it.
    out = await remember(kernel, "demo", **_ll(
        "rem-old", "Feature/kernel", "deep-copy before mutating documents"))
    assert out["indexed"] is False

    prov = SqliteVecRecordSearchProvider(kernel, db_path=str(tmp_path / "bf.db"))
    kernel.record_search_provider(prov)
    try:
        assert await backfill_index(kernel, "demo") == 1
        assert await backfill_index(kernel, "demo") == 0  # idempotent — no re-embed

        res = await recall(kernel, "demo", "mutating documents safely", k=3,
                           reconsolidate=False, now=NOW)
        assert res["degraded"] is False and res["semantic"] is True
        assert res["hits"][0]["name"] == "rem-old"
    finally:
        prov.close()


@pytest.mark.asyncio
async def test_backfill_index_without_provider_is_noop(kernel_fs):
    from dna.memory import backfill_index

    assert await backfill_index(kernel_fs, "demo") == 0
