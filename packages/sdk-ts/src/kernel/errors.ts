/**
 * Boot-time registration errors raised by Kernel.
 *
 * 1:1 parity with python/dna/kernel/errors.py.
 *
 * H1 — Boot-time validation. The Kernel's `kind/reader/writer/load`
 * registration methods used to be `this._x.push(y)` no-ops with zero
 * validation. Result: a typo in `detect()` made the Reader silently
 * ignored; two bundle Readers using the same marker file collided
 * (first-registered wins, depending on entry-point alphabetical order);
 * duplicate `(apiVersion, kind)` registrations silently overwrote.
 *
 * These errors surface those problems at boot time instead of as silent
 * runtime drift.
 */

/**
 * `buildPrompt({ agent: X })` was asked for an agent that no prompt-target
 * document in the loaded manifest declares (missing, renamed, or unparseable).
 *
 * Fail-loud contract (s-dx-build-prompt-fail-loud): the builder used to RETURN
 * the string `"Agent 'X' not found"` instead of throwing — which sailed
 * straight through a consumer's `if (!text)` check and became the LITERAL
 * agent instruction. Every consumer therefore wrote the same defensive guard
 * (`mi.findAgent(x) === null`) before every call. Throwing a typed error
 * deletes that guard: the miss is now impossible to ignore.
 *
 * 1:1 parity with python `dna.AgentNotFound` (a `LookupError` subclass).
 * Exported publicly from the package root.
 */
export class AgentNotFound extends Error {
  readonly agent: string | null;
  constructor(agent: string | null) {
    super(`Agent '${agent}' not found`);
    this.name = "AgentNotFound";
    this.agent = agent;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * `loadTools(scope).get(name)` was asked for a Tool that no `Tool` document in
 * the scope declares (missing, renamed, or in another scope).
 *
 * Fail-loud contract (s-load-tools-helper), the twin of `AgentNotFound`: the
 * agent-facing tool surface is data, so a miss must throw a typed error —
 * never return an empty surface that would silently reach a model as a tool
 * with no description.
 *
 * 1:1 parity with python `dna.ToolNotFound` (a `LookupError` subclass).
 * Exported publicly from the package root.
 */
export class ToolNotFound extends Error {
  readonly toolName: string | null;
  readonly scope: string | null;
  readonly available: string[];
  constructor(name: string | null, scope: string | null = null, available: string[] = []) {
    const where = scope ? ` in scope '${scope}'` : "";
    const hint = available.length ? ` — available: ${available.join(", ")}` : "";
    super(`Tool '${name}' not found${where}${hint}`);
    this.name = "ToolNotFound";
    this.toolName = name;
    this.scope = scope;
    this.available = available;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * `buildPrompt` hit an Agent whose `layout:` names a preset the Kind does not
 * offer (s-dx-named-layouts).
 *
 * Fail-loud DX: a typo'd layout (`persona_first` for `persona-first`) must not
 * silently fall through to the Kind default and compose in the wrong order —
 * it throws with the valid names listed.
 *
 * 1:1 parity with python `dna.UnknownLayout` (a `ValueError` subclass).
 * Exported publicly from the package root.
 */
export class UnknownLayout extends Error {
  readonly layout: string;
  readonly available: string[];
  readonly agent: string | null;
  constructor(layout: string, available: string[] = [], agent: string | null = null) {
    const where = agent ? ` on agent '${agent}'` : "";
    const hint = available.length ? ` — available: ${available.join(", ")}` : "";
    super(`Unknown layout '${layout}'${where}${hint}`);
    this.name = "UnknownLayout";
    this.layout = layout;
    this.available = available;
    this.agent = agent;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Base class for kernel registration validation failures. */
export class KernelRegistrationError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "KernelRegistrationError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * A KindPort failed Protocol conformance, uniqueness, or marker
 * collision checks at `kernel.kind(port)` time.
 *
 * Examples:
 *   - Duplicate `(apiVersion, kind)` tuple
 *   - Duplicate `alias` across registered Kinds
 *   - Two BUNDLE-pattern Kinds declaring the same
 *     `(storage.container, storage.marker)` pair
 *   - Object passed doesn't satisfy the `KindPort` interface
 */
export class KindRegistrationError extends KernelRegistrationError {
  constructor(message?: string) {
    super(message);
    this.name = "KindRegistrationError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * A ReaderPort failed structural conformance or owner-binding checks
 * at `kernel.reader(r)` time.
 *
 * Examples:
 *   - Object missing `detect` or `read` methods
 *   - Reader claims a `(container, marker)` pair already owned by
 *     another reader
 */
export class ReaderRegistrationError extends KernelRegistrationError {
  constructor(message?: string) {
    super(message);
    this.name = "ReaderRegistrationError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * A WriterPort failed structural conformance checks at
 * `kernel.writer(w)` time. Object missing `canWrite` or `write` is
 * the typical case.
 */
export class WriterRegistrationError extends KernelRegistrationError {
  constructor(message?: string) {
    super(message);
    this.name = "WriterRegistrationError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * An Extension failed structural checks at `kernel.load(ext)` time.
 * Object missing `register` callable, or its `register` raised an
 * unexpected exception that wasn't routed through the
 * `extension_error` hook.
 */
export class ExtensionLoadError extends KernelRegistrationError {
  constructor(message?: string) {
    super(message);
    this.name = "ExtensionLoadError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
