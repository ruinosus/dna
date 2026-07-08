"""s-delegation-declarative — Agent.spec.delegation_target_for.

Schema tests for the declarative delegation-target opt-in block that
replaced the hardcoded DELEGATION_CATALOG in
dna_shared.manifest_tools.delegation_tools.
"""
from __future__ import annotations

import pytest

from dna.kernel.models import (
    DelegationTargetFor,
    AgentSpec,
)


def test_absent_field_parses_to_none():
    spec = AgentSpec.from_raw({"instruction": "hi"})
    assert spec.delegation_target_for is None


def test_full_block_round_trips():
    spec = AgentSpec.from_raw({
        "delegation_target_for": {
            "agents": ["jarvis"],
            "format": "slug",
            "typical_seconds": 10,
            "use_when": "elaborate HTML",
            "purpose": "Generate elaborate HTML mockups",
        },
    })
    decl = spec.delegation_target_for
    assert isinstance(decl, DelegationTargetFor)
    assert decl.agents == ["jarvis"]
    assert decl.format == "slug"
    assert decl.typical_seconds == 10
    assert decl.use_when == "elaborate HTML"
    assert decl.purpose == "Generate elaborate HTML mockups"


def test_defaults_minimal_block():
    decl = DelegationTargetFor.from_raw({"agents": ["*"]})
    assert decl.agents == ["*"]
    assert decl.format == "text"
    assert decl.typical_seconds is None
    assert decl.use_when is None
    assert decl.purpose is None


def test_invalid_format_raises():
    with pytest.raises(ValueError, match="delegation_target_for.format"):
        DelegationTargetFor.from_raw({"agents": ["jarvis"], "format": "xml"})


def test_non_dict_value_is_ignored():
    # authoring mistake (e.g. a bare list) must not crash parse — the
    # field simply doesn't activate.
    spec = AgentSpec.from_raw({"delegation_target_for": ["jarvis"]})
    assert spec.delegation_target_for is None
