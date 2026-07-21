#!/usr/bin/env python3
"""Drift guard for the generated data model (MER) — docs/reference/data-model.md.

The MER exists because two HAND-WRITTEN snapshots were published and both
aged out inside a day: a table was removed, a control table swapped, a quota
counter added, and the plan moved from workspace to account, while the
documents went on asserting the old shape. That is the failure mode an audit
spent a day removing from this repo — a declaration shipped, reality diverging
in silence.

A generated MER only avoids that fate if something FAILS when the committed
page and the source disagree. That is this guard. It regenerates the page in
memory and diffs; a stale commit fails the build.

Why a separate script when the generator already has ``--check``: this one
prints the actual diff, so a red CI run tells you WHAT drifted rather than
just that something did, and it carries a self-test that proves the guard can
still fail. A guard nobody has watched fail is decoration.

Determinism is a hard requirement, not a nicety. ``gen_cli_docs.py``
regenerates 15 pages with whitespace-only churn, so its guard cries wolf on
every PR and people learned to wave it through. ``--determinism`` re-runs the
generator twice and asserts the bytes are identical, so that failure mode is
caught here rather than discovered as noise months later.

Usage:
    python3 scripts/data_model_guard.py                # fail if committed != regenerated
    python3 scripts/data_model_guard.py --self-test    # prove the guard can fail
    python3 scripts/data_model_guard.py --determinism  # prove the generator is stable
    python3 scripts/data_model_guard.py --write        # regenerate + write (dev convenience)

CI runs ``--self-test``, then ``--determinism``, then the real guard
(docs-build job in .github/workflows/docs.yml).
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PAGE = _REPO_ROOT / "docs" / "reference" / "data-model.md"

sys.path.insert(0, str(_REPO_ROOT / "scripts"))


def _regenerate() -> str:
    from gen_data_model_docs import _build

    return _build()


def _diff(committed: str, regenerated: str) -> str:
    return "".join(
        difflib.unified_diff(
            committed.splitlines(keepends=True),
            regenerated.splitlines(keepends=True),
            fromfile="docs/reference/data-model.md (committed)",
            tofile="docs/reference/data-model.md (regenerated)",
            n=2,
        )
    )


def check() -> int:
    if not _PAGE.exists():
        print(
            f"data_model_guard: {_PAGE.relative_to(_REPO_ROOT)} is MISSING — "
            "run `python3 scripts/gen_data_model_docs.py` and commit it.",
            file=sys.stderr,
        )
        return 1

    committed = _PAGE.read_text(encoding="utf-8")
    regenerated = _regenerate()
    if committed == regenerated:
        print(
            "data_model_guard: clean — the committed data model matches a "
            "fresh regeneration from the Kind registry + table model"
        )
        return 0

    print(
        "data_model_guard: the committed data model is STALE. The Kinds, "
        "their `x-dna-ref` declarations, or the physical tables changed and "
        "docs/reference/data-model.md was not regenerated.\n\n"
        "  fix: python3 scripts/gen_data_model_docs.py && git add "
        "docs/reference/data-model.md\n\n"
        "Do NOT hand-edit the page — it is generated, and the next run would "
        "revert you.\n",
        file=sys.stderr,
    )
    print(_diff(committed, regenerated), file=sys.stderr)
    return 1


def determinism() -> int:
    """Two regenerations must be byte-identical.

    A generator whose output wobbles makes its own guard useless: every PR
    shows a diff, the diff means nothing, and the signal is gone.
    """
    first = _regenerate()
    second = _regenerate()
    if first == second:
        print(
            f"data_model_guard: generator is deterministic "
            f"({len(first)} bytes, two runs identical)"
        )
        return 0
    print(
        "data_model_guard: NON-DETERMINISTIC generator — two runs of "
        "gen_data_model_docs.py produced different bytes. Its drift guard "
        "cannot work until this is fixed (unsorted collection, timestamp, "
        "absolute path, or set iteration order).",
        file=sys.stderr,
    )
    print(_diff(first, second), file=sys.stderr)
    return 1


def self_test() -> int:
    """Prove the guard actually fails on drift, using planted content.

    Pure string-level: no regeneration, no ``dna`` import. It tests the
    comparison, which is the part that would silently rot into
    ``return 0``.
    """
    failures: list[str] = []

    # 1. identical → clean
    if _diff("same\n", "same\n") != "":
        failures.append("identical inputs produced a diff")

    # 2. drifted → non-empty diff naming the change
    drift = _diff("a\nold line\nc\n", "a\nnew line\nc\n")
    if not drift:
        failures.append("planted drift produced NO diff")
    elif "old line" not in drift or "new line" not in drift:
        failures.append(f"diff does not name the change: {drift!r}")

    # 3. a realistic drift — an edge changing tier — is caught
    before = "| `Story` | `feature` | `Feature` | one | |\n"
    after = "| `Story` | `feature` | `Epic` | one | |\n"
    if not _diff(before, after):
        failures.append("a changed edge target was not detected")

    # 4. whitespace-only drift is still drift (it is what broke gen_cli_docs)
    if not _diff("x\n", "x \n"):
        failures.append("whitespace-only drift was not detected")

    if failures:
        print("data_model_guard SELF-TEST FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(
        "data_model_guard self-test OK (identical passes, drifted content "
        "fails and is named, whitespace-only drift still fails)"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true",
                    help="prove the guard can fail (no dna import)")
    ap.add_argument("--determinism", action="store_true",
                    help="prove two regenerations are byte-identical")
    ap.add_argument("--write", action="store_true",
                    help="regenerate and write the page (dev convenience)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.determinism:
        return determinism()
    if args.write:
        _PAGE.write_text(_regenerate(), encoding="utf-8")
        print(f"Wrote {_PAGE.relative_to(_REPO_ROOT)}")
        return 0
    return check()


if __name__ == "__main__":
    sys.exit(main())
