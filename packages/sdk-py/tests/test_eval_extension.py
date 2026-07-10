"""Eval Kinds (s-dna-eval-kit) — descriptor registration surface.

Tier B port from the internal SDK's eval extension: the AUTHORING
VOCABULARY travels (EvalCase target+checks, EvalSuite grouping, EvalRun
ledger, EvalBaseline pin); the upstream Temporal/LLM-judge runner does
not — the local runner lives in :mod:`dna.extensions.eval.runner` and is
covered by ``test_eval_runner.py``. These tests pin:

- all four Kinds register from builtin descriptors (F3 — record Kinds are
  data, not classes; the ratchet must not grow);
- identity: generated-convention aliases, record plane, yaml containers,
  permissive tenancy (undeclared — Evidence/Automation precedent);
- EvalSuite's ``cases`` dep_filter targets the EvalCase alias;
- schema enforcement at parse: strict top-level (additionalProperties
  false), required fields, the check-type enum.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel

_API = "github.com/ruinosus/dna/eval/v1"

_EXPECTED = {
    "EvalCase": ("eval-eval-case", "eval-cases"),
    "EvalSuite": ("eval-eval-suite", "eval-suites"),
    "EvalRun": ("eval-eval-run", "eval-runs"),
    "EvalBaseline": ("eval-eval-baseline", "eval-baselines"),
}


@pytest.fixture(scope="module")
def kernel() -> Kernel:
    return Kernel.auto()


@pytest.fixture(scope="module")
def ports(kernel) -> dict:
    out = {}
    for kind in _EXPECTED:
        port = kernel._kinds.get((_API, kind))
        assert port is not None, f"{kind} must register from the builtin descriptor"
        out[kind] = port
    return out


def test_identity_and_plane(ports):
    for kind, (alias, container) in _EXPECTED.items():
        port = ports[kind]
        assert port.alias == alias
        assert port.plane == "record"
        assert getattr(port, "__declarative__", False), (
            f"{kind} is a record Kind — descriptor, not class (F3 ratchet)"
        )
        assert getattr(port, "__builtin_descriptor__", False)
        assert port.is_prompt_target is False
        assert port.storage.container == container


def test_eval_run_is_runtime_artifact(ports):
    assert getattr(ports["EvalRun"], "is_runtime_artifact", False) is True
    # authored kinds are NOT runtime artifacts
    for kind in ("EvalCase", "EvalSuite", "EvalBaseline"):
        assert not getattr(ports[kind], "is_runtime_artifact", False)


def test_tenancy_permissive_undeclared(ports):
    """tenant_scope is intentionally NOT declared (permissive: base +
    per-tenant overlay) — the Evidence/Automation precedent."""
    from dna.kernel.protocols import TenantScope

    for kind, port in ports.items():
        declared = getattr(port, "scope", None)
        assert declared not in (TenantScope.TENANTED, TenantScope.GLOBAL), (
            f"{kind} must stay permissive (undeclared tenant_scope)"
        )


def test_suite_cases_dep_filter_targets_case_alias(ports):
    filters = ports["EvalSuite"].dep_filters() or {}
    assert filters.get("cases") == "eval-eval-case"


def test_strict_schemas(ports):
    for kind, port in ports.items():
        schema = port.schema() or {}
        assert schema.get("additionalProperties") is False, (
            f"{kind} ships strict — additionalProperties: false "
            f"(test_strict_schema_lint allowlist is shrink-only)"
        )


def _case_raw(spec: dict, name: str = "c1") -> dict:
    return {
        "apiVersion": _API,
        "kind": "EvalCase",
        "metadata": {"name": name},
        "spec": spec,
    }


def test_case_parse_valid(ports):
    # DeclarativeKindPort.parse is a schema-validating pass-through: it
    # returns the validated raw (the kernel wraps raw → Document).
    raw = ports["EvalCase"].parse(_case_raw({
        "description": "greeting present",
        "target": {"type": "prompt", "agent": "greeter"},
        "checks": [{"type": "contains", "value": "hello"}],
        "tags": ["smoke"],
    }))
    assert raw["metadata"]["name"] == "c1"
    assert raw["spec"]["checks"][0]["type"] == "contains"


def test_case_parse_rejects_unknown_check_type(ports):
    with pytest.raises(Exception, match="llm_judge"):
        ports["EvalCase"].parse(_case_raw({
            "checks": [{"type": "llm_judge", "value": "be nice"}],
        }))


def test_case_parse_rejects_missing_checks(ports):
    with pytest.raises(Exception):
        ports["EvalCase"].parse(_case_raw({"description": "no checks"}))


def test_case_parse_rejects_unknown_top_level_field(ports):
    with pytest.raises(Exception):
        ports["EvalCase"].parse(_case_raw({
            "checks": [{"type": "contains", "value": "x"}],
            "trajectory_mode": "strict",  # upstream field that did NOT travel
        }))


def test_run_parse_requires_counts_and_results(ports):
    with pytest.raises(Exception):
        ports["EvalRun"].parse({
            "apiVersion": _API,
            "kind": "EvalRun",
            "metadata": {"name": "r1"},
            "spec": {"suite": "s1"},
        })


def test_baseline_summary_projection(ports):
    from types import SimpleNamespace

    # summary() projects a doc OBJECT's spec (bare dicts are not Documents)
    doc = SimpleNamespace(spec={"suite": "s1", "run_name": "run-s1-1"})
    summary = ports["EvalBaseline"].summary(doc) or {}
    assert summary.get("suite") == "s1"
    assert summary.get("run_name") == "run-s1-1"
