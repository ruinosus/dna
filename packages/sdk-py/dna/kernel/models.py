"""Typed models for each kind — used by KindPort.parse().

Each Typed* class has .metadata (Metadata) and .spec (*Spec).
Document delegates doc.metadata and doc.spec to these when available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

@dataclass
class Metadata:
    """Typed metadata common to all kinds."""
    name: str = ""
    description: str = ""
    version: str = ""
    icon: str = ""
    group: str = ""
    labels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Metadata:
        return cls(
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            version=raw.get("version", ""),
            icon=raw.get("icon", ""),
            group=raw.get("group", ""),
            labels=raw.get("labels") or {},
        )


@dataclass
class FileEntry:
    """A file within a bundle (scripts/, references/, assets/)."""
    name: str
    content: str



# ---------------------------------------------------------------------------
# Genome (github.com/ruinosus/dna/v1) — Phase 16 (scope segregation)
#
# Replaces Module as the scope-root identity + runtime config doc.
# Catalog identity (owner, version, visibility) lives here. Layer policy
# moved out to ``LayerPolicy`` Kind. Custom Kinds moved out to
# ``KindDefinition`` Kind. Bill-of-materials inventory arrays
# (agents[], skills[], actors[], etc.) deleted — composition validation
# walks scanner output directly.
#
# Tenant overlay applies only to ``OVERLAYABLE_FIELDS`` declared on the
# GenomeKind. Identity (owner_tenant, version, visibility, deprecated*,
# repository, dependencies) is structurally non-overlayable.
# ---------------------------------------------------------------------------

@dataclass
class GenomeSpec:
    # Catalog identity — non-overlayable.
    owner: str | None = None
    owner_tenant: str | None = None
    repository: str | None = None
    visibility: str = "public"

    # i-112 OQ1 — uma capability de Catalog marcada mandatory é instalada-por-
    # default + não-removível; global_scope = lookup global do runtime (como o
    # model registry). Catalog identity → NÃO-overlayable.
    mandatory: bool = False
    global_scope: bool = False

    # Composition Engine V2 (Phase 17, s-comp-f1-schema, 2026-05-28):
    # Declarative parent scope for cross-scope inheritance. Resolution
    # walks the chain: local → parent → grandparent. None = root scope
    # (no inheritance). Per-Kind composition_rules in LayerPolicy
    # govern WHICH Kinds inherit + merge_strategy. Backward-compat:
    # absent treated as None during V1 transition. Slug rules same as
    # scope name: lowercase alphanumeric + hyphens, max 253 chars.
    parent_scope: str | None = None

    # Versioning — non-overlayable.
    version: str | None = None
    changelog_url: str | None = None
    deprecated: bool = False
    deprecated_message: str | None = None

    # Runtime defaults — overlayable per tenant.
    default_agent: str | None = None
    default_llm: str | None = None
    budget: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)

    # i-112 ph2 — capability manifest: o que este Genome PROVÊ. Cada entry
    # {kind, name, location}: kind=alias do Kind provido (ex "soulspec-soul"),
    # name=nome do doc, location=path relativo dentro do package. Catalog
    # identity → NÃO-overlayable. O resolver (Fase 3) lê isto pra carregar
    # capabilities de packages instalados. Forma espelha `dependencies`.
    capabilities: list[dict[str, Any]] = field(default_factory=list)

    # External deps — non-overlayable (lockfile resolves).
    dependencies: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> GenomeSpec:
        return cls(
            owner=raw.get("owner"),
            owner_tenant=raw.get("owner_tenant"),
            repository=raw.get("repository"),
            visibility=raw.get("visibility") or "public",
            mandatory=bool(raw.get("mandatory", False)),
            global_scope=bool(raw.get("global_scope", False)),
            parent_scope=raw.get("parent_scope") or None,
            version=raw.get("version") or None,
            changelog_url=raw.get("changelog_url") or None,
            deprecated=bool(raw.get("deprecated", False)),
            deprecated_message=raw.get("deprecated_message") or None,
            default_agent=raw.get("default_agent"),
            default_llm=raw.get("default_llm"),
            budget=raw.get("budget"),
            tags=raw.get("tags") or [],
            capabilities=raw.get("capabilities") or [],
            dependencies=raw.get("dependencies") or [],
        )


@dataclass
class TypedGenome:
    metadata: Metadata
    spec: GenomeSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedGenome:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=GenomeSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# LayerPolicy (github.com/ruinosus/dna/policy/v1) — Phase 16
#
# One LayerPolicy doc per (layer_id, scope). Lists per-Kind policies for
# overlay writes against that layer. Replaces ``Module.spec.layers``.
#
# Policy values: "open" (default — never raises), "restricted" (only
# override existing top-level spec keys), "locked" (any write raises).
# ---------------------------------------------------------------------------

@dataclass
class CompositionRule:
    """Composition Engine V2 (Phase 17, s-comp-f1-schema, 2026-05-28)
    — per-Kind rule on how to compose docs across the resolution chain.

    - ``scope_inheritance``: ``enabled`` (default for most assetic Kinds)
      or ``disabled`` (board Kinds like Story). Decides whether
      resolution walks parent_scope chain at all.

    - ``merge_strategy``: ``override_full`` (local replaces inherited
      entirely; suitable for binary assets like LottieAsset) or
      ``field_level`` (Kinds whose spec has independent fields the user
      might want to overlay individually, e.g. Agent persona
      inherited + model overridden locally).

    - ``tenant_overlay``: Orthogonal to scope_inheritance. ``none`` skips
      tenant layer entirely; ``field_level`` honors LayerPolicy v1
      tenant overlays for the field set.
    """
    scope_inheritance: str = "enabled"   # enabled | disabled
    merge_strategy: str = "override_full"  # override_full | field_level
    tenant_overlay: str = "field_level"  # none | field_level

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> CompositionRule:
        return cls(
            scope_inheritance=str(raw.get("scope_inheritance") or "enabled").lower(),
            merge_strategy=str(raw.get("merge_strategy") or "override_full").lower(),
            tenant_overlay=str(raw.get("tenant_overlay") or "field_level").lower(),
        )


@dataclass
class LayerPolicySpec:
    layer_id: str = ""
    policies: dict[str, str] = field(default_factory=dict)
    # Composition Engine V2: per-Kind composition rules. Keyed by Kind
    # name (e.g. "Agent", "LottieAsset"). Absent Kinds fall back
    # to global defaults (scope_inheritance=disabled, no overlay) — Kinds
    # opt-IN, never opt-out.
    composition_rules: dict[str, CompositionRule] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> LayerPolicySpec:
        policies = raw.get("policies") or {}
        comp = raw.get("composition_rules") or {}
        return cls(
            layer_id=raw.get("layer_id") or "",
            policies={
                k: str(v).lower()
                for k, v in policies.items()
                if isinstance(k, str) and v
            },
            composition_rules={
                k: CompositionRule.from_raw(v)
                for k, v in comp.items()
                if isinstance(k, str) and isinstance(v, dict)
            },
        )


@dataclass
class TypedLayerPolicy:
    metadata: Metadata
    spec: LayerPolicySpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedLayerPolicy:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=LayerPolicySpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# Agent (github.com/ruinosus/dna/v1)
#
# Prompt target. References Soul via spec.soul, Skills via spec.skills.
# Has instruction (inline or file ref), model, tools, team_members.
# ---------------------------------------------------------------------------


@dataclass
class VoicePersona:
    """Voice-first UA configuration (JARVIS — e-jarvis-voice-module).

    Opt-in block on AgentSpec. Presence flips the UA from
    text-only to voice-reachable via POST /voice/sessions. All fields
    have safe defaults so a minimal `voice_persona: {}` works.
    """
    voice: str = "cedar"  # OpenAI Realtime voice id; gpt-realtime-2 default
    style: str | None = None  # prosody hint, e.g. "concise, dry-wit"
    archetype: str | None = None  # "jarvis" | "coach" | "interviewer" | ...
    # how eagerly to yield when user barges in: high|medium|low
    interruption_tolerance: str = "high"
    # gpt-realtime-2: emit "one moment..." while parallel tool calls run
    preamble: bool = False
    # Let OpenAI Realtime call the harness MCP endpoint directly
    # (1-hop tool-call flow). Requires gpt-realtime-2.
    mcp_egress: bool = False
    # P2 ambient mode. None = push-to-talk only.
    wake_word: str | None = None
    # Per-session soft cost cap (USD). Audit WS warns at 80% + closes at 100%.
    budget: float = 5.0

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> VoicePersona:
        return cls(
            voice=raw.get("voice") or "cedar",
            style=raw.get("style"),
            archetype=raw.get("archetype"),
            interruption_tolerance=raw.get("interruption_tolerance") or "high",
            preamble=bool(raw.get("preamble", False)),
            mcp_egress=bool(raw.get("mcp_egress", False)),
            wake_word=raw.get("wake_word"),
            budget=float(raw.get("budget", 5.0)),
        )


_VALID_DELEGATION_FORMATS = ("slug", "json", "text")


@dataclass
class DelegationTargetFor:
    """Declarative delegation-target opt-in (s-delegation-declarative).

    Replaces the hardcoded ``DELEGATION_CATALOG`` that used to live in
    ``dna_shared.manifest_tools.delegation_tools``. A Agent that
    wants to receive delegated work (e.g. from the JARVIS voice agent
    via ``delegate_to``) declares this block in its spec — user-installed
    UAs opt in by declaration, no code edit needed.

    Shape rationale: the old catalog carried per-target metadata beyond
    the mere delegator list (``format`` is load-bearing — it drives how
    ``delegate_to`` parses the subagent's output; ``typical_seconds`` +
    ``use_when`` drive the delegator's narration and target choice), so
    the field is an object, not a bare list of delegator names.

    Example (AGENT.md frontmatter):
        delegation_target_for:
          agents: [jarvis]        # delegator allowlist; "*" = any agent
          format: slug            # slug | json | text (default text)
          typical_seconds: 10     # rough wait so the delegator can warn the user
          use_when: user asks for an elaborate HTML mockup
          purpose: Generate elaborate HTML mockups...  # falls back to metadata.description
    """
    # Delegator allowlist — agent names that may delegate to this UA.
    # ``["*"]`` opts in for every delegator.
    agents: list[str] = field(default_factory=list)
    # Return contract for ``delegate_to``: "slug" (creates a doc, returns
    # its slug), "json" (structured JSON in the final message), "text"
    # (free-form narrative — default).
    format: str = "text"
    # Rough wait time in seconds so the delegator can set expectations
    # ("vou pedir pro X — uns 10 segundos"). None = unknown.
    typical_seconds: int | None = None
    # Heuristic for when the delegator should pick THIS target.
    use_when: str | None = None
    # What the target is good at. When absent, consumers fall back to
    # the agent's ``metadata.description``.
    purpose: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> DelegationTargetFor:
        fmt = raw.get("format") or "text"
        if fmt not in _VALID_DELEGATION_FORMATS:
            raise ValueError(
                f"Invalid delegation_target_for.format: {fmt!r} "
                f"(expected one of {', '.join(_VALID_DELEGATION_FORMATS)})"
            )
        ts = raw.get("typical_seconds")
        return cls(
            agents=list(raw.get("agents") or []),
            format=fmt,
            typical_seconds=int(ts) if ts is not None else None,
            use_when=raw.get("use_when"),
            purpose=raw.get("purpose"),
        )


@dataclass
class AgentSpec:
    instruction: str = ""
    instruction_file: str | None = None  # NEW
    objective: str = ""
    model: str | None = None
    type: str | None = None
    soul: str | None = None
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    team_members: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    promptTemplate: str | None = None
    # s-dx-named-layouts — pick the composition ORDER by name instead of
    # hand-writing raw Mustache. ``"persona-first"`` puts the Soul before the
    # instruction; ``"instruction-first"`` (a.k.a. ``"default"``) keeps the
    # historic order. Resolved by the Kind's ``layout_template()`` into an
    # embedded preset — the common case never authors ``{{{soul_content}}}``.
    # ``promptTemplate`` (raw) still wins over ``layout`` when both are set
    # (the poweruser escape hatch). None = the Kind default template.
    layout: str | None = None
    # Phase 14x — toolset specialization. Controls which manifest tool
    # GROUPS this agent receives at graph-build time. Empty list defaults
    # to ["all"] (back-compat — agent receives every tool). Other values:
    # ["code"] (only code_* tools), ["manifest"] (only describe_*/list_*/
    # show_*/find_*), ["write"] (only mutating tools), or any combination.
    # The harness applies the filter via make_manifest_tools(); subagents
    # listed in team_members can declare disjoint groups for delegation.
    tool_groups: list[str] = field(default_factory=list)
    # s-mcp-servers-on-agent (2026-07-07, spec
    # 2026-07-07-mcp-first-tools-design.md §5.1) — external MCP servers
    # this agent consumes. Each entry is EITHER a plain string ref
    # ("drawio" ≡ {"ref": "drawio"}) OR a dict with per-agent overrides:
    #   - ref: name of an MCPFederation doc (federations/<ref>.yaml,
    #     inherited from _lib via the standard resolver chain)
    #   - allowed_tools: per-agent allowlist (intersected with the doc's
    #     own allowed_tools; default = everything the doc allows)
    #   - timeout_s: per-agent call-timeout override
    # The harness (make_mcp_tools) connects lazily via a pooled client,
    # converts remote tools to StructuredTools tagged group "mcp:<ref>",
    # and appends them AFTER the tool_groups filter — an agent may be
    # MCP-only (tool_groups: [none] does NOT strip mcp_servers). Empty
    # list/absent = no MCP.
    mcp_servers: list[str | dict[str, Any]] = field(default_factory=list)
    # Phase 14w follow-up (2026-05-08) — per-agent shell sandbox
    # opt-in. ``True`` forces the DeepAgents ``execute`` tool +
    # SessionScopedLocalShellBackend ON for this agent regardless
    # of the scope-wide ``DNA_AGENT_SHELL_SANDBOX`` env. ``False``
    # forces it OFF. ``None`` (default) defers to the env flag.
    # The agent runtime owns the gate logic and the per-session
    # workspace contract.
    shell_sandbox: bool | None = None
    # Phase 3C (2026-05-16, squishy-jumping-nebula) — reflection
    # opt-in. When ``True``, the harness appends a reflection prompt
    # paragraph to the system message instructing the UA to reread
    # its tool calls + outputs and double-check correctness BEFORE
    # emitting the final response. Useful for high-stakes write
    # tools (assessment, evidence, finding) where one wrong arg has
    # auditable consequences. Costs an extra reasoning pass per
    # turn — only enable on agents where the trade-off makes sense.
    # ``None``/``False`` (default) keeps the legacy single-pass behavior.
    reflect_before_write: bool | None = None
    # Phase 1.6 (s-toon-agent-prompts) — opt-in token-efficient encoding
    # for context arrays in this agent's prompt. ``"toon"`` emits TOON
    # (Token-Oriented Object Notation, ~40-60% fewer tokens for uniform
    # arrays). ``"json"`` (default, back-compat) keeps the legacy compact
    # JSON dump. Runtime prompt helpers honor this.
    prompt_format: str | None = None  # "json" | "toon" | None (= "json")
    # s-per-agent-max-turns (2026-05-12) — per-agent recursion budget
    # for delegation.call_agent. Single-turn JSON-gen agents
    # (tool_groups: [none]) can ship max_turns: 3. Multi-turn cognitive
    # scribes that call many read tools before write need 25-30. When
    # absent, falls back to delegation.py's default (25). Translates
    # to LangGraph recursion_limit = max_turns * 4.
    max_turns: int | None = None
    # s-agent-kind-field-langgraph-react (2026-05-12) — choose agent
    # harness. "deepagent" (default, full create_deep_agent with
    # filesystem built-ins + subagents + memory + skills); "langgraph-react"
    # (langgraph.prebuilt.create_react_agent — minimal: model + tools +
    # system_prompt, no built-ins, no GP subagent, no skills middleware).
    # Use "langgraph-react" for simple read agents that only need a
    # small whitelist of tools and compose a response. Avoids the
    # filesystem-bias of deepagents (LLM grabbing ls/grep over manifest
    # tools). Doc: docs.langchain.com/oss/python/langgraph/prebuilt.
    agent_kind: str | None = None  # "deepagent" | "langgraph-react" | None (= "deepagent")
    # Declarative rubric (deepagents RubricMiddleware, beta) — newline-delimited
    # success criteria. When set, build_graph attaches a self-grade loop so the
    # agent iterates (fix → re-grade) until every criterion passes or
    # rubric_max_iterations fires. Lets quality be governed in YAML, not code
    # (e.g. "the agent created a doc and returned its slug"). None = no rubric.
    rubric: str | None = None
    rubric_max_iterations: int | None = None
    # s-ua-agent-contract-fields (2026-05-13) — structural agent
    # contract. Replaces ad-hoc markdown copy-paste with typed fields
    # validated at parse + graph-build time, rendered into the system
    # prompt automatically.
    #
    # mandatory_tool_calls: tool slugs the UA MUST invoke before
    # stopping. Validated by `s-ua-contract-graph-validation` —
    # warn-loud when a slug isn't in `tools` or available via
    # `tool_groups`. Renders into the system prompt as
    # "Mandatory tool calls" by `s-ua-contract-prompt-injection`.
    #
    # input_schema: expected shape of the input the UA receives.
    # dict = inline JSON schema; str = reference to a Skill or
    # KindDefinition that describes the shape. Renders into the
    # system prompt as "Expected Input" with a JSON example.
    #
    # invoked_by_engine: alias of the CognitiveEngine that
    # typically dispatches this UA. Drives discovery — Studio +
    # eval-lab can link agents to their engine and vice-versa.
    # Example: oracle-risk → "oracle-risk-insight".
    mandatory_tool_calls: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] | str | None = None
    invoked_by_engine: str | None = None
    # Phase 3C (2026-05-15) — reflection pattern opt-in. When ``True``,
    # the agent's rendered system prompt gets a "Reflection step"
    # appendix that asks it to enumerate its tool plan + sanity-check
    # the values it's about to pass before issuing the first
    # mandatory_tool_call. Cheap improvement on output quality
    # without changing graph topology. ``False`` / ``None`` disable.
    # Source: Anthropic *Writing Tools for Agents* (reflection
    # consistently improves tool-use correctness, esp. for
    # ``mandatory_tool_calls`` UAs).
    reflect_before_write: bool | None = None
    # P2 architectural fix (2026-05-15) — declarative i18n bundle.
    # Maps locale → {key: literal-string}. Callers resolving a
    # PromptTemplate look up locale_strings[locale][key] instead of
    # hardcoding "português brasileiro" / "English" in Python.
    # Example:
    #   locale_strings:
    #     pt-br: {response_lang: "português brasileiro"}
    #     en:    {response_lang: "English"}
    locale_strings: dict[str, dict[str, str]] | None = None
    # JARVIS — opt-in voice persona block (e-jarvis-voice-module,
    # s-jarvis-voice-persona-schema-py). When set, this UA is reachable
    # via POST /voice/sessions and the harness wires WebRTC + audit WS
    # + (later) MCP egress for it. None = text-only agent.
    voice_persona: VoicePersona | None = None
    # s-jarvis-cross-scope (2026-05-26) — list of scopes this agent's
    # READ tools (recall_*, ecphore, search_documents, list_documents,
    # show_document) may iterate. Writes still land in the agent's
    # mounted scope — this only widens reads. ``["*"]`` means "every
    # scope the source exposes" (used by JARVIS as the user-level
    # personal assistant). Empty/None = legacy single-scope behavior.
    target_scopes: list[str] | None = None
    # Kind-Writer mode (feat/kind-writer-pilot) — declarative contract for
    # a UA that writes a Kind via structured emission. ``writes_kind`` is the
    # target Kind name. ``creative_slots`` are spec fields the LLM fills with
    # generated content. ``system_slots`` maps spec fields to deterministic
    # sources (e.g. ``{"insight": "input.oracle_id"}``) the harness fills.
    # Spec fields only here — no behavior wired yet.
    writes_kind: str | None = None
    creative_slots: list[str] = field(default_factory=list)
    system_slots: dict[str, str] = field(default_factory=dict)
    # Multi-Kind mode (feat/kind-writer-multikind) — a UA that writes N Kinds
    # per run (e.g. narrative-scribe → N ADRs + 1 Retrospective). Maps each
    # target Kind name to its OWN ``{creative_slots, system_slots}`` block, e.g.
    # ``{"ADR": {"creative_slots": [...], "system_slots": {...}},
    #    "Retrospective": {"creative_slots": [...], "system_slots": {...}}}``.
    # An agent uses EITHER ``writes_kind`` (single) OR ``writes_kinds`` (multi),
    # never both. The graph builds one ``emit_<kind>`` tool per entry; the
    # materializer persists one validated doc per emit call in the transcript.
    writes_kinds: dict[str, dict] = field(default_factory=dict)
    # Declarative reads (feat/scribe-migrate-6) — symmetric to system_slots.
    # ``reads`` maps a read-name to its params, e.g.
    # ``{"oracle_verdicts": {"n": 3}, "engrams": {"n": 5}}``. The SYSTEM fetches
    # the data (KIND_WRITER_READERS registry, called directly — not via LLM
    # tool-calls) and injects it into ``dna_input["reads"]`` AND the agent's
    # prompt. The scribe becomes a pure composer (zero read tools).
    reads: dict[str, dict] = field(default_factory=dict)
    # s-delegation-declarative (2026-07-07) — declarative opt-in to the
    # delegation surface (list_delegation_targets / delegate_to). See
    # ``DelegationTargetFor``. None = not a delegation target.
    delegation_target_for: DelegationTargetFor | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> AgentSpec:
        return cls(
            instruction=raw.get("instruction", ""),
            instruction_file=raw.get("instruction_file"),  # NEW
            objective=raw.get("objective", ""),
            model=raw.get("model"),
            type=raw.get("type"),
            soul=raw.get("soul"),
            skills=raw.get("skills") or [],
            tools=raw.get("tools") or [],
            team_members=raw.get("team_members") or [],
            tags=raw.get("tags") or [],
            guardrails=raw.get("guardrails") or [],
            promptTemplate=raw.get("promptTemplate"),
            layout=raw.get("layout"),
            tool_groups=raw.get("tool_groups") or [],
            mcp_servers=raw.get("mcp_servers") or [],
            shell_sandbox=raw.get("shell_sandbox"),
            prompt_format=raw.get("prompt_format"),
            max_turns=raw.get("max_turns"),
            agent_kind=raw.get("agent_kind"),
            mandatory_tool_calls=raw.get("mandatory_tool_calls") or [],
            input_schema=raw.get("input_schema"),
            invoked_by_engine=raw.get("invoked_by_engine"),
            reflect_before_write=raw.get("reflect_before_write"),
            locale_strings=raw.get("locale_strings"),
            rubric=raw.get("rubric"),
            rubric_max_iterations=raw.get("rubric_max_iterations"),
            voice_persona=VoicePersona.from_raw(raw["voice_persona"])
                if isinstance(raw.get("voice_persona"), dict) else None,
            target_scopes=raw.get("target_scopes"),
            writes_kind=raw.get("writes_kind"),
            creative_slots=raw.get("creative_slots") or [],
            system_slots=raw.get("system_slots") or {},
            writes_kinds=raw.get("writes_kinds") or {},
            reads=raw.get("reads") or {},
            delegation_target_for=DelegationTargetFor.from_raw(raw["delegation_target_for"])
                if isinstance(raw.get("delegation_target_for"), dict) else None,
        )


@dataclass
class TypedAgent:
    metadata: Metadata
    spec: AgentSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedAgent:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=AgentSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# Actor (github.com/ruinosus/dna/v1)
#
# Passive kind — not a prompt target. Defines an actor (UML-canonical) with
# traits, role, and an actor_type indicating whether the actor is a human,
# an external system, or a time-based trigger.
# ---------------------------------------------------------------------------

@dataclass
class ActorSpec:
    instruction: str = ""
    traits: list[str] = field(default_factory=list)
    role: str = ""
    actor_type: str = "human"  # "human" | "system" | "time"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> ActorSpec:
        actor_type = raw.get("actor_type", "human")
        if actor_type not in ("human", "system", "time"):
            raise ValueError(
                f"Invalid actor_type: {actor_type!r} (expected 'human', 'system', or 'time')"
            )
        return cls(
            instruction=raw.get("instruction", ""),
            traits=raw.get("traits") or [],
            role=raw.get("role", ""),
            actor_type=actor_type,
        )


@dataclass
class TypedActor:
    metadata: Metadata
    spec: ActorSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedActor:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=ActorSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# UseCase (github.com/ruinosus/dna/v1)
#
# UML use case modeling. Hierarchy: Module -> UseCase -> (Actor, Agent).
# Not a prompt target. Stored as a flat yaml file under use_cases/<name>.yaml.
# ---------------------------------------------------------------------------

@dataclass
class UseCaseSpec:
    primary_actor: str | None = None
    supporting_actors: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    soul: str | None = None
    guardrails: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    main_flow: list[str] = field(default_factory=list)
    alternate_flows: list[dict[str, Any]] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> UseCaseSpec:
        return cls(
            primary_actor=raw.get("primary_actor"),
            supporting_actors=raw.get("supporting_actors") or [],
            agents=raw.get("agents") or [],
            tools=raw.get("tools") or [],
            skills=raw.get("skills") or [],
            soul=raw.get("soul"),
            guardrails=raw.get("guardrails") or [],
            preconditions=raw.get("preconditions") or [],
            main_flow=raw.get("main_flow") or [],
            alternate_flows=raw.get("alternate_flows") or [],
            postconditions=raw.get("postconditions") or [],
            success_criteria=raw.get("success_criteria") or [],
        )


@dataclass
class TypedUseCase:
    metadata: Metadata
    spec: UseCaseSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedUseCase:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=UseCaseSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# Skill (agentskills.io/v1)
#
# Bundle: SKILL.md (frontmatter + instruction body) + optional scripts/,
# references/, assets/ directories. Not a prompt target — referenced by
# agents via spec.skills list.
# ---------------------------------------------------------------------------

@dataclass
class SkillSpec:
    instruction: str = ""
    scripts: dict[str, str] = field(default_factory=dict)
    references: dict[str, str] = field(default_factory=dict)
    assets: dict[str, str] = field(default_factory=dict)
    extras: dict[str, dict[str, str]] = field(default_factory=dict)
    root_files: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SkillSpec:
        return cls(
            instruction=raw.get("instruction", ""),
            scripts=raw.get("scripts", {}) if isinstance(raw.get("scripts"), dict) else {},
            references=raw.get("references", {}) if isinstance(raw.get("references"), dict) else {},
            assets=raw.get("assets", {}) if isinstance(raw.get("assets"), dict) else {},
            extras=raw.get("extras", {}),
            root_files=raw.get("root_files", {}),
        )


@dataclass
class TypedSkill:
    metadata: Metadata
    spec: SkillSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedSkill:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=SkillSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# Soul (soulspec.org/v1)
#
# Bundle: SOUL.md and/or soul.json + optional STYLE.md, AGENTS.md.
# Is a prompt target with flatten_in_context=True.
# Referenced by Agent via spec.soul.
# ---------------------------------------------------------------------------

@dataclass
class SoulSpec:
    soul_content: str = ""
    soul_json: dict[str, Any] | None = None
    style_content: str = ""
    agents_content: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SoulSpec:
        return cls(
            soul_content=raw.get("soul_content", ""),
            soul_json=raw.get("soul_json"),
            style_content=raw.get("style_content", ""),
            agents_content=raw.get("agents_content", ""),
        )


@dataclass
class TypedSoul:
    metadata: Metadata
    spec: SoulSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedSoul:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=SoulSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# HtmlArtifact (github.com/ruinosus/dna/sdlc/v1)
#
# Bundle: ARTIFACT.html (raw HTML, byte-faithful) + optional artifact.json
# (structured metadata: title, description, source, created_at). A first-class
# output of a work item (Story/Feature/Epic/Spike) — the roteiro/design doc
# that used to live in chat becomes a linkable artifact. Record plane.
# ---------------------------------------------------------------------------

@dataclass
class HtmlArtifactSpec:
    html: str = ""
    artifact_json: dict[str, Any] | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> HtmlArtifactSpec:
        aj = raw.get("artifact_json")
        return cls(
            html=raw.get("html", ""),
            artifact_json=aj if isinstance(aj, dict) else None,
        )


@dataclass
class TypedHtmlArtifact:
    metadata: Metadata
    spec: HtmlArtifactSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedHtmlArtifact:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=HtmlArtifactSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# AgentDefinition (agents.md/v1)
#
# The agents.md standard defines an agent archetype via AGENTS.md prose.
# This is a FULL agent definition — not just "context". It specifies the
# agent's identity, conventions, tools, and behavior in Markdown sections.
#
# Is a prompt target with flatten_in_context=True.
# Never filtered by dep_filters — always present in all prompts.
# ---------------------------------------------------------------------------

@dataclass
class AgentDefinitionSpec:
    content: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> AgentDefinitionSpec:
        return cls(content=raw.get("content", ""))


@dataclass
class TypedAgentDefinition:
    metadata: Metadata
    spec: AgentDefinitionSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedAgentDefinition:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=AgentDefinitionSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# Guardrail (github.com/ruinosus/dna/v1)
#
# Safety/compliance rules that agents must follow. Bundle format: GUARDRAIL.md
# with frontmatter (severity, scope) and body containing rules as markdown
# list items. Not a prompt target — composed into prompts via dep_filters
# or programmatic access.
# ---------------------------------------------------------------------------

@dataclass
class GuardrailSpec:
    rules: list[str] = field(default_factory=list)
    # Constrained fields — the documented severity/scope contracts. Typed as
    # Literal so ``_schema_from_model`` emits ``enum`` in the generated JSON
    # Schema (i-validation-shallow): a bare ``str`` mapped to bare
    # ``{"type": "string"}`` and accepted ``severity: critical``/garbage on the
    # write path, which was shallower than a plain Pydantic model. warn lets the
    # turn continue; error fails the turn; hard refuses to answer.
    severity: Literal["warn", "error", "hard"] = "warn"
    scope: Literal["input", "output", "both"] = "both"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> GuardrailSpec:
        return cls(
            rules=raw.get("rules") or [],
            severity=raw.get("severity", "warn"),
            scope=raw.get("scope", "both"),
        )


@dataclass
class TypedGuardrail:
    metadata: Metadata
    spec: GuardrailSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedGuardrail:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=GuardrailSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# SafetyPolicy (github.com/ruinosus/dna/v1)
#
# Declarative safety enforcement. Defines rules for PII masking, content
# safety, topic restriction, prompt injection detection, etc. Rules are
# applied at runtime via a tiered scanner pipeline (regex built-in,
# ML/API/LLM-judge opt-in).
# ---------------------------------------------------------------------------

@dataclass
class SafetyPolicySpec:
    scope: str = "both"       # "input", "output", or "both"
    action: str = "mask"      # "mask", "block", or "log"
    severity: str = "error"   # "error" or "warn"
    rules: list[dict[str, Any]] = field(default_factory=list)
    recognizers: list[str] = field(default_factory=list)
    # Phase 7 — ml-privacy-filter engine. All optional (backward-compatible).
    # Valid engine values: "presidio" (default — Tier-1 regex) or
    # "ml-privacy-filter" (T1 spec lock — openai/privacy-filter ONNX model).
    engine: str = "presidio"
    model: str = "openai/privacy-filter"
    backend: str = "auto"     # "auto" | "transformers" | "onnxruntime"
    threshold: float = 0.8
    # T1 LOCKED — valid values: account_number, private_address,
    # private_email, private_person, private_phone, private_url,
    # private_date, secret. None = all 8 categories.
    categories: list[str] | None = None
    mask_char: str = "[REDACTED]"
    budget_ms: float = 1000.0  # T1 LOCKED: 1000ms (covers ONNX first-call JIT)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SafetyPolicySpec:
        return cls(
            scope=raw.get("scope", "both"),
            action=raw.get("action", "mask"),
            severity=raw.get("severity", "error"),
            rules=raw.get("rules") or [],
            recognizers=raw.get("recognizers") or [],
            engine=raw.get("engine", "presidio"),
            model=raw.get("model", "openai/privacy-filter"),
            backend=raw.get("backend", "auto"),
            threshold=float(raw.get("threshold", 0.8)),
            categories=raw.get("categories"),
            mask_char=raw.get("mask_char", "[REDACTED]"),
            budget_ms=float(raw.get("budget_ms", 1000.0)),
        )


@dataclass
class TypedSafetyPolicy:
    metadata: Metadata
    spec: SafetyPolicySpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedSafetyPolicy:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=SafetyPolicySpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# KindDefinition (github.com/ruinosus/dna/core/v1)
#
# Meta-kind: documents of this kind declaratively define *new* kinds. At
# kernel load time the kernel performs a 2-phase parse — KindDefinitions
# are parsed first, then each is wrapped in a DeclarativeKindPort and
# registered on the kernel. Regular documents are parsed in the second
# phase and can therefore reference these newly registered kinds.
# ---------------------------------------------------------------------------


@dataclass
class KindDefinitionSpec:
    target_api_version: str = ""
    target_kind: str = ""
    alias: str = ""
    origin: str = ""
    is_root: bool = False
    prompt_target: bool = False
    flatten_in_context: bool = False
    schema: dict[str, Any] = field(default_factory=dict)
    docs: str | None = None
    storage: dict[str, Any] = field(default_factory=dict)
    dep_filters: dict[str, str] | None = None
    default_agent: str | None = None
    # Schema fragment composition (Story s-workitem-common-schema-fragment
    # re-scoped 2026-05-12). Open-extension primitive: list of namespaced
    # fragment IDs (e.g. ["sdlc/workitem-common", "medical/care-pathway"]).
    # Any extension can register fragments via kernel.register_schema_fragment(id, dict).
    # DeclarativeKindPort merges them in order; later fragments + Kind-specific
    # properties win over earlier ones.
    schema_fragments: list[str] | None = None
    # Back-compat shorthand: workitem_common: true is treated as
    # schema_fragments: ["sdlc/workitem-common"]. Deprecated; new code should
    # use schema_fragments explicitly.
    workitem_common: bool = False
    # UI hints — read by DeclarativeKindPort.__init__ from raw spec.
    graph_style: dict[str, str] | None = None
    ascii_icon: str | None = None
    display_label: str | None = None
    # ---- F3 descriptor fields (spec 2026-06-10-kinds-descriptor-f3, D2) ----
    # These close the gap between hand-written Kind classes and the
    # declarative descriptor so builtin record Kinds can be expressed as
    # `.kind.yaml` package data. Defaults preserve today's behavior.
    #
    # ``plane``: "composition" | "record" — mirrors KindBase.plane.
    plane: str = "composition"
    # ``tenant_scope``: "tenanted" | "global" — mirrors TenantScope.
    # Default "tenanted" matches the documented TenantScope default, BUT the
    # port only sets ``scope`` when explicitly declared (see
    # ``tenant_scope_declared``) — undeclared kinds stay permissive
    # (Phase 1 back-compat, see Kernel._kind_scope).
    tenant_scope: str = "tenanted"
    # Internal: True iff ``tenant_scope`` was explicitly present in the raw
    # spec. NOT a user-facing field.
    tenant_scope_declared: bool = False
    # ``summary``: declarative list-endpoint projection — {field: default}.
    # List form ["a", "b"] is normalized in from_raw to a dict with
    # per-schema-type defaults (array→[], boolean→False,
    # number/integer→None, else ""). None = no projection (today's None).
    summary: dict[str, Any] | None = None
    # ``embed``: source fields for embedding text (feeds D4 derivation).
    embed: list[str] | None = None
    # ``is_runtime_artifact``: docs generated by runtime workflows. The port
    # already read this via getattr but from_raw never populated it.
    is_runtime_artifact: bool = False
    # ``prompt_target_priority``: was hardcoded 5 in DeclarativeKindPort —
    # default 5 preserves that.
    prompt_target_priority: int = 5
    # Kernel classification flags — mirror KindBase defaults.
    scope_inheritable: bool = True
    is_overlayable: bool = True
    # Extra volatile spec fields, unioned with KindBase.VOLATILE_SPEC_FIELDS.
    volatile_spec_fields: list[str] | None = None
    # ---- Descriptor expressiveness fields (spec 2026-06-11, D1/D3-D7) -------
    # All optional; absent → None preserves today's behavior. Consumed by
    # DeclarativeKindPort (kernel/meta.py).
    #
    # D1 ``ui``: raw StudioUIMetadata mapping. ``from_raw`` validates keys ⊆
    # StudioUIMetadata fields (strict — unknown key → ValueError); the port
    # reconstructs the real dataclass so the /kinds/manifest output is
    # byte-identical to the deleted class version.
    ui: dict[str, Any] | None = None
    # D3 ``describe``: template string ("{name} ({status})") OR projection
    # mapping ({"path": "description"}). The port renders the display string.
    describe: str | dict[str, Any] | None = None
    # D4 ``ui_schema``: pass-through widget-hint bag (field → {widget,...}).
    # Permissive — unknown keys allowed (this is an explicitly UI-owned bag,
    # unlike ``ui``). Exposed as ``port.ui_schema``.
    ui_schema: dict[str, Any] | None = None
    # D5 ``spec_defaults``: shallow-merge map applied as {**spec_defaults,
    # **spec} BEFORE schema validation in the port's parse().
    spec_defaults: dict[str, Any] | None = None
    # D6 ``default_agent_field``: spec field whose value is returned VERBATIM
    # by get_default_agent_name (no ``or None`` coercion).
    default_agent_field: str | None = None
    # D7 ``description_fallback_field``: pass-through string attr telling Studio
    # which spec field acts as the card description fallback.
    description_fallback_field: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> KindDefinitionSpec:
        missing = [
            f for f in ("target_api_version", "target_kind", "alias", "origin", "storage")
            if not raw.get(f)
        ]
        if missing:
            raise ValueError(
                f"KindDefinition spec missing required fields: {', '.join(missing)}"
            )
        storage = raw.get("storage")
        if not isinstance(storage, dict):
            raise ValueError("KindDefinition spec.storage must be a dict")
        schema = raw.get("schema") or {}
        if not isinstance(schema, dict):
            raise ValueError("KindDefinition spec.schema must be a dict (JSON Schema)")
        # ---- F3 fields (spec D2) ----------------------------------------
        plane = raw.get("plane", "composition")
        if plane not in ("composition", "record"):
            raise ValueError(
                f"KindDefinition spec.plane must be 'composition' or 'record', got {plane!r}"
            )
        tenant_scope = raw.get("tenant_scope", "tenanted")
        if tenant_scope not in ("tenanted", "global"):
            raise ValueError(
                f"KindDefinition spec.tenant_scope must be 'tenanted' or 'global', "
                f"got {tenant_scope!r}"
            )
        summary = cls._normalize_summary(raw.get("summary"), schema)
        # ---- Descriptor expressiveness validation (spec D1/D3/D4) -----------
        ui = raw.get("ui")
        if ui is not None:
            if not isinstance(ui, dict):
                raise ValueError(
                    "KindDefinition spec.ui must be a mapping of "
                    f"StudioUIMetadata fields, got {type(ui).__name__}"
                )
            # Single source of truth: the allowed key set IS StudioUIMetadata's
            # dataclass fields — never hardcode a second list (D1).
            from dna.kernel.studio_ui import StudioUIMetadata

            allowed = set(StudioUIMetadata.__dataclass_fields__)
            unknown = set(ui) - allowed
            if unknown:
                raise ValueError(
                    "KindDefinition spec.ui has unknown key(s): "
                    f"{', '.join(sorted(unknown))} "
                    f"(allowed: {', '.join(sorted(allowed))})"
                )
        describe = raw.get("describe")
        if describe is not None and not isinstance(describe, (str, dict)):
            raise ValueError(
                "KindDefinition spec.describe must be a template string or a "
                f"{{path}} mapping, got {type(describe).__name__}"
            )
        ui_schema = raw.get("ui_schema")
        if ui_schema is not None and not isinstance(ui_schema, dict):
            raise ValueError(
                "KindDefinition spec.ui_schema must be a mapping, "
                f"got {type(ui_schema).__name__}"
            )
        spec_defaults = raw.get("spec_defaults")
        if spec_defaults is not None and not isinstance(spec_defaults, dict):
            raise ValueError(
                "KindDefinition spec.spec_defaults must be a mapping, "
                f"got {type(spec_defaults).__name__}"
            )
        return cls(
            target_api_version=raw["target_api_version"],
            target_kind=raw["target_kind"],
            alias=raw["alias"],
            origin=raw["origin"],
            is_root=bool(raw.get("is_root", False)),
            prompt_target=bool(raw.get("prompt_target", False)),
            flatten_in_context=bool(raw.get("flatten_in_context", False)),
            schema=schema,
            docs=raw.get("docs"),
            storage=storage,
            dep_filters=raw.get("dep_filters"),
            default_agent=raw.get("default_agent"),
            workitem_common=bool(raw.get("workitem_common", False)),
            schema_fragments=raw.get("schema_fragments"),
            graph_style=raw.get("graph_style"),
            ascii_icon=raw.get("ascii_icon"),
            display_label=raw.get("display_label"),
            # F3 (spec D2)
            plane=plane,
            tenant_scope=tenant_scope,
            tenant_scope_declared="tenant_scope" in raw,
            summary=summary,
            embed=raw.get("embed"),
            is_runtime_artifact=bool(raw.get("is_runtime_artifact", False)),
            prompt_target_priority=int(raw.get("prompt_target_priority", 5)),
            scope_inheritable=bool(raw.get("scope_inheritable", True)),
            is_overlayable=bool(raw.get("is_overlayable", True)),
            volatile_spec_fields=raw.get("volatile_spec_fields"),
            # Descriptor expressiveness (spec D1/D3-D7)
            ui=ui,
            describe=describe,
            ui_schema=ui_schema,
            spec_defaults=spec_defaults,
            default_agent_field=raw.get("default_agent_field"),
            description_fallback_field=raw.get("description_fallback_field"),
        )

    @staticmethod
    def _normalize_summary(
        summary: Any, schema: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Normalize spec.summary to its dict form (F3 spec D2).

        Dict form ``{field: default}`` passes through. List form
        ``["a", "b"]`` gets a default per the field's declared type in
        ``schema.properties``: array→[], boolean→False,
        number/integer→None, anything else (incl. fields absent from the
        schema)→"".
        """
        if summary is None:
            return None
        if isinstance(summary, dict):
            return summary
        if isinstance(summary, list):
            props = schema.get("properties") or {}
            out: dict[str, Any] = {}
            for field_name in summary:
                prop = props.get(field_name)
                ptype = prop.get("type") if isinstance(prop, dict) else None
                if ptype == "array":
                    out[field_name] = []
                elif ptype == "boolean":
                    out[field_name] = False
                elif ptype in ("number", "integer"):
                    out[field_name] = None
                else:
                    out[field_name] = ""
            return out
        raise ValueError(
            "KindDefinition spec.summary must be a dict {field: default} or a "
            f"list of field names, got {type(summary).__name__}"
        )


@dataclass
class TypedKindDefinition:
    metadata: Metadata
    spec: KindDefinitionSpec

    API_VERSION = "github.com/ruinosus/dna/core/v1"
    KIND = "KindDefinition"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedKindDefinition:
        av = raw.get("apiVersion", cls.API_VERSION)
        if av != cls.API_VERSION:
            raise ValueError(
                f"TypedKindDefinition expects apiVersion={cls.API_VERSION!r}, got {av!r}"
            )
        kn = raw.get("kind", cls.KIND)
        if kn != cls.KIND:
            raise ValueError(
                f"TypedKindDefinition expects kind={cls.KIND!r}, got {kn!r}"
            )
        typed = cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=KindDefinitionSpec.from_raw(raw.get("spec", {})),
        )
        # s-dna-kindport-descriptor-schema: AFTER the hand-rolled checks
        # (which own the didactic error messages), validate the effective
        # envelope against the published JSON Schema
        # (docs/schemas/kind-definition.schema.json) — the backstop that
        # catches typo'd/unknown spec fields and wrong types the
        # hand-rolled checks silently ignored. apiVersion/kind are folded
        # in with their defaults so partial raws keep working.
        from dna.kernel.kind_definition_schema import (
            validate_kind_definition,
        )
        validate_kind_definition({**raw, "apiVersion": av, "kind": kn})
        return typed


