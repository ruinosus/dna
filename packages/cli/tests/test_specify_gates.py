"""The spec-kit methodology-gate profile (s-spec-kit-journey-wiring, ADR §8.3).

spec-kit joins superpowers as an artifact-gated methodology: leaving the
specify/plan phase requires the run's spec.md/plan.md to exist on disk.
"""
from __future__ import annotations

from dna_cli._methodology_gates import GateResult, plan_gate, spec_gate


def test_spec_gate_speckit_requires_existing_artifact(tmp_path):
    spec_md = tmp_path / "spec.md"
    spec_md.write_text("# spec")
    assert spec_gate(methodology="spec-kit", phase="specify", artifact=str(spec_md)) is GateResult.PASS


def test_spec_gate_speckit_missing_artifact_fails(tmp_path):
    assert spec_gate(methodology="spec-kit", phase="specify", artifact=None) is GateResult.FAIL
    assert spec_gate(methodology="spec-kit", phase="specify",
                     artifact=str(tmp_path / "nope.md")) is GateResult.FAIL


def test_spec_gate_other_methodology_skips():
    assert spec_gate(methodology="ad-hoc", phase="specify", artifact=None) is GateResult.SKIP


def test_plan_gate_speckit_requires_plan_or_stub(tmp_path):
    plan_md = tmp_path / "plan.md"
    plan_md.write_text("# plan")
    assert plan_gate(methodology="spec-kit", phase="plan",
                     artifact=str(plan_md), auto_stub=False) is GateResult.PASS
    assert plan_gate(methodology="spec-kit", phase="plan",
                     artifact=None, auto_stub=True) is GateResult.PASS
    assert plan_gate(methodology="spec-kit", phase="plan",
                     artifact=None, auto_stub=False) is GateResult.FAIL


def test_superpowers_still_gated(tmp_path):
    # Regression: the original methodology keeps its behavior.
    assert spec_gate(methodology="superpowers", phase="specify", artifact=None) is GateResult.FAIL
