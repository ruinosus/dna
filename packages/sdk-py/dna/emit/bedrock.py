"""DNA → **Amazon Bedrock Agent** emitter (the second proven target).

Materializes an :class:`~dna.emit.EmitContext` into an **AWS CloudFormation**
template that declares an ``AWS::Bedrock::Agent`` resource — the managed,
declarative Bedrock Agents service (``CreateAgent``: ``Instruction`` /
``FoundationModel`` / ``ActionGroups``). It is the SECOND runtime the SAME DNA
source emits to (the first is Microsoft agent-framework), which is precisely the
portability proof: author once, emit per runtime, swap runtimes without a rewrite.

Why Bedrock **Agents** (and not Strands / AgentCore): AWS ships three agent
surfaces — **Bedrock Agents** (a managed service with a published *declarative*
schema), **Strands Agents SDK** (code-first, Python), and **Bedrock AgentCore**
(a runtime that *hosts* any framework). Only Bedrock Agents has a field-for-field
declarative schema (``Instruction``, ``FoundationModel``, ``ActionGroups`` with a
``FunctionSchema``), so it is the only honest de-para target. Emitting it as a
**CloudFormation** ``AWS::Bedrock::Agent`` template gives a lintable, deployable
artifact that needs **no** AWS credential to produce or validate structurally.

The de-para (DNA field → CloudFormation ``AWS::Bedrock::Agent`` field):

    metadata.name                     -> Resources.<Camel>Agent.Properties.AgentName
    metadata.description              -> Properties.Description        (when present)
    Soul + guardrails + instruction   -> Properties.Instruction        (flat, BYTE-EQUAL)
      (composed by build_prompt)
    spec.model (or Genome default_llm)-> Properties.FoundationModel     (provider token stripped)
    spec.tools[] (Tool Kind surfaces) -> Properties.ActionGroups[0].FunctionSchema.Functions[]
      Tool.name / description         ->   Function.Name / Function.Description
      Tool.input_schema.properties    ->   Function.Parameters{ name: {Type,Description,Required} }
      (client-side tools)             ->   ActionGroupExecutor.CustomControl = RETURN_CONTROL

What does NOT survive (no Bedrock slot — the DNA-only value, recorded in
``EmitResult.losses``):
    - composition STRUCTURE: Soul reuse + Guardrail-as-a-wired-doc collapse to a
      flat ``Instruction`` string (Bedrock's ``GuardrailConfiguration`` is an
      *ID-referenced* Bedrock Guardrail, a different concept — not DNA's composed
      guardrails).
    - tenant overlay: a per-tenant persona without a fork — no Bedrock field.
    - eval-as-contract: prompt invariants asserted as EvalCases — no slot.
    - tool parameter DEPTH: Bedrock ``ParameterDetail`` is a FLAT
      ``{Type, Description, Required}`` map with ``Type`` ∈
      ``{string, number, integer, boolean, array}`` — JSON-Schema ``default`` /
      ``enum`` / nested object ``properties`` / array ``items`` typing are dropped.
    - output_schema: Bedrock Agent has no structured-response / output-schema field.
    - model coordinate: a DNA ``azure/openai`` coordinate is NOT a Bedrock
      foundation-model id; ``FoundationModel`` needs a Bedrock model id or
      inference-profile ARN (and a real ``AgentResourceRoleArn`` at deploy).
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitContext, EmitResult

#: Bedrock ``ParameterDetail.Type`` allowed values (the flat scalar/array set the
#: FunctionSchema accepts). A JSON-Schema type outside this set (notably
#: ``object``) has no Bedrock slot → it is coerced to ``string`` and reported.
_BEDROCK_PARAM_TYPES = frozenset({"string", "number", "integer", "boolean", "array"})

#: CloudFormation template format version — the stable, only value.
_CFN_VERSION = "2010-09-09"

#: DNA provider tokens (the ``prov:model`` / ``prov/model`` prefixes DNA authors
#: use). These are stripped to expose the bare model id. Bedrock-native provider
#: prefixes (anthropic./amazon./cohere./meta./mistral.) use a DOT and are NOT in
#: this set, so a real Bedrock id (incl. a ``:0`` version suffix) passes through.
_DNA_PROVIDER_TOKENS = frozenset(
    {"azure", "azureopenai", "azure_openai", "openai", "foundry", "azureaifoundry",
     "vertex", "google", "gemini"}
)


def _camel(name: str) -> str:
    """``concierge-grounded`` → ``ConciergeGrounded`` (a valid CFN logical id)."""
    return "".join(part.capitalize() for part in str(name).replace("_", "-").split("-") if part)


def _bedrock_model_id(model: str | None) -> str | None:
    """Project a DNA model coordinate → a Bedrock ``FoundationModel`` id.

    Bedrock encodes the provider INSIDE the id with a DOT (``anthropic.claude-v2``,
    ``amazon.titan-...``) and uses ``:`` for a version suffix (``...-v1:0``), so a
    naive colon split would corrupt a real Bedrock id or an ``arn:`` profile.
    Rule: an ``arn:`` passes through untouched; a DNA ``prov/model`` slash
    coordinate is stripped; a ``prov:model`` colon coordinate is stripped ONLY when
    ``prov`` is a known DNA provider token (so ``openai:gpt-4o`` → ``gpt-4o`` but
    ``anthropic.claude-...-v1:0`` and ``arn:aws:bedrock:...`` pass through). The
    provider-mismatch caveat is recorded as a loss, never hidden.
    """
    if not model:
        return None
    ident = model.strip()
    if ident.lower().startswith("arn:"):
        return ident  # an inference-profile / model ARN — never split.
    if "/" in ident:
        return ident.split("/", 1)[1].strip()  # DNA slash coordinate.
    if ":" in ident:
        token, rest = ident.split(":", 1)
        if token.strip().lower() in _DNA_PROVIDER_TOKENS:
            return rest.strip()  # DNA colon coordinate for a known provider.
    return ident  # bare / Bedrock-native id (keeps any `:version`).


def _emit_parameters(input_schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Project a Tool's input JSON Schema → Bedrock ``Function.Parameters``.

    Bedrock ``Parameters`` is an ``{name: ParameterDetail}`` map where each
    ``ParameterDetail`` is a FLAT ``{Type, Description, Required}``. The top-level
    ``properties`` become the parameters; ``required`` drives ``Required``; a type
    outside the Bedrock set is coerced to ``string`` (the depth loss). Returns the
    map plus a flag saying whether any coercion happened (for the loss report).
    """
    props = input_schema.get("properties") if isinstance(input_schema, dict) else None
    if not isinstance(props, dict) or not props:
        return {}, False
    required = input_schema.get("required") or []
    required_set = set(required) if isinstance(required, (list, tuple)) else set()

    out: dict[str, Any] = {}
    coerced = False
    for pname, pschema in props.items():
        pschema = pschema if isinstance(pschema, dict) else {}
        jtype = pschema.get("type", "string")
        if jtype in _BEDROCK_PARAM_TYPES:
            btype = jtype
        else:
            btype = "string"  # object / unknown → flatten to string (recorded loss)
            coerced = True
        detail: dict[str, Any] = {"Type": btype}
        desc = pschema.get("description")
        if desc:
            detail["Description"] = desc
        detail["Required"] = pname in required_set
        out[pname] = detail
    return out, coerced


