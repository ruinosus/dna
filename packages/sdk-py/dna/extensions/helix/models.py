"""Typed models for the five Kinds HelixExtension registers.

``Genome``, ``LayerPolicy``, ``Agent``, ``Actor``, ``UseCase`` — plus the three
nested value objects that only their specs use (``CompositionRule``,
``VoicePersona``, ``DelegationTargetFor``).

Owned by the extension that REGISTERS the Kinds (i-109) — see
``dna/extensions/soulspec/models.py`` for the argument. Only
:class:`~dna.kernel.models.Metadata` comes from the kernel.

⚠️ **Genome and LayerPolicy are bootstrap Kinds and still live here.** They are
two of the three names in ``kernel/protocols.py::BOOTSTRAP_KIND_NAMES``, which
is the kernel's LOAD ORDER — a list of Kind NAMES, not of Kind schemas. The
kernel needs to know that a Kind called ``Genome`` is loaded first; it does not
need to know what a ``GenomeSpec`` contains, and it never imported these
classes. ``KindDefinition`` is the one that differs, and it differs for a
measured reason: ``kernel/meta.py``, ``kernel/kinds/registry.py`` and
``kernel/write/namespace_gate.py`` really do parse instances with
``TypedKindDefinition``, because a Kind is BORN from one. That class stays in
``kernel/models.py``; these five do not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dna.kernel.models import Metadata

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
    # NOT a reference, despite the `_id` suffix — this is the layer DIMENSION
    # name, one half of the `(layer_id, layer_value)` coordinate that addresses
    # an overlay: `layer_id` is the axis (`tenant`, `branch`, `region`, `user`),
    # `layer_value` is the point on it (`acme`, `feature-x`, `prod`). Measured,
    # not assumed: it is matched by STRING EQUALITY against the layer being
    # written (``compose/layer_policy.py``) and against the keys of the
    # ``layers`` dict at compose time (``compose/instance_builder.py``), and it
    # is used verbatim as a filesystem path segment and as a
    # ``dna_layer_instances`` primary-key column — plain TEXT, no foreign key,
    # no CHECK, no enum type. There is no ``Layer`` Kind and never has been. The
    # ``["tenant", "branch", "region", "user"]`` list in
    # ``LayerPolicyKind.ui_schema`` is advisory only: nothing validates against
    # it, and the test suite deliberately uses values outside it (``env``,
    # ``composition``, ``hybrid``), so turning it into an ``enum`` would be a
    # behaviour change, not documentation.
    layer_id: str = field(
        default="",
        metadata={"description": (
            "Which layer DIMENSION this policy governs (e.g. tenant, branch, "
            "region, user). NOT a reference: it is matched by exact string "
            "equality against the layer being composed or written — the "
            "`layer_id` half of the (layer_id, layer_value) overlay "
            "coordinate. No `Layer` Kind exists; the `_id` suffix names an "
            "axis, not an instance."
        )},
    )
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
    # The harness applies the filter via kernel.get_tools(groups=...);
    # subagents in team_members can declare disjoint groups for delegation.
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
    # f-meus-copilotos (dna-cloud, 2026-08-05) — o que o portal escrevia e o
    # SDK não falava. Dois campos que o funil de criação de copilotos grava
    # há semanas e que NÃO eram AgentSpec: o writer do AGENT.md os descartava
    # do frontmatter e o reader (canônico) os perdia para sempre; o emit nem
    # os lia. Como o allowlist do frontmatter deriva DESTE dataclass, declarar
    # aqui abre reader+writer de uma vez (o desenho anti-drift de 2026-05-08).
    #
    # description: o que este agente É, no spec (o metadata.description
    # continua existindo; este é o campo que superfícies de manutenção editam
    # junto com a instrução).
    description: str = ""
    # tools_requiring_confirmation: gate HITL POR AGENTE — cada chamada destas
    # tools pede confirmação humana antes de executar. UNIDO ao conjunto
    # derivado dos Tool docs (`Tool.spec.requires_confirmation`) em
    # build_copilot_context: o Tool doc diz "esta tool é sensível SEMPRE";
    # este campo diz "NESTE agente, esta tool pede confirmação" — política
    # por copiloto, que era exatamente o que o blueprint prometia e não
    # entregava.
    tools_requiring_confirmation: list[str] = field(default_factory=list)
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
    # READ tools (recall_*, ecphore, search_instances, list_instances,
    # show_instance) may iterate. Writes still land in the agent's
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
            description=raw.get("description", ""),
            tools_requiring_confirmation=raw.get("tools_requiring_confirmation") or [],
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


__all__ = [
    "ActorSpec",
    "AgentSpec",
    "CompositionRule",
    "DelegationTargetFor",
    "GenomeSpec",
    "LayerPolicySpec",
    "TypedActor",
    "TypedAgent",
    "TypedGenome",
    "TypedLayerPolicy",
    "TypedUseCase",
    "UseCaseSpec",
    "VoicePersona",
]
