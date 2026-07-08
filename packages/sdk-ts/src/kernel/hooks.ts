/**
 * HookRegistry — middleware (use) + events (on / onAsync) for kernel lifecycle.
 *
 * 1:1 parity with Python dna.v3.kernel.hooks.
 *
 * Dual-channel events:
 *   - Sync listeners (legacy + in-process metrics/logging):
 *       k.on("post_build_prompt", fn)        // fn: (ctx) => void
 *       k.hooks.emit("post_build_prompt", ctx)
 *   - Async listeners (I/O-heavy: event bus publishers, HTTP, DB writes):
 *       k.onAsync("post_save", fn)            // fn: (ctx) => Promise<void>
 *       await k.hooks.emitAsync("post_save", ctx)
 *
 * Sync `on()` autodetects based on whether the handler returns a Promise.
 * Callers that invoke `emit` (sync) skip async listeners — callers that
 * invoke `emitAsync` run both channels. The skip is LOUD
 * (s-kernel-fail-soft-audit, Py twin semantics): `emit` counts every skip
 * in `skippedAsyncEmits` and console.warns ONCE per (hook, listener);
 * `emit(hook, ctx, { strict: true })` throws instead — for call sites
 * where skipping a listener would be a bug, not lost telemetry. The
 * kernel's own sync emits (parse_error / kinddef_conflict /
 * extension_error / sync-path post_build_prompt) are observability
 * funnels and stay non-strict.
 *
 * Veto hooks (s-write-path-despecialize): ordered listeners that can BLOCK
 * the operation by throwing. Unlike `emit`/`emitAsync` (fire-and-forget,
 * errors swallowed), `emitVeto` runs listeners in ascending `priority`
 * order and lets exceptions PROPAGATE — a throw IS the veto. Listeners may
 * also mutate the typed context in place (e.g. fields on `ctx.raw`) — the
 * write proceeds with the mutated payload.
 *
 *   k.hooks.onVeto("pre_save", fn, { priority: 20, key: "helix.rule" });
 *   await k.hooks.emitVeto("pre_save", ctx);
 *
 * `key` makes registration idempotent: re-registering the same key REPLACES
 * the previous listener (extensions may be re-loaded onto a shared registry).
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * The full vocabulary of hook names the SDK itself emits/consumes
 * (s-dna-typed-hook-names). Py twin: `HookName` / `KNOWN_HOOK_NAMES` in
 * dna/kernel/hooks.py. Both sides are locked to the shared fixture
 * `tests/parity-fixtures/port-surface-parity.json` (section `hook_names`)
 * by tests/hook-names.test.ts + tests/test_hook_names.py — vocabulary
 * drift turns both suites red. Add a name HERE + fixture + Py, never ad hoc.
 */
export const KNOWN_HOOK_NAMES = [
  "pre_build_prompt",
  "post_build_prompt",
  "pre_save",
  "post_save",
  "post_delete",
  "kinddef_conflict",
  "parse_error",
  "extension_error",
] as const;

export type HookName = (typeof KNOWN_HOOK_NAMES)[number];

/**
 * Parameter type for hook-name arguments: the known vocabulary (with editor
 * autocomplete) plus arbitrary strings for back-compat (custom hooks stay
 * legal — they warn at runtime, never break). A misspelled builtin name
 * like `on("pre_saev", fn)` used to compile, run, and never fire, silently;
 * the registry now console.warns once per (registry, name).
 */
export type HookNameArg = HookName | (string & {});

const KNOWN_HOOK_SET: ReadonlySet<string> = new Set(KNOWN_HOOK_NAMES);

export interface HookContext {
  scope: string;
  agent?: string;
  kind?: string;
  name?: string;
  data: Record<string, unknown>;
  prompt?: string;
  /** Optional layer tuple when the write targeted a layer overlay.
   *  `undefined` means the write went to the scope's base. Set by
   *  Kernel.writeDocument when a layer kwarg is passed (Phase 2a.0). */
  layer?: [string, string];
}

export type Middleware = (ctx: HookContext) => HookContext;
export type EventHandler = (ctx: HookContext) => void;
export type AsyncEventHandler = (ctx: HookContext) => Promise<void>;

/** Typed context for the `pre_save` veto hook (s-write-path-despecialize).
 *  Handed to every veto listener BEFORE the document reaches the source
 *  adapter. `raw` is the live payload — listeners may mutate it in place.
 *  `kernel` is the kernel the write flows through (tenant-bound copy when
 *  applicable) so guards can read (getDocument, ...). Throwing vetoes the
 *  write. Py twin: dna.kernel.hooks.PreSaveContext. */