# ---------------------------------------------------------------------------
# Hook (github.com/ruinosus/dna/v1)
#
# Declarative hook definition. Allows users to declare middleware and
# event hooks as YAML documents in the manifest, auto-registered on
# the kernel's HookRegistry at instance time.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Recognizer (presidio/v1)
#
# Presidio ad-hoc recognizer for detecting PII entities using regex
# patterns or deny lists. Referenced by SafetyPolicy via dep_filters.
# ---------------------------------------------------------------------------

@dataclass
class RecognizerPattern:
    name: str = ""
    regex: str = ""
    score: float = 0.5

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> RecognizerPattern:
        return cls(
            name=raw.get("name", ""),
            regex=raw.get("regex", ""),
            score=float(raw.get("score", 0.5)),
        )


@dataclass
class RecognizerSpec:
    entity_type: str = ""
    language: str = "en"
    patterns: list[dict[str, Any]] = field(default_factory=list)
    deny_list: list[str] = field(default_factory=list)
    context: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> RecognizerSpec:
        return cls(
            entity_type=raw.get("entity_type", ""),
            language=raw.get("language", "en"),
            patterns=raw.get("patterns") or [],
            deny_list=raw.get("deny_list") or [],
            context=raw.get("context") or [],
        )


@dataclass
class TypedRecognizer:
    metadata: Metadata
    spec: RecognizerSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedRecognizer:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=RecognizerSpec.from_raw(raw.get("spec", {})),
        )


