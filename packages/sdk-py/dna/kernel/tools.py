"""@dna_tool decorator + pending registry (SDK surface).

DNA LAYER ON TOP OF LANGCHAIN — never replaces langchain.
============================================================

This module provides:

1. ``@dna_tool(group="...")`` — a decorator that wraps langchain's
   ``@tool`` (preserving the StructuredTool that langgraph/deepagents
   consume) AND emits an DNA ``ToolDefinition`` for kernel registration.

2. ``_PENDING_TOOLS`` — module-level registry populated at decorator
   call time. Used by Extension authors (or runtime bootstrap) to
   register tools into the kernel via ``kernel.tool(td)``.

3. Helpers (``get_pending_tools``, ``clear_pending_tools``,
   ``expand_group_aliases``).

The kernel's ``ToolPort`` is declared in ``kernel/protocols.py``;
``Kernel.tool()`` / ``Kernel.get_tools()`` are declared in
``kernel/__init__.py`` (analogous to ``.kind()`` / ``.list_kinds()``).

Story: s-dna-tool-decorator-port (2026-05-24).
"""
from __future__ import annotations

import logging

import inspect
from typing import Any, Callable, Optional

from dna.kernel.protocols import ToolDefinition


# ─── Module-level pending registry ──────────────────────────────────
# Populated when ``@dna_tool(...)`` runs at function definition time.
# Factory-pattern tools (defined inside ``make_cognitive_tools(holder)``)
# only populate this when the factory is CALLED — runtime bootstrap
# must invoke factories once with a stub holder to harvest metadata.

_PENDING_TOOLS: dict[str, ToolDefinition] = {}


def get_pending_tools() -> dict[str, ToolDefinition]:
    """Snapshot of definitions seen so far. Mutating the dict is OK
    (returned copy)."""
    return dict(_PENDING_TOOLS)


def clear_pending_tools() -> None:
    """Reset the pending registry. Useful in tests."""
    _PENDING_TOOLS.clear()


# ─── 'read' umbrella group ──────────────────────────────────────────
# 'read' is not a real group on any tool — it's an alias that expands
# to {code, manifest, docs, eval} at filter time. Kept here
# so consumers of Kernel.get_tools(groups=...) can pass `read` and have
# it work.

READ_UMBRELLA_GROUPS = frozenset({"code", "manifest", "docs", "eval"})


def expand_group_aliases(groups: list[str] | set[str] | None) -> set[str]:
    """Expand 'read' umbrella into its constituent groups. Other group
    names pass through unchanged."""
    if not groups:
        return set()
    out: set[str] = set()
    for g in groups:
        if g == "read":
            out.update(READ_UMBRELLA_GROUPS)
        else:
            out.add(g)
    return out


# ─── Decorator ───────────────────────────────────────────────────────


def dna_tool(
    group: Optional[str] = None,
    *,
    hitl: bool = False,
    scope: Optional[str] = None,
    name: Optional[str] = None,
) -> Callable:
    """Declare a function as an DNA agent tool.

    This is a thin layer ON TOP of langchain's ``@tool``: the returned
    object is a langchain ``StructuredTool`` (so deepagents/langgraph
    receive exactly what they expect), with an DNA ``ToolDefinition``
    side-channeled into the module-level pending registry.

    Args:
        group: tool group name (cognitive | manifest | code | docs | web |
            write | eval | eval_lab). UAs declare
            ``tool_groups: [<group>]`` in spec to enable groups of tools.
            ``None`` = tool exists but isn't filterable (rare).
        hitl: write tool that needs HumanInTheLoop interrupt at the
            root graph (current default: applied automatically for
            ``write`` group).
        scope: layer policy hint — ``"tenant"`` respects tenant overlay,
            ``"global"`` doesn't. Reserved for future use.
        name: override the tool name (defaults to ``func.__name__``).

    Usage:
        @dna_tool(group="cognitive")
        async def create_dream(spec_json: str) -> str:
            '''Create a SynthesisRun — ONEIRIC artefact.

            Args:
                spec_json: JSON. Required: affect, symbol, scenario,
                    fragments.
            '''
            ...

    The decorated callable behaves identically to ``@tool``-decorated:
    it's a ``StructuredTool`` instance with ``.name``, ``.description``,
    ``.args_schema``, etc. langgraph's tool_node consumes it as-is.
    """
    def decorator(func: Callable) -> Any:
        # ── Capture metadata BEFORE langchain wraps (it mutates) ────
        func_name = name or func.__name__
        docstring = inspect.getdoc(func) or ""
        source_module = func.__module__ or ""

        summary = ""
        if docstring:
            chunks: list[str] = []
            for line in docstring.splitlines():
                stripped = line.strip()
                if not stripped:
                    break
                if stripped.startswith(("Args:", "WHEN TO USE:")):
                    break
                chunks.append(stripped)
            summary = " ".join(chunks)

        # ── Apply langchain @tool wrapper ────────────────────────────
        # Lazy import so this module is usable in environments without
        # langchain (tests, schema-only introspection).
        try:
            from langchain_core.tools import tool as _lc_tool  # noqa: PLC0415
        except ImportError as exc:
            # langchain-core is an OPTIONAL extra ('tools'): only the
            # decorator needs it — the kernel itself never imports it.
            raise ImportError(
                "dna_tool requires the optional 'tools' extra: "
                "pip install 'dna-sdk[tools]'"
            ) from exc
        else:
            if name is not None:
                wrapped = _lc_tool(name)(func)
            else:
                wrapped = _lc_tool(func)

            # Tag the StructuredTool so ``make_manifest_tools`` filter
            # path can stay attribute-based (no registry lookup needed
            # in the hot path).
            try:
                wrapped._dna_group = group  # type: ignore[attr-defined]
                wrapped._dna_hitl = hitl  # type: ignore[attr-defined]
                wrapped._dna_scope = scope  # type: ignore[attr-defined]
            except (AttributeError, TypeError):
                pass

        # ── Extract args_schema (best-effort) ───────────────────────
        args_schema: dict[str, Any] = {}
        try:
            schema_cls = getattr(wrapped, "args_schema", None)
            if schema_cls is not None:
                if hasattr(schema_cls, "model_json_schema"):
                    args_schema = schema_cls.model_json_schema()
                elif hasattr(schema_cls, "schema"):
                    args_schema = schema_cls.schema()
        except Exception as e:  # noqa: BLE001
            # fail-soft: args_schema is best-effort tool metadata — the tool
            # still registers, but pickers lose arg hints, so log the miss.
            logging.getLogger(__name__).debug(
                "tool %s: args_schema extraction failed: %s", func_name, e,
            )

        # ── Side-channel: ToolDefinition into pending registry ──────
        # last-write-wins on same name (idempotent for factory re-calls).
        td = ToolDefinition(
            name=func_name,
            group=group,
            description=docstring,
            summary=summary,
            args_schema=args_schema,
            hitl=hitl,
            scope=scope,
            source=source_module.rsplit(".", 1)[-1] if source_module else "",
            _callable=wrapped,
        )
        _PENDING_TOOLS[func_name] = td

        return wrapped

    return decorator


__all__ = [
    "dna_tool",
    "clear_pending_tools",
    "expand_group_aliases",
    "get_pending_tools",
    "READ_UMBRELLA_GROUPS",
]