export interface PreSaveContext {
  scope: string;
  kind: string;
  name: string;
  raw: Record<string, unknown>;
  tenant: string | null;
  layer?: [string, string];
  kernel: unknown;
}

/** Veto listener: sync or async; throwing vetoes the operation. */
export type VetoHandler = (ctx: PreSaveContext) => void | Promise<void>;

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

export class HookRegistry {
  private _middleware: Map<string, Middleware[]> = new Map();
  private _events: Map<string, EventHandler[]> = new Map();
  private _asyncEvents: Map<string, AsyncEventHandler[]> = new Map();
  /** Veto channel — hook → list of {priority, seq, key, fn}. `seq` keeps
   *  registration order stable among equal priorities. */
  private _veto: Map<
    string,
    Array<{ priority: number; seq: number; key: string | null; fn: VetoHandler }>
  > = new Map();
  private _vetoSeq = 0;
  /** s-kernel-fail-soft-audit — sync-emit async-listener skip tracking:
   *  warn ONCE per (hook, listener) + count every skip per hook so a
   *  mis-wired listener is visible instead of an invisible no-op. */
  private _asyncSkipWarned: Set<string> = new Set();
  readonly skippedAsyncEmits: Map<string, number> = new Map();
  /** s-dna-typed-hook-names — unknown-name warn-once tracking (per
   *  registry, per name; same posture as _asyncSkipWarned). */
  private _unknownHookWarned: Set<string> = new Set();

  /** Warn (once per registry+name) on a name outside `HookName`.
   *  Fail-loud, NOT fail-closed: custom hook names keep working
   *  (back-compat / third-party channels), but a typo of a builtin name —
   *  the listener that never fires — is now visible. Py twin semantics:
   *  `UnknownHookNameWarning`. */
  private _checkHookName(hook: string): void {
    if (KNOWN_HOOK_SET.has(hook) || this._unknownHookWarned.has(hook)) return;
    this._unknownHookWarned.add(hook);
    console.warn(
      `unknown hook name ${JSON.stringify(hook)} — known: ` +
      `${JSON.stringify([...KNOWN_HOOK_NAMES].sort())}. A listener on (or ` +
      `emit of) a misspelled hook never fires; custom names still work ` +
      `(warning only).`,
    );
  }

  /** Register middleware. Called in order, each receives output of previous. */
  use(hook: HookNameArg, fn: Middleware): void {
    this._checkHookName(hook);
    const list = this._middleware.get(hook) ?? [];
    list.push(fn);
    this._middleware.set(hook, list);
  }

  /**
   * Register event subscriber. Fire-and-forget, errors logged but not raised.
   *
   * Autodetects sync vs async via `fn.constructor.name === "AsyncFunction"`.
   * Async functions are routed to the async channel — callers using `emit`
   * (sync) skip them; `emitAsync` runs both.
   */
  on(hook: HookNameArg, fn: EventHandler | AsyncEventHandler): void {
    this._checkHookName(hook);
    // AsyncFunction detection: works for `async function`. For regular
    // functions that happen to return Promises, prefer `onAsync` explicitly.
    if ((fn as Function).constructor?.name === "AsyncFunction") {
      const list = this._asyncEvents.get(hook) ?? [];
      list.push(fn as AsyncEventHandler);
      this._asyncEvents.set(hook, list);
    } else {
      const list = this._events.get(hook) ?? [];
      list.push(fn as EventHandler);
      this._events.set(hook, list);
    }
  }

  /** Explicit async-only registration. Prefer `on()` — this is here for
   *  symmetry and for non-`async function` callables (arrow with Promise
   *  body, partials) where AsyncFunction detection returns false. */
  onAsync(hook: HookNameArg, fn: AsyncEventHandler): void {
    this._checkHookName(hook);
    const list = this._asyncEvents.get(hook) ?? [];
    list.push(fn);
    this._asyncEvents.set(hook, list);
  }

  /** Run middleware chain. Returns modified context. */
  runMiddleware(hook: HookNameArg, ctx: HookContext): HookContext {
    this._checkHookName(hook);
    for (const fn of this._middleware.get(hook) ?? []) {
      ctx = fn(ctx);
    }
    return ctx;
  }

