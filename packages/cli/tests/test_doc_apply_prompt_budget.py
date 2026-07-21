"""Tests for `dna doc apply` clear failure on PromptBudgetExceededError.

Task 9: CLI dna doc apply clear failure (feat/model-profile-prompt-budget).

`apply` uses the local kernel (dna_session) and calls
kernel.write_document() directly. When writing an over-cap voice
Agent, the kernel raises PromptBudgetExceededError.

These tests verify that:
  1. The CLI exits with a non-zero exit code (not 0).
  2. The output contains the budget-specific error message — model ID,
     token count, and agent name — NOT a generic "write failed: ..." wrapper.
  3. Other unrelated exceptions still surface normally (regression guard).

All tests are offline — the write is monkeypatched to raise the error
without a live stack.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli.doc_cmd import doc
from dna.kernel.prompt_budget import PromptBudgetExceededError


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def over_cap_agent_yaml(tmp_path):
    """Write an over-cap voice Agent YAML fixture to tmp_path."""
    long_instruction = "x" * 80_000
    content = (
        "apiVersion: github.com/ruinosus/dna/helix/v1\n"
        "kind: Agent\n"
        "metadata:\n"
        "  name: jarvis\n"
        "spec:\n"
        "  model: gpt-realtime-2\n"
        "  voice_persona: {}\n"
        f"  instruction: '{long_instruction}'\n"
    )
    f = tmp_path / "jarvis.yaml"
    f.write_text(content, encoding="utf-8")
    return str(f)


def _make_budget_error():
    return PromptBudgetExceededError(
        model_id="gpt-realtime-2",
        estimated_tokens=17269,
        cap=16384,
        agent_name="jarvis",
    )


def _fake_session(monkeypatch, *, raise_error: Exception | None = None):
    """Fake session injected via ctx.obj — never touches DNA_SOURCE_URL / kernel boot.

    Returns a mock Session whose kernel.write_document raises `raise_error`
    (if given) or returns successfully.
    """
    from dna_cli import doc_cmd

    # Stub _load_apply_input to return a valid raw doc (bypasses kernel marker walk)
    raw_doc = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "jarvis"},
        "spec": {"model": "gpt-realtime-2", "voice_persona": {}, "instruction": "x" * 80_000},
    }

    # Build a mock session
    mock_kernel = MagicMock()
    if raise_error is not None:
        mock_kernel.write_document = AsyncMock(side_effect=raise_error)
    else:
        mock_kernel.write_document = AsyncMock(return_value={"ok": True})
    mock_kernel.with_tenant.return_value = mock_kernel

    mock_holder = MagicMock()
    mock_holder.kernel = mock_kernel

    mock_session = MagicMock()
    mock_session.kernel = mock_kernel
    mock_session.holder = mock_holder
    mock_session.scope = "hr-screening"
    mock_session.get_doc.return_value = None  # treat as new doc (CREATED)

    # run() must drive the coroutine — use a FRESH loop (i-037). The old
    # asyncio.get_event_loop() raised "no current event loop" when a prior
    # test in the suite (test_auth_cmd) had closed the thread's loop.
    import asyncio

    def _run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    mock_session.run = _run

    # Patch _load_apply_input so we skip kernel marker scan
    monkeypatch.setattr(doc_cmd, "_load_apply_input", lambda path, kernel: raw_doc)

    from contextlib import contextmanager

    @contextmanager
    def _fake_dna_session(scope=None):
        yield mock_session

    return mock_session, {SESSION_PROVIDER_KEY: _fake_dna_session}


# ---------------------------------------------------------------------------
# Main assertion: clear, red, non-zero exit on PromptBudgetExceededError
# ---------------------------------------------------------------------------


def test_apply_exits_nonzero_on_prompt_budget_exceeded(
    runner, over_cap_agent_yaml, monkeypatch
):
    """apply must exit with code != 0 when the kernel raises PromptBudgetExceededError."""
    _mock, obj = _fake_session(monkeypatch, raise_error=_make_budget_error())
    result = runner.invoke(doc, ["apply", over_cap_agent_yaml], obj=obj)
    assert result.exit_code != 0, (
        f"Expected non-zero exit, got {result.exit_code}. Output:\n{result.output}"
    )


def test_apply_shows_model_id_in_error(runner, over_cap_agent_yaml, monkeypatch):
    """The error output must name the offending model."""
    _mock, obj = _fake_session(monkeypatch, raise_error=_make_budget_error())
    result = runner.invoke(doc, ["apply", over_cap_agent_yaml], obj=obj)
    assert "gpt-realtime-2" in result.output, (
        f"Expected model ID in output. Got:\n{result.output}"
    )


def test_apply_shows_agent_name_in_error(runner, over_cap_agent_yaml, monkeypatch):
    """The error output must name the offending agent."""
    _mock, obj = _fake_session(monkeypatch, raise_error=_make_budget_error())
    result = runner.invoke(doc, ["apply", over_cap_agent_yaml], obj=obj)
    assert "jarvis" in result.output, (
        f"Expected agent name in output. Got:\n{result.output}"
    )


def test_apply_shows_token_count_in_error(runner, over_cap_agent_yaml, monkeypatch):
    """The error output must include the estimated token count."""
    _mock, obj = _fake_session(monkeypatch, raise_error=_make_budget_error())
    result = runner.invoke(doc, ["apply", over_cap_agent_yaml], obj=obj)
    # The error message contains "17269" (estimated_tokens) and "16384" (cap)
    assert "17269" in result.output or "16384" in result.output, (
        f"Expected token numbers in output. Got:\n{result.output}"
    )


def test_apply_does_not_say_write_failed_for_budget_error(
    runner, over_cap_agent_yaml, monkeypatch
):
    """Budget errors must NOT show as generic 'write failed:' prefix.

    The old code wrapped everything in 'write failed: <msg>'. For prompt
    budget errors the message should stand on its own (no confusing prefix).
    """
    _mock, obj = _fake_session(monkeypatch, raise_error=_make_budget_error())
    result = runner.invoke(doc, ["apply", over_cap_agent_yaml], obj=obj)
    # The output should NOT start with 'write failed:' for a budget error
    combined = (result.output or "") + (result.stderr or "" if hasattr(result, "stderr") else "")
    assert "write failed" not in combined.lower(), (
        f"Expected budget error without 'write failed' prefix. Got:\n{combined}"
    )


# ---------------------------------------------------------------------------
# Regression guard: other errors still surface
# ---------------------------------------------------------------------------


def test_apply_still_exits_nonzero_on_other_errors(
    runner, over_cap_agent_yaml, monkeypatch
):
    """Non-budget errors must still cause non-zero exit (regression guard)."""
    _mock, obj = _fake_session(monkeypatch, raise_error=ValueError("some other write error"))
    result = runner.invoke(doc, ["apply", over_cap_agent_yaml], obj=obj)
    assert result.exit_code != 0, (
        f"Expected non-zero exit for ValueError. Got {result.exit_code}."
    )