@dataclass
class HookSpec:
    target: str = "pre_build_prompt"
    type: str = "middleware"       # "middleware" or "event"
    action: str = "inject_fields"  # "inject_fields", "log", "script"
    fields: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> HookSpec:
        return cls(
            target=raw.get("target", "pre_build_prompt"),
            type=raw.get("type", "middleware"),
            action=raw.get("action", "inject_fields"),
            fields=raw.get("fields") or {},
            body=raw.get("body", ""),
        )


@dataclass
class TypedHook:
    metadata: Metadata
    spec: HookSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedHook:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=HookSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# Community channel — artifact allowlist
#
# Spec: docs/superpowers/specs/2026-05-18-source-as-distribution.md.
# The CommunityItem Kind was pruned (s-prune-speculative-extensions,
# recovery: git history), but the FS distribution / install channel
# (dna_shared.community.* + /community/discover + POST /catalog/install)
# lives on and validates installable artifact kinds against this
# allowlist (dna_shared/validation/bundle.py).
# ---------------------------------------------------------------------------

# Allowlist of artifact_kind values. Locked-in decision #1 of the
# source-as-distribution spec. Adding a Kind here requires the same
# entry in the TS twin (typescript/src/kernel/models.ts).
COMMUNITY_ARTIFACT_KINDS = frozenset({
    "Skill", "Soul", "Agent", "Hook",
    "SafetyPolicy", "Recognizer", "Guardrail",
})


