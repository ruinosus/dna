"""The dated-spec-field contract — every builder stamps what a reader dates by.

``i-078``: ``build_issue_spec`` wrote description / type / severity / status and
one timeline event, and skipped ``created_at``. Its two siblings
(``build_story_spec`` / ``build_feature_spec``) stamped it, the Issue Kind's
schema declared it, and the digest dates a filed Issue *by* it
(``_digest.build_digest``: ``parse_iso_utc(spec.get("created_at"))`` →
``_in_window`` is False for ``None``). Net effect: **no Issue ever landed in the
digest's ``found`` bucket** — not a windowing edge case, a permanent hole.

The class is "a read surface dates/sorts/filters by a spec field that no write
path stamps". :data:`dna.application.sdlc.DATED_SPEC_FIELDS` names the contract
per Kind; this module holds the SDK's pure builders to it. The CLI half — every
``dna sdlc … create`` verb, which hand-builds specs of its own — lives in
``packages/cli/tests/test_dated_spec_fields_cli.py`` (a test under
``packages/sdk-py/tests`` must never import ``dna_cli``).
"""
from __future__ import annotations

import pytest

from dna.application.sdlc import (
    DATED_SPEC_FIELDS,
    backfill_created_at,
    build_feature_spec,
    build_issue_spec,
    build_story_spec,
    earliest_timeline_at,
    plan_date_repair,
    set_status,
)

_NOW = "2026-07-15T09:30:00+00:00"


#: Kind → a minimal, valid call of the pure builder the shared write core uses.
#: Every Kind the core builds must appear here (asserted below).
_CORE_BUILDERS = {
    "Story": lambda: build_story_spec(
        title=None, description="a story", feature="f-x",
        now=_NOW, actor="mcp", source="mcp",
    ),
    "Issue": lambda: build_issue_spec(
        description="an issue", now=_NOW, actor="mcp", source="mcp",
    ),
    "Feature": lambda: build_feature_spec(
        title="A feature", description="a feature",
        now=_NOW, actor="mcp", source="mcp",
    ),
}


# ── the guard ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", sorted(_CORE_BUILDERS))
def test_core_builder_stamps_every_dated_field(kind):
    """A builder that skips a declared field makes the Kind invisible to the
    surface that dates it. Fail naming the Kind AND the field, so the next
    reader of this failure does not have to re-derive i-078."""
    spec = _CORE_BUILDERS[kind]()
    declared = DATED_SPEC_FIELDS[kind]
    missing = [field for field in declared if not spec.get(field)]
    assert not missing, (
        f"{kind}: the builder omits {missing} — DATED_SPEC_FIELDS declares "
        f"{list(declared)} because a read surface dates/sorts/filters {kind} by "
        f"them. Stamp them in the builder (see build_story_spec) or, if the "
        f"surface genuinely stopped reading the field, drop it from the registry."
    )


def test_every_core_built_kind_is_declared():
    """The registry must not silently lose a Kind the core writes."""
    undeclared = sorted(set(_CORE_BUILDERS) - set(DATED_SPEC_FIELDS))
    assert not undeclared, f"built by the core but absent from the registry: {undeclared}"


# ── i-078 proper: the Issue builder ─────────────────────────────────────────


def test_build_issue_spec_stamps_created_and_updated_at():
    spec = build_issue_spec(
        description="bug here", issue_type="bug", severity="high",
        now=_NOW, actor="mcp", source="mcp",
    )
    assert spec["created_at"] == _NOW
    assert spec["updated_at"] == _NOW


def test_build_issue_spec_accepts_a_title():
    spec = build_issue_spec(
        description="a long description that would be truncated for display",
        title="Digest never lists filed Issues",
        now=_NOW, actor="mcp", source="mcp",
    )
    assert spec["title"] == "Digest never lists filed Issues"


def test_build_issue_spec_omits_title_when_none_is_given():
    """No fabricated title: the Issue schema does not require one and every
    read surface already falls back to the description (``_digest._title``).
    Synthesizing ``description[:80]`` into the document would just duplicate
    the description on disk under a second key."""
    spec = build_issue_spec(
        description="no title supplied", now=_NOW, actor="mcp", source="mcp",
    )
    assert "title" not in spec


# ── the honest repair for documents already on disk ─────────────────────────


def test_earliest_timeline_at_takes_the_minimum_not_the_first_element():
    spec = {"timeline": [
        {"at": "2026-03-02T10:00:00+00:00", "type": "comment"},
        {"at": "2026-03-01T08:00:00+00:00", "type": "status_change"},
    ]}
    assert earliest_timeline_at(spec) == "2026-03-01T08:00:00+00:00"


@pytest.mark.parametrize("timeline", [None, [], [{"type": "comment"}], [{"at": ""}]])
def test_earliest_timeline_at_is_none_without_a_usable_stamp(timeline):
    assert earliest_timeline_at({"timeline": timeline}) is None


def test_backfill_uses_the_first_timeline_event():
    spec = {"status": "open", "timeline": [{"at": "2026-03-01T08:00:00+00:00"}]}
    assert backfill_created_at(spec) is True
    assert spec["created_at"] == "2026-03-01T08:00:00+00:00"


