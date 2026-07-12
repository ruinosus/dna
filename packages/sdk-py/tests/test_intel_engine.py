"""s-intel-insight-ranker — the intel ENGINE (pass → rank → suppress → deliver).

The walking skeleton's core, tested end-to-end WITHOUT LLM creds (the
SeedAnalyzer returns the REAL experiment insights). Proven here:

1. A pass with the SeedAnalyzer over the seeded ``copiloto-medico`` source
   produces IntelInsight docs (state=new, score/source_ref/created_at stamped).
2. Candidates below the source ``threshold`` are SUPPRESSED — returned in the
   PassResult but NEVER written (the anti-noise core).
3. The ranker scores 0..1 with an inspectable rationale, and the suppression
   boundary is exactly the threshold (>= kept, < suppressed).
4. The feedback transition ``set_insight_state`` moves new→actioned and rejects
   an invalid state / a missing doc.
5. The engine is transport-agnostic — no HTTP/CLI imports reach it.

Mirrors the kernel+FilesystemWritableSource wiring of ``test_intel_kinds.py``.
The engine logic lives in the CORE (dna.extensions.intel.engine) per
adr-faces-reorg; this test drives that core directly.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.intel import engine
from dna.extensions.intel.analyzer import Analyzer, SeedAnalyzer
from dna.extensions.intel.ranker import rank_and_suppress, score
from dna.kernel import Kernel

_SCOPE = "portfolio"
_TENANT = "acme"


# ── kernel + seeded source fixture ─────────────────────────────────────────


def _bootstrap_scope(tmp_path, scope: str) -> None:
    (tmp_path / scope).mkdir(parents=True, exist_ok=True)
    (tmp_path / scope / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        f"metadata: {{name: {scope}}}\nspec: {{}}\n"
    )


async def _kernel(tmp_path) -> Kernel:
    from dna.extensions.intel import IntelExtension

    k = Kernel()
    k.load(IntelExtension())
    _bootstrap_scope(tmp_path, _SCOPE)
    src = FilesystemWritableSource(str(tmp_path), writers=list(k._writers), kernel=k)
    k.source(src)
    src.attach_kernel(k)
    return k


async def _seed_source(k: Kernel, name: str = "copiloto-medico", **spec_over) -> None:
    spec = {
        "name": name,
        "type": "repo",
        "cadence": "weekly",
        "threshold": 0.6,
        "pirs": ["regulação", "concorrentes", "tech PT-BR"],
        "muted": False,
    }
    spec.update(spec_over)
    await k.write_document(
        _SCOPE, "IntelSource", name,
        {
            "apiVersion": "github.com/ruinosus/dna/intel/v1",
            "kind": "IntelSource",
            "metadata": {"name": name},
            "spec": spec,
        },
        tenant=_TENANT,
    )


# ── 1 + 2. the pass produces insights and suppresses below threshold ───────


@pytest.mark.asyncio
async def test_run_pass_produces_insights_and_suppresses(tmp_path):
    k = await _kernel(tmp_path)
    await _seed_source(k)

    result = await engine.run_pass(k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT)

    # The SeedAnalyzer ships 8 real candidates; exactly one is weak (no action,
    # anecdotal, no PIR) → suppressed. The rest clear the 0.6 threshold.
    assert result.analyzer == "SeedAnalyzer"
    assert result.kept_count == 7
    assert result.suppressed_count == 1
    assert "LLM clínico em PT" in result.suppressed[0]["title"]

    # KEPT candidates were written as IntelInsight docs, state=new, stamped.
    written = [r async for r in k.query(_SCOPE, "IntelInsight", tenant=_TENANT)]
    assert len(written) == 7
    for row in written:
        spec = row["spec"]
        assert spec["state"] == "new"
        assert spec["source_ref"] == "copiloto-medico"
        assert spec["score"] >= 0.6
        assert spec["created_at"]

    # SUPPRESSED candidates were NOT written — the anti-noise guarantee.
    titles = {r["spec"]["title"] for r in written}
    assert not any("LLM clínico em PT" in t for t in titles)


@pytest.mark.asyncio
async def test_suppressed_below_threshold_not_persisted(tmp_path):
    """Raise the threshold so MORE candidates fall below it — the count of
    written docs drops accordingly, proving the threshold gates persistence."""
    k = await _kernel(tmp_path)
    await _seed_source(k, threshold=0.95)  # only the perfect-scoring survive

    result = await engine.run_pass(k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT)
    written = [r async for r in k.query(_SCOPE, "IntelInsight", tenant=_TENANT)]

    assert result.kept_count == len(written)
    # Every written insight cleared the raised bar; suppression grew.
    assert all(r["spec"]["score"] >= 0.95 for r in written)
    assert result.suppressed_count > 1
    assert result.kept_count < 7


# ── 3. the ranker: score + inspectable rationale + boundary ────────────────


def test_score_is_inspectable_and_bounded():
    src = {"pirs": ["regulação"]}
    strong = score(
        {"action": "do X", "evidence_rating": "evidence-based", "pirs": ["regulação"]},
        src,
    )
    weak = score(
        {"action": None, "evidence_rating": "anecdotal", "pirs": []}, src,
    )
    assert strong.value == 1.0
    assert 0.0 <= weak.value <= 1.0
    assert weak.value == pytest.approx(0.30)
    # The rationale explains the number (not a black box).
    assert "concrete action" in strong.rationale
    assert "PIR match" in strong.rationale
    assert "no action" in weak.rationale


def test_rank_and_suppress_boundary_is_the_threshold():
    src = {"pirs": []}
    cands = [
        {"title": "kept-exactly-at", "action": "x", "evidence_rating": "anecdotal"},  # 0.60
        {"title": "just-below", "action": None, "evidence_rating": "opinion-practice"},  # 0.42
    ]
    kept, suppressed = rank_and_suppress(cands, 0.6, src)
    assert [c["title"] for c in kept] == ["kept-exactly-at"]  # >= threshold kept
    assert [c["title"] for c in suppressed] == ["just-below"]  # < threshold suppressed
    # Annotated in place for auditability.
    assert kept[0]["score"] == pytest.approx(0.60)
    assert "score_rationale" in suppressed[0]


# ── 4. the feedback transition ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_insight_state_transitions(tmp_path):
    k = await _kernel(tmp_path)
    await _seed_source(k)
    result = await engine.run_pass(k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT)
    name = result.kept[0]["name"]

    # new → actioned
    out = await engine.set_insight_state(
        k, name, "actioned", scope=_SCOPE, tenant=_TENANT,
    )
    assert out["state"] == "actioned"
    doc = await k.get_document(_SCOPE, "IntelInsight", name, tenant=_TENANT)
    assert doc["spec"]["state"] == "actioned"

    # invalid state rejected
    with pytest.raises(ValueError):
        await engine.set_insight_state(k, name, "bogus", scope=_SCOPE, tenant=_TENANT)

    # missing doc → InsightNotFound
    with pytest.raises(engine.InsightNotFound):
        await engine.set_insight_state(
            k, "ins-does-not-exist", "actioned", scope=_SCOPE, tenant=_TENANT,
        )


# ── 5. list projections + muted + unknown source ───────────────────────────


@pytest.mark.asyncio
async def test_list_sources_and_insights_and_filters(tmp_path):
    k = await _kernel(tmp_path)
    await _seed_source(k)
    await engine.run_pass(k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT)

    sources = await engine.list_sources(k, scope=_SCOPE, tenant=_TENANT)
    assert [s["name"] for s in sources] == ["copiloto-medico"]
    assert sources[0]["pirs"] == ["regulação", "concorrentes", "tech PT-BR"]

    all_insights = await engine.list_insights(k, scope=_SCOPE, tenant=_TENANT)
    assert len(all_insights) == 7
    # sorted by score desc
    assert all_insights[0]["score"] >= all_insights[-1]["score"]

    # state filter
    new_only = await engine.list_insights(
        k, scope=_SCOPE, tenant=_TENANT, state="new",
    )
    assert len(new_only) == 7
    actioned = await engine.list_insights(
        k, scope=_SCOPE, tenant=_TENANT, state="actioned",
    )
    assert actioned == []


@pytest.mark.asyncio
async def test_muted_source_produces_nothing(tmp_path):
    k = await _kernel(tmp_path)
    await _seed_source(k, muted=True)
    result = await engine.run_pass(k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT)
    assert result.kept_count == 0
    assert result.suppressed_count == 0
    written = [r async for r in k.query(_SCOPE, "IntelInsight", tenant=_TENANT)]
    assert written == []


@pytest.mark.asyncio
async def test_missing_source_raises(tmp_path):
    k = await _kernel(tmp_path)
    with pytest.raises(LookupError):
        await engine.run_pass(k, "nonexistent", scope=_SCOPE, tenant=_TENANT)


@pytest.mark.asyncio
async def test_custom_analyzer_is_pluggable(tmp_path):
    """A pass accepts any Analyzer — the pass stage is not hardwired to Seed."""
    k = await _kernel(tmp_path)
    await _seed_source(k)

    class OneShot:
        def analyze(self, source, context):
            return [{
                "title": "custom", "fact": "f", "action": "act",
                "evidence_rating": "evidence-based", "pirs": ["regulação"],
                "source_ref": source["name"],
            }]

    assert isinstance(OneShot(), Analyzer)  # structural protocol match
    result = await engine.run_pass(
        k, "copiloto-medico", scope=_SCOPE, tenant=_TENANT, analyzer=OneShot(),
    )
    assert result.analyzer == "OneShot"
    assert result.kept_count == 1
    assert result.kept[0]["title"] == "custom"


# ── engine stays transport-agnostic (adr-faces-reorg) ──────────────────────


def test_engine_has_no_transport_imports():
    """The CORE must not import HTTP/CLI transport — logic lives here,
    faces are thin. Guards the adr-faces-reorg invariant."""
    import pathlib

    src = pathlib.Path(engine.__file__).read_text()
    for banned in ("import click", "import fastapi", "from fastapi", "from click"):
        assert banned not in src, f"engine core must not import transport: {banned!r}"
    assert isinstance(SeedAnalyzer(), Analyzer)
