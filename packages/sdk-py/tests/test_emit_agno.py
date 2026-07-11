"""``dna.emit`` — DNA → Agno emitter (code-first scaffold target, s-emit-agno).

Pins case selection, the byte-equal invariant, syntactic validity, the PRESERVED
model coordinate (Agno takes a `provider:model` string), and honest losses.
"""
from __future__ import annotations

import pathlib
import py_compile
import tempfile

import pytest

from dna.emit import EmitContext, available_targets, emit_agent, get_emitter
from dna.emit.agno import AgnoEmitter
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


def test_agno_is_registered() -> None:
    assert "agno" in available_targets()
    assert isinstance(get_emitter("agno"), AgnoEmitter)


def test_with_tools_emit_byte_equal_and_compiles(mi) -> None:
    result = emit_agent(mi, _AGENT, "agno")  # concierge HAS a tool
    assert result.filename == "concierge.py"
    assert "from agno.agent import Agent" in result.artifact
    assert "def kb_search()" in result.artifact
    assert "instructions=INSTRUCTIONS" in result.artifact
    assert "tools=[kb_search]" in result.artifact
    assert "name='concierge'" in result.artifact
    assert _compiles(result.artifact)
    recovered = get_emitter("agno").extract_instructions(result.artifact)
    assert recovered == mi.build_prompt(_AGENT)


def test_prompt_only_emit_byte_equal_and_compiles() -> None:
    ctx = EmitContext(name="greeter", description="", instructions="Be brief.\nSay hi.",
                      model="openai:gpt-4o")
    result = AgnoEmitter().emit(ctx)
    assert "tools=" not in result.artifact  # prompt-only omits the tools kwarg
    assert "model='openai:gpt-4o'" in result.artifact  # coordinate PRESERVED
    assert _compiles(result.artifact)
    assert AgnoEmitter().extract_instructions(result.artifact) == "Be brief.\nSay hi."


def test_tool_body_reported_as_loss(mi) -> None:
    result = emit_agent(mi, _AGENT, "agno")
    assert any("tool body" in loss for loss in result.losses)


def test_unbound_model_omits_and_reports() -> None:
    ctx = EmitContext(name="a", description="", instructions="x", model=None)
    result = AgnoEmitter().emit(ctx)
    assert "model=" not in result.artifact
    assert any("model unbound" in loss for loss in result.losses)
