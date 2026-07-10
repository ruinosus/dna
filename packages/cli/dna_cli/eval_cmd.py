"""``dna eval`` — run EvalSuites locally, offline, deterministically.

The runner is the SDK's pure library (``dna.extensions.eval.runner``):
the default target is the KERNEL ITSELF — a case with
``target: {type: prompt, agent: X}`` composes ``build_prompt(agent=X)``
and applies the case's checks (contains/regex/equals/length) to the
composed prompt. "Does my agent compose what I expect?" is a real
evaluation of declarative config, with zero LLM and zero network.
LLM/live targets are host-registered ``EvalTargetPort``s (see
docs/guides/evaluating-agents.md) — this CLI ships only the
deterministic built-in.

Commands:
    dna eval run <suite> [--scope] [--save] [--baseline <name>] [--json]
    dna eval list [--scope]                — suites + saved runs
    dna eval show <run> [--scope]          — one run, per-case detail
    dna eval pin <run> [--name] [--label]  — pin a run as the baseline

Exit codes (CI-friendly):
    ``run``                 → 1 when any case failed/errored
    ``run --baseline <b>``  → 1 when the run REGRESSES vs the baseline
                              (pre-existing failures don't re-fail CI)

Kernel-bound: boots a local kernel against ``DNA_SOURCE_URL`` /
``DNA_BASE_DIR`` (filesystem source, default ``./.dna``). No service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import click

from dna_cli._ctx import dna_session, fail, print_json, print_table

EVAL_API_VERSION = "github.com/ruinosus/dna/eval/v1"

_STATUS_GLYPH = {"passed": "✓", "failed": "✗", "error": "!", "skipped": "-"}


def _spec_of(doc: Any) -> dict:
    spec = getattr(doc, "spec", None)
    if not isinstance(spec, dict):
        spec = dict(spec) if spec else {}
    return spec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@click.group(name="eval")
def eval_() -> None:
    """Run EvalSuites locally (offline, deterministic) and compare runs
    against a pinned EvalBaseline."""


# ── run ─────────────────────────────────────────────────────────────────────


def _print_run(spec: dict) -> None:
    for r in spec.get("results") or []:
        glyph = _STATUS_GLYPH.get(str(r.get("status")), "?")
        line = f"  {glyph} {r.get('case')}  [{r.get('status')}]"
        click.echo(line)
        if r.get("status") == "failed":
            for c in r.get("checks") or []:
                if not c.get("passed"):
                    click.echo(f"      · {c.get('type')}: {c.get('detail', '')}")
        elif r.get("status") == "error":
            click.echo(f"      · {r.get('error', '')}")
    click.echo(
        f"{spec.get('passed', 0)} passed · {spec.get('failed', 0)} failed · "
        f"{spec.get('errored', 0)} errored · {spec.get('skipped', 0)} skipped "
        f"(total {spec.get('total', 0)})"
    )


@eval_.command("run")
@click.argument("suite")
@click.option("--scope", default=None, help="Scope to run in (default: resolved from the source).")
@click.option("--save", is_flag=True, help="Persist the result as an EvalRun document.")
@click.option("--baseline", default=None, metavar="NAME",
              help="Compare against the EvalBaseline document NAME; exit 1 on regressions.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def cmd_run(suite: str, scope: str | None, save: bool, baseline: str | None, as_json: bool):
    """Execute SUITE offline and report per-case results.

    Without ``--baseline`` the exit code reflects the run itself (1 when
    any case failed/errored). With ``--baseline`` it reflects the DIFF:
    only a regression (a case the baseline passed, now failing) exits 1.
    """
    from dna.extensions.eval import compare, run_suite

    with dna_session(scope) as s:
        try:
            raw = run_suite(s.kernel, s.scope, suite)
        except ValueError as exc:
            raise fail(str(exc))
        spec = raw["spec"]
        run_name = raw["metadata"]["name"]

        diff = None
        baseline_run = None
        if baseline:
            base_doc = s.get_doc("EvalBaseline", baseline)
            if base_doc is None:
                raise fail(
                    f"EvalBaseline '{baseline}' not found in scope '{s.scope}' "
                    f"— pin one with `dna eval pin <run>`."
                )
            baseline_run = str(_spec_of(base_doc).get("run_name") or "")
            base_run_doc = s.get_doc("EvalRun", baseline_run)
            if base_run_doc is None:
                raise fail(
                    f"EvalBaseline '{baseline}' points at EvalRun "
                    f"'{baseline_run}', which does not exist."
                )
            diff = compare(spec, _spec_of(base_run_doc))

        if save:
            s.run(s.kernel.write_document(s.scope, "EvalRun", run_name, raw))

        if as_json:
            payload: dict[str, Any] = {"run": raw, "saved": save}
            if diff is not None:
                payload["baseline"] = {"name": baseline, "run_name": baseline_run}
                payload["compare"] = diff
            print_json(payload)
        else:
            click.echo(f"suite: {suite} (scope {s.scope})")
            _print_run(spec)
            if save:
                click.echo(f"saved: EvalRun/{run_name}")
            if diff is not None:
                click.echo(
                    f"vs baseline {baseline} ({baseline_run}): "
                    f"{len(diff['regressions'])} regression(s) · "
                    f"{len(diff['improvements'])} improvement(s) · "
                    f"{len(diff['unchanged'])} unchanged"
                )
                for case in diff["regressions"]:
                    click.echo(f"  ✗ REGRESSION: {case}")
                for case in diff["improvements"]:
                    click.echo(f"  ✓ improved: {case}")

    if diff is not None:
        if diff["has_regressions"]:
            raise SystemExit(1)
    elif int(spec.get("failed", 0)) + int(spec.get("errored", 0)) > 0:
        raise SystemExit(1)


# ── list ────────────────────────────────────────────────────────────────────


@eval_.command("list")
@click.option("--scope", default=None, help="Scope to list (default: resolved from the source).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def cmd_list(scope: str | None, as_json: bool):
    """List EvalSuites, saved EvalRuns and pinned EvalBaselines."""
    with dna_session(scope) as s:
        suites = s.query_list("EvalSuite")
        runs = s.query_list("EvalRun")
        baselines = s.query_list("EvalBaseline")

        if as_json:
            print_json({
                "scope": s.scope,
                "suites": [
                    {"name": d.name, **{k: _spec_of(d).get(k) for k in ("description",)},
                     "cases": len(_spec_of(d).get("cases") or [])}
                    for d in suites
                ],
                "runs": [
                    {"name": d.name, "suite": _spec_of(d).get("suite"),
                     "passed": _spec_of(d).get("passed"), "failed": _spec_of(d).get("failed"),
                     "total": _spec_of(d).get("total"),
                     "finished_at": _spec_of(d).get("finished_at")}
                    for d in runs
                ],
                "baselines": [
                    {"name": d.name, "suite": _spec_of(d).get("suite"),
                     "run_name": _spec_of(d).get("run_name")}
                    for d in baselines
                ],
            })
            return

        click.echo(f"scope: {s.scope}")
        click.echo("\nsuites:")
        print_table(
            [{"name": d.name, "cases": len(_spec_of(d).get("cases") or []) or "all",
              "description": (_spec_of(d).get("description") or "")[:60]}
             for d in suites],
            ["name", "cases", "description"],
        )
        click.echo("\nruns:")
        print_table(
            [{"name": d.name, "suite": _spec_of(d).get("suite", ""),
              "result": f"{_spec_of(d).get('passed', 0)}/{_spec_of(d).get('total', 0)} passed",
              "finished_at": _spec_of(d).get("finished_at", "")}
             for d in runs],
            ["name", "suite", "result", "finished_at"],
        )
        click.echo("\nbaselines:")
        print_table(
            [{"name": d.name, "suite": _spec_of(d).get("suite", ""),
              "run_name": _spec_of(d).get("run_name", "")}
             for d in baselines],
            ["name", "suite", "run_name"],
        )


# ── show ────────────────────────────────────────────────────────────────────


@eval_.command("show")
@click.argument("run_name")
@click.option("--scope", default=None, help="Scope to read (default: resolved from the source).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def cmd_show(run_name: str, scope: str | None, as_json: bool):
    """Show one saved EvalRun with per-case detail."""
    with dna_session(scope) as s:
        doc = s.get_doc("EvalRun", run_name)
        if doc is None:
            raise fail(f"EvalRun '{run_name}' not found in scope '{s.scope}'.")
        spec = _spec_of(doc)
        if as_json:
            print_json({"name": run_name, "spec": spec})
            return
        click.echo(f"EvalRun/{run_name}  (suite {spec.get('suite')}, scope {s.scope})")
        click.echo(f"started {spec.get('started_at')} · finished {spec.get('finished_at')}")
        _print_run(spec)


# ── pin ─────────────────────────────────────────────────────────────────────


@eval_.command("pin")
@click.argument("run_name")
@click.option("--scope", default=None, help="Scope to write in (default: resolved from the source).")
@click.option("--name", "baseline_name", default=None,
              help="Baseline document name (default: baseline-<suite>).")
@click.option("--label", default=None, help="Why this run is the reference.")
def cmd_pin(run_name: str, scope: str | None, baseline_name: str | None, label: str | None):
    """Pin RUN_NAME as the EvalBaseline for its suite.

    Future ``dna eval run <suite> --baseline <name>`` executions are
    compared against the pinned run (regressions exit non-zero)."""
    with dna_session(scope) as s:
        run_doc = s.get_doc("EvalRun", run_name)
        if run_doc is None:
            raise fail(
                f"EvalRun '{run_name}' not found in scope '{s.scope}' "
                f"— run with --save first."
            )
        suite = str(_spec_of(run_doc).get("suite") or "")
        name = baseline_name or f"baseline-{suite}"
        spec: dict[str, Any] = {
            "suite": suite,
            "run_name": run_name,
            "pinned_at": _now(),
        }
        if label:
            spec["label"] = label
        raw = {
            "apiVersion": EVAL_API_VERSION,
            "kind": "EvalBaseline",
            "metadata": {"name": name},
            "spec": spec,
        }
        s.run(s.kernel.write_document(s.scope, "EvalBaseline", name, raw))
        click.echo(f"pinned: EvalBaseline/{name} → EvalRun/{run_name} (suite {suite})")
