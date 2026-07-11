"""``dna.emit`` — the PORTABILITY proof: ONE DNA source → SEVEN runtimes, the
composed instruction byte-identical in every emitted artifact (s-emit-deepagents).

This is the thesis of DNA-as-Terraform made a test: author the `concierge` agent
ONCE (Agent + Soul + Guardrail + Tool), and `dna emit` materializes the native
artifact for every registered runtime — three config-declarative
(agent-framework / bedrock / vertex) and four code-first scaffolds (openai-agents /
langgraph / agno / deepagents) — with the DNA-composed prompt carried byte-equal
across ALL of them. The same author-time definition, materialized seven ways.
"""
from __future__ import annotations

import pathlib

import pytest

from dna.emit import available_targets, emit_agent, get_emitter
from dna.kernel import Kernel

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"
_AGENT = "concierge"

#: The seven runtimes the one `concierge` source emits to.
_SEVEN_RUNTIMES = {
    "agent-framework",  # config-declarative — Microsoft PromptAgent YAML
    "bedrock",          # config-declarative — AWS::Bedrock::Agent CloudFormation
    "vertex",           # config-declarative — Google ADK Agent Config
    "openai-agents",    # code-first scaffold — OpenAI Agents SDK
    "langgraph",        # code-first scaffold — LangGraph create_react_agent
    "agno",             # code-first scaffold — Agno Agent
    "deepagents",       # code-first scaffold — LangChain DeepAgents
}


@pytest.fixture()
def mi():
    return Kernel.quick(_SCOPE, base_dir=_BASE)


def test_seven_runtimes_are_registered() -> None:
    assert _SEVEN_RUNTIMES.issubset(set(available_targets()))
    assert len(_SEVEN_RUNTIMES) == 7


def test_one_source_seven_runtimes_instruction_byte_identical(mi) -> None:
    """The SAME concierge source emits to all seven runtimes with an instruction
    that is byte-identical (== build_prompt) in every artifact."""
    expected = mi.build_prompt(_AGENT)
    recovered_by_target: dict[str, str] = {}
    for target in _SEVEN_RUNTIMES:
        result = emit_agent(mi, _AGENT, target)
        recovered = get_emitter(target).extract_instructions(result.artifact)
        assert recovered is not None, f"{target} carries no recoverable instruction"
        recovered_by_target[target] = recovered

    # every target recovered the composed prompt …
    for target, recovered in recovered_by_target.items():
        assert recovered == expected, f"{target} instruction drifted from build_prompt"
    # … so they are all identical to each other — one prompt, seven artifacts.
    assert len(set(recovered_by_target.values())) == 1
