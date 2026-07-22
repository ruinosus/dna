"""Derive a copilot's runtime config from its DNA def — the machine that used
to be copy-pasted into each host copilot (memory_agent `_derive_from_def`)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CopilotConfig:
    instructions: str
    model: str
    allowed_tools: frozenset[str]
    confirm_tools: tuple[str, ...]


def copilot_config(copilot: str, *, base_dir: str, scope: str) -> CopilotConfig:
    from dna.kernel import Kernel
    from dna.emit import build_copilot_context

    mi = Kernel.quick(scope, base_dir=base_dir)
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
