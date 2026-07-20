#!/usr/bin/env python3
"""Migrate stored ``LessonLearned`` docs to ``Engram`` (s-engram-rename).

**Clean rename, not a compat shim.** Kind resolution is an exact
``(apiVersion, kind)`` lookup with no fallback (``kernel/instance.py:686``) —
so a doc still carrying the old identity is invisible to the new
``Engram`` KindPort (registered by ``HelixExtension`` from
``helix/kinds/engram.kind.yaml``) the instant the SDK pin advances. This
script rewrites the two envelope fields IN PLACE, everywhere else byte-for-
byte untouched (original newline convention — LF or CRLF — and the presence
or absence of a trailing newline are both preserved exactly):

    kind: LessonLearned                              ->  kind: Engram
    apiVersion: github.com/ruinosus/dna/sdlc/v1       ->  apiVersion: github.com/ruinosus/dna/v1

Storage container/marker (``lessons-learned/`` / ``LESSON_LEARNED.md``) are
UNCHANGED by the rename — no file move, no directory rename. Only the two
envelope fields inside each doc change.

Scope: this script targets **flat YAML docs** — ``rem-<hash>-<slug>.yaml``
with ``kind:``/``apiVersion:`` as top-level keys (the real on-disk shape
observed in local + dna-cloud data). It does NOT handle a hypothetical
bundle-marker layout (``lessons-learned/<name>/LESSON_LEARNED.md`` + a
sidecar meta file) — none was found in practice; the descriptor's
``storage.type: bundle`` declaration is aspirational/legacy here (a real
architectural note, not a bug this script needs to paper over).

Idempotent: a file already carrying the new identity (BOTH ``kind: Engram``
AND ``apiVersion: github.com/ruinosus/dna/v1``) is counted as "already
migrated" and left untouched byte-for-byte; re-running the script any
number of times converges to the same state (safe to re-run, safe as a
provisioning-time step). A doc with ``kind: Engram`` but a stale/missing
``apiVersion`` is NOT silently treated as migrated — Kind resolution is an
exact 2-tuple, so that half-state resolves under NEITHER identity and is
reported as an ORPHAN error requiring manual attention (it is not a shape
this script itself can produce, since it always rewrites both fields
together — but the input data may already contain it).

Writes are atomic: each rewrite goes to a temp file in the SAME directory
(so it's on the same filesystem for ``os.replace``) and is renamed onto the
target, so a kill mid-write (OOM, container eviction) can never leave a
truncated/corrupt YAML — the file is always cleanly old-content-in-place or
new-content-in-place, never a partial write.

Usage:
    # Dry run (default) — reports what WOULD change, writes nothing:
    python3 scripts/migrate_lesson_learned_to_engram.py <root> [<root> ...]

    # Actually rewrite the matching files:
    python3 scripts/migrate_lesson_learned_to_engram.py --apply <root> [<root> ...]

``<root>`` is any directory to walk recursively for ``*.yaml`` files (a
scope dir, a tenant overlay dir, or a whole ``.dna/`` tree — the script does
not assume a fixed layout, it content-sniffs every ``*.yaml`` file found).

**Filesystem-only.** This script walks ``*.yaml`` files on disk — it does
NOT touch a database. It covers any git-tracked ``.dna/`` tree, including
dna-cloud's (baked into the copilot container image at build time via
``COPY .dna /app/.dna`` — so if dna-cloud's ``.dna/`` ever carries
LessonLearned docs, this script must run in the SAME commit as the pin
bump, or the shipped image still has the old identity).

It does **NOT** cover dna-cloud's production runtime store, which is
**Postgres**, not this filesystem tree (``DNA_SOURCE_URL`` — see
``infra/containerapps.bicep`` in the dna-cloud repo). A Postgres-backed
migration is a different shape of problem — ``kind`` is part of a primary
key on several tables, ``apiVersion`` lives inside a JSON ``content``
column — across ``dna_documents``, ``dna_versions``, ``dna_layer_documents``,
``dna_bundle_entries`` and ``dna_search_docs``.
That migration is tracked separately as story
``s-engram-migration-postgres`` and is OUT OF SCOPE here.

This script is SDK-only tooling — it does not touch anything outside the
directories it is explicitly pointed at, and was NOT run against any real
data (local or dna-cloud) as part of this story.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

OLD_KIND = "LessonLearned"
NEW_KIND = "Engram"
OLD_API_VERSION = "github.com/ruinosus/dna/sdlc/v1"
NEW_API_VERSION = "github.com/ruinosus/dna/v1"

# Top-level (unindented) `kind:` / `apiVersion:` lines only — never touches
# schema prose, ``source_refs`` entries, or any other occurrence of the
# string deeper in the doc (e.g. `source_refs: [LessonLearned/rem-x]`,
# which is a cross-reference into another doc, not this doc's own identity,
# and is deliberately left alone — it still resolves fine as a free-form ref
# string, and rewriting it is a separate, unbounded concern).
#
# The trailing ``[ \t]*(?=\r?\n|\Z)`` — NOT a bare ``\s*$`` — is load-bearing:
# ``\s`` matches ``\n``/``\r`` too, so a greedy ``\s*$`` at the END of a file
# (the common case: `apiVersion:` is the last line) eats the file's trailing
# newline, and ``$`` in MULTILINE mode only anchors before a bare ``\n`` —
# never before a lone ``\r`` — so a naive pattern silently fails to match a
# CRLF-terminated line at all, and reading with default (universal) newline
# translation would ALSO normalize the whole file's CRLF -> LF on the round
# trip regardless. Trailing spaces/tabs on the value line are consumed
# (harmless to normalize away); the line terminator itself — bare ``\n``,
# ``\r\n``, or none (last line, no trailing newline) — is only ever
# LOOKED AHEAD AT, never consumed/replaced, so it survives untouched. Reading
# and writing with ``newline=""`` (see ``_read_text`` / ``_atomic_write``)
# additionally disables Python's own newline translation so a CRLF file
# round-trips as CRLF, not just on these two lines but throughout.
_LINE_END = r"[ \t]*(?=\r?\n|\Z)"
_KIND_FIELD_RE = re.compile(rf"^kind:[ \t]*(\S.*?){_LINE_END}", re.MULTILINE)
_API_VERSION_FIELD_RE = re.compile(rf"^apiVersion:[ \t]*(\S.*?){_LINE_END}", re.MULTILINE)


class Classification(Enum):
    """What a scanned ``*.yaml`` file is, w.r.t. this migration."""

    #: kind: LessonLearned + apiVersion: .../sdlc/v1 — rewrite it.
    CANDIDATE = "candidate"
    #: kind: Engram + apiVersion: .../v1 (the new identity, both fields) —
    #: nothing to do, idempotent no-op.
    ALREADY_MIGRATED = "already_migrated"
    #: kind: Engram but apiVersion is NOT the new identity (stale, some
    #: other value, or missing) — Kind resolution is an exact 2-tuple, so
    #: this half-state resolves under NEITHER identity. Never silently
    #: treated as "already migrated" — reported as an error.
    ORPHAN = "orphan"
    #: Neither of the above — not a LessonLearned/Engram doc at all.
    IRRELEVANT = "irrelevant"


def _field_value(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def _classify(text: str) -> Classification:
    kind = _field_value(_KIND_FIELD_RE, text)
    api_version = _field_value(_API_VERSION_FIELD_RE, text)
    if kind == NEW_KIND:
        if api_version == NEW_API_VERSION:
            return Classification.ALREADY_MIGRATED
        return Classification.ORPHAN
    if kind == OLD_KIND and api_version == OLD_API_VERSION:
        return Classification.CANDIDATE
    return Classification.IRRELEVANT


@dataclass
class MigrationReport:
    scanned: int = 0
    found_old: list[Path] = field(default_factory=list)
    already_new: list[Path] = field(default_factory=list)
    migrated: list[Path] = field(default_factory=list)
    orphans: list[Path] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)

    def summary(self, applied: bool) -> str:
        lines = [
            f"scanned {self.scanned} *.yaml file(s)",
            f"  already Engram (no-op, idempotent):        {len(self.already_new)}",
            f"  found LessonLearned (candidates to rewrite): {len(self.found_old)}",
        ]
        if applied:
            lines.append(f"  rewritten:                                   {len(self.migrated)}")
        else:
            lines.append("  (dry run — pass --apply to rewrite them)")
        if self.orphans:
            lines.append(
                f"  ORPHANS (kind: Engram, apiVersion NOT the new "
                f"identity — unresolvable, fix manually): {len(self.orphans)}"
            )
            for p in self.orphans:
                lines.append(f"    - {p}")
        if self.errors:
            lines.append(f"  errors:                                      {len(self.errors)}")
            for p, msg in self.errors:
                lines.append(f"    - {p}: {msg}")
        return "\n".join(lines)


def _rewrite(text: str) -> str:
    """Rewrite a CANDIDATE doc's two envelope fields. Callers must already
    have classified ``text`` as ``Classification.CANDIDATE`` — this function
    does not re-check."""
    text = _KIND_FIELD_RE.sub(f"kind: {NEW_KIND}", text, count=1)
    text = _API_VERSION_FIELD_RE.sub(f"apiVersion: {NEW_API_VERSION}", text, count=1)
    return text


def _read_text(path: Path) -> str:
    # newline="" disables universal-newline translation on read — a CRLF
    # file is read with its "\r\n" sequences intact (not silently
    # normalized to "\n"), so an unmodified line round-trips byte-for-byte.
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _atomic_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically: write to a temp file in the
    SAME directory (guarantees the same filesystem, required for an atomic
    ``os.replace``), then rename onto the target. A kill mid-write leaves
    the temp file orphaned and the target untouched — never a truncated
    target file."""
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(
        dir=str(directory), prefix=f".{path.name}.", suffix=".tmp",
    )
    try:
        # newline="" mirrors _read_text: write exactly the characters in
        # `content` (including any literal "\r\n") with no translation.
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def migrate(roots: list[Path], *, apply: bool) -> MigrationReport:
    report = MigrationReport()
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            report.errors.append((root, "root does not exist"))
            continue
        for path in sorted(root.rglob("*.yaml")):
            resolved = path.resolve()
            if resolved in seen:
                continue  # overlapping roots
            seen.add(resolved)
            report.scanned += 1
            try:
                text = _read_text(path)
            except (OSError, UnicodeDecodeError) as exc:
                report.errors.append((path, str(exc)))
                continue

            classification = _classify(text)

            if classification is Classification.ALREADY_MIGRATED:
                report.already_new.append(path)
                continue
            if classification is Classification.ORPHAN:
                report.orphans.append(path)
                report.errors.append((
                    path,
                    "kind: Engram but apiVersion is not "
                    f"{NEW_API_VERSION!r} — half-migrated, unresolvable "
                    "under either identity (exact 2-tuple lookup, no "
                    "fallback). Fix manually.",
                ))
                continue
            if classification is Classification.IRRELEVANT:
                continue

            # CANDIDATE
            report.found_old.append(path)
            if apply:
                try:
                    new_text = _rewrite(text)
                    _atomic_write(path, new_text)
                    report.migrated.append(path)
                except OSError as exc:
                    report.errors.append((path, str(exc)))
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "roots", nargs="+", type=Path,
        help="Directory (or directories) to walk recursively for *.yaml docs.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually rewrite matching files. Without this flag, the script "
             "only reports what it would do (dry run, the default).",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="List every file found/migrated, not just the counts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = migrate(args.roots, apply=args.apply)

    if args.verbose:
        for p in report.already_new:
            print(f"  [already-engram] {p}")
        for p in report.found_old:
            tag = "migrated" if (args.apply and p in report.migrated) else "would-migrate"
            print(f"  [{tag}] {p}")
        for p in report.orphans:
            print(f"  [ORPHAN] {p}")

    print(report.summary(applied=args.apply))

    if report.errors:
        return 1
    if not args.apply and report.found_old:
        print("\n(dry run — re-run with --apply to rewrite the file(s) above)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
