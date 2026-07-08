"""Tests for SqliteSource.query() — native push-down via json_extract.

Story s-sqlite-source-query-impl (Feature f-source-as-query, Epic
e-production-viable-kernel). Same shape as the Postgres tests,
SQLite dialect (? placeholders, json_extract, tenant IS NULL for base).

Three test classes:
  - Helper tests (pure, no DB): field expr + WHERE + ORDER BY.
  - Mock-conn tests: SqliteSource.query() issues correct SQL + params.
  - Live in-memory tests: real SQLite, seed docs, assert parity with
    Protocol fallback.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from dna.adapters.sqlite.source import (
    SqliteSource,
    _sqlite_field_expr,
    _build_sqlite_where,
    _build_sqlite_order,
)
from dna.kernel.protocols import QueryError
from contextlib import asynccontextmanager


# ===========================================================================
# Pure helper tests
# ===========================================================================


class TestSqliteFieldExpr:
    def test_name_shorthand(self):
        assert _sqlite_field_expr("name") == "name"
        assert _sqlite_field_expr("metadata.name") == "name"

    def test_kind_column(self):
        assert _sqlite_field_expr("kind") == "kind"

    def test_apiversion(self):
        assert _sqlite_field_expr("apiVersion") == "json_extract(content, '$.apiVersion')"

    def test_unprefixed_under_spec(self):
        assert _sqlite_field_expr("status") == "json_extract(content, '$.spec.status')"

    def test_explicit_spec(self):
        assert _sqlite_field_expr("spec.feature") == "json_extract(content, '$.spec.feature')"

    def test_nested(self):
        assert _sqlite_field_expr("spec.nested.deep") == "json_extract(content, '$.spec.nested.deep')"

    def test_metadata_prefix(self):
        assert _sqlite_field_expr("metadata.labels") == "json_extract(content, '$.metadata.labels')"

    def test_sql_injection_rejected(self):
        with pytest.raises(QueryError, match="invalid field path"):
            _sqlite_field_expr("status'; DROP TABLE documents; --")

    def test_empty_path_rejected(self):
        with pytest.raises(QueryError, match="invalid field path"):
            _sqlite_field_expr("")


class TestBuildSqliteWhere:
    def test_empty_returns_empty(self):
        assert _build_sqlite_where(None) == ("", [])
        assert _build_sqlite_where({}) == ("", [])

    def test_shorthand_eq(self):
        sql, params = _build_sqlite_where({"status": "in-progress"})
        assert sql == " AND json_extract(content, '$.spec.status') = ?"
        assert params == ["in-progress"]

    def test_explicit_eq(self):
        sql, params = _build_sqlite_where({"status": {"eq": "todo"}})
        assert "= ?" in sql
        assert params == ["todo"]

    def test_neq(self):
        sql, params = _build_sqlite_where({"status": {"neq": "done"}})
        assert "<> ?" in sql
        assert params == ["done"]

    def test_in_expands_to_placeholders(self):
        sql, params = _build_sqlite_where({"status": {"in": ["todo", "in-progress", "review"]}})
        # IN (?, ?, ?)
        assert "IN (?,?,?)" in sql
        assert params == ["todo", "in-progress", "review"]

    def test_in_empty_rejected(self):
        with pytest.raises(QueryError, match="non-empty"):
            _build_sqlite_where({"status": {"in": []}})

    def test_like(self):
        sql, params = _build_sqlite_where({"title": {"like": "%kernel%"}})
        assert "LIKE ?" in sql
        assert params == ["%kernel%"]

    def test_gt_lt(self):
        sql, params = _build_sqlite_where({"priority": {"gt": 3}})
        assert "> ?" in sql
        assert params == [3]
        sql, params = _build_sqlite_where({"priority": {"lte": 10}})
        assert "<= ?" in sql

    def test_multiple_keys_anded(self):
        sql, params = _build_sqlite_where({"status": "in-progress", "feature": "f-x"})
        assert "AND" in sql
        assert params == ["in-progress", "f-x"]

    def test_unknown_operator_raises(self):
        with pytest.raises(QueryError, match="unknown query operator"):
            _build_sqlite_where({"status": {"regex": ".*"}})

    def test_int_preserved(self):
        """SQLite json_extract returns int for numeric JSON. Don't coerce to str."""
        sql, params = _build_sqlite_where({"priority": 5})
        assert params == [5]

    def test_bool_coerced_to_int(self):
        sql, params = _build_sqlite_where({"enabled": True})
        assert params == [1]


