"""The trait registry — declaring participation instead of listing it.

``traits:`` on a KindDefinition plus ``kernel.kinds_with_trait(name)``. The
whole point is that a Kind joins a family by DECLARING, and every consumer sees
it without editing a list; the ratchet
(``test_kind_name_literal_ratchet.py``) is what keeps that true.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.kinds.traits import (
    known_traits,
    normalize_traits,
    port_has_trait,
    port_traits,
    register_trait,
    trait_description,
)
from dna.kernel.meta import DeclarativeKindPort
from dna.kernel.models import TypedKindDefinition

# ── the pure vocabulary ──────────────────────────────────────────────────────


def test_normalize_traits_accepts_the_yaml_shapes():
    assert normalize_traits(None) == frozenset()
    assert normalize_traits([]) == frozenset()
    assert normalize_traits(["a", "b"]) == frozenset({"a", "b"})
    assert normalize_traits(("a", " b ", "")) == frozenset({"a", "b"})
    assert normalize_traits({"a"}) == frozenset({"a"})


def test_normalize_traits_refuses_a_bare_string():
    """``traits: sdlc.work-item`` (no list) is the obvious YAML slip; refusing
    it by name beats silently making a set of 15 single characters."""
    with pytest.raises(ValueError, match=r"traits: \[sdlc\.work-item\]"):
        normalize_traits("sdlc.work-item")


def test_normalize_traits_refuses_a_non_string_member():
    with pytest.raises(ValueError, match="every trait must be a string"):
        normalize_traits(["ok", 3])


def test_register_trait_is_documentation_not_a_gate():
    register_trait("test.only", "a trait registered by this test")
    assert trait_description("test.only") == "a trait registered by this test"
    assert "test.only" in known_traits()
    # An UNREGISTERED trait is still perfectly legal on a port — the registry
    # never vetoes, which is what makes the vocabulary open.
    assert trait_description("never.registered.anywhere") is None
    assert normalize_traits(["never.registered.anywhere"]) == frozenset(
        {"never.registered.anywhere"}
    )


def test_port_traits_defaults_to_empty_for_a_port_without_the_attribute():
    class Bare:
        kind = "X"

    assert port_traits(Bare()) == frozenset()
    assert port_has_trait(Bare(), "anything") is False


# ── the descriptor field ─────────────────────────────────────────────────────


def _descriptor(**spec_extra):
    raw = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "trait-probe"},
        "spec": {
            "target_api_version": "example.com/probe/v1",
            "target_kind": "TraitProbe",
            "alias": "probe-traitprobe",
            "origin": "probe",
            "storage": {"type": "yaml", "dir": "traitprobes"},
            **spec_extra,
        },
    }
    return DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(raw))


def test_descriptor_traits_reach_the_port():
    """``port.traits`` is the CLOSURE; ``port.declared_traits`` is what was
    typed.

    This assertion used to read ``== {"sdlc.work-item", "sdlc.rollup"}`` and it
    changed on purpose: ``sdlc.rollup`` now IMPLIES ``sdlc.work-item``, which
    implies ``sdlc.dated``, so a lookup for "which Kinds are dated?" finds this
    Kind without it having to restate what its role already entails. Both facts
    stay reachable — a lookup wants the closure, a screen showing the author's
    own words wants ``declared_traits``."""
    from dna.kernel.kinds.traits import declared_traits_of

    port = _descriptor(traits=["sdlc.work-item", "sdlc.rollup"])
    assert port.traits == frozenset(
        {"sdlc.work-item", "sdlc.rollup", "sdlc.dated"}
    )
    assert declared_traits_of(port) == frozenset(
        {"sdlc.work-item", "sdlc.rollup"}
    )
    assert port_has_trait(port, "sdlc.work-item")


def test_descriptor_without_traits_declares_none():
    assert _descriptor().traits == frozenset()


def test_descriptor_traits_must_be_a_list():
    with pytest.raises(ValueError, match="spec.traits"):
        _descriptor(traits="sdlc.work-item")


# ── the kernel lookup ────────────────────────────────────────────────────────


def test_kinds_with_trait_reads_the_live_registry():
    k = Kernel.auto()
    work_items = k.kinds_with_trait("sdlc.work-item")
    # Story is the canonical work item; if THIS breaks the family is broken.
    assert "Story" in work_items
    # A trait nobody declares yields the empty set, never an error.
    assert k.kinds_with_trait("no.such.trait") == frozenset()


def test_kinds_with_trait_matches_kind_ports_with_trait():
    k = Kernel.auto()
    names = k.kinds_with_trait("sdlc.work-item")
    ports = k.kind_ports_with_trait("sdlc.work-item")
    assert {p.kind for p in ports} == names


def test_traits_of_an_unregistered_kind_is_empty():
    k = Kernel.auto()
    assert k.traits_of("NoSuchKindAnywhere") == frozenset()
    assert "sdlc.work-item" in k.traits_of("Story")
