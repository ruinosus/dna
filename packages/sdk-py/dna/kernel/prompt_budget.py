"""Prompt-budget estimation + enforcement helpers.

Conservative token estimator + instruction-budget evaluator used by the
write-path guard (``dna.extensions.helix.write_guards.prompt_budget_guard``)
that vetoes a strict/voice Agent whose instruction exceeds its model's
``instruction_token_cap`` and warns for chat models. TS twin:
``src/kernel/prompt-budget.ts`` (CHARS_PER_TOKEN = 3.5 on both sides).

CONTRACT — never hardcode token caps: the ``cap`` the evaluator receives
ALWAYS comes from the ModelProfile registry
(``kernel.model_profile(id_or_alias)``), never from a literal in code.
Motivated by a real outage: a 17269-token voice persona silently exceeded
the realtime model's 16384-token session-instructions cap.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

CHARS_PER_TOKEN = 3.5  # conservative (over-counts); mirrors instruction-budget.ts


class PromptBudgetExceededError(Exception):
    def __init__(self, *, model_id: str, estimated_tokens: int, cap: int, agent_name: str):
        self.model_id = model_id
        self.estimated_tokens = estimated_tokens
        self.cap = cap
        self.agent_name = agent_name
        super().__init__(
            f"Agent '{agent_name}' instruction is ~{estimated_tokens} tokens, "
            f"over the {cap}-token instruction cap of model '{model_id}'. "
            f"Trim the instruction or move detail to tool-discoverable docs. "
            f"(The cap comes from the model's ModelProfile doc — update the "
            f"profile if the model's real cap changed; never hardcode caps.)"
        )


def estimate_tokens(char_count: int) -> int:
    return math.ceil(char_count / CHARS_PER_TOKEN)


@dataclass
class BudgetVerdict:
    exceeded: bool
    estimated_tokens: int
    cap: int


def evaluate_instruction_budget(instruction: str, *, cap: int) -> BudgetVerdict:
    tok = estimate_tokens(len(instruction or ""))
    return BudgetVerdict(exceeded=tok > cap, estimated_tokens=tok, cap=cap)