def test_backfill_never_invents_now_when_the_timeline_is_empty():
    """The whole point: a document with no recorded history stays undated
    rather than claiming it was filed today."""
    spec = {"status": "open"}
    assert backfill_created_at(spec) is False
    assert "created_at" not in spec


def test_backfill_leaves_an_existing_created_at_alone():
    spec = {"created_at": "2026-01-01T00:00:00+00:00",
            "timeline": [{"at": "2026-03-01T08:00:00+00:00"}]}
    assert backfill_created_at(spec) is False
    assert spec["created_at"] == "2026-01-01T00:00:00+00:00"


def test_set_status_self_heals_a_legacy_doc_from_its_own_timeline():
    """A pre-fix Issue repairs itself the next time anybody transitions it —
    dated by the event that recorded its filing, never by the transition."""
    import asyncio

    filed_at = "2026-03-01T08:00:00+00:00"
    written: dict = {}

    class _Kernel:
        async def get_document(self, scope, kind, name):
            return {"spec": {"status": "open", "timeline": [
                {"at": filed_at, "type": "status_change", "to": "open"},
            ]}}

        async def write_document(self, scope, kind, name, raw, **_):
            written["raw"] = raw

    asyncio.run(set_status(_Kernel(), "sc", "Issue", "i-001-legacy", "triaged"))
    spec = written["raw"]["spec"]
    assert spec["created_at"] == filed_at
    assert spec["updated_at"] != filed_at   # the transition is its own stamp


# ── the bulk repair planner (`dna sdlc backfill-dates`) ─────────────────────
#
# Deciding the honest value for a document that never recorded when it was
# created. Ranked by how close the signal sits to the event it dates:
#   1. the document's own timeline — written BY the create path, at create time
#   2. the git commit that ADDED the file — an external witness, same day-ish
#   3. nothing — leave it undated and SAY SO
# "Now" is not on the list: it would date every legacy Issue as filed today and
# poison every future digest window, which is the failure i-078 already caused.


def test_repair_prefers_the_documents_own_timeline_over_git():
    fields, provenance = plan_date_repair(
        "Issue",
        {"status": "open", "timeline": [{"at": "2026-03-01T08:00:00+00:00"}]},
        git_added_at="2026-03-05T00:00:00+00:00",
    )
    assert provenance == "timeline"
    assert fields["created_at"] == "2026-03-01T08:00:00+00:00"


def test_repair_falls_back_to_the_commit_that_added_the_file():
    fields, provenance = plan_date_repair(
        "Issue", {"status": "open"}, git_added_at="2026-03-05T00:00:00+00:00",
    )
    assert provenance == "git"
    assert fields["created_at"] == "2026-03-05T00:00:00+00:00"


def test_repair_reports_undatable_rather_than_inventing_now():
    fields, provenance = plan_date_repair("Issue", {"status": "open"})
    assert provenance == "undatable"
    assert fields == {}


def test_repair_is_a_noop_for_a_document_that_already_has_its_stamps():
    fields, provenance = plan_date_repair(
        "Issue",
        {"created_at": "2026-01-01T00:00:00+00:00",
         "updated_at": "2026-02-01T00:00:00+00:00"},
    )
    assert provenance == "complete"
    assert fields == {}


def test_repair_dates_updated_at_by_the_last_recorded_movement():
    fields, _ = plan_date_repair("Issue", {"status": "triaged", "timeline": [
        {"at": "2026-03-01T08:00:00+00:00"},
        {"at": "2026-04-09T17:00:00+00:00"},
    ]})
    assert fields["created_at"] == "2026-03-01T08:00:00+00:00"
    assert fields["updated_at"] == "2026-04-09T17:00:00+00:00"


def test_repair_only_touches_the_fields_the_registry_declares_and_that_are_missing():
    fields, _ = plan_date_repair(
        "Issue",
        {"updated_at": "2026-05-05T00:00:00+00:00",
         "timeline": [{"at": "2026-03-01T08:00:00+00:00"}]},
    )
    assert set(fields) == {"created_at"}


def test_repair_ignores_a_kind_no_read_surface_dates():
    assert plan_date_repair("Roadmap", {"status": "active"}) == ({}, "complete")


# ── canonical identity: does the repair change what the doc IS? ─────────────


def test_backfilled_stamps_do_not_change_the_documents_canonical_digest():
    """The founder needs this stated, not assumed: ``created_at`` /
    ``updated_at`` are in ``KindBase.VOLATILE_SPEC_FIELDS``, so the Kind-aware
    ``canonical_digest`` — the identity source-sync diffs on — is computed over
    a spec with both stripped. Backfilling them leaves every document's
    canonical identity byte-identical; the FS↔Postgres sync sees no drift."""
    from dna.extensions.sdlc import IssueKind

    kind = IssueKind()

    class _Doc:
        kind = "Issue"
        name = "i-001-legacy"

        def __init__(self, spec):
            self.spec = spec

    before = {"description": "d", "type": "bug", "severity": "medium",
              "status": "open", "timeline": [{"at": "2026-03-01T08:00:00+00:00"}]}
    after = {**before, "created_at": "2026-03-01T08:00:00+00:00",
             "updated_at": "2026-03-01T08:00:00+00:00"}

    assert kind.canonical_digest(_Doc(before)) == kind.canonical_digest(_Doc(after))
