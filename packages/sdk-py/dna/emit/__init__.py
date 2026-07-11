"""``dna.emit`` — the vendor-neutral EMITTER layer (the "de-para").

DNA authors an agent ONCE — a persona (Soul), an instruction (Agent), wired
Guardrails, and Tools — as declarative Kinds. This package materializes that
one neutral definition into the NATIVE artifact each runtime framework consumes.
It is the concrete first step of "DNA as the Terraform of agents": author once,
emit per runtime, swap runtimes without rewriting the agent.

The :class:`EmitterPort` is a **first-class DNA port** — a documented contract on
the same footing as the kernel's five ports (Source / Cache / Resolver /
Reader-Writer / Kind), only it lives one layer OUT: the kernel *composes* the
neutral agent; the EmitterPort *materializes* it for a runtime. See the
`How to write an emitter <../guides/writing-an-emitter.md>`_ guide.

The contract, in two surfaces (both parity-critical across the Py/TS SDKs):

    build_emit_context(mi, agent, ...) -> EmitContext
        The kernel-facing half: compose the DNA agent (``build_prompt``) and
        project it to the NEUTRAL :class:`EmitContext`. Runs once per emit; every
        target reads the same context. This is NOT part of the port — it is the
        shared front door that feeds every port implementation.

    EmitterPort.emit(ctx) -> EmitResult
        The runtime-facing half a target implements. PURE: reads the neutral
        context, returns the native artifact. No kernel I/O, no network.

**The central invariant** every emitter MUST honor: the composed
``instructions`` in the emitted artifact is **byte-equal** to
``mi.build_prompt(agent)`` — the emit carries the composition VERBATIM, it never
paraphrases. The contract makes this checkable and *inheritable*:
:meth:`EmitterPort.extract_instructions` recovers the embedded instruction from a
target's own artifact, and one generic test (``test_emit_contract``) runs the
byte-equal assertion over EVERY registered target, so a new emitter inherits the
check for free.

Two flavors of emitter satisfy the same port (see the guide's *Passo 0*):

    - **config-declarative** — the runtime has a published declarative schema
      (a YAML/JSON agent definition). The emitter maps the context field-for-field
      into that schema. The three shipped targets are of this flavor:
      agent-framework (PromptAgent YAML), bedrock (CloudFormation
      ``AWS::Bedrock::Agent``), vertex (Google ADK Agent Config).
    - **scaffold-code** — the runtime is *code-first* (no declarative format;
      you construct an agent object in Python). A :class:`~dna.emit.scaffold.ScaffoldEmitter`
      fills a curated ``{framework × case}`` template library rather than
      generating code ad-hoc. The ``openai-agents`` target is the reference.

Shape of the layer (SDK-first; the ``dna emit`` CLI is a thin wrapper):

    EmitContext   — the runtime-agnostic view of a composed DNA agent
                    (name / description / instructions / model / tools /
                    output_schema). Built once by :func:`build_emit_context`
                    from a ManifestInstance; every emitter reads from it.
    EmitterPort   — the port an emitter implements (``target`` / ``file_extension``
                    + ``emit`` + ``extract_instructions``).
    EMITTER_REGISTRY / register_emitter / get_emitter / available_targets —
                    the pluggable registry. agent-framework is the FIRST target;
                    a new one (bedrock / vertex / openai-agents) is a class + one
                    ``register_emitter(...)`` call — the CLI core never changes.
    EmitResult    — ``{artifact, filename, target, losses[], mapping{}}``. The
                    ``losses`` list is first-class: it names the DNA axes a given
                    target has NO slot for (composition structure, tenant overlay,
                    eval-as-contract), so the de-para is honest about what does
                    NOT survive the emit.
    emit_agent    — the high-level one-call surface used by the CLI + SDK users.

Why the loss list matters: for a single agent, a native framework (agent-framework)
is genuinely clean. DNA earns its keep on the axes the emit DROPS — Soul reuse,
per-tenant overlay without a fork, prompt invariants as eval contracts. The
emitter records exactly what collapses to a flat artifact so the trade-off is
visible, not hand-waved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "EmitContext",
    "EmitResult",
    "EmitterPort",
    "EmitError",
    "UnknownTarget",
    "register_emitter",
    "get_emitter",
    "available_targets",
    "build_emit_context",
    "emit_agent",
    "emit_agent_from_scope",
]


class EmitError(RuntimeError):
    """Base class for emit-time failures (bad agent, missing tool, …)."""


class UnknownTarget(EmitError):
    """``--target`` named a runtime with no registered emitter."""

    def __init__(self, target: str, available: list[str]) -> None:
        self.target = target
        self.available = available
        super().__init__(
            f"no emitter registered for target {target!r}; "
            f"available: {', '.join(available) or '(none)'}"
        )


@dataclass
class EmitContext:
    """Runtime-agnostic view of ONE composed DNA agent.

    This is the neutral hand-off: :func:`build_emit_context` fills it from the
    kernel (the composition already produced the flat ``instructions``); each
    :class:`EmitterPort` reads from it and never touches the kernel directly.
    """

    #: The DNA agent slug (``metadata.name``).
    name: str
    #: ``metadata.description`` (the agent's one-liner), or "".
    description: str
    #: The DNA-composed system prompt — Soul + guardrails + instruction, flat.
    #: This is the byte-equal gate: an emitter MUST carry it verbatim.
    instructions: str
    #: The raw DNA model coordinate (e.g. ``openai:gpt-4o-mini``, ``azure/gpt-4o``,
    #: or bare ``gpt-4o``), or None when the DNA leaves the model unbound.
    model: str | None = None
    #: Resolved tool surfaces the agent references (``spec.tools`` → Tool Kind):
    #: ``[{name, description, parameters}]`` where ``parameters`` is the input
    #: JSON Schema. Empty when the agent calls no tools.
    tools: list[dict[str, Any]] = field(default_factory=list)
    #: Optional response JSON Schema (``spec.output_schema``), or None.
    output_schema: dict[str, Any] | None = None
    #: The scope the agent was composed from (provenance).
    scope: str | None = None
    #: Extra per-emitter hints (e.g. a CLI ``--provider`` override).
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmitResult:
    """The emitted native artifact + an honest account of the de-para."""

    #: The serialized native artifact (e.g. the agent-framework PromptAgent YAML).
    artifact: str
    #: The target runtime id (``agent-framework``).
    target: str
    #: Suggested filename (``<name>.agent.yaml``) for ``--out`` defaults.
    filename: str
    #: DNA axes with NO slot in this target — what did NOT survive the emit.
    losses: list[str] = field(default_factory=list)
    #: Field-level de-para (``dna_field -> target_field``) for reporting.
    mapping: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class EmitterPort(Protocol):
    """A runtime emitter — materializes an :class:`EmitContext` into a native
    artifact. Implement this + call :func:`register_emitter` to add a target.

    An emitter is PURE: it reads the neutral :class:`EmitContext` and returns an
    :class:`EmitResult`. It performs NO kernel I/O and NO network — that is the
    high-level :func:`emit_agent`'s job. This keeps every target trivially
    unit-testable against a hand-built context.

    A conforming emitter provides three things:

    ``target`` / ``file_extension``
        Identity: the id used on ``dna emit --target <id>`` and the extension of
        the default output filename.

    :meth:`emit`
        The materialization — the de-para from the neutral context into the
        target's native artifact, plus an honest :class:`EmitResult.losses` list.

    :meth:`extract_instructions`
        The **byte-equal invariant hook**: recover the composed instruction from
        this target's own artifact. It is what makes the central invariant
        (emitted instruction == ``build_prompt``) inheritable — one generic test
        loops every registered target and asserts
        ``extract_instructions(emit(ctx).artifact) == ctx.instructions``. An
        emitter that genuinely has no instruction slot may return ``None`` (the
        generic check skips it), but every real target carries the prompt.
    """

    #: Stable target id used on ``dna emit --target <id>``.
    target: str
    #: File extension used to build the default output filename.
    file_extension: str

    def emit(self, ctx: EmitContext) -> EmitResult:
        """Materialize ``ctx`` into a native artifact."""
        ...

    def extract_instructions(self, artifact: str) -> str | None:
        """Recover the composed instruction embedded in ``artifact``.

        The inverse of the instruction half of :meth:`emit`, used by the generic
        byte-equal contract test. A config-declarative emitter parses its own
        serialized shape (YAML/JSON) and returns the instruction field; a
        scaffold emitter reads it back from the emitted source. Return ``None``
        only when the target has no instruction slot at all.
        """
        ...


# ── registry ────────────────────────────────────────────────────────────

EMITTER_REGISTRY: dict[str, EmitterPort] = {}


def register_emitter(emitter: EmitterPort) -> EmitterPort:
    """Register an emitter under its ``target``. Last registration wins, so a
    host may override a built-in target. Returns the emitter (usable as a
    decorator on a zero-arg factory is intentionally NOT supported — an emitter
    is an instance, not a class, so hosts can parametrize it)."""
    EMITTER_REGISTRY[emitter.target] = emitter
    return emitter


def get_emitter(target: str) -> EmitterPort:
    """Look up a registered emitter or raise :class:`UnknownTarget`."""
    _ensure_builtins()
    try:
        return EMITTER_REGISTRY[target]
    except KeyError:
        raise UnknownTarget(target, available_targets()) from None


def available_targets() -> list[str]:
    """Sorted list of registered target ids."""
    _ensure_builtins()
    return sorted(EMITTER_REGISTRY)


_BUILTINS_WIRED = False


def _ensure_builtins() -> None:
    """Lazily register the in-tree emitters on first registry access. Kept lazy
    so ``import dna.emit`` stays cheap and a host can register BEFORE the
    built-ins if it wants to shadow one."""
    global _BUILTINS_WIRED
    if _BUILTINS_WIRED:
        return
    _BUILTINS_WIRED = True
    from dna.emit.agent_framework import AgentFrameworkEmitter
    from dna.emit.bedrock import BedrockEmitter
    from dna.emit.openai_agents import OpenAIAgentsEmitter
    from dna.emit.vertex import VertexEmitter

    # Only register a target that has not been claimed already (host override).
    for emitter in (
        AgentFrameworkEmitter(),
        BedrockEmitter(),
        VertexEmitter(),
        OpenAIAgentsEmitter(),
    ):
        EMITTER_REGISTRY.setdefault(emitter.target, emitter)


# ── composition: DNA agent → neutral EmitContext ─────────────────────────


def build_emit_context(
    mi: Any,
    agent: str,
    *,
    model: str | None = None,
    provider: str | None = None,
) -> EmitContext:
    """Compose a DNA agent through the kernel and project it to an
    :class:`EmitContext`.

    ``mi`` is a live ``ManifestInstance`` (the CLI reuses its session mi; SDK
    callers can pass ``Kernel.quick(scope)``). The composition — Soul + guardrails
    + instruction ordering — is the kernel's job (``build_prompt``); here we only
    project the result plus the runtime-binding fields (model, tools) an emitter
    needs.

    Model resolution order: explicit ``model`` arg → ``agent.spec.model`` →
    Genome ``spec.default_llm`` → None (unbound). ``provider`` is a pure hint
    passed through to the emitter (targets that split id/provider use it).
    """
    doc = mi.find_agent(agent)
    if doc is None:
        raise EmitError(
            f"agent {agent!r} not found in scope {getattr(mi, 'scope', '?')!r}"
        )
    spec = getattr(doc, "spec", None) or {}
    meta = getattr(doc, "metadata", None) or {}
    description = (meta.get("description") if hasattr(meta, "get") else "") or ""

    instructions = mi.build_prompt(agent)

    resolved_model = model or (spec.get("model") if hasattr(spec, "get") else None)
    if not resolved_model:
        root = getattr(mi, "root", None)
        root_spec = getattr(root, "spec", None) or {}
        resolved_model = (
            root_spec.get("default_llm") if hasattr(root_spec, "get") else None
        )

    tools = _resolve_tools(mi, spec)
    output_schema = spec.get("output_schema") if hasattr(spec, "get") else None

    return EmitContext(
        name=getattr(doc, "name", agent),
        description=description,
        instructions=instructions,
        model=resolved_model,
        tools=tools,
        output_schema=output_schema if isinstance(output_schema, dict) else None,
        scope=getattr(mi, "scope", None),
        options={"provider": provider} if provider else {},
    )


def _resolve_tools(mi: Any, spec: Any) -> list[dict[str, Any]]:
    """Project the agent's ``spec.tools`` (names) → neutral tool surfaces.

    Reuses the same ``ToolLibrary`` surface ``dna.load_tools`` serves, so an
    emitted tool description is byte-identical to what a Python ``@tool`` or a
    TS ``useCopilotAction`` reads — one source of truth."""
    names = spec.get("tools") if hasattr(spec, "get") else None
    if not names:
        return []
    from dna.tools import ToolLibrary, ToolNotFound

    lib = ToolLibrary(mi)
    out: list[dict[str, Any]] = []
    for name in names:
        try:
            surface = lib[name]
        except ToolNotFound as exc:
            raise EmitError(str(exc)) from None
        out.append(
            {
                "name": name,
                "description": surface.description,
                "parameters": dict(surface.parameters),
            }
        )
    return out


# ── high-level surfaces ──────────────────────────────────────────────────


def emit_agent(
    mi: Any,
    agent: str,
    target: str,
    *,
    model: str | None = None,
    provider: str | None = None,
) -> EmitResult:
    """Compose ``agent`` from ``mi`` and emit it for ``target``.

    The one call the CLI makes. Boots nothing (``mi`` is already live), so it is
    equally usable from a request handler that already holds a ManifestInstance.
    """
    emitter = get_emitter(target)
    ctx = build_emit_context(mi, agent, model=model, provider=provider)
    return emitter.emit(ctx)


def emit_agent_from_scope(
    scope: str,
    agent: str,
    target: str,
    *,
    base_dir: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> EmitResult:
    """Convenience: boot a filesystem kernel for ``scope`` and emit ``agent``.

    For SDK users and tests that do not already hold a ManifestInstance. Mirrors
    :func:`dna.load_tools` / :func:`dna.load_prompts` boot conventions
    (``base_dir`` → ``DNA_BASE_DIR`` → ``.dna``)."""
    import os

    if base_dir is None:
        base_dir = os.environ.get("DNA_BASE_DIR") or ".dna"
    from dna.kernel import Kernel

    mi = Kernel.quick(scope, base_dir=base_dir)
    return emit_agent(mi, agent, target, model=model, provider=provider)
