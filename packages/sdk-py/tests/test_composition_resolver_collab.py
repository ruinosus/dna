"""Unit tests for the CompositionResolver collaborator (kernel-decompose-continue).

Verifies the kernel delegates to the collaborator and that the resolution-chain
walk + composition-rule defaults work in isolation. The full cross-scope
inheritance / merge behavior is covered by test_composition_v2_resolver.py via
the kernel delegators.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.composition_resolver import CompositionResolver


def test_kernel_wires_collaborator():
    k = Kernel.auto()
    assert isinstance(k._composition, CompositionResolver)
    assert k._composition._k is k


@pytest.mark.asyncio
async def test_resolution_chain_single_scope_no_source():
    # No source registered → Genome lookup fails soft; with no tenant the chain
    # is just [(scope, None)] plus the _lib inherit-by-default fallback.
    k = Kernel()  # no source
    chain = await k._composition.compute_resolution_chain("myscope", None)
    scopes = [s for s, _ in chain]
    assert "myscope" in scopes
    assert k._INHERIT_PARENT_SCOPE in scopes  # inherit-by-default fallback


@pytest.mark.asyncio
async def test_composition_rule_default_inherits():
    # With no LayerPolicy doc, a normal Kind inherits by default
    # (enabled/override_full/field_level).
    k = Kernel()
    rule = await k._composition.get_composition_rule("myscope", "Agent")
    assert rule == ("enabled", "override_full", "field_level")


@pytest.mark.asyncio
async def test_composition_rule_non_inheritable_kind():
    # A per-scope ledger Kind (Story) does NOT inherit across scopes, but still
    # honors tenant overlay (disabled/override_full/field_level).
    k = Kernel()
    rule = await k._composition.get_composition_rule("myscope", "Story")
    assert rule[0] == "disabled"
