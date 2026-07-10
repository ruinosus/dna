"""Local eval runner (s-dna-eval-kit) — deterministic, offline, pure.

The DEFAULT target is the kernel itself: ``target: {type: prompt, agent}``
composes ``build_prompt`` and the checks judge the composed prompt — a
real evaluation of declarative config with zero LLM. Custom targets are
the host's (EvalTargetPort), same declare/execute split as Automation.

Covers: the check engine (all 7 types + case-sensitivity + unknown-type
defense), suite execution (pass/fail/skip/error rows, counts, empty
``cases`` = every case, stop_on_fail, missing case/suite), the custom
target extension point, EvalRun schema-validity + persistence round-trip,
and compare() regression semantics.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.eval import apply_checks, compare, run_suite
from dna.kernel import Kernel

_API = "github.com/ruinosus/dna/eval/v1"
_SCOPE = "eval-fixture"


# --- check engine --------------------------------------------------------------


@pytest.mark.parametrize("check,expected", [
    ({"type": "contains", "value": "Helio"}, True),
    ({"type": "contains", "value": "Zeus"}, False),
    ({"type": "contains", "value": "helio", "case_sensitive": False}, True),
    ({"type": "not_contains", "value": "Zeus"}, True),
    ({"type": "not_contains", "value": "Helio"}, False),
    ({"type": "regex", "value": r"friendly \w+"}, True),
    ({"type": "regex", "value": r"^Zeus"}, False),
    ({"type": "not_regex", "value": r"^Zeus"}, True),
    ({"type": "not_regex", "value": r"Helio"}, False),
    ({"type": "equals", "value": "You are Helio, a friendly assistant."}, True),
    ({"type": "equals", "value": "you are helio, a friendly assistant.",
      "case_sensitive": False}, True),
    ({"type": "equals", "value": "Something else"}, False),
    ({"type": "min_length", "value": 10}, True),
    ({"type": "min_length", "value": 10_000}, False),
    ({"type": "max_length", "value": 10_000}, True),
    ({"type": "max_length", "value": 10}, False),
])
def test_apply_checks_types(check, expected):
    text = "You are Helio, a friendly assistant."
    [row] = apply_checks(text, [check])
    assert row["passed"] is expected
    if not expected:
        assert row["detail"], "failed checks carry a human-readable detail"


def test_apply_checks_unknown_type_fails_loudly():
    [row] = apply_checks("text", [{"type": "llm_judge", "value": "x"}])
    assert row["passed"] is False
    assert "unknown check type" in row["detail"]


# --- fixture scope --------------------------------------------------------------


def _write(path: Path, raw: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def _case(name: str, spec: dict) -> dict:
    return {"apiVersion": _API, "kind": "EvalCase",
            "metadata": {"name": name}, "spec": spec}


def _suite(name: str, spec: dict) -> dict:
    return {"apiVersion": _API, "kind": "EvalSuite",
            "metadata": {"name": name}, "spec": spec}


@pytest.fixture()
def scope_dir(tmp_path: Path) -> Path:
    base = tmp_path / ".dna"
    root = base / _SCOPE
    _write(root / "Genome.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": _SCOPE},
        "spec": {"default_agent": "greeter"},
    })
    _write(root / "agents" / "greeter.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "greeter"},
        "spec": {"instruction": "You are Helio, a friendly assistant.\n"},
    })
    _write(root / "eval-cases" / "identity.yaml", _case("identity", {
        "description": "identity composes",
        "checks": [{"type": "contains", "value": "Helio"}],
    }))
    _write(root / "eval-cases" / "impossible.yaml", _case("impossible", {
        "description": "deliberately failing",
        "checks": [{"type": "contains", "value": "Zeus"},
                   {"type": "min_length", "value": 5}],
    }))
    _write(root / "eval-cases" / "later.yaml", _case("later", {
        "skip": True,
        "skip_reason": "not yet",
        "checks": [{"type": "contains", "value": "anything"}],
    }))
    _write(root / "eval-suites" / "main.yaml", _suite("main", {
        "description": "fixture suite",
        "cases": ["identity", "impossible", "later"],
        "target": {"type": "prompt", "agent": "greeter"},
    }))
    return base


@pytest.fixture()
def kernel(scope_dir: Path) -> Kernel:
    k = Kernel.auto()
    src = FilesystemWritableSource(
        str(scope_dir),
        writers=list(getattr(k, "active_writers", []) or []),
        kernel=k,
    )
    k.source(src)
    k.cache(FilesystemCache(str(scope_dir)))
    return k


# --- run_suite -----------------------------------------------------------------


def test_run_suite_statuses_and_counts(kernel):
    raw = run_suite(kernel, _SCOPE, "main")
    spec = raw["spec"]
    assert raw["kind"] == "EvalRun" and raw["apiVersion"] == _API
    assert raw["metadata"]["name"].startswith("run-main-")
    assert spec["suite"] == "main"
    assert (spec["total"], spec["passed"], spec["failed"],
            spec["errored"], spec["skipped"]) == (3, 1, 1, 0, 1)
    by_case = {r["case"]: r for r in spec["results"]}
    assert by_case["identity"]["status"] == "passed"
    assert by_case["identity"]["output_excerpt"].startswith("You are Helio")
    assert by_case["impossible"]["status"] == "failed"
    failed_checks = [c for c in by_case["impossible"]["checks"] if not c["passed"]]
    assert failed_checks and "Zeus" in failed_checks[0]["detail"]
    assert by_case["later"]["status"] == "skipped"


def test_run_doc_is_schema_valid_and_persists(kernel):
    """The runner's output validates against the EvalRun descriptor schema
    and round-trips through write_document → query."""
    raw = run_suite(kernel, _SCOPE, "main", run_name="run-main-pinned")
    port = kernel._kinds[(_API, "EvalRun")]
    validated = port.parse(raw)  # schema-validating parse — raises on drift
    assert validated["spec"]["total"] == 3

    import asyncio
    asyncio.run(kernel.write_document(_SCOPE, "EvalRun", "run-main-pinned", raw))
    rows = kernel.query_list_sync(_SCOPE, "EvalRun")
    assert any(getattr(r, "name", None) == "run-main-pinned" for r in rows)


def test_empty_cases_runs_every_case_sorted(kernel, scope_dir):
    _write(scope_dir / _SCOPE / "eval-suites" / "all.yaml",
           _suite("all", {"target": {"type": "prompt", "agent": "greeter"}}))
    raw = run_suite(kernel, _SCOPE, "all")
    assert [r["case"] for r in raw["spec"]["results"]] == [
        "identity", "impossible", "later",
    ]


def test_stop_on_fail(kernel, scope_dir):
    _write(scope_dir / _SCOPE / "eval-suites" / "gate.yaml", _suite("gate", {
        "cases": ["impossible", "identity"],
        "target": {"type": "prompt", "agent": "greeter"},
        "stop_on_fail": True,
    }))
    raw = run_suite(kernel, _SCOPE, "gate")
    assert [r["case"] for r in raw["spec"]["results"]] == ["impossible"]


def test_missing_case_is_error_row(kernel, scope_dir):
    _write(scope_dir / _SCOPE / "eval-suites" / "ghost.yaml", _suite("ghost", {
        "cases": ["identity", "no-such-case"],
        "target": {"type": "prompt", "agent": "greeter"},
    }))
    raw = run_suite(kernel, _SCOPE, "ghost")
    by_case = {r["case"]: r for r in raw["spec"]["results"]}
    assert by_case["no-such-case"]["status"] == "error"
    assert "not found" in by_case["no-such-case"]["error"]
    assert raw["spec"]["errored"] == 1


def test_missing_suite_raises(kernel):
    with pytest.raises(ValueError, match="no-such-suite"):
        run_suite(kernel, _SCOPE, "no-such-suite")


def test_unknown_target_type_is_error_never_silent_pass(kernel, scope_dir):
    _write(scope_dir / _SCOPE / "eval-cases" / "llm-case.yaml", _case("llm-case", {
        "target": {"type": "llm"},
        "checks": [{"type": "contains", "value": "x"}],
    }))
    _write(scope_dir / _SCOPE / "eval-suites" / "llm.yaml",
           _suite("llm", {"cases": ["llm-case"]}))
    raw = run_suite(kernel, _SCOPE, "llm")
    [row] = raw["spec"]["results"]
    assert row["status"] == "error"
    assert "EvalTargetPort" in row["error"]


def test_custom_target_port_extension_point(kernel, scope_dir):
    """The LLM extension point: the host registers a target and the runner
    dispatches to it — the SDK never executes anything itself."""
    _write(scope_dir / _SCOPE / "eval-cases" / "echo-case.yaml", _case("echo-case", {
        "target": {"type": "echo"},
        "input": "ping",
        "checks": [{"type": "equals", "value": "echo: ping"}],
    }))
    _write(scope_dir / _SCOPE / "eval-suites" / "echo.yaml",
           _suite("echo", {"cases": ["echo-case"]}))

    class EchoTarget:
        def run(self, target, case, *, kernel, scope):
            return f"echo: {case.get('input', '')}"

    raw = run_suite(kernel, _SCOPE, "echo", targets={"echo": EchoTarget()})
    [row] = raw["spec"]["results"]
    assert row["status"] == "passed"
    assert row["target_type"] == "echo"


def test_target_exception_is_error_row(kernel, scope_dir):
    _write(scope_dir / _SCOPE / "eval-cases" / "boom-case.yaml", _case("boom-case", {
        "target": {"type": "boom"},
        "checks": [{"type": "contains", "value": "x"}],
    }))
    _write(scope_dir / _SCOPE / "eval-suites" / "boom.yaml",
           _suite("boom", {"cases": ["boom-case"]}))

    class BoomTarget:
        def run(self, target, case, *, kernel, scope):
            raise RuntimeError("kaput")

    raw = run_suite(kernel, _SCOPE, "boom", targets={"boom": BoomTarget()})
    [row] = raw["spec"]["results"]
    assert row["status"] == "error"
    assert "kaput" in row["error"]


# --- compare -------------------------------------------------------------------


def _run_spec(**statuses: str) -> dict:
    return {"results": [{"case": c, "status": s} for c, s in statuses.items()]}


def test_compare_regressions_improvements_unchanged():
    baseline = _run_spec(a="passed", b="failed", c="passed", d="passed")
    current = _run_spec(a="failed", b="passed", c="passed", d="error")
    diff = compare(current, baseline)
    assert diff["regressions"] == ["a", "d"]
    assert diff["improvements"] == ["b"]
    assert diff["unchanged"] == ["c"]
    assert diff["has_regressions"] is True


def test_compare_added_removed_and_skips_excluded():
    baseline = _run_spec(a="passed", gone="passed", was_skipped="skipped")
    current = _run_spec(a="passed", new="failed", now_skipped="skipped")
    diff = compare(current, baseline)
    assert diff["added"] == ["new"]
    # skipped rows are absent on their side: was_skipped never lands in
    # removed, now_skipped never lands in added
    assert diff["removed"] == ["gone"]
    assert diff["has_regressions"] is False


def test_compare_skip_now_is_not_a_regression():
    baseline = _run_spec(a="passed")
    current = _run_spec(a="skipped")
    diff = compare(current, baseline)
    assert diff["regressions"] == []
    assert diff["removed"] == ["a"]
