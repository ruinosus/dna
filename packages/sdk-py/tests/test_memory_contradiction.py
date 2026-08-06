"""Contradiction detection — the pure half (s-grafo-2-contradicao, degrau 2).

``dna.memory.contradiction`` decides SYNTACTICALLY, with no model anywhere near
it: two declared claims contradict when they agree on subject and predicate,
disagree on object, and their world-time windows share an instant (TOKI,
arXiv:2606.06240 §2.1 — nine of Allen's thirteen base relations). The external
judge (``ContradictionScribe``) is exercised here as a plain callable, proving
the seam without a model, exactly as ``test_memory_merge.py`` does for
``MergeScribe``.

The tests that carry the design (break the implementation and THESE fail first):

* ``test_the_founders_case_livro`` — the acceptance criterion, with the
  founder's own sentences.
* ``test_meets_is_not_a_contradiction`` — a properly superseded memory and its
  successor touch at one instant and must NOT be reported. Without the interval
  test every clean supersession in the workspace becomes a false alarm.
* ``test_repetition_is_not_disagreement`` — the wall between this module and
  ``dna.memory.merge``.
* ``test_general_area_is_not_a_shared_subject`` — the MCP ``remember`` tool
  defaults ``area`` to ``"general"``; without the ``Kind/name`` filter every
  default memory in a workspace shares one "subject".
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dna.memory.contradiction import (
    ASSERTS,
    DENIES,
    Claim,
    claims_contradict,
    contradiction_report,
    intervals_overlap,
    parse_claims,
    referents,
    validate_claims,
)

_NOW = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)


def _mem(summary: str, **extra) -> dict:
    return {"summary": summary, **extra}


def _claim(memory: str, predicate: str, obj, **extra) -> Claim:
    return Claim(
        memory=memory, subject="KindDefinition/livro",
        predicate=predicate, object=obj, **extra,
    )


# ── validate_claims: the door's refusal ─────────────────────────────────────


def test_validate_fills_the_default_polarity_and_keeps_the_value():
    out = validate_claims([{"predicate": "approval", "object": "pending"}])
    assert out == [{"predicate": "approval", "object": "pending", "polarity": ASSERTS}]


def test_validate_accepts_absent_claims():
    assert validate_claims(None) == []
    assert validate_claims([]) == []


@pytest.mark.parametrize("bad, needle", [
    ("not a list", "must be a list"),
    ([["a"]], "claims[0] must be an object"),
    ([{"object": "x"}], "claims[0].predicate is required"),
    ([{"predicate": "  "}], "claims[0].predicate is required"),
    ([{"predicate": "p", "subject": ""}], "claims[0].subject"),
    ([{"predicate": "p", "polarity": "maybe"}], "claims[0].polarity"),
    ([{"predicate": "p", "object": {"nested": 1}}], "claims[0].object"),
    ([{"predicate": "p", "objekt": "typo"}], "unknown field(s) ['objekt']"),
    ([{"predicate": "ok"}, {"predicate": "p", "polarity": 1}], "claims[1].polarity"),
])
def test_validate_refuses_and_says_where(bad, needle):
    """The message names the INDEX and the FIELD — a caller told only "invalid"
    has to guess which of five claims it was."""
    with pytest.raises(ValueError) as exc:
        validate_claims(bad)
    assert needle in str(exc.value)


# ── referents: the declared subject, never the lexical one ──────────────────


def test_general_area_is_not_a_shared_subject():
    """``remember(area="general")`` is the MCP default and copies itself into
    ``source_refs``. Counting it as a referent would put every default memory in
    one group and call it a subject."""
    spec = _mem("x", area="general", source_refs=["general"])
    assert referents(spec) == frozenset()


def test_referents_take_kind_slash_name_and_claim_subjects():
    spec = _mem(
        "x", area="KindDefinition/livro", source_refs=["Story/s-1", "general"],
        claims=[{"predicate": "p", "subject": "Feature/f-x"}],
    )
    assert referents(spec) == frozenset(
        {"kinddefinition/livro", "story/s-1", "feature/f-x"}
    )


# ── parse_claims: lenient on read, defaults that do work ────────────────────


def test_subject_defaults_to_the_memory_referent_with_the_authors_case():
    spec = _mem("x", area="KindDefinition/Livro",
                claims=[{"predicate": "approval", "object": "pending"}])
    (claim,) = parse_claims("rem-a", spec)
    # display keeps the author's capitalisation; matching is casefolded.
    assert claim.subject == "KindDefinition/Livro"
    assert claim.subject_key == "kinddefinition/livro"


def test_claim_inherits_the_memorys_bitemporal_window():
    spec = _mem("x", area="Story/s-1", valid_from="2026-01-01T00:00:00+00:00",
                valid_to="2026-02-01T00:00:00+00:00",
                claims=[{"predicate": "status", "object": "todo"}])
    (claim,) = parse_claims("rem-a", spec)
    assert claim.valid_from == "2026-01-01T00:00:00+00:00"
    assert claim.valid_to == "2026-02-01T00:00:00+00:00"


def test_parse_never_raises_on_a_stored_malformation():
    """This reads DOCUMENTS. A malformed claim that got past both doors must be
    SKIPPED, never able to take a consolidation pass down."""
    spec = _mem("x", area="Story/s-1", claims=[
        "a string", {"no": "predicate"}, {"predicate": "p", "polarity": "maybe"},
        {"predicate": "p", "object": {"nested": 1}},
        {"predicate": "good", "object": "v"},
    ])
    claims = parse_claims("rem-a", spec)
    assert [c.predicate for c in claims] == ["good"]


def test_an_unanchored_claim_compares_with_nothing():
    spec = _mem("x", area="general", claims=[{"predicate": "p", "object": "v"}])
    assert parse_claims("rem-a", spec) == ()


# ── intervals: Allen, nine of thirteen ──────────────────────────────────────


def test_open_windows_always_overlap():
    assert intervals_overlap(None, None, None, None)


@pytest.mark.parametrize("a_from, a_to, b_from, b_to, expected", [
    # before / after — the two that share no instant
    ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z",
     "2026-03-01T00:00:00Z", "2026-04-01T00:00:00Z", False),
    ("2026-03-01T00:00:00Z", "2026-04-01T00:00:00Z",
     "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", False),
    # meets / met-by — touching at one instant, closed-open ⇒ NOT overlapping
    ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z",
     "2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z", False),
    ("2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z",
     "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", False),
    # overlaps / during / starts / finishes / equals — the nine
    ("2026-01-01T00:00:00Z", "2026-03-01T00:00:00Z",
     "2026-02-01T00:00:00Z", "2026-04-01T00:00:00Z", True),
    ("2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z",
     "2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z", True),
    ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z",
     "2026-01-01T00:00:00Z", "2026-03-01T00:00:00Z", True),
    ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z",
     "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", True),
    # an open end reaches forever
    ("2026-01-01T00:00:00Z", None, "2030-01-01T00:00:00Z", None, True),
])
def test_interval_overlap_is_allens_predicate(a_from, a_to, b_from, b_to, expected):
    assert intervals_overlap(a_from, a_to, b_from, b_to) is expected


def test_an_unparseable_boundary_reads_as_open_not_as_closed():
    """A typo'd timestamp must not silently STOP a real contradiction from being
    reported — "this end is not pinned" is the honest reading."""
    assert intervals_overlap("garbage", None, "2026-01-01T00:00:00Z", None)


# ── the syntactic verdict ───────────────────────────────────────────────────


def test_different_object_is_the_contradiction():
    a = _claim("rem-a", "approval", "pending")
    b = _claim("rem-b", "approval", "approved")
    assert claims_contradict(a, b) == "object"


def test_case_and_number_shape_are_not_disagreements():
    assert claims_contradict(
        _claim("rem-a", "approval", "Approved"),
        _claim("rem-b", "approval", "approved"),
    ) is None
    assert claims_contradict(
        _claim("rem-a", "count", 2), _claim("rem-b", "count", 2.0),
    ) is None


def test_a_bool_normalizes_as_a_bool_and_not_as_a_number():
    """``isinstance(True, int)`` is true in Python, so a bool that fell through
    to the numeric branch would stringify as ``"True"`` — which disagrees with
    the ``"true"`` an author typed as text, inventing a contradiction out of two
    spellings of the same value. And it must still differ from ``1``."""
    assert claims_contradict(
        _claim("rem-a", "approved", True), _claim("rem-b", "approved", "true"),
    ) is None
    assert claims_contradict(
        _claim("rem-a", "approved", True), _claim("rem-b", "approved", 1),
    ) == "object"


def test_opposite_polarity_on_the_same_object_is_a_contradiction():
    a = _claim("rem-a", "approval", "approved", polarity=ASSERTS)
    b = _claim("rem-b", "approval", "approved", polarity=DENIES)
    assert claims_contradict(a, b) == "polarity"


def test_asserting_one_value_and_denying_another_is_consistent():
    """Affirming X and denying Y (X≠Y) is coherent. A detector that flagged it
    would train its readers to dismiss it."""
    a = _claim("rem-a", "approval", "approved", polarity=ASSERTS)
    b = _claim("rem-b", "approval", "pending", polarity=DENIES)
    assert claims_contradict(a, b) is None


def test_denying_two_different_values_is_consistent():
    a = _claim("rem-a", "approval", "approved", polarity=DENIES)
    b = _claim("rem-b", "approval", "pending", polarity=DENIES)
    assert claims_contradict(a, b) is None


def test_an_existence_claim_and_a_valued_one_are_not_comparable():
    a = _claim("rem-a", "approval", None)
    b = _claim("rem-b", "approval", "approved")
    assert claims_contradict(a, b) is None


def test_two_existence_claims_of_opposite_polarity_contradict():
    a = _claim("rem-a", "approval", None, polarity=ASSERTS)
    b = _claim("rem-b", "approval", None, polarity=DENIES)
    assert claims_contradict(a, b) == "polarity"


def test_different_subject_or_predicate_never_contradicts():
    a = _claim("rem-a", "approval", "pending")
    assert claims_contradict(a, _claim("rem-b", "status", "approved")) is None
    assert claims_contradict(a, Claim(
        memory="rem-b", subject="KindDefinition/outro",
        predicate="approval", object="approved",
    )) is None


def test_a_claim_never_contradicts_itself():
    a = _claim("rem-a", "approval", "pending")
    assert claims_contradict(a, a) is None


def test_meets_is_not_a_contradiction():
    """The bi-temporal case that decides whether this feature is usable: a
    memory invalidated at exactly the instant its successor becomes valid is a
    clean SUCCESSION. Drop the interval test and every properly superseded
    memory in the workspace turns into a false alarm."""
    a = _claim("rem-a", "approval", "pending",
               valid_from="2026-01-01T00:00:00Z", valid_to="2026-06-01T00:00:00Z")
    b = _claim("rem-b", "approval", "approved",
               valid_from="2026-06-01T00:00:00Z", valid_to=None)
    assert claims_contradict(a, b) is None


# ── the report ──────────────────────────────────────────────────────────────


_REASON = "a concrete reason long enough for the affect validator to accept it"


def _livro_members() -> list[tuple[str, dict]]:
    """The founder's living proof (2026-08-05), verbatim."""
    return [
        ("rem-livro-pendente", _mem(
            "O Kind Livro ainda precisa de aprovação para virar registrado.",
            area="KindDefinition/livro", affect="ominous", affect_reason=_REASON,
            created_at="2026-07-20T10:00:00+00:00",
            claims=[{"predicate": "approval", "object": "pending",
                     "polarity": ASSERTS}],
        )),
        ("rem-livro-aprovado", _mem(
            "O Kind Livro foi aprovado pelo founder no portal.",
            area="KindDefinition/livro", affect="triumph", affect_reason=_REASON,
            created_at="2026-08-05T10:00:00+00:00",
            claims=[{"predicate": "approval", "object": "approved",
                     "polarity": ASSERTS}],
        )),
    ]


