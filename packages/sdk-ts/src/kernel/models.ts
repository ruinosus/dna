/**
 * Typed Zod schemas for each kind — used by KindPort.parse().
 *
 * 1:1 parity with Python dna.v3.kernel.models.
 */

import { z } from "zod";
import { UI_METADATA_FIELDS } from "./studio_ui.js";

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------

export const MetadataSchema = z.object({
  name: z.string(),
  description: z.string().optional().default(""),
  version: z.string().optional().default(""),
  icon: z.string().optional().default(""),
  group: z.string().optional().default(""),
  labels: z.record(z.string()).default({}),
});

export type Metadata = z.output<typeof MetadataSchema>;


// ---------------------------------------------------------------------------
// Genome (github.com/ruinosus/dna/v1) — Phase 16 (scope segregation)
//
// Replaces Module as the scope-root identity + runtime config doc.
// Catalog identity (owner, version, visibility) lives here. Layer policy
// moved out to ``LayerPolicy`` Kind. Custom Kinds moved out to
// ``KindDefinition`` Kind. Bill-of-materials inventory arrays
// (agents[], skills[], actors[], etc.) deleted — composition validation
// walks scanner output directly.
//
// Tenant overlay applies only to ``OVERLAYABLE_FIELDS`` declared on the
// GenomeKind class (see typescript/src/extensions/helix.ts). Identity
// (owner_tenant, version, visibility, deprecated*, repository,
// dependencies) is structurally non-overlayable.
//
// 1:1 parity with Python dna.kernel.models.GenomeSpec.
// ---------------------------------------------------------------------------

export const GenomeSpecSchema = z.object({
  // Catalog identity — non-overlayable.
  owner: z.string().nullish(),
  owner_tenant: z.string().nullish(),
  repository: z.string().nullish(),
  visibility: z.enum(["public", "internal", "private"]).default("public"),

  // i-112 OQ1 — a mandatory Catalog capability is installed-by-default +
  // non-removable; global_scope = global runtime lookup (like the model
  // registry). Catalog identity → NOT overlayable.
  mandatory: z.boolean().default(false),
  global_scope: z.boolean().default(false),

  // Composition Engine V2 (Phase 17, s-comp-f1-schema, 2026-05-28):
  // Declarative parent scope for cross-scope inheritance. null = root.
  // Resolution walks the chain. Per-Kind composition_rules in
  // LayerPolicy govern which Kinds inherit + merge_strategy.
  parent_scope: z.string().nullish(),

  // Versioning — non-overlayable.
  version: z.string().nullish(),
  changelog_url: z.string().nullish(),
  deprecated: z.boolean().default(false),
  deprecated_message: z.string().nullish(),

  // Runtime defaults — overlayable per tenant.
  default_agent: z.string().optional(),
  default_llm: z.string().optional(),
  budget: z.record(z.unknown()).nullish(),
  tags: z.array(z.string()).default([]),

  // i-112 ph2 — capability manifest: what this Genome PROVIDES. Each entry
  // {kind, name, location}. Catalog identity → NOT overlayable. The resolver
  // (Phase 3) reads this to load capabilities from installed packages.
  capabilities: z.array(z.record(z.unknown())).default([]),

  // External deps — non-overlayable (lockfile resolves).
  dependencies: z.array(z.record(z.unknown())).default([]),
});

export const GenomeSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("Genome"),
  metadata: MetadataSchema,
  spec: GenomeSpecSchema.default({}),
});

export type TypedGenome = z.output<typeof GenomeSchema>;

// ---------------------------------------------------------------------------
// LayerPolicy (github.com/ruinosus/dna/policy/v1) — Phase 16
//
// One LayerPolicy doc per layer dimension (e.g. tenant, branch, region).
// Lives at ``<scope>/policies/<id>.yaml``. Replaces ``Module.spec.layers``.
// Read by the kernel in write-time enforcement; Some Kinds are
// structurally non-overlayable (Genome, KindDefinition, LayerPolicy
// itself) — their policy is always locked regardless of doc contents.
//
// Policy values: ``open`` (default — never raises),
// ``restricted`` (only override existing top-level spec keys),
// ``locked`` (any write raises).
//
// 1:1 parity with Python dna.kernel.models.LayerPolicySpec.
// ---------------------------------------------------------------------------

// Composition Engine V2 (Phase 17, s-comp-f1-schema, 2026-05-28).
// 1:1 parity with Python CompositionRule.
export const CompositionRuleSchema = z.object({
  scope_inheritance: z.enum(["enabled", "disabled"]).default("enabled"),
  merge_strategy: z.enum(["override_full", "field_level"]).default("override_full"),
  tenant_overlay: z.enum(["none", "field_level"]).default("field_level"),
});

export type CompositionRule = z.output<typeof CompositionRuleSchema>;

