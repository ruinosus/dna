"""SynthesisRun structured output schema — S5 of dream-engines-v2.

Verifies 6 new optional fields on SynthesisRunKind.spec:
  insight_candidates, belief_updates, skill_candidates,
  contradictions, confidence, lens, source_event_ids

Back-compat constraint: legacy dreams (only the 5 original required
fields) MUST still validate.
"""
from __future__ import annotations
import pytest
import jsonschema
from dna.extensions.sdlc import SdlcExtension
from dna.kernel import Kernel


@pytest.fixture
def schema():
    # F3 lote-2: SynthesisRunKind class deleted — the port is synthesized
    # from kinds/synthesis-run.kind.yaml (same registration funnel).
    k = Kernel()
    k.load(SdlcExtension())
    return k.kind_port_for("SynthesisRun").schema()


@pytest.fixture
def legacy_dream(schema):
    """A dream with only the 5 original required fields."""
    affects = schema["properties"]["affect"]["enum"]
    return {
        "dreamer": "oneiric-scribe",
        "affect": affects[0],
        "symbol": "Um arquivo se abre e a página dentro está em branco.",
        "scenario": "A funcionária abre o arquivo. Vê branco. Hesita.",
        "fragments": [
            {"source": "LessonLearned/rem-x"},
            {"source": "Story/s-y"},
        ],
    }


def test_legacy_dream_still_validates(schema, legacy_dream):
    """Back-compat: pre-S5 dreams must validate as-is."""
    jsonschema.validate(legacy_dream, schema)


def test_full_v2_dream_validates(schema, legacy_dream):
    """A dream emitted by hybrid-topn engine with all 7 new fields
    populates correctly."""
    full = {
        **legacy_dream,
        "owner": "scribe-engram",
        "lens": "hindsight-cf",
        "confidence": 0.72,
        "source_event_ids": ["LessonLearned/rem-x", "Story/s-y"],
        "insight_candidates": [
            {
                "claim": "Briefs sem audience_context produzem outputs vagos.",
                "evidence": ["LessonLearned/rem-x"],
                "confidence": 0.8,
                "speculation": False,
            },
        ],
        "belief_updates": [
            {
                "target_ref": "LessonLearned/rem-x",
                "before": "Brief com 3 perguntas basta.",
                "after": "Brief precisa de audience_context explícito.",
                "reason": "Vimos 4 outputs vagos no ciclo do rem-x.",
                "confidence": 0.7,
            },
        ],
        "skill_candidates": [
            {
                "name": "check-audience-context-before-render",
                "applies_when": "rendering ResearchBrief prompt",
                "script": "if not spec.audience_context: warn user",
                "prerequisites": [],
            },
        ],
        "contradictions": [
            {
                "conflict": "rem-x diz briefs longos > curtos; rem-y diz curtos > longos.",
                "refs": ["LessonLearned/rem-x", "LessonLearned/rem-y"],
                "resolution_options": ["contexto-dependente", "merge"],
            },
        ],
    }
    jsonschema.validate(full, schema)


def test_confidence_out_of_range_rejected(schema, legacy_dream):
    """confidence must be 0.0-1.0."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**legacy_dream, "confidence": 1.5}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**legacy_dream, "confidence": -0.1}, schema)


def test_insight_candidate_requires_evidence(schema, legacy_dream):
    """Insights must have ≥1 evidence ref (provenance contract)."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**legacy_dream, "insight_candidates": [{"claim": "x", "evidence": []}]},
            schema,
        )
    # Missing evidence key entirely
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**legacy_dream, "insight_candidates": [{"claim": "x"}]},
            schema,
        )


def test_belief_update_requires_before_after_reason(schema, legacy_dream):
    """belief_updates needs the trio (before, after, reason)."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**legacy_dream, "belief_updates": [{"before": "x", "after": "y"}]},
            schema,
        )


def test_skill_candidate_requires_name_and_trigger(schema, legacy_dream):
    """Skills need (name, applies_when)."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**legacy_dream, "skill_candidates": [{"name": "x"}]},
            schema,
        )


# NOTE (F3 lote-2, 2026-06-11): the two to_card tests that lived here were
# removed with the SynthesisRunKind class — to_card was dead code (zero
# production consumers; documented delta in
# test_lote2_descriptor_equivalence.py). The curated descriptor `summary:`
# carries lens/confidence; the DERIVED counts (insight_count/belief_count/
# skill_count) died with the card.
