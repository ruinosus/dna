"""s-externalize-safety-judge-prompt — the LLM safety judge's persona + user
prompt + model are declarable per safety-rule (config); the inline constants are
the fallback last-resort (no hardcoded behaviour as the only path).
"""
from __future__ import annotations

from dna.safety.scanners.llm_judge import (
    _DEFAULT_JUDGE_MODEL,
    LLMJudgeScanner,
)


class _Resp:
    class _C:
        class _M:
            content = '{"on_topic": true, "detected_topic": "x", "reason": "r"}'
        message = _M()
    choices = [_C()]


class _FakeCompletions:
    def __init__(self, cap):
        self._cap = cap

    def create(self, *, model, messages, **kw):  # noqa: ANN001
        self._cap.update(model=model, system=messages[0]["content"], user=messages[1]["content"])
        return _Resp()


def _scanner_with_capture():
    sc = LLMJudgeScanner([])
    cap: dict = {}
    sc._client = type("C", (), {"chat": type("Ch", (), {"completions": _FakeCompletions(cap)})()})()
    return sc, cap


def test_rule_overrides_persona_prompt_and_model(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    sc, cap = _scanner_with_capture()
    rule = {
        "allowed": ["finance"], "denied": ["medical"],
        "judge_system": "SYS-OVERRIDE",
        "judge_prompt": "P {allowed} / {denied} / {text}",
        "model": "custom-judge-model",
    }
    sc._check_topic("hello world", rule)
    assert cap["model"] == "custom-judge-model"
    assert cap["system"] == "SYS-OVERRIDE"
    assert cap["user"] == "P finance / medical / hello world"


def test_falls_back_to_inline(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    sc, cap = _scanner_with_capture()
    sc._check_topic("hi", {"allowed": [], "denied": []})
    assert cap["model"] == _DEFAULT_JUDGE_MODEL
    assert "content classifier" in cap["system"]
    assert "Analyze this text" in cap["user"] and "Respond with JSON only" in cap["user"]


def test_env_model_overrides_default(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    sc, cap = _scanner_with_capture()
    sc._check_topic("hi", {})  # no rule model → env wins over the literal default
    assert cap["model"] == "env-model"
