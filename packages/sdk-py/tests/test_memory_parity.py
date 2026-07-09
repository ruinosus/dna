"""Py side of the Py↔TS memory-scoring parity (s-memory-verbs).

Runs every case in ``packages/sdk-ts/tests/fixtures/memory-scoring-parity.json``
against the Python pure-scoring core. The TS twin
(``packages/sdk-ts/tests/memory-scoring-parity.test.ts``) runs the SAME fixture
against its port. A failure on either side is a parity divergence with an
immediate reproduction. Regenerate the fixture with
``scripts/gen_memory_parity.py`` (Python is the source of truth for the numbers).

Monorepo limitation (documented on purpose): the fixture lives in sdk-ts and is
reached via a ``Path(__file__)``-relative hop; a standalone sdk-py checkout won't
have it, so the module SKIPS (explicit reason) rather than failing.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from dna.memory.decay import (
    confidence_score_numeric,
    currently_valid,
    ebbinghaus_retention,
    stability_from_spec,
)
from dna.memory.ecphory import EngramRef, score_engram
from dna.memory.encoding_context import time_of_day
from dna.memory.memory_type import classify_memory_type
from dna.memory.retrieval import Memory, rank_memories

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "sdk-ts" / "tests" / "fixtures" / "memory-scoring-parity.json"
)

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason=f"shared parity fixture lives in packages/sdk-ts (monorepo required; {FIXTURE})",
)

_FX = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {}


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def test_ebbinghaus_retention_parity():
    for c in _FX["ebbinghaus_retention"]:
        got = ebbinghaus_retention(c["stability_days"], c["days_since_recall"])
        assert got == pytest.approx(c["expected"], abs=1e-12), c


def test_currently_valid_parity():
    for c in _FX["currently_valid"]:
        got = currently_valid(c["valid_to"], now=_dt(c["now"]))
        assert got == c["expected"], c


def test_stability_from_spec_parity():
    for c in _FX["stability_from_spec"]:
        assert stability_from_spec(c["spec"]) == pytest.approx(c["expected"], abs=1e-12), c


def test_confidence_score_numeric_parity():
    for c in _FX["confidence_score_numeric"]:
        assert confidence_score_numeric(c["spec"]) == pytest.approx(c["expected"], abs=1e-12), c


def test_classify_memory_type_parity():
    for c in _FX["classify_memory_type"]:
        assert classify_memory_type(c["spec"]) == c["expected"], c


def test_time_of_day_parity():
    for c in _FX["time_of_day"]:
        assert time_of_day(datetime(2026, 1, 1, c["hour"])) == c["expected"], c


def test_rank_memories_parity():
    for c in _FX["rank_memories"]:
        mems = [Memory(m["name"], m["spec"]) for m in c["memories"]]
        ranked = rank_memories(mems, c["query"], now=_dt(c["now"]))
        assert [r.name for r in ranked] == c["expected_order"], c
        for r in ranked:
            assert r.score == pytest.approx(c["expected_scores"][r.name], abs=1e-9), (r.name, c)


def test_score_engram_parity():
    for c in _FX["score_engram"]:
        s = score_engram(EngramRef(c["engram"]["name"], c["engram"]["spec"]), c["cue_ctx"])
        assert s.score == pytest.approx(c["expected_score"], abs=1e-9), c
        assert s.matched_dims == c["expected_matched"], c
