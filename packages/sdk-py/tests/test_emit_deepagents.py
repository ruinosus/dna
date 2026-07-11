"""``dna.emit`` — DNA → DeepAgents emitter (code-first scaffold target,
s-emit-deepagents).

Pins case selection, the byte-equal invariant (on the emitted ``INSTRUCTIONS``
constant, which is a PREFIX of the effective system prompt), syntactic validity,
the PRESERVED model coordinate, and honest losses (harness prompt / no name slot).
"""
from __future__ import annotations

import pathlib
import py_compile
import tempfile

import pytest

from dna.emit import EmitContext, available_targets, emit_agent, get_emitter
from dna.emit.deepagents import DeepAgentsEmitter
from dna.kernel import Kernel

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"
_AGENT = "concierge"


@pytest.fixture()
def mi():
    return Kernel.quick(_SCOPE, base_dir=_BASE)


def _compiles(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        path = fh.name
    try:
        py_compile.compile(path, doraise=True)
        return True
    except py_compile.PyCompileError:
        return False


def test_deepagents_is_registered() -> None:
    assert "deepagents" in available_targets()
    assert isinstance(get_emitter("deepagents"), DeepAgentsEmitter)


def test_with_tools_emit_byte_equal_and_compiles(mi) -> None:
    result = emit_agent(mi, _AGENT, "deepagents")  # concierge HAS a tool
    assert result.filename == "concierge.py"
    assert "from deepagents import create_deep_agent" in result.artifact
    assert "def kb_search()" in result.artifact
    assert "system_prompt=INSTRUCTIONS" in result.artifact
    assert "tools=[kb_search]" in result.artifact
    assert _compiles(result.artifact)
    recovered = get_emitter("deepagents").extract_instructions(result.artifact)
    assert recovered == mi.build_prompt(_AGENT)


def test_prompt_only_emit_byte_equal_and_compiles() -> None:
    ctx = EmitContext(name="greeter", description="", instructions="Be brief.\nSay hi.",
                      model="anthropic:claude-sonnet-4")
    result = DeepAgentsEmitter().emit(ctx)
    assert "def " not in result.artifact.split("INSTRUCTIONS")[1]  # no tool stubs
    assert "tools=[]" in result.artifact
    assert "model='anthropic:claude-sonnet-4'" in result.artifact  # coordinate PRESERVED
    assert _compiles(result.artifact)
    assert DeepAgentsEmitter().extract_instructions(result.artifact) == "Be brief.\nSay hi."


def test_harness_prompt_and_name_reported_as_loss(mi) -> None:
    result = emit_agent(mi, _AGENT, "deepagents")
    assert any("harness prompt" in loss for loss in result.losses)
    assert any("metadata.name" in loss for loss in result.losses)


def test_unbound_model_omits_and_falls_back() -> None:
    ctx = EmitContext(name="a", description="", instructions="x", model=None)
    result = DeepAgentsEmitter().emit(ctx)
    assert "model=" not in result.artifact
    assert any("model unbound" in loss and "default deep-agent model" in loss
               for loss in result.losses)
