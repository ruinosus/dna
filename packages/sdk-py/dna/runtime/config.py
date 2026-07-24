"""Derive a copilot's runtime config from its DNA def — the machine that used
to be copy-pasted into each host copilot (memory_agent `_derive_from_def`).

The def is read from the ENV-configured source (``DNA_SOURCE_URL`` >
``DNA_BASE_DIR``), the SAME source the mcp/api faces read from — NOT a
filesystem path baked into the image. A published deployment keeps its
definitions in Postgres; reading them off disk (the old ``Kernel.quick(base_dir=)``)
crashed the copiloto whenever the on-disk scope didn't match (s-copilot-def-read-
from-source / genome-strain foundation)."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CopilotConfig:
    instructions: str
    model: str
    allowed_tools: frozenset[str]
    confirm_tools: tuple[str, ...]


def resolve_source_url(base_dir: str | None) -> str:
    """The env-driven source URL — ``DNA_SOURCE_URL`` > ``file://<base_dir>`` >
    ``file://./.dna``. Same priority the CLI boot path uses, so a published
    deploy resolves its configured source (Postgres) and dev/local resolves the
    filesystem ``base_dir``. Two paths, one contract."""
    url = os.getenv("DNA_SOURCE_URL")
    if url:
        return url
    base = base_dir or os.getenv("DNA_BASE_DIR")
    if base:
        p = Path(base).resolve()
        # mirror the classic convention: a project dir with a .dna/ child
        if (p / ".dna").is_dir():
            p = p / ".dna"
        return f"file://{p}"
    return f"file://{Path('.dna').resolve()}"


async def build_env_mi(*, base_dir: str | None, scope: str) -> Any:
    """Boot a kernel against the ENV-configured source and return ``scope``'s
    manifest instance.

    Sets ``kernel._main_loop`` to the running loop so a later
    ``build_copilot_context`` — offloaded to a worker thread — dispatches its
    sync-over-async kernel reads BACK to this loop. That is required for a SQL
    source: an asyncpg connection is bound to the loop that opened it, so the
    reads cannot run on a throwaway per-call loop.

    Must therefore be awaited on the loop that will outlive the compose (the
    server's main loop). Filesystem sources have no loop-bound handle, so the
    same code path is safe there too.
    """
    from dna.kernel import Kernel
    from dna.adapters.source_url import source_from_url

    kernel = Kernel.auto()
    source = await source_from_url(resolve_source_url(base_dir), kernel=kernel)
    kernel.source(source)
    if getattr(source, "supports_readers", False):
        # filesystem: real cache + local resolvers (scopes-root lives on disk),
        # exactly like Kernel.quick / build_auto_kernel wire it (kz-001).
        from dna.adapters.filesystem import FilesystemCache
        from dna.kernel.boot.bootstrap import wire_filesystem_resolvers

        base = str(getattr(source, "base_dir", ".dna"))
        kernel.cache(FilesystemCache(base))
        wire_filesystem_resolvers(kernel, base)
    else:
        # SQL / self-contained: a noop cache — no filesystem dependency at all.
        from dna.kernel.boot.bootstrap import _NoopCache

        kernel.cache(_NoopCache())
    kernel._main_loop = asyncio.get_running_loop()
    return await kernel.instance_async(scope)


def _derive_config(mi: Any, copilot: str) -> CopilotConfig:
    """Pure derivation from a composed instance. Sync — runs in a worker thread
    whose sync-over-async kernel reads dispatch to ``mi``'s kernel._main_loop."""
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, copilot)
    allowed = {
        t
        for s in (getattr(ctx, "mcp_servers", None) or [])
        for t in (getattr(s, "allowed_tools", None) or [])
    }
    # The Tool-doc alias `list` runs as `list_memories` (federation doc note).
    if "list" in allowed:
        allowed.add("list_memories")
    return CopilotConfig(
        instructions=ctx.instructions or "",
        model=ctx.model,
        allowed_tools=frozenset(allowed),
        confirm_tools=tuple(
            sorted(getattr(ctx, "tools_requiring_confirmation", None) or [])
        ),
    )


async def copilot_config(
    copilot: str, *, base_dir: str | None = None, scope: str
) -> CopilotConfig:
    """Derive ``copilot``'s runtime config, reading its def from the
    ENV-configured source (``resolve_source_url``). ``base_dir`` is the local
    fallback used only when ``DNA_SOURCE_URL`` is unset.

    Async (was sync ``Kernel.quick``): the SQL source must be built and read on
    a persistent loop — see ``build_env_mi``. The heavy ``build_copilot_context``
    is offloaded to a worker thread that dispatches back to that loop."""
    mi = await build_env_mi(base_dir=base_dir, scope=scope)
    return await asyncio.to_thread(_derive_config, mi, copilot)
