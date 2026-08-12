"""The DNAP conformance suite, tested the only way a conformance suite can be.

A suite that has never failed is a suite nobody has checked. Running it against
a server that passes proves that it RUNS; it does not prove that it CHECKS. So
the bulk of this file is mutation: for each defect the specification names,
``tests/dnap_stub.py`` implements it, and the test asserts that the case which
owns that rule ends up in ``report.failed`` — by name.

Three properties beyond the per-case mutants, each guarding a way this suite
could quietly stop being worth anything:

* ``test_a_server_that_errors_on_everything_fails_the_positive_control`` — every
  "must refuse" case in the suite would PASS against a server that answers
  nothing. The positive control is what makes that server fail instead.
* ``test_every_skip_says_what_it_left_unchecked`` — "did not run" must never be
  legible as "passed".
* ``test_unverified_is_not_a_pass_and_not_a_skip`` — a server that declines the
  fault hooks does not thereby earn a green on §8.5.
"""
from __future__ import annotations

import pytest

from dna.testing import (
    DnapCaseNotApplicable,
    DnapRuleUnverified,
    DnapSpecGap,
    dnap_conformance_suite,
    run_dnap_conformance,
)
from dna.testing.dnap_conformance import _Session, _harness  # noqa: PLC2701

from dnap_stub import (  # noqa: E402
    ACCEPT_DERIVED_METADATA,
    ANSWER_NOTIFICATIONS,
    BARE_VALIDATION_ERROR,
    DEGRADED_WITHOUT_REASON,
    ECHO_SELECT_BUT_NARROW,
    EMPTY_ON_UNSERVED_CHANNEL,
    EMPTY_ON_UNSERVED_KIND,
    ERROR_ON_EVERYTHING,
    FOREIGN_CURSOR_IS_EXHAUSTION,
    HIDDEN_KIND_ON_CHANNEL,
    IGNORE_IFMATCH,
    LIST_ALWAYS_EMPTY,
    MODEL_IS_A_VENDOR_ID,
    NARROW_IS_A_POST_FILTER,
    NO_BATCH,
    NOTIFICATION_CARRIES_THE_BODY,
    PAGES_DROP_ROWS,
    RESOLVE_BLANK_ON_MISSING,
    RESOLVE_LEAKS_HOST_CONCERNS,
    REVISION_MOVES_BETWEEN_PAGES,
    SEARCH_HAS_A_RELEVANCE_FLOOR,
    SEARCH_HIDES_THE_NOTICE,
    SEARCH_ONE_NOTE_ONLY,
    SELECT_IS_A_HINT,
    SUBSTITUTE_CHANNEL,
    SUBSTITUTE_TENANT,
    UNKNOWN_METHOD_IS_A_RESULT,
    DnapStubServer,
    stub_harness,
)


# ---------------------------------------------------------------------------
# the conformant server
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", dnap_conformance_suite(stub_harness()), ids=lambda c: c.name,
)
async def test_conformant_stub_passes_every_case(case):
    try:
        await case.run()
    except DnapSpecGap as gap:
        # A hole in the DOCUMENT, not in the server. Reported as an xfail so it
        # stays visible in every CI run with its question attached: a spec gap
        # that quietly became a skip would be a spec gap nobody closes.
        pytest.xfail(str(gap))


@pytest.mark.asyncio
async def test_the_report_is_clean_for_a_conformant_server():
    report = await run_dnap_conformance(stub_harness())
    report.raise_if_failed()
    assert report.ok, report.summary()
    assert not report.failed
    assert not report.unverified
    # The one member of §6.4 rule 2 the spec leaves unnamed. It is a finding
    # against the DOCUMENT, and a conformant server does not make it go away.
    assert [n for n, _ in report.spec_gaps] == ["min_similarity_discloses_its_effect"]


# ---------------------------------------------------------------------------
# mutants — one per rule. `case` must be in report.failed when `mutation` is on.
# ---------------------------------------------------------------------------

