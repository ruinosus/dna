"""HookRegistry — middleware (use) + events (on / on_async) for kernel lifecycle.

Middleware: intercepts and can modify data flowing through the kernel.
  k.use("pre_build_prompt", fn)  → fn(ctx) → modified ctx

Events: fire-and-forget notifications. Two channels:
  - Sync listeners (legacy + in-process metrics/logging):
      k.on("post_build_prompt", fn)     # fn: (ctx) -> None
      k.hooks.emit("post_build_prompt", ctx)
  - Async listeners (I/O-heavy: event bus publishers, network calls, db writes):
      k.on_async("post_save", fn)        # fn: (ctx) -> Awaitable[None]
      await k.hooks.emit_async("post_save", ctx)

Design rationale — dual channel over "make everything async":
  - Sync consumers (logging, metrics, error counters) don't need a loop and
    historically attach to hooks that fire in sync code paths (parse_error,
    post_build_prompt from a sync prompt_builder.build()). Forcing async on
    them would cascade-break the whole SDK.
  - Async consumers want to `await` directly (event bus publish, HTTP, DB)
    without the `asyncio.create_task` workaround that drops errors and has
    no backpressure.
  - Callers of `emit_async` (write_document, delete_document — already async)
    see both channels fire; sync listeners still run, async ones are awaited.
  - Callers of `emit` (sync code paths) run only sync listeners. Registering
    an async listener for a hook only fired from sync emit used to be an
    INVISIBLE no-op (debug-only log). Since s-kernel-fail-soft-audit the
    skip is loud: `emit` warns ONCE per (hook, listener) at WARNING level,
    counts every skip in `skipped_async_emits[hook]`, and accepts
    `strict=True` to raise instead — for emit sites where reaching every
    listener is load-bearing.

  Kernel-internal emit posture (s-kernel-fail-soft-audit, documented
  decision): the kernel's own sync emits (`parse_error`,
  `kinddef_conflict`, `extension_error`, and `post_build_prompt` from the
  SYNC prompt_builder path) are observability funnels — a mis-wired async
  listener there means lost telemetry, not corrupted state, so they emit
  with strict=False and rely on the warn-once. Async call sites reach both
  channels instead: `prompt_kernel.build_prompt_async` awaits `emit_async`
  for `post_build_prompt` (it used to fire sync `emit` and silently skip
  async listeners despite being in an async context).

Veto hooks (s-write-path-despecialize): ordered listeners that can BLOCK the
operation by raising. Unlike `emit`/`emit_async` (fire-and-forget, errors
swallowed), `emit_veto` runs listeners in ascending `priority` order and lets
exceptions PROPAGATE — a raise IS the veto. Listeners may also mutate the
typed context in place (e.g. preserve fields on `ctx.raw`) — the write
proceeds with the mutated payload. Sync and async listeners share one
ordered chain.

  k.hooks.on_veto("pre_save", fn, priority=20, key="helix.prompt-budget")
  await k.hooks.emit_veto("pre_save", PreSaveContext(...))

`key` makes registration idempotent: re-registering the same key REPLACES
the previous listener (extensions may be re-loaded onto a shared registry).

Hook points:
  - pre_build_prompt:  called before prompt rendering, can modify context
  - post_build_prompt: called after prompt rendering, receives final prompt
  - pre_save:          called before document save, can reject (veto channel;
                       emitted by kernel.write_document with PreSaveContext)
  - post_save:         called after document save  [fires via emit_async]
  - post_delete:       called after document delete [fires via emit_async]
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Union

logger = logging.getLogger(__name__)


@dataclass
class HookContext:
    """Data passed to middleware and event hooks."""
    scope: str = ""
    agent: str | None = None
    kind: str | None = None
    name: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    prompt: str | None = None
    layer: tuple[str, str] | None = None  # Layer context for post_save/post_delete (phase 2a.0)


@dataclass
class PreSaveContext:
    """Typed context for the ``pre_save`` veto hook.

    Handed to every veto listener BEFORE the document reaches the source
    adapter. ``raw`` is the live payload — listeners may mutate it in place
    (the write persists the mutated dict). ``kernel`` is the kernel the
    write is flowing through (tenant-bound copy when applicable) so guards
    can do reads (``get_document``, ``model_profile``, ...) without module
    globals. Raising from a listener vetoes the write.
    """
    scope: str
    kind: str
    name: str
    raw: dict[str, Any]
    tenant: str | None = None
    layer: tuple[str, str] | None = None
    kernel: Any = None


# Middleware: (HookContext) -> HookContext
MiddlewareFn = Callable[[HookContext], HookContext]
# Event (sync): (HookContext) -> None
EventFn = Callable[[HookContext], None]
# Event (async): (HookContext) -> Awaitable[None]
AsyncEventFn = Callable[[HookContext], Awaitable[None]]
# Veto listener: sync or async; raising vetoes the operation.
VetoFn = Callable[[Any], Union[None, Awaitable[None]]]


class HookRegistry:
    """Manages middleware chains and event subscribers (sync + async)."""

    def __init__(self) -> None:
        self._middleware: dict[str, list[MiddlewareFn]] = {}
        self._events: dict[str, list[EventFn]] = {}
        self._async_events: dict[str, list[AsyncEventFn]] = {}
        # Veto channel — hook → list of (priority, seq, key, fn). seq keeps
        # registration order stable among equal priorities.
        self._veto: dict[str, list[tuple[int, int, "str | None", VetoFn]]] = {}
        self._veto_seq: int = 0
        # s-kernel-fail-soft-audit — sync-emit async-listener skip tracking:
        # warn ONCE per (hook, listener) + count every skip per hook so a
        # mis-wired listener is visible instead of an invisible no-op.
        self._async_skip_warned: set[tuple[str, str]] = set()
        self.skipped_async_emits: dict[str, int] = {}

    def use(self, hook: str, fn: MiddlewareFn) -> None:
        """Register middleware. Called in order, each receives output of previous."""
        self._middleware.setdefault(hook, []).append(fn)

    def on(self, hook: str, fn: Union[EventFn, AsyncEventFn]) -> None:
        """Register event subscriber. Fire-and-forget, errors logged but not raised.

        Accepts either sync ``fn(ctx) -> None`` or async ``async fn(ctx) -> None``.
        Async functions are routed to the async channel automatically — callers
        that invoke ``emit`` (sync) will skip them; callers that invoke
        ``emit_async`` run both channels.
        """
        if inspect.iscoroutinefunction(fn):
            self._async_events.setdefault(hook, []).append(fn)  # type: ignore[arg-type]
        else:
            self._events.setdefault(hook, []).append(fn)  # type: ignore[arg-type]

    def on_async(self, hook: str, fn: AsyncEventFn) -> None:
        """Explicit async-only registration.

        Prefer ``on()`` — it autodetects. ``on_async`` is here for symmetry
        and for lambdas / partials where ``iscoroutinefunction`` returns False
        incorrectly.
        """
        self._async_events.setdefault(hook, []).append(fn)

    def run_middleware(self, hook: str, ctx: HookContext) -> HookContext:
        """Run middleware chain. Returns modified context."""
        for fn in self._middleware.get(hook, []):
            ctx = fn(ctx)
        return ctx

    def emit(self, hook: str, ctx: HookContext, *, strict: bool = False) -> None:
        """Sync emit. Runs only sync listeners.

        If async listeners exist for this hook they CANNOT run here — the
        caller must use ``emit_async`` to reach them. The skip is loud
        (s-kernel-fail-soft-audit):

        - ``strict=False`` (default): each skipped listener is counted in
          ``skipped_async_emits[hook]`` and a WARNING fires once per
          (hook, listener) — a mis-wired async listener is visible, not
          an invisible no-op. Used by the kernel's own observability
          funnels (parse_error / kinddef_conflict / extension_error /
          sync-path post_build_prompt) where taking the operation down
          over a listener wiring mistake would be worse than the skip.
        - ``strict=True``: raise RuntimeError instead — for emit sites
          where skipping a listener would be a bug, not lost telemetry.
        """
        for fn in self._events.get(hook, []):
            try:
                fn(ctx)
            except Exception as e:
                logger.warning("Hook %s subscriber error: %s", hook, e)
        skipped = self._async_events.get(hook)
        if skipped:
            self.skipped_async_emits[hook] = (
                self.skipped_async_emits.get(hook, 0) + len(skipped)
            )
            if strict:
                names = [getattr(fn, "__qualname__", repr(fn)) for fn in skipped]
                raise RuntimeError(
                    f"Hook {hook!r} was emitted via sync emit(strict=True) but "
                    f"has {len(skipped)} async listener(s) {names} that cannot "
                    f"run — use emit_async() at this call site."
                )
            for fn in skipped:
                key = (hook, getattr(fn, "__qualname__", repr(fn)))
                if key in self._async_skip_warned:
                    continue
                self._async_skip_warned.add(key)
                logger.warning(
                    "Hook %s has async listener %s but was fired via sync "
                    "emit(); the listener was SKIPPED (total skips for this "
                    "hook: %d). Use emit_async() to reach it. "
                    "(warned once per (hook, listener))",
                    hook, key[1], self.skipped_async_emits[hook],
                )

    async def emit_async(self, hook: str, ctx: HookContext) -> None:
        """Async emit. Runs sync listeners inline, then awaits each async listener.

        Use from async call sites (kernel.write_document, kernel.delete_document).
        Errors in any listener are logged and do NOT prevent other listeners
        from running.
        """
        # Sync listeners first (same behavior as emit()).
        for fn in self._events.get(hook, []):
            try:
                fn(ctx)
            except Exception as e:
                logger.warning("Hook %s (sync) subscriber error: %s", hook, e)
        # Async listeners — await each. No gather() so errors in one don't
        # cancel the others; simple linear await keeps ordering deterministic.
        for fn in self._async_events.get(hook, []):
            try:
                await fn(ctx)
            except Exception as e:
                logger.warning("Hook %s (async) subscriber error: %s", hook, e)

    # -- Veto channel (s-write-path-despecialize) -----------------------------

    def on_veto(
        self, hook: str, fn: VetoFn, *,
        priority: int = 0, key: str | None = None,
    ) -> None:
        """Register a veto listener on ``hook``.

        Listeners run in ascending ``priority`` (ties keep registration
        order). Raising from a listener PROPAGATES to the emitter — that is
        the veto. Sync and async callables both work.

        ``key`` (recommended: ``"<extension>.<rule>"``) makes registration
        idempotent — a second ``on_veto`` with the same key REPLACES the
        earlier listener instead of stacking a duplicate.
        """
        listeners = self._veto.setdefault(hook, [])
        if key is not None:
            listeners[:] = [entry for entry in listeners if entry[2] != key]
        self._veto_seq += 1
        listeners.append((priority, self._veto_seq, key, fn))
        listeners.sort(key=lambda entry: (entry[0], entry[1]))

    async def emit_veto(self, hook: str, ctx: Any) -> None:
        """Run veto listeners for ``hook`` in priority order.

        Unlike ``emit``/``emit_async``, exceptions are NOT swallowed — the
        first raise aborts the chain and propagates to the caller (the
        operation is vetoed). Listeners may mutate ``ctx`` in place.
        """
        for _prio, _seq, _key, fn in self._veto.get(hook, []):
            result = fn(ctx)
            if inspect.isawaitable(result):
                await result

    def has_veto(self, hook: str) -> bool:
        """Check if any veto listeners are registered for ``hook``."""
        return bool(self._veto.get(hook))

    def has(self, hook: str) -> bool:
        """Check if any middleware, events (sync or async) or veto listeners
        are registered."""
        return (
            bool(self._middleware.get(hook))
            or bool(self._events.get(hook))
            or bool(self._async_events.get(hook))
            or bool(self._veto.get(hook))
        )
