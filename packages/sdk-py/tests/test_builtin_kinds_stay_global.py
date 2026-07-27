"""i-081 — scoping store-loaded Kinds must not scope the ones shipped in code.

Only a Kind loaded from a STORE is bound to a scope. Extension classes and
builtin ``*.kind.yaml`` descriptors are registered at boot, apply everywhere,
and must resolve IDENTICALLY however the lookup is made — unscoped, or from any
scope, by bare name or pinned to an apiVersion.

This is the regression net for the whole catalogue rather than a sample: it
enumerates every Kind a fully-booted kernel registers and checks each one, so
adding a Kind adds it here for free.
"""
from __future__ import annotations

import logging

import pytest

from dna.kernel import Kernel
from dna.kernel.kinds.registry import port_scopes

# Two scopes that exist nowhere — the point is that a GLOBAL Kind does not care.
_SCOPES = ("scope-alpha", "scope-beta")


@pytest.fixture(scope="module")
def booted() -> Kernel:
    return Kernel.auto()


def test_every_registered_kind_is_global(booted: Kernel):
    """Nothing a boot registers is scope-bound — the binding is exclusively for
    Kinds that arrive from a store."""
    scoped = {
        p.kind: sorted(port_scopes(p) or ())
        for p in booted.kind_ports()
        if port_scopes(p) is not None
    }
    assert scoped == {}


def test_the_catalogue_is_not_accidentally_empty(booted: Kernel):
    """A guard on the guards: every assertion below is a for-loop, and a loop
    over nothing passes."""
    assert len(booted.kind_ports()) >= 76


def test_every_kind_resolves_pinned_from_every_scope(booted: Kernel):
    for port in booted.kind_ports():
        unscoped = booted.kind_port_for(port.kind, api_version=port.api_version)
        assert unscoped is port, port.kind
        for scope in _SCOPES:
            assert booted.kind_port_for(
                port.kind, api_version=port.api_version, scope=scope,
            ) is port, (port.kind, scope)


def test_every_kind_resolves_by_bare_name_from_every_scope(booted: Kernel, caplog):
    with caplog.at_level(logging.WARNING):
        for port in booted.kind_ports():
            unscoped = booted.kind_port_for(port.kind)
            assert unscoped is not None, port.kind
            for scope in _SCOPES:
                assert booted.kind_port_for(port.kind, scope=scope) is unscoped, (
                    port.kind, scope,
                )


def test_alias_and_storage_resolution_are_scope_independent(booted: Kernel):
    for port in booted.kind_ports():
        alias = booted._alias_for(port.kind)
        sd = booted.storage_for_kind(port.kind, api_version=port.api_version)
        container = booted.container_for_kind(
            port.kind, api_version=port.api_version,
        )
        for scope in _SCOPES:
            assert booted._kindreg.alias_for(port.kind, scope=scope) == alias
            assert booted.storage_for_kind(
                port.kind, api_version=port.api_version, scope=scope,
            ) is sd
            assert booted.container_for_kind(
                port.kind, api_version=port.api_version, scope=scope,
            ) == container


def test_container_lookup_is_scope_independent(booted: Kernel):
    containers = {
        c for p in booted.kind_ports()
        if (c := getattr(getattr(p, "storage", None), "container", None))
    }
    assert containers  # the loop below must have something to chew on
    for container in containers:
        unscoped = booted.kind_by_container(container)
        for scope in _SCOPES:
            assert booted.kind_by_container(container, scope=scope) == unscoped, (
                container, scope,
            )


def test_dep_filter_targets_still_resolve_from_every_scope(booted: Kernel):
    """The alias wire format — dep_filters, Mustache sections, LayerPolicy keys
    — is what a scoped registry could silently break."""
    aliases = [a for p in booted.kind_ports() if (a := getattr(p, "alias", None))]
    assert len(aliases) >= 76
    for alias in aliases:
        unscoped = booted.resolve_dep_filter_target(alias)
        assert unscoped is not None, alias
        for scope in _SCOPES:
            assert booted.resolve_dep_filter_target(alias, scope=scope) is unscoped


def test_the_plane_of_every_kind_is_scope_independent(booted: Kernel):
    for port in booted.kind_ports():
        plane = booted.kind_plane(port.kind, api_version=port.api_version)
        for scope in _SCOPES:
            assert booted.kind_plane(
                port.kind, api_version=port.api_version, scope=scope,
            ) == plane