def test_the_founders_case_livro():
    """THE acceptance criterion. Two memories the system believes at the same
    time; one says the Kind still needs approval, the other says it was
    approved. Before this module, both were served and neither was flagged."""
    report = contradiction_report(_livro_members(), now=_NOW)

    assert len(report["contradictions"]) == 1
    conflict = report["contradictions"][0]
    assert conflict["subject"] == "KindDefinition/livro"
    assert conflict["predicate"] == "approval"
    assert conflict["names"] == ["rem-livro-aprovado", "rem-livro-pendente"]
    assert conflict["decided_by"] == "rule"
    assert [p["reason"] for p in conflict["pairs"]] == ["object"]
    # the evidence carries BOTH sides — a human decides, so a human must see.
    pair = conflict["pairs"][0]
    assert {pair["a_claim"]["object"], pair["b_claim"]["object"]} == {
        "pending", "approved"
    }
    # PRESENTED, never applied.
    assert conflict["proposal"]["strategy"] == "await_confirmation"


def test_the_proposal_prefers_transaction_time_over_the_authored_clock():
    """``created_at`` is authored — a correction filed today can claim to
    predate what it corrects. ``recorded_at`` is when the STORE came to believe
    it, and it is the clock the survivor election must use."""
    members = _livro_members()
    # The authored clock LIES: the stale memory claims to be the newer one.
    members[0][1]["created_at"] = "2026-08-05T23:00:00+00:00"
    stamps = {
        "rem-livro-pendente": "2026-07-20T10:00:00+00:00",
        "rem-livro-aprovado": "2026-08-05T10:00:00+00:00",
    }
    conflict = contradiction_report(
        members, recorded_at=stamps, now=_NOW,
    )["contradictions"][0]
    assert conflict["proposal"]["basis"] == "recorded_at"
    assert conflict["proposal"]["suggested_keep"] == "rem-livro-aprovado"
    assert conflict["proposal"]["suggested_supersede"] == ["rem-livro-pendente"]


