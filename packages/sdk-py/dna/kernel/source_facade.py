"""SourceFacade — read-only source-adapter introspection extracted from the
Kernel god-object (``s-kernel-decomp-f5-satellites``).

``source_type`` / ``list_scopes_async`` / ``source_metadata`` are the stable
public surface that replaced the harness's habit of peeking at private adapter
state (``type(kernel._source).__name__``, ``kernel._source._dsn``,
``await kernel._source.list_scopes()``). They expose only what is safe: the
adapter class name, the scope list (normalised across sync/async adapters), and
a whitelisted metadata snapshot (dsn / schema / base_dir) — private state
(pools, connections) stays inside the adapter.

Behavior-preserving extraction: the three bodies move here verbatim; the kernel
keeps ``source_type`` / ``list_scopes_async`` / ``source_metadata`` as thin
delegators (widely called across kinds-api / cognitive-api / catalog). A
STATELESS back-ref collaborator reaching the source through the host.
"""
from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import SourceFacadeHost


class SourceFacade:
    """The kernel's read-only source-introspection surface. One per kernel."""

    def __init__(self, kernel: "SourceFacadeHost") -> None:
        self._k = kernel

    @property
    def source_type(self) -> str:
        """Source adapter class name — safe for capability checks.

        Replaces ``type(kernel._source).__name__`` peeking at the
        private attribute. Returns the empty string when no source is
        wired (helps tests that build a kernel without a source).
        """
        src = self._k._source
        if src is None:
            return ""
        return type(src).__name__

    async def list_scopes_async(self) -> list[str]:
        """Proxy to ``source.list_scopes()`` — uniform across adapters.

        Replaces 7+ callsites in the harness that did
        ``await kernel._source.list_scopes()`` (private attribute
        access). FilesystemWritableSource exposes ``list_scopes``
        as sync, SQLite + Postgres expose it as async — this method
        normalises both.
        """
        src = self._k._source
        if src is None:
            return []
        result = src.list_scopes()  # type: ignore[attr-defined]
        if inspect.isawaitable(result):
            result = await result
        return list(result)

    def source_metadata(self) -> dict:
        """Read-only snapshot of source adapter metadata.

        Returns a typed dict with the same fields the harness used
        to peek at via ``getattr(kernel._source, "_dsn", None)``,
        ``_schema``, ``base_dir`` — but as a stable public API.
        Returns only what's safe to expose; private state (pools,
        connection objects) stays inside the adapter.

        Keys (all optional):
          - ``type``: source class name (also via ``source_type``)
          - ``dsn``: connection string (Postgres / SQLite) when known
          - ``schema``: SQL schema (Postgres) when known
          - ``base_dir``: filesystem root (FS) when known

        Callers that need adapter-specific data should add their
        own getter to the adapter; the kernel just surfaces the
        common ones.
        """
        src = self._k._source
        if src is None:
            return {}
        meta: dict = {"type": type(src).__name__}
        # Use stable public-ish names if the adapter exposes them.
        # Fall back to private attrs only when adapter hasn't
        # adopted the public API yet (Phase 16 follow-up Story).
        dsn = getattr(src, "dsn", None) or getattr(src, "_dsn", None)
        if dsn:
            meta["dsn"] = dsn
        schema = getattr(src, "schema", None) or getattr(src, "_schema", None)
        if schema:
            meta["schema"] = schema
        base_dir = getattr(src, "base_dir", None)
        if base_dir:
            meta["base_dir"] = str(base_dir)
        return meta