export const LayerPolicySpecSchema = z.object({
  layer_id: z.string().default(""),
  // Map of kind alias → policy string. Values are normalized to
  // lowercase by the parse hook on the KindPort (TypeScript Zod runs
  // its own coercion via .transform on the LayerPolicyKind to mirror
  // Python's LayerPolicySpec.from_raw normalization).
  policies: z.record(z.string()).default({}),
  // Composition Engine V2: per-Kind composition rules (1:1 parity
  // with Python LayerPolicySpec.composition_rules). Absent Kinds fall
  // back to opt-in defaults (no inheritance, no overlay).
  composition_rules: z.record(CompositionRuleSchema).default({}),
});

export const LayerPolicySchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/policy/v1"),
  kind: z.literal("LayerPolicy"),
  metadata: MetadataSchema,
  spec: LayerPolicySpecSchema.default({}),
});

export type TypedLayerPolicy = z.output<typeof LayerPolicySchema>;

// ---------------------------------------------------------------------------
// Agent (github.com/ruinosus/dna/v1)
// ---------------------------------------------------------------------------

export const AgentSpecSchema = z.object({
  instruction: z.string().optional().default(""),
  instruction_file: z.string().optional(),
  objective: z.string().optional().default(""),
  model: z.string().optional(),
  type: z.string().optional(),
  soul: z.string().optional(),
  skills: z.array(z.string()).default([]),
  tools: z.array(z.string()).default([]),
  team_members: z.array(z.string()).default([]),
  tags: z.array(z.string()).default([]),
  guardrails: z.array(z.string()).default([]),
  promptTemplate: z.string().optional(),
  // s-dx-named-layouts — pick the composition ORDER by name instead of
  // hand-writing raw Mustache. "persona-first" puts the Soul before the
  // instruction; "instruction-first" (a.k.a. "default") keeps the historic
  // order. Resolved by the Kind's layoutTemplate() into an embedded preset.
  // A raw promptTemplate still wins over layout when both are set.
  layout: z.string().optional(),
  // Phase 14x — tool-group specialization (TS parity with Python).
  tool_groups: z.array(z.string()).default([]),
  // s-mcp-servers-on-agent (2026-07-07, spec
  // 2026-07-07-mcp-first-tools-design.md §5.1) — external MCP servers
  // this agent consumes. Each entry is EITHER a plain string ref
  // ("drawio" ≡ {ref: "drawio"}) OR an object with per-agent overrides:
  // ref (MCPFederation doc name, inherited from _lib), allowed_tools
  // (per-agent allowlist ∩ the doc's own), timeout_s (call-timeout
  // override). Runtime consumption is Python-only (make_mcp_tools);
  // the TS SDK ships the schema for parity + Studio.
  mcp_servers: z
    .array(
      z.union([
        z.string(),
        z
          .object({
            ref: z.string(),
            allowed_tools: z.array(z.string()).optional(),
            timeout_s: z.number().optional(),
          })
          .passthrough(),
      ]),
    )
    .default([]),
  // Phase 14w follow-up (2026-05-08) — per-agent shell sandbox
  // opt-in (TS parity with Python). ``true`` forces the
  // DeepAgents ``execute`` tool ON for this agent regardless of
  // the scope-wide ``DNA_AGENT_SHELL_SANDBOX`` env. ``false``
  // forces it OFF. Absent (the default) defers to the env.
  shell_sandbox: z.boolean().optional(),
  // Phase 3C (2026-05-15) — reflection pattern opt-in (TS parity
  // with Python). When true, graph.py renders a "Reflection step
  // (before tool calls)" block into the system prompt instructing
  // the UA to enumerate its plan in one turn before issuing any
  // write tool. Pattern from Anthropic Writing Tools for Agents —
  // reduces uncreated rate for UAs with mandatory_tool_calls.
  reflect_before_write: z.boolean().optional(),
  // P2 architectural fix (2026-05-15) — declarative i18n bundle
  // (TS parity with Python). Maps locale → {key: literal-string}.
  // Callers resolving a PromptTemplate look up
  // locale_strings[locale][key] instead of hardcoding strings in code.
  locale_strings: z.record(z.string(), z.record(z.string(), z.string())).optional(),
  // Phase 1.6 (s-toon-agent-prompts) — opt-in token-efficient
  // encoding for context arrays. ``"toon"`` uses TOON (~40-60%
  // fewer tokens for uniform arrays); ``"json"`` (default,
  // back-compat) uses compact JSON. Runtime prompt
  // helpers honor this.
  prompt_format: z.enum(["json", "toon"]).optional(),
  // s-per-agent-max-turns (2026-05-12) — per-agent recursion budget
  // for delegation.call_agent. Single-turn JSON-gen agents
  // (tool_groups: [none]) can ship max_turns: 3. Multi-turn cognitive
  // scribes that call many read tools before write need 25-30.
  // Absent → delegation.py default (25). LangGraph recursion_limit
  // = max_turns * 4.
  max_turns: z.number().int().positive().optional(),
  // s-agent-kind-field-langgraph-react (2026-05-12) — pick agent
  // harness. "deepagent" (default) = full create_deep_agent.
  // "langgraph-react" = lightweight create_react_agent (no filesystem
  // built-ins, no GP subagent). For simple read agents.
  agent_kind: z.enum(["deepagent", "langgraph-react"]).optional(),
  // s-ua-agent-contract-fields (2026-05-13) — structural agent
  // contract. Replaces ad-hoc markdown copy-paste with typed fields
  // validated at parse + graph-build time, rendered into the system
  // prompt automatically.
  //
  // mandatory_tool_calls: tool slugs the UA MUST invoke before
  // stopping. Validated by `s-ua-contract-graph-validation` —
  // warn-loud when a slug isn't in `tools` or available via
  // `tool_groups`. Renders into the system prompt as
  // "Mandatory tool calls" by `s-ua-contract-prompt-injection`.
  //
  // input_schema: expected shape of the input the UA receives.
  // Object = inline JSON schema; string = reference to a Skill
  // or KindDefinition that describes the shape. Renders into the
  // system prompt as "Expected Input" with a JSON example.
  //
  // invoked_by_engine: alias of the CognitiveEngine that
  // typically dispatches this UA. Drives discovery — Studio +
  // eval-lab link agents to their engine.
  mandatory_tool_calls: z.array(z.string()).default([]),
  input_schema: z.union([z.record(z.unknown()), z.string()]).optional(),
  invoked_by_engine: z.string().optional(),
  // JARVIS — opt-in voice persona block (e-jarvis-voice-module).
  // Presence flips the UA from text-only to voice-reachable via
  // POST /voice/sessions. Mirrors Python `VoicePersona` dataclass.
  voice_persona: z.object({
    voice: z.string().default("cedar"),
    style: z.string().optional(),
    archetype: z.string().optional(),
    interruption_tolerance: z.enum(["high", "medium", "low"]).default("high"),
    preamble: z.boolean().default(false),
    mcp_egress: z.boolean().default(false),
    wake_word: z.string().optional(),
    budget: z.number().default(5.0),
  }).optional(),
  // s-jarvis-cross-scope (2026-05-26) — list of scopes this agent's
  // READ tools (recall_*, ecphore, search_documents, list_documents)
  // may iterate. Writes still land in the mounted scope. ``["*"]``
  // means "every scope the source exposes" — used by JARVIS as the
  // user-level personal assistant. Empty/undefined = legacy single-
  // scope behaviour. Mirrors Python ``AgentSpec.target_scopes``.
  target_scopes: z.array(z.string()).optional(),
  // Kind-Writer mode (feat/kind-writer-pilot) — declarative contract for a
  // UA that writes a Kind via structured emission (TS parity with Python).
  // ``writes_kind`` is the target Kind name. ``creative_slots`` are spec
  // fields the LLM fills with generated content. ``system_slots`` maps spec
  // fields to deterministic sources (e.g. {"insight": "input.oracle_id"}).
  // Spec fields only here — no behavior wired yet.
  writes_kind: z.string().optional(),
  creative_slots: z.array(z.string()).default([]),
  system_slots: z.record(z.string(), z.string()).default({}),
  // Multi-Kind mode (feat/kind-writer-multikind) — a UA that writes N Kinds
  // per run (e.g. narrative-scribe → N ADRs + 1 Retrospective). Maps each
  // target Kind name to its OWN {creative_slots, system_slots} block. An agent
  // uses EITHER writes_kind (single) OR writes_kinds (multi), never both.
  // (TS parity with Python AgentSpec.writes_kinds.)
  writes_kinds: z
    .record(z.string(), z.record(z.string(), z.any()))
    .default({}),
  // Declarative reads (feat/scribe-migrate-6) — symmetric to system_slots.
  // ``reads`` maps a read-name to its params, e.g.
  // {"oracle_verdicts": {"n": 3}, "engrams": {"n": 5}}. The SYSTEM fetches the
  // data (reader registry, called directly — not via LLM tool-calls) and
  // injects it into dna_input.reads AND the agent's prompt. The scribe becomes
  // a pure composer (zero read tools).
  reads: z.record(z.string(), z.record(z.string(), z.any())).default({}),
  // s-delegation-declarative (2026-07-07) — declarative opt-in to the
  // delegation surface (TS parity with Python ``DelegationTargetFor``).
  // Replaces the hardcoded DELEGATION_CATALOG that used to live in
  // dna_shared.manifest_tools.delegation_tools: a UA that wants to
  // receive delegated work (e.g. from JARVIS via ``delegate_to``)
  // declares this block — user-installed UAs opt in by declaration.
  //
  // Shape rationale: an object (not a bare list of delegator names)
  // because the old catalog carried per-target metadata — ``format``
  // is load-bearing (drives how delegate_to parses the subagent's
  // output); ``typical_seconds`` + ``use_when`` drive the delegator's
  // narration and target choice.
  //   agents: delegator allowlist; ["*"] = any agent may delegate here.
  //   format: return contract — "slug" (creates a doc, returns its
  //     slug) | "json" (structured JSON in final message) | "text"
  //     (free-form narrative, default).
  //   typical_seconds: rough wait so the delegator can warn the user.
  //   use_when: heuristic for when to pick THIS target.
  //   purpose: what the target is good at; consumers fall back to
  //     metadata.description when absent.
  // Runtime consumption is Python-only (make_delegation_tools); the
  // TS SDK ships the schema for parity + Studio.
  delegation_target_for: z
    .object({
      agents: z.array(z.string()).default([]),
      format: z.enum(["slug", "json", "text"]).default("text"),
      typical_seconds: z.number().int().positive().optional(),
      use_when: z.string().optional(),
      purpose: z.string().optional(),
    })
    .optional(),
});

