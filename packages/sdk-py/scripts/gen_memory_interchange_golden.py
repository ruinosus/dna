"""Regenerate the memory-interchange golden fixture (s-memory-interchange-verbs).

The fixture (``packages/sdk-py/tests/goldens/memory-interchange.json``) freezes
the canonical ``to_mif``/``from_mif`` outputs of the Engram<->MIF projection,
asserted by ``tests/test_memory_interchange_golden.py``.

MIF is a WIRE format that crosses the MCP and REST faces into other runtimes,
so a diff here is a compatibility change for every consumer — review it, do
not just commit it. Mirrors the sibling ``gen_memory_scoring_golden.py``
convention exactly.

Run from ``packages/sdk-py``:  ``python scripts/gen_memory_interchange_golden.py``
"""
from __future__ import annotations

import json
from pathlib import Path

from dna.memory.interchange import from_mif, to_mif

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "goldens" / "memory-interchange.json"

_REASON = "a concrete reason long enough for the affect validator to accept in full"


def _full_engram_spec() -> dict:
    return {
        "area": "Feature/kernel",
        "surface_when": ["feature_touched", "cycle_open"],
        "source_refs": ["Feature/kernel", "WorkflowEvent/wf-1"],
        "affect": "regret",
        "affect_reason": _REASON,
        "affect_evidence_refs": ["rem-abc123", "verdict-xyz"],
        "summary": "Always deep-copy the L2 cache before mutating.",
        "body": "# Lesson\n\nThe L2 cache hands back a shared ref — deep-copy before mutating.",
        "relevance_decay_seed": 0.9,
        "surface_count": 3,
        "confidence_score": 4.2,
        "cues_history": [{"at": "2026-07-01T10:00:00+00:00", "cue": "cache mutation", "actor": "claude-code"}],
        "revisions": [{"at": "2026-07-02T10:00:00+00:00", "by": "claude-code", "delta": "clarified wording"}],
        "tags": ["kernel", "cache"],
        "owner": "claude-code",
        "visibility": "shared",
        "memory_type": "procedural",
        "valid_from": "2026-07-01T00:00:00+00:00",
        "valid_to": "2026-08-01T00:00:00+00:00",
        "superseded_by_memory": "rem-successor",
        "encoding_context": {
            "area": "Feature/kernel",
            "affect": "regret",
            "co_topics": ["kernel", "cache"],
            "source_refs": ["Feature/kernel"],
            "time_of_day": "afternoon",
            "day_of_week": "Wednesday",
            "engraphed_by": "semon-scribe",
        },
        "homophonic_links": [
            {"target_name": "rem-neighbor", "resonance_score": 0.73, "basis": "co-area"},
        ],
        "created_at": "2026-06-30T09:00:00+00:00",
        "last_surfaced": "2026-07-03T11:00:00+00:00",
    }


def _minimal_engram_spec() -> dict:
    return {
        "area": "general",
        "surface_when": ["feature_touched"],
        "source_refs": ["Feature/x"],
        "affect": "triumph",
        "summary": "A minimal memory.",
        "created_at": "2026-07-01T00:00:00+00:00",
    }


def build() -> dict:
    fx: dict = {
        "_note": (
            "Golden fixture for dna.memory.interchange (to_mif/from_mif). "
            "Regenerate via packages/sdk-py/scripts/gen_memory_interchange_golden.py"
        )
    }

    full_spec = _full_engram_spec()
    minimal_spec = _minimal_engram_spec()

    fx["to_mif"] = [
        {"name": "full", "spec": full_spec, "mif_id": "test-uuid-1234", "expected": to_mif(full_spec, mif_id="test-uuid-1234")},
        {"name": "minimal", "spec": minimal_spec, "mif_id": "min-id", "expected": to_mif(minimal_spec, mif_id="min-id")},
    ]

    foreign_doc = {
        "id": "ext-1",
        "type": "semantic",
        "content": "The team prefers dark mode.",
        "created": "2026-07-01T00:00:00+00:00",
    }
    dna_doc = to_mif(full_spec, mif_id="test-uuid-1234")

    fx["from_mif"] = [
        {"name": "foreign", "doc": foreign_doc, "expected": from_mif(foreign_doc)},
        {"name": "dna_authored", "doc": dna_doc, "expected": from_mif(dna_doc)},
    ]

    return fx


def main() -> None:
    fx = build()
    FIXTURE.write_text(json.dumps(fx, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE} ({FIXTURE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
