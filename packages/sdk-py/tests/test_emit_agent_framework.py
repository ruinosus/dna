"""``dna.emit`` — DNA → Microsoft agent-framework emitter (s-emit-agent-framework).

The pivot's first proof: DNA is a vendor-neutral DEFINITION layer that authors an
agent ONCE and MATERIALIZES the artifact a runtime consumes. These tests pin:

1. **The byte-equal gate** (the survival claim): the emitted PromptAgent's
   ``instructions`` is byte-equal to the DNA-composed prompt (``build_prompt``) —
   i.e. the emit carries the composition verbatim, it does not paraphrase it.
2. **The structural de-para**: name→CamelCase, model→{id,provider}, tools (the
   Tool Kind) → ``kind: function`` entries with the input JSON Schema, description
   passed through. Not a string dump — a field-level mapping.
3. **The pluggable registry**: ``available_targets`` / ``UnknownTarget`` /
   ``register_emitter`` — a new target is additive, the CLI core never changes.
4. **The honest losses**: composition structure / tenant / eval have no target
   slot and are reported.
5. **Gated live load**: when ``agent_framework_declarative`` is importable, the
   emitted YAML loads into a live AgentFactory Agent (skips without the runtime).
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

from dna.emit import (
    EmitContext,
    EmitError,
    UnknownTarget,
    available_targets,
    build_emit_context,
    emit_agent,
    emit_agent_from_scope,
    get_emitter,
    register_emitter,
)
from dna.emit.agent_framework import AgentFrameworkEmitter, _camel, _split_model
from dna.kernel import Kernel

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"
_AGENT = "concierge"


@pytest.fixture()
def mi():
    return Kernel.quick(_SCOPE, base_dir=_BASE)


# ── 1. the byte-equal gate ────────────────────────────────────────────────


def test_instructions_byte_equal_to_composed_prompt(mi) -> None:
    """The single most important claim: the emitted `instructions` is the
    DNA-composed prompt VERBATIM (Soul + guardrails + instruction)."""
    result = emit_agent(mi, _AGENT, "agent-framework")
    emitted = yaml.safe_load(result.artifact)
    assert emitted["instructions"] == mi.build_prompt(_AGENT)


def test_from_scope_convenience_boots_and_emits() -> None:
    result = emit_agent_from_scope(_SCOPE, _AGENT, "agent-framework", base_dir=_BASE)
    emitted = yaml.safe_load(result.artifact)
    mi = Kernel.quick(_SCOPE, base_dir=_BASE)
    assert emitted["instructions"] == mi.build_prompt(_AGENT)


# ── 2. the structural de-para ──────────────────────────────────────────────


def test_prompt_agent_envelope(mi) -> None:
    doc = yaml.safe_load(emit_agent(mi, _AGENT, "agent-framework").artifact)
    assert doc["kind"] == "Prompt"
    assert doc["name"] == "Concierge"  # CamelCase of the slug
    assert doc["description"] == "Internal engineering support concierge grounded in runbooks."


def test_model_split_to_id_provider(mi) -> None:
    doc = yaml.safe_load(emit_agent(mi, _AGENT, "agent-framework").artifact)
    assert doc["model"] == {"id": "gpt-4o", "provider": "AzureOpenAI"}


def test_tools_mapped_as_function_kind(mi) -> None:
    doc = yaml.safe_load(emit_agent(mi, _AGENT, "agent-framework").artifact)
    tools = doc["tools"]
    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == "kb-search"
    assert tool["kind"] == "function"  # AgentSchema function-tool kind (NOT `type`)
    assert "runbook knowledge base" in tool["description"]
    # parameters carry the Tool's input JSON Schema faithfully.
    assert tool["parameters"]["required"] == ["query"]
    assert tool["parameters"]["properties"]["query"]["type"] == "string"


def test_provider_override_wins(mi) -> None:
    result = emit_agent(mi, _AGENT, "agent-framework", model="my-deploy", provider="OpenAI")
    doc = yaml.safe_load(result.artifact)
    assert doc["model"] == {"id": "my-deploy", "provider": "OpenAI"}


def test_field_order_preserved(mi) -> None:
    """Emitted key order is intentional (kind, name, description, model, tools,
    instructions) — sort_keys=False keeps the artifact human-legible."""
    doc = yaml.safe_load(emit_agent(mi, _AGENT, "agent-framework").artifact)
    assert list(doc.keys()) == ["kind", "name", "description", "model", "tools", "instructions"]


# ── the pure mapping helpers ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("concierge-grounded", "ConciergeGrounded"),
        ("greeter", "Greeter"),
        ("kb_search_bot", "KbSearchBot"),
    ],
)
def test_camel(raw, expected) -> None:
    assert _camel(raw) == expected


@pytest.mark.parametrize(
    "model,hint,expected",
    [
        ("openai:gpt-4o-mini", None, {"id": "gpt-4o-mini", "provider": "OpenAI"}),
        ("azure/gpt-4o", None, {"id": "gpt-4o", "provider": "AzureOpenAI"}),
        ("gpt-4o", None, {"id": "gpt-4o", "provider": "AzureOpenAI"}),  # bare → default
        ("gpt-4o", "OpenAI", {"id": "gpt-4o", "provider": "OpenAI"}),  # hint wins
        (None, None, None),
    ],
)
def test_split_model(model, hint, expected) -> None:
    assert _split_model(model, hint) == expected


# ── 3. the pluggable registry ──────────────────────────────────────────────


def test_agent_framework_is_registered() -> None:
    assert "agent-framework" in available_targets()
    assert isinstance(get_emitter("agent-framework"), AgentFrameworkEmitter)


def test_unknown_target_raises_helpful() -> None:
    with pytest.raises(UnknownTarget) as ei:
        get_emitter("bedrock")
    assert ei.value.target == "bedrock"
    assert "agent-framework" in ei.value.available


def test_register_new_target_is_additive() -> None:
    """A new target plugs in with a class + one register_emitter() call — the
    CLI/emit-core never changes. This is how bedrock/vertex/openai land."""

    class _EchoEmitter:
        target = "echo-test"
        file_extension = "txt"

        def emit(self, ctx: EmitContext):
            from dna.emit import EmitResult

            return EmitResult(artifact=ctx.instructions, target=self.target,
                              filename=f"{ctx.name}.txt")

    try:
        register_emitter(_EchoEmitter())
        assert "echo-test" in available_targets()
        ctx = EmitContext(name="x", description="", instructions="hello")
        assert get_emitter("echo-test").emit(ctx).artifact == "hello"
    finally:
        from dna.emit import EMITTER_REGISTRY

        EMITTER_REGISTRY.pop("echo-test", None)


# ── 4. honest losses ───────────────────────────────────────────────────────


def test_losses_reported(mi) -> None:
    result = emit_agent(mi, _AGENT, "agent-framework")
    joined = " ".join(result.losses)
    assert "composition structure" in joined
    assert "tenant overlay" in joined
    assert "eval-as-contract" in joined
    assert "spec.tools[] (Tool Kind)" in result.mapping


def test_missing_agent_fails_loud(mi) -> None:
    with pytest.raises(EmitError):
        build_emit_context(mi, "does-not-exist")


# ── 5. gated: the emitted artifact loads into a live agent-framework Agent ──


def test_emitted_yaml_loads_into_agent_framework(mi) -> None:
    """PROOF the emit round-trips into the real runtime — skipped when
    agent-framework-declarative (+ its .NET dependency) is not installed."""
    afd = pytest.importorskip("agent_framework_declarative")
    import os

    os.environ.setdefault("DOTNET_ROLL_FORWARD", "Major")
    os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://spike.invalid/")
    os.environ.setdefault("AZURE_OPENAI_API_KEY", "sk-emit-dummy")

    artifact = emit_agent(mi, _AGENT, "agent-framework").artifact
    factory = afd.AgentFactory()
    agent = factory.create_agent_from_yaml(artifact)
    assert agent is not None
    assert getattr(agent, "name", None)