def test_without_transaction_time_the_basis_says_so():
    conflict = contradiction_report(_livro_members(), now=_NOW)["contradictions"][0]
    assert conflict["proposal"]["basis"] == "spec"


def test_an_approximate_winner_is_refused_and_an_approximate_loser_is_not():
    """A pruned first version makes the stamp an UPPER bound — it reads newer
    than the truth. Sound in one direction only: losing on it holds (the truth
    is older still), winning on it rests on the error itself."""
    members = _livro_members()
    stamps = {
        "rem-livro-pendente": "2026-08-05T23:00:00+00:00",   # bound, and it WINS
        "rem-livro-aprovado": "2026-08-05T10:00:00+00:00",
    }
    conflict = contradiction_report(
        members, recorded_at=stamps, recorded_at_approximate=["rem-livro-pendente"],
        now=_NOW,
    )["contradictions"][0]
    assert conflict["proposal"]["basis"] == "spec"

    # The same bound on the LOSER decides nothing it is not entitled to decide.
    stamps["rem-livro-pendente"] = "2026-07-20T10:00:00+00:00"
    conflict = contradiction_report(
        members, recorded_at=stamps, recorded_at_approximate=["rem-livro-pendente"],
        now=_NOW,
    )["contradictions"][0]
    assert conflict["proposal"]["basis"] == "recorded_at"
    assert conflict["proposal"]["suggested_keep"] == "rem-livro-aprovado"


