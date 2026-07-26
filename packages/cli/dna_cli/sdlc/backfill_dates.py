"""``dna sdlc backfill-dates`` — repair documents filed before i-078.

``build_issue_spec`` and ``dna sdlc issue file`` both wrote an Issue without
``spec.created_at``, and the digest dates a filed Issue by exactly that field —
so every Issue ever filed was invisible in the digest's ``found`` bucket. The
writers are fixed; this repairs what is already on disk.

The decision the repair turns on is *what date to write*, and it lives in the
pure core (:func:`dna.application.sdlc.plan_date_repair`): the document's own
timeline first, the git commit that ADDED the file second, and — explicitly —
nothing third. This module supplies the two impure inputs the core cannot
compute: the board's documents (via the kernel session) and the git history of
the scope directory.

Idempotent: a document that already carries its declared stamps is untouched,
so the verb is safe to re-run and safe to wire into a migration.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import click

from dna.application.sdlc import DATED_SPEC_FIELDS, plan_date_repair
from dna_cli._ctx import open_session
from dna_cli.sdlc._common import _build_raw, _scope_option
from dna_cli.sdlc._root import sdlc


# ─── git witness ──────────────────────────────────────────────────────


def _as_utc(stamp: str) -> str:
    """Git's ``%aI`` is the author's LOCAL time with an offset; the board stamps
    UTC. Normalize so a backfilled date sorts and compares against every other
    stamp on the board. Unparseable input passes through untouched."""
    try:
        return (
            datetime.fromisoformat(stamp)
            .astimezone(timezone.utc)
            .isoformat(timespec="seconds")
        )
    except ValueError:
        return stamp


def parse_git_log(text: str) -> dict[str, tuple[str, str]]:
    """Parse ``git log --reverse --format=%x00%aI --name-only`` into
    ``path → (added_at, last_touched_at)``, both normalized to UTC.

    Pure so the parsing is testable without a repo. ``--reverse`` means the
    FIRST time a path appears is the commit that added it and the LAST is the
    most recent commit that touched it; ``%x00`` prefixes the date line so it
    can never be confused with a filename.
    """
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("\x00"):
            current = _as_utc(line[1:].strip())
            continue
        path = line.strip()
        if not path or not current:
            continue
        first.setdefault(path, current)
        last[path] = current
    return {path: (first[path], last[path]) for path in first}


def index_by_doc_name(paths: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """Re-key git dates from repo paths onto document names.

    A document is stored either as ``<container>/<name>.yaml`` or, for bundle
    Kinds, as a ``<container>/<name>/`` directory — so both the file stem and
    the parent directory name are plausible document names. Registering both
    keeps this storage-shape-agnostic; when several paths map to one name (a
    bundle's entries) the earliest add and the latest touch win, which is
    exactly the document's own span.
    """
    out: dict[str, tuple[str, str]] = {}
    for path, (added, touched) in paths.items():
        p = Path(path)
        for key in {p.stem, p.parent.name}:
            if not key:
                continue
            if key in out:
                prev_added, prev_touched = out[key]
                out[key] = (min(prev_added, added), max(prev_touched, touched))
            else:
                out[key] = (added, touched)
    return out


def _scope_dir(scope: str) -> Path | None:
    """On-disk directory of ``scope``, or None for a non-filesystem source."""
    from dna_cli._ctx import _resolve_source_url

    parsed = urlparse(_resolve_source_url())
    if parsed.scheme not in ("file", "fs", ""):
        return None
    base = (parsed.netloc + parsed.path) if parsed.netloc else (parsed.path or "")
    directory = Path(base) / scope
    return directory if directory.is_dir() else None


def git_dates_for_scope(scope: str) -> dict[str, tuple[str, str]]:
    """``doc name → (added_at, last_touched_at)`` from the git history of the
    scope directory. Empty (never raises) outside a working tree, without git,
    or for a non-filesystem source — the repair simply loses its second-choice
    witness and reports the affected documents as undatable."""
    directory = _scope_dir(scope)
    if directory is None:
        return {}
    try:
        result = subprocess.run(
            ["git", "log", "--reverse", "--format=%x00%aI", "--name-only",
             "--", str(directory)],
            capture_output=True, text=True, timeout=30, check=False,
            cwd=str(directory),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {}
    if result.returncode != 0:
        return {}
    return index_by_doc_name(parse_git_log(result.stdout))


# ─── the verb ─────────────────────────────────────────────────────────


@sdlc.command("backfill-dates")
@click.option("--dry-run", is_flag=True,
              help="Report what would be stamped, write nothing.")
@click.option("--kind", "only_kind", default=None,
              help="Repair a single Kind (default: every Kind that a read "
                   "surface dates — see DATED_SPEC_FIELDS).")
@_scope_option
def cmd_backfill_dates(dry_run: bool, only_kind: str | None, scope: str) -> None:
    """Stamp the dates a document was filed without.

    Repairs ``created_at`` / ``updated_at`` on every board Kind a read surface
    dates by (the digest's windows, the derived journey, recency sorts), taking
    the value from the document's own timeline, else from the commit that added
    its file. Documents with neither are LEFT ALONE and listed — inventing
    "now" would date them all as filed today and skew every digest window from
    here on. Idempotent; ``--dry-run`` previews.
    """
    kinds = sorted(DATED_SPEC_FIELDS)
    if only_kind:
        if only_kind not in DATED_SPEC_FIELDS:
            raise click.ClickException(
                f"{only_kind!r} is not dated by any read surface "
                f"(known: {', '.join(kinds)})"
            )
        kinds = [only_kind]

    git_dates = git_dates_for_scope(scope)
    repaired: list[tuple[str, str, dict[str, str], str]] = []
    undatable: list[tuple[str, str]] = []

    with open_session(scope) as s:
        for kind in kinds:
            for doc in s.query_list(kind):
                spec: dict[str, Any] = (
                    dict(doc.spec) if isinstance(doc.spec, dict) else {}
                )
                added, touched = git_dates.get(doc.name, (None, None))
                fields, provenance = plan_date_repair(
                    kind, spec, git_added_at=added, git_touched_at=touched,
                )
                if provenance == "undatable":
                    undatable.append((kind, doc.name))
                    continue
                if not fields:
                    continue
                repaired.append((kind, doc.name, fields, provenance))
                if dry_run:
                    continue
                spec.update(fields)
                s.run(s.kernel.write_document(
                    scope, kind, doc.name, _build_raw(kind, doc.name, spec),
                ))

    for kind, name, fields, provenance in repaired:
        stamps = ", ".join(f"{k}={v}" for k, v in sorted(fields.items()))
        click.echo(f"  {kind}/{name}  [{provenance}]  {stamps}")
    for kind, name in undatable:
        click.secho(
            f"  {kind}/{name}  [undatable] no timeline and no git history — "
            f"left unstamped on purpose",
            fg="yellow",
        )
    click.secho(
        f"\n{len(repaired)} repaired, {len(undatable)} left undatable"
        + (" (dry-run — nothing written)" if dry_run else ""),
        fg="yellow" if dry_run else "green", bold=True,
    )
