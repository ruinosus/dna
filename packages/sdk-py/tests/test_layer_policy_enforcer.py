"""Unit tests for the LayerPolicyEnforcer collaborator (kernel-decompose-continue).

Exercises the LOCKED / RESTRICTED / OPEN + non-overlayable semantics directly,
with a fake kernel (the few accessors the enforcer needs) and a fake base MI.
The kernel-level behavior is covered exhaustively by test_kernel_layer_policy.py
and test_layer_policy_phase16.py via the delegators.
"""
from __future__ import annotations

import pytest

from dna.kernel.compose.layer_policy import LayerPolicyEnforcer
from dna.kernel.protocols import LayerPolicy, LayerPolicyViolationError


class _FakeDoc:
    def __init__(self, spec):
        self.spec = spec
        self.raw = {"spec": spec}


class _FakeMI:
    """Fake base MI: `_all('LayerPolicy')` → policy docs; `_one(kind,name)` → doc
    (the enforcer consumes the MI internal non-deprecated twins —
    s-blessed-query-surface)."""
    def __init__(self, policies_for_layer=None, existing=None):
        self._lp = policies_for_layer or []
        self._existing = existing

    def _all(self, kind):
        return self._lp if kind == "LayerPolicy" else []

    def _one(self, kind, name):
        return self._existing


class _FakeKernel:
    def __init__(self, non_overlayable=frozenset()):
        self._NON_OVERLAYABLE_KINDS = non_overlayable

    def _alias_for(self, kind):
        return f"owner-{kind.lower()}"


def _enforcer(non_overlayable=frozenset()):
    return LayerPolicyEnforcer(_FakeKernel(non_overlayable))


def _enforce(enf, mi, kind="Skill", name="x", raw=None, layer=("tenant-a", "")):
    enf._enforce(
        mi, "scope", kind, name, raw or {"spec": {}}, layer,
        LayerPolicy=LayerPolicy, LayerPolicyViolationError=LayerPolicyViolationError,
    )


def _lp_doc(layer_id, alias, mode):
    return _FakeDoc({"layer_id": layer_id, "policies": {alias: mode}})


def test_open_allows():
    _enforce(_enforcer(), _FakeMI())  # no policy docs → OPEN, no raise


def test_non_overlayable_raises_first():
    enf = _enforcer(non_overlayable=frozenset({"Genome"}))
    with pytest.raises(LayerPolicyViolationError, match="non-overlayable"):
        _enforce(enf, _FakeMI(), kind="Genome")


def test_locked_raises():
    mi = _FakeMI(policies_for_layer=[_lp_doc("tenant-a", "owner-skill", "locked")])
    with pytest.raises(LayerPolicyViolationError, match="LOCKED"):
        _enforce(_enforcer(), mi)


def test_restricted_new_doc_raises():
    mi = _FakeMI(
        policies_for_layer=[_lp_doc("tenant-a", "owner-skill", "restricted")],
        existing=None,  # not present in base → adding new doc
    )
    with pytest.raises(LayerPolicyViolationError, match="cannot add new document"):
        _enforce(_enforcer(), mi)


def test_restricted_new_top_level_key_raises():
    mi = _FakeMI(
        policies_for_layer=[_lp_doc("tenant-a", "owner-skill", "restricted")],
        existing=_FakeDoc({"a": 1}),  # base has key 'a'
    )
    with pytest.raises(LayerPolicyViolationError, match="new top-level spec keys"):
        _enforce(_enforcer(), mi, raw={"spec": {"a": 1, "b": 2}})  # adds 'b'


def test_restricted_override_existing_key_allowed():
    mi = _FakeMI(
        policies_for_layer=[_lp_doc("tenant-a", "owner-skill", "restricted")],
        existing=_FakeDoc({"a": 1}),
    )
    _enforce(_enforcer(), mi, raw={"spec": {"a": 99}})  # overrides 'a' → allowed


def test_policy_for_other_layer_is_ignored():
    # A LOCKED policy on a DIFFERENT layer_id must not affect this write.
    mi = _FakeMI(policies_for_layer=[_lp_doc("other-layer", "owner-skill", "locked")])
    _enforce(_enforcer(), mi)  # our layer is 'tenant-a' → OPEN, no raise