def test_a_partial_stamp_set_falls_back_rather_than_ranking_on_half_a_clock():
    stamps = {"rem-livro-aprovado": "2026-08-05T10:00:00+00:00"}
    conflict = contradiction_report(
        _livro_members(), recorded_at=stamps, now=_NOW,
    )["contradictions"][0]
    assert conflict["proposal"]["basis"] == "spec"


def test_repetition_is_not_disagreement():
    """The wall between this module and ``dna.memory.merge``. Two memories that
    say the SAME thing overlap lexically and are a merge candidate; they are not
    a contradiction, and nothing here may report them as one."""
    members = [
        ("rem-a", _mem("deploy broke cache invalidation kernel",
                       area="Feature/kernel",
                       claims=[{"predicate": "state", "object": "broken"}])),
        ("rem-b", _mem("deploy broke cache invalidation kernel again",
                       area="Feature/kernel",
                       claims=[{"predicate": "state", "object": "broken"}])),
    ]
    assert contradiction_report(members, now=_NOW)["contradictions"] == []


def test_undecided_names_what_the_rule_could_not_judge():
    """Prose disagreement with no claims: reported as UNDECIDED, never as
    agreement and never as a contradiction."""
    members = [
        ("rem-a", _mem("O Kind Livro ainda precisa de aprovação.",
                       area="KindDefinition/livro")),
        ("rem-b", _mem("O Kind Livro foi aprovado.",
                       area="KindDefinition/livro")),
    ]
    report = contradiction_report(members, now=_NOW)
    assert report["contradictions"] == []
    (undecided,) = report["undecided"]
    assert undecided["referent"] == "kinddefinition/livro"
    assert undecided["names"] == ["rem-a", "rem-b"]
    assert "prose" in undecided["reason"]


