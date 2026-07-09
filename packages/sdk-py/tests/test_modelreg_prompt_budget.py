"""s-tier-a-modelprofile — ModelProfile Kind + prompt-budget write guard.

Covers the two halves shipped together:

1. The ``modelreg`` extension registers ModelProfile from its descriptor
   (``kinds/model-profile.kind.yaml`` — record plane, GLOBAL, generated-
   convention alias) and ``kernel.model_profile`` resolves it from ``_lib``
   by ``model_id`` then ``aliases[]``.
2. The helix ``prompt_budget_guard`` three paths (never hardcode token
   caps — every cap below comes from a ModelProfile doc, never a literal
   in the production code):

   - VETO  — strict model (voice persona, or ``realtime: true`` profile)
     over ``instruction_token_cap`` → ``PromptBudgetExceededError``,
     nothing persisted.
   - WARN  — chat Agent (``spec.model``, non-realtime profile) over the
     cap → write succeeds, loud ``[prompt-budget]`` warning.
   - PASS  — no model declared / no profile found / within budget →
     write succeeds silently (enforcement is opt-in by data).

TS twin: tests/modelreg-prompt-budget.test.ts.
"""
from __future__ import annotations

import logging

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.helix import HelixExtension
from dna.extensions.modelreg import ModelRegExtension
from dna.kernel import Kernel
from dna.kernel.prompt_budget import PromptBudgetExceededError
from dna.kernel.protocols import TenantScope


# Caps chosen tiny so a short instruction crosses them; the values live in
# ModelProfile DOCS (the registry), mirroring production — the guard itself
# never carries a number.
def _profile(name: str, *, realtime: bool, cap: int | None = 100,
             aliases: list[str] | None = None) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/modelreg/v1",
        "kind": "ModelProfile",
        "metadata": {"name": name},
        "spec": {
            "model_id": name,
            "provider": "test",
            "realtime": realtime,
            "context_window": 32768,
            "instruction_token_cap": cap,
            "modalities": ["text", "audio"] if realtime else ["text"],
            "aliases": aliases or [],
        },
    }


def _agent(name: str, spec: dict) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": name},
        "spec": spec,
    }


OVER_CAP = "x" * 1000   # ~286 tokens at chars/3.5 — over a 100-token cap
UNDER_CAP = "hi there"  # ~3 tokens


async def _kernel(tmp_path) -> Kernel:
    k = Kernel()
    k.load(HelixExtension())
    k.load(ModelRegExtension())
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)
    # Profiles live in the _lib scope (model-profiles/<model_id>.yaml) —
    # kernel.model_profile queries _lib directly regardless of caller scope.
    await k.write_document(
        "_lib", "ModelProfile", "voice-strict",
        _profile("voice-strict", realtime=True, aliases=["voice-strict-preview"]),
    )
    await k.write_document(
        "_lib", "ModelProfile", "chat-friendly",
        _profile("chat-friendly", realtime=False),
    )
    # Seed the working scope so post-veto get_document asserts read an
    # existing scope dir (a vetoed FIRST write leaves no scope at all).
    await k.write_document(
        "proj", "Agent", "seed", _agent("seed", {"instruction": "seed"}),
    )
    return k


# ---------------------------------------------------------------------------
# 1. Kind registration + registry resolution
# ---------------------------------------------------------------------------

def test_model_profile_kind_registered_from_descriptor():
    k = Kernel()
    k.load(ModelRegExtension())
    kp = k.kind_port_for("ModelProfile")
    assert kp is not None
    # Generated-convention alias (<owner>-<kebab(kind)>) declared verbatim in
    # the descriptor — the EXPLICIT_ALIAS_ALLOWLIST class ratchet is untouched.
    assert kp.alias == "modelreg-model-profile"
    assert kp.plane == "record"
    # GLOBAL — a shared base registry, no per-tenant override (herdável ⇒
    # nunca TENANTED does not even apply: ModelProfile is not inheritable).
    assert kp.scope == TenantScope.GLOBAL
    assert kp.storage.container == "model-profiles"
    assert getattr(kp, "__declarative__", False) is True


@pytest.mark.asyncio
async def test_model_profile_resolves_by_id_then_alias(tmp_path):
    k = await _kernel(tmp_path)
    by_id = await k.model_profile("voice-strict")
    assert by_id is not None
    assert (by_id.get("spec") or {})["instruction_token_cap"] == 100
    by_alias = await k.model_profile("voice-strict-preview")
    assert by_alias is not None
    assert (by_alias.get("spec") or {})["model_id"] == "voice-strict"
    assert await k.model_profile("no-such-model") is None


