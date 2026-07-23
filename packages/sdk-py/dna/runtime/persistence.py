"""``dna.runtime.persistence`` — declarative resolution of ``ctx.persistence``
(the neutral ``{checkpoint, memory, cache}`` block ``build_copilot_context``
projects, each slot ``{backend, ref}`` or ``None``) into live LangGraph
checkpointer/store handles.

Reuses the SAME ``ref -> DNA_<REF>_URL`` slug rule ``dna.emit.scaffold``
already uses to tell a host what to provision (``pg_env_var``) — imported,
not reimplemented, so the runtime and the emitted-scaffold's env-var name can
never drift apart. That module only imports ``dna.emit`` (already a runtime
dependency via ``EmitContext``), so importing it here does not pull any
extra heavy dependency.

**Where this fits:** ``LangChainRuntime.build`` calls ``resolve_persistence``
ONLY when the host did NOT inject ``hooks.checkpointer`` — i.e. this is the
declarative FALLBACK path for a host that has no persistence lifecycle of
its own. A host that owns connection lifecycle end-to-end (dna-cloud's
``apps/copilot/app/copilot_hooks.py::open_checkpointer``, which enters the
same ``AsyncPostgresSaver``/``AsyncPostgresStore`` CMs and holds them across
the ASGI app lifespan so it can cleanly ``__aexit__`` them on shutdown)
should keep injecting via ``hooks.checkpointer``/``hooks.store`` — this
module does not replace that contract, it fills the gap for hosts that don't
have one.

**Lifecycle (read before wiring a new caller):** ``AsyncPostgresSaver.
from_conn_string`` / ``AsyncPostgresStore.from_conn_string`` are ASYNC
CONTEXT MANAGERS — entering one opens a connection pool that must be closed
via ``__aexit__`` or it leaks. ``resolve_persistence`` returns the ENTERED
saver/store (the shape ``create_agent(checkpointer=, store=)`` wants
directly) — a 2-tuple, matching the plan's signature — NOT the CMs. That
means a caller of ``resolve_persistence`` currently has no handle to close
these on shutdown, unlike ``open_checkpointer`` (which returns
``(saver, store, cms)`` precisely so its caller can). For a short-lived
process this is harmless; for a long-lived server that relies on this
fallback path (as opposed to injecting via hooks) it is a KNOWN gap — flagged
for Task 6, which decides how ``dna-cloud`` wires the two together.
"""
from __future__ import annotations

import os
from typing import Any

from dna.emit.scaffold import pg_env_var


def _pg_dsn(ref: str) -> str:
    """Read the Postgres DSN for ``ref`` from its declared env var. The ONLY
    legit env read in this module — a SECRET named declaratively by the ref,
    never a hardcoded literal env name, never a raw config value."""
    return os.environ[pg_env_var(ref)]


async def _resolve_checkpointer(slot: dict[str, Any] | None) -> Any:
    """Resolve the ``checkpoint`` slot to a live checkpointer, or ``None``
    for the framework's own in-memory default (``inmemory``/absent/``None``
    backend, or a backend this adapter does not yet wire)."""
    if not slot or slot.get("backend") != "postgres":
        return None

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    dsn = _pg_dsn(slot["ref"])
    saver = await AsyncPostgresSaver.from_conn_string(dsn).__aenter__()
    await saver.setup()
    return saver


async def _resolve_store(slot: dict[str, Any] | None) -> Any:
    """Resolve the ``memory`` slot (the STORE, per the plan's naming) to a
    live store, or ``None`` for the framework's own in-memory default."""
    if not slot or slot.get("backend") != "postgres":
        return None

    from langgraph.store.postgres.aio import AsyncPostgresStore

    dsn = _pg_dsn(slot["ref"])
    store = await AsyncPostgresStore.from_conn_string(dsn).__aenter__()
    await store.setup()
    return store


async def resolve_persistence(persistence: dict[str, Any] | None) -> tuple[Any, Any]:
    """Resolve ``EmitContext.persistence`` into a ``(checkpointer, store)``
    pair the LangChain adapter can pass straight to
    ``create_agent(checkpointer=, store=)``.

    ``persistence`` is ``{checkpoint, memory, cache}`` (each ``{backend,
    ref}`` or ``None``), or ``None`` when the copilot declares no
    ``persistence`` block at all. ``checkpoint`` resolves to the
    checkpointer; ``memory`` (cross-session long-term state) resolves to the
    store. ``cache`` has no LangChain-adapter consumer yet and is ignored
    here — not an oversight, there is nothing to wire it to today.

    ``backend == "postgres"`` is the only backend resolved to a real handle
    in C0; every other backend in the open set (``sqlite``/``mongo``/
    ``redis``/``inmemory``/``serialize``/``null``, or an absent slot) yields
    ``None`` for that slot, which LangChain's ``create_agent`` already
    treats as "use the framework's own in-memory default" — so a def naming
    a not-yet-supported backend degrades gracefully instead of crashing the
    whole copilot at boot.
    """
    persistence = persistence or {}
    checkpointer = await _resolve_checkpointer(persistence.get("checkpoint"))
    store = await _resolve_store(persistence.get("memory"))
    return checkpointer, store
