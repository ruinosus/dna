"""DNA → **Google ADK Agent Config** emitter (the third proven target).

Materializes an :class:`~dna.emit.EmitContext` into a **Google Agent Development
Kit (ADK) Agent Config** YAML — the declarative, code-free way to define an ADK
``LlmAgent`` (loaded with ``config_agent_utils.from_config(<path>.yaml)``). It is
the THIRD runtime the SAME DNA source emits to (after Microsoft agent-framework
and Amazon Bedrock), which is the portability proof: author once, emit per
runtime, swap runtimes without a rewrite.

Why the ADK **Agent Config** (and not the ADK code-first ``LlmAgent`` object or
the Vertex AI Agent Engine): Google ships two ADK authoring surfaces —
**Agent Config** (a published, declarative YAML schema:
``https://raw.githubusercontent.com/google/adk-python/.../AgentConfig.json`` —
``agent_class`` / ``name`` / ``model`` / ``instruction`` / ``tools`` / …) and the
**code-first** Python/Java ``LlmAgent`` object. Only Agent Config has a
field-for-field *declarative* schema, so it is the only honest de-para target;
Vertex AI Agent Engine is a *deployment host* that runs an ADK agent, not a
declarative agent definition of its own. Emitting the Agent Config YAML gives a
lintable artifact that needs **no** GCP credential to produce or validate
structurally (the ``# yaml-language-server`` header wires the real schema into any
editor / validator).

The de-para (DNA field → ADK ``LlmAgentConfig`` field):

    (fixed)                           -> agent_class: LlmAgent
    metadata.name                     -> name          (snake_cased — ADK requires
                                                         a valid Python identifier)
    metadata.description              -> description    (when present)
    Soul + guardrails + instruction   -> instruction   (flat, BYTE-EQUAL)
      (composed by build_prompt)
    spec.model (or Genome default_llm)-> model          (Gemini id; provider token stripped)
    spec.tools[] (Tool Kind surfaces) -> tools[].name   (a CODE reference — see loss)

What does NOT survive (no Agent Config slot — the DNA-only value or an ADK
code-reference-only field, recorded in ``EmitResult.losses``):
    - composition STRUCTURE: Soul reuse + Guardrail-as-a-wired-doc collapse to a
      flat ``instruction`` string (Agent Config has no ``soul:``/``guardrails:`` slot).
    - tenant overlay: a per-tenant persona without a fork — no Agent Config field.
    - eval-as-contract: prompt invariants asserted as EvalCases — no slot.
    - tool binding shape: ADK binds a tool by a **code reference** (a fully
      qualified Python path or a built-in name), NOT a declarative schema — so a
      Tool's ``description`` and ``parameters`` (JSON Schema) have NO Agent Config
      slot; ADK derives them from the referenced Python function's signature +
      docstring at load. Each emitted ``- name`` is a PLACEHOLDER to repoint to the
      tool's real fully-qualified path.
    - output_schema: ADK ``output_schema`` is a ``CodeConfig`` (a reference to a
      Pydantic class by FQN), not an inline JSON Schema — DNA's inline
      ``spec.output_schema`` has no inline Agent Config slot.
    - model coordinate: ADK ``model`` natively accepts a Gemini id; a DNA
      ``azure/openai`` coordinate is not a Gemini id and needs ``model_code`` (a
      ``LiteLlm`` ``CodeConfig``) at deploy, plus a GCP project/region.
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitContext, EmitResult

#: The published ADK Agent Config JSON Schema. Emitted as a leading
#: ``# yaml-language-server`` header so any editor / validator binds the artifact
#: to the REAL schema — the credential-free structural-validation hook.
_ADK_SCHEMA_URL = (
    "https://raw.githubusercontent.com/google/adk-python/refs/heads/main/"
    "src/google/adk/agents/config_schemas/AgentConfig.json"
)

#: The ADK ``agent_class`` this emitter targets (the declarative LLM agent).
_AGENT_CLASS = "LlmAgent"

#: DNA provider tokens (the ``prov:model`` / ``prov/model`` prefixes DNA authors
#: use). Stripped to expose the bare model id. A bare Gemini id
#: (``gemini-2.0-flash``) has no token and passes through unchanged.
_DNA_PROVIDER_TOKENS = frozenset(
    {"azure", "azureopenai", "azure_openai", "openai", "foundry", "azureaifoundry",
     "vertex", "google", "gemini", "anthropic"}
)


def _snake(name: str) -> str:
    """``concierge-grounded`` → ``concierge_grounded`` (a valid ADK agent name).

    ADK requires the agent ``name`` to be a valid Python identifier (starts with
    a letter/underscore, then letters/digits/underscores). DNA slugs use dashes,
    so we lower-case and map any non-identifier char to ``_``; a leading digit is
    prefixed with ``_``. Mirrors Bedrock's ``_camel`` transform for its logical id.
    """
    out = []
    for ch in str(name).strip():
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    ident = "".join(out).strip("_").lower() or "agent"
    if ident[0].isdigit():
        ident = f"_{ident}"
    return ident


def _vertex_model_id(model: str | None) -> str | None:
    """Project a DNA model coordinate → an ADK ``model`` id (a Gemini id).

    A DNA ``prov/model`` or ``prov:model`` coordinate has its provider token
    stripped when the token is a known DNA provider (``vertex/gemini-2.0-flash`` →
    ``gemini-2.0-flash``, ``openai:gpt-4o`` → ``gpt-4o``); a bare id passes through.
    A non-Gemini bare id survives too — but ADK's ``model`` accepts only Gemini
    natively, so the caller records the coordinate mismatch as a loss.
    """
    if not model:
        return None
    ident = model.strip()
    if "/" in ident:
        token, rest = ident.split("/", 1)
        if token.strip().lower() in _DNA_PROVIDER_TOKENS:
            return rest.strip()
        return ident
    if ":" in ident:
        token, rest = ident.split(":", 1)
        if token.strip().lower() in _DNA_PROVIDER_TOKENS:
            return rest.strip()
    return ident


def _is_gemini(model_id: str | None) -> bool:
    """Whether an emitted ``model`` id is a native Gemini id (else needs model_code)."""
    return bool(model_id) and model_id.strip().lower().startswith("gemini")


def _emit_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project neutral tool surfaces → ADK ``tools`` code references.

    ADK Agent Config binds a tool by a CODE reference — ``- name: <fqn>`` (a fully
    qualified Python path or a built-in name), optionally with ``args``. There is
    NO inline function-schema slot (unlike agent-framework / Bedrock): ADK derives
    a tool's description + parameters from the referenced Python callable at load.
    So the faithful de-para carries the tool NAME (the wiring intent) as a
    placeholder reference; the schema depth is reported as a loss, not hidden.
    """
    return [{"name": t["name"]} for t in tools]


