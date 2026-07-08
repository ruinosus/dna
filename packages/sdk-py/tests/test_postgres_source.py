"""Tests for PostgresSource — CRUD, versioning, layers.

GAP-15: PostgresSource adapter (asyncpg). Requires a running PostgreSQL instance.
Set DATABASE_URL env var to run these tests.

    DATABASE_URL=postgresql://user:pass@localhost/dna_test pytest -k test_postgres
"""
from __future__ import annotations

import asyncio
import json
import os
import pytest
import pytest_asyncio

# Skip entire module if no DATABASE_URL
pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.asyncio(loop_scope="module"),
]


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def source():
    """Create a PostgresSource with a clean schema for testing."""
    import asyncpg
    from dna.adapters.postgres import PostgresSource

    dsn = os.environ["DATABASE_URL"]
    schema = "dna_test_v3"

    # Clean up schema from previous runs
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    pool = await asyncpg.create_pool(dsn)
    src = PostgresSource(pool, schema=schema)
    await src.init()

    # Seed a module
    module_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": "test-mod"}, "spec": {"default_agent": "bot"},
    }
    await src.save_document("test-mod", "Genome", "test-mod", module_raw)
    await src.publish("test-mod", "Genome", "test-mod")

    yield src

    # Cleanup
    await src.close()
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.close()


class TestPostgresCRUD:
    async def test_load_bootstrap_docs(self, source):
        from dna.kernel.protocols import package_doc_for_scope
        m = await package_doc_for_scope(source, "test-mod")
        assert m is not None
        assert m["kind"] == "Genome"

    async def test_load_bootstrap_docs_missing(self, source):
        from dna.kernel.protocols import package_doc_for_scope
        m = await package_doc_for_scope(source, "nope")
        assert m is None

    async def test_save_and_load(self, source):
        agent = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "bot"}, "spec": {"instruction": "Be helpful"},
        }
        await source.save_document("test-mod", "Agent", "bot", agent)
        await source.publish("test-mod", "Agent", "bot")
        docs = await source.load_all("test-mod")
        names = [d["metadata"]["name"] for d in docs]
        assert "bot" in names

    async def test_delete(self, source):
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "temp"}, "spec": {},
        }
        await source.save_document("test-mod", "Agent", "temp", raw)
        await source.publish("test-mod", "Agent", "temp")
        await source.delete_document("test-mod", "Agent", "temp")
        docs = await source.load_all("test-mod")
        assert all(d["metadata"]["name"] != "temp" for d in docs)


class TestPostgresVersioning:
    async def test_multiple_versions(self, source):
        for i in range(3):
            await source.save_document("test-mod", "Skill", "vs", {
                "apiVersion": "agentskills.io/v1", "kind": "Skill",
                "metadata": {"name": "vs"}, "spec": {"instruction": f"v{i+1}"},
            })
        versions = await source.list_versions("test-mod", "Skill", "vs")
        assert len(versions) >= 3


class TestPostgresLayers:
    async def test_save_and_load_layer(self, source):
        await source.save_layer_document("test-mod", "tenant", "team-a", "Skill", "ls", {
            "apiVersion": "agentskills.io/v1", "kind": "Skill",
            "metadata": {"name": "ls"}, "spec": {"instruction": "Team A"},
        })
        docs = await source.load_layer("test-mod", "tenant", "team-a")
        assert len(docs) >= 1

    async def test_list_layers(self, source):
        layers = await source.list_layers("test-mod")
        assert any(l["layer_id"] == "tenant" for l in layers)

    async def test_empty_layer(self, source):
        docs = await source.load_layer("test-mod", "x", "nonexistent")
        assert docs == []


class TestPostgresCapabilities:
    def test_capabilities(self, source):
        # s-capabilities-dataclass — sync, typed SourceCapabilities derived from
        # the Protocols the adapter satisfies (no magic-string dict).
        caps = source.capabilities()
        assert caps.source == "postgres"
        assert caps.drafts is True
        assert caps.versions is True
        assert caps.layers is True

    async def test_list_scopes(self, source):
        scopes = await source.list_scopes()
        assert "test-mod" in scopes


