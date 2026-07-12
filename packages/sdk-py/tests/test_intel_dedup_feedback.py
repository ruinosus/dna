"""s-intel-dedup-memory + s-intel-feedback-loop — dedup + feedback, in the CORE.

Two stages of the intelligence cycle, backed by the memory co-pillar:

  * **Dedup** — re-running a pass over the same source produces 0 NEW insights
    (repetition is the #1 source of noise). The deterministic normalized-key
    floor is proven pure; the end-to-end re-run proves it through the engine.
  * **Feedback** — dismissing an insight records a negative-feedback engram (a
    LessonLearned, via the memory co-pillar's ``remember``) that SUPPRESSES a
    semantically-similar candidate on the next pass; ``actioned`` reinforces; a
    precision / noise-rate metric is exposed.

The pure decisions (dedup partition, score adjustment, precision) are tested
directly; the engine-level tests drive the transport-agnostic core (no HTTP/CLI)
— mirroring test_intel_engine.py's kernel+FilesystemWritableSource wiring, and
test_memory_verbs.py's Kernel.auto()+source wiring for the LessonLearned writes.
"""
from __future__ import annotations

import pytest

from dna.extensions.intel import dedup as dedup_core
from dna.extensions.intel import engine
from dna.extensions.intel import feedback as feedback_core
from dna.memory.semantic import cosine_similarity

_SCOPE = "portfolio"
_TENANT = "acme"


# ── pure: dedup partition ──────────────────────────────────────────────────


def test_normalized_key_is_source_scoped_and_slugged():
    a = {"title": "SaMD Classe II — rache a arquitetura!", "source_ref": "s1"}
    b = {"title": "samd classe ii   rache a arquitetura", "source_ref": "s1"}
    assert dedup_core.normalized_key(a) == dedup_core.normalized_key(b)
    # a different source never collides with the same title
    assert dedup_core.normalized_key(a, "other") != dedup_core.normalized_key(a, "s1")


def test_dedup_partition_key_floor_and_cosine():
    keys = ["s::a", "s::b", "s::c"]
    existing = {"s::a"}  # 'a' already surfaced
    # cosines: b is a near-identical restatement (>= threshold), c is fresh
    cosines = [0.0, 0.99, 0.10]
    fresh, dup, reasons = dedup_core.dedup_partition(keys, cosines, existing)
    assert fresh == [2]
    assert set(dup) == {0, 1}
    assert reasons[0][0] == "key"
    assert reasons[1][0] == "cosine"


def test_dedup_partition_dedups_within_the_batch():
    # two candidates with the SAME key in one pass → only the first survives
    keys = ["s::x", "s::x"]
    fresh, dup, _ = dedup_core.dedup_partition(keys, None, set())
    assert fresh == [0]
    assert dup == [1]


# ── pure: feedback adjustment + metrics ────────────────────────────────────


def test_adjust_score_penalizes_dismissed_and_reinforces_actioned():
    # similar to a dismissed insight → strong penalty (effective threshold rises)
    adj, notes = feedback_core.adjust_score(0.85, sim_dismissed=0.90, sim_actioned=0.0)
    assert adj == pytest.approx(0.85 - feedback_core.DISMISS_PENALTY)
    assert any("dismissed" in n for n in notes)
    # similar to an actioned insight → small reinforcement
    adj2, notes2 = feedback_core.adjust_score(0.50, sim_dismissed=0.0, sim_actioned=0.95)
    assert adj2 == pytest.approx(0.50 + feedback_core.ACTION_BONUS)
    assert any("actioned" in n for n in notes2)
    # below the similarity threshold → untouched, no notes
    adj3, notes3 = feedback_core.adjust_score(0.70, sim_dismissed=0.5, sim_actioned=0.5)
    assert adj3 == pytest.approx(0.70)
    assert notes3 == []


