"""Item 16 — the alias convention, enforced where it can be.

#244 made a tenant-authored Kind safe by namespacing its ``apiVersion``, and left
``spec.alias`` author-supplied. That closes the door and leaves the window open:
an alias is UNIQUE across the whole registry, so two authors both declaring
``alias: deal`` means the second one's Kind cannot register AT ALL — and whoever
registered first owns that name in every ``dep_filters`` key, Mustache variable
and LayerPolicy instance.

**The decision, and its limits.** Enforce, for DESCRIPTORS only, and rename
nothing:

* descriptors are the tenant-authorable path and the one that arrives at
  runtime; a class Kind ships in the distribution and is reviewed;
* the alias is a LIVE wire format, so the six builtin descriptors that predate
  the rule keep their aliases and sit in a shrink-only allowlist. Renaming one
  would break instances in the wild to satisfy a convention.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.errors import KindRegistrationError
from dna.kernel.kinds.registry import (
    DESCRIPTOR_ALIAS_NAMESPACE_ALLOWLIST,
    alias_namespace_violation,
    alias_owner_token,
)
from dna.kernel.meta import DeclarativeKindPort
from dna.kernel.models import TypedKindDefinition


def _descriptor(*, alias: str, origin: str, kind: str = "Deal"):
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "probe"},
        "spec": {
            "target_api_version": "example.com/acme/v1",
            "target_kind": kind,
            "alias": alias,
            "origin": origin,
            "storage": {"type": "yaml", "dir": "deals"},
        },
    }


def _port(**kw):
    return DeclarativeKindPort.from_typed(
        TypedKindDefinition.from_raw(_descriptor(**kw)))


@pytest.mark.parametrize("origin, expected", [
    ("github.com/ruinosus/dna/sdlc", "sdlc"),
    ("example.com/acme", "acme"),
    ("mif-spec.dev", "mif-spec-dev"),
    ("", ""),
])
def test_the_owner_token_is_the_origins_last_segment(origin, expected):
    assert alias_owner_token(origin) == expected


def test_a_namespaced_alias_is_accepted():
    assert alias_namespace_violation(
        _port(alias="acme-deal", origin="example.com/acme")) is None


def test_a_bare_alias_is_refused_and_says_what_to_use():
    problem = alias_namespace_violation(
        _port(alias="deal", origin="example.com/acme"))
    assert problem is not None
    assert "acme-" in problem
    assert "acme-deal" in problem
    # ...and it says WHY, not just what: the collision surface is the point.
    assert "dep_filter" in problem


def test_an_alias_namespaced_to_somebody_else_is_refused():
    """The failure mode that matters: claiming another owner's prefix."""
    assert alias_namespace_violation(
        _port(alias="sdlc-deal", origin="example.com/acme")) is not None


def test_an_origin_with_no_owner_is_refused_rather_than_waved_through():
    """``origin`` is required by the descriptor schema, so an EMPTY one cannot
    be authored — but a port constructed some other way can still present one,
    and "cannot be checked" must not read as "passes"."""
    class _Unownable:
        __declarative__ = True
        alias = "deal"
        origin = "   "
        kind = "Deal"

    problem = alias_namespace_violation(_Unownable())
    assert problem is not None
    assert "names no owner" in problem


def test_class_kinds_are_out_of_scope():
    """A class Kind ships in the distribution and its alias is a live wire
    format; the rule is for the path a tenant can author."""
    class _NotDeclarative:
        alias = "totally-unnamespaced"
        origin = "example.com/acme"
        kind = "Deal"

    assert alias_namespace_violation(_NotDeclarative()) is None


def test_registration_refuses_a_bare_descriptor_alias():
    k = Kernel.auto()
    with pytest.raises(KindRegistrationError, match="namespace owner"):
        k.kind(_port(alias="deal", origin="example.com/acme"))


def test_registration_accepts_a_namespaced_one():
    k = Kernel.auto()
    k.kind(_port(alias="acme-deal", origin="example.com/acme"))
    assert k.kind_port_for("Deal", api_version="example.com/acme/v1") is not None


# ── the allowlist is shrink-only ────────────────────────────────────────────


def test_every_shipped_descriptor_either_complies_or_is_allowlisted():
    k = Kernel.auto()
    offenders = [
        p.alias for p in k.kind_ports()
        if alias_namespace_violation(p) is not None
    ]
    assert not offenders, offenders


def test_no_stale_allowlist_entries():
    """An allowlisted alias that no longer exists must be deleted, or the next
    author reads it as licence."""
    k = Kernel.auto()
    live = {
        getattr(p, "alias", "") for p in k.kind_ports()
        if getattr(p, "__declarative__", False)
    }
    stale = sorted(DESCRIPTOR_ALIAS_NAMESPACE_ALLOWLIST - live)
    assert not stale, f"allowlisted aliases that no longer exist: {stale}"


def test_the_allowlist_only_covers_genuine_violations():
    """Every entry must actually need the exemption — an allowlist that carries
    compliant names is one nobody trusts."""
    k = Kernel.auto()
    by_alias = {getattr(p, "alias", ""): p for p in k.kind_ports()}
    for alias in DESCRIPTOR_ALIAS_NAMESPACE_ALLOWLIST:
        port = by_alias.get(alias)
        assert port is not None, alias
        owner = alias_owner_token(getattr(port, "origin", ""))
        assert not (owner and alias.startswith(f"{owner}-")), (
            f"{alias!r} complies with the convention — remove it from the "
            f"allowlist"
        )
