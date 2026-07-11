"""``dna.emit`` — DNA → Amazon Bedrock Agent emitter (s-emit-bedrock).

The portability proof's SECOND runtime: the SAME concierge DNA source that emits
a Microsoft agent-framework ``PromptAgent`` also emits an AWS CloudFormation
``AWS::Bedrock::Agent`` template. One definition → two runtimes, swapped without a
rewrite. These tests pin:

1. **The byte-equal gate** (the survival claim): the emitted ``Properties.Instruction``
   is byte-equal to the DNA-composed prompt (``build_prompt``).
2. **The structural de-para**: name→AgentName, model→FoundationModel (provider
   token stripped), description→Description, tools (the Tool Kind) →
   ``ActionGroups[].FunctionSchema.Functions[]`` with a flat
   ``Parameters{Type,Description,Required}`` map. Not a string dump.
3. **Credential-free structural validation**: the emitted template conforms to the
   documented ``AWS::Bedrock::Agent`` CloudFormation schema (required keys, name
   patterns, the enum ParameterDetail Types) — no AWS call needed.
4. **The pluggable registry**: ``bedrock`` is registered additively; the CLI core
   never changes.
5. **The honest losses**: composition structure / tenant / eval / tool-param-depth
   / output_schema / model-coordinate — reported, not hidden.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from dna.emit import (
    EmitContext,
    EmitError,
    available_targets,
    build_emit_context,
    emit_agent,
    emit_agent_from_scope,
    get_emitter,
)
from dna.emit.bedrock import BedrockEmitter, _bedrock_model_id, _camel, _emit_parameters
from dna.kernel import Kernel

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"
_AGENT = "concierge"

# The documented AWS::Bedrock::Agent constraints we validate against (no creds).
_NAME_PATTERN = re.compile(r"^([0-9a-zA-Z][_-]?){1,100}$")
_PARAM_TYPES = {"string", "number", "integer", "boolean", "array"}


@pytest.fixture()
def mi():
    return Kernel.quick(_SCOPE, base_dir=_BASE)


def _template(mi, **kw) -> dict:
    return json.loads(emit_agent(mi, _AGENT, "bedrock", **kw).artifact)


def _agent_props(template: dict) -> dict:
    (resource,) = template["Resources"].values()
    return resource["Properties"]


# ── 1. the byte-equal gate ────────────────────────────────────────────────


def test_instruction_byte_equal_to_composed_prompt(mi) -> None:
    """The single most important claim: the emitted `Instruction` is the
    DNA-composed prompt VERBATIM (Soul + guardrails + instruction)."""
    props = _agent_props(_template(mi))
    assert props["Instruction"] == mi.build_prompt(_AGENT)


def test_from_scope_convenience_boots_and_emits() -> None:
    result = emit_agent_from_scope(_SCOPE, _AGENT, "bedrock", base_dir=_BASE)
    props = _agent_props(json.loads(result.artifact))
    mi = Kernel.quick(_SCOPE, base_dir=_BASE)
    assert props["Instruction"] == mi.build_prompt(_AGENT)


# ── 2. the structural de-para ──────────────────────────────────────────────


def test_cfn_envelope(mi) -> None:
    t = _template(mi)
    assert t["AWSTemplateFormatVersion"] == "2010-09-09"
    assert "concierge" in t["Description"]
    (logical_id,) = t["Resources"].keys()
    assert logical_id == "ConciergeAgent"  # CamelCase(slug) + "Agent"
    assert t["Resources"][logical_id]["Type"] == "AWS::Bedrock::Agent"


def test_agent_properties(mi) -> None:
    props = _agent_props(_template(mi))
    assert props["AgentName"] == "concierge"
    assert props["Description"] == "Internal engineering support concierge grounded in runbooks."
    assert props["FoundationModel"] == "gpt-4o"  # azure/gpt-4o → provider token stripped
    assert props["AutoPrepare"] is True
    # intentional, human-legible key order.
    assert list(props.keys()) == [
        "AgentName", "Description", "FoundationModel", "Instruction", "ActionGroups", "AutoPrepare",
    ]


def test_tools_mapped_as_function_schema(mi) -> None:
    props = _agent_props(_template(mi))
    groups = props["ActionGroups"]
    assert len(groups) == 1
    group = groups[0]
    assert group["ActionGroupName"] == "concierge-actions"
    # client-side tools → RETURN_CONTROL (no Lambda ARN needed).
    assert group["ActionGroupExecutor"] == {"CustomControl": "RETURN_CONTROL"}
    functions = group["FunctionSchema"]["Functions"]
    assert len(functions) == 1
    fn = functions[0]
    assert fn["Name"] == "kb-search"
    assert "runbook knowledge base" in fn["Description"]
    # Parameters is a FLAT map name -> {Type, Description, Required}.
    params = fn["Parameters"]
    assert params["query"]["Type"] == "string"
    assert params["query"]["Required"] is True
    assert params["top_k"]["Type"] == "integer"
    assert params["top_k"]["Required"] is False  # not in the schema's `required`


def test_model_override_strips_provider(mi) -> None:
    # a bedrock-native id (with a `:version` suffix) passes through UNTOUCHED.
    props = _agent_props(_template(mi, model="anthropic.claude-3-5-sonnet-20240620-v1:0"))
    assert props["FoundationModel"] == "anthropic.claude-3-5-sonnet-20240620-v1:0"
    # a DNA slash coordinate is stripped to the bare id.
    props2 = _agent_props(_template(mi, model="bedrock/anthropic.claude-v2"))
    assert props2["FoundationModel"] == "anthropic.claude-v2"
    # an inference-profile ARN is never split.
    arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-v2"
    props3 = _agent_props(_template(mi, model=arn))
    assert props3["FoundationModel"] == arn


# ── 3. credential-free structural validation against the documented schema ──


def test_emitted_template_conforms_to_bedrock_agent_schema(mi) -> None:
    """Validate the artifact against the documented ``AWS::Bedrock::Agent`` schema
    WITHOUT an AWS call: required keys, name patterns, and the enum
    ``ParameterDetail.Type`` set. This is the shape gate the task asks for."""
    t = _template(mi)
    assert set(t) >= {"AWSTemplateFormatVersion", "Resources"}
    (resource,) = t["Resources"].values()
    assert resource["Type"] == "AWS::Bedrock::Agent"
    props = resource["Properties"]

    # AgentName is the one required property; it must match the CFN pattern.
    assert "AgentName" in props
    assert _NAME_PATTERN.match(props["AgentName"])
    # Instruction has a documented minimum length of 40.
    assert len(props["Instruction"]) >= 40

    for group in props.get("ActionGroups", []):
        assert _NAME_PATTERN.match(group["ActionGroupName"])  # required, patterned
        assert set(group["ActionGroupExecutor"]) <= {"Lambda", "CustomControl"}
        functions = group["FunctionSchema"]["Functions"]  # FunctionSchema.Functions required
        assert functions
        for fn in functions:
            assert _NAME_PATTERN.match(fn["Name"])  # Function.Name required + patterned
            for detail in fn.get("Parameters", {}).values():
                assert detail["Type"] in _PARAM_TYPES  # ParameterDetail.Type enum
                assert isinstance(detail["Required"], bool)


def test_cfn_lint_gated(mi) -> None:
    """PROOF the template passes the real CloudFormation linter — skipped when
    ``cfn-lint`` (an optional dev tool) is not installed, mirroring the
    agent-framework live-load gate."""
    cfnlint_api = pytest.importorskip("cfnlint.api")
    artifact = emit_agent(mi, _AGENT, "bedrock").artifact
    matches = cfnlint_api.lint(artifact)
    # Ignore W (warnings) / I (info); fail only on E (structural/schema errors).
    errors = [m for m in matches if str(getattr(m.rule, "id", "")).startswith("E")]
    assert errors == [], f"cfn-lint errors: {[(m.rule.id, m.message) for m in errors]}"


# ── the pure mapping helpers ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [("concierge-grounded", "ConciergeGrounded"), ("greeter", "Greeter"), ("kb_search_bot", "KbSearchBot")],
)
def test_camel(raw, expected) -> None:
    assert _camel(raw) == expected


@pytest.mark.parametrize(
    "model,expected",
    [
        ("azure/gpt-4o", "gpt-4o"),
        ("openai:gpt-4o-mini", "gpt-4o-mini"),  # known DNA provider token → stripped
        ("anthropic.claude-v2", "anthropic.claude-v2"),  # bare bedrock id passes through
        ("anthropic.claude-3-v1:0", "anthropic.claude-3-v1:0"),  # `:version` kept
        ("arn:aws:bedrock:us-east-1:1:foundation-model/x", "arn:aws:bedrock:us-east-1:1:foundation-model/x"),
        (None, None),
    ],
)
def test_bedrock_model_id(model, expected) -> None:
    assert _bedrock_model_id(model) == expected


def test_emit_parameters_flattens_unsupported_types() -> None:
    """A JSON-Schema `object` param has no Bedrock slot → coerced to string, and
    the coercion is flagged so the loss can be reported."""
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {
            "a": {"type": "string", "description": "kept"},
            "b": {"type": "object"},  # unsupported → string + flag
        },
    }
    params, coerced = _emit_parameters(schema)
    assert coerced is True
    assert params["a"] == {"Type": "string", "Description": "kept", "Required": True}
    assert params["b"] == {"Type": "string", "Required": False}


# ── 4. the pluggable registry ──────────────────────────────────────────────


def test_bedrock_is_registered() -> None:
    assert "bedrock" in available_targets()
    assert isinstance(get_emitter("bedrock"), BedrockEmitter)


# ── 5. honest losses ───────────────────────────────────────────────────────


def test_losses_reported(mi) -> None:
    result = emit_agent(mi, _AGENT, "bedrock")
    joined = " ".join(result.losses)
    assert "composition structure" in joined
    assert "tenant overlay" in joined
    assert "eval-as-contract" in joined
    assert "tool parameter depth" in joined  # tools present
    assert "model coordinate" in joined  # model bound but provider-native
    assert "spec.tools[] (Tool Kind)" in result.mapping


def test_losses_include_unbound_model() -> None:
    """A toolless, model-less context reports the unbound-model loss instead of
    the coordinate one — and emits no FoundationModel / ActionGroups."""
    ctx = EmitContext(name="bare", description="", instructions="x" * 40, model=None)
    result = BedrockEmitter().emit(ctx)
    props = _agent_props(json.loads(result.artifact))
    assert "FoundationModel" not in props
    assert "ActionGroups" not in props
    joined = " ".join(result.losses)
    assert "model unbound" in joined
    assert "tool parameter depth" not in joined  # no tools


def test_missing_agent_fails_loud(mi) -> None:
    with pytest.raises(EmitError):
        build_emit_context(mi, "does-not-exist")
