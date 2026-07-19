#!/usr/bin/env python3
"""Unified entry point: migrate stored ``LessonLearned`` docs to ``Engram``
(s-engram-rename / s-engram-migration-postgres), against EITHER a
filesystem ``.dna/`` tree or a Postgres source — dispatched by ``--source``.

    # Filesystem (delegates to migrate_lesson_learned_to_engram.py, byte-for-
    # byte identical behavior — dry run is the default):
    python3 scripts/migrate_engram.py --source .dna
    python3 scripts/migrate_engram.py --source .dna --apply

    # Postgres (delegates to migrate_engram_postgres.py — dry run default):
    python3 scripts/migrate_engram.py --source postgresql://user:pass@host/db
    python3 scripts/migrate_engram.py --source postgresql://user:pass@host/db --apply --schema public

Multiple ``--source`` values are accepted for the filesystem case (multiple
roots to walk, same as the FS script's ``roots`` positional argument) — but
exactly ONE is accepted when it is a Postgres DSN (a single migration run
targets a single database/schema; mixing a DSN with filesystem roots in one
invocation is rejected, they are different jobs with different exit-code
semantics).

This script does not contain migration LOGIC itself — it is a thin
dispatcher over the two implementations, each independently
importable/testable:

  * ``migrate_lesson_learned_to_engram.py`` — filesystem, pre-existing
    (s-engram-rename), untouched by this story except for being imported
    here instead of only invoked as ``__main__``.
  * ``migrate_engram_postgres.py`` — Postgres, new in this story
    (s-engram-migration-postgres). See its module docstring for the full
    schema analysis, collision pre-flight design, and the ``dna_outbox``
    decision.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _is_pg_dsn(s: str) -> bool:
    return s.startswith(("postgresql://", "postgres://", "postgresql+asyncpg://"))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source", action="append", required=True, dest="sources",
        help="A filesystem root to walk, OR a single postgresql:// DSN. "
             "Repeatable for multiple filesystem roots.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually write. Without this flag: dry run (the default) — "
             "reports what would change, writes nothing.",
    )
    parser.add_argument(
        "--schema", default="public",
        help="Postgres schema (ignored for filesystem sources). Default: public.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    pg_sources = [s for s in args.sources if _is_pg_dsn(s)]
    fs_sources = [s for s in args.sources if not _is_pg_dsn(s)]

    if pg_sources and fs_sources:
        print(
            "error: cannot mix a Postgres DSN with filesystem roots in one "
            f"invocation (--source values: {args.sources!r})",
            file=sys.stderr,
        )
        return 2
    if len(pg_sources) > 1:
        print(
            "error: only one Postgres --source DSN is supported per run "
            f"(got {len(pg_sources)}: {pg_sources!r})",
            file=sys.stderr,
        )
        return 2

    if pg_sources:
        pg_mod = _load_module("migrate_engram_postgres", "migrate_engram_postgres.py")
        return pg_mod.main([pg_sources[0], "--schema", args.schema]
                            + (["--apply"] if args.apply else [])
                            + (["--verbose"] if args.verbose else []))

    fs_mod = _load_module("migrate_lesson_learned_to_engram", "migrate_lesson_learned_to_engram.py")
    fs_argv = list(fs_sources) + (["--apply"] if args.apply else []) + (["--verbose"] if args.verbose else [])
    return fs_mod.main(fs_argv)


if __name__ == "__main__":
    raise SystemExit(main())
