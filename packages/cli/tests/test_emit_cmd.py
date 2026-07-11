"""Tests for ``dna emit`` — materialize a DNA agent into a runtime's native
artifact (s-emit-agent-framework).

Exercises the REAL CLI path (dna_session → dna.emit → the registered emitter)
against the committed ``examples/emitting-to-a-runtime`` concierge scope: the
command must list targets, emit a valid agent-framework PromptAgent whose
``instructions`` is the DNA-composed prompt, write to ``--out``, and surface the
de-para losses.
"""
from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from click.testing import CliRunner

from dna_cli.emit_cmd import emit

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DNA_BASE_DIR", str(_BASE))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)


def _run(runner, *args):
    return runner.invoke(emit, list(args), catch_exceptions=False)


def test_list_targets(runner):
    r = _run(runner, "--list-targets")
    assert r.exit_code == 0, r.output
    assert "agent-framework" in r.output


def test_emit_concierge_to_stdout(runner):
    r = _run(runner, "concierge", "--target", "agent-framework", "--scope", "concierge")
    assert r.exit_code == 0, r.output
    doc = yaml.safe_load(r.output)  # de-para losses go to stderr, so stdout is clean YAML
    assert doc["kind"] == "Prompt"
    assert doc["name"] == "Concierge"
    assert doc["model"] == {"id": "gpt-4o", "provider": "AzureOpenAI"}
    assert doc["tools"][0]["kind"] == "function"


def test_emit_json_includes_mapping_and_losses(runner):
    r = _run(runner, "concierge", "-t", "agent-framework", "--scope", "concierge", "--json")
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["target"] == "agent-framework"
    assert "spec.tools[] (Tool Kind)" in payload["mapping"]
    assert any("composition structure" in loss for loss in payload["losses"])


def test_emit_to_out_file(runner, tmp_path):
    out = tmp_path / "concierge.agent.yaml"
    r = _run(runner, "concierge", "-t", "agent-framework", "--scope", "concierge",
             "--out", str(out))
    assert r.exit_code == 0, r.output
    assert out.exists()
    doc = yaml.safe_load(out.read_text())
    assert doc["kind"] == "Prompt"


def test_emit_concierge_to_bedrock(runner):
    """The SECOND runtime: the SAME concierge source emits a CloudFormation
    AWS::Bedrock::Agent template (the portability proof, end-to-end via the CLI)."""
    r = _run(runner, "concierge", "-t", "bedrock", "--scope", "concierge", "--json")
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["target"] == "bedrock"
    assert payload["filename"] == "concierge.bedrock.json"
    t = json.loads(payload["artifact"])
    (resource,) = t["Resources"].values()
    assert resource["Type"] == "AWS::Bedrock::Agent"
    props = resource["Properties"]
    assert props["AgentName"] == "concierge"
    assert props["FoundationModel"] == "gpt-4o"
    assert props["ActionGroups"][0]["FunctionSchema"]["Functions"][0]["Name"] == "kb-search"


def test_unknown_target_fails(runner):
    r = _run(runner, "concierge", "-t", "vertex", "--scope", "concierge")  # not yet implemented
    assert r.exit_code != 0


def test_missing_target_fails(runner):
    r = _run(runner, "concierge", "--scope", "concierge")
    assert r.exit_code != 0
