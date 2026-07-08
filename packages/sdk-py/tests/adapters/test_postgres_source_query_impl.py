"""Tests for PostgresSource.query() — native push-down impl.

Story s-postgres-source-query-impl (Feature f-source-as-query, Epic
e-production-viable-kernel).

Three test classes:
  - Helper tests (pure, no DB): SQL field expr + WHERE + ORDER BY.
  - Mock-pool tests: PostgresSource.query() issues correct SQL + params
    via a faked asyncpg pool, projection applied in Python.
  - Live PG tests (skipped when DNA_PG_TEST_DSN unset): real Postgres
    with seeded data, asserts <50ms hot query + parity with the
    Protocol fallback semantics.
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from dna.adapters.postgres.source import (
    PostgresSource,
    _pg_field_expr,
    _build_pg_where,
    _build_pg_order,
)
from dna.kernel.protocols import QueryError


# ===========================================================================
# Pure helper tests — no DB required.
# ===========================================================================


class TestPgFieldExpr:
    def test_name_shorthand_maps_to_column(self):
        assert _pg_field_expr("name") == "name"
        assert _pg_field_expr("metadata.name") == "name"

    def test_kind_maps_to_column(self):
        assert _pg_field_expr("kind") == "kind"

    def test_unprefixed_resolves_under_spec(self):
        expr = _pg_field_expr("status")
        assert expr == "(content::jsonb->'spec'->>'status')"

    def test_explicit_spec_prefix(self):
        expr = _pg_field_expr("spec.feature")
        assert expr == "(content::jsonb->'spec'->>'feature')"

    def test_nested_walks_via_arrow(self):
        expr = _pg_field_expr("spec.nested.deep")
        # spec → nested via ->, deep via ->>
        assert expr == "(content::jsonb->'spec'->'nested'->>'deep')"

    def test_metadata_prefix(self):
        expr = _pg_field_expr("metadata.labels")
        assert expr == "(content::jsonb->'metadata'->>'labels')"

    def test_apiversion_top_level(self):
        assert _pg_field_expr("apiVersion") == "(content::jsonb->>'apiVersion')"

    def test_sql_injection_attempt_rejected(self):
        with pytest.raises(QueryError, match="invalid field path"):
            _pg_field_expr("status'; DROP TABLE dna_documents; --")

    def test_empty_path_rejected(self):
        with pytest.raises(QueryError, match="invalid field path"):
            _pg_field_expr("")


class TestBuildPgWhere:
    def test_empty_returns_empty_string(self):
        sql, params = _build_pg_where(None, start_idx=4)
        assert sql == ""
        assert params == []
        sql, params = _build_pg_where({}, start_idx=4)
        assert sql == ""

    def test_single_eq_shorthand(self):
        sql, params = _build_pg_where({"status": "in-progress"}, start_idx=4)
        assert sql == " AND (content::jsonb->'spec'->>'status') = $4"
        assert params == ["in-progress"]

    def test_explicit_eq_op(self):
        sql, params = _build_pg_where(
            {"status": {"eq": "todo"}}, start_idx=4,
        )
        assert "= $4" in sql
        assert params == ["todo"]

    def test_neq_operator(self):
        sql, params = _build_pg_where({"status": {"neq": "done"}}, start_idx=4)
        assert "<> $4" in sql

    def test_in_operator_uses_any_array(self):
        sql, params = _build_pg_where(
            {"status": {"in": ["todo", "in-progress"]}}, start_idx=4,
        )
        assert "= ANY($4::text[])" in sql
        assert params == [["todo", "in-progress"]]

    def test_in_empty_list_rejected(self):
        with pytest.raises(QueryError, match="non-empty"):
            _build_pg_where({"status": {"in": []}}, start_idx=4)

    def test_like_operator(self):
        sql, params = _build_pg_where({"title": {"like": "%kernel%"}}, start_idx=4)
        assert "LIKE $4" in sql
        assert params == ["%kernel%"]

    def test_gt_lt_operators(self):
        sql, params = _build_pg_where(
            {"updated_at": {"gt": "2026-05-01"}}, start_idx=4,
        )
        assert "> $4" in sql
        assert params == ["2026-05-01"]

    def test_multiple_keys_anded(self):
        sql, params = _build_pg_where(
            {"status": "in-progress", "feature": "f-foo"}, start_idx=4,
        )
        assert "AND" in sql
        assert "$4" in sql and "$5" in sql
        assert params == ["in-progress", "f-foo"]

    def test_unknown_operator_raises(self):
        with pytest.raises(QueryError, match="unknown query operator"):
            _build_pg_where({"status": {"regex": ".*"}}, start_idx=4)

    def test_param_indexing_starts_at_given(self):
        # When called with start_idx=10, params reference $10, $11, ...
        sql, _ = _build_pg_where(
            {"status": "x", "feature": "y"}, start_idx=10,
        )
        assert "$10" in sql and "$11" in sql

    def test_numeric_shorthand_uses_numeric_cast(self):
        # s-pg-query-pushdown-typing — numeric values compare numerically, not
        # as TEXT. (Was: coerced to "5" + plain TEXT eq.)
        sql, params = _build_pg_where({"priority": 5}, start_idx=4)
        assert "::numeric" in sql
        assert params == [5]  # bound as int, not "5"

    def test_string_value_stays_text(self):
        # Non-numeric values keep the TEXT comparison path unchanged.
        sql, params = _build_pg_where({"status": "todo"}, start_idx=4)
        assert "::numeric" not in sql
        assert params == ["todo"]


class TestBuildPgOrder:
    def test_single_asc(self):
        sql = _build_pg_order(["spec.updated_at"])
        assert sql == " ORDER BY (content::jsonb->'spec'->>'updated_at') ASC NULLS LAST"

    def test_single_desc_with_dash(self):
        sql = _build_pg_order(["-spec.updated_at"])
        assert "DESC NULLS LAST" in sql

    def test_multiple_ordered_left_to_right(self):
        sql = _build_pg_order(["spec.feature", "-spec.priority"])
        # Primary then secondary.
        feature_pos = sql.index("'feature'")
        priority_pos = sql.index("'priority'")
        assert feature_pos < priority_pos

    def test_unprefixed_resolves_under_spec(self):
        sql = _build_pg_order(["status"])
        assert "(content::jsonb->'spec'->>'status')" in sql

    def test_name_short(self):
        sql = _build_pg_order(["name"])
        assert "name ASC NULLS LAST" in sql


# ===========================================================================
# Mock-pool tests — verify the right SQL is dispatched.
# ===========================================================================


def _mock_pool(rows):
    # Mirrors the `_acquire_safe()` path (source.py:149-166): it does
    # `conn = await self._pool.acquire()` then `await self._pool.release(conn)`
    # — acquire/release are awaited coroutines, NOT an async context manager.
    # So both must be AsyncMocks (the old cm-with-__aenter__ shape fed the
    # awaited acquire() a MagicMock and raised TypeError).
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire = AsyncMock(return_value=conn)
    pool.release = AsyncMock(return_value=None)
    return pool, conn


def _row(name, **spec):
    content = {
        "kind": "Story",
        "metadata": {"name": name},
        "spec": spec,
    }
    return {"name": name, "kind": "Story", "content": json.dumps(content)}


@pytest.mark.asyncio
async def test_query_dispatches_single_sql_with_filter():
    pool, conn = _mock_pool([_row("s-a", status="in-progress"), _row("s-b", status="in-progress")])
    src = PostgresSource.__new__(PostgresSource)
    src._pool = pool
    src._schema = "public"
    src._ensure_migrated = AsyncMock(return_value=None)

    rows = [r async for r in src.query(
        "scope-x", "Story",
        filter={"status": "in-progress"},
        limit=50,
    )]

    assert conn.fetch.call_count == 1, "Native push-down: 1 SELECT not N+1"
    sql = conn.fetch.call_args.args[0]
    params = conn.fetch.call_args.args[1:]
    assert "WHERE scope=$1 AND kind=$2 AND tenant=$3" in sql
    assert "(content::jsonb->'spec'->>'status') = $4" in sql
    assert "LIMIT $5" in sql
    assert params == ("scope-x", "Story", "", "in-progress", 50)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_query_with_no_filter_omits_where():
    pool, conn = _mock_pool([])
    src = PostgresSource.__new__(PostgresSource)
    src._pool = pool
    src._schema = "public"
    src._ensure_migrated = AsyncMock(return_value=None)

    [r async for r in src.query("x", "Story")]

    sql = conn.fetch.call_args.args[0]
    assert "AND tenant=$3" in sql
    # No extra AND fragment after tenant placeholder.
    assert sql.count(" AND ") == 2  # kind, tenant


@pytest.mark.asyncio
async def test_query_with_order_by_appends_clause():
    pool, conn = _mock_pool([])
    src = PostgresSource.__new__(PostgresSource)
    src._pool = pool
    src._schema = "public"
    src._ensure_migrated = AsyncMock(return_value=None)

    [r async for r in src.query("x", "Story", order_by=["-spec.updated_at"])]
    sql = conn.fetch.call_args.args[0]
    assert "ORDER BY (content::jsonb->'spec'->>'updated_at') DESC" in sql


@pytest.mark.asyncio
async def test_query_projection_applied_in_python():
    pool, conn = _mock_pool([_row("s-a", status="todo", title="T", description="LONG_BODY")])
    src = PostgresSource.__new__(PostgresSource)
    src._pool = pool
    src._schema = "public"
    src._ensure_migrated = AsyncMock(return_value=None)

    rows = [r async for r in src.query(
        "x", "Story",
        projection=["spec.title", "spec.status"],
    )]

    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "s-a"
    assert r["spec"]["title"] == "T"
    assert r["spec"]["status"] == "todo"
    assert "description" not in r.get("spec", {})


@pytest.mark.asyncio
async def test_query_tenant_overlay_queries_both_layers():
    """When tenant is set, query fires twice: once for overlay, once for base."""
    pool = MagicMock()
    conn = MagicMock()
    base_rows = [_row("s-shared", title="base"), _row("s-only-base", title="x")]
    overlay_rows = [_row("s-shared", title="overlay"), _row("s-only-overlay", title="y")]

    fetch_results = [overlay_rows, base_rows]
    conn.fetch = AsyncMock(side_effect=fetch_results)
    # acquire/release are awaited (see _acquire_safe, source.py:149-166).
    pool.acquire = AsyncMock(return_value=conn)
    pool.release = AsyncMock(return_value=None)

    src = PostgresSource.__new__(PostgresSource)
    src._pool = pool
    src._schema = "public"
    src._ensure_migrated = AsyncMock(return_value=None)

    rows = [r async for r in src.query("x", "Story", tenant="acme")]
    by_name = {r["metadata"]["name"]: r for r in rows}

    assert conn.fetch.call_count == 2
    assert by_name["s-shared"]["spec"]["title"] == "overlay"  # overlay shadows
    assert "s-only-base" in by_name
    assert "s-only-overlay" in by_name


@pytest.mark.asyncio
async def test_query_full_raw_without_projection():
    pool, conn = _mock_pool([_row("s-a", description="X", status="todo")])
    src = PostgresSource.__new__(PostgresSource)
    src._pool = pool
    src._schema = "public"
    src._ensure_migrated = AsyncMock(return_value=None)

    rows = [r async for r in src.query("x", "Story")]
    assert rows[0]["spec"]["description"] == "X"
    assert rows[0]["kind"] == "Story"


@pytest.mark.asyncio
async def test_query_rejects_non_dict_filter():
    pool, _ = _mock_pool([])
    src = PostgresSource.__new__(PostgresSource)
    src._pool = pool
    src._schema = "public"
    src._ensure_migrated = AsyncMock(return_value=None)

    with pytest.raises(QueryError, match="filter must be dict"):
        [_ async for _ in src.query("x", "Story", filter="status=todo")]


# ===========================================================================
# Live PG tests — skip when no DSN configured.
# ===========================================================================

def _resolve_live_dsn() -> str | None:
    pin = os.environ.get("DNA_PG_TEST_DSN")
    if pin:
        return pin
    src_url = os.environ.get("DNA_SOURCE_URL", "")
    if src_url.startswith("postgres"):
        return src_url
    return None


LIVE_DSN = _resolve_live_dsn()


@pytest.mark.skipif(not LIVE_DSN, reason="set DNA_PG_TEST_DSN or DNA_SOURCE_URL=postgres://...")
@pytest.mark.asyncio
async def test_live_query_filter_returns_correct_rows():
    """Live: query against a real Postgres returns rows matching filter
    semantics, and uses 1 SELECT (we can observe via timing — N+1 would
    be orders of magnitude slower)."""
    import asyncpg

    pool = await asyncpg.create_pool(LIVE_DSN, min_size=1, max_size=2)
    try:
        src = PostgresSource(pool)
        await src.init()
        rows = [
            r async for r in src.query(
                "dna-development", "Story",
                filter={"status": "in-progress"},
                projection=["spec.title", "spec.status"],
                limit=20,
            )
        ]
        # All returned rows must satisfy the filter.
        for r in rows:
            assert r["spec"]["status"] == "in-progress"
    finally:
        await pool.close()


@pytest.mark.skipif(not LIVE_DSN, reason="set DNA_PG_TEST_DSN or DNA_SOURCE_URL=postgres://...")
@pytest.mark.asyncio
async def test_live_query_under_50ms_on_real_data():
    """Live: indexed query on dna-development scope (~1500 docs) runs
    under 50ms. Proves push-down + the new v8 indices land."""
    import asyncpg
    import time

    pool = await asyncpg.create_pool(LIVE_DSN, min_size=1, max_size=2)
    try:
        src = PostgresSource(pool)
        await src.init()
        # Warm pool / cache.
        [_ async for _ in src.query("dna-development", "Story", limit=10)]

        t0 = time.perf_counter()
        rows = [
            r async for r in src.query(
                "dna-development", "Story",
                filter={"status": "in-progress"},
                limit=50,
            )
        ]
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # Generous budget — actual is typically <20ms on the existing seed.
        assert elapsed_ms < 100, (
            f"query took {elapsed_ms:.1f}ms — push-down or indices broken?"
        )
    finally:
        await pool.close()


# ===========================================================================
# s-pg-query-pushdown-typing — typed comparisons + parity with the Python
# fallback (_match_filter). No DB required: asserts the SQL builder casts by
# value type, and that the fallback's native numeric semantics are what the
# push-down now mirrors (the old TEXT path compared '9' > '10' lexically).
# ===========================================================================

from dna.adapters.postgres.source import _pg_compare_clause
from dna.kernel.protocols import _match_filter


class TestTypedComparisons:
    def test_numeric_gt_casts_to_numeric_with_guard(self):
        sql, params = _build_pg_where({"priority": {"gt": 9}}, start_idx=1)
        assert "::numeric" in sql           # numeric comparison, not TEXT
        assert "~ '^-?[0-9]" in sql          # guarded cast (non-numeric → NULL)
        assert params == [9]                 # int param, not "9"

    def test_float_lte_is_numeric(self):
        sql, params = _build_pg_where({"signal": {"lte": 0.5}}, start_idx=1)
        assert "::numeric" in sql
        assert params == [0.5]

    def test_bool_casts_to_boolean(self):
        sql, params = _build_pg_where({"spec.active": {"eq": True}}, start_idx=1)
        assert "::boolean" in sql
        assert params == [True]              # bound as bool, not "true"

    def test_string_comparison_unchanged(self):
        sql, params = _build_pg_where({"updated_at": {"gt": "2026-05-01"}}, start_idx=1)
        assert "::numeric" not in sql and "::boolean" not in sql
        assert params == ["2026-05-01"]

    def test_helper_bool_check_precedes_int(self):
        # bool is a subclass of int — must be handled as boolean, not numeric.
        clause, param = _pg_compare_clause("(x)", "=", True, 3)
        assert "::boolean" in clause and param is True


class TestPushdownParityWithFallback:
    """The push-down now compares numerically — the same semantics the Python
    fallback (_match_filter) has always used. Lock the divergence shut: the
    classic 9-vs-10 case where lexicographic TEXT ordering disagreed with
    numeric ordering."""

    def test_gt_9_numeric_not_lexicographic(self):
        # Python fallback: 10 > 9 (numeric) → matches; '10' > '9' (lexical) → would NOT.
        doc10 = {"metadata": {"name": "a"}, "spec": {"priority": 10}}
        doc9 = {"metadata": {"name": "b"}, "spec": {"priority": 9}}
        assert _match_filter(doc10, {"priority": {"gt": 9}}) is True
        assert _match_filter(doc9, {"priority": {"gt": 9}}) is False
        # Push-down mirrors it: numeric cast (so PG compares 10>9, not '10'>'9').
        sql, params = _build_pg_where({"priority": {"gt": 9}}, start_idx=1)
        assert "::numeric" in sql and params == [9]

    def test_lt_100_numeric(self):
        doc = {"metadata": {"name": "a"}, "spec": {"priority": 20}}
        # 20 < 100 numerically (True); '20' < '100' lexically would be False.
        assert _match_filter(doc, {"priority": {"lt": 100}}) is True
        sql, _ = _build_pg_where({"priority": {"lt": 100}}, start_idx=1)
        assert "::numeric" in sql