class VertexEmitter:
    """Emit a DNA agent as a Google ADK ``LlmAgent`` Agent Config YAML."""

    target = "vertex"
    file_extension = "adk.yaml"

    def to_agent_config(self, ctx: EmitContext) -> dict[str, Any]:
        """The PURE de-para: :class:`EmitContext` → the ADK Agent Config dict.

        Parity-critical: the TS twin (``packages/sdk-ts/src/emit/vertex.ts``) must
        build the SAME dict from the same context. Field order is intentional and
        preserved on serialization (``sort_keys=False``). The schema-header comment
        is prepended at serialization time, not part of this dict."""
        doc: dict[str, Any] = {"agent_class": _AGENT_CLASS, "name": _snake(ctx.name)}
        if ctx.description:
            doc["description"] = ctx.description
        model_id = _vertex_model_id(ctx.model)
        if model_id:
            doc["model"] = model_id
        # instruction carried verbatim — the byte-equal gate.
        doc["instruction"] = ctx.instructions
        if ctx.tools:
            doc["tools"] = _emit_tools(ctx.tools)
        return doc

    def emit(self, ctx: EmitContext) -> EmitResult:
        import yaml

        config = self.to_agent_config(ctx)
        body = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
        # Prepend the schema header so the artifact self-validates in any editor.
        artifact = f"# yaml-language-server: $schema={_ADK_SCHEMA_URL}\n{body}"

        losses: list[str] = [
            "composition structure — Soul reuse + wired Guardrails flatten to one "
            "`instruction` string (Agent Config has no `soul:`/`guardrails:` slot)",
            "tenant overlay — a per-tenant persona without a fork has no Agent Config field",
            "eval-as-contract — prompt invariants (EvalCases) have no Agent Config slot",
        ]
        if ctx.tools:
            losses.append(
                "tool binding — ADK binds a tool by a CODE reference (a fully "
                "qualified Python path or a built-in name), not a declarative schema; "
                "a Tool's `description` and `parameters` (JSON Schema) have no Agent "
                "Config slot (ADK derives them from the Python callable at load). Each "
                "emitted `- name` is a placeholder to repoint to the tool's real FQN"
            )
        if ctx.output_schema:
            losses.append(
                "output_schema — ADK `output_schema` is a `CodeConfig` (a reference to "
                "a Pydantic class by FQN), not an inline JSON Schema; DNA's inline "
                "`spec.output_schema` has no inline Agent Config slot"
            )
        model_id = _vertex_model_id(ctx.model)
        if model_id is None:
            losses.append(
                "model unbound in DNA and none supplied — emitted config has no `model`; "
                "ADK inherits the ancestor / system default (gemini)"
            )
        elif not _is_gemini(model_id):
            losses.append(
                "model coordinate — ADK `model` natively accepts a Gemini id; a DNA "
                "`azure/openai` coordinate is not a Gemini id and needs `model_code` (a "
                "`LiteLlm` CodeConfig) at deploy, plus a GCP project/region"
            )

        mapping = {
            "metadata.name": "name (snake_case identifier)",
            "metadata.description": "description",
            "build_prompt (Soul+guardrails+instruction)": "instruction (byte-equal)",
            "spec.model / Genome.default_llm": "model (Gemini id; provider token stripped)",
            "spec.tools[] (Tool Kind)": "tools[].name (code reference)",
        }

        return EmitResult(
            artifact=artifact,
            target=self.target,
            filename=f"{ctx.name}.{self.file_extension}",
            losses=losses,
            mapping=mapping,
        )

    def extract_instructions(self, artifact: str) -> str | None:
        """Byte-equal invariant hook: read ``instruction`` back from the emitted
        ADK Agent Config YAML — the leading ``# yaml-language-server`` header is a
        comment PyYAML skips (see
        :meth:`~dna.emit.EmitterPort.extract_instructions`)."""
        import yaml

        config = yaml.safe_load(artifact)
        return config.get("instruction") if isinstance(config, dict) else None
