"""Solution A — hand-rolled prompt composer over a YAML folder + Pydantic.

Mirrors DNA's `build_prompt` for the same agent: persona-first layout composes
Soul body, then the agent instruction, then the guardrail block (last, as hard
policy). Skills are declared capability refs — like DNA's default layouts, they
are validated + wired but NOT inlined into the prompt.

Usage:
    python compose.py support
    python compose.py billing
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from models import Agent, Guardrail, Skill, Soul

ROOT = Path(__file__).resolve().parent


def _load_one(kind_dir: str, name: str, model):
    raw = yaml.safe_load((ROOT / kind_dir / f"{name}.yaml").read_text())
    return model.model_validate(raw)


def load_agent(name: str) -> Agent:
    return _load_one("agents", name, Agent)


def _guardrail_block(g: Guardrail) -> str:
    out = f"## Guardrail: {g.name} ({g.severity})\n"
    if g.description:
        out += f"_{g.description}_\n\n"
    for rule in g.rules:
        out += f"- {rule}\n"
    return out


def build_prompt(agent_name: str) -> str:
    agent = load_agent(agent_name)

    # Validate every referenced dependency exists + is well-formed (fail loud).
    soul = _load_one("souls", agent.soul, Soul) if agent.soul else None
    for skill_name in agent.skills:
        _load_one("skills", skill_name, Skill)  # validated, not inlined
    guardrails = [_load_one("guardrails", g, Guardrail) for g in agent.guardrails]

    soul_body = soul.body.strip() if soul else ""
    instruction = agent.instruction.strip()

    if agent.layout == "persona-first":
        parts = [soul_body, instruction]
    else:  # instruction-first
        parts = [instruction, soul_body]

    prompt = "\n\n".join(p for p in parts if p)
    if guardrails:
        prompt += "\n\n" + "".join(_guardrail_block(g) for g in guardrails)
    return prompt.rstrip("\n")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "support"
    print(build_prompt(which))
