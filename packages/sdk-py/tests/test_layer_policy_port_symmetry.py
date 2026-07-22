"""Read/write policy-port SYMMETRY (i-049).

The 2026-07-21 finding (fallout of the i-044 work): the two ports of layer
policy answered DIFFERENTLY for the same declared policy. The read/merge port
(``DefaultLayerResolver._policy_for_kind``) accepted the key as exact Kind
name → declared alias → legacy suffixes; the write port
(``LayerPolicyEnforcer._enforce``) accepted ONLY the alias. So a LayerPolicy
with ``Agent: locked`` (keyed by name) locked the merge but was SILENTLY
ignored on write — worse than not holding at all: false confidence.

The repaired contract, pinned here: both ports resolve the key through the
SAME resolver (``dna.kernel.layer_resolver.match_policy_key``). Properties:

* the same policy locks READ **and** WRITE — keyed by Kind NAME;
* the same policy locks READ **and** WRITE — keyed by declared ALIAS;
* a near-miss key matches NEITHER port (no inference beyond the declared
  i-044 order — a typo must not half-lock the system).

Mutation guide (each port, swap the shared resolver back for its old one):
* write port ``lp_policies.get(alias)``   → the lock-by-NAME write test dies;
* read  port ``policies.get(declared)``   → the lock-by-NAME read test dies.
"""
from __future__ import annotations

import pytest

from dna.kernel.layer_policy import LayerPolicyEnforcer
from dna.kernel.layer_resolver import DefaultLayerResolver, match_policy_key
from dna.kernel.protocols import LayerPolicy, LayerPolicyViolationError

# ── harnesses: one per port, same declared world ────────────────────────────
#
# The Kind is 'Skill'; its registry-declared alias is 'owner-skill' (the
# fake kernel's _alias_for and the resolver's kind_aliases map agree —
# exactly how the real kernel wires both ports from the same registry).

_KIND = "Skill"
_ALIAS = "owner-skill"


class _FakeDoc:
    def __init__(self, spec):
        self.spec = spec
        self.raw = {"spec": spec}


class _FakeMI:
    def __init__(self, policies_for_layer=None):
        self._lp = policies_for_layer or []

    def _all(self, kind):
        return self._lp if kind == "LayerPolicy" else []

    def _one(self, kind, name):
        return None


class _FakeKernel:
    _NON_OVERLAYABLE_KINDS = frozenset()

    def _alias_for(self, kind):
        return _ALIAS if kind == _KIND else f"owner-{kind.lower()}"


def _write_allowed(policy_key: str) -> bool:
    """Attempt a WRITE of Skill/x to layer 'tenant-a' under a LayerPolicy doc
    ``{policy_key: locked}``. True → the write passed (policy did not bind)."""
    enf = LayerPolicyEnforcer(_FakeKernel())
    mi = _FakeMI([_FakeDoc({"layer_id": "tenant-a", "policies": {policy_key: "locked"}})])
    try:
        enf._enforce(
            mi, "scope", _KIND, "x", {"spec": {}}, ("tenant-a", ""),
            LayerPolicy=LayerPolicy,
            LayerPolicyViolationError=LayerPolicyViolationError,
        )
        return True
    except LayerPolicyViolationError:
        return False


def _read_merge_held(policy_key: str) -> bool:
    """Resolve a base Skill doc against a tampering overlay under
    ``{policy_key: LOCKED}``. True → the base survived (lock held)."""
    resolver = DefaultLayerResolver(kind_aliases={_KIND: _ALIAS})
    base = [{
        "apiVersion": "v1", "kind": _KIND,
        "metadata": {"name": "x"}, "spec": {"body": "base"},
    }]
    overlay = [{
        "apiVersion": "v1", "kind": _KIND,
        "metadata": {"name": "x"}, "spec": {"body": "tampered"},
    }]

    class _Src:
        def load_layer(self, _scope, _lid, _lv):
            return overlay

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # LOCKED-ignored / fallback warnings
        result = resolver.resolve(
            base, {"tenant": "a"}, _Src(), "s",
            {policy_key: LayerPolicy.LOCKED},
        )
    return result[0]["spec"]["body"] == "base"


# ── the symmetry properties ─────────────────────────────────────────────────


def test_lock_keyed_by_kind_name_binds_both_ports():
    """THE i-049 finding: ``Skill: locked`` (Kind NAME). The merge held —
    and the write must now be denied too, instead of silently passing."""
    assert _read_merge_held(_KIND), "read port must honor a name-keyed lock"
    assert not _write_allowed(_KIND), (
        "write port ignored a name-keyed lock the read port enforces — "
        "the i-049 asymmetry is back (false confidence: the operator's "
        "declared protection holds on one port only)"
    )


def test_lock_keyed_by_declared_alias_binds_both_ports():
    """``owner-skill: locked`` (declared ALIAS) — the write port's historic
    happy path, and the read port's i-044 declared path. Both must bind."""
    assert _read_merge_held(_ALIAS)
    assert not _write_allowed(_ALIAS)


def test_near_miss_key_binds_neither_port():
    """A typo'd key ('owner-skil') matches NOTHING on either port — the
    resolver must not invent a match, and BOTH ports must agree it is absent
    (the read port additionally warns, pinned by the i-044 suite)."""
    assert not _read_merge_held("owner-skil"), "near-miss must not lock the merge"
    assert _write_allowed("owner-skil"), "near-miss must not lock the write"


def test_both_ports_resolve_through_the_same_function():
    """Structural pin: the shared resolver answers for name, alias and
    near-miss exactly as the two port-level tests above observe — and the
    ports import THIS function (mutating either port back to a private
    lookup kills the corresponding port test above)."""
    policies = {"Skill": "locked"}
    assert match_policy_key(_KIND, policies, declared_alias=_ALIAS) == "locked"
    assert match_policy_key(_KIND, {_ALIAS: "locked"}, declared_alias=_ALIAS) == "locked"
    assert match_policy_key(_KIND, {"owner-skil": "locked"}, declared_alias=_ALIAS) is None


def test_legacy_suffix_key_binds_both_ports():
    """The legacy heuristic ('anything-skill') was a READ-port-only path
    pre-i-049; symmetry means it now governs the write too — same resolver,
    same answer, no port-private dialect of key matching."""
    assert _read_merge_held("legacy-skill")
    assert not _write_allowed("legacy-skill")