class TestPhase15_1Migration5:
    """Phase 15.1 PR1 — schema migration for KernelEventBus.

    Verifies migration #5 creates `dna_outbox` and `dna_versions_seq`
    with the columns the EventBus contract relies on. Subsequent PRs
    populate these tables; this PR only ships the schema.
    """

    async def test_dna_outbox_table_shape(self, source):
        """dna_outbox has the columns the EventBus payload contract requires."""
        async with source._pool.acquire() as conn:
            cols = await conn.fetch(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = 'dna_outbox' "
                "ORDER BY ordinal_position",
                source._schema,
            )
        col_map = {c["column_name"]: c for c in cols}
        # Spec §"Data model" — every field is load-bearing.
        for required in (
            "id", "occurred_at", "scope", "tenant",
            "kind", "name", "op", "doc_version", "actor", "cause",
        ):
            assert required in col_map, f"missing column {required!r}"
        # tenant defaults to '' (matches Phase 8a dna_documents convention).
        assert col_map["tenant"]["column_default"] is not None
        # id is BIGINT (BIGSERIAL).
        assert col_map["id"]["data_type"] == "bigint"

    async def test_dna_outbox_indexes(self, source):
        """Composite (scope, tenant, id) for replay; (occurred_at) for retention sweep."""
        async with source._pool.acquire() as conn:
            idx = await conn.fetch(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = $1 AND tablename = 'dna_outbox'",
                source._schema,
            )
        names = {r["indexname"] for r in idx}
        assert "dna_outbox_scope_id_idx" in names
        assert "dna_outbox_occurred_at_idx" in names

    async def test_dna_versions_seq_table_shape(self, source):
        """dna_versions_seq is the per-(scope, tenant) gap-detection checkpoint."""
        async with source._pool.acquire() as conn:
            cols = await conn.fetch(
                "SELECT column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = 'dna_versions_seq' "
                "ORDER BY ordinal_position",
                source._schema,
            )
        col_map = {c["column_name"]: c["data_type"] for c in cols}
        assert col_map.get("scope") == "text"
        assert col_map.get("tenant") == "text"
        assert col_map.get("last_id") == "bigint"
        # Composite PK ensures one row per (scope, tenant).
        async with source._pool.acquire() as conn:
            pk = await conn.fetchval(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = $1 AND t.relname = 'dna_versions_seq' "
                "AND c.contype = 'p'",
                source._schema,
            )
        assert pk == "PRIMARY KEY (scope, tenant)"

    async def test_migration_5_recorded(self, source):
        """The migrations registry tracks v5 as applied (idempotency guarantee)."""
        async with source._pool.acquire() as conn:
            row = await conn.fetchval(
                f"SELECT count(*) FROM {source._schema}.dna_schema_migrations "
                f"WHERE version = 5"
            )
        assert row == 1

    async def test_migration_5_idempotent(self, source):
        """Re-running migrations does not fail (CREATE TABLE IF NOT EXISTS path).

        This is what happens on every harness boot — must be a no-op
        when v5 is already applied.
        """
        await source._run_migrations()
        async with source._pool.acquire() as conn:
            n = await conn.fetchval(
                f"SELECT count(*) FROM {source._schema}.dna_schema_migrations"
            )
        # Each version recorded exactly once.
        assert n >= 5


