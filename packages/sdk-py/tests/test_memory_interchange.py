"""Unit tests for ``dna.memory.interchange`` (s-memory-interchange-verbs).

Pure functions, no kernel/network — every test constructs plain dicts and
asserts on plain dicts. Covers:

  1. every §2-mapped field surviving an Engram -> MIF -> Engram round trip,
     INCLUDING the ``extensions.x-dna`` vault, byte-identically;
  2. the §6 id-stability decision (``resolve_or_mint_mif_id`` mint-once +
     reuse, the pin surviving both directions);
  3. relationship-shaped fields (``source_refs``, ``superseded_by_memory``,
     ``homophonic_links``) round-tripping through ``relationships[]`` with NO
     vault entry (the divergence this story found against the design table);
  4. importing the REAL MIF spec fixtures used by ``test_mif_memory_kind.py``
     (``tests/parity-fixtures/mif/memories/*``) — market-fidelity: proving
     ``from_mif`` against genuine MIF examples, not only DNA-authored data.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from dna.memory.interchange import from_mif, resolve_or_mint_mif_id, to_mif

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_BASE = REPO_ROOT / "tests" / "parity-fixtures" / "mif" / "memories"

_REASON = "a concrete reason long enough for the affect validator to accept in full"


def _full_engram_spec() -> dict:
    """An Engram spec exercising EVERY field this module maps, including the
    full x-dna vault set."""
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


# ─────────────────────────── round trip: every field ──────────────────────


def test_full_round_trip_preserves_every_mapped_field():
    spec = _full_engram_spec()
    doc = to_mif(spec, mif_id="test-uuid-1234")
    back = from_mif(doc)

    for field in (
        "area", "surface_when", "source_refs", "affect", "affect_reason",
        "affect_evidence_refs", "summary", "body", "relevance_decay_seed",
        "surface_count", "confidence_score", "cues_history", "revisions",
        "tags", "owner", "visibility", "memory_type", "valid_from",
        "valid_to", "superseded_by_memory", "homophonic_links", "created_at",
        "last_surfaced",
    ):
        assert back[field] == spec[field], f"field {field!r} did not survive the round trip"

    # encoding_context round-trips minus/plus the mif_id pin.
    assert back["encoding_context"]["mif_id"] == "test-uuid-1234"
    for k, v in spec["encoding_context"].items():
        assert back["encoding_context"][k] == v


def test_x_dna_vault_present_on_export():
    spec = _full_engram_spec()
    doc = to_mif(spec, mif_id="id-1")
    vault = doc["extensions"]["x-dna"]
    for field in (
        "confidence_score", "relevance_decay_seed", "surface_count",
        "cues_history", "affect", "affect_reason", "visibility",
        "affect_evidence_refs", "surface_when", "revisions", "last_surfaced",
    ):
        assert field in vault, f"{field!r} missing from the x-dna vault"
    assert "encoding_context" in vault
    assert "mif_id" not in vault["encoding_context"], (
        "mif_id must NOT be duplicated into the vaulted encoding_context — "
        "it is reconstructed from doc['id'] on import"
    )


def test_homophonic_links_round_trip_via_relationships_not_vault():
    """The divergence this story found: resonance_score fits natively in
    relationships[].strength — no vault entry needed."""
    spec = _full_engram_spec()
    doc = to_mif(spec, mif_id="id-1")
    vault = doc.get("extensions", {}).get("x-dna", {})
    assert "homophonic_links" not in vault

    rel = next(r for r in doc["relationships"] if r["type"] == "relates-to")
    assert rel["target"] == "rem-neighbor"
    assert rel["strength"] == pytest.approx(0.73)
    assert rel["metadata"]["basis"] == "co-area"

    back = from_mif(doc)
    assert back["homophonic_links"] == spec["homophonic_links"]


def test_source_refs_and_supersession_round_trip_via_relationships():
    spec = _full_engram_spec()
    doc = to_mif(spec, mif_id="id-1")
    rel_types = {r["type"] for r in doc["relationships"]}
    assert "derived-from" in rel_types
    assert "supersedes" in rel_types
    assert doc["provenance"]["wasDerivedFrom"] == spec["source_refs"]
    assert doc["provenance"]["wasAttributedTo"] == "claude-code"

    back = from_mif(doc)
    assert back["source_refs"] == spec["source_refs"]
    assert back["superseded_by_memory"] == "rem-successor"
    assert back["owner"] == "claude-code"


def test_type_and_title_and_content_map_1to1():
    spec = _full_engram_spec()
    doc = to_mif(spec, mif_id="id-1")
    assert doc["type"] == "procedural"
    assert doc["title"] == spec["summary"]
    assert doc["content"] == spec["body"]
    assert doc["created"] == spec["created_at"]


def test_temporal_maps_valid_from_to_validFrom_validUntil():
    spec = _full_engram_spec()
    doc = to_mif(spec, mif_id="id-1")
    assert doc["temporal"] == {
        "validFrom": spec["valid_from"],
        "validUntil": spec["valid_to"],
    }


def test_namespace_area_round_trip_is_reversible_not_lossy():
    """Guards against the design table's lossy lowercase-slug example —
    round-trip fidelity requires EXACT area recovery, including case and the
    embedded `/`."""
    spec = _full_engram_spec()
    spec["area"] = "Feature/Kernel-Cache"  # mixed case, on purpose
    doc = to_mif(spec, mif_id="id-1")
    assert doc["namespace"] == "_procedural/Feature/Kernel-Cache"
    back = from_mif(doc)
    assert back["area"] == "Feature/Kernel-Cache"


def test_memory_type_inferred_when_absent():
    spec = _full_engram_spec()
    del spec["memory_type"]
    spec["summary"] = "Always deep-copy before mutating."  # a rule word
    doc = to_mif(spec, mif_id="id-1")
    assert doc["type"] == "procedural"  # classify_memory_type heuristic


# ─────────────────────────── §6 id stability ───────────────────────────────


def test_resolve_or_mint_mif_id_mints_when_absent():
    spec = {"summary": "x"}
    mif_id, minted = resolve_or_mint_mif_id(spec, id_factory=lambda: "fresh-id")
    assert mif_id == "fresh-id"
    assert minted is True


def test_resolve_or_mint_mif_id_reuses_pinned_id():
    spec = {"summary": "x", "encoding_context": {"mif_id": "already-pinned"}}
    mif_id, minted = resolve_or_mint_mif_id(spec, id_factory=lambda: "should-not-be-called")
    assert mif_id == "already-pinned"
    assert minted is False


def test_reexport_of_the_same_engram_produces_the_same_id():
    spec = _full_engram_spec()
    mif_id_1, minted_1 = resolve_or_mint_mif_id(spec, id_factory=lambda: "minted-once")
    assert minted_1 is True
    doc_1 = to_mif(spec, mif_id=mif_id_1)

    # The CLI pins the minted id back onto the Engram's encoding_context —
    # simulate that here.
    spec["encoding_context"]["mif_id"] = mif_id_1

    mif_id_2, minted_2 = resolve_or_mint_mif_id(spec, id_factory=lambda: "should-not-be-called-again")
    assert mif_id_2 == mif_id_1
    assert minted_2 is False
    doc_2 = to_mif(spec, mif_id=mif_id_2)
    assert doc_1["id"] == doc_2["id"] == "minted-once"


def test_import_pins_the_docs_own_id_for_a_stable_reexport():
    doc = {
        "id": "foreign-id-42",
        "type": "semantic",
        "content": "some fact",
        "created": "2026-07-01T00:00:00+00:00",
    }
    spec = from_mif(doc)
    assert spec["encoding_context"]["mif_id"] == "foreign-id-42"

    mif_id, minted = resolve_or_mint_mif_id(spec)
    assert mif_id == "foreign-id-42"
    assert minted is False

    reexported = to_mif(spec, mif_id=mif_id)
    assert reexported["id"] == "foreign-id-42"


def test_import_pin_self_heals_against_a_stale_vaulted_mif_id():
    """If a copied doc's x-dna.encoding_context carries a DIFFERENT mif_id
    than doc['id'] (e.g. hand-edited, or copy-pasted from another memory),
    the doc's own id always wins on import — never the vaulted copy."""
    doc = {
        "id": "real-id",
        "type": "semantic",
        "content": "fact",
        "created": "2026-07-01T00:00:00+00:00",
        "extensions": {"x-dna": {"encoding_context": {"mif_id": "stale-other-id"}}},
    }
    spec = from_mif(doc)
    assert spec["encoding_context"]["mif_id"] == "real-id"