  /**
   * Sync emit. Runs only sync listeners. If async listeners exist for this
   * hook they CANNOT run here — the caller must use `emitAsync` to reach
   * them. The skip is loud (s-kernel-fail-soft-audit):
   *
   * - default: each skipped listener is counted in `skippedAsyncEmits` and
   *   a console.warn fires once per (hook, listener) — a mis-wired async
   *   listener is visible, not an invisible no-op.
   * - `strict: true`: throw instead — for emit sites where skipping a
   *   listener would be a bug, not lost telemetry.
   */
  emit(hook: HookNameArg, ctx: HookContext, opts?: { strict?: boolean }): void {
    this._checkHookName(hook);
    for (const fn of this._events.get(hook) ?? []) {
      try {
        fn(ctx);
      } catch (e) {
        console.warn(`Hook ${hook} subscriber error:`, e);
      }
    }
    const skipped = this._asyncEvents.get(hook) ?? [];
    if (skipped.length > 0) {
      const total = (this.skippedAsyncEmits.get(hook) ?? 0) + skipped.length;
      this.skippedAsyncEmits.set(hook, total);
      if (opts?.strict) {
        const names = skipped.map((fn) => fn.name || "<anonymous>");
        throw new Error(
          `Hook ${JSON.stringify(hook)} was emitted via sync emit(strict) ` +
          `but has ${skipped.length} async listener(s) ` +
          `${JSON.stringify(names)} that cannot run — use emitAsync() at ` +
          `this call site.`,
        );
      }
      for (const fn of skipped) {
        const key = `${hook}\0${fn.name || "<anonymous>"}`;
        if (this._asyncSkipWarned.has(key)) continue;
        this._asyncSkipWarned.add(key);
        console.warn(
          `Hook ${hook} has async listener ${fn.name || "<anonymous>"} but ` +
          `was fired via sync emit(); the listener was SKIPPED (total ` +
          `skips for this hook: ${total}). Use emitAsync() to reach it. ` +
          `(warned once per (hook, listener))`,
        );
      }
    }
  }

  /**
   * Async emit. Runs sync listeners inline, then awaits each async listener.
   * Use from async call sites (kernel.writeDocument, kernel.deleteDocument).
   * Errors in any listener are logged and do NOT prevent other listeners.
   */
  async emitAsync(hook: HookNameArg, ctx: HookContext): Promise<void> {
    this._checkHookName(hook);
    for (const fn of this._events.get(hook) ?? []) {
      try {
        fn(ctx);
      } catch (e) {
        console.warn(`Hook ${hook} (sync) subscriber error:`, e);
      }
    }
    for (const fn of this._asyncEvents.get(hook) ?? []) {
      try {
        await fn(ctx);
      } catch (e) {
        console.warn(`Hook ${hook} (async) subscriber error:`, e);
      }
    }
  }

  // -- Veto channel (s-write-path-despecialize) ------------------------------

  /**
   * Register a veto listener on `hook`. Listeners run in ascending
   * `priority` (ties keep registration order). Throwing from a listener
   * PROPAGATES to the emitter — that is the veto. Sync and async callables
   * both work.
   *
   * `key` (recommended: `"<extension>.<rule>"`) makes registration
   * idempotent — a second `onVeto` with the same key REPLACES the earlier
   * listener instead of stacking a duplicate.
   */
  onVeto(
    hook: HookNameArg,
    fn: VetoHandler,
    opts?: { priority?: number; key?: string },
  ): void {
    this._checkHookName(hook);
    const listeners = this._veto.get(hook) ?? [];
    const key = opts?.key ?? null;
    const filtered = key !== null
      ? listeners.filter((entry) => entry.key !== key)
      : listeners;
    this._vetoSeq += 1;
    filtered.push({
      priority: opts?.priority ?? 0, seq: this._vetoSeq, key, fn,
    });
    filtered.sort((a, b) => a.priority - b.priority || a.seq - b.seq);
    this._veto.set(hook, filtered);
  }

  /**
   * Run veto listeners for `hook` in priority order. Unlike
   * `emit`/`emitAsync`, exceptions are NOT swallowed — the first throw
   * aborts the chain and propagates to the caller (the operation is
   * vetoed). Listeners may mutate `ctx` in place.
   */
  async emitVeto(hook: HookNameArg, ctx: PreSaveContext): Promise<void> {
    this._checkHookName(hook);
    for (const entry of this._veto.get(hook) ?? []) {
      await entry.fn(ctx);
    }
  }

  /** Check if any veto listeners are registered for `hook`. */
  hasVeto(hook: string): boolean {
    return (this._veto.get(hook)?.length ?? 0) > 0;
  }

  /** Check if any middleware, events (sync or async) or veto listeners are
   *  registered. */
  has(hook: string): boolean {
    return (
      (this._middleware.get(hook)?.length ?? 0) > 0 ||
      (this._events.get(hook)?.length ?? 0) > 0 ||
      (this._asyncEvents.get(hook)?.length ?? 0) > 0 ||
      (this._veto.get(hook)?.length ?? 0) > 0
    );
  }
}
