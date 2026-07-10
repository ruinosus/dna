"""`dna eval` — local offline eval runner CLI (s-dna-eval-kit).

End-to-end against a temp filesystem source (CliRunner, no network, no
LLM): run (exit codes), --save persistence, pin, --baseline compare
(regression gate semantics — pre-existing failures don't re-fail, a
fresh regression does), list/show, and the didactic error paths.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from dna_cli import main

_GENOME = """apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata: { name: playground }
spec: { default_agent: greeter }
"""

_AGENT = """apiVersion: github.com/ruinosus/dna/v1
kind: Agent
metadata: { name: greeter }
spec:
  instruction: |
    You are Helio, a friendly assistant.
"""

_CASE_OK = """apiVersion: github.com/ruinosus/dna/eval/v1
kind: EvalCase
metadata: { name: identity }
spec:
  description: identity composes
  checks:
  - { type: contains, value: Helio }
"""

_CASE_BAD = """apiVersion: github.com/ruinosus/dna/eval/v1
kind: EvalCase
metadata: { name: impossible }
spec:
  description: deliberately failing
  checks:
  - { type: contains, value: Zeus }
"""

_SUITE = """apiVersion: github.com/ruinosus/dna/eval/v1
kind: EvalSuite
metadata: { name: main }
spec:
  description: fixture suite
  cases: [identity, impossible]
  target: { type: prompt, agent: greeter }
"""

_SUITE_GREEN = """apiVersion: github.com/ruinosus/dna/eval/v1
kind: EvalSuite
metadata: { name: green }
spec:
  cases: [identity]
  target: { type: prompt, agent: greeter }