class TestBuildSqliteOrder:
    def test_asc_default(self):
        sql = _build_sqlite_order(["spec.updated_at"])
        assert sql == " ORDER BY json_extract(content, '$.spec.updated_at') ASC NULLS LAST"

    def test_desc_dash_prefix(self):
        sql = _build_sqlite_order(["-spec.updated_at"])
        assert "DESC NULLS LAST" in sql

    def test_multiple_ordered_left_to_right(self):
        sql = _build_sqlite_order(["spec.feature", "-spec.priority"])
        f_pos = sql.index("'$.spec.feature'")
        p_pos = sql.index("'$.spec.priority'")
        assert f_pos < p_pos

    def test_unprefixed_under_spec(self):
        sql = _build_sqlite_order(["status"])
        assert "$.spec.status" in sql

    def test_name_column(self):
        sql = _build_sqlite_order(["name"])
        assert "name ASC NULLS LAST" in sql


# ===========================================================================
# Mock-conn tests
# ===========================================================================


def _mock_conn(rows):
    """Build a mock aiosqlite connection where execute() returns a cursor
    that fetchall() yields ``rows``."""
    cursor = MagicMock()
    cursor.fetchall = AsyncMock(return_value=rows)
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cursor)
    return conn, cursor


def _patch_acquire(src, conn):
    """Make src._acquire() yield this mock conn — replaces the old
    `_patch_acquire(src, conn)` now that SqliteSource opens a connection per operation."""
    @asynccontextmanager
    async def _fake():
        yield conn
    src._acquire = _fake


def _row(name, **spec):
    content = {"kind": "Story", "metadata": {"name": name}, "spec": spec}

    class R:
        def __init__(self, d):
            self._d = d
        def __getitem__(self, k):
            return self._d[k]

    # aiosqlite Row supports both dict() and indexing
    raw = {"name": name, "kind": "Story", "content": json.dumps(content)}
    # Use a real dict; the SqliteSource calls dict(r) so it's flexible
    return raw


@pytest.mark.asyncio
async def test_query_dispatches_single_sql_with_filter():
    conn, _cursor = _mock_conn([
        _row("s-a", status="in-progress"),
        _row("s-b", status="in-progress"),
    ])
    src = SqliteSource.__new__(SqliteSource)
    _patch_acquire(src, conn)

    rows = [r async for r in src.query(
        "scope-x", "Story",
        filter={"status": "in-progress"},
        limit=50,
    )]

    assert conn.execute.call_count == 1
    sql = conn.execute.call_args.args[0]
    params = conn.execute.call_args.args[1]
    assert "WHERE scope=? AND kind=? AND tenant IS NULL" in sql
    assert "json_extract(content, '$.spec.status') = ?" in sql
    assert "LIMIT ?" in sql
    assert params == ("scope-x", "Story", "in-progress", 50)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_query_without_filter_omits_where_fragment():
    conn, _cursor = _mock_conn([])
    src = SqliteSource.__new__(SqliteSource)
    _patch_acquire(src, conn)

    [r async for r in src.query("x", "Story")]
    sql = conn.execute.call_args.args[0]
    assert "tenant IS NULL" in sql
    # No extra AND clauses after the tenant predicate.
    assert sql.count(" AND ") == 2