export const AgentSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("Agent"),
  metadata: MetadataSchema,
  spec: AgentSpecSchema.default({}),
});

export type TypedAgent = z.output<typeof AgentSchema>;

// ---------------------------------------------------------------------------
// Actor (github.com/ruinosus/dna/v1)
// ---------------------------------------------------------------------------

export const ActorSpecSchema = z.object({
  instruction: z.string().optional().default(""),
  traits: z.array(z.string()).default([]),
  role: z.string().optional().default(""),
  actorType: z.enum(["human", "system", "time"]).default("human"),
});

export const ActorSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("Actor"),
  metadata: MetadataSchema,
  spec: ActorSpecSchema.default({}),
});

export type TypedActor = z.output<typeof ActorSchema>;

// ---------------------------------------------------------------------------
// UseCase (github.com/ruinosus/dna/v1)
// ---------------------------------------------------------------------------

export const UseCaseSpecSchema = z.object({
  primary_actor: z.string().optional(),
  supporting_actors: z.array(z.string()).default([]),
  agents: z.array(z.string()).default([]),
  tools: z.array(z.string()).default([]),
  skills: z.array(z.string()).default([]),
  soul: z.string().optional(),
  guardrails: z.array(z.string()).default([]),
  preconditions: z.array(z.string()).default([]),
  main_flow: z.array(z.string()).default([]),
  alternate_flows: z.array(z.record(z.unknown())).default([]),
  postconditions: z.array(z.string()).default([]),
  success_criteria: z.array(z.string()).default([]),
});