def _emit_action_groups(ctx: EmitContext) -> tuple[list[dict[str, Any]], bool]:
    """Project the agent's tools → a single Bedrock action group (FunctionSchema).

    All DNA tools collapse into ONE action group whose ``FunctionSchema.Functions``
    holds one ``Function`` per tool. The executor is ``CustomControl:
    RETURN_CONTROL`` — Bedrock returns the tool call to the CALLER to run, which
    is the faithful mapping for DNA's client-side / builtin tools (no Lambda ARN
    required to produce a structurally-valid, credential-free artifact).
    """
    functions: list[dict[str, Any]] = []
    any_coerced = False
    for t in ctx.tools:
        fn: dict[str, Any] = {"Name": t["name"]}
        desc = t.get("description")
        if desc:
            fn["Description"] = desc
        params, coerced = _emit_parameters(t.get("parameters") or {})
        any_coerced = any_coerced or coerced
        if params:
            fn["Parameters"] = params
        functions.append(fn)

    group = {
        "ActionGroupName": f"{ctx.name}-actions",
        "Description": f"DNA-emitted tools for agent {ctx.name}",
        "ActionGroupExecutor": {"CustomControl": "RETURN_CONTROL"},
        "FunctionSchema": {"Functions": functions},
    }
    return [group], any_coerced


