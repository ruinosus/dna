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


def test_emit_concierge_to_vertex(runner):
    """The THIRD runtime: the SAME concierge source emits a Google ADK Agent Config
    YAML (an LlmAgent). Three runtimes from one definition, end-to-end via the CLI."""
    r = _run(runner, "concierge", "-t", "vertex", "--scope", "concierge", "--json")
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["target"] == "vertex"
    assert payload["filename"] == "concierge.adk.yaml"
    assert payload["artifact"].startswith("# yaml-language-server: $schema=")
    config = yaml.safe_load(payload["artifact"])
    assert config["agent_class"] == "LlmAgent"
    assert config["name"] == "concierge"
    assert config["model"] == "gpt-4o"
    assert config["tools"] == [{"name": "kb-search"}]


def test_emit_infra_emits_tfvars_json(runner):
    """`dna emit <copilot> --infra` renders the Terraform infra inputs from the
    copilot's persistence/knowledge.store/hosting (f-copilot-infra-binding)."""
    r = _run(runner, "memory-copilot", "--infra", "--scope", "concierge", "--json")
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["target"] == "terraform"
    (art,) = payload["artifacts"]
    assert art["role"] == "infra"
    assert art["path"] == "memory_agent.tfvars.json"
    tf = json.loads(art["content"])
    # postgres deduped by ref (checkpoint+memory+pgvector store → one resource)
    assert [p["ref"] for p in tf["postgres"]] == ["primary-pg"]
    assert tf["postgres"][0]["pgvector"] is True
    assert tf["hosting"]["target"] == "foundry"
    assert tf["env_injection"]["DNA_PG_URI_PRIMARY_PG"]["secret"] is True


def test_emit_infra_to_out_dir(runner, tmp_path):
    out_dir = tmp_path / "infra"
    out_dir.mkdir()
    r = _run(runner, "memory-copilot", "--infra", "--scope", "concierge",
             "--out", str(out_dir))
    assert r.exit_code == 0, r.output
    written = out_dir / "memory_agent.tfvars.json"
    assert written.exists()
    json.loads(written.read_text())


def test_emit_hosting_foundry_json(runner):
    """`dna emit <copilot> --hosting` renders the HOSTED variant from the copilot's
    `hosting` block (mode=hosted, target=foundry) — f-copilot-hosting."""
    r = _run(runner, "hosted-copilot", "--hosting", "--scope", "concierge", "--json")
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["target"] == "foundry-hosted"
    paths = {a["path"]: a for a in payload["artifacts"]}
    assert set(paths) == {"Dockerfile", "main.py", "requirements.txt", "azure.yaml"}
    assert all(a["role"] == "hosting" for a in payload["artifacts"])
    assert "ResponsesHostServer(build_agent()).run()" in paths["main.py"]["content"]
    assert "host: azure.ai.agent" in paths["azure.yaml"]["content"]


def test_emit_hosting_to_out_dir(runner, tmp_path):
    out_dir = tmp_path / "hosted"
    out_dir.mkdir()
    r = _run(runner, "hosted-copilot", "--hosting", "--scope", "concierge",
             "--out", str(out_dir))
    assert r.exit_code == 0, r.output
    for name in ("Dockerfile", "main.py", "requirements.txt", "azure.yaml"):
        assert (out_dir / name).exists()


def test_emit_hosting_self_hosted_fails(runner):
    """A `mode: self-hosted` copilot has no hosted variant → the command fails."""
    r = _run(runner, "memory-copilot", "--hosting", "--scope", "concierge")
    assert r.exit_code != 0


def test_emit_multi_artifact_writes_n_files(runner, tmp_path):
    """A multi-artifact emitter (agent.py + serve.py) treats --out as a DIRECTORY
    and lands every EmitArtifact at its own `path`. Registered as an in-test stub
    (the real multi-artifact target — agno copilot — lands in Chunk 4)."""
    from dna.emit import EmitArtifact, EmitResult, register_emitter

    class _MultiStub:
        target = "multi-stub"
        file_extension = "py"

        def emit(self, ctx):
            return EmitResult(
                target=self.target,
                artifacts=[
                    EmitArtifact(path="agent.py", content="INSTRUCTIONS = 'x'\n", role="agent"),
                    EmitArtifact(path="serve.py", content="# serve app\n", role="serving"),
                ],
                losses=["composition structure", "tenant overlay", "eval-as-contract"],
            )

        def extract_instructions(self, artifact):
            return "x"

    register_emitter(_MultiStub())
    out_dir = tmp_path / "emitted"
    r = _run(runner, "concierge", "-t", "multi-stub", "--scope", "concierge",
             "--out", str(out_dir))
    assert r.exit_code == 0, r.output
    assert (out_dir / "agent.py").read_text() == "INSTRUCTIONS = 'x'\n"
    assert (out_dir / "serve.py").read_text() == "# serve app\n"
    assert "2 files" in r.output


def test_emit_multi_artifact_requires_out_dir(runner):
    """Multi-artifact emit without --out errors (it must write N files)."""
    from dna.emit import EmitArtifact, EmitResult, register_emitter

    class _MultiStub2:
        target = "multi-stub-2"
        file_extension = "py"

        def emit(self, ctx):
            return EmitResult(
                target=self.target,
                artifacts=[
                    EmitArtifact(path="agent.py", content="INSTRUCTIONS = 'x'\n", role="agent"),
                    EmitArtifact(path="serve.py", content="# serve\n", role="serving"),
                ],
            )

        def extract_instructions(self, artifact):
            return "x"

    register_emitter(_MultiStub2())
    r = _run(runner, "concierge", "-t", "multi-stub-2", "--scope", "concierge")
    assert r.exit_code != 0


def test_unknown_target_fails(runner):
    r = _run(runner, "concierge", "-t", "no-such-runtime", "--scope", "concierge")
    assert r.exit_code != 0


def test_missing_target_fails(runner):
    r = _run(runner, "concierge", "--scope", "concierge")
    assert r.exit_code != 0
