"""s-unify-composition-subsystems — the composition readers CONVERGE.

``mi.composition.validate()`` (MI plane), ``nav_kernel``'s validation +
inventory classification (source plane) and kinds-api docs all consume
the SAME canonical dep_filter resolver
(``KindRegistry.resolve_dep_filter_target``, s-alias): a legacy
``kind=<Name>`` filter and an alias filter resolve IDENTICALLY on every
path. The record-plane rule is also ONE rule for every reader: ref in
index → resolved; absent + record target → deferred (never missing).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from dna.kernel import Kernel
from dna.kernel.document import Document
from dna.kernel.kinds.base import KindBase
from dna.kernel.query.nav import (
    scope_inventory_async,
    validate_composition_async,
)
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


def _nav_kernel_over(k: Kernel, raws: list[dict]) -> SimpleNamespace:
    """Source-plane view: a kernel façade whose ``query`` serves ``raws``
    (records INCLUDED — the source sees both planes), sharing the REAL
    kernel's registered kinds so both paths resolve over the same ports."""
    by_kind: dict[str, list[dict]] = {}
    for r in raws:
        by_kind.setdefault(r["kind"], []).append(r)

    async def _query(scope, kind, **kw):
        for r in by_kind.get(kind, []):
            yield r

    async def _list(scope, *, kind=None, tenant=None):
        if kind is None:
            return [(r["kind"], r["metadata"]["name"]) for rs in by_kind.values() for r in rs]
        return [(r["kind"], r["metadata"]["name"]) for r in by_kind.get(kind, [])]

    def _parse(raw, origin="local"):
        meta = raw.get("metadata", {}) or {}
        return Document(
            api_version=raw.get("apiVersion", "v1"), kind=raw["kind"],
            name=meta.get("name", ""), metadata=meta,
            spec=raw.get("spec", {}) or {},
        )

    return SimpleNamespace(
        query=_query, list_documents=_list, _parse_doc=_parse,
        _kinds=k._kinds,
    )


# ---------- kind= legado e alias resolvem IGUAL nos dois caminhos ----------

@pytest.mark.asyncio
async def test_legacy_and_alias_filters_resolve_identically_on_both_paths():
    k = _kernel()
    raws = [
        _raw("TargetLike", "t-1"),
        _raw("ConsumerLike", "c-1", by_alias="t-1", by_legacy="t-1"),
    ]

    # MI plane (mi.composition.validate)
    mi = k.build(raws, "scope-x")
    mi_result = mi.composition.validate()

    # Source plane (nav_kernel.validate_composition_async)
    nav_result = await validate_composition_async(
        _nav_kernel_over(k, raws), "scope-x",
    )

    for result, plane in ((mi_result, "MI"), (nav_result, "nav")):
        assert any("by_alias=t-1" in r for r in result.resolved), (
            f"[{plane}] alias filter must resolve: {result.resolved}"
        )
        assert any("by_legacy=t-1" in r for r in result.resolved), (
            f"[{plane}] legacy kind= filter must resolve identically to the "
            f"alias filter: resolved={result.resolved} "
            f"warnings={result.warnings}"
        )
        assert result.missing == []
        assert result.warnings == []

    # No records involved → the two planes see the same doc set and must
    # produce byte-identical labels.
    assert sorted(mi_result.resolved) == sorted(nav_result.resolved)


@pytest.mark.asyncio
async def test_inventory_classification_uses_the_same_resolver():
    k = _kernel()
    raws = [
        _raw("TargetLike", "t-1"),
        _raw("ConsumerLike", "c-1", by_alias="t-1", by_legacy="t-1"),
    ]
    inv = await scope_inventory_async(_nav_kernel_over(k, raws), "scope-x")
    (consumer,) = inv["kinds"]["ConsumerLike"]["documents"]
    assert consumer["refs_confidence"]["by_alias"] == "EXTRACTED"
    assert consumer["refs_confidence"]["by_legacy"] == "EXTRACTED", (
        "kind= legado deve classificar igual ao alias (mesmo resolvedor): "
        f"{consumer['refs_confidence']}"
    )


# ---------- record rule: uma regra, dois planos ----------

@pytest.mark.asyncio
async def test_record_rule_one_rule_both_planes():
    k = _kernel()
    raws = [
        _raw("TargetLike", "t-1"),
        _raw("RecordLike", "r-1"),
        _raw("ConsumerLike", "c-1", by_alias="t-1", by_legacy="t-1",
             rec="r-1"),
    ]

    # MI plane: records são excluídos da materialização → ref defere.
    mi = k.build(raws, "scope-x")
    mi_result = mi.composition.validate()
    assert any("r-1" in d for d in mi_result.deferred)
    assert not any("r-1" in m for m in mi_result.missing)

    # Source plane: o record está no índice → resolve.
    nav_result = await validate_composition_async(
        _nav_kernel_over(k, raws), "scope-x",
    )
    assert any("rec=r-1" in r for r in nav_result.resolved)
    assert not any("r-1" in m for m in nav_result.missing)


@pytest.mark.asyncio
async def test_dangling_record_ref_defers_on_source_plane_too():
    k = _kernel()
    raws = [
        _raw("TargetLike", "t-1"),
        _raw("ConsumerLike", "c-1", by_alias="t-1", by_legacy="t-1",
             rec="r-ghost"),
    ]
    nav_result = await validate_composition_async(
        _nav_kernel_over(k, raws), "scope-x",
    )
    assert any("r-ghost" in d for d in nav_result.deferred), (
        "ref a record ausente defere (resolve lazy via record plane), "
        f"nunca falso-missing: deferred={nav_result.deferred} "
        f"missing={nav_result.missing}"
    )
    assert not any("r-ghost" in m for m in nav_result.missing)