def test_precision_and_noise_rate():
    assert feedback_core.precision(0, 0) is None  # undefined until a disposition
    assert feedback_core.precision(3, 1) == pytest.approx(0.75)
    assert feedback_core.noise_rate(3, 1) == pytest.approx(0.25)
    m = feedback_core.summarize_states({"new": 2, "actioned": 3, "dismissed": 1})
    assert m["precision"] == pytest.approx(0.75)
    assert m["noise_rate"] == pytest.approx(0.25)
    assert m["actioned"] == 3 and m["dismissed"] == 1


# ── engine: dedup re-run yields 0 new (IntelExtension-only kernel) ──────────


def _bootstrap_scope(tmp_path, scope: str) -> None:
    (tmp_path / scope).mkdir(parents=True, exist_ok=True)
    (tmp_path / scope / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        f"metadata: {{name: {scope}}}\nspec: {{}}\n"
    )


async def _intel_kernel(tmp_path):
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.intel import IntelExtension
    from dna.kernel import Kernel

    k = Kernel()
    k.load(IntelExtension())
    _bootstrap_scope(tmp_path, _SCOPE)
    src = FilesystemWritableSource(str(tmp_path), writers=list(k._writers), kernel=k)
    k.source(src)
    src.attach_kernel(k)
    return k


async def _seed_source(k, name="copiloto-medico", **over):
    spec = {
        "name": name, "type": "repo", "cadence": "weekly", "threshold": 0.6,
        "pirs": ["regulação", "concorrentes", "tech PT-BR"], "muted": False,
    }
    spec.update(over)
    await k.write_document(
        _SCOPE, "IntelSource", name,
        {
            "apiVersion": "github.com/ruinosus/dna/intel/v1",
            "kind": "IntelSource", "metadata": {"name": name}, "spec": spec,
        },
        tenant=_TENANT,
    )


@pytest.mark.asyncio
async def test_rerun_pass_yields_zero_new_insights(tmp_path):
    """(a) dedup — re-running a pass over the same source writes 0 NEW docs."""
    k = await _intel_kernel(tmp_path)
    await _seed_source(k)

    first = await engine.run_pass(k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT)
    assert first.kept_count == 7
    assert first.deduped_count == 0  # nothing surfaced before

    after_first = [r async for r in k.query(_SCOPE, "IntelInsight", tenant=_TENANT)]
    assert len(after_first) == 7

    # Re-run: every candidate is already surfaced → 0 new, all deduped.
    second = await engine.run_pass(k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT)
    assert second.kept_count == 0
    assert second.deduped_count == 7
    assert second.dedup_rate == pytest.approx(1.0)

    after_second = [r async for r in k.query(_SCOPE, "IntelInsight", tenant=_TENANT)]
    assert len(after_second) == 7  # unchanged — no duplicates written


# ── engine: feedback suppresses similar candidates (memory co-pillar) ──────


# insight A and candidate B: title+fact token sets share 9 of 10 tokens, so the
# fake-embedder cosine ≈ 0.90 — above the feedback threshold (0.80) but below the
# dedup threshold (0.97). So B is caught by FEEDBACK (a dismissed-similar
# candidate), NOT by dedup (it is not a near-identical repeat) and NOT by the key
# (its title differs). Tokens are all-distinct to keep the cosine predictable.
_A = {
    "title": "regulacao samd classe dispositivo alpha",
    "fact": "anvisa conduta suggestion liability deskilling",
    "action": "rache a arquitetura", "evidence_rating": "evidence-based",
    "source_ref": "copiloto-medico", "pirs": [],
}
_B = {
    "title": "omega samd classe dispositivo regulacao",
    "fact": "anvisa conduta suggestion liability deskilling",
    "action": "rache a arquitetura", "evidence_rating": "evidence-based",
    "source_ref": "copiloto-medico", "pirs": [],
}


class _OneShot:
    def __init__(self, cand):
        self._cand = cand

    def analyze(self, source, context):
        return [dict(self._cand)]


