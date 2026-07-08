"""Unit tests for the ToolRegistry collaborator (kernel-decompose-continue).

Exercises register / get / group-filtering / groups() in isolation, plus the
kernel delegators + the back-compat ``_tools`` property.
"""
from __future__ import annotations

from dna.kernel import Kernel
from dna.kernel.protocols import ToolDefinition
from dna.kernel.tool_registry import ToolRegistry


def _td(name: str, group: str | None = None) -> ToolDefinition:
    return ToolDefinition(name=name, group=group, description=f"{name} desc")


def test_register_and_get():
    r = ToolRegistry()
    r.register(_td("a", "g1"))
    assert r.get("a") is not None
    assert r.get("a").name == "a"
    assert r.get("missing") is None


def test_register_last_write_wins():
    r = ToolRegistry()
    r.register(_td("a", "g1"))
    r.register(_td("a", "g2"))  # same name re-registers (idempotent factory)
    assert len(r._tools) == 1
    assert r.get("a").group == "g2"


def test_get_many_unfiltered_returns_all():
    r = ToolRegistry()
    r.register(_td("a", "g1"))
    r.register(_td("b", "g2"))
    assert {t.name for t in r.get_many()} == {"a", "b"}


def test_get_many_filters_by_group_and_groups():
    r = ToolRegistry()
    r.register(_td("a", "g1"))
    r.register(_td("b", "g2"))
    r.register(_td("c", "g3"))
    assert {t.name for t in r.get_many(group="g1")} == {"a"}
    assert {t.name for t in r.get_many(groups=["g1", "g2"])} == {"a", "b"}


def test_groups_reverse_map():
    r = ToolRegistry()
    r.register(_td("a", "g1"))
    r.register(_td("b", "g1"))
    r.register(_td("c", "g2"))
    r.register(_td("ungrouped", None))  # no group → excluded
    groups = r.groups()
    assert groups["g1"] == ["a", "b"]   # sorted
    assert groups["g2"] == ["c"]
    assert "ungrouped" not in {n for names in groups.values() for n in names}


def test_kernel_delegates_and_back_compat_property():
    k = Kernel()
    k.tool(_td("kt", "kg"))
    # Public API delegates to the registry.
    assert k.get_tool("kt") is not None
    assert {t.name for t in k.get_tools(group="kg")} == {"kt"}
    assert k.list_tool_groups()["kg"] == ["kt"]
    # Back-compat read accessor still exposes the dict.
    assert "kt" in k._tools
    assert k._tools is k._toolreg._tools
