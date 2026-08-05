"""Canonical HITL: the LangChain HumanInTheLoopMiddleware, configured from the
def's requires_confirmation tools + the host's local confirm tools. No
DNA-custom interrupt/resume shape — action_requests / decisions.

The one DNA addition is the WHY channel (s-hitl-por-que-mcp-writes): every
gated tool gets an `InterruptOnConfig.description` FACTORY — the canonical
middleware's own extension point (`description: str | _DescriptionFactory`,
called with `(tool_call, state, runtime)` at interrupt time) — that reads the
model's stated reason from `tool_call["args"]["rationale"]` (the optional arg
`DnaMcpToolsMiddleware` injects into gated MCP tool schemas and strips again
before execution). With a rationale, the interrupt's `description` IS the
model's reason, verbatim — the approval card renders it as the "Why". Without
one, the factory reproduces the canonical default machinery BYTE-IDENTICALLY
("Tool execution requires approval\\n\\nTool: …\\nArgs: …"), which the portal
already recognizes as machinery and degrades to absence — so behavior without
a rationale is indistinguishable from today's.
"""
from __future__ import annotations

# Parity anchor: HumanInTheLoopMiddleware's default `description_prefix`. The
# portal's `rationaleOf` treats a description starting with this prefix as
# machinery (no rationale) — so the no-rationale branch below must keep
# producing it, byte-identical to the canonical default.
_DEFAULT_DESCRIPTION_PREFIX = "Tool execution requires approval"


def _rationale_description(tool_call, state, runtime) -> str:
    """`_DescriptionFactory` for every gated tool: the model's `rationale`
    verbatim when it sent one, else the canonical default machinery string
    (byte-identical to `HumanInTheLoopMiddleware._create_action_and_config`'s
    no-description branch, so downstream consumers cannot tell the factory
    was ever configured)."""
    args = tool_call.get("args") or {}
    rationale = args.get("rationale")
    if isinstance(rationale, str) and rationale.strip():
        return rationale.strip()
    return (
        f"{_DEFAULT_DESCRIPTION_PREFIX}\n\n"
        f"Tool: {tool_call['name']}\nArgs: {tool_call['args']}"
    )


def dna_hitl_middleware(confirm_tools, extra_confirm=None, *, allowed_decisions=("approve", "edit", "reject")):
    from langchain.agents.middleware import HumanInTheLoopMiddleware

    tools = list(confirm_tools) + list(extra_confirm or [])
    interrupt_on = {
        t: {
            "allowed_decisions": list(allowed_decisions),
            "description": _rationale_description,
        }
        for t in tools
    }
    return HumanInTheLoopMiddleware(interrupt_on=interrupt_on)