class BedrockEmitter:
    """Emit a DNA agent as an ``AWS::Bedrock::Agent`` CloudFormation template."""

    target = "bedrock"
    file_extension = "bedrock.json"

    def to_template(self, ctx: EmitContext) -> dict[str, Any]:
        """The PURE de-para: :class:`EmitContext` → the CloudFormation dict.

        Golden-locked: the emitted dict is frozen under ``tests/goldens/``.
        Field order is intentional and preserved on serialization
        (``json.dumps`` keeps insertion order)."""
        logical_id = f"{_camel(ctx.name)}Agent"

        props: dict[str, Any] = {"AgentName": ctx.name}
        if ctx.description:
            props["Description"] = ctx.description
        model_id = _bedrock_model_id(ctx.model)
        if model_id:
            props["FoundationModel"] = model_id
        # Instruction carried verbatim — the byte-equal gate.
        props["Instruction"] = ctx.instructions
        if ctx.tools:
            groups, _ = _emit_action_groups(ctx)
            props["ActionGroups"] = groups
        # DRAFT auto-prepare so the emitted agent is ready to invoke on deploy.
        props["AutoPrepare"] = True

        return {
            "AWSTemplateFormatVersion": _CFN_VERSION,
            "Description": f"DNA-emitted Amazon Bedrock Agent: {ctx.name}",
            "Resources": {
                logical_id: {"Type": "AWS::Bedrock::Agent", "Properties": props}
            },
        }

    def emit(self, ctx: EmitContext) -> EmitResult:
        import json

        template = self.to_template(ctx)
        artifact = json.dumps(template, indent=2, ensure_ascii=False) + "\n"

        losses: list[str] = [
            "composition structure — Soul reuse + wired Guardrails flatten to one "
            "`Instruction` string (Bedrock `GuardrailConfiguration` is an "
            "ID-referenced Bedrock Guardrail, not DNA's composed guardrails)",
            "tenant overlay — a per-tenant persona without a fork has no Bedrock Agent field",
            "eval-as-contract — prompt invariants (EvalCases) have no Bedrock slot",
        ]
        if ctx.tools:
            losses.append(
                "tool parameter depth — Bedrock `ParameterDetail` is a flat "
                "{Type, Description, Required} map (Type ∈ string|number|integer|"
                "boolean|array); JSON-Schema `default`, `enum`, nested object "
                "`properties`, and array `items` typing are dropped"
            )
        if ctx.output_schema:
            losses.append(
                "output_schema — Bedrock Agent has no structured-response / "
                "output-schema field; the agent's typed output contract is dropped"
            )
        if ctx.model is None:
            losses.append(
                "model unbound in DNA and none supplied — emitted template has no "
                "`FoundationModel`; pass --model or set spec.model / Genome default_llm"
            )
        else:
            losses.append(
                "model coordinate — a DNA `azure/openai` coordinate is not a Bedrock "
                "foundation-model id; `FoundationModel` needs a Bedrock model id or "
                "inference-profile ARN, plus an `AgentResourceRoleArn` at deploy"
            )

        mapping = {
            "metadata.name": "Resources.<id>Agent.Properties.AgentName",
            "metadata.description": "Properties.Description",
            "build_prompt (Soul+guardrails+instruction)": "Properties.Instruction (byte-equal)",
            "spec.model / Genome.default_llm": "Properties.FoundationModel",
            "spec.tools[] (Tool Kind)": "Properties.ActionGroups[].FunctionSchema.Functions[]",
            "Tool.input_schema.properties": "Function.Parameters{Type,Description,Required}",
        }

        return EmitResult(
            artifact=artifact,
            target=self.target,
            filename=f"{ctx.name}.{self.file_extension}",
            losses=losses,
            mapping=mapping,
        )

    def extract_instructions(self, artifact: str) -> str | None:
        """Byte-equal invariant hook: read ``Properties.Instruction`` back from
        the emitted CloudFormation template (see
        :meth:`~dna.emit.EmitterPort.extract_instructions`)."""
        import json

        template = json.loads(artifact)
        resources = template.get("Resources") if isinstance(template, dict) else None
        if not isinstance(resources, dict) or not resources:
            return None
        (resource,) = tuple(resources.values())
        return resource.get("Properties", {}).get("Instruction")