async def _memory_kernel(tmp_path):
    """Kernel.auto() (LessonLearned + intel Kinds + writers registered) over a
    filesystem source — mirrors test_memory_verbs.py so the co-pillar's
    ``remember`` can persist the feedback engram."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.kernel import Kernel

    base = tmp_path / "src"
    base.mkdir(parents=True)
    _bootstrap_scope(base, _SCOPE)
    kernel = Kernel.auto()
    src = FilesystemWritableSource(base_dir=str(base))
    Kernel.auto(source=src)
    kernel.source(src)
    return kernel


@pytest.mark.asyncio
async def test_fixture_cosine_lands_between_feedback_and_dedup_thresholds(tmp_path):
    """Self-check: the crafted A/B texts sit in the band where feedback fires
    but dedup does not — so the suppression below is unambiguously feedback."""
    k = await _memory_kernel(tmp_path)
    va, vb = await k.embed([dedup_core.insight_text(_A), dedup_core.insight_text(_B)])
    cos = cosine_similarity(va, vb)
    assert feedback_core.FEEDBACK_SIM_THRESHOLD <= cos < dedup_core.DEDUP_COSINE_THRESHOLD


@pytest.mark.asyncio
async def test_dismiss_suppresses_similar_candidate_next_pass(tmp_path):
    """(b) feedback — dismissing insight A records a negative engram that
    suppresses the similar candidate B on the next pass. Control: without the
    dismissal, B is delivered — so the suppression is caused by the feedback."""
    # --- control: B alone is delivered (clears the ranker + dedup) ---
    kc = await _memory_kernel(tmp_path / "ctrl")
    await _seed_source(kc)
    ctrl = await engine.run_pass(
        kc, "copiloto-medico", scope=_SCOPE, tenant=_TENANT, analyzer=_OneShot(_B),
    )
    assert ctrl.kept_count == 1
    assert ctrl.kept[0]["title"] == _B["title"]

    # --- treatment: surface A, dismiss it, then run B ---
    k = await _memory_kernel(tmp_path / "treat")
    await _seed_source(k)
    first = await engine.run_pass(
        k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT, analyzer=_OneShot(_A),
    )
    assert first.kept_count == 1
    name_a = first.kept[0]["name"]

    await engine.set_insight_state(k, name_a, "dismissed", scope=_SCOPE, tenant=_TENANT)
    # the co-pillar recorded a feedback engram (LessonLearned)
    engrams = [
        r async for r in k.query(_SCOPE, "LessonLearned", tenant=_TENANT)
    ]
    assert any(
        feedback_core.FEEDBACK_TAG in (r.get("spec", {}).get("tags") or [])
        for r in engrams
    ), "dismissing an insight must record an intel-feedback engram"

    treat = await engine.run_pass(
        k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT, analyzer=_OneShot(_B),
    )
    # B is now SUPPRESSED (below the feedback-raised effective threshold), not
    # written — and it was NOT merely deduped (different title, cosine < dedup).
    assert treat.kept_count == 0
    assert treat.suppressed_count == 1
    assert "feedback" in treat.suppressed[0]["rationale"]
    written_titles = {
        r["spec"]["title"] async for r in k.query(_SCOPE, "IntelInsight", tenant=_TENANT)
    }
    assert _B["title"] not in written_titles


@pytest.mark.asyncio
async def test_feedback_metrics_precision(tmp_path):
    """(b) a precision / noise-rate metric is exposed and inspectable."""
    k = await _memory_kernel(tmp_path)
    await _seed_source(k)
    res = await engine.run_pass(k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT)
    names = [r["name"] for r in res.kept]
    # action 3, dismiss 1 → precision 0.75, noise 0.25
    for n in names[:3]:
        await engine.set_insight_state(k, n, "actioned", scope=_SCOPE, tenant=_TENANT)
    await engine.set_insight_state(k, names[3], "dismissed", scope=_SCOPE, tenant=_TENANT)

    metrics = await engine.feedback_metrics(k, scope=_SCOPE, tenant=_TENANT)
    assert metrics["actioned"] == 3
    assert metrics["dismissed"] == 1
    assert metrics["precision"] == pytest.approx(0.75)
    assert metrics["noise_rate"] == pytest.approx(0.25)
