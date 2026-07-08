"""s-realtime-model-single-default — the realtime fallback the kernel's
prompt-budget gate caps against resolves through ONE env (DNA_VOICE_REALTIME_MODEL),
the SAME one the voice server pins on. Asserts the kernel reads the env at
access-time (so a pin set after import still applies) and falls back to the
literal otherwise — no drift between the cap target and the minted session.
"""
from __future__ import annotations

from dna.kernel import Kernel


def test_default_realtime_model_falls_back_to_literal(monkeypatch):
    monkeypatch.delenv("DNA_VOICE_REALTIME_MODEL", raising=False)
    k = Kernel()
    assert k._DEFAULT_REALTIME_MODEL == "gpt-realtime-2"
    assert k._DEFAULT_REALTIME_MODEL_FALLBACK == "gpt-realtime-2"


def test_env_pins_the_realtime_model(monkeypatch):
    k = Kernel()
    # access-time read — pin set after the kernel was built still applies,
    # so the prompt-budget cap can't drift from the voice server's pin.
    monkeypatch.setenv("DNA_VOICE_REALTIME_MODEL", "gpt-realtime-2-2026-05-07")
    assert k._DEFAULT_REALTIME_MODEL == "gpt-realtime-2-2026-05-07"
