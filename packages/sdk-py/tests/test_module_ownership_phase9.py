"""Phase 9 — TypedGenome.spec gains owner_tenant + visibility fields.

Pure schema tests — no adapter / kernel resolution involved. Those land
in Phase 9b/9c.
"""
from __future__ import annotations

from dna.kernel.models import GenomeSpec, TypedGenome


def test_module_spec_defaults_to_public_platform_owned():
    """Default state matches Phase 8 behavior — no migration needed."""
    spec = GenomeSpec.from_raw({})
    assert spec.owner_tenant is None
    assert spec.visibility == "public"


def test_module_spec_round_trip_owner_tenant():
    spec = GenomeSpec.from_raw({"owner_tenant": "acme", "visibility": "private"})
    assert spec.owner_tenant == "acme"
    assert spec.visibility == "private"


def test_module_spec_visibility_falsy_falls_to_public():
    """Empty string / null in YAML round-trips to the default 'public'.

    Reason: hand-written YAMLs can have ``visibility:`` (no value) which
    parses as None — that should mean 'I didn't set it', not 'invalid'.
    """
    spec = GenomeSpec.from_raw({"visibility": None})
    assert spec.visibility == "public"
    spec_empty = GenomeSpec.from_raw({"visibility": ""})
    assert spec_empty.visibility == "public"


def test_typed_module_from_raw_propagates_new_fields():
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": "screening-pro"},
        "spec": {
            "owner_tenant": "acme",
            "visibility": "private",
            "default_agent": "screener",
        },
    }
    typed = TypedGenome.from_raw(raw)
    assert typed.spec.owner_tenant == "acme"
    assert typed.spec.visibility == "private"
    assert typed.spec.default_agent == "screener"


def test_module_spec_legacy_yaml_unchanged():
    """A pre-Phase-9 manifest (no new fields) still parses cleanly."""
    raw = {
        "default_agent": "talent-screener",
        "default_llm": "openai:gpt-4o-mini",
        "owner": "dna-reference",
        "tags": ["hr", "recruiting"],
        "agents": ["talent-screener"],
    }
    spec = GenomeSpec.from_raw(raw)
    assert spec.owner_tenant is None
    assert spec.visibility == "public"
    # All legacy fields preserved
    assert spec.default_agent == "talent-screener"
    assert spec.owner == "dna-reference"
    assert "hr" in spec.tags
