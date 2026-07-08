"""F1 — Composition Engine V2 schema tests (Phase 17).

Story s-comp-f1-schema (2026-05-28).

Verifica:
1. Genome.spec.parent_scope parse OK + None default.
2. LayerPolicy.spec.composition_rules — per-Kind rules parse, normalize,
   default fields preenchidos.
3. Backward-compat: docs antigos (sem parent_scope / composition_rules)
   carregam clean.
"""
from __future__ import annotations

from dna.kernel.models import (
    CompositionRule,
    LayerPolicySpec,
    GenomeSpec,
)


# ---------- Genome.parent_scope -----------------------------------------


def test_package_parent_scope_present():
    s = GenomeSpec.from_raw({"parent_scope": "innovec-base"})
    assert s.parent_scope == "innovec-base"


def test_package_parent_scope_absent_defaults_to_none():
    s = GenomeSpec.from_raw({})
    assert s.parent_scope is None


def test_package_parent_scope_empty_string_treated_as_none():
    """Empty string → None (catches accidental ``parent_scope: ""``
    in YAML)."""
    s = GenomeSpec.from_raw({"parent_scope": ""})
    assert s.parent_scope is None


def test_package_parent_scope_with_other_fields():
    """parent_scope coexists with existing catalog identity fields."""
    s = GenomeSpec.from_raw({
        "parent_scope": "_lib",
        "owner_tenant": "acme",
        "visibility": "internal",
        "version": "1.2.3",
    })
    assert s.parent_scope == "_lib"
    assert s.owner_tenant == "acme"
    assert s.visibility == "internal"
    assert s.version == "1.2.3"


# ---------- LayerPolicy.composition_rules --------------------------------


def test_composition_rule_defaults():
    """All fields default sensibly when raw is empty."""
    r = CompositionRule.from_raw({})
    assert r.scope_inheritance == "enabled"
    assert r.merge_strategy == "override_full"
    assert r.tenant_overlay == "field_level"


def test_composition_rule_explicit_values():
    r = CompositionRule.from_raw({
        "scope_inheritance": "disabled",
        "merge_strategy": "field_level",
        "tenant_overlay": "none",
    })
    assert r.scope_inheritance == "disabled"
    assert r.merge_strategy == "field_level"
    assert r.tenant_overlay == "none"


def test_composition_rule_case_normalized():
    """Values lowercased on parse."""
    r = CompositionRule.from_raw({
        "scope_inheritance": "ENABLED",
        "merge_strategy": "Field_Level",
    })
    assert r.scope_inheritance == "enabled"
    assert r.merge_strategy == "field_level"


def test_layer_policy_composition_rules_per_kind():
    """Different Kinds get different rules — independent normalization."""
    s = LayerPolicySpec.from_raw({
        "layer_id": "composition",
        "composition_rules": {
            "Agent": {
                "scope_inheritance": "enabled",
                "merge_strategy": "field_level",
            },
            "LottieAsset": {
                "scope_inheritance": "enabled",
                "merge_strategy": "override_full",
                "tenant_overlay": "none",
            },
            "Story": {
                "scope_inheritance": "disabled",
            },
        },
    })
    assert set(s.composition_rules) == {"Agent", "LottieAsset", "Story"}

    ua = s.composition_rules["Agent"]
    assert ua.scope_inheritance == "enabled"
    assert ua.merge_strategy == "field_level"
    assert ua.tenant_overlay == "field_level"  # default

    lottie = s.composition_rules["LottieAsset"]
    assert lottie.merge_strategy == "override_full"
    assert lottie.tenant_overlay == "none"

    story = s.composition_rules["Story"]
    assert story.scope_inheritance == "disabled"
    # Even when inheritance is disabled, the other fields default.
    assert story.merge_strategy == "override_full"


def test_layer_policy_composition_rules_absent_defaults_empty():
    """Backward-compat: LayerPolicy without composition_rules parses
    clean with empty dict."""
    s = LayerPolicySpec.from_raw({"layer_id": "tenant"})
    assert s.composition_rules == {}


def test_layer_policy_composition_rules_ignores_invalid_kinds():
    """Non-string keys or non-dict values dropped silently."""
    s = LayerPolicySpec.from_raw({
        "composition_rules": {
            "Agent": {"scope_inheritance": "enabled"},
            123: {"scope_inheritance": "enabled"},  # invalid key
            "BadValue": "not-a-dict",                # invalid value
        },
    })
    assert list(s.composition_rules) == ["Agent"]


def test_layer_policy_policies_coexist_with_composition_rules():
    """Phase 16 policies dict + Phase 17 composition_rules side-by-side."""
    s = LayerPolicySpec.from_raw({
        "layer_id": "hybrid",
        "policies": {
            "helix-agent": "restricted",
        },
        "composition_rules": {
            "Agent": {"scope_inheritance": "enabled"},
        },
    })
    assert s.policies == {"helix-agent": "restricted"}
    assert "Agent" in s.composition_rules
