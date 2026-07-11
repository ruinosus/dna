"""DNA → Microsoft **agent-framework** emitter (the first proven target).

Materializes an :class:`~dna.emit.EmitContext` into the declarative
``PromptAgent`` YAML that ``agent-framework-declarative``'s ``AgentFactory``
loads (``create_agent_from_yaml`` / ``create_agent_from_yaml_path``). Proven in
the pivot spike: the emitted ``instructions`` are byte-equal to the DNA-composed
prompt, and the artifact loads into a live agent-framework ``Agent`` object.

The de-para (DNA field → PromptAgent field):

    metadata.name                     -> name         (CamelCased id)
    metadata.description              -> description
    Soul + guardrails + instruction   -> instructions (flat — kernel-composed)
      (composed by build_prompt)
    spec.model (or Genome default_llm)-> model.{id, provider}
    spec.tools[] (Tool Kind surfaces) -> tools[] (kind: function)
    spec.output_schema                -> outputSchema (only when present)

What does NOT survive (no PromptAgent slot — the DNA-only value, recorded in
``EmitResult.losses``):
    - composition STRUCTURE: Soul reuse + Guardrail-as-a-wired-doc collapse to a
      flat ``instructions`` string. The structure is a DNA authoring-time concept.
    - tenant overlay: a per-tenant persona without a fork — no PromptAgent field.
    - eval-as-contract: prompt invariants asserted as EvalCases — no slot.
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitContext, EmitResult

#: Map a DNA provider token → the agent-framework ``model.provider`` value.
#: agent-framework's declarative loader binds a chat client by provider name;
#: these are the providers its ``AgentFactory`` resolves. Unknown tokens pass
#: through unchanged (so a future provider works without a code change).
_PROVIDER_MAP = {
    "azure": "AzureOpenAI",
    "azureopenai": "AzureOpenAI",
    "azure_openai": "AzureOpenAI",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "foundry": "AzureAIFoundry",
    "azureaifoundry": "AzureAIFoundry",
}

#: When the DNA model is bare (no provider token) and no ``--provider`` is given,
#: default to AzureOpenAI — the provider the spike proved and the common Foundry
#: deployment. Documented as an emitter default, never silently wrong.
_DEFAULT_PROVIDER = "AzureOpenAI"


def _camel(name: str) -> str:
    """``concierge-grounded`` → ``ConciergeGrounded`` (a valid PromptAgent id)."""
    return "".join(part.capitalize() for part in str(name).replace("_", "-").split("-") if part)


def _split_model(model: str | None, provider_hint: str | None) -> dict[str, str] | None:
    """Split a DNA model coordinate into agent-framework ``{id, provider}``.

    Accepts ``prov:model`` (``openai:gpt-4o-mini``), ``prov/model``
    (``azure/gpt-4o``), or a bare id (``gpt-4o``). An explicit ``provider_hint``
    (CLI ``--provider``) always wins.
    """
    if not model:
        return None
    token: str | None = None
    ident = model
    for sep in (":", "/"):
        if sep in model:
            token, ident = model.split(sep, 1)
            break
    if provider_hint:
        provider = provider_hint
    elif token:
        provider = _PROVIDER_MAP.get(token.strip().lower(), token)
    else:
        provider = _DEFAULT_PROVIDER
    return {"id": ident.strip(), "provider": provider}


def _emit_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project neutral tool surfaces → agent-framework declarative ``tools``.

    Each Tool becomes a ``kind: function`` entry — the shape the agent-framework
    declarative **AgentSchema** uses for a declared function tool
    (``microsoft.github.io/AgentSchema`` — tool kinds: function, openapi,
    code_interpreter, file_search, mcp, web_search, custom): a ``name``, a
    ``description`` (the text the model reads), and ``parameters`` (the input
    contract the model fills in). This is exactly the surface ``dna.load_tools``
    serves, so the emitted tool is byte-identical to what a Python ``@tool`` or a
    TS ``useCopilotAction`` would show.

    ``parameters`` is carried as the Tool's JSON Schema (``spec.input_schema``) —
    the faithful, source-of-truth representation of the arguments. (AgentSchema
    also accepts a flattened ``{param: {kind, description}}`` map; DNA emits the
    full JSON Schema so nested/required structure is not lost — a documented
    fidelity choice.)
    """
    out: list[dict[str, Any]] = []
    for t in tools:
        entry: dict[str, Any] = {
            "name": t["name"],
            "kind": "function",
            "description": t.get("description", ""),
        }
        params = t.get("parameters") or {}
        if params:
            entry["parameters"] = params
        out.append(entry)
    return out


class AgentFrameworkEmitter:
    """Emit a DNA agent as an agent-framework declarative ``PromptAgent``."""

    target = "agent-framework"
    file_extension = "agent.yaml"

    def to_prompt_agent(self, ctx: EmitContext) -> dict[str, Any]:
        """The PURE de-para: :class:`EmitContext` → the PromptAgent dict.

        Parity-critical: the TS twin (`packages/sdk-ts/src/emit/agentFramework.ts`)
        must build the same dict from the same context. Field order is
        intentional and preserved on serialization (``sort_keys=False``)."""
        provider_hint = ctx.options.get("provider") if ctx.options else None
        doc: dict[str, Any] = {"kind": "Prompt", "name": _camel(ctx.name)}
        if ctx.description:
            doc["description"] = ctx.description
        model = _split_model(ctx.model, provider_hint)
        if model:
            doc["model"] = model
        if ctx.tools:
            doc["tools"] = _emit_tools(ctx.tools)
        # instructions carried verbatim — the byte-equal gate.
        doc["instructions"] = ctx.instructions
        if ctx.output_schema:
            doc["outputSchema"] = ctx.output_schema
        return doc

    def emit(self, ctx: EmitContext) -> EmitResult:
        import yaml

        prompt_agent = self.to_prompt_agent(ctx)
        artifact = yaml.safe_dump(prompt_agent, sort_keys=False, allow_unicode=True)

        losses: list[str] = [
            "composition structure — Soul reuse + wired Guardrails flatten to one "
            "`instructions` string (no `soul:`/`guardrails:` slot in a PromptAgent)",
            "tenant overlay — a per-tenant persona without a fork has no PromptAgent field",
            "eval-as-contract — prompt invariants (EvalCases) have no PromptAgent slot",
        ]
        if ctx.model is None:
            losses.append(
                "model unbound in DNA and none supplied — emitted PromptAgent has no "
                "`model:` block; pass --model or set the agent's spec.model / Genome default_llm"
            )

        mapping = {
            "metadata.name": "name (CamelCase)",
            "metadata.description": "description",
            "build_prompt (Soul+guardrails+instruction)": "instructions",
            "spec.model / Genome.default_llm": "model.{id,provider}",
            "spec.tools[] (Tool Kind)": "tools[] (kind: function)",
            "spec.output_schema": "outputSchema",
        }

        return EmitResult(
            artifact=artifact,
            target=self.target,
            filename=f"{ctx.name}.{self.file_extension}",
            losses=losses,
            mapping=mapping,
        )

    def extract_instructions(self, artifact: str) -> str | None:
        """Byte-equal invariant hook: read ``instructions`` back from the
        emitted PromptAgent YAML (see :meth:`~dna.emit.EmitterPort.extract_instructions`)."""
        import yaml

        doc = yaml.safe_load(artifact)
        return doc.get("instructions") if isinstance(doc, dict) else None
