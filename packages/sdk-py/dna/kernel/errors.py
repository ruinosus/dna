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


class AgentNotFound(LookupError):
    """``build_prompt(agent=X)`` was asked for an agent that no prompt-target
    document in the loaded manifest declares (missing, renamed, or unparseable).

    Fail-loud contract (s-dx-build-prompt-fail-loud): the builder used to
    RETURN the string ``"Agent 'X' not found"`` instead of raising — which
    sailed straight through a consumer's ``if not text`` check and became the
    LITERAL agent instruction. Every consumer therefore wrote the same
    defensive guard (``mi.one("Agent", x) is None``) before every call. Raising
    a typed error deletes that guard: the miss is now impossible to ignore.

    Subclasses ``LookupError`` (not ``ValueError``) — semantically a
    lookup miss, and narrow enough that a caller can ``except AgentNotFound``
    (or the broader ``except LookupError``) without swallowing unrelated
    failures. Exported publicly from the ``dna`` package.
    """

    def __init__(self, agent: str | None) -> None:
        self.agent = agent
        super().__init__(f"Agent '{agent}' not found")


class SourceRegistrationError(KernelRegistrationError):
    """A source failed the SourcePort boot gate at ``kernel.source(src)``
    time (s-dna-source-conformance-kit).

    The gate checks that the CORE SourcePort surface exists BY NAME
    (``runtime_checkable`` semantics — names only, not behavior). A
    source that passes the gate can still misbehave; run the public
    conformance kit (``dna.testing.source_conformance_suite``)
    against your adapter to verify actual behavior. See
    docs/PORT-CONTRACT.md."""
