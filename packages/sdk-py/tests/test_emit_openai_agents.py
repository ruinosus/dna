"""``dna.emit`` — DNA → OpenAI Agents SDK emitter (the first CODE-FIRST target,
s-emit-port-contract).

The scaffold flavor of the EmitterPort: a code-first runtime has no declarative
agent format, so the emitter fills a curated ``{framework × case}`` template
instead of generating code ad-hoc. These tests pin:

1. **Case selection** — ``select_scaffold`` routes from the ctx's DNA signals: an
   agent WITH tools → ``with-tools``; WITHOUT tools → ``prompt-only``. That is the
   whole scaffold mechanism: *selection + fill*, never codegen.
2. **The byte-equal invariant** — the emitted ``INSTRUCTIONS`` constant is
   byte-equal to ``build_prompt`` (recovered via the contract's
   ``extract_instructions`` AST hook), in BOTH cases.
3. **Syntactic validity** — the emitted source ``py_compile``s (it is real,
   loadable Python, not a sketch).
4. **Honest losses** — tool bodies are stubs; the DNA-only axes have no slot.
"""
from __future__ import annotations

import pathlib
import py_compile
import tempfile

import pytest

from dna.emit import EmitContext, available_targets, emit_agent, get_emitter
from dna.emit.openai_agents import OpenAIAgentsEmitter, _bare_model_id
from dna.emit.scaffold import classify_case, select_scaffold
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


# ── 1. case selection (the classifier) ──────────────────────────────────────


def test_classify_case_from_dna_signals() -> None:
    no_tools = EmitContext(name="a", description="", instructions="x")
    with_tools = EmitContext(name="a", description="", instructions="x",
                             tools=[{"name": "t", "description": "d", "parameters": {}}])
    structured = EmitContext(name="a", description="", instructions="x",
                             output_schema={"type": "object"})
    assert classify_case(no_tools) == "prompt-only"
    assert classify_case(with_tools) == "with-tools"
    assert classify_case(structured) == "structured-output"


def test_select_scaffold_picks_with_tools_when_tools_present() -> None:
    ctx = EmitContext(name="a", description="", instructions="x",
                      tools=[{"name": "t", "description": "d", "parameters": {}}])
    choice = select_scaffold("openai-agents", ctx)
    assert choice.case == "with-tools"
    assert "function_tool" in choice.template


def test_select_scaffold_picks_prompt_only_without_tools() -> None:
    ctx = EmitContext(name="a", description="", instructions="x")
    choice = select_scaffold("openai-agents", ctx)
    assert choice.case == "prompt-only"
    assert "function_tool" not in choice.template


def test_structured_output_falls_back_and_records_loss() -> None:
    """`structured-output` is not shipped for openai-agents yet → falls back to
    `with-tools`, and the fallback is reported as a loss (honest de-para)."""
    ctx = EmitContext(name="a", description="", instructions="x",
                      tools=[{"name": "t", "description": "d", "parameters": {}}],
                      output_schema={"type": "object"})
    choice = select_scaffold("openai-agents", ctx)
    assert choice.requested == "structured-output"
    assert choice.case == "with-tools"  # closest shipped template
    result = OpenAIAgentsEmitter().emit(ctx)
    assert any("scaffold case" in loss for loss in result.losses)


# ── 2 + 3. byte-equal invariant + syntactic validity, both cases ────────────


def test_with_tools_emit_byte_equal_and_compiles(mi) -> None:
    result = emit_agent(mi, _AGENT, "openai-agents")  # concierge HAS a tool
    assert result.filename == "concierge.py"
    assert "from agents import Agent, function_tool" in result.artifact
    assert "def kb_search()" in result.artifact
    assert _compiles(result.artifact)
    recovered = get_emitter("openai-agents").extract_instructions(result.artifact)
    assert recovered == mi.build_prompt(_AGENT)


def test_prompt_only_emit_byte_equal_and_compiles() -> None:
    ctx = EmitContext(name="greeter", description="", instructions="Be brief.\nSay hi.",
                      model="openai:gpt-4o")
    result = OpenAIAgentsEmitter().emit(ctx)
    assert "function_tool" not in result.artifact
    assert "model='gpt-4o'" in result.artifact
    assert _compiles(result.artifact)
    assert OpenAIAgentsEmitter().extract_instructions(result.artifact) == "Be brief.\nSay hi."


# ── 4. registry + honest losses + helpers ───────────────────────────────────


def test_openai_agents_is_registered() -> None:
    assert "openai-agents" in available_targets()
    assert isinstance(get_emitter("openai-agents"), OpenAIAgentsEmitter)


def test_tool_body_reported_as_loss(mi) -> None:
    result = emit_agent(mi, _AGENT, "openai-agents")
    assert any("tool body" in loss for loss in result.losses)


@pytest.mark.parametrize(
    "model,expected",
    [
        ("openai:gpt-4o", "gpt-4o"),
        ("azure/gpt-4o", "gpt-4o"),
        ("gpt-4o", "gpt-4o"),
        (None, None),
    ],
)
def test_bare_model_id(model, expected) -> None:
    assert _bare_model_id(model) == expected
