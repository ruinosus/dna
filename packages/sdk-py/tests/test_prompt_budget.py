from dna.kernel.prompt_budget import (
    estimate_tokens, evaluate_instruction_budget, PromptBudgetExceededError,
)

def test_estimate_tokens_over_counts():
    # mirror the Studio guard: 60488 chars must estimate >= the real 17269 tokens
    assert estimate_tokens(60488) >= 17269

def test_evaluate_under_cap_ok():
    verdict = evaluate_instruction_budget("short", cap=16384)
    assert verdict.exceeded is False

def test_evaluate_over_cap_flags():
    verdict = evaluate_instruction_budget("x" * 80000, cap=16384)
    assert verdict.exceeded is True
    assert verdict.estimated_tokens > 16384

def test_error_carries_context():
    e = PromptBudgetExceededError(
        model_id="gpt-realtime-2", estimated_tokens=17269, cap=16384, agent_name="jarvis",
    )
    assert "jarvis" in str(e) and "16384" in str(e)
