"""DNA → **Agno** emitter (code-first, ``agno.agent``).

Agno is code-first: you build an agent by constructing an object —
``Agent(name=..., model=..., instructions=..., tools=[...])`` — there is no
declarative agent file to map onto. So this target is a
:class:`~dna.emit.scaffold.ScaffoldEmitter`: it fills a curated ``{agno × case}``
template rather than generating code ad-hoc, and the emitted ``INSTRUCTIONS``
constant is byte-equal to the DNA-composed prompt.

The de-para (DNA field → Agno source):

    build_prompt (Soul+guardrails+instruction) -> INSTRUCTIONS constant (BYTE-EQUAL)
      (composed, flat)                             → Agent(instructions=INSTRUCTIONS)
    metadata.name                     -> Agent(name=...)   (the display name)
    spec.model (or Genome default_llm)-> Agent(model=...)  (DNA coordinate PRESERVED —
                                         Agno accepts a `provider:model` string)
    spec.tools[] (Tool Kind surfaces) -> plain-function stubs passed to tools=[...]
                                         (with-tools case only; Agno auto-wraps
                                         plain callables as tools)

Cases (selected by the classifier from ctx signals):
    - ``prompt-only``  — no tools: the minimal ``Agent(name, model, instructions)``.
    - ``with-tools``   — tools present: one plain-function stub per DNA Tool wired
                         into ``tools=[...]`` (Agno turns a callable into a tool).
    (``structured-output`` — Agno has ``output_schema`` — is not shipped yet; it
    falls back with a recorded loss.)

What does NOT survive (recorded in ``EmitResult.losses``): the DNA-only axes
(composition structure / tenant overlay / eval-as-contract), plus — code-first
specific — a Tool's real BODY and typed signature (each stub is a bare callable),
and the model-coordinate assumption (the string form assumes Agno's string-model
resolution; a specific ``Model`` object — e.g. ``OpenAIChat(id=...)`` — is the
alternative at wire-up).
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitContext
from dna.emit.scaffold import ScaffoldChoice, ScaffoldEmitter, py_identifier, py_str_literal


class AgnoEmitter(ScaffoldEmitter):
    """Emit a DNA agent as Agno ``Agent(...)`` source (scaffold, code-first)."""

    framework = "agno"
    target = "agno"
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
        out: list[str] = []
        if ctx.tools:
            out.append(
                "tool body — each tool is a scaffolded STUB (a bare callable + "
                "`raise NotImplementedError`); its real implementation and typed "
                "signature must be wired (Agno derives the tool schema from the "
                "function signature + docstring)"
            )
        if ctx.model is None:
            out.append(
                "model unbound in DNA and none supplied — emitted `Agent(...)` has no "
                "`model=`; supply one at wire-up (Agno requires a model)"
            )
        else:
            out.append(
                "model coordinate — the DNA coordinate is carried verbatim as a "
                "string; this assumes Agno's string-model resolution. A specific "
                "`Model` object (e.g. `OpenAIChat(id=...)`) is the alternative at wire-up"
            )
        if ctx.output_schema:
            out.append(
                "output_schema — map DNA's `spec.output_schema` to "
                "`Agent(output_schema=...)` (a Pydantic model) by hand; the scaffold "
                "does not synthesize the class"
            )
        return out

    def mapping(self) -> dict[str, str]:
        return {
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
            "metadata.name": "Agent(name=...)",
            "spec.model / Genome.default_llm": "Agent(model=...) (DNA coordinate preserved)",
            "spec.tools[] (Tool Kind)": "plain-function stubs → Agent(tools=[...])",
        }
