"""``PostgresQuotaStore`` — the DURABLE quota counter, against a real database.

The MCP quota meter shipped with exactly one ``QuotaStore``:
``InProcQuotaStore``, two dicts in the server process. Its own docstring
admitted it was "WRONG for real billing", and it was, in two specific ways
that made DNA Cloud's overage job unimplementable:

1. **a restart zeroed the day's usage** — the counter lived in memory, so a
   deploy or a crash handed every tenant a fresh budget; and
2. **each replica counted alone** — N replicas kept N dicts, so the effective
   cap was ~N x ``calls_per_day`` and the Pro cap was not enforceable at all.

Neither is a property of Python that a fake can demonstrate, so these tests
run against a REAL Postgres (marker + DSN, see ``tests/conftest.py``): 1 is
proven by rebuilding the store from scratch and finding the count still there;
2 by hammering one counter from many threads and asserting nothing was lost.

The table is NOT created by hand here. It is created by
``SqlAlchemySource.connect()`` running the SDK's Alembic ladder — the same
call a DNA Cloud container makes at boot — so these tests also prove the
revision provisions what the store actually needs.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from dna_cli import _mcp_quota as Q

from conftest import pg_dsn

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def pg_schema():
    """A throwaway schema, migrated by the SDK exactly as a container would.

    Yields ``(dsn, schema)``. Dropped on the way out, so a failing test cannot
    leak state into the next one — which matters more than usual here, since
    the whole subject is state that outlives its process.
    """
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("psycopg2")
    asyncpg = pytest.importorskip("asyncpg")

    dsn = pg_dsn()
    schema = f"dna_quota_{uuid.uuid4().hex[:12]}"

    async def setup():
        conn = await asyncpg.connect(dsn)
        await conn.execute(f"CREATE SCHEMA {schema}")
        await conn.close()
        from dna.adapters.sqlalchemy_ import SqlAlchemySource

        src = SqlAlchemySource(
            dsn.replace("postgresql://", "postgresql+asyncpg://", 1), schema=schema
        )
        await src.connect()  # runs the Alembic ladder → creates dna_quota_counters
        await src.close()

    async def teardown():
        conn = await asyncpg.connect(dsn)
        await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await conn.close()

    asyncio.run(setup())
    try:
        yield dsn, schema
    finally:
        asyncio.run(teardown())


def _store(pg_schema) -> Q.PostgresQuotaStore:
    dsn, schema = pg_schema
    return Q.PostgresQuotaStore(dsn, schema=schema)


# ── the migration actually provisions the counter ──────────────────────────


def test_the_alembic_ladder_creates_the_counter_table(pg_schema):
    """No hand-rolled DDL anywhere: connecting a source is enough."""
    store = _store(pg_schema)
    try:
        assert store.calls_on("nobody") == 0  # table exists and is readable
    finally:
        store.close()


# ── proof 1: the count SURVIVES the process ────────────────────────────────


def test_the_count_survives_a_brand_new_store_instance(pg_schema):
    """DURABILITY — the defect that let a restart refund the day's usage.

    Spends three calls, throws the store (and its connection pool) away, then
    builds a completely fresh one against the same database. The counter picks
    up at 4, not 1. The in-process store fails this by construction.
    """
    key = Q.quota_key("acme", "pro")

    first = _store(pg_schema)
    try:
        assert [first.incr_day(key) for _ in range(3)] == [1, 2, 3]
    finally:
        first.close()  # the "process" ends here

    second = _store(pg_schema)  # a "restarted" server: new object, new pool
    try:
        assert second.incr_day(key) == 4, "the restart refunded the day's usage"
        assert second.calls_on("acme") == 4
    finally:
        second.close()


def test_a_restart_does_not_refund_an_exhausted_daily_cap(pg_schema):
    """The same defect, at the level that matters: ENFORCEMENT.

    A tenant that burned its Free cap must stay denied across a restart —
    otherwise 'calls_per_day' means 'calls per day per deploy'.
    """
    caps = {"feature_families": [], "calls_per_day": 2, "rate_per_sec": None}

    before = _store(pg_schema)
    try:
        for _ in range(2):
            Q.enforce_quota(caps=caps, tenant="acme", tier="free",
                            family="memory", store=before)
        with pytest.raises(Q.OverQuotaError):
            Q.enforce_quota(caps=caps, tenant="acme", tier="free",
                            family="memory", store=before)
    finally:
        before.close()

    after = _store(pg_schema)  # restarted
    try:
        with pytest.raises(Q.OverQuotaError, match="quota"):
            Q.enforce_quota(caps=caps, tenant="acme", tier="free",
                            family="memory", store=after)
    finally:
        after.close()


# ── proof 2: N concurrent increments produce exactly N ─────────────────────


def test_concurrent_increments_never_lose_one(pg_schema):
    """ATOMICITY — the test that catches a read-modify-write.

    64 threads x 8 increments against ONE counter. A store that did
    SELECT-then-UPDATE would interleave and land well under 512; the atomic
    ``INSERT ... ON CONFLICT DO UPDATE SET calls = calls + 1`` cannot, because
    the losing writer blocks on the row lock and adds to the COMMITTED value.

    The returned values are checked too, not just the total: each increment
    must have observed a DISTINCT post-increment count. That is the stronger
    claim — a store could reach the right total while handing two callers the
    same number, and the meter would then enforce the cap against a count it
    had already given away.
    """
    threads, per_thread = 64, 8
    total = threads * per_thread
    key = Q.quota_key("acme", "pro")

    # One store, one pool — the concurrency is real, not serialized by a lock.
    store = Q.PostgresQuotaStore(
        pg_schema[0], schema=pg_schema[1], pool_size=threads
    )
    try:
        def hammer(_):
            return [store.incr_day(key) for _ in range(per_thread)]

        with ThreadPoolExecutor(max_workers=threads) as pool:
            seen = [n for chunk in pool.map(hammer, range(threads)) for n in chunk]

        assert store.calls_on("acme") == total, (
            f"lost increments: {total} calls counted as {store.calls_on('acme')} "
            "— the counter is doing read-modify-write"
        )
        assert sorted(seen) == list(range(1, total + 1)), (
            "two callers were handed the same post-increment count"
        )
    finally:
        store.close()


def test_concurrent_replicas_share_one_budget(pg_schema):
    """The replica defect, end to end.

    Four INDEPENDENT store instances — the shape of four container replicas —
    metering the same tenant against a cap of 10. Exactly 10 calls may pass in
    total, not 10 each. This is the assertion that was impossible before.
    """
    caps = {"feature_families": [], "calls_per_day": 10, "rate_per_sec": None}
    replicas = [_store(pg_schema) for _ in range(4)]
    allowed = denied = 0
    try:
        # 40 calls round-robin across the replicas.
        for i in range(40):
            try:
                Q.enforce_quota(caps=caps, tenant="acme", tier="pro",
                                family="memory", store=replicas[i % 4])
                allowed += 1
            except Q.OverQuotaError:
                denied += 1
        assert (allowed, denied) == (10, 30), (
            f"{allowed} calls passed a cap of 10 — the replicas are not sharing "
            "a counter"
        )
    finally:
        for r in replicas:
            r.close()


# ── the billing read the overage job needs ─────────────────────────────────


def test_calls_on_is_per_tenant_per_day_and_sums_tiers(pg_schema):
    """``calls_on(tenant, day)`` — what the DNA Cloud overage job calls.

    Sums across tiers (a tenant that upgraded mid-day is billed for everything
    it called), isolates other tenants, and isolates other days.
    """
    store = _store(pg_schema)
    try:
        store.incr_day(Q.quota_key("acme", "free"))
        store.incr_day(Q.quota_key("acme", "free"))
        store.incr_day(Q.quota_key("acme", "pro"))  # upgraded mid-day
        store.incr_day(Q.quota_key("globex", "pro"))

        assert store.calls_on("acme") == 3
        assert store.calls_on("globex") == 1
        assert store.calls_on("never-called") == 0

        yesterday = _dt.datetime.now(_dt.UTC).date() - _dt.timedelta(days=1)
        assert store.calls_on("acme", yesterday) == 0, "days are not isolated"
    finally:
        store.close()


def test_personal_partitions_keep_their_structured_tenant(pg_schema):
    """Personal memory meters under ``personal:<family>:<sub>``; the key split
    must not shred those colons into the tier column."""
    store = _store(pg_schema)
    try:
        tenant = "personal:google:sub-9"
        store.incr_day(Q.quota_key(tenant, "pro"))
        store.incr_day(Q.quota_key(tenant, "pro"))
        assert store.calls_on(tenant) == 2
    finally:
        store.close()


# ── the documented limit: rate is per-replica, on purpose ──────────────────


def test_the_rate_window_is_deliberately_not_durable(pg_schema):
    """A restart clears the rate window, and that is the DESIGN, not a bug.

    Persisting a one-second window would mean a row per call for data nothing
    bills on. The daily counter — the one money depends on — is durable; the
    rate limit is a per-replica throttle. Pinned by a test so the asymmetry is
    a decision on the record rather than a surprise.
    """
    key = Q.quota_key("acme", "pro")

    first = _store(pg_schema)
    try:
        for _ in range(5):
            first.note_call(key)
        assert first.rate_count(key, 1.0) == 5
    finally:
        first.close()

    second = _store(pg_schema)
    try:
        assert second.rate_count(key, 1.0) == 0, "the rate window became durable"
        # ...while the DAILY counter in the same store is durable.
        first_daily = _store(pg_schema)
        try:
            first_daily.incr_day(key)
        finally:
            first_daily.close()
        assert second.calls_on("acme") == 1
    finally:
        second.close()
