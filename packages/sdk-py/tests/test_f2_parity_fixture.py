"""Two-planes F2 — Py↔TS parity by shared fixture.

Runs every case in ``packages/sdk-ts/tests/fixtures/f2-parity.json``
against the Py in-memory query/count core (the ``SourcePort``
protocol-default — the exact code path the Filesystem adapter delegates
to). The TS twin (``packages/sdk-ts/tests/f2-parity.test.ts``) runs the
SAME fixture against ``queryDocs``/``countDocs``. A failure on either
side is a parity divergence with an immediate reproduction.

MONOREPO LIMITATION (documented on purpose): the fixture lives in the
sdk-ts package and is reached via a ``Path(__file__)``-relative hop
across packages. That only works in a monorepo checkout — an sdk-py
sdist/wheel or a standalone checkout won't have it, so the whole module
SKIPS (with an explicit reason) instead of failing. If this skips in CI
of THIS repo, someone moved the fixture — treat that as a failure.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from dna.kernel.query_fallback import count_via_query, query_via_load_all

# packages/sdk-py/tests/test_f2_parity_fixture.py
#   parents[0]=tests, [1]=sdk-py, [2]=packages
FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "sdk-ts" / "tests" / "fixtures" / "f2-parity.json"
)

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason=(
        "shared parity fixture lives in packages/sdk-ts (monorepo checkout "
        f"required; looked at {FIXTURE})"
    ),
)


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class _FixtureSource:
    """Minimal source: protocol-default query/count run over load_all.

    ``query`` delegates to the protocol-default explicitly (same move the
    Filesystem adapter makes) because the shared ``count_via_query`` fallback's
    counts via ``self.query`` on the instance.
    """

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    async def load_all(self, scope: str, readers=None) -> list[dict[str, Any]]:
        # Deep-copy so no case can mutate the shared dataset.
        return copy.deepcopy(self._docs)

    async def query(self, scope: str, kind: str, **kwargs):
        async for row in query_via_load_all(self, scope, kind, **kwargs):
            yield row


def _cases() -> list[dict[str, Any]]:
    if not FIXTURE.exists():  # pragma: no cover — skipif already guards
        return []
    return _fixture()["cases"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
async def test_f2_parity_case(case: dict[str, Any]) -> None:
    fx = _fixture()
    src = _FixtureSource(fx["docs"])
    if case["op"] == "query":
        rows = [
            r async for r in query_via_load_all(
                src, "sc", case["kind"],
                filter=case.get("filter"),
                order_by=case.get("order_by"),
                limit=case.get("limit"),
                offset=case.get("offset"),
            )
        ]
        names = [(r.get("metadata") or {}).get("name") for r in rows]
        assert names == case["expected"]
    elif case["op"] == "count":
        res = await count_via_query(
            src, "sc", case["kind"],
            filter=case.get("filter"),
            group_by=case.get("group_by"),
        )
        assert res == case["expected"]
    else:  # pragma: no cover — fixture authoring error
        pytest.fail(f"unknown fixture op {case['op']!r}")


def test_fixture_sanity() -> None:
    """Guard the fixture shape both sides rely on."""
    fx = _fixture()
    kinds = {d["kind"] for d in fx["docs"]}
    assert kinds == {"Story", "Issue"}
    assert len(fx["cases"]) >= 8
