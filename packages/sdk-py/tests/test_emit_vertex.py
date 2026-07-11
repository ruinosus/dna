"""``dna.emit`` — DNA → Google ADK Agent Config emitter (s-emit-vertex).

The portability proof's THIRD runtime: the SAME concierge DNA source that emits a
Microsoft agent-framework ``PromptAgent`` and an AWS CloudFormation
``AWS::Bedrock::Agent`` also emits a **Google ADK Agent Config** YAML (an
``LlmAgent`` loaded with ``config_agent_utils.from_config``). One definition →
three runtimes, swapped without a rewrite. These tests pin:

1. **The byte-equal gate** (the survival claim): the emitted ``instruction`` is
   byte-equal to the DNA-composed prompt (``build_prompt``) — AND identical to the
   agent-framework ``instructions`` and the Bedrock ``Instruction`` (one source →
   three runtimes, the SAME prompt).
2. **The structural de-para**: fixed ``agent_class: LlmAgent``, name→``name``
   (snake_cased identifier), description→``description``, model→``model`` (provider
   token stripped), tools (the Tool Kind) → ``tools[].name`` code references. Not a
   string dump.
3. **Credential-free structural validation**: the emitted config conforms to the
   documented ADK ``LlmAgentConfig`` schema (required ``name``, agent_class, a
   valid-identifier name, string ``instruction``, ``tools`` as ``{name}`` refs) and
   carries the ``# yaml-language-server`` schema header — no GCP call needed.
4. **The pluggable registry**: ``vertex`` is registered additively; the CLI core
   never changes.
5. **The honest losses**: composition structure / tenant / eval / tool-binding /
   output_schema / model-coordinate — reported, not hidden.
"""
from __future__ import annotations

import pathlib
import re

import pytest
import yaml

from dna.emit import (
    EmitContext,
    EmitError,
    available_targets,
    build_emit_context,
    emit_agent,
    emit_agent_from_scope,
    get_emitter,
)
from dna.emit.vertex import (
    VertexEmitter,
    _is_gemini,
    _snake,
    _vertex_model_id,
)
from dna.kernel import Kernel

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"
_AGENT = "concierge"

# ADK requires the agent `name` to be a valid Python identifier.
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SCHEMA_HEADER = "# yaml-language-server: $schema=https://raw.githubusercontent.com/google/adk-python"


@pytest.fixture()
def mi():
    return Kernel.quick(_SCOPE, base_dir=_BASE)


def _config(mi, **kw) -> dict:
    return yaml.safe_load(emit_agent(mi, _AGENT, "vertex", **kw).artifact)


# ── 1. the byte-equal gate (and the 3-runtime identity) ─────────────────────


def test_instruction_byte_equal_to_composed_prompt(mi) -> None:
    """The single most important claim: the emitted `instruction` is the
    DNA-composed prompt VERBATIM (Soul + guardrails + instruction)."""
    config = _config(mi)
    assert config["instruction"] == mi.build_prompt(_AGENT)


def test_instruction_identical_across_all_three_runtimes(mi) -> None:
    """One source → three runtimes: the composed prompt is byte-identical in the
    agent-framework `instructions`, the Bedrock `Instruction`, and the Vertex/ADK
    `instruction`. This is the portability thesis, proven end-to-end."""
    import json

    composed = mi.build_prompt(_AGENT)
    af = yaml.safe_load(emit_agent(mi, _AGENT, "agent-framework").artifact)["instructions"]
    bd = json.loads(emit_agent(mi, _AGENT, "bedrock").artifact)["Resources"]["ConciergeAgent"]["Properties"]["Instruction"]
    vx = _config(mi)["instruction"]
    assert af == bd == vx == composed


def test_from_scope_convenience_boots_and_emits() -> None:
    result = emit_agent_from_scope(_SCOPE, _AGENT, "vertex", base_dir=_BASE)
    config = yaml.safe_load(result.artifact)
    mi = Kernel.quick(_SCOPE, base_dir=_BASE)
    assert config["instruction"] == mi.build_prompt(_AGENT)


# ── 2. the structural de-para ──────────────────────────────────────────────


def test_agent_config_fields(mi) -> None:
    config = _config(mi)
    assert config["agent_class"] == "LlmAgent"
    assert config["name"] == "concierge"
    assert config["description"] == "Internal engineering support concierge grounded in runbooks."
    assert config["model"] == "gpt-4o"  # azure/gpt-4o → provider token stripped
    # intentional, human-legible key order.
    assert list(config.keys()) == [
        "agent_class", "name", "description", "model", "instruction", "tools",
    ]


def test_schema_header_present(mi) -> None:
    """The artifact leads with the `# yaml-language-server` header binding it to the
    REAL published ADK schema — the credential-free validation hook."""
    artifact = emit_agent(mi, _AGENT, "vertex").artifact
    header = artifact.splitlines()[0]
    assert header.startswith(_SCHEMA_HEADER)
    assert header.endswith("AgentConfig.json")  # binds to the real published schema


def test_tools_mapped_as_code_references(mi) -> None:
    tools = _config(mi)["tools"]
    assert tools == [{"name": "kb-search"}]  # name-only code reference (no inline schema)


