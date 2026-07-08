"""AsyncSourceAdapter — wraps a sync SourcePort for async callers.

Uses asyncio.to_thread() to run blocking I/O in a thread pool,
preventing event loop blocking in FastAPI/Starlette.

Usage:
    from dna.adapters.async_adapter import AsyncSourceAdapter
    from dna.adapters.s3.source import S3Source

    sync_source = S3Source(bucket="my-manifests")   # sync SourcePort
    async_source = AsyncSourceAdapter(sync_source)

    docs = await async_source.load_all("my-scope")

Design (s-dna-source-conformance-kit): the adapter is a TRANSPARENT
proxy — it structurally mirrors whatever the wrapped source implements,
via a table-driven ``__getattr__`` that thread-hops known SourcePort /
WritableSourcePort methods and forwards everything else untouched.

This is the ONE in-repo source adapter that deliberately does NOT
subclass the ``SourcePort`` Protocol: inheriting would attach the
Protocol's no-op method stubs to the class, which would (a) shadow the
``__getattr__`` forwarding and (b) make the wrapper claim methods its
inner source doesn't have. Structural transparency is the contract —
``isinstance(AsyncSourceAdapter(s), SourcePort)`` reports the truth
about ``s``, and ``derive_capabilities`` sees the inner source's real
surface (hops carry the inner signature via ``functools.wraps``).
"""
from __future__ import annotations

import asyncio
import functools
import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dna.kernel.capabilities import SourceCapabilities


# Sync methods of the Source/WritableSource contract that must be executed
# off the event loop. Anything callable NOT in this set is forwarded as-is
# (helpers, sync capability methods like fetch_bundle_entry — the
# BundleEntryReadable protocol explicitly allows sync returns).
_THREAD_HOPPED: frozenset[str] = frozenset({
    # SourcePort
    "load_bootstrap_docs", "load_all", "resolve_ref", "load_layer",
    "close", "list_doc_refs", "load_one", "count",
    # WritableSourcePort
    "save_document", "delete_document", "save_manifest", "list_versions",
    "get_version", "publish", "load_drafts", "list_scopes",
})

# `query` is special: the port promises an AsyncIterator, so the sync
# result (an iterable / generator) is materialized in the worker thread
# and re-emitted as an async generator.
_ASYNC_ITER_HOPPED: frozenset[str] = frozenset({"query"})


class AsyncSourceAdapter:
    """Async transparent proxy around any sync SourcePort."""

    def __init__(self, source: Any) -> None:
        self._source = source

    @property
    def supports_readers(self) -> bool:
        return getattr(self._source, "supports_readers", False)

    def capabilities(self) -> "SourceCapabilities":
        """Sync, typed capabilities of the WRAPPED source.

        Passthrough when the inner source declares; otherwise falls back
        to reflection-derivation over the inner source (external sync
        sources — e.g. ``S3Source`` — predate the declaration contract).
        Both answers match the wrapper's own structural surface, since
        the proxy mirrors the inner source member-for-member.
        """
        fn = getattr(self._source, "capabilities", None)
        if callable(fn) and not inspect.iscoroutinefunction(fn):
            caps = fn()
            from dna.kernel.capabilities import SourceCapabilities
            if isinstance(caps, SourceCapabilities):
                return caps
        from dna.kernel.capabilities import derive_capabilities
        return derive_capabilities(
            self._source, label=type(self._source).__name__,
        )

    # -- Transparent forwarding ------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Mirror the wrapped source: thread-hop known sync port methods,
        forward everything else untouched. Missing members raise
        ``AttributeError`` naturally — the proxy never invents surface."""
        attr = getattr(self._source, name)
        if not callable(attr):
            return attr
        # Already-async inner methods need no hop (mixed sources).
        if inspect.iscoroutinefunction(attr) or inspect.isasyncgenfunction(attr):
            return attr

        if name in _ASYNC_ITER_HOPPED:
            @functools.wraps(attr)
            async def _aiter_hop(*args: Any, **kwargs: Any):
                rows = await asyncio.to_thread(
                    lambda: list(attr(*args, **kwargs))
                )
                for row in rows:
                    yield row
            return _aiter_hop

        if name in _THREAD_HOPPED:
            @functools.wraps(attr)
            async def _hop(*args: Any, **kwargs: Any) -> Any:
                return await asyncio.to_thread(attr, *args, **kwargs)
            return _hop

        return attr
