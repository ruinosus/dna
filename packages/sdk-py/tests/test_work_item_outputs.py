"""TDD for resolve_work_item_outputs (s-produces-schema-resolver).

A work item is a hub: its outputs are the union of the explicit `produces[]`
relationship and the legacy per-Kind back-refs (spec_refs, research_refs,
html_artifacts, follow_ups, a linked Plan via story_ref, a Engram via
source_refs). Deduped by (kind, name). Zero migration — old docs with only
back-refs still surface their outputs.
"""
from __future__ import annotations

from dna.extensions.sdlc.work_item_outputs import resolve_work_item_outputs


def _keys(outs):
    return {(o["kind"], o["name"]) for o in outs}


def test_empty_when_nothing() -> None:
    assert resolve_work_item_outputs("s-foo", {"status": "todo"}) == []


def test_explicit_produces_returned() -> None:
    outs = resolve_work_item_outputs("s-foo", {
        "produces": [
            {"kind": "Research", "name": "rsh-x", "role": "investigation"},
            {"kind": "HtmlArtifact", "name": "ha-y"},
        ],
    })
    assert _keys(outs) == {("Research", "rsh-x"), ("HtmlArtifact", "ha-y")}
    research = next(o for o in outs if o["kind"] == "Research")
    assert research["role"] == "investigation"
    assert research["source"] == "produces"


def test_legacy_back_refs_unioned() -> None:
    outs = resolve_work_item_outputs("s-foo", {
        "spec_refs": ["spec-a"],
        "research_refs": ["rsh-b"],
        "html_artifacts": ["ha-c"],
    })
    assert _keys(outs) == {("Spec", "spec-a"), ("Research", "rsh-b"), ("HtmlArtifact", "ha-c")}
    assert all(o["source"] == "legacy" for o in outs)


def test_linked_plan_and_lesson_from_params() -> None:
    outs = resolve_work_item_outputs(
        "s-foo",
        {"status": "done"},
        plans=[{"name": "plan-s-foo", "spec": {"story_ref": "s-foo"}}],
        lessons=[{"name": "rem-foo", "spec": {"source_refs": ["Story/s-foo"]}}],
    )
    assert ("Plan", "plan-s-foo") in _keys(outs)
    assert ("Engram", "rem-foo") in _keys(outs)


def test_lesson_matches_any_work_item_kind() -> None:
    # A Spike's lesson points back via "Spike/<name>" (not Story/).
    outs = resolve_work_item_outputs(
        "s-spike-x",
        {},
        lessons=[{"name": "rem-z", "spec": {"source_refs": ["Spike/s-spike-x"]}}],
    )
    assert ("Engram", "rem-z") in _keys(outs)


def test_dedup_produces_wins_over_legacy() -> None:
    outs = resolve_work_item_outputs("s-foo", {
        "produces": [{"kind": "Plan", "name": "plan-s-foo", "role": "explicit"}],
    }, plans=[{"name": "plan-s-foo", "spec": {"story_ref": "s-foo"}}])
    plan_entries = [o for o in outs if o["kind"] == "Plan" and o["name"] == "plan-s-foo"]
    assert len(plan_entries) == 1
    assert plan_entries[0]["source"] == "produces"  # explicit wins


def test_follow_ups_as_outputs() -> None:
    outs = resolve_work_item_outputs("s-spike", {
        "follow_up_story": "s-next",
        "follow_up_adr": "adr-1",
        "follow_up_spec": "spec-1",
    })
    assert ("Story", "s-next") in _keys(outs)
    assert ("ADR", "adr-1") in _keys(outs)
    assert ("Spec", "spec-1") in _keys(outs)  # spike → design Spec shows in OUTPUTS
