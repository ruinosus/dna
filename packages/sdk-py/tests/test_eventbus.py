"""Phase 15.1 PR3 — KernelEventBus + Kernel.invalidate contract tests.

Two tiers:

    * In-process tests: validate Kernel.invalidate semantics, holder
      registration, idempotency, and the Evidence-skip rule. No
      Postgres required — these run on every CI box.

    * Postgres-backed tests: validate PostgresEventBus end-to-end —
      warm-start baseline, NOTIFY → invalidation, reconnect-replay.
      Skipped without DATABASE_URL.

Cross-process tests (process A writes, process B's kernel sees the
invalidation) live in PR4 alongside the harness wiring; this PR
proves the building blocks work in isolation.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest
import pytest_asyncio


# ─── Tier 1: in-process Kernel.invalidate semantics ─────────────────


class _StubHolder:
    """Minimal MIHolder shape for invalidation tests — records reload calls."""

    def __init__(self, scope: str):
        self.scope = scope
        self.reloads = 0

    def reload(self):
        self.reloads += 1


class TestKernelInvalidateContract:
    """Phase 15.1 PR3 — Kernel.invalidate contract is idempotent, scoped,
    and respects the Evidence-skip rule.
    """

    def test_invalidate_drops_base_cache(self):
        from dna.kernel import Kernel
        from dna.extensions.helix import HelixExtension
        k = Kernel()
        # Register Agent so the kernel reads its is_schema_affecting=True
        # classification (s-kernel-kindport-classification-attrs — the schema-
        # invalidation set is now derived from the registered Kind, not a name list).
        k.load(HelixExtension())
        # Simulate a populated base cache.
        k._kcache._base = {"hr-screening": "stale-mi", "other-scope": "x"}
        k.invalidate(
            scope="hr-screening", tenant="",
            kind="Agent", name="bot", op="write",
        )
        assert "hr-screening" not in k._kcache._base
        # Other scopes untouched.
        assert k._kcache._base.get("other-scope") == "x"

    def test_invalidate_calls_holder_reload(self):
        from dna.kernel import Kernel
        k = Kernel()
        h = _StubHolder("hr-screening")
        k.register_holder(h)
        k.invalidate(
            scope="hr-screening", tenant="",
            kind="Skill", name="ls", op="write",
        )
        assert h.reloads == 1

    def test_invalidate_does_not_reload_other_scope(self):
        from dna.kernel import Kernel
        k = Kernel()
        a = _StubHolder("hr-screening")
        b = _StubHolder("other-scope")
        k.register_holder(a)
        k.register_holder(b)
        k.invalidate(
            scope="hr-screening", tenant="",
            kind="Skill", name="ls", op="write",
        )
        assert a.reloads == 1
        assert b.reloads == 0          # different scope, not touched

    def test_invalidate_skips_evidence(self):
        """Audit-stream churn-avoidance: Evidence writes don't reload."""
        from dna.kernel import Kernel
        k = Kernel()
        h = _StubHolder("hr-screening")
        k.register_holder(h)
        k._kcache._base = {"hr-screening": "stale-mi"}
        k.invalidate(
            scope="hr-screening", tenant="",
            kind="Evidence", name="ev-1", op="write",
        )
        assert h.reloads == 0
        # Cache also untouched — Evidence churn doesn't drop the cache.
        assert k._kcache._base.get("hr-screening") == "stale-mi"

    def test_invalidate_idempotent(self):
        """Replaying a known event is safe (multiple calls, no error)."""
        from dna.kernel import Kernel
        k = Kernel()
        h = _StubHolder("hr-screening")
        k.register_holder(h)
        for _ in range(3):
            k.invalidate(
                scope="hr-screening", tenant="",
                kind="Skill", name="ls", op="write",
            )
        # 3 reloads — each invalidation reloads (a no-op when holder
        # is already fresh, but still idempotent in the sense that
        # nothing breaks).
        assert h.reloads == 3

    def test_invalidate_swallows_holder_exceptions(self):
        """One bad holder must not break invalidation for the others."""
        from dna.kernel import Kernel
        k = Kernel()

        class _Bad(_StubHolder):
            def reload(self):
                raise RuntimeError("simulated holder failure")

        bad = _Bad("hr-screening")
        good = _StubHolder("hr-screening")
        k.register_holder(bad)
        k.register_holder(good)
        # Must not raise.
        k.invalidate(
            scope="hr-screening", tenant="",
            kind="Skill", name="ls", op="write",
        )
        assert good.reloads == 1       # bad's failure didn't stop good

    def test_unregister_holder_stops_reloads(self):
        from dna.kernel import Kernel
        k = Kernel()
        h = _StubHolder("hr-screening")
        k.register_holder(h)
        k.unregister_holder(h)
        k.invalidate(
            scope="hr-screening", tenant="",
            kind="Skill", name="ls", op="write",
        )
        assert h.reloads == 0

    def test_register_holder_idempotent(self):
        """Registering twice doesn't double-reload."""
        from dna.kernel import Kernel
        k = Kernel()
        h = _StubHolder("hr-screening")
        k.register_holder(h)
        k.register_holder(h)
        k.invalidate(
            scope="hr-screening", tenant="",
            kind="Skill", name="ls", op="write",
        )
        assert h.reloads == 1

    def test_event_bus_property_starts_none(self):
        from dna.kernel import Kernel
        k = Kernel()
        assert k.active_event_bus is None

    def test_event_bus_registration(self):
        from dna.kernel import Kernel

        class _StubBus:
            async def start(self, kernel): pass
            async def stop(self): pass

        k = Kernel()
        bus = _StubBus()
        k.event_bus(bus)
        assert k.active_event_bus is bus