def test_a_decided_conflict_is_not_repeated_as_undecided():
    report = contradiction_report(_livro_members(), now=_NOW)
    assert report["undecided"] == []


def test_a_lone_memory_is_never_undecided():
    members = [("rem-a", _mem("x", area="KindDefinition/livro"))]
    assert contradiction_report(members, now=_NOW)["undecided"] == []


# ── the external judge ──────────────────────────────────────────────────────


def _undecided_members() -> list[tuple[str, dict]]:
    return [
        ("rem-a", _mem("O Kind Livro ainda precisa de aprovação.",
                       area="KindDefinition/livro")),
        ("rem-b", _mem("O Kind Livro foi aprovado.",
                       area="KindDefinition/livro")),
    ]


def test_the_scribe_can_decide_what_the_rule_cannot():
    def scribe(group):
        assert len(group) == 2  # the group's specs, sorted by name
        return {"contradicts": True, "reason": "one says pending, one says approved",
                "predicate": "approval"}

    report = contradiction_report(_undecided_members(), scribe=scribe, now=_NOW)
    assert report["undecided"] == []
    (conflict,) = report["contradictions"]
    assert conflict["decided_by"] == "scribe"
    assert conflict["reason"].startswith("one says")
    assert conflict["proposal"]["strategy"] == "await_confirmation"


def test_a_scribe_that_says_no_leaves_the_group_undecided():
    report = contradiction_report(
        _undecided_members(), scribe=lambda g: {"contradicts": False}, now=_NOW,
    )
    assert report["contradictions"] == []
    assert len(report["undecided"]) == 1


def test_a_raising_scribe_never_breaks_the_pass_and_is_named():
    def scribe(group):
        raise RuntimeError("model timeout")

    report = contradiction_report(_undecided_members(), scribe=scribe, now=_NOW)
    assert report["contradictions"] == []
    (undecided,) = report["undecided"]
    assert undecided["scribe_error"] == "RuntimeError: model timeout"


def test_a_scribe_with_no_verdict_is_silence_not_a_yes():
    report = contradiction_report(
        _undecided_members(), scribe=lambda g: {"reason": "hmm"}, now=_NOW,
    )
    assert report["contradictions"] == []
    assert report["undecided"][0]["scribe_error"] == "scribe returned no verdict"


def test_the_rules_verdict_is_distinguishable_from_the_models():
    """A reader must be able to tell the syntactic verdict from the modelled
    one — they carry different warranties."""
    report = contradiction_report(
        _livro_members() + _undecided_members(),
        scribe=lambda g: {"contradicts": True, "reason": "judged"},
        now=_NOW,
    )
    assert {c["decided_by"] for c in report["contradictions"]} == {"rule", "scribe"}
