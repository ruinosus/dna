"""F2 Task 3: native COUNT push-down on the Postgres dialect.

Two-planes F2 (spec docs/superpowers/specs/2026-06-09-kinds-two-planes-design.md
D2). ``SqlAlchemySource.count`` runs ``SELECT count(*) … GROUP BY`` natively —
only aggregates travel back, never rows. The central assert is PARITY: the
same scenario through the native override and through the protocol-default
fallback (``await count_via_query(pg_src, …)``, the shared helper — since
``pg_src.count`` is always the native one) must agree.

Requires a running PostgreSQL instance (DATABASE_URL).
"""
from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio

# Skip entire module if no DATABASE_URL
pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.asyncio(loop_scope="module"),
]

SCHEMA = "dna_test_f2_count"


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _story(name: str, spec: dict) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Story",
        "metadata": {"name": name}, "spec": dict(spec),
    }


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def source():
    """pg-dialect SqlAlchemySource with a clean schema + seeded count scenarios."""
    import asyncpg
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    dsn = os.environ["DATABASE_URL"]

    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    await conn.execute(f"CREATE SCHEMA {SCHEMA}")
    await conn.close()

    sa_url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    src = SqlAlchemySource(sa_url, schema=SCHEMA)
    await src.connect()

    # Plain scope — 4 Stories (2 todo, 1 done, 1 sem status) + 1 Issue
    # (other kind, must never count).
    await src.save_document("count-scope", "Story", "s-1", _story("s-1", {"status": "todo"}))
    await src.save_document("count-scope", "Story", "s-2", _story("s-2", {"status": "todo"}))
    await src.save_document("count-scope", "Story", "s-3", _story("s-3", {"status": "done"}))
    await src.save_document("count-scope", "Story", "s-4", _story("s-4", {}))
    await src.save_document("count-scope", "Issue", "i-1", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Issue",
        "metadata": {"name": "i-1"}, "spec": {"status": "open"},
    })

    # Tenant scope — base: a-1 (todo) + a-2 (done); overlay acme: a-1
    # (done — SHADOWS base) + b-1 (todo — overlay-only).
    await src.save_document("tn-scope", "Story", "a-1", _story("a-1", {"status": "todo"}))
    await src.save_document("tn-scope", "Story", "a-2", _story("a-2", {"status": "done"}))
    await src.save_document(
        "tn-scope", "Story", "a-1", _story("a-1", {"status": "done"}), tenant="acme",
    )
    await src.save_document(
        "tn-scope", "Story", "b-1", _story("b-1", {"status": "todo"}), tenant="acme",
    )

    yield src
    await src.close()


# ---------------------------------------------------------------------------
# Native push-down property — count must NOT ride self.query
# ---------------------------------------------------------------------------

class TestNativePushdown:
    async def test_count_does_not_ride_query(self, source, monkeypatch):
        """The native impl aggregates in SQL — it must NOT iterate
        ``self.query`` (that was the interim delegator's path). This is
        the red→green pin for Task 3."""
        rode_query = False
        orig_query = type(source).query

        def _spy(self, *a, **kw):
            nonlocal rode_query
            rode_query = True
            return orig_query(self, *a, **kw)

        monkeypatch.setattr(type(source), "query", _spy)
        res = await source.count("count-scope", "Story")
        assert res == {"total": 4, "groups": None}
        assert not rode_query, "SqlAlchemySource.count must push down, not ride query()"


# ---------------------------------------------------------------------------
# Behavior — total / filter / group_by
# ---------------------------------------------------------------------------

class TestCountBehavior:
    async def test_count_total(self, source):
        res = await source.count("count-scope", "Story")
        assert res == {"total": 4, "groups": None}

    async def test_count_total_with_filter(self, source):
        res = await source.count("count-scope", "Story", filter={"status": "todo"})
        assert res == {"total": 2, "groups": None}

    async def test_count_filter_operator_in(self, source):
        res = await source.count(
            "count-scope", "Story", filter={"status": {"in": ["todo", "done"]}},
        )
        assert res == {"total": 3, "groups": None}

    async def test_count_group_by(self, source):
        res = await source.count("count-scope", "Story", group_by="spec.status")
        assert res["total"] == 4
        assert res["groups"] == [
            {"key": "todo", "count": 2},
            # done x None tie (1 each) → NULLS LAST: done before None.
            {"key": "done", "count": 1},
            {"key": None, "count": 1},
        ]

    async def test_count_group_by_with_filter(self, source):
        res = await source.count(
            "count-scope", "Story",
            filter={"status": {"in": ["todo", "done"]}},
            group_by="spec.status",
        )
        assert res["total"] == 3
        assert res["groups"] == [
            {"key": "todo", "count": 2},
            {"key": "done", "count": 1},
        ]

    async def test_count_other_kind_isolated(self, source):
        res = await source.count("count-scope", "Issue")
        assert res["total"] == 1

    async def test_count_empty_scope(self, source):
        res = await source.count("ghost-scope", "Story", group_by="spec.status")
        assert res == {"total": 0, "groups": []}


