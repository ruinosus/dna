"""Unit tests for the InstanceBuilder collaborator (kernel-decompose-continue).

Plus a regression test for the with_tenant back-ref bug: the stateless
collaborators must rebind to the tenant copy so per-kernel state (tenant) is
read from the COPY, not the original kernel.
"""
from __future__ import annotations

from dna.kernel import Kernel
from dna.kernel.compose.instance_builder import InstanceBuilder
from dna.kernel.boot.invalidation import InvalidationController
from dna.kernel.compose.resolver import CompositionResolver


def test_kernel_wires_builder():
    k = Kernel.auto()
    assert isinstance(k._builder, InstanceBuilder)
    assert k._builder._k is k


def test_with_tenant_rebinds_stateless_collaborators_to_the_copy():
    # The bug: a shared collaborator held a back-ref to the ORIGINAL kernel, so
    # instance_async read tenant=None instead of the copy's tenant.
    k = Kernel()
    k2 = k.with_tenant("acme")
    assert k2.tenant == "acme"
    # Every stateless back-ref collaborator points at the COPY, not the original.
    for collab in (k2._builder, k2._invctl, k2._composition,
                   k2._sync, k2._layerpol, k2._bundleio):
        assert collab._k is k2, f"{type(collab).__name__} still points at original"
    # The original's collaborators still point at the original.
    assert k._builder._k is k
    assert isinstance(k2._invctl, InvalidationController)
    assert isinstance(k2._composition, CompositionResolver)


def test_with_tenant_keeps_stateful_collaborators_shared():
    # The state-HOLDING collaborators (cache / tools / kinds) stay shared across
    # tenant views — their state is global.
    k = Kernel.auto()
    k2 = k.with_tenant("acme")
    assert k2._kcache is k._kcache       # one read cache
    assert k2._toolreg is k._toolreg     # one tool registry
    assert k2._kindreg is k._kindreg     # one kind registry (same dict)


def test_builder_instance_async_reads_copy_tenant():
    # instance_async promotes the copy's tenant into layers — pin that the
    # collaborator reads the COPY's tenant (regression for the back-ref bug).
    k = Kernel()
    k2 = k.with_tenant("acme")
    # The builder bound to k2 sees tenant=acme.
    assert k2._builder._k.tenant == "acme"
    assert k._builder._k.tenant is None