# ---------------------------------------------------------------------------
# 2. Guard path 1 — VETO (strict/voice over cap)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_agent_over_cap_is_vetoed(tmp_path, monkeypatch):
    monkeypatch.delenv("DNA_PROMPT_BUDGET_ENFORCE", raising=False)
    k = await _kernel(tmp_path)
    with pytest.raises(PromptBudgetExceededError) as ei:
        await k.write_document(
            "proj", "Agent", "talker",
            _agent("talker", {
                "instruction": OVER_CAP,
                "voice_persona": {"model": "voice-strict"},
            }),
        )
    # Didactic error: names the agent, the estimate, the cap and the model.
    msg = str(ei.value)
    assert "talker" in msg and "100-token" in msg and "voice-strict" in msg
    assert "never hardcode caps" in msg
    # Veto happened pre-persist — nothing stored.
    assert await k.get_document("proj", "Agent", "talker") is None


@pytest.mark.asyncio
async def test_chat_agent_on_realtime_profile_is_also_strict(tmp_path, monkeypatch):
    """`realtime: true` on the PROFILE marks the model strict even without a
    voice persona on the Agent — the cap is a hard session limit."""
    monkeypatch.delenv("DNA_PROMPT_BUDGET_ENFORCE", raising=False)
    k = await _kernel(tmp_path)
    with pytest.raises(PromptBudgetExceededError):
        await k.write_document(
            "proj", "Agent", "sneaky",
            _agent("sneaky", {"instruction": OVER_CAP, "model": "voice-strict"}),
        )
    assert await k.get_document("proj", "Agent", "sneaky") is None


@pytest.mark.asyncio
async def test_kill_switch_downgrades_veto_to_warn(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("DNA_PROMPT_BUDGET_ENFORCE", "0")
    k = await _kernel(tmp_path)
    with caplog.at_level(logging.WARNING):
        await k.write_document(
            "proj", "Agent", "talker",
            _agent("talker", {
                "instruction": OVER_CAP,
                "voice_persona": {"model": "voice-strict"},
            }),
        )
    assert await k.get_document("proj", "Agent", "talker") is not None
    assert any("[prompt-budget]" in r.message and "downgraded" in r.message
               for r in caplog.records)


# ---------------------------------------------------------------------------
# 3. Guard path 2 — WARN (chat model over cap)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_agent_over_cap_warns_and_writes(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("DNA_PROMPT_BUDGET_ENFORCE", raising=False)
    k = await _kernel(tmp_path)
    with caplog.at_level(logging.WARNING):
        await k.write_document(
            "proj", "Agent", "chatty",
            _agent("chatty", {"instruction": OVER_CAP, "model": "chat-friendly"}),
        )
    assert await k.get_document("proj", "Agent", "chatty") is not None
    warned = [r for r in caplog.records if "[prompt-budget]" in r.message]
    assert warned, "chat over-cap must warn loud"
    assert "chat-friendly" in warned[0].message
    assert "instruction_token_cap" in warned[0].message


# ---------------------------------------------------------------------------
# 4. Guard path 3 — PASS (opt-in enforcement)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_without_model_passes(tmp_path, monkeypatch):
    monkeypatch.delenv("DNA_PROMPT_BUDGET_ENFORCE", raising=False)
    k = await _kernel(tmp_path)
    await k.write_document(
        "proj", "Agent", "plain",
        _agent("plain", {"instruction": OVER_CAP}),
    )
    assert await k.get_document("proj", "Agent", "plain") is not None


@pytest.mark.asyncio
async def test_chat_agent_with_unknown_model_passes(tmp_path, monkeypatch):
    monkeypatch.delenv("DNA_PROMPT_BUDGET_ENFORCE", raising=False)
    k = await _kernel(tmp_path)
    await k.write_document(
        "proj", "Agent", "mystery",
        _agent("mystery", {"instruction": OVER_CAP, "model": "not-registered"}),
    )
    assert await k.get_document("proj", "Agent", "mystery") is not None


@pytest.mark.asyncio
async def test_voice_agent_under_cap_passes(tmp_path, monkeypatch):
    monkeypatch.delenv("DNA_PROMPT_BUDGET_ENFORCE", raising=False)
    k = await _kernel(tmp_path)
    await k.write_document(
        "proj", "Agent", "brief",
        _agent("brief", {
            "instruction": UNDER_CAP,
            "voice_persona": {"model": "voice-strict"},
        }),
    )
    assert await k.get_document("proj", "Agent", "brief") is not None