# ---------------------------------------------------------------------------
# TextBlock + HtmlBlock (github.com/ruinosus/dna/v1) — generative blocks
#
# Spec: s-generative-blocks (2026-05-19). Any agent (voice-episode-scribe,
# story-analyst, etc.) can persist a free-form text or HTML block. Studio's
# JARVIS bench renders them in TextSlot/HtmlSlot. HtmlBlock body lands in
# an iframe sandbox="" — pattern Open Generative UI from CopilotKit/AG-UI.
#
# 4-axis taxonomy (matches LessonLearned):
#   - owner (Semon privacy: general vs agent-private; default null/general)
#   - generated_by (provenance)
#   - area (subject — Feature/X, Genome/Y, ...)
#   - affect (emotional tone — optional, mostly for voice-derived blocks)
# ---------------------------------------------------------------------------

@dataclass
class TextBlockSpec:
    """A markdown text block authored by an agent or human."""
    title: str = ""
    body: str = ""                            # markdown content
    area: str = ""                            # Feature/X, Epic/Y, etc.
    owner: str | None = None                  # agent slug | None=general
    generated_by: str = ""                    # provenance: who wrote it
    affect: str = ""                          # optional emotional tone
    tags: list[str] = field(default_factory=list)
    created_at: str = ""                      # ISO 8601 UTC

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TextBlockSpec:
        tags = raw.get("tags") or []
        return cls(
            title=raw.get("title", ""),
            body=raw.get("body", ""),
            area=raw.get("area", ""),
            owner=raw.get("owner") or None,
            generated_by=raw.get("generated_by", ""),
            affect=raw.get("affect", ""),
            tags=list(tags) if isinstance(tags, list) else [],
            created_at=raw.get("created_at", ""),
        )


