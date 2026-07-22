import asyncio
from types import SimpleNamespace
from dna.runtime.middleware.compose_prompt import DnaComposePromptMiddleware

def test_sets_composed_prompt_and_degrades():
    async def ok_compose(_): return "COMPOSED"
    async def handler(req): return req.system_message
    mw = DnaComposePromptMiddleware(ok_compose, fallback="FALLBACK")
    req = SimpleNamespace(system_message=None, state={})
    assert asyncio.run(mw.awrap_model_call(req, handler)) == "COMPOSED"
    async def bad_compose(_): raise RuntimeError("mcp down")
    mw2 = DnaComposePromptMiddleware(bad_compose, fallback="FALLBACK")
    req2 = SimpleNamespace(system_message=None, state={})
    assert asyncio.run(mw2.awrap_model_call(req2, handler)) == "FALLBACK"
