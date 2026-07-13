"""Solution A — a hand-rolled emitter for ONE target (LangGraph).

The baseline has no portability out of the box: to run the composed agent on a
runtime you write an emitter per target. This is the LangGraph one. DNA ships
seven such emitters (agent-framework, bedrock, vertex, openai-agents, langgraph,
agno, deepagents) behind `dna emit --target ...`; this file is the honest cost
of matching ONE of them.

    python emit_langgraph.py support
"""
from __future__ import annotations

import sys

from compose import build_prompt, load_agent


def emit(agent_name: str) -> str:
    agent = load_agent(agent_name)
    instructions = build_prompt(agent_name)
    return (
        '"""Hand-emitted LangGraph ReAct agent: ' + agent.name + '."""\n'
        "from langgraph.prebuilt import create_react_agent\n\n"
        f"INSTRUCTIONS = {instructions!r}\n\n"
        "agent = create_react_agent(\n"
        f"    model={agent.model!r},\n"
        "    tools=[],\n"
        "    prompt=INSTRUCTIONS,\n"
        f"    name={agent.name!r},\n"
        ")\n"
    )


if __name__ == "__main__":
    print(emit(sys.argv[1] if len(sys.argv) > 1 else "support"))
