"""DNA → **DeepAgents** emitter (code-first, ``deepagents``).

DeepAgents (the LangChain "batteries-included agent harness") is code-first: you
build an agent by calling ``create_deep_agent(model=..., tools=[...],
system_prompt="...")`` — there is no declarative agent file to map onto. So this
target is a :class:`~dna.emit.scaffold.ScaffoldEmitter`: it fills a curated
``{deepagents × case}`` template rather than generating code ad-hoc, and the
emitted ``INSTRUCTIONS`` constant is byte-equal to the DNA-composed prompt.

The de-para (DNA field → DeepAgents source):

    build_prompt (Soul+guardrails+instruction) -> INSTRUCTIONS constant (BYTE-EQUAL)
      (composed, flat)                             → create_deep_agent(system_prompt=INSTRUCTIONS)
    spec.model (or Genome default_llm)-> create_deep_agent(model=...) (DNA coordinate
                                         PRESERVED — resolved via `init_chat_model`)
    spec.tools[] (Tool Kind surfaces) -> callable stubs passed to tools=[...]
                                         (with-tools case only)

Note ``system_prompt`` sits in FRONT of the deep-agent's built-in harness prompt
(the planning / filesystem / sub-agent scaffolding), which is appended by the
framework — so the DNA prompt is a PREFIX of the effective system prompt, not the
whole of it. The byte-equal invariant is on the emitted ``INSTRUCTIONS`` constant.

Cases (selected by the classifier from ctx signals):
    - ``prompt-only``  — no tools: ``create_deep_agent`` with an empty tool list.
    - ``with-tools``   — tools present: one callable stub per DNA Tool wired into
                         ``tools=[...]``.
    (``structured-output`` is not shipped yet; it falls back with a recorded loss.)

What does NOT survive (recorded in ``EmitResult.losses``): the DNA-only axes
(composition structure / tenant overlay / eval-as-contract), plus — code-first
specific — a Tool's real BODY and typed signature (each stub is a callable), the
built-in harness prompt appended by the framework (DNA prompt is a prefix), no
declarative slot for ``metadata.name`` in ``create_deep_agent``, and the
model-coordinate convention (``init_chat_model`` provider prefixes; a DNA
``azure/…`` needs ``azure_openai:``; unbound falls back to the deep-agent default).
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitContext
from dna.emit.scaffold import ScaffoldChoice, ScaffoldEmitter, py_identifier, py_str_literal


class DeepAgentsEmitter(ScaffoldEmitter):
    """Emit a DNA agent as DeepAgents ``create_deep_agent`` source (scaffold)."""

    framework = "deepagents"
    target = "deepagents"
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
            "tools": tools,
            "tool_list": ", ".join(t["func_name"] for t in tools),
        }

    def losses(self, ctx: EmitContext, choice: ScaffoldChoice) -> list[str]:
        out: list[str] = [
            "harness prompt — `system_prompt` sits in FRONT of the deep-agent's "
            "built-in harness prompt (planning / filesystem / sub-agent scaffolding), "
            "which the framework appends; the DNA prompt is a PREFIX of the effective "
            "system prompt, not the whole of it",
            "metadata.name — `create_deep_agent` has no declarative name slot; the "
            "DNA agent name is not carried",
        ]
        if ctx.tools:
            out.append(
                "tool body — each tool is a scaffolded STUB (a callable + "
                "`raise NotImplementedError`); its real implementation and typed "
                "signature must be wired"
            )
        if ctx.model is None:
            out.append(
                "model unbound in DNA and none supplied — emitted `create_deep_agent(...)` "
                "has no `model=`; the framework falls back to its default deep-agent model"
            )
        else:
            out.append(
                "model coordinate — the DNA coordinate is carried verbatim; "
                "`create_deep_agent` resolves it via `init_chat_model`, whose provider "
                "prefixes are `openai` / `anthropic` / `azure_openai` / `google_genai`; "
                "a DNA `azure/…` coordinate needs the `azure_openai:` prefix at wire-up"
            )
        if ctx.output_schema:
            out.append(
                "output_schema — DNA's `spec.output_schema` has no direct "
                "`create_deep_agent` slot; enforce structured output via a middleware "
                "or a typed sub-agent by hand"
            )
        return out

    def mapping(self) -> dict[str, str]:
        return {
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal, PREFIX of system_prompt)",
            "spec.model / Genome.default_llm": "create_deep_agent(model=...) (DNA coordinate preserved)",
            "spec.tools[] (Tool Kind)": "callable stubs → create_deep_agent(tools=[...])",
        }
