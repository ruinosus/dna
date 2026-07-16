"""``dna.emit`` — the EmitterPort CONTRACT, run over EVERY registered target
(s-emit-port-contract).

Where ``test_emit_agent_framework`` / ``_bedrock`` / ``_vertex`` pin each target's
specific de-para, this suite pins the *contract itself* — the invariants EVERY
emitter must honor, asserted generically over ``available_targets()`` so a NEW
emitter inherits the checks the moment it registers:

1. **The byte-equal invariant** (the central promise): the composed instruction in
   the emitted artifact is byte-equal to ``mi.build_prompt(agent)``. Checked via
   the contract's own :meth:`EmitterPort.extract_instructions` hook, so it holds
   for config-declarative (YAML/JSON) AND scaffold (code) targets uniformly.
2. **The port shape**: ``target`` / ``file_extension`` present and consistent with
   the :class:`EmitResult` (target echoed, filename carries the extension), losses
   is a list.
3. **The registry is pluggable and honest**: ``available_targets`` is non-empty and
   ``UnknownTarget`` names the available set.
"""
from __future__ import annotations

import pathlib

import pytest

from dna.emit import (
    EmitArtifact,
    EmitResult,
    UnknownTarget,
    available_targets,
    build_emit_context,
    emit_agent,
    get_emitter,
)
from dna.kernel import Kernel

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"
_AGENT = "concierge"


@pytest.fixture()
def mi():
    return Kernel.quick(_SCOPE, base_dir=_BASE)


# ── 1. the byte-equal invariant — over EVERY registered target ──────────────


@pytest.mark.parametrize("target", available_targets())
def test_byte_equal_invariant_holds_for_every_target(mi, target: str) -> None:
    """THE contract invariant: whatever the target's native shape, the composed
    instruction it carries is the DNA-composed prompt VERBATIM. A new emitter
    inherits this the moment it appears in ``available_targets()``."""
    result = emit_agent(mi, _AGENT, target)
    emitter = get_emitter(target)
    recovered = emitter.extract_instructions(result.artifact)
    assert recovered is not None, f"{target} carries no recoverable instruction"
    assert recovered == mi.build_prompt(_AGENT)


# ── 2. the port shape — over EVERY registered target ────────────────────────


@pytest.mark.parametrize("target", available_targets())
def test_port_shape_is_consistent(mi, target: str) -> None:
    emitter = get_emitter(target)
    assert emitter.target == target
    assert isinstance(emitter.file_extension, str) and emitter.file_extension
    result = emit_agent(mi, _AGENT, target)
    assert result.target == target
    assert result.filename.endswith(emitter.file_extension)
    assert isinstance(result.losses, list)
    # every target drops the three DNA-only axes — the honest core of the de-para.
    joined = " ".join(result.losses)
    assert "composition structure" in joined
    assert "tenant overlay" in joined
    assert "eval-as-contract" in joined


# ── 3. the registry is pluggable and honest ─────────────────────────────────


def test_registry_non_empty_and_contains_both_flavors() -> None:
    targets = available_targets()
    assert targets, "no emitters registered"
    # config-declarative flavor + scaffold (code-first) flavor both present.
    assert "agent-framework" in targets  # config-declarative
    assert "openai-agents" in targets  # scaffold / code-first


def test_unknown_target_names_the_available_set() -> None:
    with pytest.raises(UnknownTarget) as ei:
        get_emitter("no-such-runtime")
    assert set(ei.value.available) == set(available_targets())


def test_build_context_is_the_shared_front_door(mi) -> None:
    """`build_emit_context` is the neutral half every target reads from — same
    context, N artifacts."""
    ctx = build_emit_context(mi, _AGENT)
    assert ctx.instructions == mi.build_prompt(_AGENT)
    assert ctx.name == _AGENT


# ── 4. multi-artifact EmitResult (back-compat single) ───────────────────────


def test_multi_artifact_byte_equal_on_agent_role():
    """A multi-artifact emit carries the byte-equal instruction on the
    ``role="agent"`` entry; other roles (serving, …) ride alongside."""
    res = EmitResult(
        target="x",
        artifacts=[
            EmitArtifact(path="agent.py", content="INSTRUCTIONS = 'hi'\n", role="agent"),
            EmitArtifact(path="serve.py", content="# serve", role="serving"),
        ],
    )
    assert {a.role for a in res.artifacts} == {"agent", "serving"}
    assert res.artifact == res.artifact_for("agent")
    from dna.emit.agno import AgnoEmitter

    assert AgnoEmitter().extract_instructions(res.artifact_for("agent")) == "hi"


def test_single_artifact_back_compat():
    """The legacy single-artifact constructor still works: ``artifact``/
    ``filename`` resolve transparently to the lone ``role="agent"`` entry."""
    res = EmitResult(artifact="A", target="x", filename="a.py")
    assert res.artifact == "A" and res.filename == "a.py"
    assert [a.role for a in res.artifacts] == ["agent"]
