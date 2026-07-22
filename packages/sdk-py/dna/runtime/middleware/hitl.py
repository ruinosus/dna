"""Canonical HITL: the LangChain HumanInTheLoopMiddleware, configured from the
def's requires_confirmation tools + the host's local confirm tools. No
DNA-custom interrupt/resume shape — action_requests / decisions."""
from __future__ import annotations


def dna_hitl_middleware(confirm_tools, extra_confirm=None, *, allowed_decisions=("approve", "edit", "reject")):
    from langchain.agents.middleware import HumanInTheLoopMiddleware

    tools = list(confirm_tools) + list(extra_confirm or [])
    interrupt_on = {
        t: {"allowed_decisions": list(allowed_decisions)} for t in tools
    }
    return HumanInTheLoopMiddleware(interrupt_on=interrupt_on)
