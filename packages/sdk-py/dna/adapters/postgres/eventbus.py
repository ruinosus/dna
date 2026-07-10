"""PostgresEventBus — LISTEN/NOTIFY consumer with reconnect + replay.

Concrete `KernelEventBus` impl backed by Postgres. The producer side is
the SQL source's postgres dialect (SqlAlchemySource outbox emitter), but
this subscriber is conceptually independent: it could subscribe to a
Postgres a different writer is using.

Lifecycle:

    1. `start(kernel)`:
        - Acquire a dedicated asyncpg connection (NOT from the source's
          pool — LISTEN holds the connection for its lifetime).
        - Warm-start: read `dna_versions_seq.last_id` per known
          (scope, tenant) so we don't replay history. Initial baseline
          treats whatever is currently on disk as "already seen".
        - LISTEN on KERNEL_EVENTBUS_CHANNEL.
        - Spawn the consume Task that translates NOTIFYs into
          `kernel.invalidate(...)` calls.

    2. On NOTIFY: parse JSON payload, advance `_last_seen[(scope, tenant)]`,
       call `kernel.invalidate(...)`. Idempotent — replaying a known
       event is a no-op on the kernel side.

    3. On disconnect (asyncpg fires the connection's terminated
       callback): the consume Task observes the closed conn, sleeps
       with exponential backoff, reconnects, replays the gap from
       `dna_outbox WHERE id > last_seen` BEFORE re-LISTENing, then
       resumes normal NOTIFY consumption.

    4. `stop()`: cancel consume Task, close conn.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TYPE_CHECKING

from dna.kernel.eventbus import (
    KERNEL_EVENTBUS_CHANNEL,
    KernelEvent,
    KernelEventBus,
)

if TYPE_CHECKING:
    import asyncpg
    from dna.kernel import Kernel

logger = logging.getLogger(__name__)


class PostgresEventBus(KernelEventBus):
    """LISTEN-on-NOTIFY KernelEventBus backed by Postgres.

    Args:
        dsn: Postgres connection string. Must be the same database as the
            producer; channel is database-scoped.
        schema: Postgres schema for the dna_outbox / dna_versions_seq
            tables. Default 'public' matches the SQL source's default.
        channel: NOTIFY channel name. Default
            `KERNEL_EVENTBUS_CHANNEL`. Override only if a deploy needs
            multiple isolated buses on the same DB.
        reconnect_backoff: List of seconds to sleep between reconnect
            attempts. The last value is used for all subsequent retries.
            Default `[1, 2, 5, 10, 30]`.
    """

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = "public",
        channel: str = KERNEL_EVENTBUS_CHANNEL,
        reconnect_backoff: list[float] | None = None,
    ) -> None:
        self._dsn = dsn
        self._schema = schema
        self._channel = channel
        self._backoff = reconnect_backoff or [1.0, 2.0, 5.0, 10.0, 30.0]

        self._kernel: "Kernel" | None = None
        self._conn: "asyncpg.Connection" | None = None
        self._task: asyncio.Task | None = None
        self._stop_requested = asyncio.Event()
        # last seen outbox.id per (scope, tenant). Advanced on every
        # delivered event AND on reconnect-replay.
        self._last_seen: dict[tuple[str, str], int] = {}

    async def start(self, kernel: "Kernel") -> None:
        """Establish the LISTEN connection + start the consume loop.

        Idempotent: a second call is a no-op while the bus is running.
        """
        if self._task is not None and not self._task.done():
            return  # already running
        self._kernel = kernel
        self._stop_requested.clear()
        self._task = asyncio.create_task(
            self._run(), name=f"PostgresEventBus({self._channel})"
        )

    async def stop(self) -> None:
        """Cancel the consume loop + close the connection."""
        self._stop_requested.set()
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        # Close conn if still open (consume loop should have closed it,
        # but be defensive).
        if self._conn is not None and not self._conn.is_closed():
            try:
                await self._conn.close()
            except Exception:
                pass
        self._conn = None

    # ─── internal ────────────────────────────────────────────────────

    async def _run(self) -> None:
        """Top-level consume loop. Wraps connect/listen in a reconnect
        loop until stop() is requested.
        """
        attempt = 0
        while not self._stop_requested.is_set():
            try:
                await self._connect_and_consume()
                # _connect_and_consume returns cleanly only on stop.
                break
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — defensive top-level
                if self._stop_requested.is_set():
                    break
                wait = self._backoff[min(attempt, len(self._backoff) - 1)]
                logger.warning(
                    "PostgresEventBus: connection lost (%s: %s); "
                    "retry in %.1fs (attempt %d)",
                    type(e).__name__, e, wait, attempt + 1,
                )
                attempt += 1
                try:
                    await asyncio.wait_for(
                        self._stop_requested.wait(), timeout=wait,
                    )
                    # If stop arrived during sleep, exit.
                    return
                except TimeoutError:
                    pass  # backoff elapsed, try reconnect
            else:
                attempt = 0

    async def _connect_and_consume(self) -> None:
        """One connect+LISTEN session. Returns when stop is requested.
        Raises on connection errors (or termination by Postgres) so
        `_run` can retry.
        """
        import asyncpg  # local — avoid hard dep at import time

        self._conn = await asyncpg.connect(self._dsn)
        # Termination listener: fires when Postgres closes the conn
        # (pg_terminate_backend, server restart, network drop). We use
        # this to wake the parked coroutine and force `_run` to retry.
        conn_terminated = asyncio.Event()

        def _on_terminated(_c) -> None:
            # Signal-safe — asyncpg calls this from its own reader task.
            # Setting an asyncio.Event is thread/task safe in CPython.
            conn_terminated.set()

        self._conn.add_termination_listener(_on_terminated)
        try:
            # Replay any events missed since last_seen BEFORE re-LISTEN.
            # If this is the cold start and no scopes are tracked yet,
            # warm-start from dna_versions_seq.last_id (treat current
            # state as baseline; do NOT replay history).
            if not self._last_seen:
                await self._warm_start_baseline(self._conn)
            else:
                await self._replay_gap(self._conn)

            # Now LISTEN. Notifications arrive via the listener callback.
            await self._conn.add_listener(self._channel, self._on_notify)
            try:
                # Park here until either stop is requested OR the conn
                # is terminated externally. Whichever fires first wins:
                #   - stop_requested → return cleanly (caller exits loop).
                #   - conn_terminated → raise so `_run` can reconnect.
                stop_task = asyncio.create_task(self._stop_requested.wait())
                term_task = asyncio.create_task(conn_terminated.wait())
                done, pending = await asyncio.wait(
                    {stop_task, term_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                if conn_terminated.is_set() and not self._stop_requested.is_set():
                    # Connection died on us — force reconnect via _run.
                    raise ConnectionError(
                        "PostgresEventBus: LISTEN connection terminated"
                    )
            finally:
                try:
                    await self._conn.remove_listener(
                        self._channel, self._on_notify
                    )
                except Exception:
                    pass
        finally:
            try:
                self._conn.remove_termination_listener(_on_terminated)
            except Exception:
                pass
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None

    async def _warm_start_baseline(self, conn: "asyncpg.Connection") -> None:
        """First-ever connect: snapshot current `dna_versions_seq.last_id`
        per (scope, tenant) so we treat present state as 'already seen'.
        Otherwise we'd replay every historical event on first boot.
        """
        rows = await conn.fetch(
            f"SELECT scope, tenant, last_id FROM {self._schema}.dna_versions_seq"
        )
        for r in rows:
            self._last_seen[(r["scope"], r["tenant"])] = r["last_id"]
        logger.info(
            "PostgresEventBus: warm-start baseline — %d (scope, tenant) tracked",
            len(self._last_seen),
        )

    async def _replay_gap(self, conn: "asyncpg.Connection") -> None:
        """On reconnect: query `dna_outbox` for events with id > last_seen
        per (scope, tenant) and dispatch each through the kernel.

        Replay happens BEFORE re-LISTEN so we can't miss events emitted
        during the disconnect window.
        """
        if not self._last_seen:
            await self._warm_start_baseline(conn)
            return
        for (scope, tenant), last_id in list(self._last_seen.items()):
            rows = await conn.fetch(
                f"SELECT id, scope, tenant, kind, name, op, doc_version "
                f"FROM {self._schema}.dna_outbox "
                "WHERE scope = $1 AND tenant = $2 AND id > $3 "
                "ORDER BY id",
                scope, tenant, last_id,
            )
            for r in rows:
                evt = KernelEvent(
                    id=r["id"], scope=r["scope"], tenant=r["tenant"],
                    kind=r["kind"], name=r["name"], op=r["op"],
                    doc_version=r["doc_version"],
                )
                self._dispatch(evt)
            if rows:
                logger.info(
                    "PostgresEventBus: replayed %d events for (%s, %s)",
                    len(rows), scope, tenant,
                )

    def _on_notify(
        self,
        _conn: "asyncpg.Connection",
        _pid: int,
        _channel: str,
        payload: str,
    ) -> None:
        """asyncpg listener callback. Synchronous (asyncpg's contract).

        Parses the payload + dispatches. Errors are logged + swallowed
        so a malformed payload doesn't tear down the connection.
        """
        try:
            d = json.loads(payload)
            evt = KernelEvent(
                id=int(d["id"]),
                scope=d["scope"],
                tenant=d.get("tenant", ""),
                kind=d["kind"],
                name=d["name"],
                op=d["op"],
                doc_version=int(d.get("doc_version", 0)),
            )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error(
                "PostgresEventBus: invalid payload %r — %s",
                payload, e,
            )
            return
        self._dispatch(evt)

    def _dispatch(self, evt: KernelEvent) -> None:
        """Advance `_last_seen` and call `kernel.invalidate(...)`.

        Idempotent — replaying an event already past `_last_seen` is a
        cheap kernel no-op (the kernel's invalidate is itself idempotent).
        """
        key = (evt.scope, evt.tenant)
        prev = self._last_seen.get(key, 0)
        if evt.id > prev:
            self._last_seen[key] = evt.id
        if self._kernel is None:
            return
        try:
            self._kernel.invalidate(
                scope=evt.scope, tenant=evt.tenant,
                kind=evt.kind, name=evt.name, op=evt.op,
            )
        except Exception as e:  # noqa: BLE001 — never break the bus
            logger.exception(
                "PostgresEventBus: kernel.invalidate raised on %s — %s",
                evt, e,
            )