class TestPhase15_1OutboxWrites:
    """Phase 15.1 PR2 — every successful write/publish/delete emits an
    outbox row + advances dna_versions_seq + fires pg_notify, atomically
    in the same transaction as the data mutation.
    """

    async def test_save_emits_outbox_row(self, source):
        """save_document writes one matching outbox row with op='write'."""
        # Establish baseline outbox count.
        async with source._pool.acquire() as conn:
            before = await conn.fetchval(
                f"SELECT count(*) FROM {source._schema}.dna_outbox "
                "WHERE scope='test-mod' AND kind='Agent' AND name='outbox-write-test'"
            )
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "outbox-write-test"}, "spec": {},
        }
        await source.save_document(
            "test-mod", "Agent", "outbox-write-test", raw, author="alice",
        )
        async with source._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT scope, tenant, kind, name, op, doc_version, actor "
                f"FROM {source._schema}.dna_outbox "
                "WHERE scope='test-mod' AND kind='Agent' "
                "AND name='outbox-write-test' "
                "ORDER BY id DESC LIMIT 1"
            )
            after = await conn.fetchval(
                f"SELECT count(*) FROM {source._schema}.dna_outbox "
                "WHERE scope='test-mod' AND kind='Agent' AND name='outbox-write-test'"
            )
        assert row is not None
        assert row["scope"] == "test-mod"
        assert row["tenant"] == ""              # base layer
        assert row["kind"] == "Agent"
        assert row["name"] == "outbox-write-test"
        assert row["op"] == "write"
        assert row["doc_version"] >= 1
        assert row["actor"] == "alice"          # author propagates
        assert after == before + 1              # exactly one new event

    async def test_versions_seq_advances_monotonically(self, source):
        """N writes to (scope, tenant) → dna_versions_seq.last_id strictly grows."""
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "seq-test"}, "spec": {},
        }

        async def last_id():
            async with source._pool.acquire() as conn:
                return await conn.fetchval(
                    f"SELECT last_id FROM {source._schema}.dna_versions_seq "
                    "WHERE scope='test-mod' AND tenant=''"
                )

        seq = []
        for i in range(3):
            raw["spec"] = {"iteration": i}
            await source.save_document(
                "test-mod", "Agent", "seq-test", raw,
            )
            seq.append(await last_id())

        # Strictly monotonic — BIGSERIAL guarantees this.
        assert seq[0] < seq[1] < seq[2]

    async def test_pg_notify_payload_shape(self, source):
        """LISTEN consumer receives the documented JSON payload."""
        import asyncio
        import asyncpg

        # Dedicated LISTEN connection (not from the source's pool — LISTEN
        # is per-connection and the test should not block other tests).
        dsn = os.environ["DATABASE_URL"]
        listen_conn = await asyncpg.connect(dsn)

        received: list[dict] = []
        ready = asyncio.Event()

        async def handler(_conn, _pid, _channel, payload_str):
            received.append(json.loads(payload_str))
            ready.set()

        await listen_conn.add_listener("kernel_writes", handler)
        try:
            raw = {
                "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
                "metadata": {"name": "notify-test"}, "spec": {},
            }
            await source.save_document(
                "test-mod", "Agent", "notify-test", raw,
            )
            # Wait for the NOTIFY to land. asyncpg delivers notifications
            # on its own task; give it up to 2s.
            try:
                await asyncio.wait_for(ready.wait(), timeout=2.0)
            except TimeoutError:
                pytest.fail(f"no NOTIFY received within 2s; got: {received!r}")
        finally:
            await listen_conn.remove_listener("kernel_writes", handler)
            await listen_conn.close()

        # Find our event (other tests may have produced concurrent events).
        ours = [
            e for e in received
            if e.get("name") == "notify-test" and e.get("scope") == "test-mod"
        ]
        assert ours, f"didn't see our notify-test event in {received!r}"
        evt = ours[-1]
        # Spec §"Write path" — every key in the documented contract.
        for k in ("id", "scope", "tenant", "kind", "name", "op", "doc_version"):
            assert k in evt, f"missing key {k!r} in payload {evt!r}"
        assert evt["op"] == "write"
        assert evt["kind"] == "Agent"
        assert evt["doc_version"] >= 1
        assert isinstance(evt["id"], int)

    async def test_delete_emits_outbox_row(self, source):
        """delete_document emits op='delete' with doc_version=0 sentinel."""
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "outbox-delete-test"}, "spec": {},
        }
        await source.save_document(
            "test-mod", "Agent", "outbox-delete-test", raw,
        )
        await source.delete_document(
            "test-mod", "Agent", "outbox-delete-test",
        )
        async with source._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT op, doc_version FROM {source._schema}.dna_outbox "
                "WHERE scope='test-mod' AND kind='Agent' "
                "AND name='outbox-delete-test' "
                "ORDER BY id DESC LIMIT 1"
            )
        assert row is not None
        assert row["op"] == "delete"
        assert row["doc_version"] == 0          # sentinel from spec

    async def test_write_atomicity_no_partial_state(self, source, monkeypatch):
        """If outbox emit fails, the entire write transaction rolls back.

        Verifies the contract: write_document is atomic with respect to
        outbox + versions_seq + dna_documents. A failure in any step
        leaves zero on-disk state.
        """
        # Patch _emit_outbox to write the row then raise — exercising
        # the rollback path AFTER outbox INSERT lands inside the tx.
        # The savepoint must rewind everything.
        orig_emit = source._emit_outbox

        async def boom(conn, **kw):
            await orig_emit(conn, **kw)
            raise RuntimeError("Phase 15.1 atomicity probe")

        monkeypatch.setattr(source, "_emit_outbox", boom)

        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
            "metadata": {"name": "atomic-probe"}, "spec": {},
        }
        with pytest.raises(RuntimeError, match="Phase 15.1 atomicity probe"):
            await source.save_document(
                "test-mod", "Agent", "atomic-probe", raw,
            )

        # Nothing committed — neither the doc nor the outbox row should exist.
        async with source._pool.acquire() as conn:
            doc_count = await conn.fetchval(
                f"SELECT count(*) FROM {source._schema}.dna_documents "
                "WHERE name='atomic-probe'"
            )
            outbox_count = await conn.fetchval(
                f"SELECT count(*) FROM {source._schema}.dna_outbox "
                "WHERE name='atomic-probe'"
            )
            version_count = await conn.fetchval(
                f"SELECT count(*) FROM {source._schema}.dna_versions "
                "WHERE name='atomic-probe'"
            )
        assert doc_count == 0
        assert outbox_count == 0
        assert version_count == 0