export const UseCaseSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("UseCase"),
  metadata: MetadataSchema,
  spec: UseCaseSpecSchema.default({}),
});

export type TypedUseCase = z.output<typeof UseCaseSchema>;

// ---------------------------------------------------------------------------
// Tool (github.com/ruinosus/dna/v1)
//
// Declarative, invocable capability an agent can call. Bridges helix with
// OpenAI/Anthropic tool-calling conventions.
// ---------------------------------------------------------------------------

export const ToolTypeEnum = z.enum(["http", "mcp", "python", "shell", "builtin"]);
export const ToolAuthTypeEnum = z.enum(["none", "api_key", "bearer", "oauth2"]);

export const ToolSpecSchema = z.object({
  type: ToolTypeEnum.default("builtin"),
  endpoint: z.string().optional().default(""),
  method: z.string().optional().default("POST"),
  mcp_server: z.string().optional().default(""),
  mcp_tool: z.string().optional().default(""),
  python_module: z.string().optional().default(""),
  python_callable: z.string().optional().default(""),
  shell_command: z.string().optional().default(""),
  input_schema: z.record(z.unknown()).default({}),
  output_schema: z.record(z.unknown()).default({}),
  auth_type: ToolAuthTypeEnum.default("none"),
  auth_env_var: z.string().optional().default(""),
  read_only: z.boolean().default(true),
  requires_confirmation: z.boolean().default(false),
  tags: z.array(z.string()).default([]),
  examples: z.array(z.record(z.unknown())).default([]),
});

export const ToolSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("Tool"),
  metadata: MetadataSchema,
  spec: ToolSpecSchema.default({}),
});

export type TypedTool = z.output<typeof ToolSchema>;

// ---------------------------------------------------------------------------
// Skill (agentskills.io/v1)
// ---------------------------------------------------------------------------

export const SkillSpecSchema = z.object({
  instruction: z.string().optional().default(""),
  scripts: z.record(z.string()).default({}),
  references: z.record(z.string()).default({}),
  assets: z.record(z.string()).default({}),
  extras: z.record(z.record(z.string())).default({}),
  root_files: z.record(z.string()).default({}),
});

