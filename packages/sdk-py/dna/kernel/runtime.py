"""
Runtime — public facade over Kernel.

Provides the new vocabulary: storage() instead of source(),
manifest() instead of instance(). Subclasses Kernel for full
backwards compatibility during the transition.

1:1 parity with TypeScript kernel/runtime.ts.
"""
from __future__ import annotations
from typing import Any

from . import Kernel
from .protocols import SourcePort


class Runtime(Kernel):
    """Runtime that integrates any agent configuration standard."""

    def storage(self, s: SourcePort) -> None:
        """Register a storage backend. Alias for source()."""
        self.source(s)

    def manifest(self, scope: str, layers: dict[str, str] | None = None):
        """Load a manifest for a scope. Alias for instance()."""
        return self.instance(scope, layers)

    async def manifest_async(
        self, scope: str, layers: dict[str, str] | None = None,
    ):
        """Async variant of `manifest()`. Use from inside an event loop
        to avoid the asyncio.run-in-thread fallback that orphans pool-
        based source adapters (asyncpg).
        """
        return await self.instance_async(scope, layers)
