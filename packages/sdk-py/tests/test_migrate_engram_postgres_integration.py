"""Integration tests for ``scripts/migrate_engram_postgres.py`` — real
Postgres, no mocks (s-engram-migration-postgres).

Provisioning: same gate as the rest of the pg-integration suite
(``requires_postgres`` marker, ``tests/conftest.py``) — set ``DATABASE_URL``
/ ``DNA_PG_TEST_URL`` / ``DNA_PG_TEST_DSN`` to a real (local or ephemeral)
Postgres to run these; they auto-skip otherwise, same as
``test_layers_integration.py`` / ``test_mi_exclusion_integration_pg.py``.

Each test gets a FRESH throwaway schema (mirrors
``test_layers_integration.py``'s ``_pg_env()``), bootstrapped by the REAL
``SqlAlchemySource.connect()`` (applies ``PG_MIGRATIONS`` 1..9 for real), so
the tables/indexes under test are byte-identical to what a production
Postgres-backed DNA store has — never a hand-rolled subset schema. Rows are
seeded through the SAME writer paths production traffic uses
(``save_document`` / ``save_layer_document`` / ``write_bundle_entry``), so
the outbox side effects, JSON envelope shape, and tenant defaulting are all
the real thing, not a stub.

``dna_search_docs`` (the pgvector search store) needs the ``vector``
Postgres extension, which this local dev environment does not have
installed — every test here therefore exercises the REAL
"table absent → skip cleanly" path for it (this is also the honest
production case for any dna-cloud deployment that never opted into
``search-pgvector``). The identical generic collision-detection code path
``dna_search_docs`` would use (``_preflight_kind_only_table`` /
``_apply_kind_only_table`` — the same functions ``dna_bundle_entries``
uses) is separately exercised end-to-end against a throwaway table with a
REAL ``UNIQUE`` constraint in ``test_generic_kind_only_collision_detection_is_real``,
so the collision logic itself is proven against a live constraint even
though the specific ``dna_search_docs`` table was not.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.requires_postgres, pytest.mark.asyncio]

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pgmig = _load("migrate_engram_postgres", "migrate_engram_postgres.py")

OLD_KIND = pgmig.OLD_KIND
NEW_KIND = pgmig.NEW_KIND
OLD_API_VERSION = pgmig.OLD_API_VERSION
NEW_API_VERSION = pgmig.NEW_API_VERSION


def _dsn() -> str:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DNA_PG_TEST_URL")
        or os.environ.get("DNA_PG_TEST_DSN")
        or ""
    )


async def _fresh_schema():
    import asyncpg

    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    dsn = _dsn()
    schema = f"dna_engrampg_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    sa_url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    src = SqlAlchemySource(sa_url, schema=schema)
    await src.connect()  # applies PG_MIGRATIONS 1..9 for real

    async def cleanup() -> None:
        await src.close()
        c = await asyncpg.connect(dsn)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()

    return dsn, schema, src, cleanup


def _lesson_raw(name: str, summary: str = "A test memory.") -> dict:
    return {
        "kind": OLD_KIND,
        "apiVersion": OLD_API_VERSION,
        "metadata": {"name": name},
        "spec": {"summary": summary, "area": "testing"},
    }


def _engram_raw(name: str, summary: str = "Already migrated.") -> dict:
    return {
        "kind": NEW_KIND,
        "apiVersion": NEW_API_VERSION,
        "metadata": {"name": name},
        "spec": {"summary": summary},
    }


def _story_raw(name: str) -> dict:
    return {
        "kind": "Story",
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "metadata": {"name": name},
        "spec": {"title": "unrelated"},
    }


# ---------------------------------------------------------------------------
# 1. Clean migration across all tables
# ---------------------------------------------------------------------------


async def test_clean_migration_across_all_tables():
    dsn, schema, src, cleanup = await _fresh_schema()
    try:
        scope = "test-scope"

        # documents + versions + outbox (real side effect of save_document)
        await src.save_document(scope, OLD_KIND, "rem-abc123", _lesson_raw("rem-abc123"))
        # an unrelated doc must be left completely alone
        await src.save_document(scope, "Story", "s-unrelated", _story_raw("s-unrelated"))

        # layer_documents (non-tenant layer — tenant layers route through
        # documents.tenant instead, see save_layer_document)
        await src.save_layer_document(
            scope, "role", "qa", OLD_KIND, "rem-layered",
            _lesson_raw("rem-layered"),
        )

        # bundle_entries
        await src.write_bundle_entry(
            scope, "lessons-learned", "rem-bundled", "LESSON_LEARNED.md",
            "# A bundled memory\n", kind=OLD_KIND,
        )

        # edges — not managed by SqlAlchemySource, raw insert (mirrors the
        # dna-cloud app.py write-hook observer that populates this table)
        import asyncpg
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                f"INSERT INTO {schema}.dna_edges "
                "(scope, from_kind, from_name, to_kind, to_name, edge_type, tenant) "
                "VALUES ($1,$2,$3,$4,$5,'spec-ref','')",
                scope, OLD_KIND, "rem-abc123", "Story", "s-unrelated",
            )
            await conn.execute(
                f"INSERT INTO {schema}.dna_edges "
                "(scope, from_kind, from_name, to_kind, to_name, edge_type, tenant) "
                "VALUES ($1,$2,$3,$4,$5,'spec-ref','')",
                scope, "Story", "s-unrelated", OLD_KIND, "rem-abc123",
            )
            # a totally unrelated edge — must survive untouched
            await conn.execute(
                f"INSERT INTO {schema}.dna_edges "
                "(scope, from_kind, from_name, to_kind, to_name, edge_type, tenant) "
                "VALUES ($1,'Story','s-unrelated','Feature','f-x','spec-ref','')",
                scope,
            )
            # snapshot the "before" timestamps to prove the minor updated_at
            # consistency fix: dna_documents/dna_layer_documents get touched,
            # dna_versions' created_at (an immutable historical timestamp)
            # must NOT be touched by this migration.
            before_doc_updated_at = await conn.fetchval(
                f"SELECT updated_at FROM {schema}.dna_documents "
                "WHERE scope=$1 AND name='rem-abc123'", scope,
            )
            before_layer_updated_at = await conn.fetchval(
                f"SELECT updated_at FROM {schema}.dna_layer_documents "
                "WHERE scope=$1 AND name='rem-layered'", scope,
            )
            before_version_created_at = await conn.fetchval(
                f"SELECT created_at FROM {schema}.dna_versions "
                "WHERE scope=$1 AND name='rem-abc123'", scope,
            )
        finally:
            await conn.close()

        report = await pgmig.migrate_postgres(dsn, schema=schema, apply=True)

        assert not report.has_collisions(), report.summary()
        assert report.applied is True
        assert report.tables["dna_documents"].candidates == 1
        assert report.tables["dna_versions"].candidates == 1
        assert report.tables["dna_layer_documents"].candidates == 1
        assert report.tables["dna_bundle_entries"].candidates == 1
        assert report.tables["dna_edges"].candidates == 2  # one edge per side
        assert report.tables["dna_search_docs"].skipped_missing_table is True
        # outbox: at least the 3 substantive writes above (save_document x2
        # incl. version insert emits once per save_document call, layer
        # save routes through save_document too when layer_id=='tenant'
        # only — role layer does NOT emit outbox; write_bundle_entry does
        # not emit outbox either). At minimum the rem-abc123 save_document
        # emitted one LessonLearned outbox event.
        assert report.outbox_candidate_count >= 1
        assert report.outbox_decision == "leave-immutable"

        conn = await __import__("asyncpg").connect(dsn)
        try:
            # documents: renamed
            row = await conn.fetchrow(
                f"SELECT kind, content FROM {schema}.dna_documents "
                "WHERE scope=$1 AND name='rem-abc123'", scope,
            )
            assert row["kind"] == NEW_KIND
            import json as _json
            content = _json.loads(row["content"])
            assert content["kind"] == NEW_KIND
            assert content["apiVersion"] == NEW_API_VERSION
            assert content["spec"]["summary"] == "A test memory."  # untouched

            doc_updated_at = await conn.fetchval(
                f"SELECT updated_at FROM {schema}.dna_documents "
                "WHERE scope=$1 AND name='rem-abc123'", scope,
            )
            assert doc_updated_at != before_doc_updated_at, (
                "dna_documents.updated_at must be bumped by the rewrite — a "
                "consumer using it as a staleness signal must see this change"
            )

            # unrelated Story doc untouched
            row2 = await conn.fetchrow(
                f"SELECT kind FROM {schema}.dna_documents "
                "WHERE scope=$1 AND name='s-unrelated'", scope,
            )
            assert row2["kind"] == "Story"

            # versions: renamed, but created_at is an immutable historical
            # timestamp — this migration corrected an identity, it did not
            # create a new version, so created_at must NOT change.
            vrow = await conn.fetchrow(
                f"SELECT kind, created_at FROM {schema}.dna_versions "
                "WHERE scope=$1 AND name='rem-abc123'", scope,
            )
            assert vrow["kind"] == NEW_KIND
            assert vrow["created_at"] == before_version_created_at, (
                "dna_versions.created_at must NOT be touched — no updated_at "
                "column exists on this table by design"
            )

            # layer_documents: renamed, and updated_at bumped (same
            # consistency fix as dna_documents).
            lrow = await conn.fetchrow(
                f"SELECT kind, updated_at FROM {schema}.dna_layer_documents "
                "WHERE scope=$1 AND name='rem-layered'", scope,
            )
            assert lrow["kind"] == NEW_KIND
            assert lrow["updated_at"] != before_layer_updated_at

            # bundle_entries: renamed
            brow = await conn.fetchrow(
                f"SELECT kind FROM {schema}.dna_bundle_entries "
                "WHERE scope=$1 AND name='rem-bundled'", scope,
            )
            assert brow["kind"] == NEW_KIND

            # edges: BOTH directions renamed on the LessonLearned side only
            erows = await conn.fetch(
                f"SELECT from_kind, to_kind FROM {schema}.dna_edges "
                "WHERE scope=$1 AND (from_name='rem-abc123' OR to_name='rem-abc123')",
                scope,
            )
            assert len(erows) == 2
            for r in erows:
                assert NEW_KIND in (r["from_kind"], r["to_kind"])
                assert OLD_KIND not in (r["from_kind"], r["to_kind"])

            # the unrelated edge is completely untouched
            urow = await conn.fetchrow(
                f"SELECT from_kind, to_kind FROM {schema}.dna_edges "
                "WHERE scope=$1 AND from_name='s-unrelated' AND to_name='f-x'",
                scope,
            )
            assert urow["from_kind"] == "Story"
            assert urow["to_kind"] == "Feature"

            # outbox: NEVER rewritten — the row(s) still say LessonLearned
            orows = await conn.fetch(
                f"SELECT kind FROM {schema}.dna_outbox WHERE scope=$1", scope,
            )
            old_kind_outbox = [r for r in orows if r["kind"] == OLD_KIND]
            assert len(old_kind_outbox) >= 1, (
                "dna_outbox must remain an immutable historical record — "
                "at least one LessonLearned-kind event must survive"
            )
        finally:
            await conn.close()
    finally:
        await cleanup()


# ---------------------------------------------------------------------------
# 2. Idempotency — re-running an already-applied migration is a no-op
# ---------------------------------------------------------------------------


async def test_idempotent_rerun_is_a_noop():
    dsn, schema, src, cleanup = await _fresh_schema()
    try:
        scope = "test-scope"
        await src.save_document(scope, OLD_KIND, "rem-abc123", _lesson_raw("rem-abc123"))

        first = await pgmig.migrate_postgres(dsn, schema=schema, apply=True)
        assert not first.has_collisions()
        assert first.tables["dna_documents"].candidates == 1

        second = await pgmig.migrate_postgres(dsn, schema=schema, apply=True)
        assert not second.has_collisions()
        assert second.tables["dna_documents"].candidates == 0
        assert second.tables["dna_documents"].already_migrated == 1
        assert second.tables["dna_versions"].candidates == 0
        assert second.tables["dna_versions"].already_migrated == 1
    finally:
        await cleanup()


# ---------------------------------------------------------------------------
# 3. Collision pre-flight aborts the WHOLE run before any write
# ---------------------------------------------------------------------------


async def test_collision_preflight_aborts_before_any_write():
    dsn, schema, src, cleanup = await _fresh_schema()
    try:
        scope = "test-scope"
        # A candidate...
        await src.save_document(scope, OLD_KIND, "rem-dup", _lesson_raw("rem-dup"))
        # ...and a PRE-EXISTING Engram row at the exact key it would land on.
        await src.save_document(scope, NEW_KIND, "rem-dup", _engram_raw("rem-dup"))
        # Also seed a clean, non-colliding candidate in a DIFFERENT table
        # (bundle_entries) to prove the abort is store-wide, not just the
        # documents table.
        await src.write_bundle_entry(
            scope, "lessons-learned", "rem-clean", "LESSON_LEARNED.md",
            "# clean\n", kind=OLD_KIND,
        )

        report = await pgmig.migrate_postgres(dsn, schema=schema, apply=True)

        assert report.has_collisions()
        assert report.applied is False
        assert ("test-scope", "rem-dup", "") in report.tables["dna_documents"].collisions

        import asyncpg
        conn = await asyncpg.connect(dsn)
        try:
            # NOTHING written — the LessonLearned row is still LessonLearned.
            row = await conn.fetchrow(
                f"SELECT kind FROM {schema}.dna_documents "
                "WHERE scope=$1 AND name='rem-dup' AND kind=$2", scope, OLD_KIND,
            )
            assert row is not None, "candidate row must be untouched after an aborted run"

            # The clean bundle_entries candidate — in a DIFFERENT table from
            # where the collision was found — must ALSO be untouched. This
            # is the single-transaction guarantee: a collision anywhere
            # blocks writes everywhere.
            brow = await conn.fetchrow(
                f"SELECT kind FROM {schema}.dna_bundle_entries "
                "WHERE scope=$1 AND name='rem-clean'", scope,
            )
            assert brow["kind"] == OLD_KIND
        finally:
            await conn.close()
    finally:
        await cleanup()


async def test_edges_collision_on_either_side_is_detected():
    """A pre-existing edge that already has 'Engram' in the exact slot a
    candidate edge would rewrite to must be caught too — PK collision is
    independent per from_kind/to_kind side."""
    dsn, schema, src, cleanup = await _fresh_schema()
    try:
        scope = "test-scope"
        import asyncpg
        conn = await asyncpg.connect(dsn)
        try:
            # candidate: from_kind=LessonLearned
            await conn.execute(
                f"INSERT INTO {schema}.dna_edges "
                "(scope, from_kind, from_name, to_kind, to_name, edge_type, tenant) "
                "VALUES ($1,$2,'rem-x','Story','s-y','spec-ref','')",
                scope, OLD_KIND,
            )
            # a pre-existing row that already occupies the post-rewrite key
            await conn.execute(
                f"INSERT INTO {schema}.dna_edges "
                "(scope, from_kind, from_name, to_kind, to_name, edge_type, tenant) "
                "VALUES ($1,$2,'rem-x','Story','s-y','spec-ref','')",
                scope, NEW_KIND,
            )
        finally:
            await conn.close()

        report = await pgmig.migrate_postgres(dsn, schema=schema, apply=True)
        assert report.has_collisions()
        assert report.tables["dna_edges"].collisions
        assert report.applied is False
    finally:
        await cleanup()


async def test_edges_candidate_vs_candidate_collision_is_detected():
    """Regression for a review finding: TWO independently-valid, currently
    DISTINCT rows can rename INTO each other because from_kind/to_kind are
    independent columns — neither row's CURRENT key equals the other's
    target, so a pre-flight that only checks candidates against stationary
    (non-renaming) rows misses this entirely.

        Row A: (from_kind=LessonLearned, from_name=X, to_kind=Engram,   to_name=Y)
        Row B: (from_kind=Engram,        from_name=X, to_kind=LessonLearned, to_name=Y)

    Both rename to (Engram, X, Engram, Y). Before the fix, the dry run
    reported a clean bill of health (has_collisions=False, 2 candidates, 0
    collisions) and --apply raised a live asyncpg.UniqueViolationError on
    dna_edges_pkey — the exact failure the pre-flight exists to prevent."""
    dsn, schema, src, cleanup = await _fresh_schema()
    try:
        scope = "test-scope"
        import asyncpg
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                f"INSERT INTO {schema}.dna_edges "
                "(scope, from_kind, from_name, to_kind, to_name, edge_type, tenant) "
                "VALUES ($1,$2,'X','Engram','Y','spec-ref','')",
                scope, OLD_KIND,
            )
            await conn.execute(
                f"INSERT INTO {schema}.dna_edges "
                "(scope, from_kind, from_name, to_kind, to_name, edge_type, tenant) "
                "VALUES ($1,'Engram','X',$2,'Y','spec-ref','')",
                scope, OLD_KIND,
            )
        finally:
            await conn.close()

        dry_run = await pgmig.migrate_postgres(dsn, schema=schema, apply=False)
        assert dry_run.tables["dna_edges"].candidates == 2
        assert dry_run.has_collisions(), (
            "candidate-vs-candidate convergence must be caught by the dry run — "
            "this is exactly the case a stationary-rows-only check misses"
        )
        assert len(dry_run.tables["dna_edges"].collisions) == 2

        applied = await pgmig.migrate_postgres(dsn, schema=schema, apply=True)
        assert applied.has_collisions()
        assert applied.applied is False, "must refuse to write, not just report"

        # Nothing written — both rows still carry their original kinds.
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                f"SELECT from_kind, to_kind FROM {schema}.dna_edges "
                "WHERE scope=$1 AND from_name='X' AND to_name='Y'", scope,
            )
            assert len(rows) == 2
            kinds = {(r["from_kind"], r["to_kind"]) for r in rows}
            assert kinds == {(OLD_KIND, "Engram"), ("Engram", OLD_KIND)}
        finally:
            await conn.close()
    finally:
        await cleanup()


# ---------------------------------------------------------------------------
# 4. Dry run writes nothing
# ---------------------------------------------------------------------------


async def test_dry_run_writes_nothing():
    dsn, schema, src, cleanup = await _fresh_schema()
    try:
        scope = "test-scope"
        await src.save_document(scope, OLD_KIND, "rem-abc123", _lesson_raw("rem-abc123"))

        report = await pgmig.migrate_postgres(dsn, schema=schema, apply=False)

        assert not report.has_collisions()
        assert report.applied is False
        assert report.tables["dna_documents"].candidates == 1

        import asyncpg
        conn = await asyncpg.connect(dsn)
        try:
            row = await conn.fetchrow(
                f"SELECT kind FROM {schema}.dna_documents "
                "WHERE scope=$1 AND name='rem-abc123'", scope,
            )
            assert row["kind"] == OLD_KIND, "dry run must not write anything"
        finally:
            await conn.close()
    finally:
        await cleanup()


# ---------------------------------------------------------------------------
# 5. The generic kind-only-table collision path (search_docs' code path),
#    proven against a REAL UNIQUE constraint since pgvector isn't installed
#    in this dev environment to create the real dna_search_docs table.
# ---------------------------------------------------------------------------


async def test_generic_kind_only_collision_detection_is_real():
    dsn, schema, src, cleanup = await _fresh_schema()
    try:
        import asyncpg
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                f"CREATE TABLE {schema}.dna_test_kindonly ("
                "scope TEXT NOT NULL, name TEXT NOT NULL, tenant TEXT NOT NULL DEFAULT '', "
                "kind TEXT NOT NULL, UNIQUE (scope, kind, name, tenant))"
            )
            await conn.execute(
                f"INSERT INTO {schema}.dna_test_kindonly (scope, name, tenant, kind) "
                "VALUES ('s', 'n', '', $1)", OLD_KIND,
            )
            await conn.execute(
                f"INSERT INTO {schema}.dna_test_kindonly (scope, name, tenant, kind) "
                "VALUES ('s', 'n2', '', $1)", NEW_KIND,
            )

            report = await pgmig._preflight_kind_only_table(
                conn, schema, "dna_test_kindonly", ("scope", "name", "tenant"),
            )
            assert report.candidates == 1
            assert not report.collisions

            # A real UPDATE with the real UNIQUE constraint must succeed
            # cleanly (no collision here).
            await pgmig._apply_kind_only_table(conn, schema, "dna_test_kindonly")
            row = await conn.fetchrow(
                f"SELECT kind FROM {schema}.dna_test_kindonly WHERE name='n'"
            )
            assert row["kind"] == NEW_KIND

            # Now create an actual collision and prove the REAL constraint
            # would reject a naive UPDATE (i.e. the pre-flight is not
            # theatre — Postgres itself enforces this).
            await conn.execute(
                f"INSERT INTO {schema}.dna_test_kindonly (scope, name, tenant, kind) "
                "VALUES ('s', 'dup', '', $1)", OLD_KIND,
            )
            await conn.execute(
                f"INSERT INTO {schema}.dna_test_kindonly (scope, name, tenant, kind) "
                "VALUES ('s', 'dup', '', $1)", NEW_KIND,
            )
            report2 = await pgmig._preflight_kind_only_table(
                conn, schema, "dna_test_kindonly", ("scope", "name", "tenant"),
            )
            assert ("s", "dup", "") in report2.collisions

            with pytest.raises(asyncpg.UniqueViolationError):
                async with conn.transaction():
                    await pgmig._apply_kind_only_table(conn, schema, "dna_test_kindonly")
        finally:
            await conn.close()
    finally:
        await cleanup()


# ---------------------------------------------------------------------------
# 6. Missing dna_search_docs is a clean skip, not an error
# ---------------------------------------------------------------------------


async def test_missing_search_docs_table_is_a_clean_skip():
    dsn, schema, src, cleanup = await _fresh_schema()
    try:
        report = await pgmig.migrate_postgres(dsn, schema=schema, apply=False)
        assert report.tables["dna_search_docs"].skipped_missing_table is True
        assert not report.has_collisions()
    finally:
        await cleanup()
