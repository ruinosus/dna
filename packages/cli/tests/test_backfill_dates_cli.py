"""``dna sdlc backfill-dates`` — the repair for documents filed before i-078.

Two layers, like the rest of the SDLC CLI:

* the git witness is PURE parsing (``parse_git_log`` / ``index_by_doc_name``),
  tested against real ``git log`` output shapes with no repo involved;
* the verb itself runs against the in-memory fake session, with the git probe
  monkeypatched — so what is asserted is what lands in the store.

The date-choosing policy itself is not re-tested here; it lives in
``dna.application.sdlc.plan_date_repair`` and is covered in
``packages/sdk-py/tests/test_dated_spec_fields.py``.
"""
from __future__ import annotations

import pytest

from dna_cli.sdlc import backfill_dates as B
from dna_cli.sdlc_cmd import sdlc

_SCOPE = "dna-development"

_GIT_LOG = (
    "\x002026-03-01T08:00:00+00:00\n"
    "\n"
    "issues/i-001-legacy.yaml\n"
    "issues/i-002-other.yaml\n"
    "\x002026-04-09T17:00:00+00:00\n"
    "\n"
    "issues/i-001-legacy.yaml\n"
)


def _legacy_issue(name: str, timeline: list[dict] | None = None) -> dict:
    spec: dict = {
        "description": f"filed before the fix ({name})",
        "type": "bug", "severity": "medium", "status": "open",
    }
    if timeline is not None:
        spec["timeline"] = timeline
    return {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "Issue", "metadata": {"name": name}, "spec": spec,
    }


# ── the git witness (pure) ──────────────────────────────────────────────────


def test_parse_git_log_takes_first_appearance_as_added_and_last_as_touched():
    parsed = B.parse_git_log(_GIT_LOG)
    assert parsed["issues/i-001-legacy.yaml"] == (
        "2026-03-01T08:00:00+00:00", "2026-04-09T17:00:00+00:00",
    )
    # Only ever touched once → added and last-touched coincide.
    assert parsed["issues/i-002-other.yaml"] == (
        "2026-03-01T08:00:00+00:00", "2026-03-01T08:00:00+00:00",
    )


def test_parse_git_log_is_empty_for_empty_output():
    assert B.parse_git_log("") == {}


def test_parse_git_log_normalizes_the_authors_local_offset_to_utc():
    """``%aI`` is the author's local time. Left as-is, a backfilled stamp would
    not compare against the UTC stamps every other write path produces."""
    parsed = B.parse_git_log(
        "\x002026-07-25T08:56:13-03:00\n\nissues/i-004-local.yaml\n"
    )
    assert parsed["issues/i-004-local.yaml"] == (
        "2026-07-25T11:56:13+00:00", "2026-07-25T11:56:13+00:00",
    )


def test_index_by_doc_name_handles_flat_files_and_bundle_directories():
    indexed = B.index_by_doc_name({
        "issues/i-001-legacy.yaml": ("2026-03-01T08:00:00+00:00",
                                     "2026-04-09T17:00:00+00:00"),
        "plans/plan-x/PLAN.md": ("2026-02-01T00:00:00+00:00",
                                 "2026-02-02T00:00:00+00:00"),
        "plans/plan-x/plan.yaml": ("2026-01-15T00:00:00+00:00",
                                   "2026-03-20T00:00:00+00:00"),
    })
    assert indexed["i-001-legacy"] == ("2026-03-01T08:00:00+00:00",
                                       "2026-04-09T17:00:00+00:00")
    # A bundle's entries collapse onto the document: earliest add, latest touch.
    assert indexed["plan-x"] == ("2026-01-15T00:00:00+00:00",
                                 "2026-03-20T00:00:00+00:00")


# ── the verb ────────────────────────────────────────────────────────────────


@pytest.fixture
def no_git(monkeypatch):
    monkeypatch.setattr(B, "git_dates_for_scope", lambda scope: {})


def test_backfill_dates_stamps_from_the_documents_own_timeline(
    sdlc_runner, store, no_git,
):
    store[(_SCOPE, "Issue", "i-001-legacy")] = _legacy_issue(
        "i-001-legacy", [{"at": "2026-03-01T08:00:00+00:00", "type": "status_change"}],
    )
    result = sdlc_runner.invoke(sdlc, ["backfill-dates"])
    assert result.exit_code == 0, result.output
    spec = store[(_SCOPE, "Issue", "i-001-legacy")]["spec"]
    assert spec["created_at"] == "2026-03-01T08:00:00+00:00"
    assert spec["updated_at"] == "2026-03-01T08:00:00+00:00"
    assert "[timeline]" in result.output


def test_backfill_dates_falls_back_to_git(sdlc_runner, store, monkeypatch):
    monkeypatch.setattr(B, "git_dates_for_scope", lambda scope: {
        "i-002-no-timeline": ("2026-03-05T00:00:00+00:00",
                              "2026-03-06T00:00:00+00:00"),
    })
    store[(_SCOPE, "Issue", "i-002-no-timeline")] = _legacy_issue("i-002-no-timeline")
    result = sdlc_runner.invoke(sdlc, ["backfill-dates"])
    assert result.exit_code == 0, result.output
    spec = store[(_SCOPE, "Issue", "i-002-no-timeline")]["spec"]
    assert spec["created_at"] == "2026-03-05T00:00:00+00:00"
    assert spec["updated_at"] == "2026-03-06T00:00:00+00:00"
    assert "[git]" in result.output


def test_backfill_dates_leaves_an_undatable_document_alone_and_says_so(
    sdlc_runner, store, no_git,
):
    store[(_SCOPE, "Issue", "i-003-orphan")] = _legacy_issue("i-003-orphan")
    result = sdlc_runner.invoke(sdlc, ["backfill-dates"])
    assert result.exit_code == 0, result.output
    spec = store[(_SCOPE, "Issue", "i-003-orphan")]["spec"]
    assert "created_at" not in spec, "invented a date for an undatable document"
    assert "undatable" in result.output
    assert "1 left undatable" in result.output


def test_backfill_dates_dry_run_writes_nothing(sdlc_runner, store, no_git):
    store[(_SCOPE, "Issue", "i-001-legacy")] = _legacy_issue(
        "i-001-legacy", [{"at": "2026-03-01T08:00:00+00:00", "type": "status_change"}],
    )
    result = sdlc_runner.invoke(sdlc, ["backfill-dates", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "created_at" not in store[(_SCOPE, "Issue", "i-001-legacy")]["spec"]
    assert "nothing written" in result.output


def test_backfill_dates_is_idempotent(sdlc_runner, store, no_git):
    store[(_SCOPE, "Issue", "i-001-legacy")] = _legacy_issue(
        "i-001-legacy", [{"at": "2026-03-01T08:00:00+00:00", "type": "status_change"}],
    )
    assert sdlc_runner.invoke(sdlc, ["backfill-dates"]).exit_code == 0
    before = dict(store[(_SCOPE, "Issue", "i-001-legacy")]["spec"])
    second = sdlc_runner.invoke(sdlc, ["backfill-dates"])
    assert second.exit_code == 0, second.output
    assert store[(_SCOPE, "Issue", "i-001-legacy")]["spec"] == before
    assert "0 repaired" in second.output


def test_backfill_dates_rejects_a_kind_no_read_surface_dates(sdlc_runner, no_git):
    result = sdlc_runner.invoke(sdlc, ["backfill-dates", "--kind", "Roadmap"])
    assert result.exit_code != 0
    assert "not dated by any read surface" in result.output
