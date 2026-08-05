"""dna_hitl_middleware — canonical HumanInTheLoopMiddleware wiring + the WHY
channel (s-hitl-por-que-mcp-writes): every gated tool carries a description
FACTORY that surfaces the model's `rationale` arg verbatim on the interrupt,
and degrades BYTE-IDENTICALLY to the canonical default machinery without one.

Parity is asserted THROUGH the door (`after_model` → captured `interrupt()`
payload) against the canonical middleware's own output for the same tool call
— never against a copied literal that could drift.
"""
from langchain_core.messages import AIMessage

from dna.runtime.middleware.hitl import dna_hitl_middleware


def test_configures_canonical_hitl_for_every_confirm_tool():
    mw = dna_hitl_middleware(["remember", "forget"], extra_confirm=["update_memory_draft"])
    cfg = mw.interrupt_on  # dict[tool -> InterruptOnConfig]
    assert set(cfg) == {"remember", "forget", "update_memory_draft"}
    assert list(cfg["remember"]["allowed_decisions"]) == ["approve", "edit", "reject"]


def test_every_gated_tool_carries_the_same_description_factory():
    mw = dna_hitl_middleware(["remember"], extra_confirm=["local_write"])
    factories = {name: cfg.get("description") for name, cfg in mw.interrupt_on.items()}
    assert all(callable(f) for f in factories.values())
    assert factories["remember"] is factories["local_write"]  # one rule, not copies


# --- through the door: after_model → the captured interrupt() payload -------


def _captured_action_requests(mw, tool_call, monkeypatch):
    """Drive the CANONICAL `after_model` with `interrupt` captured — returns
    the `action_requests` the portal would receive on the wire."""
    captured = {}

    def fake_interrupt(hitl_request):
        captured["request"] = hitl_request
        return {"decisions": [{"type": "approve"}] * len(hitl_request["action_requests"])}

    monkeypatch.setattr(
        "langchain.agents.middleware.human_in_the_loop.interrupt", fake_interrupt
    )
    ai = AIMessage(content="", tool_calls=[tool_call])
    state = {"messages": [ai]}
    runtime = object()  # only threaded to the description factory, which ignores it
    mw.after_model(state, runtime)
    return captured["request"]["action_requests"]


def test_interrupt_description_is_the_models_rationale_verbatim(monkeypatch):
    mw = dna_hitl_middleware(["remember"])
    tool_call = {
        "name": "remember",
        "args": {
            "summary": "Barna prefere deploys por release",
            "rationale": "Você pediu que eu guardasse essa preferência de deploy.",
        },
        "id": "c1",
        "type": "tool_call",
    }
    (req,) = _captured_action_requests(mw, tool_call, monkeypatch)
    assert req["description"] == "Você pediu que eu guardasse essa preferência de deploy."
    # Args ride verbatim — the rationale arg is stripped at EXECUTION
    # (DnaMcpToolsMiddleware), never from the wire the human reviews.
    assert req["args"]["summary"] == "Barna prefere deploys por release"


def test_without_rationale_description_is_byte_identical_to_canonical_default(monkeypatch):
    """The backward-compat contract: with no rationale, the factory's output
    must be indistinguishable from the canonical middleware configured with NO
    description at all — asserted against the canonical output itself."""
    from langchain.agents.middleware import HumanInTheLoopMiddleware

    tool_call = {
        "name": "remember",
        "args": {"summary": "x", "tags": ["a"]},
        "id": "c1",
        "type": "tool_call",
    }
    canonical = HumanInTheLoopMiddleware(
        interrupt_on={"remember": {"allowed_decisions": ["approve", "edit", "reject"]}}
    )
    (canonical_req,) = _captured_action_requests(canonical, dict(tool_call), monkeypatch)

    ours = dna_hitl_middleware(["remember"])
    (our_req,) = _captured_action_requests(ours, dict(tool_call), monkeypatch)

    assert our_req["description"] == canonical_req["description"]
    # And it IS the machinery shape the portal's rationaleOf degrades to null.
    assert our_req["description"].startswith("Tool execution requires approval")


def test_blank_or_junk_rationale_degrades_to_the_default_machinery(monkeypatch):
    mw = dna_hitl_middleware(["forget"])
    for junk in ("   ", "", 42, None, ["not", "a", "string"]):
        args = {"name": "old-memory"}
        if junk is not None:
            args["rationale"] = junk
        tool_call = {"name": "forget", "args": args, "id": "c1", "type": "tool_call"}
        (req,) = _captured_action_requests(mw, tool_call, monkeypatch)
        assert req["description"].startswith("Tool execution requires approval"), (
            f"junk rationale {junk!r} must degrade to machinery, got: {req['description']!r}"
        )


def test_rationale_is_trimmed_but_otherwise_verbatim(monkeypatch):
    mw = dna_hitl_middleware(["consolidate"])
    tool_call = {
        "name": "consolidate",
        "args": {"apply": True, "rationale": "  Re-score pedido pelo usuário.  "},
        "id": "c1",
        "type": "tool_call",
    }
    (req,) = _captured_action_requests(mw, tool_call, monkeypatch)
    assert req["description"] == "Re-score pedido pelo usuário."
