"""``dna.application.live`` — the live DNA handle the use-cases operate over.

Per ``adr-faces-reorg`` (move #1): the transport-agnostic application layer
lives in the CORE, not buried in a face. ``LiveDna`` is the kernel-only handle
every use-case in :mod:`dna.application.runtime` takes — a thin wrapper over the
configured kernel + default scope. It has ZERO transport dependencies (no HTTP /
Click / FastMCP); a face BOOTS one (the CLI's ``boot_live`` composition root) and
hands it to the shared use-cases.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LiveDna:
    """A live handle over the configured DNA source — the kernel plus the
    default scope. Built ONCE per face (lazily, on the first call) and shared by
    every use-case. Transport-agnostic: it depends only on the kernel."""

    base_scope: str
    kernel: Any
    provider: Any  # sqlite-vec search provider, or None (lexical fallback)

    async def mi(self, scope: str | None = None, tenant: str | None = None) -> Any:
        """Build a (optionally tenant-resolved) ManifestInstance for ``scope``.

        Eager (``lazy=False``) so ``mi.documents`` is fully materialized for
        agent/tool enumeration. ``tenant`` promotes into the layer context, so
        ``build_prompt`` composes the per-tenant overlay — the axis emit drops.
        """
        layers = {"tenant": tenant} if tenant else None
        return await self.kernel.instance_async(
            scope or self.base_scope, layers, lazy=False
        )
