"""CHARACTERIZATION — pins current behavior for kernel decomposition Fases 2-5;
if this breaks during an extraction, the extraction changed observable behavior.

Block 3 of the kernel-decomposition spec (2026-07-08-kernel-decomposition-design)
= Kind registration / the H1 validation funnel (``kind`` = 183 loc,
``_register_kind_definitions``, ``_lint_kind_plane``, ``kind_from_descriptor``,
…, ~555 loc). Fase 3 finishes the ``KindRegistry`` collaborator by moving these
in. The H1 boot-time validation is load-bearing (spec Risk §3.3); this suite
freezes the exact conflict/idempotency classes so the move is provable.

Already covered elsewhere (referenced, NOT duplicated):
  - ``test_kind_plane``              → the full plane-lint contradiction matrix.
  - ``test_kind_name_collision``     → i-195 name-collision + allowlist + demotion.
  - ``test_kind_from_descriptor``    → descriptor digest idempotency + per-scope
                                       kinddef warn+skip + plane lint on funnels.
  - ``test_alias_generation``        → generated-alias uniqueness + dep_filters.

Genuine GAPS this suite closes — the H1 branches with no dedicated golden:
  1. Protocol-conformance rejection (object is not a KindPort).
  2. Duplicate (api_version, kind) by a DIFFERENT class → raise; SAME class → no-op.
  3. Duplicate ALIAS across two distinct keys → raise.
  4. BUNDLE (container, marker) collision → raise; and the N=2 opt-in
     (``marker_shared_allowed=True`` on BOTH) → allowed.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel, KindRegistrationError
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import StorageDescriptor


# ── Fixture Kinds ─────────────────────────────────────────────────────────

class _AlphaKind(KindBase):
    api_version = "reg.io/v1"
    kind = "Alpha"
    alias = "reg-alpha"
    storage = StorageDescriptor.yaml("alphas")


class _AlphaKindOtherClass(KindBase):
    """Same (api_version, kind) as _AlphaKind but a DIFFERENT class."""
    api_version = "reg.io/v1"
    kind = "Alpha"
    alias = "reg-alpha-other"
    storage = StorageDescriptor.yaml("alphas2")


class _BetaKind(KindBase):
    api_version = "reg.io/v1"
    kind = "Beta"
    alias = "reg-beta"
    storage = StorageDescriptor.yaml("betas")


class _BetaAliasClash(KindBase):
    """Distinct key, but reuses _BetaKind's alias."""
    api_version = "reg.io/v2"
    kind = "BetaTwo"
    alias = "reg-beta"  # collides
    storage = StorageDescriptor.yaml("betatwos")


class _BundleOne(KindBase):
    api_version = "reg.io/v1"
    kind = "BundleOne"
    alias = "reg-bundleone"
    storage = StorageDescriptor.bundle("programs", "program.md")


class _BundleTwoSameMarker(KindBase):
    api_version = "reg.io/v2"
    kind = "BundleTwo"
    alias = "reg-bundletwo"
    storage = StorageDescriptor.bundle("programs", "program.md")  # same pair


class _BundleSharedA(KindBase):
    api_version = "reg.io/v1"
    kind = "SharedA"
    alias = "reg-shareda"
    storage = StorageDescriptor.bundle("shared", "prog.md")
    marker_shared_allowed = True


class _BundleSharedB(KindBase):
    api_version = "reg.io/v2"
    kind = "SharedB"
    alias = "reg-sharedb"
    storage = StorageDescriptor.bundle("shared", "prog.md")
    marker_shared_allowed = True


# ── 1. Protocol conformance ───────────────────────────────────────────────

def test_register_non_kindport_raises_registration_error():
    k = Kernel()

    class _NotAKind:  # missing the whole KindPort surface
        pass

    with pytest.raises(KindRegistrationError, match="KindPort"):
        k.kind(_NotAKind())  # type: ignore[arg-type]


# ── 2. Duplicate (api_version, kind) ──────────────────────────────────────

def test_same_class_reregistration_is_idempotent_noop():
    k = Kernel()
    port = _AlphaKind()
    k.kind(port)
    k.kind(_AlphaKind())  # same class, same key → silent no-op
    assert k.kind_port_for("Alpha") is port  # first registration kept


def test_different_class_same_key_raises():
    k = Kernel()
    k.kind(_AlphaKind())
    with pytest.raises(KindRegistrationError, match="already registered"):
        k.kind(_AlphaKindOtherClass())


# ── 3. Duplicate alias ────────────────────────────────────────────────────

def test_duplicate_alias_across_distinct_keys_raises():
    k = Kernel()
    k.kind(_BetaKind())
    with pytest.raises(KindRegistrationError, match="alias"):
        k.kind(_BetaAliasClash())


# ── 4. BUNDLE (container, marker) collision + N=2 opt-in ──────────────────

def test_bundle_marker_collision_raises():
    k = Kernel()
    k.kind(_BundleOne())
    with pytest.raises(KindRegistrationError, match="BUNDLE"):
        k.kind(_BundleTwoSameMarker())


def test_bundle_marker_shared_allowed_on_both_is_permitted():
    """Two bundle Kinds may share a (container, marker) pair IFF BOTH opt in
    via marker_shared_allowed=True (they disambiguate at read time by
    frontmatter dialect). Registration succeeds; both ports are queryable."""
    k = Kernel()
    k.kind(_BundleSharedA())
    k.kind(_BundleSharedB())  # must NOT raise
    assert k.kind_port_for("SharedA") is not None
    assert k.kind_port_for("SharedB") is not None


def test_bundle_shared_requires_both_sides_to_opt_in():
    """One-sided opt-in is not enough — the non-opted side still collides."""
    k = Kernel()
    k.kind(_BundleSharedA())  # opted in

    class _OneSided(KindBase):
        api_version = "reg.io/v3"
        kind = "OneSided"
        alias = "reg-onesided"
        storage = StorageDescriptor.bundle("shared", "prog.md")
        # marker_shared_allowed defaults False

    with pytest.raises(KindRegistrationError, match="BUNDLE"):
        k.kind(_OneSided())


# ── 5. plane lint runs inside kind() (reference: test_kind_plane) ─────────

def test_plane_lint_rejects_record_with_composition_signal():
    """Anchor that the plane lint fires through kind() itself (the funnel
    Fase 3 moves) — the exhaustive matrix lives in test_kind_plane."""
    k = Kernel()

    class _BadRecord(KindBase):
        api_version = "reg.io/v1"
        kind = "BadRecord"
        alias = "reg-badrecord"
        storage = StorageDescriptor.yaml("badrecords")
        plane = "record"
        is_prompt_target = True  # contradiction

    with pytest.raises(KindRegistrationError, match="record"):
        k.kind(_BadRecord())
