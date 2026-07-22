import asyncio
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, SystemMessage

from dna.runtime.middleware.compose_prompt import DnaComposePromptMiddleware


def test_sets_composed_prompt_and_degrades():
    async def ok_compose(_): return "COMPOSED"
    async def handler(req): return req.system_message
    mw = DnaComposePromptMiddleware(ok_compose, fallback="FALLBACK")
    req = SimpleNamespace(system_message=None, state={})
    result = asyncio.run(mw.awrap_model_call(req, handler))
    assert isinstance(result, SystemMessage)
    assert not isinstance(result, HumanMessage)
    assert result.content == "COMPOSED"

    async def bad_compose(_): raise RuntimeError("mcp down")
    mw2 = DnaComposePromptMiddleware(bad_compose, fallback="FALLBACK")
    req2 = SimpleNamespace(system_message=None, state={})
    result2 = asyncio.run(mw2.awrap_model_call(req2, handler))
    assert isinstance(result2, SystemMessage)
    assert not isinstance(result2, HumanMessage)
    assert result2.content == "FALLBACK"


def test_composed_prompt_is_a_real_system_message_not_human():
    """i-040 regression: request.system_message must be delivered as a
    SystemMessage, not a plain str (langchain coerces a bare str assigned to
    request.system_message into a HumanMessage, which puts the persona on a
    USER turn instead of the system turn)."""
    async def ok_compose(_): return "COMPOSED PERSONA"

    captured = {}

    async def handler(req):
        captured["system_message"] = req.system_message
        return req.system_message

    mw = DnaComposePromptMiddleware(ok_compose, fallback="FALLBACK")
    req = SimpleNamespace(system_message=None, state={})
    asyncio.run(mw.awrap_model_call(req, handler))

    msg = captured["system_message"]
    assert isinstance(msg, SystemMessage)
    assert not isinstance(msg, HumanMessage)
    assert msg.content == "COMPOSED PERSONA"


def test_degrade_path_is_also_a_real_system_message():
    """Same guarantee must hold on the degrade-on-error path."""
    async def bad_compose(_): raise RuntimeError("mcp down")

    captured = {}

    async def handler(req):
        captured["system_message"] = req.system_message
        return req.system_message

    mw = DnaComposePromptMiddleware(bad_compose, fallback="FALLBACK")
    req = SimpleNamespace(system_message=None, state={})
    asyncio.run(mw.awrap_model_call(req, handler))

    msg = captured["system_message"]
    assert isinstance(msg, SystemMessage)
    assert not isinstance(msg, HumanMessage)
    assert msg.content == "FALLBACK"
