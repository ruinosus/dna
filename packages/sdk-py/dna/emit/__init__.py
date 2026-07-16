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
    "EmitMcpServer",
    "EmitArtifact",
    "EmitResult",
    "EmitterPort",
    "EmitError",
    "UnknownTarget",
    "register_emitter",
    "get_emitter",
    "available_targets",
    "build_emit_context",
    "build_copilot_context",
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
class EmitMcpServer:
    """A neutral projection of ONE ``MCPFederation`` the mounted agent consumes.

    Filled by :func:`build_copilot_context` from the mounted ``Agent.spec.
    mcp_servers`` refs resolved to their ``MCPFederation`` docs. ``transport`` is
    normalized to the MCP client wire form (``streamable-http``) that Chunk 4's
    ``MCPTools(url, transport=…)`` consumes — the federation Kind stores it as
    ``streamable_http`` (schema enum).
    """

    #: Name of the ``MCPFederation`` doc (``mcp_servers[].ref``).
    ref: str
    #: MCP transport wire name — ``streamable-http`` or ``stdio``.
    transport: str
    #: Server endpoint (``streamable_http`` only), else None.
    url: str | None = None
    #: Auth block by env-var NAME (``{kind, env, header?}``) — never a secret
    #: value. Empty when the federation declares no auth.
    auth: dict[str, Any] = field(default_factory=dict)
    #: Effective tool allowlist — the per-agent allowlist intersected with the
    #: federation's own. Empty = everything the federation allows.
    allowed_tools: list[str] = field(default_factory=list)
    #: Whether the HTTP transport stamps tenant/scope/agent headers.
    propagate_tenant: bool = True


