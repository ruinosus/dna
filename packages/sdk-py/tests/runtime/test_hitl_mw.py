from dna.runtime.middleware.hitl import dna_hitl_middleware


def test_configures_canonical_hitl_for_every_confirm_tool():
    mw = dna_hitl_middleware(["remember", "forget"], extra_confirm=["update_memory_draft"])
    cfg = mw.interrupt_on  # dict[tool -> InterruptOnConfig]
    assert set(cfg) == {"remember", "forget", "update_memory_draft"}
    assert list(cfg["remember"]["allowed_decisions"]) == ["approve", "edit", "reject"]
