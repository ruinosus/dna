"""Git ↔ SDLC symbiosis — trailer convention + commit queries.

The convention (s-sdlc-git-symbiosis)
-------------------------------------
Every commit made while a Story is active (``.dna/active-story.txt``,
written by ``dna sdlc story start``) is stamped with two trailers by the
versioned ``prepare-commit-msg`` hook (``scripts/git-hooks/``):

    Work-Item: Story/<story-name>
    Co-Authored-By: dna-sdlc[bot] <dna-sdlc[bot]@users.noreply.github.com>

``Work-Item: <Kind>/<name>`` is the machine-readable link back to the
SDLC document. The co-author is **the dna sdlc tool itself** (GitHub
bot-identity convention) — a provenance seal meaning "this commit was
born under story governance: it has a plan, a timeline, a test gate".
It is NOT a human co-author; human/agent authorship stays in the normal
git author + their own trailers. Override the identity with the
``DNA_SDLC_COAUTHOR`` env var.

No active story → no stamp. Absence is signal too.

The way back: ``git log --grep "Work-Item: Story/<name>"`` materializes
the commit list for a Story with zero manual bookkeeping — surfaced by
``dna sdlc story show`` (Commits section) and ``dna sdlc story commits``.

This module is the single home for the constants + the (fail-soft) git
queries. The hook itself is a standalone python3 script (zero deps — it
must run without any venv); ``tests/test_git_symbiosis_hook.py`` asserts
the hook's constants match this module so the two can't drift.
"""
from __future__ import annotations

import os
import subprocess
from importlib.resources import files as _pkg_files
from pathlib import Path
from typing import Any

WORK_ITEM_TRAILER = "Work-Item"
COAUTHOR_TRAILER = "Co-Authored-By"
DEFAULT_SDLC_COAUTHOR = "dna-sdlc[bot] <dna-sdlc[bot]@users.noreply.github.com>"
COAUTHOR_ENV = "DNA_SDLC_COAUTHOR"

#: Repo-relative hooks dir that ``dna sdlc hooks install`` points
#: ``core.hooksPath`` at. Versioned in-repo so the hook ships with the clone.
HOOKS_DIR = "scripts/git-hooks"
HOOK_NAME = "prepare-commit-msg"

_GIT_TIMEOUT = 10  # seconds — every git call here is local + bounded


def sdlc_coauthor() -> str:
    """Effective tool-identity co-author (env override → default bot)."""
    return os.environ.get(COAUTHOR_ENV, "").strip() or DEFAULT_SDLC_COAUTHOR


def work_item_ref(kind: str, name: str) -> str:
    """Canonical work-item reference used in the trailer: ``<Kind>/<name>``."""
    return f"{kind}/{name}"


def trailer_lines(kind: str, name: str) -> list[str]:
    """The exact trailer lines the hook stamps for a work item."""
    return [
        f"{WORK_ITEM_TRAILER}: {work_item_ref(kind, name)}",
        f"{COAUTHOR_TRAILER}: {sdlc_coauthor()}",
    ]


def hook_source_path() -> Path:
    """Path of the canonical hook script shipped inside the package.

    ``scripts/git-hooks/prepare-commit-msg`` in the repo is a byte-identical
    copy (enforced by test) so clones get the hook without installing dna-cli.
    """
    return Path(str(_pkg_files("dna_cli").joinpath("data/git-hooks/prepare-commit-msg")))


def _run_git(args: list[str], *, cwd: str | Path | None = None) -> str | None:
    """Run a git command; return stdout or ``None`` on any failure.

    Fail-soft by design — callers treat ``None`` as "no git information
    available" (git missing, not a repo, etc). Never raises.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT,
            cwd=str(cwd) if cwd else None,
        )
    except Exception:  # noqa: BLE001 — git absent / timeout / OS error
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def repo_root(*, cwd: str | Path | None = None) -> Path | None:
    """Top-level of the enclosing git working tree, or ``None``."""
    out = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    if not out:
        return None
    top = out.strip()
    return Path(top) if top else None


def commits_for_work_item(
    kind: str, name: str, *, cwd: str | Path | None = None,
) -> list[dict[str, Any]] | None:
    """Commits whose message carries ``Work-Item: <Kind>/<name>``.

    Returns ``None`` when git / a repo isn't available (fail-soft), else a
    list (possibly empty) of ``{sha, full_sha, date, subject}`` dicts,
    newest first — straight from ``git log --grep`` on the trailer.
    """
    ref = f"{WORK_ITEM_TRAILER}: {work_item_ref(kind, name)}"
    out = _run_git(
        [
            "log", "--fixed-strings", f"--grep={ref}",
            "--date=short", "--format=%h%x1f%H%x1f%ad%x1f%s",
        ],
        cwd=cwd,
    )
    if out is None:
        return None
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        sha, full_sha, date, subject = parts
        rows.append({
            "sha": sha, "full_sha": full_sha, "date": date, "subject": subject,
        })
    return rows
