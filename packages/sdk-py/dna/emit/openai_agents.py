"""DNA → **OpenAI Agents SDK** emitter (the first CODE-FIRST target).

The OpenAI Agents SDK is code-first: you construct an agent in Python —
``Agent(name=..., instructions=..., model=..., tools=[...])`` — there is no
declarative agent file to map onto. So this target is a
:class:`~dna.emit.scaffold.ScaffoldEmitter`: it fills a curated
``{openai-agents × case}`` template rather than generating code ad-hoc, and the
emitted ``INSTRUCTIONS`` constant is byte-equal to the DNA-composed prompt.

The de-para (DNA field → OpenAI Agents SDK source):

    Soul + guardrails + instruction   -> INSTRUCTIONS constant (flat, BYTE-EQUAL)
      (composed by build_prompt)          → Agent(instructions=INSTRUCTIONS)
    metadata.name                     -> Agent(name=...)   (the display name)
    spec.model (or Genome default_llm)-> Agent(model=...)  (provider token stripped)
    spec.tools[] (Tool Kind surfaces) -> @function_tool stubs passed to tools=[...]
                                         (with-tools case only)

Cases (selected by :func:`~dna.emit.scaffold.select_scaffold` from ctx signals):
    - ``prompt-only``  — no tools: the minimal ``Agent(name, instructions, model)``.
    - ``with-tools``   — tools present: the ReAct idiom, one ``@function_tool`` stub
                         per DNA Tool wired into ``tools=[...]``.
    (``structured-output`` is not shipped yet — it falls back to ``with-tools`` /
    ``prompt-only`` with a recorded loss; a follow-up story adds it.)

What does NOT survive (recorded in ``EmitResult.losses``): the DNA-only axes
(composition structure / tenant overlay / eval-as-contract), plus — code-first
specific — a Tool's real BODY and typed signature (each ``@function_tool`` is a
scaffolded stub to wire), and a non-OpenAI model coordinate (the SDK's ``model``
takes an OpenAI model name or a ``Model`` object; a DNA ``azure/...`` coordinate
needs a custom provider / ``ModelSettings`` at wire-up).
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitContext
from dna.emit.scaffold import ScaffoldChoice, ScaffoldEmitter, py_identifier, py_str_literal

#: DNA provider tokens stripped to expose the bare model id passed to the SDK.
_DNA_PROVIDER_TOKENS = frozenset(
    {"azure", "azureopenai", "azure_openai", "openai", "foundry", "azureaifoundry",
     "vertex", "google", "gemini", "anthropic"}
)


def _bare_model_id(model: str | None) -> str | None:
    """Strip a DNA ``prov:model`` / ``prov/model`` coordinate to the bare id."""
    if not model:
        return None
    ident = model.strip()
    for sep in (":", "/"):
        if sep in ident:
            token, rest = ident.split(sep, 1)
            if token.strip().lower() in _DNA_PROVIDER_TOKENS:
                return rest.strip()
    return ident


def _is_openai_model(model_id: str | None) -> bool:
    """Whether a bare id looks like an OpenAI model the SDK accepts natively."""
    return bool(model_id) and model_id.strip().lower().startswith(("gpt-", "o1", "o3", "o4"))


class OpenAIAgentsEmitter(ScaffoldEmitter):
    """Emit a DNA agent as OpenAI Agents SDK source (scaffold, code-first)."""

    framework = "openai-agents"
    target = "openai-agents"
    file_extension = "py"

    def render_context(self, ctx: EmitContext, case: str) -> dict[str, Any]:
        model_id = _bare_model_id(ctx.model)
        tools = [
            {
                "name": t["name"],
                "func_name": py_identifier(t["name"]),
                "docstring_literal": py_str_literal(t.get("description") or t["name"]),
            }
            for t in ctx.tools
        ]
        return {
            "has_model": model_id is not None,
            "model_literal": py_str_literal(model_id) if model_id else "",
            "tools": tools,
            "tool_list": ", ".join(t["func_name"] for t in tools),
        }

    def losses(self, ctx: EmitContext, choice: ScaffoldChoice) -> list[str]:
        out: list[str] = []
        if ctx.tools:
            out.append(
                "tool body — each `@function_tool` is a scaffolded STUB (name + "
                "`raise NotImplementedError`); its real implementation and typed "
                "signature must be wired (the OpenAI Agents SDK derives the tool "
                "schema from the Python function signature + docstring)"
            )
        model_id = _bare_model_id(ctx.model)
        if model_id is None:
            out.append(
                "model unbound in DNA and none supplied — emitted `Agent(...)` has no "
                "`model=`; the SDK falls back to its default"
            )
        elif not _is_openai_model(model_id):
            out.append(
                "model coordinate — the OpenAI Agents SDK `model=` takes an OpenAI "
                "model name or a `Model` object; a non-OpenAI coordinate needs a "
                "custom provider / `ModelSettings` at wire-up"
            )
        if ctx.output_schema:
            out.append(
                "output_schema — map DNA's `spec.output_schema` to `Agent(output_type=...)` "
                "(a Pydantic/TypedDict class) by hand; the scaffold does not synthesize the class"
            )
        return out

    def mapping(self) -> dict[str, str]:
        return {
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
            "metadata.name": "Agent(name=...)",
            "spec.model / Genome.default_llm": "Agent(model=...) (provider token stripped)",
            "spec.tools[] (Tool Kind)": "@function_tool stubs → Agent(tools=[...])",
        }
