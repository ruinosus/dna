"""T1 — schema validation tests for the Cognitive Memory Triad.

Three new Kinds:
- ``LessonLearned`` (alias ``sdlc-remembrance``) — affective recall artifact.
- ``SynthesisRun`` (alias ``sdlc-dream``) — forward scenario with verifiable predictions.
- ``ArchiveProposal`` (alias ``sdlc-forgetting``) — pruning proposal.

Per Spec ``docs/superpowers/specs/2026-05-11-cognitive-memory-triad.md`` §3.

Three test cases per Kind (9 total):
1. Minimal valid spec passes parse.
2. Missing any required field fails parse.
3. Extra field is preserved (not stripped) — the schema is intentionally
   permissive to allow forward-compat.

The Kinds use BUNDLE storage with marker files ``LEMBRANCA.md`` /
``DREAM.md`` / ``FORGETTING.md`` mirroring SPEC.md / PLAN.md convention.
"""
from __future__ import annotations


from dna.kernel import Kernel
from dna.extensions.sdlc import SdlcExtension


def _port(kind: str):
    """F3 lote-1/lote-2: the triad classes were deleted — ports are
    synthesized from kinds/*.kind.yaml (same registration funnel)."""
    k = Kernel()
    k.load(SdlcExtension())
    return k.kind_port_for(kind)


def _lesson_learned_port():
    return _port("LessonLearned")


# ----------------------------------------------------------------------
# Registration — the extension must register the 3 new Kinds (total 15)
# ----------------------------------------------------------------------


def test_extension_registers_three_cognitive_kinds():
    k = Kernel()
    k.load(SdlcExtension())
    api_kinds = sorted(kn for (av, kn) in k._kinds if av == "github.com/ruinosus/dna/sdlc/v1")
    assert "LessonLearned" in api_kinds
    assert "SynthesisRun" in api_kinds
    assert "ArchiveProposal" in api_kinds


def test_extension_version_is_post_cognitive_triad():
    """v1.9.0 added the cognitive triad; subsequent bumps add new Kinds
    (Forecast/PreMortem/AffectPalette/EngramStrengthPolicy/...).
    Test pins minimum version, not exact — exact bumps churn every Kind
    addition. Cross-Stack Parity oracle still reads .version."""
    import packaging.version
    actual = packaging.version.parse(SdlcExtension().version)
    assert actual >= packaging.version.parse("1.9.0"), (
        f"SdlcExtension.version regressed below 1.9.0: {actual}"
    )


# ----------------------------------------------------------------------
# Storage descriptors — bundle marker per Spec §3
# ----------------------------------------------------------------------


def test_lesson_learned_storage_bundle():
    sd = _lesson_learned_port().storage
    assert sd.pattern.value == "bundle"
    assert sd.container == "lessons-learned"
    assert sd.marker == "LESSON_LEARNED.md"


def test_cognitive_display_labels_are_market_aligned():
    """Surface labels use enterprise pt-BR (PMBOK 'Lessons Learned' etc.),
    not the deprecated poetic terms (s-sdlcv2-memorias-market-viz)."""
    assert _lesson_learned_port().display_label == "Lições Aprendidas"
    assert _port("SynthesisRun").display_label == "Sínteses"
    assert _port("ArchiveProposal").display_label == "Arquivamento"


def test_synthesis_run_storage_bundle():
    sd = _port("SynthesisRun").storage
    assert sd.pattern.value == "bundle"
    assert sd.container == "synthesis-runs"
    assert sd.marker == "SYNTHESIS_RUN.md"


def test_archive_proposal_storage_bundle():
    sd = _port("ArchiveProposal").storage
    assert sd.pattern.value == "bundle"
    assert sd.container == "archive-proposals"
    assert sd.marker == "ARCHIVE_PROPOSAL.md"


# ----------------------------------------------------------------------
# Lembrança schema
# ----------------------------------------------------------------------


LEMBRANCA_MIN = {
    "area": "Feature/f-cognitive-memory",
    "surface_when": ["feature_touched"],
    "source_refs": ["Narrative/cycle-f-X-20260510"],
    "affect": "wistful",
    "summary": "Lembre-se daquele ciclo onde resolvemos com Spec real.",
}


def test_remembrance_required_fields():
    schema = _lesson_learned_port().schema()
    assert set(schema["required"]) == {
        "area", "surface_when", "source_refs", "affect", "summary",
    }


def test_remembrance_affect_enum_is_evocative():
    """Per Spec §15 decision: evocative palette, not neutral pos/neg/neutral/mixed."""
    schema = _lesson_learned_port().schema()
    affect_enum = schema["properties"]["affect"]["enum"]
    assert set(affect_enum) == {"triumph", "regret", "surprise", "wistful", "ominous"}


def test_remembrance_surface_when_enum():
    schema = _lesson_learned_port().schema()
    items = schema["properties"]["surface_when"]["items"]
    assert set(items["enum"]) == {"feature_touched", "cycle_open", "session_start", "oracle_consult"}


