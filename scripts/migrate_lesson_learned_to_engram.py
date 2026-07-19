#!/usr/bin/env python3
"""Migrate stored ``LessonLearned`` docs to ``Engram`` (s-engram-rename).

**Clean rename, not a compat shim.** Kind resolution is an exact
``(apiVersion, kind)`` lookup with no fallback (``kernel/instance.py:686``) —
so a doc still carrying the old identity is invisible to the new
``Engram`` KindPort (registered by ``HelixExtension`` from
``helix/kinds/engram.kind.yaml``) the instant the SDK pin advances. This
script rewrites the two envelope fields IN PLACE, everywhere else byte-for-
byte untouched:

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

Idempotent: a file already carrying the new identity is counted as
"already migrated" and left untouched byte-for-byte; re-running the script
any number of times converges to the same state (safe to re-run, safe as a
provisioning-time step).

Usage:
    # Dry run (default) — reports what WOULD change, writes nothing:
    python3 scripts/migrate_lesson_learned_to_engram.py <root> [<root> ...]

    # Actually rewrite the matching files:
    python3 scripts/migrate_lesson_learned_to_engram.py --apply <root> [<root> ...]

``<root>`` is any directory to walk recursively for ``*.yaml`` files (a
scope dir, a tenant overlay dir, or a whole ``.dna/`` tree — the script does
not assume a fixed layout, it content-sniffs every ``*.yaml`` file found).

This script is SDK-only tooling — it does not touch anything outside the
directories it is explicitly pointed at, and was NOT run against dna-cloud's
``.dna/`` (a separate repo) as part of this story; that migration happens at
the SDK-pin-bump deploy step in dna-cloud, using this same script.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
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
_KIND_RE = re.compile(rf"^kind:\s*{re.escape(OLD_KIND)}\s*$", re.MULTILINE)
_API_VERSION_RE = re.compile(
    rf"^apiVersion:\s*{re.escape(OLD_API_VERSION)}\s*$", re.MULTILINE
)
_ALREADY_KIND_RE = re.compile(rf"^kind:\s*{re.escape(NEW_KIND)}\s*$", re.MULTILINE)


@dataclass
class MigrationReport:
    scanned: int = 0
    found_old: list[Path] = field(default_factory=list)
    already_new: list[Path] = field(default_factory=list)
    migrated: list[Path] = field(default_factory=list)
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
        if self.errors:
            lines.append(f"  errors:                                      {len(self.errors)}")
            for p, msg in self.errors:
                lines.append(f"    - {p}: {msg}")
        return "\n".join(lines)


def _is_lesson_learned_doc(text: str) -> bool:
    return bool(_KIND_RE.search(text) and _API_VERSION_RE.search(text))


def _is_already_engram_doc(text: str) -> bool:
    # Best-effort idempotency signal: a doc that already declares kind:
    # Engram. We don't require apiVersion to also already match — a
    # half-migrated file (shouldn't happen, this script rewrites both
    # atomically) still counts so re-runs never double-touch it.
    return bool(_ALREADY_KIND_RE.search(text))


def _rewrite(text: str) -> str:
    text = _KIND_RE.sub(f"kind: {NEW_KIND}", text)
    text = _API_VERSION_RE.sub(f"apiVersion: {NEW_API_VERSION}", text)
    return text


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
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                report.errors.append((path, str(exc)))
                continue

            if _is_already_engram_doc(text):
                report.already_new.append(path)
                continue
            if not _is_lesson_learned_doc(text):
                continue  # not a LessonLearned doc at all — unrelated yaml

            report.found_old.append(path)
            if apply:
                try:
                    new_text = _rewrite(text)
                    path.write_text(new_text, encoding="utf-8")
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

    print(report.summary(applied=args.apply))

    if report.errors:
        return 1
    if not args.apply and report.found_old:
        print("\n(dry run — re-run with --apply to rewrite the file(s) above)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
