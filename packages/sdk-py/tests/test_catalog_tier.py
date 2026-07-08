"""Phase 3b ch1 — pure resolver of the Catalog scope set (i-112).

``resolve_catalog_scopes`` turns "what's installed for this tenant" into the
ordered list of ``(scope, target_tenant)`` tuples the resolver/query splice in
between Local and Base. UNION of:
  - mandatory platform packages (``owner_tenant is None ∧ spec.mandatory``) →
    universal, tenant=None
  - the tenant's lockfile installs (``GenomeEntry`` list) → scope from
    ``source.split("/")[-1]``, tenant from ``target_tenant or None``
deduped by scope (mandatory wins, tenant=None), ``exclude`` dropped, sorted.
"""
from __future__ import annotations

from dna.kernel.catalog_tier import resolve_catalog_scopes


class _P:
    """Fake Genome doc — exposes ``.name`` (scope) + ``.spec`` (dict)."""

    def __init__(self, name, owner_tenant=None, mandatory=False):
        self.name = name
        self.spec = {"owner_tenant": owner_tenant, "mandatory": mandatory}


class _Entry:
    """Fake GenomeEntry — ``.source`` (``<owner>/<name>``) + ``.target_tenant``."""

    def __init__(self, source, target_tenant=""):
        self.source = source
        self.target_tenant = target_tenant


def test_mandatory_platform_always_plus_lock_union_sorted_deduped():
    pkgs = [_P("voice-core", mandatory=True), _P("hr", owner_tenant="acme")]
    out = resolve_catalog_scopes(
        pkgs,
        [_Entry("acme/hr", "acme")],
        exclude={"proj", "_lib"},
    )
    # → sorted by scope: hr (from lock, tenant=acme), voice-core (mandatory, None)
    assert out == [("hr", "acme"), ("voice-core", None)]


def test_mandatory_only_platform_owned():
    # owner_tenant is NOT None → not a platform-mandatory package → excluded.
    out = resolve_catalog_scopes(
        [_P("x", owner_tenant="acme", mandatory=True)], [], exclude=set(),
    )
    assert out == []


def test_excludes_requesting_and_base_scope():
    out = resolve_catalog_scopes(
        [_P("voice-core", mandatory=True)], [], exclude={"voice-core"},
    )
    assert out == []


def test_lock_entry_without_target_tenant_maps_to_none():
    out = resolve_catalog_scopes(
        [], [_Entry("acme/hr", "")], exclude=set(),
    )
    assert out == [("hr", None)]


def test_mandatory_wins_tenant_none_on_dedup():
    # Same scope appears as both mandatory platform AND a lock install →
    # mandatory wins (tenant=None).
    out = resolve_catalog_scopes(
        [_P("voice-core", mandatory=True)],
        [_Entry("platform/voice-core", "acme")],
        exclude=set(),
    )
    assert out == [("voice-core", None)]


def test_empty_inputs_empty_output():
    assert resolve_catalog_scopes([], [], exclude=set()) == []


def test_non_mandatory_platform_package_not_included_without_lock():
    # A platform package that is NOT mandatory and NOT in the lock → out.
    out = resolve_catalog_scopes(
        [_P("opt-core", mandatory=False)], [], exclude=set(),
    )
    assert out == []