# ─── Tier 2: PostgresEventBus end-to-end ────────────────────────────

pgmark = pytest.mark.requires_postgres


@pytest_asyncio.fixture(loop_scope="function")
async def pg_setup():
    """Per-function fixture: clean schema with migration #5 applied + a
    PostgresSource ready to write outbox events.
    """
    import asyncpg
    from dna.adapters.postgres import PostgresSource

    dsn = os.environ["DATABASE_URL"]
    schema = "dna_test_eventbus"

    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    pool = await asyncpg.create_pool(dsn)
    src = PostgresSource(pool, schema=schema)
    await src.init()

    # Seed a Module so `save_document` round-trips.
    module_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": "evbus-test"}, "spec": {"default_agent": "bot"},
    }
    await src.save_document("evbus-test", "Genome", "evbus-test", module_raw)

    yield {"dsn": dsn, "schema": schema, "source": src, "pool": pool}

    await src.close()
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.close()


@pgmark
@pytest.mark.asyncio(loop_scope="function")
class TestPostgresEventBus:

    async def test_warm_start_does_not_replay_history(self, pg_setup):
        """First-ever start treats current state as 'already seen' — no
        spurious invalidations on boot.
        """
        from dna.kernel import Kernel
        from dna.adapters.postgres.eventbus import PostgresEventBus

        # The seed (save_document above) already produced 1 outbox row.
        kernel = Kernel()
        # Stub holder + counter to detect spurious invalidations.
        h = _StubHolder("evbus-test")
        kernel.register_holder(h)

        bus = PostgresEventBus(pg_setup["dsn"], schema=pg_setup["schema"])
        await bus.start(kernel)
        try:
            # Give the consume loop a beat to warm-start + register listener.
            await asyncio.sleep(0.3)
            # Warm-start should NOT have replayed the seed write.
            assert h.reloads == 0
        finally:
            await bus.stop()

    async def test_notify_triggers_invalidation(self, pg_setup):
        """Live write → NOTIFY → kernel.invalidate → holder.reload."""
        from dna.kernel import Kernel
        from dna.adapters.postgres.eventbus import PostgresEventBus

        kernel = Kernel()
        h = _StubHolder("evbus-test")
        kernel.register_holder(h)

        bus = PostgresEventBus(pg_setup["dsn"], schema=pg_setup["schema"])
        await bus.start(kernel)
        try:
            await asyncio.sleep(0.2)        # let LISTEN attach

            # Now write — should trigger invalidation via NOTIFY.
            agent_raw = {
                "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
                "metadata": {"name": "live-bot"}, "spec": {},
            }
            await pg_setup["source"].save_document(
                "evbus-test", "Agent", "live-bot", agent_raw,
            )

            # Wait up to 2s for the NOTIFY to round-trip + dispatch.
            for _ in range(20):
                await asyncio.sleep(0.1)
                if h.reloads >= 1:
                    break
            assert h.reloads >= 1, (
                f"holder.reload never called within 2s; reloads={h.reloads}"
            )
        finally:
            await bus.stop()

    async def test_evidence_writes_skipped(self, pg_setup):
        """Evidence-kind writes flow through the bus but kernel.invalidate
        skips them — holder is NOT reloaded.
        """
        from dna.kernel import Kernel
        from dna.adapters.postgres.eventbus import PostgresEventBus

        kernel = Kernel()
        h = _StubHolder("evbus-test")
        kernel.register_holder(h)

        bus = PostgresEventBus(pg_setup["dsn"], schema=pg_setup["schema"])
        await bus.start(kernel)
        try:
            await asyncio.sleep(0.2)

            evid_raw = {
                "apiVersion": "github.com/ruinosus/dna/evidence/v1", "kind": "Evidence",
                "metadata": {"name": "ev-1"}, "spec": {"type": "test"},
            }
            await pg_setup["source"].save_document(
                "evbus-test", "Evidence", "ev-1", evid_raw,
            )

            # Wait long enough that a NOTIFY for Evidence would have
            # arrived AND dispatched if it were going to.
            await asyncio.sleep(1.0)
            assert h.reloads == 0

            # Sanity: a non-Evidence write still triggers the bus.
            agent_raw = {
                "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
                "metadata": {"name": "after-evidence"}, "spec": {},
            }
            await pg_setup["source"].save_document(
                "evbus-test", "Agent", "after-evidence", agent_raw,
            )
            for _ in range(20):
                await asyncio.sleep(0.1)
                if h.reloads >= 1:
                    break
            assert h.reloads >= 1
        finally:
            await bus.stop()

    async def test_replay_after_disconnect(self, pg_setup):
        """When the LISTEN connection drops, missed events are replayed
        from dna_outbox before re-LISTEN resumes.

        This is the killer feature: NOTIFY queues are best-effort, but
        the outbox is durable, so reconnect catches every gap.
        """
        from dna.kernel import Kernel
        from dna.adapters.postgres.eventbus import PostgresEventBus
        import asyncpg

        kernel = Kernel()
        h = _StubHolder("evbus-test")
        kernel.register_holder(h)

        # Tight backoff so the test doesn't hang.
        bus = PostgresEventBus(
            pg_setup["dsn"], schema=pg_setup["schema"],
            reconnect_backoff=[0.1, 0.2, 0.5],
        )
        await bus.start(kernel)
        try:
            await asyncio.sleep(0.3)        # let LISTEN attach + warm-start

            # Capture the consumer's connection PID then terminate it
            # from a parallel admin session — simulates network drop.
            assert bus._conn is not None
            consumer_pid = await bus._conn.fetchval("SELECT pg_backend_pid()")

            admin = await asyncpg.connect(pg_setup["dsn"])
            try:
                await admin.execute(
                    "SELECT pg_terminate_backend($1)", consumer_pid,
                )
            finally:
                await admin.close()

            # Write 3 docs while the consumer is reconnecting.
            for i in range(3):
                raw = {
                    "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
                    "metadata": {"name": f"replay-{i}"}, "spec": {"i": i},
                }
                await pg_setup["source"].save_document(
                    "evbus-test", "Agent", f"replay-{i}", raw,
                )

            # Wait for the consumer to reconnect + replay the gap.
            # Backoff is 0.1s, so 3s is plenty.
            for _ in range(30):
                await asyncio.sleep(0.1)
                if h.reloads >= 3:
                    break
            assert h.reloads >= 3, (
                f"replay incomplete after 3s; reloads={h.reloads}"
            )
        finally:
            await bus.stop()
