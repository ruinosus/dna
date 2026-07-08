"""Review PR guard (i-133-story-review-pr-guard).

Repo rule: review = PR aberto. `dna sdlc story review <s>` checks for an
open PR on the current git branch via `gh pr list --head` and, when none
exists, blocks unless the explicit escape `--no-pr --reason "<why>"` is
given. The gh lookup is fail-soft (gateway weather must never brick the
transition) — `prs is None` means "couldn't check" and allows with a
warning.
"""
from __future__ import annotations

import subprocess
from unittest import mock

from dna_cli.sdlc_cmd import (
    _gh_open_prs_for_branch,
    review_pr_guard,
)


# ---------------------------------------------------------------------------
# review_pr_guard — pure decision
# ---------------------------------------------------------------------------

def test_allows_when_open_pr_exists() -> None:
    allowed, warns = review_pr_guard([{"number": 307}], no_pr=False, reason=None)
    assert allowed is True
    assert warns == []


def test_blocks_when_no_pr_and_no_escape() -> None:
    allowed, warns = review_pr_guard([], no_pr=False, reason=None)
    assert allowed is False
    assert any("--no-pr" in w for w in warns)


def test_allows_with_no_pr_escape_and_reason() -> None:
    allowed, warns = review_pr_guard([], no_pr=True, reason="PR sai do batch no fim")
    assert allowed is True
    assert any("PR sai do batch" in w for w in warns)


def test_no_pr_escape_requires_reason() -> None:
    allowed, warns = review_pr_guard([], no_pr=True, reason=None)
    assert allowed is False
    assert any("--reason" in w for w in warns)

    allowed, _ = review_pr_guard([], no_pr=True, reason="   ")
    assert allowed is False


def test_fail_soft_when_gh_unavailable() -> None:
    allowed, warns = review_pr_guard(None, no_pr=False, reason=None)
    assert allowed is True
    assert any("gh" in w for w in warns)


# ---------------------------------------------------------------------------
# _gh_open_prs_for_branch — subprocess wrapper (mocked)
# ---------------------------------------------------------------------------

def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr="",
    )


def test_gh_parses_open_prs() -> None:
    with mock.patch("subprocess.run", return_value=_completed('[{"number": 42}]')):
        assert _gh_open_prs_for_branch("fix/x") == [{"number": 42}]


def test_gh_empty_list() -> None:
    with mock.patch("subprocess.run", return_value=_completed("[]")):
        assert _gh_open_prs_for_branch("fix/x") == []


def test_gh_nonzero_exit_is_none() -> None:
    with mock.patch("subprocess.run", return_value=_completed("", returncode=1)):
        assert _gh_open_prs_for_branch("fix/x") is None


def test_gh_timeout_is_none() -> None:
    with mock.patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=3),
    ):
        assert _gh_open_prs_for_branch("fix/x") is None


def test_gh_missing_binary_is_none() -> None:
    with mock.patch("subprocess.run", side_effect=FileNotFoundError):
        assert _gh_open_prs_for_branch("fix/x") is None


def test_gh_garbage_json_is_none() -> None:
    with mock.patch("subprocess.run", return_value=_completed("not json")):
        assert _gh_open_prs_for_branch("fix/x") is None
