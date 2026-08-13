"""s-unify-composition-subsystems — the composition readers CONVERGE.

``mi.composition.validate()`` (validation), ``mi.nav.inventory()``
(inventory classification) and kinds-api docs all consume the SAME
canonical dep_filter resolver (``KindRegistry.resolve_dep_filter_target``,
s-alias): a legacy ``kind=<Name>`` filter and an alias filter resolve
IDENTICALLY on every path. The record-plane rule is also ONE rule for
every reader: ref in index → resolved; absent + record target →
deferred (never missing).

⚠️ This suite used to assert convergence between the MI plane and a
"source plane" spelled ``kernel/query/nav.py`` — an async twin of
``query/navigator.py`` with ZERO production callers, deleted in
s-dna-shrink-faixa-1 (i-047). Half of every "the two planes agree"
assertion was therefore about code no caller reached, which is worse
than no assertion: it read as convergence evidence while covering one
live reader and one dead one. The convergence claim is now made between
the two readers that actually run — ``composition.validate()`` and
``nav.inventory()`` — over the SAME ``ManifestInstance``.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import StorageDescriptor

# -- reuse do harness (pytest põe tests/ no sys.path; SEM prefixo tests.) --
from test_kernel_invalidate_modes import _FakeWritableSource


class _TargetLike(KindBase):
    api_version = "test.io/v1"
    kind = "TargetLike"
    alias = "test-targetlike"
    storage = StorageDescriptor.yaml("targetlikes")


class _RecordLike(KindBase):
    api_version = "test.io/v1"
    kind = "RecordLike"
    alias = "test-recordlike"
    storage = StorageDescriptor.yaml("recordlikes")
    plane = "record"


class _ConsumerLike(KindBase):
    """dep_filters mixing the alias contract, the legacy ``kind=`` shim
    and a record-plane target — the exact three shapes whose semantics
    used to diverge across readers."""
    api_version = "test.io/v1"
    kind = "ConsumerLike"
    alias = "test-consumerlike"
    storage = StorageDescriptor.yaml("consumerlikes")

    def dep_filters(self):
        return {
            "by_alias": "test-targetlike",
            "by_legacy": "kind=TargetLike",
            "rec": "test-recordlike",
        }


def _raw(kind: str, name: str, **spec):
    return {"apiVersion": "test.io/v1", "kind": kind,
            "metadata": {"name": name}, "spec": spec}


def _kernel() -> Kernel:
    k = Kernel()
    k._source = _FakeWritableSource()  # type: ignore[assignment]
    k.kind(_TargetLike())
    k.kind(_RecordLike())
    k.kind(_ConsumerLike())
    return k


# ---------- kind= legado e alias resolvem IGUAL nos dois leitores ----------

def test_legacy_and_alias_filters_resolve_identically():
    k = _kernel()
    raws = [
        _raw("TargetLike", "t-1"),
        _raw("ConsumerLike", "c-1", by_alias="t-1", by_legacy="t-1"),
    ]
    mi = k.build(raws, "scope-x")
    result = mi.composition.validate()

    assert any("by_alias=t-1" in r for r in result.resolved), (
        f"alias filter must resolve: {result.resolved}"
    )
    assert any("by_legacy=t-1" in r for r in result.resolved), (
        "legacy kind= filter must resolve IDENTICALLY to the alias filter "
        f"(same canonical resolver): resolved={result.resolved} "
        f"warnings={result.warnings}"
    )
    assert result.missing == []
    assert result.warnings == []


def test_inventory_classification_uses_the_same_resolver():
    """The OTHER live reader — ``mi.nav.inventory()`` — classifies the two
    filter shapes identically. This is the convergence half that still has
    two real readers: validation labels the edge, inventory grades its
    confidence, and both must agree that ``kind=TargetLike`` and
    ``test-targetlike`` name the same target."""
    k = _kernel()
    raws = [
        _raw("TargetLike", "t-1"),
        _raw("ConsumerLike", "c-1", by_alias="t-1", by_legacy="t-1"),
    ]
    mi = k.build(raws, "scope-x")
    inv = mi.nav.inventory()
    (consumer,) = inv["kinds"]["ConsumerLike"]["instances"]
    assert consumer["refs_confidence"]["by_alias"] == "EXTRACTED"
    assert consumer["refs_confidence"]["by_legacy"] == "EXTRACTED", (
        "kind= legado deve classificar igual ao alias (mesmo resolvedor): "
        f"{consumer['refs_confidence']}"
    )
    # …and the two readers agree the edge is clean.
    assert inv["composition"]["missing"] == []
    assert inv["composition"]["resolved"] == mi.composition.validate().resolved


# ---------- record rule: uma regra para todo leitor ----------

def test_record_ref_defers_never_missing():
    """Records are excluded from materialization, so an MI-plane ref to one
    DEFERS — it is resolved lazily off the record plane — and must never be
    reported as missing."""
    k = _kernel()
    raws = [
        _raw("TargetLike", "t-1"),
        _raw("RecordLike", "r-1"),
        _raw("ConsumerLike", "c-1", by_alias="t-1", by_legacy="t-1",
             rec="r-1"),
    ]
    mi = k.build(raws, "scope-x")
    result = mi.composition.validate()
    assert any("r-1" in d for d in result.deferred)
    assert not any("r-1" in m for m in result.missing)


def test_dangling_record_ref_defers_too():
    """Even a record target that exists NOWHERE defers rather than failing
    missing: the MI plane cannot see the record plane, so absence there is
    not evidence of absence. Reporting it missing would be a false negative
    on every lazily-resolved ref."""
    k = _kernel()
    raws = [
        _raw("TargetLike", "t-1"),
        _raw("ConsumerLike", "c-1", by_alias="t-1", by_legacy="t-1",
             rec="r-ghost"),
    ]
    mi = k.build(raws, "scope-x")
    result = mi.composition.validate()
    assert any("r-ghost" in d for d in result.deferred), (
        "ref a record ausente defere (resolve lazy via record plane), "
        f"nunca falso-missing: deferred={result.deferred} "
        f"missing={result.missing}"
    )
    assert not any("r-ghost" in m for m in result.missing)