export const SkillSchema = z.object({
  apiVersion: z.literal("agentskills.io/v1"),
  kind: z.literal("Skill"),
  metadata: MetadataSchema,
  spec: SkillSpecSchema.default({}),
});

export type TypedSkill = z.output<typeof SkillSchema>;

// ---------------------------------------------------------------------------
// Soul (soulspec.org/v1)
// ---------------------------------------------------------------------------

export const SoulSpecSchema = z.object({
  soul_content: z.string().optional().default(""),
  soul_json: z.record(z.unknown()).optional(),
  style_content: z.string().optional().default(""),
  agents_content: z.string().optional().default(""),
});

export const SoulSchema = z.object({
  apiVersion: z.literal("soulspec.org/v1"),
  kind: z.literal("Soul"),
  metadata: MetadataSchema,
  spec: SoulSpecSchema.default({}),
});

export type TypedSoul = z.output<typeof SoulSchema>;

// ---------------------------------------------------------------------------
// HtmlArtifact (github.com/ruinosus/dna/sdlc/v1)
// ---------------------------------------------------------------------------

export const HtmlArtifactSpecSchema = z.object({
  html: z.string().optional().default(""),
  artifact_json: z.record(z.unknown()).optional(),
});

export const HtmlArtifactSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/sdlc/v1"),
  kind: z.literal("HtmlArtifact"),
  metadata: MetadataSchema,
  spec: HtmlArtifactSpecSchema.default({}),
});

export type TypedHtmlArtifact = z.output<typeof HtmlArtifactSchema>;

// ---------------------------------------------------------------------------
// AgentDefinition (agents.md/v1)
// ---------------------------------------------------------------------------

export const AgentDefinitionSpecSchema = z.object({
  content: z.string().optional().default(""),
});

export const AgentDefinitionSchema = z.object({
  apiVersion: z.literal("agents.md/v1"),
  kind: z.literal("AgentDefinition"),
  metadata: MetadataSchema,
  spec: AgentDefinitionSpecSchema.default({}),
});

export type TypedAgentDefinition = z.output<typeof AgentDefinitionSchema>;

// ---------------------------------------------------------------------------
// Guardrail (github.com/ruinosus/dna/v1)
// ---------------------------------------------------------------------------

export const GuardrailSpecSchema = z.object({
  rules: z.array(z.string()).default([]),
  severity: z.string().optional().default("warn"),
  scope: z.string().optional().default("both"),
});

export const GuardrailSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("Guardrail"),
  metadata: MetadataSchema,
  spec: GuardrailSpecSchema.default({}),
});

export type TypedGuardrail = z.output<typeof GuardrailSchema>;

// ---------------------------------------------------------------------------
// KindDefinition (github.com/ruinosus/dna/core/v1) — meta-kind
// ---------------------------------------------------------------------------

export const KIND_DEFINITION_API_VERSION = "github.com/ruinosus/dna/core/v1";
export const KIND_DEFINITION_KIND = "KindDefinition";

