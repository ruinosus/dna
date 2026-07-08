"""Tests for the `dna sdlc story start` plan gate (s-story-start-plan-gate).

The gate enforces a plan-of-attack before a Story can go in-progress — inline
(--plan), a linked Plan (--plan-doc), or a conscious skip (--no-plan
--skip-reason). These tests cover the two enforcement *rejections*, which fire
BEFORE any source write (no session needed): the validations are pure.
"""
from __future__ import annotations

from click.testing import CliRunner

from dna_cli import sdlc_cmd


def test_no_plan_requires_skip_reason() -> None:
    # --no-plan without --skip-reason is rejected (skip must be justified).
    r = CliRunner().invoke(
        sdlc_cmd.sdlc,
        ["story", "start", "s-x", "--no-plan", "--scope", "dna-development"],
    )
    assert r.exit_code != 0
    assert "skip-reason" in r.output


def test_start_without_any_plan_flag_blocked_noninteractive() -> None:
    # No plan flag + non-interactive (CliRunner stdin is not a TTY) → blocked
    # with the three explicit options, before touching the source.
    r = CliRunner().invoke(
        sdlc_cmd.sdlc,
        ["story", "start", "s-x", "--scope", "dna-development"],
    )
    assert r.exit_code != 0
    out = r.output.lower()
    assert "obrigat" in out  # "plano obrigatório pra começar"
    assert "--plan" in r.output and "--no-plan" in r.output


def test_start_command_exposes_gate_options() -> None:
    names = {o.name for o in sdlc_cmd.cmd_story_start.params}
    assert {"plan_text", "plan_doc", "no_plan", "skip_reason"} <= names
