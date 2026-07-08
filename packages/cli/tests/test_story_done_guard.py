"""TDD for the story-done guard (i-034-i-sdlc-done-requires-merge).

Done = shipped + accepted. The guard surfaces two honest warnings: (a) marking
done with no shipping commit, and (b) jumping to done without passing through
review (the review→done flow that keeps work-in-review out of limbo).
"""
from __future__ import annotations

from dna_cli.sdlc_cmd import story_done_guard


def test_warns_when_no_commit_and_not_no_commit() -> None:
    warns = story_done_guard("review", commit_ref=None, no_commit=False)
    assert any("commit" in w.lower() for w in warns)


def test_no_commit_flag_silences_commit_warning() -> None:
    warns = story_done_guard("review", commit_ref=None, no_commit=True)
    assert not any("commit de entrega" in w for w in warns)


def test_warns_when_skipping_review() -> None:
    warns = story_done_guard("in-progress", commit_ref="abc1234", no_commit=False)
    assert any("review" in w.lower() for w in warns)


def test_clean_when_review_and_commit() -> None:
    assert story_done_guard("review", commit_ref="abc1234", no_commit=False) == []


def test_clean_when_no_commit_flag_and_review() -> None:
    assert story_done_guard("review", commit_ref=None, no_commit=True) == []


# ── s-sdlc-tests-required-on-done: the HARD test gate predicate ───────────────
from dna_cli.sdlc_cmd import done_blocks_on_missing_tests


def test_gate_blocks_when_code_and_no_passing_run() -> None:
    assert done_blocks_on_missing_tests(
        no_commit=False, allow_no_tests=False, has_passing_run=False
    ) is True


def test_gate_passes_when_a_passing_run_exists() -> None:
    assert done_blocks_on_missing_tests(
        no_commit=False, allow_no_tests=False, has_passing_run=True
    ) is False


def test_gate_escaped_by_allow_no_tests() -> None:
    assert done_blocks_on_missing_tests(
        no_commit=False, allow_no_tests=True, has_passing_run=False
    ) is False


def test_gate_exempt_for_no_commit_story() -> None:
    # Story without code never needs tests.
    assert done_blocks_on_missing_tests(
        no_commit=True, allow_no_tests=False, has_passing_run=False
    ) is False