def test_model_override_strips_provider(mi) -> None:
    # a bare Gemini id passes through untouched.
    assert _config(mi, model="gemini-2.0-flash")["model"] == "gemini-2.0-flash"
    # a DNA slash coordinate for a known provider is stripped to the bare id.
    assert _config(mi, model="vertex/gemini-1.5-pro")["model"] == "gemini-1.5-pro"
    # a DNA colon coordinate for a known provider is stripped.
    assert _config(mi, model="google:gemini-2.5-flash")["model"] == "gemini-2.5-flash"


# ── 3. credential-free structural validation ───────────────────────────────


def test_emitted_config_conforms_to_adk_agent_config_schema(mi) -> None:
    """Validate the artifact against the documented ADK ``LlmAgentConfig`` schema
    WITHOUT a GCP call: required ``name`` (a valid identifier), the ``LlmAgent``
    class, a string ``instruction``, and ``tools`` as code references. This is the
    shape gate the task asks for."""
    config = _config(mi)
    assert "name" in config  # the one required field
    assert _IDENT.match(config["name"])  # ADK: name must be a valid Python identifier
    assert config["agent_class"] == "LlmAgent"
    assert isinstance(config["instruction"], str) and config["instruction"]
    assert isinstance(config.get("model", ""), str)
    for entry in config.get("tools", []):
        assert set(entry) == {"name"}  # ADK ToolConfig: `name` (a code reference)
        assert isinstance(entry["name"], str) and entry["name"]


def test_emitted_config_loads_into_adk_gated() -> None:
    """PROOF the config loads into a live ADK agent — skipped when
    ``google.adk`` (an optional dev dep) is not installed, mirroring the
    agent-framework live-load gate. Uses a toolless / Gemini-model variant so the
    load resolves without a real Python tool module or GCP credential."""
    pytest.importorskip("google.adk")
    from google.adk.agents import config_agent_utils  # type: ignore

    import tempfile

    ctx = EmitContext(
        name="concierge",
        description="test",
        instructions="x" * 60,
        model="gemini-2.0-flash",
    )
    artifact = VertexEmitter().emit(ctx).artifact
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(artifact)
        path = fh.name
    agent = config_agent_utils.from_config(path)  # live LlmAgent
    assert agent.name == "concierge"


# ── the pure mapping helpers ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("concierge-grounded", "concierge_grounded"),
        ("greeter", "greeter"),
        ("KB Search Bot", "kb_search_bot"),
        ("2fast", "_2fast"),
    ],
)
def test_snake(raw, expected) -> None:
    assert _snake(raw) == expected
    assert _IDENT.match(_snake(raw))


@pytest.mark.parametrize(
    "model,expected",
    [
        ("azure/gpt-4o", "gpt-4o"),
        ("vertex/gemini-2.0-flash", "gemini-2.0-flash"),  # known DNA token → stripped
        ("openai:gpt-4o-mini", "gpt-4o-mini"),
        ("gemini-1.5-pro", "gemini-1.5-pro"),  # bare Gemini id passes through
        ("some-registry/model-x", "some-registry/model-x"),  # unknown token → kept
        (None, None),
    ],
)
def test_vertex_model_id(model, expected) -> None:
    assert _vertex_model_id(model) == expected


def test_is_gemini() -> None:
    assert _is_gemini("gemini-2.0-flash") is True
    assert _is_gemini("gpt-4o") is False
    assert _is_gemini(None) is False


# ── 4. the pluggable registry ──────────────────────────────────────────────


def test_vertex_is_registered() -> None:
    assert "vertex" in available_targets()
    assert isinstance(get_emitter("vertex"), VertexEmitter)


# ── 5. honest losses ───────────────────────────────────────────────────────


def test_losses_reported(mi) -> None:
    result = emit_agent(mi, _AGENT, "vertex")
    joined = " ".join(result.losses)
    assert "composition structure" in joined
    assert "tenant overlay" in joined
    assert "eval-as-contract" in joined
    assert "tool binding" in joined  # tools present
    assert "model coordinate" in joined  # model bound but not a Gemini id
    assert "spec.tools[] (Tool Kind)" in result.mapping


def test_losses_include_unbound_model_and_omit_tools() -> None:
    """A toolless, model-less context reports the unbound-model loss instead of the
    coordinate one — and emits no `model` / `tools`."""
    ctx = EmitContext(name="bare", description="", instructions="x" * 40, model=None)
    result = VertexEmitter().emit(ctx)
    config = yaml.safe_load(result.artifact)
    assert "model" not in config
    assert "tools" not in config
    joined = " ".join(result.losses)
    assert "model unbound" in joined
    assert "tool binding" not in joined  # no tools


def test_gemini_model_reports_no_coordinate_loss() -> None:
    """A native Gemini id is a clean fit — no model-coordinate loss."""
    ctx = EmitContext(name="g", description="", instructions="x" * 40, model="gemini-2.0-flash")
    joined = " ".join(VertexEmitter().emit(ctx).losses)
    assert "model coordinate" not in joined
    assert "model unbound" not in joined


def test_output_schema_reported_as_loss() -> None:
    ctx = EmitContext(
        name="o", description="", instructions="x" * 40, model="gemini-2.0-flash",
        output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
    )
    joined = " ".join(VertexEmitter().emit(ctx).losses)
    assert "output_schema" in joined


def test_missing_agent_fails_loud(mi) -> None:
    with pytest.raises(EmitError):
        build_emit_context(mi, "does-not-exist")
