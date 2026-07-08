"""Prompt-budget estimation + enforcement helpers.

Conservative token estimator + instruction-budget evaluator used by the
write-path guard that blocks voice Agents whose instruction exceeds
the realtime model's instruction_token_cap. Mirrors the Studio client guard
apps/studio/src/lib/voice/instruction-budget.ts (CHARS_PER_TOKEN = 3.5) so
client and server agree. Motivated by the 2026-05-29 JARVIS bug (17269-token
persona > gpt-realtime-2's 16384-token session.instructions cap).
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
            f"Trim the persona (s-jarvis-persona-trim-to-budget) or move detail to "
            f"tool-discoverable docs."
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
