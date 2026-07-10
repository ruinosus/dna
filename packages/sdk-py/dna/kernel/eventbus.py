"""KernelEventBus — cross-process invalidation primitive (Phase 15.1).

The Kernel keeps materialized ManifestInstance + per-scope caches in
process memory. When N processes share the same Postgres source, a write
in one process must invalidate caches in all the others. Without this
primitive, the harness HTTP serves stale data after a worker writes.

Design contract (see docs/superpowers/specs/2026-04-30-phase-15-1-kernel-eventbus-design.md):

    * Producer side: `PostgresWritableSource.save_document` /
      `delete_document` / `publish` insert into `dna_outbox` and
      `pg_notify('kernel_writes', payload)` atomically inside the
      same transaction as the data write. (Phase 15.1 PR2 — done.)

    * Subscriber side (this file): `KernelEventBus.start(kernel)`
      establishes a persistent connection that LISTENs on the channel.
      Each NOTIFY → `kernel.invalidate(...)`. On disconnect, the
      adapter replays missed events from `dna_outbox` (gap detection
      via `dna_versions_seq.last_id`) before resuming LISTEN.

    * Idempotency: `kernel.invalidate(scope, tenant, kind, name, op)`
      is called for every event. It must be safe to call multiple
      times for the same event (replay during reconnect re-delivers).

This module declares the Protocol + the small `KernelEvent` payload
dataclass. The concrete Postgres adapter lives at
`dna.adapters.postgres.eventbus`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel import Kernel


KERNEL_EVENTBUS_CHANNEL = "kernel_writes"
"""Channel name. Producers and subscribers must agree.

THE single constant — the producer (`SqlAlchemySource`'s postgresql
dialect, via its outbox emitter) and the subscriber (`PostgresEventBus`)
both import it from here.
"""


def build_notify_payload(
    outbox_id: int,
    scope: str,
    tenant: str,
    kind: str,
    name: str,
    op: str,
    doc_version: int,
    author: str | None,
    write_class: str = "substantive",
) -> str:
    """Build the ``kernel_writes`` NOTIFY payload (i-076).

    THE producer half of the event contract (the consumer half is
    :class:`KernelEvent` below). Lives next to the channel constant so the
    wire shape has exactly one home — it was born as
    ``dna.adapters.postgres.source._build_notify_payload`` and moved here
    when the raw SQL adapters were retired (s-retire-raw-sql-adapters).

    MUST include ``author``: cross-process subscribers read it to honor
    author-based loop guards (``skip_if_authored_by_self`` /
    ``skip_if_authored_by_any_hook``). Dropping it makes every
    cross-process event look human-authored, which defeated the guards and
    let hook-authored writes drive a self-sustaining feedback loop. Pure +
    tiny so the contract is unit-tested without a DB.

    ``write_class`` (s-buswrite-class-substantive-cue) classifies the write
    as ``substantive`` (a real doc create/change) or ``cue`` (a pure
    metadata bump). Hooks that react to substantive writes filter out
    ``cue`` events BY CLASS — so metadata-bump feedback cycles can't close
    by construction, instead of relying on the coarse "skip any hook
    author".
    """
    return json.dumps(
        {
            "id": outbox_id, "scope": scope, "tenant": tenant,
            "kind": kind, "name": name, "op": op,
            "doc_version": doc_version, "author": author or "",
            "write_class": write_class or "substantive",
        },
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True)
class KernelEvent:
    """Identifying-only event payload.

    No doc body — subscribers re-fetch via the existing `load_all` path
    on invalidation. This keeps NOTIFY under Postgres's 8 KB payload
    limit and avoids producer/consumer schema coupling.
    """

    id: int
    """Monotonic outbox row id (BIGSERIAL). Used for gap detection on
    reconnect (consumer tracks the highest id seen per scope/tenant)."""

    scope: str
    tenant: str
    """Empty string ('') is the documented sentinel for "base layer /
    no tenant", mirroring the dna_documents convention."""

    kind: str
    name: str
    op: str
    """Either 'write' (save_document or publish) or 'delete'."""

    doc_version: int
    """`dna_documents.version` after the write; `0` for op='delete'
    (sentinel — subscribers treat delete as drop-cache, no version
    comparison)."""


@runtime_checkable
class KernelEventBus(Protocol):
    """Cross-process invalidation bus.

    Implementations are environment-specific (Postgres LISTEN/NOTIFY,
    Redis pub-sub, in-memory for tests, etc.). The Kernel only depends
    on this Protocol.
    """

    async def start(self, kernel: "Kernel") -> None:
        """Begin consuming events and dispatching them to
        `kernel.invalidate(...)`. Must not block; the consume loop
        runs as a background asyncio.Task. Idempotent: calling start
        twice is a no-op (or restarts cleanly — implementation choice
        as long as the contract holds).
        """

    async def stop(self) -> None:
        """Cancel the consume loop and release any held resources
        (connections, etc). After stop, the bus may be restarted
        with another `start()` call."""