@pytest.mark.asyncio
async def test_query_with_order_by_appends_clause():
    conn, _cursor = _mock_conn([])
    src = SqliteSource.__new__(SqliteSource)
    _patch_acquire(src, conn)

    [r async for r in src.query("x", "Story", order_by=["-spec.updated_at"])]
    sql = conn.execute.call_args.args[0]
    assert "ORDER BY json_extract(content, '$.spec.updated_at') DESC" in sql


@pytest.mark.asyncio
async def test_query_projection_in_python():
    conn, _cursor = _mock_conn([
        _row("s-a", title="T", status="todo", description="LONG_BODY"),
    ])
    src = SqliteSource.__new__(SqliteSource)
    _patch_acquire(src, conn)

    rows = [r async for r in src.query(
        "x", "Story", projection=["spec.title", "spec.status"],
    )]

    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "s-a"
    assert r["spec"]["title"] == "T"
    assert r["spec"]["status"] == "todo"
    assert "description" not in r.get("spec", {})


@pytest.mark.asyncio
async def test_query_tenant_overlay_queries_both_layers():
    cursor1 = MagicMock()
    cursor1.fetchall = AsyncMock(return_value=[
        _row("s-shared", title="overlay"),
        _row("s-only-overlay", title="y"),
    ])
    cursor2 = MagicMock()
    cursor2.fetchall = AsyncMock(return_value=[
        _row("s-shared", title="base"),
        _row("s-only-base", title="x"),
    ])
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=[cursor1, cursor2])

    src = SqliteSource.__new__(SqliteSource)
    _patch_acquire(src, conn)

    rows = [r async for r in src.query("x", "Story", tenant="acme")]
    by_name = {r["metadata"]["name"]: r for r in rows}

    assert conn.execute.call_count == 2
    assert by_name["s-shared"]["spec"]["title"] == "overlay"
    assert "s-only-base" in by_name
    assert "s-only-overlay" in by_name


@pytest.mark.asyncio
async def test_query_uses_tenant_param_for_overlay():
    """When tenant is set, the overlay query passes tenant=? param;
    the base query uses tenant IS NULL with no param."""
    cursor = MagicMock()
    cursor.fetchall = AsyncMock(return_value=[])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cursor)

    src = SqliteSource.__new__(SqliteSource)
    _patch_acquire(src, conn)

    [r async for r in src.query("x", "Story", tenant="acme")]
    # 2 calls
    sql_overlay = conn.execute.call_args_list[0].args[0]
    params_overlay = conn.execute.call_args_list[0].args[1]
    sql_base = conn.execute.call_args_list[1].args[0]
    params_base = conn.execute.call_args_list[1].args[1]
    assert "tenant=?" in sql_overlay
    assert "acme" in params_overlay
    assert "tenant IS NULL" in sql_base
    assert "acme" not in params_base


@pytest.mark.asyncio
async def test_query_rejects_non_dict_filter():
    conn, _cursor = _mock_conn([])
    src = SqliteSource.__new__(SqliteSource)
    _patch_acquire(src, conn)
    with pytest.raises(QueryError, match="filter must be dict"):
        [_ async for _ in src.query("x", "Story", filter="status=todo")]


# ===========================================================================
# Live in-memory SQLite — no external dep.
# ===========================================================================


@pytest_asyncio.fixture
async def live_src(tmp_path):
    """Real SqliteSource over a temp file."""
    src = SqliteSource(str(tmp_path / "test.db"))
    await src.connect()
    yield src
    await src.close()


async def _seed(src, scope, docs, *, tenant=None):
    """Write `docs` (list of dicts) into the live SQLite. Bypasses
    save_document to avoid version+bundle machinery; the query path
    only reads from `documents` table."""
    async with src._acquire() as conn:
        for doc in docs:
            kind = doc["kind"]
            name = doc["metadata"]["name"]
            await conn.execute(
                "INSERT OR REPLACE INTO documents "
                "(scope, kind, name, content, version, updated_at, tenant) "
                "VALUES (?, ?, ?, ?, 1, '2026-01-01', ?)",
                (scope, kind, name, json.dumps(doc), tenant),
            )
        await conn.commit()


