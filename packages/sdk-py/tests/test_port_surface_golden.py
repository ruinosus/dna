"""s-dna-port-surface-parity — the port-surface golden lock.

The ports ARE the extension contract: every source adapter, cache, resolver,
reader/writer, Kind, tool and embedding provider — in-tree or third-party — is
written against these ``typing.Protocol`` classes. Adding or removing a member
is therefore a public API event, and this suite makes it one.

The golden ``tests/golden-fixtures/port-surface.json`` (repo root) lists the
expected members per port. This suite introspects the REAL Protocol classes
(and dataclass/module surfaces) and compares — so:

  - a member added to a Protocol without a fixture entry → red
    ("undeclared drift");
  - a member removed from a Protocol while still listed → red
    ("fixture lies").

History: this was a Py↔TS parity harness, each member carrying a
{py, ts} pair. The TypeScript SDK was frozen (tag ``sdk-ts-final``) and the
``ts`` half was dropped; the Python surface lock — the part that catches real
regressions — stays.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import pathlib
import typing
from typing import Any, Callable

import pytest

from dna.kernel import capabilities as caps_mod
from dna.kernel import protocols as P

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "tests" / "golden-fixtures" / "port-surface.json"
)


def _protocol_members(cls: type) -> set[str]:
    """Members of a ``typing.Protocol`` — the same set ``runtime_checkable``
    isinstance checks. 3.13+: ``typing.get_protocol_members``; 3.12:
    ``__protocol_attrs__``; older: the private ``_get_protocol_attrs``."""
    get = getattr(typing, "get_protocol_members", None)
    if get is not None:
        return set(get(cls))
    attrs = getattr(cls, "__protocol_attrs__", None)
    if attrs is not None:
        return set(attrs)
    return set(typing._get_protocol_attrs(cls))  # type: ignore[attr-defined]


def _capability_protocol_names() -> set[str]:
    """Protocol classes EXPORTED by kernel.capabilities (the optional
    source-adapter capability vocabulary)."""
    from typing import Protocol

    return {
        name
        for name, val in vars(caps_mod).items()
        if inspect.isclass(val)
        and val is not Protocol
        and getattr(val, "_is_protocol", False)
        and val.__module__ == caps_mod.__name__
    }


# Port name → callable returning the REAL introspected Python surface.
_INTROSPECTORS: dict[str, Callable[[], set[str]]] = {
    "SourcePort": lambda: _protocol_members(P.SourcePort),
    # OWN members only — the inherited SourcePort half is tracked above.
    "WritableSourcePort": lambda: (
        _protocol_members(P.WritableSourcePort) - _protocol_members(P.SourcePort)
    ),
    "CachePort": lambda: _protocol_members(P.CachePort),
    "ResolverPort": lambda: _protocol_members(P.ResolverPort),
    "ReaderPort": lambda: _protocol_members(P.ReaderPort),
    "WriterPort": lambda: _protocol_members(P.WriterPort),
    "KindPort": lambda: _protocol_members(P.KindPort),
    # The optional presentation slice (s-dna-kindport-descriptor-schema):
    # a typing-only capability Protocol — NOT runtime_checkable, NOT part
    # of KindPort (the H1 isinstance gate must never require it). TS folds
    # the same members into KindPort via `extends KindPresentation`.
    "KindPresentation": lambda: _protocol_members(P.KindPresentation),
    "ToolPort": lambda: _protocol_members(P.ToolPort),
    "ExtensionHost": lambda: _protocol_members(P.ExtensionHost),
    "Extension": lambda: _protocol_members(P.Extension),
    "TemplateProvider": lambda: _protocol_members(P.TemplateProvider),
    "RecordSearchProvider": lambda: _protocol_members(P.RecordSearchProvider),
    "EmbeddingPort": lambda: _protocol_members(P.EmbeddingPort),
    "SourceCapabilities": lambda: {
        f.name for f in dataclasses.fields(caps_mod.SourceCapabilities)
    },
    "CapabilityProtocols": _capability_protocol_names,
}


def _load_fixture() -> dict[str, Any]:
    assert _FIXTURE.exists(), f"golden fixture missing: {_FIXTURE}"
    return json.loads(_FIXTURE.read_text())


def _py_members(port: dict[str, Any]) -> set[str]:
    return {m["py"] for m in port["members"]}


def diff_surface(actual: set[str], fixture_py: set[str]) -> dict[str, list[str]]:
    """Pure comparator (meta-tested below): actual Py surface vs fixture."""
    return {
        # On the Protocol but NOT in the fixture → undocumented new member.
        "undeclared": sorted(actual - fixture_py),
        # In the fixture but NOT on the Protocol → member removed (or the
        # fixture lies about the Py surface).
        "missing": sorted(fixture_py - actual),
    }


def test_fixture_exists_and_covers_every_introspected_port():
    fixture = _load_fixture()
    untracked = sorted(set(_INTROSPECTORS) - set(fixture["ports"]))
    assert not untracked, f"introspected port(s) missing from fixture: {untracked}"
    unknown = sorted(set(fixture["ports"]) - set(_INTROSPECTORS))
    assert not unknown, (
        f"fixture tracks port(s) this test can't introspect — add an "
        f"introspector: {unknown}"
    )


@pytest.mark.parametrize("port_name", sorted(_INTROSPECTORS))
def test_python_surface_matches_fixture(port_name: str):
    fixture = _load_fixture()
    actual = _INTROSPECTORS[port_name]()
    expected = _py_members(fixture["ports"][port_name])
    diff = diff_surface(actual, expected)
    assert not diff["undeclared"], (
        f"Py {port_name} member(s) not tracked in port-surface.json — "
        f"declare them (a port member is public API): {diff['undeclared']}"
    )
    assert not diff["missing"], (
        f"fixture lists Py {port_name} member(s) the Protocol no longer has — "
        f"a removal is a breaking change; land it in the fixture too: "
        f"{diff['missing']}"
    )


def test_excluded_surfaces_are_justified_not_silent():
    fixture = _load_fixture()
    excluded = fixture["excluded_surfaces"]
    # The known internal/glue surface stays documented.
    assert "collaborator-ports" in excluded
    for key, entry in excluded.items():
        assert (entry.get("justification") or "").strip(), (
            f"excluded surface {key!r} has no justification"
        )


# ── test-of-the-test (gate 5): removing a member from the fixture MUST
# turn the comparison red — the lock can't silently erode.

def test_meta_dropping_a_fixture_member_is_detected():
    fixture = _load_fixture()
    expected = _py_members(fixture["ports"]["SourcePort"])
    expected.discard("close")
    diff = diff_surface(_INTROSPECTORS["SourcePort"](), expected)
    assert diff["undeclared"] == ["close"]


def test_meta_a_fixture_member_missing_from_the_protocol_is_detected():
    fixture = _load_fixture()
    expected = _py_members(fixture["ports"]["SourcePort"]) | {"phantom_member"}
    diff = diff_surface(_INTROSPECTORS["SourcePort"](), expected)
    assert diff["missing"] == ["phantom_member"]
