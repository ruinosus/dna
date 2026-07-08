"""Round-trip tests for ml-privacy-filter SafetyPolicySpec fields (Phase 7 T5)."""
from __future__ import annotations

from dna.kernel.models import SafetyPolicySpec, TypedSafetyPolicy


def test_ml_privacy_filter_engine_round_trips() -> None:
    """Phase 7 — engine=ml-privacy-filter + new fields parse cleanly."""
    raw = {
        "kind": "SafetyPolicy",
        "metadata": {"name": "pii-ml"},
        "spec": {
            "engine": "ml-privacy-filter",
            "model": "openai/privacy-filter",
            "backend": "auto",
            "threshold": 0.85,
            # T1 LOCKED category names — uses real entity_group values
            "categories": ["private_email", "private_phone"],
            "scope": "input",
            "action": "mask",
            "mask_char": "[PII]",
            "budget_ms": 1000,
        },
    }
    doc = TypedSafetyPolicy.from_raw(raw)
    assert doc.spec.engine == "ml-privacy-filter"
    assert doc.spec.model == "openai/privacy-filter"
    assert doc.spec.backend == "auto"
    assert doc.spec.threshold == 0.85
    assert doc.spec.categories == ["private_email", "private_phone"]
    assert doc.spec.scope == "input"
    assert doc.spec.action == "mask"
    assert doc.spec.mask_char == "[PII]"
    assert doc.spec.budget_ms == 1000.0


def test_ml_fields_default_to_presidio_engine() -> None:
    """Backward-compat: a spec without the new fields defaults to presidio."""
    spec = SafetyPolicySpec.from_raw({"scope": "both", "action": "mask"})
    assert spec.engine == "presidio"
    assert spec.model == "openai/privacy-filter"  # still default; only used when ml engine is selected
    assert spec.backend == "auto"
    assert spec.threshold == 0.8
    assert spec.categories is None
    assert spec.mask_char == "[REDACTED]"
    assert spec.budget_ms == 1000.0


def test_categories_explicit_none_preserved() -> None:
    """`categories: null` (None) is the documented "all 8" sentinel."""
    spec = SafetyPolicySpec.from_raw({"engine": "ml-privacy-filter", "categories": None})
    assert spec.categories is None


def test_threshold_coerces_int_to_float() -> None:
    """YAML may load `threshold: 1` as int — must coerce."""
    spec = SafetyPolicySpec.from_raw({"engine": "ml-privacy-filter", "threshold": 1})
    assert spec.threshold == 1.0
    assert isinstance(spec.threshold, float)