# ─────────────────────────── foreign-import defaults ──────────────────────


def test_from_mif_fills_honest_defaults_for_a_foreign_doc():
    doc = {
        "id": "ext-1",
        "type": "semantic",
        "content": "The team prefers dark mode.",
        "created": "2026-07-01T00:00:00+00:00",
    }
    spec = from_mif(doc)
    assert spec["affect"] == "surprise"
    assert len(spec["affect_reason"]) >= 20
    assert spec["surface_when"] == ["feature_touched"]
    assert spec["source_refs"] == ["mif:ext-1"]
    assert spec["area"] == "imported/mif"
    assert spec["summary"] == "The team prefers dark mode."


def test_unrecognized_relationship_types_are_dropped_not_erroring():
    doc = {
        "id": "ext-2",
        "type": "semantic",
        "content": "fact",
        "created": "2026-07-01T00:00:00+00:00",
        "relationships": [{"type": "implements", "target": "/semantic/spec.md"}],
    }
    spec = from_mif(doc)  # must not raise
    assert "implements" not in str(spec.get("homophonic_links", ""))


# ─────────────────────────── real MIF spec fixtures ────────────────────────


def _split_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "expected a frontmatter block"
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]


def test_from_mif_on_real_minimal_preference_fixture():
    marker = FIXTURE_BASE / "minimal-preference" / "MEMORY.md"
    fm, body = _split_frontmatter(marker.read_text())
    doc = {**fm, "content": body.strip()}

    spec = from_mif(doc)
    assert spec["memory_type"] == "semantic"
    assert spec["body"] == "User prefers dark mode for all applications."
    assert spec["encoding_context"]["mif_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert spec["created_at"] == "2026-01-15T10:30:00Z"
    # No x-dna vault on this fixture -> honest defaults kick in.
    assert spec["affect"] == "surprise"
    assert spec["source_refs"] == ["mif:550e8400-e29b-41d4-a716-446655440000"]


def test_from_mif_on_real_decision_fixture_preserves_relationships_and_vault():
    marker = FIXTURE_BASE / "decision-react-over-vue" / "MEMORY.md"
    fm, body = _split_frontmatter(marker.read_text())
    doc = {**fm, "content": body.strip()}

    spec = from_mif(doc)
    assert spec["area"] == "decisions"  # _semantic/decisions -> decisions
    assert spec["summary"] == "Use React over Vue for the dashboard"
    assert spec["tags"] == ["frontend", "architecture"]
    assert spec["superseded_by_memory"] == "/semantic/vue-exploration.md"
    assert spec["homophonic_links"] == [{"target_name": "/semantic/frontend-architecture.md"}]
    # x-dna vault on this fixture carries confidence_score + visibility.
    assert spec["confidence_score"] == 0.92
    assert spec["visibility"] == "shared"
    assert spec["encoding_context"]["mif_id"] == "decision-react-over-vue"


def test_real_decision_fixture_round_trips_back_to_mif():
    marker = FIXTURE_BASE / "decision-react-over-vue" / "MEMORY.md"
    fm, body = _split_frontmatter(marker.read_text())
    doc = {**fm, "content": body.strip()}

    spec = from_mif(doc)
    mif_id, _ = resolve_or_mint_mif_id(spec)
    reexported = to_mif(spec, mif_id=mif_id)

    assert reexported["id"] == "decision-react-over-vue"
    assert reexported["type"] == "semantic"
    assert reexported["namespace"] == "_semantic/decisions"
    assert reexported["tags"] == ["frontend", "architecture"]
    rel_types = {r["type"] for r in reexported["relationships"]}
    # The fixture has no `derived-from` relationship and no `provenance`, so
    # from_mif's honest fallback (`source_refs = ["mif:<id>"]`) round-trips
    # back out as a synthetic derived-from relationship on re-export — on
    # top of the fixture's own real `supersedes`/`relates-to`.
    assert rel_types == {"derived-from", "supersedes", "relates-to"}