export const KindDefinitionSpecSchema = z.object({
  target_api_version: z.string().min(1),
  target_kind: z.string().min(1),
  alias: z.string().min(1),
  origin: z.string().min(1),
  is_root: z.boolean().default(false),
  prompt_target: z.boolean().default(false),
  flatten_in_context: z.boolean().default(false),
  schema: z.record(z.unknown()).default({}),
  docs: z.string().optional(),
  storage: z.record(z.unknown()),
  dep_filters: z.record(z.string()).nullable().optional(),
  default_agent: z.string().nullable().optional(),
  // UI hints — read by DeclarativeKindPort from the parsed spec. Python's
  // KindDefinitionSpec carried these since the UI-hints feature; the TS zod
  // object silently STRIPPED them (latent divergence — per-scope KIND.yaml
  // styles fell back to the derived origin-hash color in TS). Exposed by
  // the F3 descriptor pilot (kaizen.kind.yaml graph_style), fixed here.
  graph_style: z.record(z.string()).nullable().optional(),
  ascii_icon: z.string().nullable().optional(),
  display_label: z.string().nullable().optional(),
  // ---- F3 descriptor fields (spec 2026-06-10-kinds-descriptor-f3, D2) ----
  // These close the gap between hand-written Kind classes and the
  // declarative descriptor so builtin record Kinds can be expressed as
  // `.kind.yaml` package data. Defaults preserve today's behavior.
  // 1:1 parity with Python KindDefinitionSpec (models.py).
  //
  // `plane`: "composition" | "record" — mirrors KindBase.plane.
  plane: z.enum(["composition", "record"]).default("composition"),
  // `tenant_scope`: "tenanted" | "global" — mirrors TenantScope. Optional
  // (no Zod default) so the normalizing transform below can record whether
  // it was EXPLICITLY declared — undeclared kinds stay permissive
  // (Phase 1 back-compat; see `tenant_scope_declared`).
  tenant_scope: z.enum(["tenanted", "global"]).optional(),
  // `summary`: declarative list-endpoint projection — {field: default}.
  // List form ["a", "b"] is normalized by the transform below to a dict
  // with per-schema-type defaults (array→[], boolean→false,
  // number/integer→null, else ""). null/absent = no projection.
  summary: z
    .union([z.record(z.unknown()), z.array(z.string())])
    .nullable()
    .optional(),
  // `embed`: source fields for embedding text (feeds D4 derivation).
  embed: z.array(z.string()).nullable().optional(),
  // `is_runtime_artifact`: docs generated by runtime workflows.
  is_runtime_artifact: z.boolean().default(false),
  // `prompt_target_priority`: was hardcoded 5 in DeclarativeKindPort —
  // default 5 preserves that.
  prompt_target_priority: z.number().int().default(5),
  // Kernel classification flags — mirror KindBase defaults.
  scope_inheritable: z.boolean().default(true),
  is_overlayable: z.boolean().default(true),
  // Extra volatile spec fields, unioned with KindBase volatileSpecFields.
  volatile_spec_fields: z.array(z.string()).nullable().optional(),
  // ---- Descriptor expressiveness fields (spec 2026-06-11, D1/D3-D7) -------
  // All optional; absent → null/undefined preserves today's behavior. 1:1
  // parity with Python KindDefinitionSpec (models.py). Consumed by
  // DeclarativeKindPort (meta.ts).
  //
  // D1 `ui`: raw StudioUIMetadata mapping. Keys are validated ⊆
  // StudioUIMetadata fields (strict — unknown key → ZodError); the allowed
  // set is derived from UI_METADATA_FIELDS, the single source of truth (no
  // second hardcoded list). The port reconstructs the real StudioUIMetadata
  // so /kinds/manifest output is byte-identical to the deleted class.
  ui: z
    .record(z.unknown())
    .refine(
      (m) => Object.keys(m).every((k) => (UI_METADATA_FIELDS as readonly string[]).includes(k)),
      (m) => ({
        message:
          "spec.ui has unknown key(s): " +
          Object.keys(m)
            .filter((k) => !(UI_METADATA_FIELDS as readonly string[]).includes(k))
            .sort()
            .join(", ") +
          ` (allowed: ${[...UI_METADATA_FIELDS].sort().join(", ")})`,
      }),
    )
    .nullable()
    .optional(),
  // D3 `describe`: template string OR projection mapping ({path: field}).
  describe: z.union([z.string(), z.record(z.unknown())]).nullable().optional(),
  // D4 `ui_schema`: pass-through widget-hint bag, permissive (unknown keys ok).
  ui_schema: z.record(z.unknown()).nullable().optional(),
  // D5 `spec_defaults`: shallow-merge map applied before schema validation.
  spec_defaults: z.record(z.unknown()).nullable().optional(),
  // D6 `default_agent_field`: spec field returned VERBATIM by
  // getDefaultAgentName.
  default_agent_field: z.string().nullable().optional(),
  // D7 `description_fallback_field`: pass-through string attr for Studio.
  description_fallback_field: z.string().nullable().optional(),
});

/** Normalize spec.summary to its dict form (F3 spec D2).
 *
 * Dict form `{field: default}` passes through. List form `["a", "b"]`
 * gets a default per the field's declared type in `schema.properties`:
 * array→[], boolean→false, number/integer→null, anything else (incl.
 * fields absent from the schema)→"". Mirrors Python
 * KindDefinitionSpec._normalize_summary. */
function normalizeKindDefSummary(
  summary: Record<string, unknown> | string[] | null | undefined,
  schema: Record<string, unknown>,
): Record<string, unknown> | null {
  if (summary == null) return null;
  if (!Array.isArray(summary)) return summary;
  const props = (schema.properties as Record<string, unknown>) ?? {};
  const out: Record<string, unknown> = {};
  for (const fieldName of summary) {
    const prop = props[fieldName];
    const ptype =
      prop != null && typeof prop === "object"
        ? ((prop as Record<string, unknown>).type as string | undefined)
        : undefined;
    if (ptype === "array") out[fieldName] = [];
    else if (ptype === "boolean") out[fieldName] = false;
    else if (ptype === "number" || ptype === "integer") out[fieldName] = null;
    else out[fieldName] = "";
  }
  return out;
}

