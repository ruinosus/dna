"""Unit tests for the CompositionResolver collaborator (kernel-decompose-continue).

Verifies the kernel delegates to the collaborator and that the resolution-chain
walk + composition-rule defaults work in isolation. The full cross-scope
inheritance / merge behavior is covered by test_composition_v2_resolver.py via
the kernel delegators.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.compose.resolver import CompositionResolver


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
    # A per-scope ledger Kind does NOT inherit across scopes, but still honors
    # tenant overlay (disabled/override_full/field_level).
    #
    # i-107: this used a BARE `Kernel()` and the name "Story", which worked only
    # because query/resolver.py held a literal list of 13 Kind names. With the
    # fact moved to the Kind's own `scope_inheritable` declaration, a bare
    # kernel has no Story registered and therefore nothing to read — so the
    # test now registers a Kind that DECLARES it, which is what it meant all
    # along. `Kernel.auto()` would also work (Story really does declare it);
    # a local class keeps this a resolver test rather than an extension test.
    from dna.kernel.kinds.base import KindBase
    from dna.kernel.protocols import StorageDescriptor

    class _Ledger(KindBase):
        api_version = "collabtest.io/v1"
        kind = "Ledger"
        alias = "collabtest-ledger"
        storage = StorageDescriptor.yaml("ledgers")
        scope_inheritable = False

    k = Kernel()
    k.kind(_Ledger())
    rule = await k._composition.get_composition_rule("myscope", "Ledger")
    assert rule[0] == "disabled"
    assert rule[1:] == ("override_full", "field_level")
