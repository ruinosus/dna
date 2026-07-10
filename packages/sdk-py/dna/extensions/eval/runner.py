"""Local synchronous eval runner — a pure library over the kernel.

The upstream runner was a Temporal worker driving live agents; it did not
travel (see the extension docstring). This module is the local-first
evolution: run an :code:`EvalSuite` offline, deterministically, with the
kernel itself as the default evaluable system.

Three pieces:

- :class:`EvalTargetPort` — the extension point. A target turns one
  EvalCase into TEXT; the runner judges the text with the case's checks.
  The built-in :class:`PromptCompositionTarget` (``type: prompt``)
  composes the agent's system prompt via ``build_prompt`` — evaluating
  declarative config without any LLM. Hosts register richer targets
  (an LLM call, an HTTP endpoint) by passing ``targets={"llm": ...}``
  to :func:`run_suite` — the same declare-here/execute-in-the-host
  split as Automation runners.
- :func:`run_suite` — executes a suite and returns the raw ``EvalRun``
  document (the caller persists it via ``kernel.write_document``).
- :func:`compare` — diffs a run against a baseline run: regressions /
  improvements / unchanged / added / removed. ``has_regressions`` is
  the bit a user's CI gates on.

Everything is synchronous and side-effect free (no writes, no network):
the ONLY effects are the reads the kernel instance performs.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

API_VERSION = "github.com/ruinosus/dna/eval/v1"

#: Check vocabulary (mirrors the EvalCase descriptor enum).
CHECK_TYPES = (
    "contains",
    "not_contains",
    "regex",
    "not_regex",
    "equals",
    "min_length",
    "max_length",
)

_EXCERPT_CHARS = 200


@runtime_checkable
class EvalTargetPort(Protocol):
    """Turns one EvalCase into the TEXT the checks are applied to.

    ``target`` is the resolved target mapping (case ``target`` → suite
    ``target`` → ``{"type": "prompt"}``); ``case`` is the EvalCase spec.
    ``kernel``/``scope`` give the target the same blessed surface the
    runner itself uses (``kernel.instance(scope)`` → query/build_prompt).
    """

    def run(self, target: dict, case: dict, *, kernel: Any, scope: str) -> str: ...


class PromptCompositionTarget:
    """The built-in ``type: prompt`` target — the kernel as the evaluable
    system. Composes ``build_prompt(agent=target.agent)`` in
    ``target.scope`` (default: the suite's scope). Deterministic and
    offline: "does my agent compose the prompt I expect?" is a real
    evaluation of declarative config."""

    def run(self, target: dict, case: dict, *, kernel: Any, scope: str) -> str:
        del case  # the prompt target evaluates config, not input
        instance = kernel.instance(str(target.get("scope") or scope))
        agent = target.get("agent") or None
        return instance.build_prompt(agent=agent)


_BUILTIN_TARGETS: dict[str, EvalTargetPort] = {
    "prompt": PromptCompositionTarget(),
}


def _spec(doc: Any) -> dict[str, Any]:
    spec = getattr(doc, "spec", None)
    return spec if isinstance(spec, dict) else (dict(spec) if spec else {})


def apply_checks(text: str, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply the case's declared checks to ``text``.

    Returns one result row per check: ``{type, value, passed, detail}``
    (``detail`` only when the check failed). Unknown check types fail
    loudly in the row (the descriptor enum blocks them at write time;
    the runner stays defensive for hand-built specs)."""
    results: list[dict[str, Any]] = []
    for check in checks or []:
        ctype = str((check or {}).get("type", ""))
        value = (check or {}).get("value")
        case_sensitive = bool(check.get("case_sensitive", True))
        row: dict[str, Any] = {"type": ctype, "passed": False}
        if value is not None:
            row["value"] = value

        haystack = text if case_sensitive else text.lower()
        needle = str(value) if value is not None else ""
        if not case_sensitive:
            needle = needle.lower()

        if ctype == "contains":
            row["passed"] = needle in haystack
            if not row["passed"]:
                row["detail"] = f"text does not contain {str(value)!r}"
        elif ctype == "not_contains":
            row["passed"] = needle not in haystack
            if not row["passed"]:
                row["detail"] = f"text contains forbidden {str(value)!r}"
        elif ctype == "regex":
            row["passed"] = re.search(str(value), text) is not None
            if not row["passed"]:
                row["detail"] = f"pattern {str(value)!r} not found"
        elif ctype == "not_regex":
            match = re.search(str(value), text)
            row["passed"] = match is None
            if not row["passed"]:
                row["detail"] = f"forbidden pattern {str(value)!r} matched {match.group(0)!r}"
        elif ctype == "equals":
            row["passed"] = haystack == needle
            if not row["passed"]:
                row["detail"] = f"text != expected ({len(text)} chars vs {len(str(value))})"
        elif ctype == "min_length":
            row["passed"] = len(text) >= int(value)
            if not row["passed"]:
                row["detail"] = f"length {len(text)} < min {value}"
        elif ctype == "max_length":
            row["passed"] = len(text) <= int(value)
            if not row["passed"]:
                row["detail"] = f"length {len(text)} > max {value}"
        else:
            row["detail"] = f"unknown check type {ctype!r}"
        results.append(row)
    return results


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_suite(
    kernel: Any,
    scope: str,
    suite_name: str,
    *,
    targets: dict[str, EvalTargetPort] | None = None,
    run_name: str | None = None,
) -> dict[str, Any]:
    """Execute ``suite_name`` in ``scope`` and return the raw ``EvalRun``
    document (envelope included; NOT persisted — the caller decides, e.g.
    ``dna eval run --save`` writes it via ``kernel.write_document``).

    ``targets`` extends/overrides the built-in target registry
    (``{"prompt": PromptCompositionTarget()}``) — the LLM extension
    point. A case whose resolved target type has no registered port
    yields ``status: error`` (never a silent pass).
    """
    registry: dict[str, EvalTargetPort] = {**_BUILTIN_TARGETS, **(targets or {})}
    # Eval Kinds are record-plane: read them through the kernel's query
    # surface (query_list_sync/get_document_sync — the mi.all/mi.one
    # replacements), not mi.documents (which carries composition docs).

    suite_doc = kernel.get_document_sync(scope, "EvalSuite", suite_name)
    if suite_doc is None:
        raise ValueError(f"EvalSuite {suite_name!r} not found in scope {scope!r}")
    suite = _spec(suite_doc)
    suite_target = suite.get("target") if isinstance(suite.get("target"), dict) else {}

    all_cases = {d.name: d for d in kernel.query_list_sync(scope, "EvalCase")}
    declared = [str(c) for c in (suite.get("cases") or [])]
    if declared:
        case_docs: list[tuple[str, Any]] = [
            (name, all_cases.get(name)) for name in declared
        ]
    else:
        case_docs = sorted(all_cases.items(), key=lambda t: t[0])

    started = _now_iso()
    results: list[dict[str, Any]] = []
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}

    for name, doc in case_docs:
        if doc is None:
            counts["error"] += 1
            results.append({
                "case": name, "status": "error",
                "error": f"EvalCase {name!r} not found in scope {scope!r}",
            })
            if suite.get("stop_on_fail"):
                break
            continue
        case = _spec(doc)
        if case.get("skip"):
            counts["skipped"] += 1
            results.append({"case": name, "status": "skipped"})
            continue

        target = case.get("target") if isinstance(case.get("target"), dict) else None
        target = target or suite_target or {}
        target_type = str(target.get("type") or "prompt")
        row: dict[str, Any] = {"case": name, "target_type": target_type}

        port = registry.get(target_type)
        if port is None:
            counts["error"] += 1
            row.update({
                "status": "error",
                "error": (
                    f"no EvalTargetPort registered for target type "
                    f"{target_type!r} — built-in: prompt; custom targets "
                    f"are host-registered (targets={{...}})"
                ),
            })
            results.append(row)
            if suite.get("stop_on_fail"):
                break
            continue

        try:
            text = port.run(dict(target), dict(case), kernel=kernel, scope=scope)
        except Exception as exc:  # noqa: BLE001 — one broken case must not kill the run
            counts["error"] += 1
            row.update({"status": "error", "error": f"target raised: {exc}"})
            results.append(row)
            if suite.get("stop_on_fail"):
                break
            continue

        check_rows = apply_checks(str(text), case.get("checks") or [])
        ok = bool(check_rows) and all(c["passed"] for c in check_rows)
        row["status"] = "passed" if ok else "failed"
        row["checks"] = check_rows
        row["output_excerpt"] = str(text)[:_EXCERPT_CHARS]
        counts["passed" if ok else "failed"] += 1
        results.append(row)
        if not ok and suite.get("stop_on_fail"):
            break

    finished = _now_iso()
    name = run_name or (
        f"run-{suite_name}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    )
    return {
        "apiVersion": API_VERSION,
        "kind": "EvalRun",
        "metadata": {"name": name},
        "spec": {
            "suite": suite_name,
            "started_at": started,
            "finished_at": finished,
            "target": dict(suite_target) if suite_target else {"type": "prompt"},
            "total": len(results),
            "passed": counts["passed"],
            "failed": counts["failed"],
            "errored": counts["error"],
            "skipped": counts["skipped"],
            "results": results,
        },
    }


def _status_by_case(run_spec: dict[str, Any]) -> dict[str, str]:
    return {
        str(r.get("case")): str(r.get("status"))
        for r in (run_spec.get("results") or [])
        if r.get("case")
    }


def compare(run_spec: dict[str, Any], baseline_spec: dict[str, Any]) -> dict[str, Any]:
    """Diff a fresh run against a baseline run (both: EvalRun ``spec``).

    A case is OK when its status is ``passed``. Skipped cases are treated
    as absent on their side (a deliberate skip is not a regression).
    Returns ``regressions`` (baseline OK → now failing/errored),
    ``improvements`` (the reverse), ``unchanged``, ``added``/``removed``
    (case present on one side only) and ``has_regressions`` — the bit a
    CI gate reads (``dna eval run --baseline`` exits non-zero on it)."""
    current = {c: s for c, s in _status_by_case(run_spec).items() if s != "skipped"}
    base = {c: s for c, s in _status_by_case(baseline_spec).items() if s != "skipped"}

    regressions: list[str] = []
    improvements: list[str] = []
    unchanged: list[str] = []
    for case in sorted(set(current) & set(base)):
        now_ok = current[case] == "passed"
        was_ok = base[case] == "passed"
        if was_ok and not now_ok:
            regressions.append(case)
        elif not was_ok and now_ok:
            improvements.append(case)
        else:
            unchanged.append(case)

    return {
        "regressions": regressions,
        "improvements": improvements,
        "unchanged": unchanged,
        "added": sorted(set(current) - set(base)),
        "removed": sorted(set(base) - set(current)),
        "has_regressions": bool(regressions),
    }
