"""Tests for ``dna explain`` — per-section prompt provenance
(s-dna-explain-provenance).

Exercises the REAL CLI path (dna_session → mi.explain_prompt) against the
committed ``examples/emitting-to-a-runtime`` concierge scope: the command must
print a provenance table attributing each composed section (instruction, soul,
guardrail) to its source file + hash + origin, and its ``--json`` payload must
carry the composed prompt byte-identical to ``build_prompt``.
"""
from __future__ import annotations

import json
import pathlib

import pytest
from click.testing import CliRunner

from dna_cli.explain_cmd import explain

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DNA_BASE_DIR", str(_BASE))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_TENANT", raising=False)


def _run(runner, *args):
    return runner.invoke(explain, list(args), catch_exceptions=False)


def test_table_lists_composed_sections(runner):
    r = _run(runner, "concierge", "--scope", "concierge")
    assert r.exit_code == 0, r.output
    # Header + one row per composed section.
    assert "section" in r.output and "source file" in r.output and "origin" in r.output
    assert "instruction" in r.output
    assert "soul" in r.output
    # The Soul source artifact path is attributed.
    assert "souls/helpdesk-host/SOUL.md" in r.output


def test_json_prompt_is_byte_equal_to_build(runner):
    from dna_cli.emit_cmd import emit  # emit embeds build_prompt verbatim

    r = _run(runner, "concierge", "--scope", "concierge", "--json")
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["agent"] == "concierge"
    assert isinstance(payload["sections"], list) and payload["sections"]
    # Each section row carries the documented columns.
    row = payload["sections"][0]
    assert {"section", "source", "hash", "version", "origin", "overridden_by_tenant"} <= set(row)
    # The composed prompt equals what emit carries verbatim (byte-equal gate).
    er = CliRunner().invoke(
        emit, ["concierge", "-t", "agent-framework", "--scope", "concierge", "--json"],
        catch_exceptions=False,
    )
    emit_payload = json.loads(er.output)
    import yaml
    emitted = yaml.safe_load(emit_payload["artifact"])
    assert emitted["instructions"] == payload["prompt"]


def test_missing_agent_fails(runner):
    r = _run(runner, "--scope", "concierge")
    assert r.exit_code != 0
