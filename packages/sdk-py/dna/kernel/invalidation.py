"""InvalidationController — the kernel's cache-coherence fan-out, extracted from
the Kernel god-object (kernel-decompose-continue).

This is the cache-invalidation *logic* (write-observer fan-out, the per-event
invalidate, the real `_invalidate_internal` work, and the `batch_writes`
coalescing context manager). The kernel RETAINS the write-mediation core
(write_document / delete_document) — invalidation is the cache-coherence concern
that hangs off it.

STATELESS by design: the controller holds only a back-ref to the kernel. All
mutable state (``_batch_mode_depth``, ``_batch_pending``, ``_write_observers``,
``_holders``) stays on the kernel instance, so ``with_tenant`` shallow-copy
semantics are preserved EXACTLY (each kernel copy keeps its own batch depth; the
observer/holder lists shallow-copy as before). The registration setters
(``on_write`` / ``register_holder`` / ``unregister_holder`` / ``event_bus``)
also stay on the kernel — they just append to that state.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import InvalidationHost

_logger = logging.getLogger(__name__)


class InvalidationController:
    """Cache-coherence fan-out for write/delete events. One per kernel; stateless
    (state lives on the kernel, reached via the back-ref)."""

    def __init__(self, kernel: "InvalidationHost") -> None:
        self._k = kernel

    def fire_write_observers(
        self, scope: str, kind: str, name: str, op: str, tenant: str = "",
    ) -> None:
        """Invoke all registered on_write callbacks. Swallows exceptions.
        Suppressed inside a ``batch_writes()`` block — the batch exit fires one
        invalidate per touched scope which fans out here once."""
        k = self._k
        if k._batch_mode_depth > 0:
            return
        for cb in getattr(k, "_write_observers", []):
            try:
                try:
                    cb(scope, kind, name, op, tenant)
                except TypeError:
                    # Back-compat: legacy 4-arg callbacks. Drop tenant.
                    cb(scope, kind, name, op)
            except Exception as e:  # noqa: BLE001
                # fail-soft: observers are best-effort fan-out — but a raising
                # observer means SOME cache/SSE consumer just missed a write
                # (stale UI), so the failure logs loud, never silent.
                _logger.warning(
                    "write observer %r raised for %s/%s/%s (%s): %s",
                    getattr(cb, "__qualname__", cb), scope, kind, name, op, e,
                )

    @contextlib.contextmanager
    def batch_writes(self):
        """Suppress per-write reload + observer fan-out for the block; on exit,
        fire ONE consolidated invalidation per touched scope. Reentrant — nested
        blocks coalesce; only the outermost exit flushes."""
        k = self._k
        k._batch_mode_depth += 1
        try:
            yield
        finally:
            k._batch_mode_depth -= 1
            if k._batch_mode_depth == 0:
                pending = k._batch_pending
                k._batch_pending = []
                # Dedupe: keep the last event per scope (informational —
                # invalidate_internal drops the full base cache regardless).
                seen: dict[str, tuple[str, str, str, str, str]] = {}
                for evt in pending:
                    seen[evt[0]] = evt
                for scope_, tenant_, kind_, name_, op_ in seen.values():
                    self.invalidate_internal(
                        scope=scope_, tenant=tenant_, kind=kind_, name=name_, op=op_,
                    )

    def invalidate(
        self, *, scope: str, tenant: str = "", kind: str, name: str, op: str,
    ) -> None:
        """Invalidate in-process caches for a (scope, tenant) write/delete event.
        Idempotent. Inside a ``batch_writes()`` block, buffers the event and
        skips the expensive reload + fan-out (the outermost exit drains it)."""
        k = self._k
        if k._batch_mode_depth > 0:
            k._batch_pending.append((scope, tenant, kind, name, op))
            return
        self.invalidate_internal(
            scope=scope, tenant=tenant, kind=kind, name=name, op=op,
        )

    def invalidate_internal(
        self, *, scope: str, tenant: str, kind: str, name: str, op: str,
    ) -> None:
        """Real invalidation work — bypasses the batch-mode short-circuit.
        Called from ``invalidate()`` and the ``batch_writes()`` exit flush."""
        k = self._k
        # 1. Evidence skip — preserve audit-stream churn-avoidance.
        if kind == "Evidence":
            return

        # 2. Drop kernel-level base cache ONLY for schema-changing kinds.
        # User-data writes have their own granular doc cache; the per-scope MI
        # cache stays warm.
        if kind in k._SCHEMA_INVALIDATING_KINDS:
            k._kcache.base_drop(scope)

        # 2b. Cross-scope surgical invalidation via the reverse-dep observer
        # graph (Phase 17) — populated in resolve_document.
        observers = getattr(k, "_layer_observers", None)
        if observers is not None:
            parent_key = (scope, kind, name, tenant)
            dependents = observers.get(parent_key)
            if dependents:
                for child_scope, child_tenant in list(dependents):
                    # Drop the dependent's keys DIRECTLY (O(dependents)). The
                    # granular tenant component is stored as `tenant or ""`, so
                    # the child's own tenant + base cover its entries.
                    for t in {child_tenant or "", ""}:
                        k._kcache.doc_drop_key((child_scope, kind, name, t))
                    # Drop child MI cache so next mi.all/one_async re-walks.
                    k._kcache.base_drop(child_scope)
                # Evict the observer entry on drop — re-registers on next resolve.
                observers.pop(parent_key, None)

        # 3. Reload holders bound to this scope. Inside an event loop, schedule
        # the async reload on it so the source pool stays on the right loop;
        # otherwise call sync reload (workers / tests).
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        for holder in list(getattr(k, "_holders", [])):
            try:
                if getattr(holder, "scope", None) != scope:
                    continue
                reload_async = getattr(holder, "reload_async", None)
                if loop is not None and reload_async is not None:
                    loop.create_task(reload_async())
                else:
                    holder.reload()
            except Exception:
                _logger.exception(
                    "Kernel.invalidate: holder.reload() raised for scope=%r", scope,
                )

        # 4. Fan out to in-process on_write observers — critical for cross-process
        # writes (CLI / worker → Postgres outbox → EventBus → invalidate): without
        # this the SSE observer never fires and Studio stays stale. Local writes
        # may double-fire (harmless — the SSE handler is idempotent).
        self.fire_write_observers(scope, kind, name, op, tenant=tenant)
