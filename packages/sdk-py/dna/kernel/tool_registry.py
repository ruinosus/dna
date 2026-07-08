"""ToolRegistry — the kernel's @tool definition registry, extracted from the
Kernel god-object (s-kernel-decompose-god-object / kernel-decompose-continue).

Behavior-preserving: the registry dict + the register / lookup / group-filter
logic move verbatim from ``Kernel``; the kernel keeps ``tool`` / ``get_tool`` /
``get_tools`` / ``list_tool_groups`` as thin public delegators (every call site
unchanged), plus a read-only ``_tools`` property for any code that historically
read the dict directly. Tools are global (not tenant-scoped), so one registry is
safely shared across ``with_tenant`` shallow copies.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.protocols import ToolDefinition


class ToolRegistry:
    """Name → ToolDefinition registry with group-aware filtering."""

    def __init__(self) -> None:
        self._tools: dict[str, "ToolDefinition"] = {}

    def register(self, td: "ToolDefinition") -> None:
        """Register a tool definition. Last-write-wins on same name (idempotent —
        factory-pattern tools re-register on every ``make_*_tools(holder)`` call)."""
        self._tools[td.name] = td

    def get(self, name: str) -> "ToolDefinition | None":
        """Return a tool definition by name, or None if unknown."""
        return self._tools.get(name)

    def get_many(
        self,
        *,
        group: str | None = None,
        groups: "list[str] | set[str] | None" = None,
    ) -> "list[ToolDefinition]":
        """Return registered tool definitions, optionally filtered.

        - ``group="cognitive"`` — exactly that group
        - ``groups=["cognitive", "manifest"]`` — union of groups
        - ``groups=["read"]`` — expands via the 'read' umbrella alias
        Pass nothing to get the full catalog.
        """
        if group is None and not groups:
            return list(self._tools.values())
        from dna.kernel.tools import expand_group_aliases  # noqa: PLC0415
        wanted = {group} if group else set()
        if groups:
            wanted |= set(groups)
        wanted = expand_group_aliases(wanted)
        return [td for td in self._tools.values() if td.group in wanted]

    def groups(self) -> dict[str, list[str]]:
        """Reverse-build {group: [tool_names...]} from the registry."""
        out: dict[str, set[str]] = {}
        for td in self._tools.values():
            if td.group:
                out.setdefault(td.group, set()).add(td.name)
        return {g: sorted(names) for g, names in out.items()}
