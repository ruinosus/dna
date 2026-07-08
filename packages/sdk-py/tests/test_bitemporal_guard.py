"""Bi-temporal invalidation guard (i-046) — never resurrect a superseded memory."""
from __future__ import annotations

from dna.kernel.bitemporal_guard import preserve_bitemporal_invalidation


def test_preserves_valid_to_when_incoming_drops_it():
    incoming = {"summary": "x", "surface_count": 0}  # a maintenance re-write
    existing = {"summary": "x", "valid_to": "2026-06-02T00:00:00+00:00",
                "superseded_by_memory": "sem-x"}
    changed = preserve_bitemporal_invalidation(incoming, existing)
    assert changed is True
    assert incoming["valid_to"] == "2026-06-02T00:00:00+00:00"
    assert incoming["superseded_by_memory"] == "sem-x"


def test_noop_when_existing_not_invalidated():
    incoming = {"summary": "x"}
    existing = {"summary": "x"}  # no valid_to
    assert preserve_bitemporal_invalidation(incoming, existing) is False
    assert "valid_to" not in incoming


def test_respects_incoming_valid_to():
    # the consolidation close-out write carries its OWN valid_to — don't override
    incoming = {"valid_to": "2026-07-01T00:00:00+00:00", "superseded_by_memory": "sem-new"}
    existing = {"valid_to": "2026-06-02T00:00:00+00:00", "superseded_by_memory": "sem-old"}
    assert preserve_bitemporal_invalidation(incoming, existing) is False
    assert incoming["valid_to"] == "2026-07-01T00:00:00+00:00"
    assert incoming["superseded_by_memory"] == "sem-new"


def test_none_existing_is_safe():
    incoming = {"summary": "x"}
    assert preserve_bitemporal_invalidation(incoming, None) is False