@dataclass
class EmitContext:
    """Runtime-agnostic view of ONE composed DNA agent.

    This is the neutral hand-off: :func:`build_emit_context` fills it from the
    kernel (the composition already produced the flat ``instructions``); each
    :class:`EmitterPort` reads from it and never touches the kernel directly.

    A single-agent emit leaves the copilot-only fields (``mcp_servers``,
    ``tools_requiring_confirmation``, ``tenant_propagate``, ``knowledge``) at
    their empty defaults; :func:`build_copilot_context` fills them from a
    ``Copilot`` binder + its mounted agent.
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
    # ── copilot-only projections (filled by build_copilot_context) ──────────
    #: External MCP servers the mounted agent consumes, resolved from its
    #: ``mcp_servers`` refs → ``MCPFederation`` docs. Empty for a single agent.
    mcp_servers: list[EmitMcpServer] = field(default_factory=list)
    #: Tool names the mounted agent gates on human approval
    #: (``Tool.requires_confirmation``) — the HITL-write surface. Empty = none.
    tools_requiring_confirmation: set[str] = field(default_factory=set)
    #: Whether the emitted serving layer derives inbound tenant from request
    #: headers into run-state (Copilot ``tenant.propagate`` / federation
    #: ``propagate_tenant``).
    tenant_propagate: bool = False
    #: RAG collection refs the copilot may read (``knowledge.collections``).
    #: Empty when the copilot declares no knowledge (RAG optional).
    knowledge: list[str] = field(default_factory=list)


@dataclass
class EmitArtifact:
    """One emitted file, tagged with a semantic role.

    A single-agent emit produces one ``role="agent"`` artifact; a servable
    copilot emits several (agent module + AG-UI serve app + …). ``artifacts`` on
    :class:`EmitResult` is the source of truth; the legacy ``artifact``/
    ``filename`` are read-only views of the ``role="agent"`` entry.
    """

    #: Target-relative output path (``"agent.py"``, ``"serve.py"``); the legacy
    #: ``filename`` for a single emit.
    path: str
    #: Serialized file content (source / YAML / JSON).
    content: str
    #: Semantic role — ``"agent"`` carries the byte-equal instruction; ``"serving"``
    #: is the AG-UI serve app. Extensible (route/frontend later).
    role: str = "agent"


class EmitResult:
    """The emitted native artifact(s) + an honest account of the de-para.

    ``artifacts`` is the SINGLE SOURCE OF TRUTH; ``artifact``/``filename`` are
    read-only views of the ``role="agent"`` entry (back-compat). This is a plain
    class with an explicit ``__init__`` rather than a ``@dataclass`` because a
    dataclass cannot host both an ``artifact`` init-field AND an ``artifact``
    ``@property`` of the same name — the property object would collide with the
    field's class-level default. The explicit ``__init__`` accepts EITHER the
    legacy ``artifact=``+``filename=`` pair OR ``artifacts=[...]``, so every
    existing keyword-only call site keeps working verbatim.
    """

    def __init__(
        self,
        target: str,
        *,
        artifact: str | None = None,
        filename: str | None = None,
        artifacts: list[EmitArtifact] | None = None,
        losses: list[str] | None = None,
        mapping: dict[str, str] | None = None,
    ) -> None:
        if artifacts is None:
            if artifact is None or filename is None:
                raise EmitError(
                    "EmitResult needs `artifacts=[...]` or the legacy "
                    "`artifact=`+`filename=` pair"
                )
            artifacts = [EmitArtifact(path=filename, content=artifact, role="agent")]
        #: The emitted files (source of truth). At least one, conventionally
        #: including a ``role="agent"`` entry that carries the byte-equal prompt.
        self.artifacts = artifacts
        #: The target runtime id (``agent-framework``).
        self.target = target
        #: DNA axes with NO slot in this target — what did NOT survive the emit.
        self.losses = losses if losses is not None else []
        #: Field-level de-para (``dna_field -> target_field``) for reporting.
        self.mapping = mapping if mapping is not None else {}

    def artifact_for(self, role: str) -> str:
        """Return the content of the artifact tagged ``role`` (raises if absent)."""
        for a in self.artifacts:
            if a.role == role:
                return a.content
        raise EmitError(
            f"no artifact with role {role!r} (have {[a.role for a in self.artifacts]})"
        )

    @property
    def artifact(self) -> str:
        """Legacy single-artifact content = the ``role="agent"`` entry."""
        return self.artifact_for("agent")

    @property
    def filename(self) -> str:
        """Legacy single-artifact path = the ``role="agent"`` entry's path."""
        for a in self.artifacts:
            if a.role == "agent":
                return a.path
        raise EmitError("EmitResult has no role='agent' artifact")


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
    from dna.emit.agno import AgnoEmitter
    from dna.emit.bedrock import BedrockEmitter
    from dna.emit.deepagents import DeepAgentsEmitter
    from dna.emit.langgraph import LanggraphEmitter
    from dna.emit.openai_agents import OpenAIAgentsEmitter
    from dna.emit.vertex import VertexEmitter

    # Only register a target that has not been claimed already (host override).
    for emitter in (
        AgentFrameworkEmitter(),
        BedrockEmitter(),
        VertexEmitter(),
        OpenAIAgentsEmitter(),
        LanggraphEmitter(),
        AgnoEmitter(),
        DeepAgentsEmitter(),
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


def build_copilot_context(
    mi: Any,
    copilot: str,
    *,
    model: str | None = None,
    provider: str | None = None,
) -> EmitContext:
    """Compose a ``Copilot`` doc through the kernel and project it to an enriched
    :class:`EmitContext` — the Chunk 1↔4 seam.

    Where :func:`build_emit_context` is keyed by an *Agent* name, a ``Copilot``
    is a binder: it mounts an Agent and carries the copilot-level concerns that
    don't belong on any single Agent (``serving``/``tenant``/``hitl``/
    ``knowledge``). This resolves the mounted agent's base ctx via the existing
    front door (so the byte-equal instruction contract is untouched —
    ``instructions`` still come from the Agent, unchanged), then **enriches** it
    with the projections the single-agent front door has no slot for:

    - ``mcp_servers`` — the mounted ``Agent.spec.mcp_servers`` refs resolved to
      their ``MCPFederation`` docs (transport/url/auth/allowed_tools).
    - ``tools_requiring_confirmation`` — the mounted agent's tools whose
      ``Tool.spec.requires_confirmation`` is true (the HITL intent).
    - ``tenant_propagate`` — the Copilot ``tenant.propagate``, falling back to
      the mounted federations' ``propagate_tenant``.
    - ``knowledge`` — the Copilot ``knowledge.collections`` refs (empty when the
      copilot declares no RAG).

    Chunk 4's Agno scaffold emits from *this* context.
    """
    doc = mi._one("Copilot", copilot)
    if doc is None:
        raise EmitError(
            f"copilot {copilot!r} not found in scope {getattr(mi, 'scope', '?')!r}"
        )
    cspec = getattr(doc, "spec", None) or {}
    mounts = _spec_get(cspec, "mounts")
    if not mounts:
        raise EmitError(f"copilot {copilot!r} declares no mounts")
    mount0 = mounts[0]
    agent_name = _spec_get(mount0, "agent")
    if not agent_name:
        raise EmitError(f"copilot {copilot!r} mount[0] has no agent")

    # Base ctx from the EXISTING front door — keyed by the mounted agent's name.
    ctx = build_emit_context(mi, agent_name, model=model, provider=provider)

    # ── enrich (Task 3b) ────────────────────────────────────────────────────
    agent_doc = mi.find_agent(agent_name)
    agent_spec = getattr(agent_doc, "spec", None) or {}

    mcp_servers = _project_mcp_servers(mi, agent_spec)
    ctx.mcp_servers = mcp_servers
    ctx.tools_requiring_confirmation = _project_hitl_intent(mi, agent_spec)

    tenant_block = _spec_get(cspec, "tenant") or {}
    copilot_propagate = _spec_get(tenant_block, "propagate")
    if copilot_propagate is not None:
        ctx.tenant_propagate = bool(copilot_propagate)
    else:
        # No explicit Copilot signal → derive from the mounted federations.
        ctx.tenant_propagate = any(s.propagate_tenant for s in mcp_servers)

    knowledge_block = _spec_get(cspec, "knowledge") or {}
    ctx.knowledge = list(_spec_get(knowledge_block, "collections") or [])

    return ctx


def _spec_get(obj: Any, key: str) -> Any:
    """Read ``key`` from a doc spec node that may be a dict OR an
    attribute-namespace (record-plane reads project either shape)."""
    if obj is None:
        return None
    if hasattr(obj, "get"):
        return obj.get(key)
    return getattr(obj, key, None)


def _project_mcp_servers(mi: Any, agent_spec: Any) -> list["EmitMcpServer"]:
    """Resolve the mounted ``Agent.spec.mcp_servers`` refs → their
    ``MCPFederation`` docs, projected to neutral :class:`EmitMcpServer` surfaces.

    Each ``mcp_servers`` entry is EITHER a plain string ref (``"dna-mcp"``) OR a
    dict ``{ref, allowed_tools?, timeout_s?}`` (``models.py:362``). The effective
    ``allowed_tools`` is the per-agent allowlist intersected with the
    federation's own (``models.py:369``) — empty on either side means "all the
    other side allows". ``transport`` is normalized from the federation's
    ``streamable_http`` (schema enum, ``federation/__init__.py``) to the MCP
    client wire form ``streamable-http`` that ``MCPTools(url, transport=…)``
    consumes downstream (Chunk 4)."""
    entries = _spec_get(agent_spec, "mcp_servers") or []
    out: list[EmitMcpServer] = []
    for entry in entries:
        if isinstance(entry, str):
            ref, agent_allow = entry, []
        else:
            ref = _spec_get(entry, "ref")
            agent_allow = list(_spec_get(entry, "allowed_tools") or [])
        if not ref:
            continue
        fed = mi._one("MCPFederation", ref)
        if fed is None:
            raise EmitError(
                f"MCPFederation {ref!r} referenced by the mounted agent was not "
                f"found in scope {getattr(mi, 'scope', '?')!r}"
            )
        fspec = getattr(fed, "spec", None) or {}
        fed_allow = list(_spec_get(fspec, "allowed_tools") or [])
        if agent_allow and fed_allow:
            allowed = [t for t in agent_allow if t in fed_allow]
        else:
            allowed = agent_allow or fed_allow
        raw_transport = _spec_get(fspec, "transport") or "stdio"
        transport = "streamable-http" if raw_transport == "streamable_http" else raw_transport
        auth = _spec_get(fspec, "auth")
        propagate = _spec_get(fspec, "propagate_tenant")
        out.append(
            EmitMcpServer(
                ref=ref,
                transport=transport,
                url=_spec_get(fspec, "url"),
                auth=dict(auth) if isinstance(auth, dict) else {},
                allowed_tools=allowed,
                propagate_tenant=True if propagate is None else bool(propagate),
            )
        )
    return out


def _project_hitl_intent(mi: Any, agent_spec: Any) -> set[str]:
    """The mounted agent's tools whose ``Tool.spec.requires_confirmation`` is
    true (``tool.kind.yaml:111``) — the HITL-gated write surface. Read via the
    same record-plane surface :class:`~dna.tools.ToolLibrary` uses."""
    names = _spec_get(agent_spec, "tools") or []
    gated: set[str] = set()
    for name in names:
        tdoc = mi._one("Tool", name)
        if tdoc is None:
            continue
        tspec = getattr(tdoc, "spec", None) or {}
        if bool(_spec_get(tspec, "requires_confirmation")):
            gated.add(name)
    return gated


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
