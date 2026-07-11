"""Pure-unit coverage for the retrospective digest aggregator.

``dna_cli._digest`` is kernel-free by design (the CLI command owns the impure
edges), so the whole aggregation contract is testable with plain dicts here —
no source, no session. Covers window resolution (``--since`` forms), timeline
bucketing (completed/decided/found/progressed/artifacts), the CURRENT-state
"needs your attention" scan, dedupe, and the RAG/verdict rollup.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dna_cli._digest import (
    build_digest,
    parse_iso_utc,
    resolve_since,
)

NOW = datetime(2026, 7, 11, 18, 0, 0, tzinfo=timezone.utc)


def _at(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


# ─── window resolution ────────────────────────────────────────────────

def test_resolve_since_default_is_24h():
    since, label = resolve_since(None, now=NOW)
    assert since == NOW - timedelta(hours=24)
    assert "24h" in label


@pytest.mark.parametrize("spec,secs", [
    ("90m", 90 * 60), ("24h", 24 * 3600), ("3d", 3 * 86400), ("2w", 2 * 604800),
])
def test_resolve_since_relative_spans(spec, secs):
    since, _ = resolve_since(spec, now=NOW)
    assert since == NOW - timedelta(seconds=secs)


def test_resolve_since_iso_timestamp():
    since, _ = resolve_since("2026-07-10T00:00:00Z", now=NOW)
    assert since == datetime(2026, 7, 10, tzinfo=timezone.utc)


def test_resolve_since_last_digest_uses_prior_timestamp():
    prior = NOW - timedelta(hours=5)
    since, label = resolve_since("last-digest", now=NOW, last_digest_at=prior)
    assert since == prior
    assert "last digest" in label


def test_resolve_since_last_digest_falls_back_when_none():
    since, label = resolve_since("last-digest", now=NOW, last_digest_at=None)
    assert since == NOW - timedelta(hours=24)
    assert "no prior digest" in label


def test_resolve_since_bad_input_raises():
    with pytest.raises(ValueError):
        resolve_since("garbage", now=NOW)


def test_parse_iso_handles_z_and_naive():
    assert parse_iso_utc("2026-07-11T12:00:00Z") == datetime(
        2026, 7, 11, 12, tzinfo=timezone.utc)
    assert parse_iso_utc("2026-07-11T12:00:00") == datetime(
        2026, 7, 11, 12, tzinfo=timezone.utc)
    assert parse_iso_utc("nonsense") is None
    assert parse_iso_utc(None) is None


# ─── aggregation buckets ──────────────────────────────────────────────

def _digest(docs, **kw):
    return build_digest(
        docs=docs, since=NOW - timedelta(hours=24), until=NOW,
        since_label="last 24h", scope="s", **kw,
    )


def test_completed_captures_terminal_in_window_only():
    docs = [
        {"kind": "Story", "name": "s-recent", "spec": {
            "status": "done", "title": "Recent",
            "timeline": [{"type": "status_change", "to": "done", "at": _at(2),
                          "commit_ref": "abc"}],
        }},
        {"kind": "Story", "name": "s-old", "spec": {
            "status": "done", "title": "Old",
            "timeline": [{"type": "status_change", "to": "done", "at": _at(48)}],
        }},
    ]
    dg = _digest(docs)
    names = [r["name"] for r in dg["completed"]]
    assert names == ["s-recent"]
    assert dg["completed"][0]["commit_ref"] == "abc"


def test_adr_acceptance_is_decision_not_completed():
    docs = [{"kind": "ADR", "name": "adr-x", "spec": {
        "status": "accepted", "title": "Pivot", "decision": "Go vendor-neutral",
        "created_at": _at(3),
        "timeline": [{"type": "status_change", "to": "accepted", "at": _at(3)}],
    }}]
    dg = _digest(docs)
    assert dg["completed"] == []
    assert [r["name"] for r in dg["decided"]] == ["adr-x"]
    assert "vendor-neutral" in dg["decided"][0]["summary"]


def test_decision_events_surface_in_decided():
    docs = [{"kind": "Story", "name": "s-a", "spec": {
        "status": "in-progress", "title": "A",
        "timeline": [{"type": "decision", "summary": "optei por X porque Y",
                      "at": _at(1)}],
    }}]
    dg = _digest(docs)
    assert dg["decided"][0]["summary"].startswith("optei por X")


def test_found_dedupes_kaizen_event_against_kaizen_doc():
    body = "SDLC gap: cite resolves Reference only"
    docs = [
        {"kind": "Story", "name": "s-a", "spec": {
            "status": "done", "timeline": [
                {"type": "kaizen", "summary": body, "at": _at(2)}]}},
        {"kind": "Kaizen", "name": "kz-001", "spec": {
            "status": "observed", "body": body, "created_at": _at(2)}},
    ]
    dg = _digest(docs)
    # Only one entry, and the canonical Kaizen doc wins (docs sorted first).
    assert len(dg["found"]) == 1
    assert dg["found"][0]["name"] == "kz-001"


def test_progressed_tracks_feature_epic_movement():
    docs = [{"kind": "Feature", "name": "f-x", "spec": {
        "status": "in-development", "title": "Feat",
        "timeline": [{"type": "status_change", "to": "in-development", "at": _at(4)}],
    }}]
    dg = _digest(docs)
    assert [r["name"] for r in dg["progressed"]] == ["f-x"]


def test_progressed_excludes_items_that_completed():
    docs = [{"kind": "Feature", "name": "f-x", "spec": {
        "status": "done", "title": "Feat",
        "timeline": [
            {"type": "status_change", "to": "in-development", "at": _at(4)},
            {"type": "status_change", "to": "done", "at": _at(1)},
        ],
    }}]
    dg = _digest(docs)
    assert [r["name"] for r in dg["completed"]] == ["f-x"]
    assert dg["progressed"] == []


def test_artifacts_from_artifact_produced_events():
    docs = [{"kind": "Story", "name": "s-a", "spec": {
        "status": "done", "timeline": [
            {"type": "artifact_produced", "kind": "TestGuide",
             "name": "tg-a", "at": _at(1)}]}}]
    dg = _digest(docs)
    assert dg["artifacts"][0] == {
        "kind": "TestGuide", "name": "tg-a", "work_item": "Story/s-a",
        "at": _at(1),
    }


def test_releases_filtered_to_window():
    tags = [
        {"name": "v1.0.0", "at": _at(2)},
        {"name": "v0.9.0", "at": _at(72)},
    ]
    dg = _digest([], tags=tags)
    assert [r["tag"] for r in dg["releases"]] == ["v1.0.0"]


# ─── "needs your attention" — current-state, window-independent ───────

def test_attention_blocked_recovers_reason_and_is_not_windowed():
    docs = [{"kind": "Story", "name": "s-b", "spec": {
        "status": "blocked", "title": "Blocked one",
        "timeline": [{"type": "status_change", "to": "blocked",
                      "reason": "waiting on infra", "at": _at(200)}],
    }}]
    dg = _digest(docs)
    blocked = dg["attention"]["blocked"]
    assert blocked[0]["name"] == "s-b"
    assert blocked[0]["reason"] == "waiting on infra"
    assert dg["rag_status"] == "red"


def test_attention_review_matches_open_prs():
    docs = [{"kind": "Story", "name": "s-rev", "spec": {
        "status": "review", "title": "In review",
        "timeline": [{"type": "pr_opened",
                      "pr_url": "https://github.com/o/r/pull/9", "at": _at(3)}]}}]
    prs = [{"number": 9, "title": "t", "headRefName": "feat/x",
            "url": "https://github.com/o/r/pull/9"}]
    dg = _digest(docs, open_prs=prs)
    rev = dg["attention"]["review_awaiting"]
    assert rev[0]["name"] == "s-rev"
    assert rev[0]["prs"][0]["number"] == 9
    assert dg["rag_status"] == "amber"


def test_attention_owner_decisions_and_open_questions():
    docs = [
        {"kind": "ADR", "name": "adr-p", "spec": {
            "status": "proposed", "title": "Proposed"}},
        {"kind": "Spike", "name": "spk-q", "spec": {
            "status": "in-progress", "question_to_answer": "which db?"}},
    ]
    dg = _digest(docs)
    assert [r["name"] for r in dg["attention"]["owner_decisions"]] == ["adr-p"]
    assert dg["attention"]["open_questions"][0]["question"] == "which db?"


def test_clean_board_is_green_with_nothing_pending():
    docs = [{"kind": "Story", "name": "s-done", "spec": {
        "status": "done",
        "timeline": [{"type": "status_change", "to": "done", "at": _at(1)}]}}]
    dg = _digest(docs)
    assert dg["counts"]["attention"] == 0
    assert dg["rag_status"] == "green"
    assert "nada precisa" in dg["verdict"]


def test_counts_and_verdict_rollup():
    docs = [
        {"kind": "Story", "name": "s1", "spec": {"status": "done", "timeline": [
            {"type": "status_change", "to": "done", "at": _at(1)}]}},
        {"kind": "Story", "name": "s2", "spec": {"status": "blocked", "timeline": [
            {"type": "status_change", "to": "blocked", "reason": "x", "at": _at(2)}]}},
    ]
    dg = _digest(docs)
    assert dg["counts"]["completed"] == 1
    assert dg["counts"]["attention"] == 1
    assert "1 precisa" in dg["verdict"]