@dataclass
class TypedTextBlock:
    metadata: Metadata
    spec: TextBlockSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedTextBlock:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=TextBlockSpec.from_raw(raw.get("spec", {})),
        )


@dataclass
class HtmlBlockSpec:
    """An HTML block authored by an agent. Rendered in sandboxed iframe."""
    title: str = ""
    body: str = ""                            # raw HTML
    area: str = ""
    owner: str | None = None
    generated_by: str = ""
    affect: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    # Optional iframe sandbox feature list — comma-separated tokens (e.g.
    # "allow-popups,allow-popups-to-escape-sandbox"). Empty = fully
    # locked-down (no JS, no popups, no navigation).
    sandbox_features: str = ""
    # Estimated render height in px (renderer fallback if ResizeObserver
    # can't measure). Agents can hint; renderer uses 480 as default.
    estimated_height_px: int = 0

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> HtmlBlockSpec:
        tags = raw.get("tags") or []
        return cls(
            title=raw.get("title", ""),
            body=raw.get("body", ""),
            area=raw.get("area", ""),
            owner=raw.get("owner") or None,
            generated_by=raw.get("generated_by", ""),
            affect=raw.get("affect", ""),
            tags=list(tags) if isinstance(tags, list) else [],
            created_at=raw.get("created_at", ""),
            sandbox_features=raw.get("sandbox_features", ""),
            estimated_height_px=int(raw.get("estimated_height_px", 0) or 0),
        )