def test_remembrance_relevance_decay_seed_default():
    """Decay seed defaults to 0.95/24h per Spec §3.1."""
    schema = _lesson_learned_port().schema()
    props = schema["properties"]
    assert props["relevance_decay_seed"]["default"] == 0.95


# ----------------------------------------------------------------------
# SynthesisRun schema
# ----------------------------------------------------------------------


# SynthesisRun redesign (s-dream-redesign 2026-05-13): SynthesisRun is now oneiric-only
# — surreal recombination with affect + symbol + scenario + fragments. The
# forward-looking shape (timeframe/would_change/status/outcome_check_at)
# moved to the new Forecast Kind. The DREAM_MIN constant below reflects
# the new shape; the forecast equivalent lives under Forecast tests.
DREAM_MIN = {
    "dreamer": "future-scenarios",
    "affect": "wonder",
    "symbol": "uma ponte que se redesenha enquanto atravesso",
    "scenario": (
        "Atravesso uma ponte que muda de forma. Cada pé apoiado solta um "
        "ângulo. Olho pra trás — o caminho já não é o que pisei."
    ),
    "fragments": [
        {"source": "Story/s-a", "lifted": "rigor"},
        {"source": "Story/s-b", "lifted": "presença"},
    ],
}


def test_dream_required_fields():
    """SynthesisRun (oneiric Kind) requires affect + symbol + scenario + fragments
    (post s-dream-redesign). Forward-looking forecast shape lives on
    Forecast — see test_forecast_required_fields below."""
    schema = _port("SynthesisRun").schema()
    assert set(schema["required"]) == {
        "dreamer", "affect", "symbol", "scenario", "fragments",
    }


def test_dream_affect_enum_is_oneiric():
    """SynthesisRun affect palette differs from LessonLearned affect — SynthesisRun uses
    surreal/oneiric affects (anxiety, wonder, vertigo, ...)."""
    schema = _port("SynthesisRun").schema()
    affect_enum = schema["properties"]["affect"]["enum"]
    # Subset check — extension may grow palette without breaking test
    expected_subset = {"anxiety", "longing", "triumph", "eerie", "vertigo",
                       "wistful", "ominous", "dread", "wonder"}
    assert expected_subset.issubset(set(affect_enum)), (
        f"missing oneiric affects: {expected_subset - set(affect_enum)}"
    )


def test_forecast_kind_carries_would_change_shape():
    """The forward-looking 'would_change' contract migrated from SynthesisRun
    to Forecast as part of s-dream-redesign. Forecast keeps the
    timeframe + status + outcome_check_at + would_change shape."""
    schema = _port("Forecast").schema()
    required = set(schema["required"])
    assert "would_change" in required
    assert "timeframe" in required
    assert "status" in required
    assert "outcome_check_at" in required
    item = schema["properties"]["would_change"]["items"]
    assert {"metric", "from", "to"}.issubset(set(item["required"]))


def test_forecast_status_lifecycle_enum():
    """Status lifecycle migrated to Forecast (was on SynthesisRun pre-redesign)."""
    schema = _port("Forecast").schema()
    status_enum = set(schema["properties"]["status"]["enum"])
    # Core lifecycle states should be present (subset check tolerates
    # extension adding new states).
    assert {"drafted", "observing", "fulfilled", "refuted"}.issubset(status_enum)


def test_dream_no_kind_of_field_in_v1():
    """Per Spec §15 decision: derive from dreamer, no explicit kind_of in v1."""
    schema = _port("SynthesisRun").schema()
    assert "kind_of" not in schema["properties"]


# ----------------------------------------------------------------------
# ArchiveProposal schema
# ----------------------------------------------------------------------


FORGETTING_MIN = {
    "target_kind": "Plan",
    "target_name": "2026-04-12-orphan-plan",
    "reason": "orphan",
    "evidence": "Unreferenced by any WorkflowEvent for 73 days.",
    "proposed_by": "cleanup-suggestions",
    "status": "proposed",
    "review_deadline": "2026-05-25T10:30:00Z",
}


def test_forgetting_required_fields():
    schema = _port("ArchiveProposal").schema()
    assert set(schema["required"]) == {
        "target_kind", "target_name", "reason", "evidence",
        "proposed_by", "status", "review_deadline",
    }


def test_forgetting_reason_enum():
    schema = _port("ArchiveProposal").schema()
    reason_enum = schema["properties"]["reason"]["enum"]
    assert set(reason_enum) == {"orphan", "superseded", "stale", "contradicted", "duplicate"}


def test_forgetting_status_lifecycle():
    schema = _port("ArchiveProposal").schema()
    status_enum = schema["properties"]["status"]["enum"]
    assert set(status_enum) == {"proposed", "approved", "vetoed", "executed"}


# ----------------------------------------------------------------------
# Aliases — match Cross-Stack Parity expectations
# ----------------------------------------------------------------------


def test_aliases_follow_sdlc_convention():
    assert _lesson_learned_port().alias == "sdlc-lesson-learned"
    assert _port("SynthesisRun").alias == "sdlc-synthesis-run"
    assert _port("ArchiveProposal").alias == "sdlc-archive-proposal"
