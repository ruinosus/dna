"""Two-planes F2 — the query/count core, locked to a golden case set.

Runs every case in ``tests/goldens/f2-query.json`` against the Python
in-memory query/count core (the ``SourcePort`` protocol-default — the exact
code path the Filesystem adapter delegates to). The cases cover ``filter``,
``order_by``, ``limit``, ``offset`` and ``group_by`` semantics; a change in
any of them reds this suite with an immediate reproduction.

History: this began as a Py↔TS parity harness and the fixture lived in
``packages/sdk-ts``. The TypeScript SDK was frozen (tag ``sdk-ts-final``);
what it was really protecting was the PYTHON query semantics, so the fixture
moved into this package and the suite stayed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from dna.kernel.query.fallback import count_via_query, query_via_load_all

FIXTURE = Path(__file__).parent / "goldens" / "f2-query.json"


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
    """Guard the shape the cases rely on."""
    fx = _fixture()
    kinds = {d["kind"] for d in fx["docs"]}
    assert kinds == {"Story", "Issue"}
    assert len(fx["cases"]) >= 8
