from types import SimpleNamespace
from dna.runtime.middleware.allowlist import DnaAllowlistMiddleware

def test_wrap_model_call_drops_non_allowlisted_tools():
    mw = DnaAllowlistMiddleware(frozenset({"recall", "remember"}))
    captured = {}
    def handler(req):
        captured["tools"] = [t.name for t in req.tools]
        return "RESP"
    req = SimpleNamespace(tools=[SimpleNamespace(name=n) for n in ("recall", "create_story", "remember")])
    out = mw.wrap_model_call(req, handler)
    assert out == "RESP"
    assert captured["tools"] == ["recall", "remember"]  # create_story dropped, fail-closed
