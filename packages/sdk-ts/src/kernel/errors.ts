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