"""


def _env(tmp_path: Path, monkeypatch) -> tuple[CliRunner, Path]:
    base = tmp_path / ".dna"
    scope = base / "playground"
    (scope / "agents").mkdir(parents=True)
    (scope / "eval-cases").mkdir()
    (scope / "eval-suites").mkdir()
    (scope / "Genome.yaml").write_text(_GENOME, encoding="utf-8")
    (scope / "agents" / "greeter.yaml").write_text(_AGENT, encoding="utf-8")
    (scope / "eval-cases" / "identity.yaml").write_text(_CASE_OK, encoding="utf-8")
    (scope / "eval-cases" / "impossible.yaml").write_text(_CASE_BAD, encoding="utf-8")
    (scope / "eval-suites" / "main.yaml").write_text(_SUITE, encoding="utf-8")
    (scope / "eval-suites" / "green.yaml").write_text(_SUITE_GREEN, encoding="utf-8")
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_TENANT", raising=False)
    return CliRunner(), base


def _eval(runner, *args):
    return runner.invoke(main, ["eval", *args, "--scope", "playground"])


# ─── run ──────────────────────────────────────────────────────────────


def test_run_green_suite_exit_zero(tmp_path, monkeypatch):
    runner, _ = _env(tmp_path, monkeypatch)
    res = _eval(runner, "run", "green")
    assert res.exit_code == 0, res.output
    assert "identity" in res.output
    assert "1 passed" in res.output


def test_run_failing_suite_exit_one_with_detail(tmp_path, monkeypatch):
    runner, _ = _env(tmp_path, monkeypatch)
    res = _eval(runner, "run", "main")
    assert res.exit_code == 1
    assert "impossible" in res.output
    assert "Zeus" in res.output  # failed check detail is didactic


def test_run_missing_suite_fails_didactically(tmp_path, monkeypatch):
    runner, _ = _env(tmp_path, monkeypatch)
    res = _eval(runner, "run", "no-such-suite")
    assert res.exit_code == 1
    assert "no-such-suite" in res.output


def test_run_save_persists_eval_run(tmp_path, monkeypatch):
    runner, base = _env(tmp_path, monkeypatch)
    res = _eval(runner, "run", "green", "--save", "--json")
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["saved"] is True
    name = payload["run"]["metadata"]["name"]
    run_file = base / "playground" / "eval-runs" / f"{name}.yaml"
    assert run_file.exists(), "EvalRun must persist under <scope>/eval-runs/"
    raw = yaml.safe_load(run_file.read_text(encoding="utf-8"))
    assert raw["spec"]["passed"] == 1


def test_run_json_shape(tmp_path, monkeypatch):
    runner, _ = _env(tmp_path, monkeypatch)
    res = _eval(runner, "run", "main", "--json")
    assert res.exit_code == 1  # still fails the shell — CI-friendly
    payload = json.loads(res.output)
    statuses = {r["case"]: r["status"] for r in payload["run"]["spec"]["results"]}
    assert statuses == {"identity": "passed", "impossible": "failed"}


# ─── pin + baseline compare ───────────────────────────────────────────


def _save_and_pin(runner, suite="main"):
    res = _eval(runner, "run", suite, "--save", "--json")
    name = json.loads(res.output)["run"]["metadata"]["name"]
    res = _eval(runner, "pin", name)
    assert res.exit_code == 0, res.output
    return name


def test_pin_creates_baseline_doc(tmp_path, monkeypatch):
    runner, base = _env(tmp_path, monkeypatch)
    run_name = _save_and_pin(runner)
    baseline_file = base / "playground" / "eval-baselines" / "baseline-main.yaml"
    assert baseline_file.exists()
    raw = yaml.safe_load(baseline_file.read_text(encoding="utf-8"))
    assert raw["spec"] == {
        "suite": "main",
        "run_name": run_name,
        "pinned_at": raw["spec"]["pinned_at"],
    }


def test_pin_missing_run_fails(tmp_path, monkeypatch):
    runner, _ = _env(tmp_path, monkeypatch)
    res = _eval(runner, "pin", "run-ghost")
    assert res.exit_code == 1
    assert "--save" in res.output  # tells the user how to get a run


def test_baseline_gate_ignores_preexisting_failure(tmp_path, monkeypatch):
    """`main` has a pre-existing failure (impossible). Against a baseline
    that already failed it, the re-run is NOT a regression — exit 0."""
    runner, _ = _env(tmp_path, monkeypatch)
    _save_and_pin(runner)
    res = _eval(runner, "run", "main", "--baseline", "baseline-main")
    assert res.exit_code == 0, res.output
    assert "0 regression(s)" in res.output


def test_baseline_gate_catches_regression(tmp_path, monkeypatch):
    """Break the agent config after pinning: the previously-passing case
    now fails → regression → exit 1."""
    runner, base = _env(tmp_path, monkeypatch)
    _save_and_pin(runner)
    agent = base / "playground" / "agents" / "greeter.yaml"
    agent.write_text(_AGENT.replace("Helio", "Anonymous"), encoding="utf-8")
    res = _eval(runner, "run", "main", "--baseline", "baseline-main")
    assert res.exit_code == 1
    assert "REGRESSION: identity" in res.output


def test_baseline_missing_fails_didactically(tmp_path, monkeypatch):
    runner, _ = _env(tmp_path, monkeypatch)
    res = _eval(runner, "run", "main", "--baseline", "nope")
    assert res.exit_code == 1
    assert "dna eval pin" in res.output


# ─── list / show ──────────────────────────────────────────────────────


def test_list_shows_suites_runs_baselines(tmp_path, monkeypatch):
    runner, _ = _env(tmp_path, monkeypatch)
    _save_and_pin(runner)
    res = _eval(runner, "list")
    assert res.exit_code == 0, res.output
    assert "main" in res.output
    assert "baseline-main" in res.output
    payload = json.loads(_eval(runner, "list", "--json").output)
    assert {s["name"] for s in payload["suites"]} == {"main", "green"}
    assert len(payload["runs"]) == 1
    assert payload["baselines"][0]["suite"] == "main"


def test_show_run_detail(tmp_path, monkeypatch):
    runner, _ = _env(tmp_path, monkeypatch)
    run_name = _save_and_pin(runner)
    res = _eval(runner, "show", run_name)
    assert res.exit_code == 0, res.output
    assert "impossible" in res.output and "identity" in res.output


def test_show_missing_run_fails(tmp_path, monkeypatch):
    runner, _ = _env(tmp_path, monkeypatch)
    res = _eval(runner, "show", "run-ghost")
    assert res.exit_code == 1
    assert "run-ghost" in res.output
