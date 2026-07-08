"""s-blessed-query-surface — blessed query surface lock (Python side).

The shared fixture ``tests/parity-fixtures/port-surface-parity.json``
(repo root, section ``blessed_query_surface``) declares:

  - ``blessed``: the ONE documented read/query surface (what docs/,
    README and examples teach). Members must exist and calling the
    cheap ones must be silent (no DeprecationWarning).
  - ``deprecated``: still work, but emit ``DeprecationWarning`` naming
    the exact replacement and the removal release (1.0).
  - ``public_surface``: EXACT set of public members on an instantiated
    ManifestInstance — adding/removing/renaming a public member without
    editing the fixture turns this suite red, so every public-surface
    change is a conscious decision.

TS twin: ``packages/sdk-ts/tests/blessed-query-surface.test.ts``.
"""
from __future__ import annotations

import json
import pathlib
import warnings

import pytest

from dna.kernel import Kernel
from dna.kernel.instance import ManifestInstance

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "tests" / "parity-fixtures" / "port-surface-parity.json"
)


@pytest.fixture(scope="module")
def surface() -> dict:
    data = json.loads(_FIXTURE.read_text())
    assert "blessed_query_surface" in data, (
        "fixture missing blessed_query_surface section"
    )
    return data["blessed_query_surface"]


def _mi() -> ManifestInstance:
    return ManifestInstance(scope="t", documents=[], kinds={})


# ---------------------------------------------------------------------------
# Existence — blessed + deprecated members are real attributes
# ---------------------------------------------------------------------------


def test_blessed_mi_members_exist(surface):
    mi = _mi()
    for m in surface["ManifestInstance"]["blessed"]:
        if m["py"] is None:
            assert m.get("justification"), f"one-sided member {m} needs justification"
            continue
        assert hasattr(mi, m["py"]), f"blessed MI member missing: {m['py']}"


def test_deprecated_mi_members_exist(surface):
    mi = _mi()
    for m in surface["ManifestInstance"]["deprecated"]:
        assert m.get("replacement"), f"deprecated member {m} must name a replacement"
        assert m.get("removal") == "1.0", f"deprecated member {m} must state removal release"
        assert hasattr(mi, m["py"]), f"deprecated MI member missing: {m['py']}"


def test_blessed_kernel_members_exist(surface):
    k = Kernel()
    for m in surface["Kernel"]["blessed"]:
        if m["py"] is None:
            assert m.get("justification"), f"one-sided member {m} needs justification"
            continue
        assert hasattr(k, m["py"]), f"blessed Kernel member missing: {m['py']}"


def test_one_sided_members_carry_justification(surface):
    for cls in ("ManifestInstance", "Kernel"):
        for group in ("blessed", "deprecated"):
            for m in surface[cls].get(group, []):
                if m.get("py") is None or m.get("ts") is None:
                    assert m.get("justification"), (
                        f"{cls}.{group} one-sided member {m} MUST carry a "
                        f"non-empty justification — asymmetries are "
                        f"documented, never silent"
                    )


# ---------------------------------------------------------------------------
# Public-surface exact lock — conscious decisions only
# ---------------------------------------------------------------------------


def test_mi_public_surface_is_exactly_the_fixture(surface):
    expected = set(surface["ManifestInstance"]["public_surface"]["py"])
    actual = {n for n in dir(_mi()) if not n.startswith("_")}
    added = actual - expected
    removed = expected - actual
    assert not added and not removed, (
        f"ManifestInstance public surface drifted from the fixture — "
        f"added={sorted(added)} removed={sorted(removed)}. If intentional, "
        f"update blessed_query_surface.ManifestInstance.public_surface in "
        f"{_FIXTURE} (both py AND ts sides — this is a parity decision)."
    )


# ---------------------------------------------------------------------------
# Deprecation behavior — deprecated warns with guidance, blessed is silent
# ---------------------------------------------------------------------------


def test_mi_all_warns_with_replacement():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _mi().all("Skill")
    msgs = [str(x.message) for x in w if issubclass(x.category, DeprecationWarning)]
    assert msgs, "mi.all() must emit DeprecationWarning"
    assert any(
        "will be removed in 1.0" in m and "mi.documents" in m and "kernel.query" in m
        for m in msgs
    ), f"mi.all() warning must name the blessed replacement; got {msgs}"


def test_mi_one_warns_with_replacement():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _mi().one("Skill", "x")
    msgs = [str(x.message) for x in w if issubclass(x.category, DeprecationWarning)]
    assert msgs, "mi.one() must emit DeprecationWarning"
    assert any(
        "will be removed in 1.0" in m
        and "mi.documents" in m
        and "kernel.get_document" in m
        for m in msgs
    ), f"mi.one() warning must name the blessed replacement; got {msgs}"


def test_blessed_surface_is_silent():
    """Touching the blessed read surface emits NO DeprecationWarning."""
    mi = _mi()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _ = mi.documents
        _ = mi.root
        _ = mi.default_agent()
        _ = mi.find_agent("nope")
        _ = mi.resolve(None)
    deps = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert not deps, (
        f"blessed surface must be warning-free; got "
        f"{[str(x.message) for x in deps]}"
    )


def test_internal_twins_are_silent():
    """The SDK's own collaborators use _all/_one — never the warning shims."""
    mi = _mi()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert mi._all("Skill") == []
        assert mi._one("Skill", "x") is None
    deps = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert not deps