// F3 (spec D2): normalized spec — adds `tenant_scope_declared` (true iff
// tenant_scope was explicitly present; NOT a user-facing field), defaults
// tenant_scope to "tenanted", and normalizes the list form of `summary`.
// The plain object schema stays exported above because zodSpecToJsonSchema
// needs `.shape` (ZodObject, not ZodEffects).
const KindDefinitionSpecNormalizedSchema = KindDefinitionSpecSchema.transform(
  (s) => ({
    ...s,
    tenant_scope: s.tenant_scope ?? ("tenanted" as const),
    tenant_scope_declared: s.tenant_scope !== undefined,
    summary: normalizeKindDefSummary(s.summary, s.schema),
  }),
);

export const KindDefinitionSchema = z.object({
  apiVersion: z.literal(KIND_DEFINITION_API_VERSION),
  kind: z.literal(KIND_DEFINITION_KIND),
  metadata: MetadataSchema,
  spec: KindDefinitionSpecNormalizedSchema,
});

export type TypedKindDefinition = z.output<typeof KindDefinitionSchema>;

// ---------------------------------------------------------------------------
// Hook (github.com/ruinosus/dna/v1)
// ---------------------------------------------------------------------------

export const HookActionEnum = z.enum(["inject_fields", "log", "script"]);

export const HookSpecSchema = z.object({
  target: z.string().min(1).default("pre_build_prompt"), // "pre_build_prompt", "post_build_prompt", etc.
  type: z.enum(["middleware", "event"]).default("middleware"),
  action: HookActionEnum.default("inject_fields"),
  fields: z.record(z.unknown()).default({}),   // For inject_fields action
  body: z.string().optional().default(""),       // Raw body (script code or YAML fields)
});

export const HookSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("Hook"),
  metadata: MetadataSchema,
  spec: HookSpecSchema.default({}),
});

export type TypedHook = z.output<typeof HookSchema>;

// ---------------------------------------------------------------------------
// Community channel — artifact allowlist
//
// Spec: docs/superpowers/specs/2026-05-18-source-as-distribution.md.
// The CommunityItem Kind was pruned (s-prune-speculative-extensions,
// recovery: git history); the FS install channel lives on and this
// allowlist mirrors Python COMMUNITY_ARTIFACT_KINDS. Adding a Kind
// here requires the same entry in python/dna/kernel/models.py.
// ---------------------------------------------------------------------------

export const CommunityArtifactKindEnum = z.enum([
  "Skill",
  "Soul",
  "Agent",
  "Hook",
  "SafetyPolicy",
  "Recognizer",
  "Guardrail",
]);

// ---------------------------------------------------------------------------
// TextBlock + HtmlBlock (github.com/ruinosus/dna/v1) — generative blocks
//
// Spec: s-generative-blocks (2026-05-19). Mirrors Python's
// TextBlockSpec / HtmlBlockSpec in dna.kernel.models.
// ---------------------------------------------------------------------------

export const TextBlockSpecSchema = z.object({
  title: z.string().default(""),
  body: z.string().default(""),
  area: z.string().default(""),
  owner: z.string().nullable().default(null),
  generated_by: z.string().default(""),
  affect: z.string().default(""),
  tags: z.array(z.string()).default([]),
  created_at: z.string().default(""),
});

export const TextBlockSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("TextBlock"),
  metadata: MetadataSchema,
  spec: TextBlockSpecSchema.default({}),
});

export type TypedTextBlock = z.output<typeof TextBlockSchema>;

export const HtmlBlockSpecSchema = z.object({
  title: z.string().default(""),
  body: z.string().default(""),
  area: z.string().default(""),
  owner: z.string().nullable().default(null),
  generated_by: z.string().default(""),
  affect: z.string().default(""),
  tags: z.array(z.string()).default([]),
  created_at: z.string().default(""),
  sandbox_features: z.string().default(""),
  estimated_height_px: z.number().int().nonnegative().default(0),
});

export const HtmlBlockSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("HtmlBlock"),
  metadata: MetadataSchema,
  spec: HtmlBlockSpecSchema.default({}),
});

export type TypedHtmlBlock = z.output<typeof HtmlBlockSchema>;

// ---------------------------------------------------------------------------
// HtmlTemplate (github.com/ruinosus/dna/v1) — Mustache-templated reusable widget.
// Story: s-html-templates (2026-05-19).
// ---------------------------------------------------------------------------

export const HtmlTemplateSpecSchema = z.object({
  title: z.string().default(""),
  description: z.string().default(""),
  body: z.string().default(""),
  version: z.string().default("0.1.0"),
  params: z.record(z.unknown()).default({}),
  example: z.record(z.unknown()).default({}),
  theme: z.string().default(""),
  area: z.string().default(""),
  owner: z.string().nullable().default(null),
  generated_by: z.string().default(""),
  tags: z.array(z.string()).default([]),
  created_at: z.string().default(""),
});

export const HtmlTemplateSchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("HtmlTemplate"),
  metadata: MetadataSchema,
  spec: HtmlTemplateSpecSchema.default({}),
});

export type TypedHtmlTemplate = z.output<typeof HtmlTemplateSchema>;

