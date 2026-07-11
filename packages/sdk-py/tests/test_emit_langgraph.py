"""``dna.emit`` — DNA → LangGraph emitter (code-first scaffold target,
s-emit-langgraph).

A code-first runtime has no declarative agent format, so the emitter fills a
curated ``{langgraph × case}`` template instead of generating code ad-hoc. These
tests pin:

1. **Case selection** — WITH tools → ``with-tools`` (the ReAct idiom, ``@tool``
   stubs); WITHOUT tools → ``prompt-only``.
2. **The byte-equal invariant** — the emitted ``INSTRUCTIONS`` constant is
   byte-equal to ``build_prompt`` (recovered via the contract's AST hook).
3. **Syntactic validity** — the emitted source ``py_compile``s.
4. **Model coordinate PRESERVED** — LangGraph resolves the string via
   ``init_chat_model``, so the DNA coordinate is carried verbatim (not stripped).
5. **Honest losses** — tool bodies are stubs; the model-coordinate convention and
   the DNA-only axes are reported.
"""
from __future__ import annotations

import pathlib
import py_compile
import tempfile

import pytest

from dna.emit import EmitContext, available_targets, emit_agent, get_emitter
from dna.emit.langgraph import LanggraphEmitter
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


def test_langgraph_is_registered() -> None:
    assert "langgraph" in available_targets()
    assert isinstance(get_emitter("langgraph"), LanggraphEmitter)


def test_with_tools_emit_byte_equal_and_compiles(mi) -> None:
    result = emit_agent(mi, _AGENT, "langgraph")  # concierge HAS a tool
    assert result.filename == "concierge.py"
    assert "from langgraph.prebuilt import create_react_agent" in result.artifact
    assert "from langchain_core.tools import tool" in result.artifact
    assert "@tool" in result.artifact
    assert "def kb_search()" in result.artifact
    assert "prompt=INSTRUCTIONS" in result.artifact
    assert _compiles(result.artifact)
    recovered = get_emitter("langgraph").extract_instructions(result.artifact)
    assert recovered == mi.build_prompt(_AGENT)


def test_prompt_only_emit_byte_equal_and_compiles() -> None:
    ctx = EmitContext(name="greeter", description="", instructions="Be brief.\nSay hi.",
                      model="openai:gpt-4o")
    result = LanggraphEmitter().emit(ctx)
    assert "@tool" not in result.artifact
    assert "tools=[]" in result.artifact
    # model coordinate PRESERVED (provider token NOT stripped, unlike openai-agents)
    assert "model='openai:gpt-4o'" in result.artifact
    assert _compiles(result.artifact)
    assert LanggraphEmitter().extract_instructions(result.artifact) == "Be brief.\nSay hi."


def test_model_coordinate_preserved_and_reported() -> None:
    ctx = EmitContext(name="a", description="", instructions="x", model="azure/gpt-4o")
    result = LanggraphEmitter().emit(ctx)
    assert "model='azure/gpt-4o'" in result.artifact
    assert any("model coordinate" in loss for loss in result.losses)


def test_tool_body_reported_as_loss(mi) -> None:
    result = emit_agent(mi, _AGENT, "langgraph")
    assert any("tool body" in loss for loss in result.losses)


def test_unbound_model_omits_and_reports() -> None:
    ctx = EmitContext(name="a", description="", instructions="x", model=None)
    result = LanggraphEmitter().emit(ctx)
    assert "model=" not in result.artifact
    assert any("model unbound" in loss and "REQUIRES a model" in loss for loss in result.losses)
