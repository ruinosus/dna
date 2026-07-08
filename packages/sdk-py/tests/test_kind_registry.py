"""Unit tests for the KindRegistry collaborator (kernel-decompose-continue).

Exercises the lookup surface (port_for / all_ports / alias_for / storage_for /
container_for / by_container / describe) in isolation, plus the kernel's
_kinds property-proxy + delegators over a real Kernel.auto().
"""
from __future__ import annotations

from types import SimpleNamespace

from dna.kernel import Kernel
from dna.kernel.kind_registry import KindRegistry


def _kp(kind, alias, container, api="x/v1"):
    storage = SimpleNamespace(container=container)
    return SimpleNamespace(kind=kind, alias=alias, api_version=api, storage=storage)


def _reg(*ports):
    r = KindRegistry()
    for p in ports:
        r._kinds[(p.api_version, p.kind)] = p
    return r


def test_port_for_and_all_ports():
    a, b = _kp("Skill", "x-skill", "skills"), _kp("Soul", "x-soul", "souls")
    r = _reg(a, b)
    assert r.port_for("Skill") is a
    assert r.port_for("Missing") is None
    assert set(p.kind for p in r.all_ports()) == {"Skill", "Soul"}


def test_alias_for_falls_back_to_lowercase():
    r = _reg(_kp("Skill", "x-skill", "skills"))
    assert r.alias_for("Skill") == "x-skill"
    assert r.alias_for("Unregistered") == "unregistered"  # fallback


def test_storage_and_container_for():
    r = _reg(_kp("Skill", "x-skill", "skills"))
    assert r.container_for("Skill") == "skills"
    assert r.storage_for("Skill").container == "skills"
    assert r.container_for("Missing") is None
    assert r.storage_for("Missing") is None


def test_by_container():
    r = _reg(_kp("Skill", "x-skill", "skills"), _kp("Soul", "x-soul", "souls"))
    assert r.by_container("souls") == "Soul"
    assert r.by_container("") is None        # ROOT kinds don't route by path
    assert r.by_container("nope") is None


def test_describe_shape():
    r = _reg(_kp("Skill", "x-skill", "skills"))
    d = r.describe("Skill")
    assert d["kind"] == "Skill"
    assert d["alias"] == "x-skill"
    assert d["api_version"] == "x/v1"
    assert r.describe("Missing") is None


def test_kernel_proxy_and_delegators():
    k = Kernel.auto()
    # The _kinds property IS the registry dict (one shared map).
    assert k._kinds is k._kindreg._kinds
    # Delegators agree with the collaborator.
    assert k.storage_for_kind("Agent") is k._kindreg.storage_for("Agent")
    assert k._alias_for("Agent") == k._kindreg.alias_for("Agent")
    assert {p.kind for p in k.kind_ports()} == {p.kind for p in k._kindreg.all_ports()}
