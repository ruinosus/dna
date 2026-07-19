"""Py side of the Py<->TS memory-interchange parity (s-memory-interchange-verbs).

Runs every case in
``packages/sdk-ts/tests/fixtures/memory-interchange-parity.json`` against the
Python ``to_mif``/``from_mif`` projection. The TS twin
(``packages/sdk-ts/tests/memory-interchange-parity.test.ts``) runs the SAME
fixture against its port. A failure on either side is a parity divergence
with an immediate reproduction. Regenerate with
``scripts/gen_memory_interchange_parity.py`` (Python is the source of truth).

Monorepo limitation (documented on purpose, same as ``test_memory_parity.py``):
the fixture lives in sdk-ts and is reached via a ``Path(__file__)``-relative
hop; a standalone sdk-py checkout won't have it, so the module SKIPS rather
than failing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dna.memory.interchange import from_mif, to_mif

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "sdk-ts" / "tests" / "fixtures" / "memory-interchange-parity.json"
)

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason=f"shared parity fixture lives in packages/sdk-ts (monorepo required; {FIXTURE})",
)

_FX = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {}


def test_to_mif_parity():
    for c in _FX["to_mif"]:
        got = to_mif(c["spec"], mif_id=c["mif_id"])
        assert got == c["expected"], c["name"]


def test_from_mif_parity():
    for c in _FX["from_mif"]:
        got = from_mif(c["doc"])
        assert got == c["expected"], c["name"]