MUTANTS = [
    # §3 — scope is an address
    (EMPTY_ON_UNSERVED_CHANNEL, "unserved_channel_is_channel_not_served"),
    (SUBSTITUTE_CHANNEL, "unserved_channel_is_never_substituted"),
    (SUBSTITUTE_TENANT, "unserved_tenant_overlay_is_not_the_base"),
    # §8.2 — the vocabulary
    (EMPTY_ON_UNSERVED_KIND, "unadvertised_kind_is_kind_not_served"),
    (EMPTY_ON_UNSERVED_KIND, "unadvertised_kind_is_not_an_empty_collection"),
    (HIDDEN_KIND_ON_CHANNEL, "channel_vocabulary_never_exceeds_the_advertised_one"),
    (UNKNOWN_METHOD_IS_A_RESULT, "unknown_method_is_method_not_found"),
    # §6.2 rule 1 — select is a contract
    (ECHO_SELECT_BUT_NARROW, "select_full_never_echoes_a_narrower_shape"),
    (SELECT_IS_A_HINT, "unhonourable_select_is_invalid_params"),
    # §6.2 rules 2 & 3 — pagination
    (REVISION_MOVES_BETWEEN_PAGES, "revision_is_constant_across_pages"),
    (PAGES_DROP_ROWS, "pages_neither_duplicate_nor_drop"),
    (FOREIGN_CURSOR_IS_EXHAUSTION, "foreign_cursor_is_an_error_not_exhaustion"),
    # §5 / §6.2 — write
    (IGNORE_IFMATCH, "stale_ifmatch_is_revision_conflict"),
    (BARE_VALIDATION_ERROR, "validation_failure_names_path_and_rule"),
    (ACCEPT_DERIVED_METADATA, "derived_metadata_on_write_is_refused"),
    # §7/§8.5 — the central rule
    (LIST_ALWAYS_EMPTY, "an_empty_collection_is_falsifiable"),
    # §2 — framing
    (NO_BATCH, "batch_is_supported"),
    (ANSWER_NOTIFICATIONS, "notification_gets_no_response"),
    # §6.3 — resolution
    (RESOLVE_LEAKS_HOST_CONCERNS, "resolution_carries_no_host_concerns"),
    (MODEL_IS_A_VENDOR_ID, "resolved_model_is_a_coordinate"),
    (RESOLVE_BLANK_ON_MISSING, "resolving_an_unknown_name_is_an_error"),
    # §6.4 — the five search rules
    (SEARCH_HIDES_THE_NOTICE, "search_envelope_declares_ranked_not_filtered"),
    (SEARCH_HAS_A_RELEVANCE_FLOOR, "search_ships_no_relevance_floor"),
    (SEARCH_ONE_NOTE_ONLY, "two_notes_travel"),
    (NARROW_IS_A_POST_FILTER, "narrow_applies_where_candidates_are_chosen"),
    (DEGRADED_WITHOUT_REASON, "degraded_carries_a_reason"),
    # §6.5 — notifications
    (NOTIFICATION_CARRIES_THE_BODY,
     "change_notification_carries_the_fact_not_the_document"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation,case_name", MUTANTS, ids=lambda v: v if isinstance(v, str) else v,
)
async def test_each_mutation_is_caught_by_its_case(mutation, case_name):
    """The heart of this file: a rule the suite does not CATCH is a rule the
    suite does not have, however well it reads."""
    report = await run_dnap_conformance(stub_harness(mutation))
    failed = dict(report.failed)
    assert case_name in failed, (
        f"mutation {mutation!r} was NOT caught by {case_name!r}.\n"
        f"  failed:     {sorted(failed)}\n"
        f"  passed:     {sorted(report.passed)}\n"
        f"  skipped:    {[n for n, _ in report.skipped]}\n"
        f"  unverified: {[n for n, _ in report.unverified]}"
    )


@pytest.mark.asyncio
async def test_a_server_that_errors_on_everything_fails_the_positive_control():
    """⭐ The tautology guard, tested.

    A server that answers every request with an error satisfies every "must
    refuse" assertion in this suite by accident. The positive control is the
    reason it does not sail through — and the refusal cases must fail with it,
    not pass around it.
    """
    report = await run_dnap_conformance(stub_harness(ERROR_ON_EVERYTHING))
    failed = dict(report.failed)
    assert "positive_control_a_valid_listing_succeeds" in failed
    for refusal_case in (
        "unserved_channel_is_channel_not_served",
        "unadvertised_kind_is_kind_not_served",
        "unknown_method_is_method_not_found",
    ):
        assert refusal_case in failed, (
            f"{refusal_case!r} PASSED against a server that errors on everything — "
            f"which is exactly the tautology the positive control exists to "
            f"prevent. passed={sorted(report.passed)}"
        )
    # What MAY still pass is only what this server still does correctly: the
    # envelope and the handshake. Anything that claims something about CONTENT
    # passing here would mean the suite read a refusal as an answer.
    framing_and_handshake = {
        "envelope_is_jsonrpc_2", "batch_is_supported",
        "initialize_advertises_the_connection", "advertised_kinds_are_a_vocabulary",
    }
    leaked = set(report.passed) - framing_and_handshake
    assert not leaked, (
        f"{sorted(leaked)} passed against a server that answers nothing but errors. "
        f"Every one of those is a claim about content that was never observed."
    )


# ---------------------------------------------------------------------------
# the outcome vocabulary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wave_two_cases_skip_with_an_explicit_reason():
    """A wave-1 server (no resolve, no search) must leave every wave-2 case NOT
    RUN — and every one of those skips has to name the obligation it left
    unchecked, or the report reads like a pass."""
    report = await run_dnap_conformance(
        stub_harness(capabilities=("write",), hooks=False))
    skipped = dict(report.skipped)
    for wave_two in (
        "resolve_returns_the_runtime_neutral_shape",
        "resolution_carries_no_host_concerns",
        "search_envelope_declares_ranked_not_filtered",
        "narrow_applies_where_candidates_are_chosen",
        "min_similarity_is_the_callers_policy",
    ):
        assert wave_two in skipped, (
            f"{wave_two!r} did not report as NOT RUN on a wave-1 server: "
            f"failed={dict(report.failed)} passed={report.passed}")
        reason = skipped[wave_two]
        assert reason.startswith("NOT RUN —"), reason
        assert "UNCHECKED:" in reason, (
            f"the skip for {wave_two!r} does not say what went unchecked: {reason}")
        assert "wave 2" in reason


def test_a_skip_cannot_be_constructed_without_a_reason():
    """The structural half: an unexplained skip is a ValueError, not a skip."""
    with pytest.raises(ValueError):
        DnapCaseNotApplicable(missing="", unchecked="something")
    with pytest.raises(ValueError):
        DnapCaseNotApplicable(missing="something", unchecked="   ")
    skip = DnapCaseNotApplicable(missing="no write capability",
                                 unchecked="that [] is falsifiable")
    assert "NOT RUN — no write capability" in str(skip)
    assert "UNCHECKED: that [] is falsifiable" in str(skip)


@pytest.mark.asyncio
async def test_unverified_is_not_a_pass_and_not_a_skip():
    """⭐ §8.5 is the rule that cost the reference implementation the most, and it
    is not observable from outside. A server that supplies no fault hook must not
    be able to bank a green on it by being untestable."""
    report = await run_dnap_conformance(stub_harness(hooks=False))
    unverified = dict(report.unverified)
    assert "induced_store_failure_is_an_error" in unverified
    assert "search_unavailable_is_never_empty_hits" in unverified
    assert "partial_resolution_is_resolution_incomplete" in unverified
    assert "expired_cursor_is_cursor_expired" in unverified
    assert "break_store" in unverified["induced_store_failure_is_an_error"]

    assert not report.ok, "a report with unverified obligations is not 'ok'"
    with pytest.raises(AssertionError, match="UNVERIFIED"):
        report.raise_if_failed()
    # and never quietly filed as a skip
    assert "induced_store_failure_is_an_error" not in dict(report.skipped)


@pytest.mark.asyncio
async def test_the_induced_failure_case_catches_the_empty_collection():
    """⭐ The rule §7 puts above its own error table, with the hook supplied and
    the store broken: `[]` where an error belongs."""
    from dna.testing.dnap_conformance import (
        _case_induced_store_failure_is_an_error,  # noqa: PLC2701
    )

    class _BreaksIntoEmpty(DnapStubServer):
        def _rows(self, channel, kind):
            if self.store_broken:
                return []          # the defect, verbatim
            return super()._rows(channel, kind)

    async def factory():
        from dna.testing import DnapHarness
        server = _BreaksIntoEmpty(())
        return DnapHarness(endpoint=server.handle, break_store=server.break_store)

    harness = await _harness(factory)
    session = _Session(harness)
    await session.initialize()
    with pytest.raises(AssertionError, match="FAILURE wearing the shape of a finding"):
        await _case_induced_store_failure_is_an_error(session)


@pytest.mark.asyncio
async def test_the_spec_gap_is_reported_and_is_not_a_pass():
    """§6.4 rule 2's disclosure count has no field name in the spec. The suite
    files the hole rather than inventing one — and a filed hole is not a pass."""
    report = await run_dnap_conformance(stub_harness())
    gaps = dict(report.spec_gaps)
    assert "min_similarity_discloses_its_effect" in gaps
    assert "min_similarity_discloses_its_effect" not in report.passed
    assert "§6.4 rule 2" in gaps["min_similarity_discloses_its_effect"]

    gap = DnapSpecGap(section="§X", question="what?")
    assert not isinstance(gap, DnapRuleUnverified)
    assert isinstance(gap, AssertionError)


# ---------------------------------------------------------------------------
# the suite freezes the QUESTION, not the ANSWER
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_server_that_grows_its_vocabulary_still_passes():
    """A suite that asserted "exactly N Kinds" or "exactly M methods" would break
    on a spec that grew, for a reason that has nothing to do with conformance."""
    class _Roomier(DnapStubServer):
        def _initialize(self):
            hello = super()._initialize()
            hello["kinds"] = [*hello["kinds"], "ConformanceFuture"]
            hello["capabilities"]["somethingNewInTwoPointOh"] = {}
            hello["serverExtension"] = {"anything": True}
            return hello

    async def factory():
        return _Roomier(()).handle

    report = await run_dnap_conformance(factory)
    assert not report.failed, report.failed