def _doc(kind, name, **spec):
    return {"kind": kind, "metadata": {"name": name}, "spec": spec}


@pytest.mark.asyncio
async def test_live_filter_returns_matching_rows(live_src):
    await _seed(live_src, "scope-x", [
        _doc("Story", "s-a", status="in-progress"),
        _doc("Story", "s-b", status="done"),
        _doc("Story", "s-c", status="in-progress"),
    ])
    rows = [r async for r in live_src.query(
        "scope-x", "Story", filter={"status": "in-progress"},
    )]
    assert sorted(r["metadata"]["name"] for r in rows) == ["s-a", "s-c"]


@pytest.mark.asyncio
async def test_live_in_operator(live_src):
    await _seed(live_src, "x", [
        _doc("Story", "s-a", status="todo"),
        _doc("Story", "s-b", status="in-progress"),
        _doc("Story", "s-c", status="done"),
    ])
    rows = [r async for r in live_src.query(
        "x", "Story", filter={"status": {"in": ["todo", "in-progress"]}},
    )]
    assert sorted(r["metadata"]["name"] for r in rows) == ["s-a", "s-b"]


@pytest.mark.asyncio
async def test_live_order_by_desc_limit_offset(live_src):
    await _seed(live_src, "x", [
        _doc("Story", "s-a", priority=1),
        _doc("Story", "s-b", priority=2),
        _doc("Story", "s-c", priority=3),
        _doc("Story", "s-d", priority=4),
    ])
    rows = [r async for r in live_src.query(
        "x", "Story", order_by=["-spec.priority"], limit=2, offset=1,
    )]
    # priorities sorted desc: [4, 3, 2, 1]; offset 1, limit 2 → [3, 2]
    assert [r["spec"]["priority"] for r in rows] == [3, 2]


@pytest.mark.asyncio
async def test_live_projection(live_src):
    await _seed(live_src, "x", [
        _doc("Story", "s-a", title="T", status="todo", description="LONG"),
    ])
    rows = [r async for r in live_src.query(
        "x", "Story", projection=["spec.title", "spec.status"],
    )]
    assert rows[0]["name"] == "s-a"
    assert rows[0]["spec"] == {"title": "T", "status": "todo"}


@pytest.mark.asyncio
async def test_live_tenant_overlay_shadows_base(live_src):
    await _seed(live_src, "x", [
        _doc("Story", "s-shared", title="base"),
        _doc("Story", "s-only-base", title="x"),
    ])
    await _seed(live_src, "x", [
        _doc("Story", "s-shared", title="overlay"),
        _doc("Story", "s-only-overlay", title="y"),
    ], tenant="acme")

    rows = [r async for r in live_src.query("x", "Story", tenant="acme")]
    by_name = {r["metadata"]["name"]: r for r in rows}

    assert by_name["s-shared"]["spec"]["title"] == "overlay"
    assert "s-only-base" in by_name
    assert "s-only-overlay" in by_name


@pytest.mark.asyncio
async def test_live_query_under_30ms_on_1000_docs(live_src):
    """Bench: 1000-doc filter+order+limit query stays under 30ms."""
    import time
    docs = [_doc("Story", f"s-{i:04d}", status="in-progress" if i % 3 else "done", priority=i)
            for i in range(1000)]
    await _seed(live_src, "x", docs)

    # Warm
    [_ async for _ in live_src.query("x", "Story", limit=10)]

    t0 = time.perf_counter()
    rows = [r async for r in live_src.query(
        "x", "Story",
        filter={"status": "in-progress"},
        order_by=["-spec.priority"],
        limit=50,
    )]
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert len(rows) == 50
    assert elapsed_ms < 100, f"query took {elapsed_ms:.1f}ms — push-down or indices broken?"
