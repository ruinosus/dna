"""Boot-time registration errors raised by Kernel.

H1 — Boot-time validation. The Kernel's `kind/reader/writer/load`
registration methods used to be `self._x.append(y)` no-ops with zero
validation. Result: a typo in `detect()` made the Reader silently
ignored; two bundle Readers using the same marker file collided
(first-registered wins, depending on entry-point alphabetical order);
duplicate `(api_version, kind)` registrations silently overwrote.

These errors surface those problems at boot time instead of as silent
runtime drift. They subclass ``ValueError`` so existing code that
broadly catches ``ValueError`` still works.
"""
from __future__ import annotations


class KernelRegistrationError(ValueError):
    """Base class for kernel registration validation failures."""


class KindRegistrationError(KernelRegistrationError):
    """A KindPort failed Protocol conformance, uniqueness, or marker
    collision checks at ``kernel.kind(port)`` time.

    Examples:
      - Duplicate ``(api_version, kind)`` tuple
      - Duplicate ``alias`` across registered Kinds
      - Two BUNDLE-pattern Kinds declaring the same
        ``(storage.container, storage.marker)`` pair
      - Object passed doesn't satisfy the ``KindPort`` Protocol
    """


class ReaderRegistrationError(KernelRegistrationError):
    """A ReaderPort failed Protocol conformance or owner-binding checks
    at ``kernel.reader(r)`` time.

    Examples:
      - Object missing ``detect`` or ``read`` methods
      - Reader claims a ``(container, marker)`` pair already owned by
        another reader (only enforced for BUNDLE-pattern Kinds)
    """


class WriterRegistrationError(KernelRegistrationError):
    """A WriterPort failed Protocol conformance checks at
    ``kernel.writer(w)`` time. Object missing ``can_write`` or
    ``write`` methods is the typical case."""


class ExtensionLoadError(KernelRegistrationError):
    """An Extension failed structural checks at ``kernel.load(ext)``
    time. Object missing ``register`` callable, or its ``register``
    raised an unexpected exception that wasn't routed through the
    ``extension_error`` hook."""
