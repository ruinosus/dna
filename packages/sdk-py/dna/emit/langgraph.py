"""DNA → **LangGraph** emitter (code-first, ``langgraph.prebuilt``).

LangGraph is code-first: you build an agent by calling a constructor —
``create_react_agent(model, tools=[...], prompt="...")`` — there is no declarative
agent file to map onto. So this target is a
:class:`~dna.emit.scaffold.ScaffoldEmitter`: it fills a curated
``{langgraph × case}`` template rather than generating code ad-hoc, and the
emitted ``INSTRUCTIONS`` constant is byte-equal to the DNA-composed prompt.

The de-para (DNA field → LangGraph source):

    build_prompt (Soul+guardrails+instruction) -> INSTRUCTIONS constant (BYTE-EQUAL)
      (composed, flat)                             → create_react_agent(prompt=INSTRUCTIONS)
    metadata.name                     -> create_react_agent(name=...)  (graph name)
    spec.model (or Genome default_llm)-> create_react_agent(model=...) (DNA coordinate
                                         PRESERVED — LangGraph resolves it via
                                         `init_chat_model`, which takes `provider:model`)
    spec.tools[] (Tool Kind surfaces) -> @tool stubs passed to tools=[...]
                                         (with-tools case only)

Cases (selected by the classifier from ctx signals):
    - ``prompt-only``  — no tools: a ReAct agent with an empty tool list.
    - ``with-tools``   — tools present: the canonical ReAct idiom, one
                         ``@tool`` stub per DNA Tool wired into ``tools=[...]``.
    (``structured-output`` — LangGraph has ``response_format`` — is not shipped
    yet; it falls back with a recorded loss.)

What does NOT survive (recorded in ``EmitResult.losses``): the DNA-only axes
(composition structure / tenant overlay / eval-as-contract), plus — code-first
specific — a Tool's real BODY and typed signature (each ``@tool`` is a scaffolded
stub), and the model-coordinate convention (``create_react_agent`` resolves the
string via ``init_chat_model``, whose provider prefixes are ``openai`` /
``anthropic`` / ``azure_openai`` / ``google_genai`` — a DNA ``azure/…`` coordinate
needs the ``azure_openai:`` prefix, or a model instance, at wire-up).
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitContext
from dna.emit.scaffold import ScaffoldChoice, ScaffoldEmitter, py_identifier, py_str_literal


class LanggraphEmitter(ScaffoldEmitter):
    """Emit a DNA agent as LangGraph ``create_react_agent`` source (scaffold)."""

    framework = "langgraph"
    target = "langgraph"
    file_extension = "py"

    def render_context(self, ctx: EmitContext, case: str) -> dict[str, Any]:
        tools = [
            {
                "name": t["name"],
                "func_name": py_identifier(t["name"]),
                "docstring_literal": py_str_literal(t.get("description") or t["name"]),
            }
            for t in ctx.tools
        ]
        return {
            "has_model": ctx.model is not None,
            "model_literal": py_str_literal(ctx.model) if ctx.model else "",
            "has_name": bool(ctx.name),
            "tools": tools,
            "tool_list": ", ".join(t["func_name"] for t in tools),
        }

    def losses(self, ctx: EmitContext, choice: ScaffoldChoice) -> list[str]:
        out: list[str] = []
        if ctx.tools:
            out.append(
                "tool body — each `@tool` is a scaffolded STUB (name + "
                "`raise NotImplementedError`); its real implementation and typed "
                "signature must be wired (LangChain derives the tool schema from the "
                "function signature + docstring)"
            )
        if ctx.model is None:
            out.append(
                "model unbound in DNA and none supplied — `create_react_agent` "
                "REQUIRES a model; the emitted call omits `model=`, so supply one at "
                "wire-up"
            )
        else:
            out.append(
                "model coordinate — the DNA coordinate is carried verbatim; "
                "`create_react_agent` resolves it via `init_chat_model`, whose "
                "provider prefixes are `openai` / `anthropic` / `azure_openai` / "
                "`google_genai`; a DNA `azure/…` coordinate needs the `azure_openai:` "
                "prefix (or a model instance) at wire-up"
            )
        if ctx.output_schema:
            out.append(
                "output_schema — map DNA's `spec.output_schema` to "
                "`create_react_agent(response_format=...)` (a Pydantic model) by hand; "
                "the scaffold does not synthesize the class"
            )
        return out

    def mapping(self) -> dict[str, str]:
        return {
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
            "metadata.name": "create_react_agent(name=...) (graph name)",
            "spec.model / Genome.default_llm": "create_react_agent(model=...) (DNA coordinate preserved)",
            "spec.tools[] (Tool Kind)": "@tool stubs → create_react_agent(tools=[...])",
        }
