"""MIF interchange projection, locked to a golden case set (s-memory-interchange-verbs).

Runs every case in ``tests/goldens/memory-interchange.json`` against the Python
``to_mif``/``from_mif`` projection. MIF is a WIRE format — it crosses the MCP
and REST faces into other runtimes — so its shape is a compatibility contract,
not an internal detail. A drift here is a breaking change for every consumer.

History: this began as a Py↔TS parity harness and the fixture lived in
``packages/sdk-ts``. The TypeScript SDK was frozen (tag ``sdk-ts-final``);
Python was always the source of truth for these values, so the fixture moved
into this package and the suite stayed.
"""
from __future__ import annotations

import json
from pathlib import Path

from dna.memory.interchange import from_mif, to_mif

FIXTURE = Path(__file__).parent / "goldens" / "memory-interchange.json"

_FX = json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_to_mif_golden():
    for c in _FX["to_mif"]:
        got = to_mif(c["spec"], mif_id=c["mif_id"])
        assert got == c["expected"], c["name"]


def test_from_mif_golden():
    for c in _FX["from_mif"]:
        got = from_mif(c["doc"])
        assert got == c["expected"], c["name"]