# ---------------------------------------------------------------------------
# Tenant overlay — dedup by name, overlay shadows base
# ---------------------------------------------------------------------------

class TestCountTenant:
    async def test_count_tenant_total_dedups_shadowed_name(self, source):
        # a-1 (base+overlay → 1) + a-2 (base) + b-1 (overlay-only) = 3.
        res = await source.count("tn-scope", "Story", tenant="acme")
        assert res == {"total": 3, "groups": None}

    async def test_count_no_tenant_sees_base_only(self, source):
        res = await source.count("tn-scope", "Story")
        assert res == {"total": 2, "groups": None}

    async def test_count_tenant_group_by_uses_overlay_values(self, source):
        # a-1 counts under its OVERLAY status (done), not base (todo).
        res = await source.count("tn-scope", "Story", tenant="acme", group_by="spec.status")
        assert res["total"] == 3
        assert res["groups"] == [
            {"key": "done", "count": 2},   # a-1 (overlay), a-2 (base)
            {"key": "todo", "count": 1},   # b-1 (overlay-only)
        ]


# ---------------------------------------------------------------------------
# Parity — adapter (native) ↔ protocol-default (unbound fallback)
# ---------------------------------------------------------------------------

PARITY_CASES = [
    ("count-scope", {}),
    ("count-scope", {"filter": {"status": "todo"}}),
    ("count-scope", {"filter": {"status": {"in": ["todo", "done"]}}}),
    ("count-scope", {"group_by": "spec.status"}),
    ("count-scope", {"filter": {"status": {"in": ["todo", "done"]}}, "group_by": "spec.status"}),
    ("tn-scope", {"tenant": "acme"}),
    ("tn-scope", {"tenant": "acme", "group_by": "spec.status"}),
    # base row matches the filter, its overlay shadow does NOT — both
    # paths count the base row (filter applies per physical row, before
    # the name-dedup; mirrors the native query()'s per-tenant fetches).
    ("tn-scope", {"tenant": "acme", "filter": {"status": "todo"}}),
    ("tn-scope", {"tenant": "acme", "filter": {"status": "done"}, "group_by": "spec.status"}),
]


class TestCountParity:
    @pytest.mark.parametrize("scope,kw", PARITY_CASES)
    async def test_native_matches_protocol_default(self, source, scope, kw):
        from dna.kernel.query.fallback import count_via_query
        native = await source.count(scope, "Story", **kw)
        fallback = await count_via_query(source, scope, "Story", **kw)
        assert native == fallback, f"parity broke for {scope} {kw}"


# ---------------------------------------------------------------------------
# Bundle-override guard — reader_can_produce → protocol-default fallback
# ---------------------------------------------------------------------------

class TestBundleOverrideGuard:
    async def test_reader_can_produce_falls_back_to_default(self, source, monkeypatch):
        """When a registered reader can produce the kind, SQL-only count
        would diverge (bundle docs can cross containers) — count must
        ride the protocol-default (which inherits query()'s slow-path
        bundle resolution)."""

        class _FakeStoryReader:
            _kind = "Story"

            def detect(self, handle):  # never claims a bundle
                return False

        monkeypatch.setattr(source, "_readers", [_FakeStoryReader()])

        rode_query = False
        orig_query = type(source).query

        def _spy(self, *a, **kw):
            nonlocal rode_query
            rode_query = True
            return orig_query(self, *a, **kw)

        monkeypatch.setattr(type(source), "query", _spy)
        res = await source.count("count-scope", "Story", group_by="spec.status")
        assert res["total"] == 4
        groups = {g["key"]: g["count"] for g in res["groups"]}
        assert groups == {"todo": 2, "done": 1, None: 1}
        assert rode_query, "guard must fall back to the protocol-default (rides query)"
