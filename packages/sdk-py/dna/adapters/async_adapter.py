"""AsyncSourceAdapter — wraps a sync SourcePort for async callers.

Uses asyncio.to_thread() (Python 3.9+) to run blocking I/O
in a thread pool, preventing event loop blocking in FastAPI/Starlette.

Usage:
    from dna.adapters.async_adapter import AsyncSourceAdapter

    sync_source = FilesystemSource(".dna")
    async_source = AsyncSourceAdapter(sync_source)

    docs = await async_source.load_all("my-module")
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dna.kernel.capabilities import SourceCapabilities


class AsyncSourceAdapter:
    """Async wrapper around any sync SourcePort."""

    def __init__(self, source: Any) -> None:
        self._source = source

    @property
    def supports_readers(self) -> bool:
        return getattr(self._source, "supports_readers", False)

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._source.load_bootstrap_docs, scope, tenant=tenant
        )

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._source.load_all, scope, readers)

    async def resolve_ref(self, scope: str, ref: str) -> str:
        return await asyncio.to_thread(self._source.resolve_ref, scope, ref)

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._source.load_layer, scope, layer_id, layer_value, readers
        )

    # -- WritableSourcePort methods (forwarded if available) --

    async def save_document(
        self, scope: str, kind: str, name: str, raw: dict,
    ) -> str:
        return await asyncio.to_thread(
            self._source.save_document, scope, kind, name, raw
        )

    async def delete_document(self, scope: str, kind: str, name: str) -> None:
        return await asyncio.to_thread(
            self._source.delete_document, scope, kind, name
        )

    async def publish(self, scope: str, kind: str, name: str) -> str:
        return await asyncio.to_thread(self._source.publish, scope, kind, name)

    async def save_manifest(self, scope: str, manifest: dict) -> str:
        return await asyncio.to_thread(
            self._source.save_manifest, scope, manifest
        )

    async def list_versions(
        self, scope: str, kind: str, name: str,
    ) -> list[dict]:
        return await asyncio.to_thread(
            self._source.list_versions, scope, kind, name
        )

    async def get_version(
        self, scope: str, kind: str, name: str, version_id: str,
    ) -> dict:
        return await asyncio.to_thread(
            self._source.get_version, scope, kind, name, version_id
        )

    async def load_drafts(self, scope: str) -> list[dict]:
        return await asyncio.to_thread(self._source.load_drafts, scope)

    async def list_scopes(self) -> list[str]:
        return await asyncio.to_thread(self._source.list_scopes)

    def capabilities(self) -> "SourceCapabilities":
        # s-capabilities-dataclass — capabilities() is uniformly sync across all
        # adapters now (a cheap isinstance-derived dataclass, no I/O), so this is
        # a plain passthrough rather than a thread hop.
        return self._source.capabilities()

    # -- Passthrough for non-async attributes --

    def __getattr__(self, name: str) -> Any:
        """Forward unknown attributes to the wrapped source."""
        return getattr(self._source, name)