// ---------------------------------------------------------------------------
// SafetyPolicy (github.com/ruinosus/dna/v1)
// ---------------------------------------------------------------------------

export const SafetyRuleSchema = z.object({
  type: z.enum(["pii", "content_safety", "topic_restriction", "prompt_injection", "banned_words", "custom_regex"]),
  tier: z.enum(["regex", "ml", "api", "llm_judge"]).optional(),
  entities: z.array(z.string()).optional(),
  region: z.string().optional(),
  categories: z.array(z.string()).optional(),
  threshold: z.number().optional(),
  allowed: z.array(z.string()).optional(),
  denied: z.array(z.string()).optional(),
  patterns: z.array(z.string()).optional(),
  words: z.array(z.string()).optional(),
});

export const SafetyPolicySpecSchema = z.object({
  scope: z.enum(["input", "output", "both"]).default("both"),
  action: z.enum(["mask", "block", "log"]).default("mask"),
  severity: z.enum(["error", "warn"]).default("error"),
  rules: z.array(SafetyRuleSchema).default([]),
  recognizers: z.array(z.string()).default([]),
  // Phase 7 — ml-privacy-filter engine. All optional (backward-compatible).
  engine: z.enum(["presidio", "ml-privacy-filter"]).default("presidio"),
  model: z.string().default("openai/privacy-filter"),
  backend: z.enum(["auto", "transformers", "onnxruntime"]).default("auto"),
  threshold: z.number().min(0).max(1).default(0.8),
  // T1 LOCKED valid values: account_number, private_address, private_email,
  // private_person, private_phone, private_url, private_date, secret
  categories: z.array(z.string()).nullable().default(null),
  mask_char: z.string().default("[REDACTED]"),
  budget_ms: z.number().default(1000),
});

export const SafetyPolicySchema = z.object({
  apiVersion: z.literal("github.com/ruinosus/dna/v1"),
  kind: z.literal("SafetyPolicy"),
  metadata: MetadataSchema,
  spec: SafetyPolicySpecSchema.default({}),
});

export type TypedSafetyPolicy = z.output<typeof SafetyPolicySchema>;

// ---------------------------------------------------------------------------
// Recognizer (presidio/v1)
// ---------------------------------------------------------------------------

export const RecognizerPatternSchema = z.object({
  name: z.string(),
  regex: z.string(),
  score: z.number().min(0).max(1),
});

export const RecognizerSpecSchema = z.object({
  entity_type: z.string().min(1),
  language: z.string().default("en"),
  patterns: z.array(RecognizerPatternSchema).default([]),
  deny_list: z.array(z.string()).default([]),
  context: z.array(z.string()).default([]),
});

export const RecognizerSchema = z.object({
  apiVersion: z.literal("presidio/v1"),
  kind: z.literal("Recognizer"),
  metadata: MetadataSchema,
  spec: RecognizerSpecSchema,
});

export type TypedRecognizer = z.output<typeof RecognizerSchema>;

// ---------------------------------------------------------------------------
// Zod → JSON Schema helper
// ---------------------------------------------------------------------------

/** Convert a Zod object schema's .shape to a minimal JSON Schema.
 *  No external library — walks Zod internals directly. */
export function zodSpecToJsonSchema(zodSchema: z.ZodObject<any>): Record<string, unknown> {
  const shape = zodSchema.shape;
  const properties: Record<string, unknown> = {};

  function typeOf(z: any): Record<string, unknown> {
    const def = z?._def;
    const tn = def?.typeName;
    if (tn === "ZodString") return { type: "string" };
    if (tn === "ZodNumber" || tn === "ZodInt") return { type: "number" };
    if (tn === "ZodBoolean") return { type: "boolean" };
    if (tn === "ZodEnum") return { type: "string", enum: def.values };
    if (tn === "ZodArray") {
      const items = def.type ? typeOf(def.type) : { type: "string" };
      return { type: "array", items };
    }
    if (tn === "ZodRecord") return { type: "object" };
    if (tn === "ZodOptional") return typeOf(def.innerType);
    if (tn === "ZodDefault") return typeOf(def.innerType);
    if (tn === "ZodObject") return { type: "object" };
    if (tn === "ZodUnknown" || tn === "ZodAny") return {};
    return {};
  }

  for (const [key, zodType] of Object.entries(shape)) {
    properties[key] = typeOf(zodType);
  }

  return { type: "object", properties };
}
// ── DNA namespace ───────────────────────────────────────────────────────────
// Single authoritative namespace constant (spec §8: swapping the namespace
// is one commit + a golden regen). NOTE: literal-type positions (z.literal /
// *.kind.yaml descriptors) must stay in sync with this value — the
// descriptor + parity suites enforce it.
export const DNA_NAMESPACE = "github.com/ruinosus/dna";