@dataclass
class TypedHtmlBlock:
    metadata: Metadata
    spec: HtmlBlockSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedHtmlBlock:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=HtmlBlockSpec.from_raw(raw.get("spec", {})),
        )


# ---------------------------------------------------------------------------
# HtmlTemplate — Mustache-templated HTML reusable across many renders.
#
# Story: s-html-templates (2026-05-19). JARVIS "hologram" pattern: instead
# of regenerating layout from scratch every time, the agent picks a
# template from a catalog and fills in the data. Cuts tokens by 10x,
# enforces visual coherence, and gives the bench a library that grows.
#
# Bundle layout: ``html-templates/<slug>/TEMPLATE.html``
#   • frontmatter: name, description, version, params, example, theme
#   • body: Mustache HTML (escapes by default — XSS-safe)
# ---------------------------------------------------------------------------

@dataclass
class HtmlTemplateSpec:
    """A reusable Mustache-templated HTML widget.

    Body is a Mustache template string. Rendering happens at the
    consumer side (frontend mustache.js or backend chevron). The
    rendered output is fed to HtmlBlock.body for sandboxed display.
    """
    title: str = ""               # display label in catalogs / UI
    description: str = ""         # what this template renders, for the LLM
    body: str = ""                # Mustache template HTML
    version: str = "0.1.0"        # semver — bump on breaking schema changes
    # JSON-Schema-shaped param descriptor. Open-ended on purpose so the
    # author can decide how strict to be. Typical shape:
    #   { "title": {"type": "string", "required": true},
    #     "items": {"type": "array", "items": {...}} }
    params: dict[str, Any] = field(default_factory=dict)
    # Optional preview seed — Studio + JARVIS use this to show what the
    # template looks like without binding to live data.
    example: dict[str, Any] = field(default_factory=dict)
    # Optional skin name — applied as an extra wrapper class so a
    # consistent design language (e.g. "jarvis-neon") can be themed
    # across templates. Empty = use the default HtmlSlot wrapper.
    theme: str = ""
    area: str = ""
    owner: str | None = None
    generated_by: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> HtmlTemplateSpec:
        tags = raw.get("tags") or []
        params = raw.get("params") or {}
        example = raw.get("example") or {}
        return cls(
            title=raw.get("title", ""),
            description=raw.get("description", ""),
            body=raw.get("body", ""),
            version=raw.get("version", "0.1.0"),
            params=dict(params) if isinstance(params, dict) else {},
            example=dict(example) if isinstance(example, dict) else {},
            theme=raw.get("theme", ""),
            area=raw.get("area", ""),
            owner=raw.get("owner") or None,
            generated_by=raw.get("generated_by", ""),
            tags=list(tags) if isinstance(tags, list) else [],
            created_at=raw.get("created_at", ""),
        )


@dataclass
class TypedHtmlTemplate:
    metadata: Metadata
    spec: HtmlTemplateSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedHtmlTemplate:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=HtmlTemplateSpec.from_raw(raw.get("spec", {})),
        )
# ── DNA namespace ──────────────────────────────────────────────────────────
# Single authoritative namespace constant (spec §8: swapping the namespace
# is one commit + a golden regen). NOTE: literal-type positions
# (typing.Literal / schema literals / *.kind.yaml descriptors) must stay in
# sync with this value — the descriptor + parity suites enforce it.
DNA_NAMESPACE = "github.com/ruinosus/dna"
