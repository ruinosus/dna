#!/usr/bin/env python3
"""Migrate stored ``LessonLearned`` docs to ``Engram`` — the Postgres leg
(s-engram-migration-postgres).

``scripts/migrate_lesson_learned_to_engram.py`` (s-engram-rename) is
**filesystem-only**: it walks ``*.yaml`` files on disk. dna-cloud's
production DNA source is **Postgres** (``DNA_SOURCE_URL=postgresql://…``),
so that script migrates zero production rows there. Kind resolution is an
exact ``(apiVersion, kind)`` 2-tuple lookup with no fallback
(``dna/kernel/instance.py:686`` — ``self._kinds.get((doc.api_version,
doc.kind))``), so the moment the ``Engram``-only SDK pin ships, every
unmigrated Postgres row becomes invisible. This module is that migration.

Schema reality (verified against ``dna/adapters/sqlalchemy_/migrations.py``
and ``dna/adapters/search/pgvector_migrations.py`` — READ THOSE FILES, don't
trust a summary):

  * ``dna_documents``       — PK ``(scope, kind, name, tenant)``. ``kind`` is
    a real column; ``content`` is TEXT holding a JSON envelope
    (``json.dumps``/``json.loads`` — NOT YAML), so rewriting ``kind`` +
    ``apiVersion`` is pure SQL, no parse/re-serialize round trip needed
    beyond a single ``jsonb_set``.
  * ``dna_versions``        — real PK is a surrogate ``id``; ``kind`` only
    participates in a **partial** UNIQUE index
    (``scope, kind, name, tenant, semver``) that applies *only when semver
    IS NOT NULL* — and only ``Genome``/module docs ever set semver
    (``SqlAlchemySource.save_document``: ``if kind == "Genome": spec_version
    = …``). A memory Kind's version rows are practically collision-free, but
    the pre-flight checks the partial-unique case anyway rather than assume.
  * ``dna_layer_documents``  — PK ``(scope, layer_id, layer_value, kind,
    name)``. Tenant overlays are routed through ``dna_documents.tenant``
    instead (``save_layer_document``: ``layer_id == "tenant"`` redirects to
    ``save_document``), so this table normally only carries non-tenant
    layers — but the schema itself still keys on ``kind``, so it is treated
    generically like ``dna_documents``.
  * ``dna_bundle_entries``   — PK ``(scope, kind, name, entry_path,
    tenant)``. ``content`` here is a raw bundle file body (markdown/YAML
    text or bytes), NOT a JSON envelope — there is no ``apiVersion`` signal
    at this granularity. Identity is the ``kind`` COLUMN alone. (In practice
    ``LessonLearned``/``Engram`` are flat-YAML, non-bundle docs — see the FS
    script's own docstring — so this table is expected to have zero
    matching rows, but the code does not assume that.)
  * ``dna_search_docs``      — lives in a SEPARATE optional store
    (``dna/adapters/search/pgvector_migrations.py``, extra
    ``search-pgvector``): UNIQUE ``(scope, kind, name, tenant)``. This table
    may not exist at all (pgvector extension/migrations are opt-in) — the
    migration checks for it with ``to_regclass`` and skips cleanly if
    absent, it does NOT assume it is there.
  * ``dna_outbox``           — audit/event log, ``id BIGSERIAL`` PK, no
    unique constraint on ``kind``. See ``_OUTBOX_DECISION`` below for the
    rewrite-vs-leave-alone call.

**Discrepancy vs the story's schema summary**: the story states
``dna_documents``' PK is ``(scope, kind, name)``. As of migration version 3
(Phase 8a, "tenant first-class column") the PK is
``(scope, kind, name, tenant)`` — ``tenant`` was added to the PK, not just
the table. The same is true of ``dna_bundle_entries``' PK. This module's
collision keys account for ``tenant`` accordingly; a check that ignored it
would UNDER-collision (miss real conflicts on a non-default tenant) or
OVER-collision (flag two different tenants' docs as colliding), either of
which is a mistake worth calling out explicitly.

Collision pre-flight (the main hazard, per the story): because ``kind``
lives inside four different PK/UNIQUE constraints, a pre-existing
``Engram``-kind row sharing the rest of a candidate row's key would abort
the ``UPDATE`` mid-run (Postgres raises a unique-violation and the whole
statement — or, without a wrapping transaction, everything already
committed before it — is at risk). This module ALWAYS runs the full
pre-flight first (read-only), across every table, and refuses to write
ANYTHING (non-zero exit, ``PgMigrationReport.has_collisions() is True``) if
even one collision is found anywhere. Dry-run (the default) reports the
same pre-flight, just never proceeds to a write.

Single transaction: every table's ``UPDATE`` runs inside ONE
``asyncpg`` transaction (``async with conn.transaction():``) — a
half-migrated store is worse than an unmigrated one, because ``kind_for()``
(``dna/kernel/instance.py:693``) matches on the bare kind name ignoring
``apiVersion``, so a doc renamed in one table but not another would resolve
*confusingly* (found by kind, inconsistent identity) rather than cleanly
(simply invisible).

This module is SDK-only tooling. It was NOT run against any real database
(local or dna-cloud) as part of authoring this story — it is exercised only
against ephemeral, throwaway Postgres schemas created by its own test suite
(``tests/test_migrate_engram_postgres_integration.py``).
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Identity constants — SINGLE SOURCE OF TRUTH is the FS script. scripts/ is
# not a package (no relative import), so load it by path the same way its
# own test suite does (tests/test_migrate_lesson_learned_to_engram.py).
# ---------------------------------------------------------------------------

_FS_SCRIPT_PATH = Path(__file__).resolve().parent / "migrate_lesson_learned_to_engram.py"


def _load_fs_module():
    spec = importlib.util.spec_from_file_location(
        "migrate_lesson_learned_to_engram", _FS_SCRIPT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_fs = _load_fs_module()
OLD_KIND: str = _fs.OLD_KIND
NEW_KIND: str = _fs.NEW_KIND
OLD_API_VERSION: str = _fs.OLD_API_VERSION
NEW_API_VERSION: str = _fs.NEW_API_VERSION

# Same trusted-config-only guard SqlAlchemySource applies to a Postgres
# schema identifier (it's f-string-interpolated into DDL/DML, can't be a
# bind param).
_VALID_SCHEMA_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

# ``dna_outbox`` DECISION (requirement 5): LEAVE IT ALONE, never rewritten.
#
# Argument for "leave immutable": dna_outbox is an event LOG, not a live
# identity surface. Nothing resolves Kind identity through it — Kind
# resolution is the kernel's exact (apiVersion, kind) tuple lookup over
# dna_documents-sourced instances (kernel/instance.py:686); dna_outbox rows
# are read by the eventbus (PostgresEventBus / pg_notify subscribers) purely
# to invalidate caches and checkpoint dna_versions_seq, keyed by
# (scope, tenant, id) — never by kind. Rewriting old rows would misrepresent
# history: an outbox row with kind='LessonLearned' genuinely recorded a
# write that happened under that identity at that time (the same reasoning
# a ledger or git history gets: you don't rewrite what a past commit said).
# It is also the weaker of the two choices operationally — a live consumer
# reading stale kind='LessonLearned' events off the bus mid-migration would
# only affect cache invalidation (best-effort, harmless if stale — the next
# read simply recomputes), never correctness of what gets served.
# Argument for rewriting (rejected): "consistency" — every row in the store
# says the same thing. Rejected because it falsifies the record for no
# operational gain, and dna_outbox is unbounded/append-only in spirit; a
# migration that rewrites it sets a precedent that outbox rows are mutable,
# which undermines its value as an audit trail for THE NEXT rename too.
# Implementation: the count of LessonLearned-kind outbox rows is still
# surfaced in the report (visibility for the human reviewing the dry run),
# but PgMigrationReport never issues an UPDATE against dna_outbox.
_OUTBOX_DECISION = "leave-immutable"


def _classify_doc(kind_col: str, raw: dict[str, Any]) -> str:
    """CANDIDATE / ALREADY_MIGRATED / ORPHAN / IRRELEVANT — the same 4-way
    rule as ``migrate_lesson_learned_to_engram._classify``, operating on a
    parsed JSON envelope (Postgres ``content`` is real JSON, not YAML text,
    so no regex is needed here)."""
    kind = raw.get("kind")
    api_version = raw.get("apiVersion")
    if kind == NEW_KIND:
        return "already_migrated" if api_version == NEW_API_VERSION else "orphan"
    if kind == OLD_KIND and api_version == OLD_API_VERSION:
        return "candidate"
    return "irrelevant"


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------


@dataclass
class TableReport:
    table: str
    candidates: int = 0
    already_migrated: int = 0
    orphans: int = 0
    content_kind_drift: int = 0
    collisions: list[tuple] = field(default_factory=list)
    skipped_missing_table: bool = False

    def summary(self) -> str:
        if self.skipped_missing_table:
            return f"  {self.table}: table not present — skipped"
        lines = [
            f"  {self.table}: candidates={self.candidates} "
            f"already_migrated={self.already_migrated} orphans={self.orphans}",
        ]
        if self.content_kind_drift:
            lines.append(
                f"    WARNING: {self.content_kind_drift} row(s) where the "
                "kind COLUMN disagrees with content->>'kind' (data "
                "integrity issue, unrelated to this migration — fix "
                "manually)."
            )
        if self.collisions:
            lines.append(f"    COLLISIONS ({len(self.collisions)}) — would abort the UPDATE:")
            for key in self.collisions:
                lines.append(f"      - {key!r}")
        return "\n".join(lines)


@dataclass
class PgMigrationReport:
    schema: str = "public"
    tables: dict[str, TableReport] = field(default_factory=dict)
    outbox_candidate_count: int = 0
    outbox_decision: str = _OUTBOX_DECISION
    applied: bool = False

    def has_collisions(self) -> bool:
        return any(t.collisions for t in self.tables.values())

    def total_candidates(self) -> int:
        return sum(t.candidates for t in self.tables.values())

    def summary(self) -> str:
        lines = [f"Postgres schema: {self.schema!r}"]
        for t in self.tables.values():
            lines.append(t.summary())
        lines.append(
            f"  dna_outbox: {self.outbox_candidate_count} LessonLearned-kind "
            f"row(s) found — decision: {self.outbox_decision} (never rewritten, "
            "see _OUTBOX_DECISION in migrate_engram_postgres.py)"
        )
        if self.has_collisions():
            lines.append(
                "\nABORTING: pre-existing Engram-kind row(s) collide with "
                "candidate(s) above. NOTHING was written. Resolve the "
                "collisions manually (rename/merge the conflicting docs) "
                "and re-run."
            )
        elif self.applied:
            lines.append(f"\nApplied: {self.total_candidates()} candidate row(s) rewritten across all tables.")
        else:
            lines.append(
                f"\nDry run — {self.total_candidates()} candidate row(s) would be "
                "rewritten. Re-run with --apply to write (after freezing "
                "writes — see docs/guides/engram-postgres-cutover.md)."
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pre-flight (read-only) per table shape
# ---------------------------------------------------------------------------


async def _table_exists(conn: Any, schema: str, table: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"{schema}.{table}"))


async def _preflight_content_table(
    conn: Any, schema: str, table: str, key_cols: tuple[str, ...],
) -> TableReport:
    """``dna_documents`` / ``dna_layer_documents`` shape: a JSON ``content``
    envelope + a denormalized ``kind`` column. Collision key = ``key_cols``
    (the PK minus ``kind``)."""
    report = TableReport(table=table)
    if not await _table_exists(conn, schema, table):
        report.skipped_missing_table = True
        return report

    cols = ", ".join(key_cols)
    rows = await conn.fetch(
        f"SELECT {cols}, kind, content FROM {schema}.{table} WHERE kind = $1 OR kind = $2",
        OLD_KIND, NEW_KIND,
    )
    engram_keys: set[tuple] = set()
    candidates: list[tuple] = []
    for r in rows:
        key = tuple(r[c] for c in key_cols)
        raw = json.loads(r["content"])
        if raw.get("kind") is not None and raw.get("kind") != r["kind"]:
            report.content_kind_drift += 1
        cls = _classify_doc(r["kind"], raw)
        if cls == "candidate":
            report.candidates += 1
            candidates.append(key)
        elif cls == "already_migrated":
            report.already_migrated += 1
        elif cls == "orphan":
            report.orphans += 1
        if r["kind"] == NEW_KIND:
            engram_keys.add(key)

    report.collisions = [k for k in candidates if k in engram_keys]
    return report


async def _preflight_versions(conn: Any, schema: str) -> TableReport:
    """``dna_versions``: real PK is a surrogate ``id`` — ``kind`` only
    participates in the PARTIAL unique index
    ``(scope, kind, name, tenant, semver) WHERE semver IS NOT NULL``. A
    collision is only possible between two rows that BOTH have semver set,
    so the key includes semver and rows with semver IS NULL are excluded
    from collision checking entirely (Postgres allows unlimited NULLs in a
    unique index)."""
    table = "dna_versions"
    report = TableReport(table=table)
    if not await _table_exists(conn, schema, table):
        report.skipped_missing_table = True
        return report

    rows = await conn.fetch(
        f"SELECT scope, name, tenant, semver, kind, content FROM {schema}.{table} "
        "WHERE kind = $1 OR kind = $2",
        OLD_KIND, NEW_KIND,
    )
    engram_keys: set[tuple] = set()
    candidates: list[tuple] = []
    for r in rows:
        raw = json.loads(r["content"])
        if raw.get("kind") is not None and raw.get("kind") != r["kind"]:
            report.content_kind_drift += 1
        cls = _classify_doc(r["kind"], raw)
        if cls == "candidate":
            report.candidates += 1
            if r["semver"] is not None:
                candidates.append((r["scope"], r["name"], r["tenant"], r["semver"]))
        elif cls == "already_migrated":
            report.already_migrated += 1
        elif cls == "orphan":
            report.orphans += 1
        if r["kind"] == NEW_KIND and r["semver"] is not None:
            engram_keys.add((r["scope"], r["name"], r["tenant"], r["semver"]))

    report.collisions = [k for k in candidates if k in engram_keys]
    return report


async def _preflight_kind_only_table(
    conn: Any, schema: str, table: str, key_cols: tuple[str, ...],
) -> TableReport:
    """``dna_bundle_entries`` / ``dna_search_docs`` shape: no JSON envelope
    at this granularity, ``kind`` column is the ONLY identity signal — every
    ``kind = 'LessonLearned'`` row is a candidate (no apiVersion to
    cross-check against)."""
    report = TableReport(table=table)
    if not await _table_exists(conn, schema, table):
        report.skipped_missing_table = True
        return report

    cols = ", ".join(key_cols)
    rows = await conn.fetch(
        f"SELECT {cols}, kind FROM {schema}.{table} WHERE kind = $1 OR kind = $2",
        OLD_KIND, NEW_KIND,
    )
    engram_keys: set[tuple] = set()
    candidates: list[tuple] = []
    for r in rows:
        key = tuple(r[c] for c in key_cols)
        if r["kind"] == OLD_KIND:
            report.candidates += 1
            candidates.append(key)
        else:
            report.already_migrated += 1
        if r["kind"] == NEW_KIND:
            engram_keys.add(key)

    report.collisions = [k for k in candidates if k in engram_keys]
    return report


# ---------------------------------------------------------------------------
# Apply (write) — only called after a collision-free pre-flight, inside the
# caller's single transaction.
# ---------------------------------------------------------------------------


def _now() -> str:
    """Same ISO-8601 TEXT convention ``SqlAlchemySource._now()`` writes into
    ``updated_at`` — mirrored here (not imported) because that helper is
    private to the adapter module."""
    return datetime.now(timezone.utc).isoformat()


async def _apply_content_table(
    conn: Any, schema: str, table: str, *, touch_updated_at: bool = True,
) -> None:
    """Rewrite ``kind``/``content`` for every candidate row. ``touch_updated_at``
    is False for ``dna_versions``, which has no ``updated_at`` column at all
    (only ``created_at`` — an immutable historical timestamp this migration
    must NOT touch, since it did not create a new version, it corrected the
    identity of an existing one). ``dna_documents``/``dna_layer_documents``
    both have a real ``updated_at TEXT`` column (same ISO-8601 convention
    ``SqlAlchemySource`` writes); a consumer that treats it as a staleness
    signal must see this rewrite, so it is bumped here too."""
    set_clause = "kind = $1, content = jsonb_set(jsonb_set(content::jsonb, '{kind}', to_jsonb($1::text)), '{apiVersion}', to_jsonb($2::text))::text"
    params: list[Any] = [NEW_KIND, NEW_API_VERSION, OLD_KIND, OLD_API_VERSION]
    if touch_updated_at:
        set_clause += ", updated_at = $5"
        params.append(_now())
    await conn.execute(
        f"""
        UPDATE {schema}.{table}
        SET {set_clause}
        WHERE kind = $3 AND content::jsonb->>'apiVersion' = $4
        """,
        *params,
    )


async def _apply_kind_only_table(conn: Any, schema: str, table: str) -> None:
    await conn.execute(
        f"UPDATE {schema}.{table} SET kind = $1 WHERE kind = $2",
        NEW_KIND, OLD_KIND,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def migrate_postgres(
    dsn: str, *, schema: str = "public", apply: bool = False,
) -> PgMigrationReport:
    """Dry-run (default) or ``apply``-and-write migration of the
    ``LessonLearned`` -> ``Engram`` identity across every Postgres table
    that carries it. ALWAYS runs the full pre-flight first; if it finds any
    collision, NOTHING is written (``report.has_collisions()`` — check this
    even on ``apply=True``, a collision aborts regardless)."""
    import asyncpg

    if not _VALID_SCHEMA_IDENT.match(schema):
        raise ValueError(
            f"invalid Postgres schema identifier {schema!r}: must match "
            f"{_VALID_SCHEMA_IDENT.pattern}"
        )

    conn = await asyncpg.connect(dsn)
    try:
        report = PgMigrationReport(schema=schema)

        report.tables["dna_documents"] = await _preflight_content_table(
            conn, schema, "dna_documents", ("scope", "name", "tenant"),
        )
        report.tables["dna_versions"] = await _preflight_versions(conn, schema)
        report.tables["dna_layer_documents"] = await _preflight_content_table(
            conn, schema, "dna_layer_documents",
            ("scope", "layer_id", "layer_value", "name"),
        )
        report.tables["dna_bundle_entries"] = await _preflight_kind_only_table(
            conn, schema, "dna_bundle_entries", ("scope", "name", "entry_path", "tenant"),
        )
        report.tables["dna_search_docs"] = await _preflight_kind_only_table(
            conn, schema, "dna_search_docs", ("scope", "name", "tenant"),
        )

        if await _table_exists(conn, schema, "dna_outbox"):
            report.outbox_candidate_count = await conn.fetchval(
                f"SELECT count(*) FROM {schema}.dna_outbox WHERE kind = $1", OLD_KIND,
            )

        if report.has_collisions():
            return report  # HARD ABORT — caller must not proceed. Nothing written.

        if apply:
            async with conn.transaction():
                for table, tr in report.tables.items():
                    if tr.skipped_missing_table or tr.candidates == 0:
                        continue
                    if table in ("dna_documents", "dna_layer_documents"):
                        await _apply_content_table(conn, schema, table)
                    elif table == "dna_versions":
                        await _apply_content_table(conn, schema, table, touch_updated_at=False)
                    else:
                        await _apply_kind_only_table(conn, schema, table)
            report.applied = True
        return report
    finally:
        await conn.close()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dsn", help="postgresql:// DSN (asyncpg-compatible).")
    parser.add_argument("--schema", default="public", help="Postgres schema (default: public).")
    parser.add_argument("--apply", action="store_true", help="Actually write. Default is dry-run.")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = asyncio.run(migrate_postgres(args.dsn, schema=args.schema, apply=args.apply))
    print(report.summary())
    if report.has_collisions():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
