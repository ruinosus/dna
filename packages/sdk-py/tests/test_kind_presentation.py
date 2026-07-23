"""s-dna-kindport-descriptor-schema — KindPresentation capability Protocol.

The ~9 optional presentation attrs/methods that lived only in the KindPort
docstring + hasattr duck-typing now have a typed home: the
``KindPresentation`` Protocol (typing-only). The load-bearing invariant this
suite locks is the one that bit us with ``is_runtime_artifact``
(test_port_contract.py): ``runtime_checkable`` isinstance checks member
PRESENCE, so the optional members must NEVER migrate onto the
runtime_checkable ``KindPort`` — a minimal Kind with only the core contract
must stay registrable through the H1 gate.
"""
from __future__ import annotations

import typing

import pytest

from dna.kernel import protocols as P
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import (
    KindPort,
    KindPresentation,
    StorageDescriptor,
)

# The presentation surface — must stay OFF the runtime_checkable KindPort.
_PRESENTATION_MEMBERS = {
    "docs",
    "description_fallback_field",
    "ui_schema",
    "graph_style",
    "ascii_icon",
    "display_label",
    "visible_in_backend",
    "preview",
    "graph_meta",
}


def _protocol_members(cls: type) -> set[str]:
    get = getattr(typing, "get_protocol_members", None)
    if get is not None:
        return set(get(cls))
    return set(cls.__protocol_attrs__)  # type: ignore[attr-defined]


class _MinimalKind:
    """A Kind providing ONLY the core KindPort contract — no KindBase, no
    presentation members. This is exactly what a third-party extension may
    ship; the H1 gate must accept it."""

    api_version = "minimal.example/v1"
    kind = "MinimalPresentationTest"
    alias = "minimal-presentation-test"
    model = dict
    origin = "tests/test_kind_presentation.py::_MinimalKind"
    storage = StorageDescriptor.yaml("minimal-presentation-tests")
    is_root = False
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    is_runtime_artifact = False

    def dep_filters(self): return None
    def dependencies(self): return None
    def schema(self): return None
    def get_default_agent_name(self, doc): return None
    def get_layer_policies(self, doc): return None
    def parse(self, raw): return raw
    def describe(self, doc): return None
    def summary(self, doc): return None
    def prompt_template(self): return None


def test_minimal_kind_satisfies_kindport_isinstance():
    assert isinstance(_MinimalKind(), KindPort)


def test_minimal_kind_registers_through_the_h1_gate():
    """End-to-end proof: kernel.kind() (H1 registration funnel) accepts a
    Kind with zero presentation members."""
    from dna.kernel import Kernel

    k = Kernel.auto()
    k.kind(_MinimalKind())
    assert ("minimal.example/v1", "MinimalPresentationTest") in k._kinds


def test_presentation_members_stay_off_the_runtime_checkable_kindport():
    """THE ratchet: none of the optional presentation members may appear in
    KindPort.__protocol_attrs__ — the set isinstance checks. Adding one
    breaks every third-party Kind that doesn't declare it (the
    is_runtime_artifact precedent)."""
    overlap = _protocol_members(KindPort) & _PRESENTATION_MEMBERS
    assert not overlap, (
        f"presentation member(s) leaked onto the runtime_checkable KindPort "
        f"Protocol: {sorted(overlap)} — they belong on KindPresentation "
        f"(typing-only), NEVER on KindPort (isinstance would start requiring "
        f"them on minimal third-party Kinds)."
    )


def test_kind_presentation_declares_the_full_optional_surface():
    assert _protocol_members(KindPresentation) == _PRESENTATION_MEMBERS


def test_kind_presentation_is_not_runtime_checkable():
    """Typing-only by design — an isinstance check against it must raise,
    never silently gate on presence."""
    with pytest.raises(TypeError):
        isinstance(object(), KindPresentation)  # noqa: B015


def test_kind_presentation_is_exported():
    assert "KindPresentation" in P.__all__


def test_kindbase_defaults_cover_the_attribute_members():
    """KindBase carries a None default for every ATTRIBUTE member of the
    presentation surface, so subclasses opt in field-by-field. The two
    METHOD members (preview/graph_meta) deliberately have NO default —
    absence is meaningful (consumers fall back to the generic renderer)."""
    for attr in _PRESENTATION_MEMBERS - {"preview", "graph_meta"}:
        assert hasattr(KindBase, attr), f"KindBase missing default for {attr}"
        assert getattr(KindBase, attr) is None
    assert not hasattr(KindBase, "preview")
    assert not hasattr(KindBase, "graph_meta")
