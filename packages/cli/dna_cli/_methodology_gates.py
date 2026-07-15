"""Methodology gates — pure functions enforcing the superpowers contract.

`methodology=superpowers` was historically just a string label in
`JOURNEY_METHODOLOGIES`. These gates turn it into a verifiable
contract: spec/plan artifacts must exist, build → reflect requires
test files in the diff, and the Auditor blocks ad-hoc streaks.

The four gates are PURE FUNCTIONS — no I/O beyond filesystem stat and
a single subprocess call in `_git_diff_files` (which is monkeypatched
in tests). The CLI in `sdlc_cmd.py` calls these at phase boundaries
and translates GateResult.FAIL into exit code 2.

Spec: docs/superpowers/specs/2026-05-11-f-superpowers-skill-integration.md
"""
from __future__ import annotations

import subprocess
from enum import Enum
from pathlib import Path


class GateResult(Enum):
    """Outcome of a gate check.

    PASS — gate satisfied, proceed.
    FAIL — gate violated, caller should exit 2 unless --force --reason.
    SKIP — gate not applicable in this context (e.g. methodology=ad-hoc).
    """

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


# Methodologies whose specify/plan phases must be backed by a real artifact
# on disk. Superpowers pins its docs/superpowers/{specs,plans}/*.md; Spec Kit
# pins its .specify/-run spec.md / plan.md (s-spec-kit-journey-wiring, ADR §8.3).
_ARTIFACT_GATED = frozenset({"superpowers", "spec-kit"})


# ───── spec_gate ─────────────────────────────────────────────────────


def spec_gate(*, methodology: str, phase: str, artifact: str | None) -> GateResult:
    """Specify phase under an artifact-gated methodology requires a real Spec doc.

    Returns SKIP unless `methodology` is artifact-gated (superpowers | spec-kit)
    and `phase == "specify"`. FAIL if `artifact` is None or points to a missing
    file. PASS otherwise (for spec-kit the artifact is the run's ``spec.md``).
    """
    if methodology not in _ARTIFACT_GATED or phase != "specify":
        return GateResult.SKIP
    if not artifact:
        return GateResult.FAIL
    return GateResult.PASS if Path(artifact).exists() else GateResult.FAIL


# ───── plan_gate ─────────────────────────────────────────────────────


def plan_gate(
    *,
    methodology: str,
    phase: str,
    artifact: str | None,
    auto_stub: bool,
) -> GateResult:
    """Plan phase under superpowers requires Plan doc OR --auto-stub.

    SKIP if not (artifact-gated methodology + plan).
    PASS if --auto-stub (caller will stub the plan file) or artifact exists.
    FAIL otherwise.
    """
    if methodology not in _ARTIFACT_GATED or phase != "plan":
        return GateResult.SKIP
    if auto_stub:
        return GateResult.PASS
    if not artifact:
        return GateResult.FAIL
    return GateResult.PASS if Path(artifact).exists() else GateResult.FAIL


# ───── tdd_gate ──────────────────────────────────────────────────────


def _git_diff_files(since: str) -> list[str]:
    """Return list of files changed between ``since..HEAD``.

    Returns [] on any git error (we fail-open at the caller via SKIP
    when since_sha is missing).
    """
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{since}..HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return []
    return [line for line in out.stdout.splitlines() if line]


def _looks_like_test_file(path: str) -> bool:
    """Heuristic: does this path look like a test file?

    Accepts: anything under ``tests/`` (Python convention) or files
    matching ``test_*.py`` / ``*_test.py`` / ``*.test.ts`` / ``*.spec.ts``.
    """
    if "tests/" in path or "/test_" in path:
        return True
    name = path.rsplit("/", 1)[-1]
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    if name.endswith(".test.ts") or name.endswith(".test.tsx"):
        return True
    if name.endswith(".spec.ts") or name.endswith(".spec.tsx"):
        return True
    return False


def tdd_gate(
    *,
    methodology: str,
    prev_phase: str,
    next_phase: str,
    since_sha: str | None,
) -> GateResult:
    """Transition build → reflect under superpowers requires test files in diff.

    SKIP if methodology is not superpowers, transition is not build→reflect,
    or `since_sha` is missing (cannot verify honestly).
    PASS if any file in the git diff since `since_sha` looks like a test.
    FAIL otherwise.
    """
    if methodology != "superpowers" or prev_phase != "build" or next_phase != "reflect":
        return GateResult.SKIP
    if not since_sha:
        return GateResult.SKIP
    files = _git_diff_files(since_sha)
    return GateResult.PASS if any(_looks_like_test_file(f) for f in files) else GateResult.FAIL


# ───── auditor_gate ──────────────────────────────────────────────────


_AUDITOR_WINDOW = 5
_AUDITOR_THRESHOLD = 3


def auditor_gate(
    *,
    recent_methodologies: list[str],
    next_methodology: str,
) -> GateResult:
    """Block ad-hoc streaks. Looks at the last 5 methodologies.

    SKIP when history < 4 (insufficient data).
    PASS when next_methodology is `superpowers` (any streak satisfied by upgrade).
    PASS when last 5 contain < 3 ad-hoc entries.
    FAIL when last 5 contain >= 3 ad-hoc AND next is not superpowers.
    """
    if len(recent_methodologies) < 4:
        return GateResult.SKIP
    window = recent_methodologies[-_AUDITOR_WINDOW:]
    ad_hoc_count = sum(1 for m in window if m == "ad-hoc")
    if ad_hoc_count >= _AUDITOR_THRESHOLD and next_methodology != "superpowers":
        return GateResult.FAIL
    return GateResult.PASS
