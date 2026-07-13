/**
 * HelixExtension — Module, Agent, Actor kinds.
 *
 * 1:1 parity with Python dna.v3.extensions.helix.
 */

import yaml from "js-yaml";
import { join as pathJoin } from "node:path";
import { nodeFS, readTextSafe, collectDir } from "../kernel/fs.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { KindBase } from "../kernel/kind_base.js";
import type { FSLike } from "../kernel/fs.js";
import { AgentSchema, ActorSchema, UseCaseSchema, AgentSpecSchema, ActorSpecSchema, UseCaseSpecSchema, GenomeSchema, GenomeSpecSchema, LayerPolicySchema, LayerPolicySpecSchema, zodSpecToJsonSchema } from "../kernel/models.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";
import type { Extension, ExtensionHost, KindPort, LayerPolicy, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { SD } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";
import type { PreviewBlock } from "../kernel/preview.js";
import type { CompositionProfile } from "../kernel/composition-resolver.js";
import { readSpecString, readSpecStringArray, readSpecRecordArray } from "../kernel/spec-access.js";
import { SettingKind, ThemeKind, UserProfileKind, CanvasKind } from "./helix_extras.js";
import { registerWriteGuards } from "./helix/write-guards.js";

const MOD_URL = import.meta.url;

// ── Named composition layouts (s-dx-named-layouts) ─────────────────────
//
// An author orders persona-vs-instruction by NAME (`layout:` in the Agent
// spec) instead of hand-writing raw Mustache with internal section names.
// Each preset resolves to one of these embedded templates via
// `AgentKind.layoutTemplate()`. 1:1 with Python `dna.extensions.helix`.
//
// The guardrails block is shared verbatim — guardrails are hard policy and
// always land LAST, after both the instruction and the soul, regardless of
// their relative order. (Aligns TS composition to Python, closing the
// pre-existing i-213/i-011 divergence where TS omitted the guardrails block.)
const GUARDRAILS_BLOCK =
  "{{#guardrails-guardrail}}" +
  "## Guardrail: {{name}} ({{severity}})\n" +
  "{{#description}}_{{description}}_\n\n{{/description}}" +
  "{{#rules}}- {{{.}}}\n{{/rules}}\n" +
  "{{/guardrails-guardrail}}";

// Skills block (i-031) — a referenced Skill COMPOSES into the system prompt,
// exactly like Guardrails: a Mustache section over the dep-filtered
// `agentskills-skill` list, inlining each skill's SKILL.md body. Before this
// fix a wired Skill was inert (in context, rendered by no layout). Skills
// land AFTER the soul and BEFORE guardrails; a skill-less agent renders the
// empty section to nothing, composing byte-identically to before. 1:1 with
// Python `_SKILLS_BLOCK`.
const SKILLS_BLOCK =
  "{{#agentskills-skill}}" +
  "## Skill: {{name}}\n" +
  "{{#description}}_{{description}}_\n\n{{/description}}" +
  "{{{instruction}}}\n\n" +
  "{{/agentskills-skill}}";

// instruction-first (a.k.a. "default") — historic order: instruction, soul,
// skills, guardrails. IS the kind default template.
const LAYOUT_INSTRUCTION_FIRST =
  "{{{agent.instruction}}}\n\n{{{soul_content}}}\n\n" + SKILLS_BLOCK + GUARDRAILS_BLOCK;

// persona-first — Soul leads, then instruction, then skills, then guardrails.
const LAYOUT_PERSONA_FIRST =
  "{{{soul_content}}}\n\n{{{agent.instruction}}}\n\n" + SKILLS_BLOCK + GUARDRAILS_BLOCK;

const AGENT_LAYOUTS: Record<string, string> = {
  default: LAYOUT_INSTRUCTION_FIRST,
  "instruction-first": LAYOUT_INSTRUCTION_FIRST,
  "persona-first": LAYOUT_PERSONA_FIRST,
};

const AGENT_LAYOUT_NAMES: string[] = ["default", "instruction-first", "persona-first"];

// GenomeKind — Phase 16 (scope segregation)
//
// Replaces ModuleKind as the scope-root identity Kind. Carries catalog
// identity, versioning, runtime defaults, and external dependencies.
// Tenant overlay is field-level via OVERLAYABLE_FIELDS allowlist.
//
// 1:1 parity with Python dna.extensions.helix.GenomeKind.
// Phase 16 commit 3 — root flag transferred from Module to Genome
// once examples migrated to ``Genome.yaml``. Module's ``isRoot`` flips
// to false in lockstep so the "exactly one root Kind" invariant is
// preserved. Commit 4 removes ``isRoot`` from KindPort entirely.
// ---------------------------------------------------------------------------

class GenomeKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "Genome";
  readonly alias = "helix-genome";
  readonly isSchemaAffecting = true;
  readonly isOverlayable = false;
  readonly scopeInheritable = false;
  // Genome IS the catalog identity (Phase 3b ch1, i-112;
  // s-write-path-despecialize). Py twin: GenomeKind.is_catalog_identity.
  readonly isCatalogIdentity = true;
  readonly origin = "github.com/ruinosus/dna";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.root("Genome.yaml");
  readonly graphStyle = { fill: "#3B82F6", stroke: "#1D4ED8", textColor: "#fff" };
  readonly asciiIcon = "📦";
  readonly displayLabel = "Genome";
  readonly _sourceUrl = MOD_URL;

  // Tenant-overlayable fields. Identity and versioning are NOT here on
  // purpose: tenant overlays must not change owner, version, etc.
  // Kernel enforces this allowlist (commit 2).
  static readonly OVERLAYABLE_FIELDS = new Set<string>([
    "default_agent",
    "default_llm",
    "budget",
    "tags",
  ]);

  readonly docs =
    "A Genome is the scope-root identity document (Phase 16). It declares " +
    "catalog identity (owner, owner_tenant, repository, visibility), " +
    "versioning (version, changelog_url, deprecated), runtime defaults " +
    "(default_agent, default_llm, budget, tags), and external dependencies. " +
    "Replaces the legacy Module Kind. Layer policy moved to LayerPolicy " +
    "docs at <scope>/policies/. Custom Kinds moved to KindDefinition docs " +
    "at <scope>/kinds/.";

  readonly uiSchema = {
    owner_tenant: { widget: "readonly", label: "Owner tenant", help: "null = platform-owned (catalog item).", order: 5 },
    visibility: { widget: "select", label: "Visibility", options: ["public", "internal", "private"], help: "Who can discover and install this Genome.", order: 6 },
    version: { widget: "text", label: "Version", help: "Semver. Opt-in. null = unversioned.", order: 7 },
    changelog_url: { widget: "text", label: "Changelog URL", order: 8 },
    deprecated: { widget: "checkbox", label: "Deprecated", order: 9 },
    deprecated_message: { widget: "textarea", label: "Deprecated message", order: 10 },
    default_agent: { widget: "text", label: "Default agent", help: "Tenant-overlayable.", order: 20 },
    default_llm: { widget: "text", label: "Default LLM", help: "Tenant-overlayable.", order: 21 },
    budget: { widget: "readonly", label: "Budget", help: "Tenant-overlayable.", order: 22 },
    tags: { widget: "tags", label: "Tags", help: "Tenant-overlayable.", order: 23 },
    owner: { widget: "text", label: "Owner", order: 30 },
    repository: { widget: "text", label: "Repository", order: 31 },
    dependencies: { widget: "readonly", label: "External dependencies", order: 90 },
  };

  // Genome has no inventory deps; ``dependencies`` is a list of external
  // module refs resolved via ResolverPort. Composition validation walks
  // scanner-discovered docs directly.
  dependencies() { return null; }
  schema() { return zodSpecToJsonSchema(GenomeSpecSchema); }

  getDefaultAgentName(doc: Document): string | null {
    return readSpecString(doc, "default_agent") ?? null;
  }

  parse(raw: Record<string, unknown>): unknown {
    return GenomeSchema.parse(raw);
  }

  describe(doc: Document): string | null {
    const lines = [`Name:       ${doc.name}`, `Kind:       Genome`];
    const ownerTenant = readSpecString(doc, "owner_tenant") ?? "platform";
    lines.push(`Owner:      ${ownerTenant}`);
    const version = readSpecString(doc, "version");
    if (version) lines.push(`Version:    ${version}`);
    const visibility = readSpecString(doc, "visibility");
    if (visibility) lines.push(`Visibility: ${visibility}`);
    const defaultAgent = readSpecString(doc, "default_agent");
    if (defaultAgent) lines.push(`Default:    ${defaultAgent}`);
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    if (spec.deprecated) {
      const msg = readSpecString(doc, "deprecated_message") ?? "";
      lines.push(`Deprecated: ${msg}`);
    }
    return lines.join("\n");
  }

  summary(doc: Document): Record<string, unknown> {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      owner_tenant: spec.owner_tenant ?? null,
      visibility: spec.visibility ?? null,
      version: spec.version ?? null,
      default_agent: spec.default_agent ?? null,
      deprecated: Boolean(spec.deprecated),
    };
  }


  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const fields: Array<{ label: string; value: string }> = [];
    for (const label of ["owner_tenant", "visibility", "version", "default_agent", "default_llm"]) {
      const value = spec[label];
      if (value !== null && value !== undefined && value !== "") {
        fields.push({ label, value: String(value) });
      }
    }
    if (spec.deprecated) {
      fields.push({ label: "deprecated", value: String(spec.deprecated_message ?? "true") });
    }
    const deps = spec.dependencies;
    if (Array.isArray(deps) && deps.length > 0) {
      fields.push({ label: "dependencies", value: `${deps.length} entries` });
    }
    if (fields.length === 0) {
      return [{ kind: "empty", title: `Genome ${doc.name}` }];
    }
    return [{ kind: "fields", title: `Genome ${doc.name}`, fields }];
  }
}

// ---------------------------------------------------------------------------
// LayerPolicyKind — Phase 16
//
// Overlay policy per (layer, kind) tuple. One LayerPolicy doc per layer
// dimension (e.g. tenant, branch). Lives at ``<scope>/policies/<id>.yaml``.
// Replaces the legacy ``Module.spec.layers`` field.
//
// 1:1 parity with Python dna.extensions.helix.LayerPolicyKind.
// ---------------------------------------------------------------------------

class LayerPolicyKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/policy/v1";
  readonly kind = "LayerPolicy";
  readonly alias = "policy-layer-policy"; // s-kind-alias-convention-fix: <owner>-<kebab(kind)>; was "policy-layer"
  readonly isSchemaAffecting = true;
  readonly isOverlayable = false;
  readonly scopeInheritable = false;
  readonly origin = "github.com/ruinosus/dna/policy";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("policies");
  readonly graphStyle = { fill: "#A855F7", stroke: "#7E22CE", textColor: "#fff" };
  readonly asciiIcon = "🔒";
  readonly displayLabel = "Layer Policies";
  readonly _sourceUrl = MOD_URL;

  readonly docs =
    "A LayerPolicy declares overlay rules for one layer dimension " +
    "(tenant, branch, region, etc.). Kernel reads these docs to enforce " +
    "write policy when a layer overlay is applied. Replaces the legacy " +
    "Module.spec.layers field. Some Kinds are structurally non-overlayable " +
    "(Genome, KindDefinition, LayerPolicy itself) — their policy is " +
    "always locked regardless of doc contents.";

  readonly uiSchema = {
    layer_id: { widget: "select", label: "Layer dimension", options: ["tenant", "branch", "region", "user"], help: "Which layer dimension this policy applies to.", order: 10 },
    policies: { widget: "readonly", label: "Per-Kind policies", help: "Map of kind alias → policy (open/restricted/locked).", order: 20 },
  };

  dependencies() { return null; }
  schema() { return zodSpecToJsonSchema(LayerPolicySpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    const parsed = LayerPolicySchema.parse(raw) as { spec: { layer_id: string; policies: Record<string, string> } };
    // Mirror Python's LayerPolicySpec.from_raw normalization:
    // lowercase + drop falsy values + drop non-string keys.
    const normalized: Record<string, string> = {};
    for (const [k, v] of Object.entries(parsed.spec.policies ?? {})) {
      if (typeof k === "string" && k && v) {
        normalized[k] = String(v).toLowerCase();
      }
    }
    parsed.spec.policies = normalized;
    return parsed;
  }

  describe(doc: Document): string | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const layerId = (spec.layer_id as string | undefined) ?? doc.name;
    const policies = (spec.policies ?? {}) as Record<string, unknown>;
    const n = Object.keys(policies).length;
    return `Name:    ${doc.name}\nKind:    LayerPolicy\nLayer:   ${layerId}\nRules:   ${n}`;
  }

  summary(doc: Document): Record<string, unknown> {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const policies = (spec.policies ?? {}) as Record<string, unknown>;
    return {
      layer_id: spec.layer_id ?? null,
      rule_count: Object.keys(policies).length,
    };
  }


  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const fields: Array<{ label: string; value: string }> = [];
    if (spec.layer_id) {
      fields.push({ label: "layer_id", value: String(spec.layer_id) });
    }
    const policies = spec.policies as Record<string, unknown> | undefined;
    if (policies && typeof policies === "object") {
      for (const alias of Object.keys(policies).sort()) {
        fields.push({ label: alias, value: String(policies[alias]) });
      }
    }
    if (fields.length === 0) {
      return [{ kind: "empty", title: `LayerPolicy ${doc.name}` }];
    }
    return [{ kind: "fields", title: `LayerPolicy ${doc.name}`, fields }];
  }
}

// ---------------------------------------------------------------------------
// AgentKind
// ---------------------------------------------------------------------------

class AgentKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "Agent";
  readonly alias = "helix-agent";
  readonly isSchemaAffecting = true;
  readonly origin = "github.com/ruinosus/dna";
  readonly isPromptTarget = true;
  readonly promptTargetPriority = 10;
  readonly flattenInContext = false;
  readonly storage = SD.bundle("agents", "AGENT.md");
  readonly graphStyle = { fill: "#F97316", stroke: "#EA580C", textColor: "#fff" };
  readonly asciiIcon = "🤖";
  readonly displayLabel = "Agents";
  readonly _sourceUrl = MOD_URL;
  readonly docs =
    "A Agent is the primary prompt target in a helix manifest — " +
    "what actually runs when a user (or another agent) talks to the system. " +
    "It carries an instruction, a model, and dep_filters declaring which " +
    "Soul, Skills, Guardrails, and Actors it composes with. Bundle-based " +
    "storage: agents/<name>/AGENT.md.";
  readonly uiSchema = {
    instruction: {
      widget: "markdown-toc",
      label: "Instruction (AGENT.md)",
      help: "The agent's main prompt body. Supports Mustache tags like {{soul_content}}.",
      height: 520,
      order: 10,
    },
    objective: { widget: "textarea", label: "Objective", order: 15 },
    model: { widget: "text", label: "Model", order: 20 },
    layout: {
      widget: "select",
      label: "Layout",
      options: ["default", "instruction-first", "persona-first"],
      help: "Named composition order — 'persona-first' puts the Soul before the instruction. Leave empty for the default. A raw promptTemplate, if set, overrides this.",
      order: 25,
    },
    soul: { widget: "text", label: "Soul", help: "Name of the Soul doc to flatten into the prompt.", order: 30 },
    skills: { widget: "tags", label: "Skills", order: 40 },
    actors: { widget: "tags", label: "Actors this agent serves", order: 50 },
    guardrails: { widget: "tags", label: "Guardrails", order: 60 },
    tools: { widget: "tags", label: "Tools", order: 70 },
    team_members: { widget: "tags", label: "Team members", order: 80 },
    // s-mcp-servers-on-agent (Py parity) — MCPFederation refs.
    mcp_servers: {
      widget: "tags",
      label: "MCP servers",
      help: "MCPFederation doc names this agent consumes (e.g. 'drawio'). Remote tools load as first-class agent tools tagged mcp:<ref>. Entries may also be objects {ref, allowed_tools, timeout_s} for per-agent overrides.",
      order: 87,
    },
    tags: { widget: "tags", label: "Tags", order: 90 },
  };

  depFilters() {
    return {
      soul: "soulspec-soul",
      skills: "agentskills-skill",
      guardrails: "guardrails-guardrail",
      actors: "helix-actor",
      tools: "helix-tool",
    };
  }
  schema() { return zodSpecToJsonSchema(AgentSpecSchema); }


  parse(raw: Record<string, unknown>): unknown {
    return AgentSchema.parse(raw);
  }

  describe(doc: Document): string | null {
    const spec = doc.spec;
    const meta = doc.metadata;
    const name = (meta.name as string) ?? "";
    const desc = (meta.description as string) ?? "";
    const soul = (spec.soul as string) ?? "";
    const skills = (spec.skills as string[]) ?? [];
    const model = (spec.model as string) ?? "";

    const lines = [`Name:    ${name}`, `Kind:    Agent`];
    if (desc) lines.push(`Desc:    ${desc}`);
    if (soul) lines.push(`Soul:    ${soul}`);
    if (skills.length > 0) lines.push(`Skills:  ${skills.join(", ")} (${skills.length})`);
    if (model) lines.push(`Model:   ${model}`);
    return lines.join("\n");
  }

  summary(doc: Document): Record<string, unknown> | null {
    const skills = readSpecStringArray(doc, "skills");
    return { skills: skills.length, soul: readSpecString(doc, "soul") ?? null };
  }

  promptTemplate() {
    // IS the `instruction-first` / `default` named layout — the kind default
    // template and the `default` layout are one string, so an agent with no
    // `layout:` composes identically. Includes the skills block (i-031) and
    // the guardrails block — Soul, Skills, and Guardrails all compose into the
    // prompt. See the layout-constants comment above.
    return LAYOUT_INSTRUCTION_FIRST;
  }

  layoutTemplate(name: string): string | null {
    return AGENT_LAYOUTS[name] ?? null;
  }

  layoutNames(): string[] {
    return [...AGENT_LAYOUT_NAMES];
  }

  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const blocks: PreviewBlock[] = [];
    const instruction = typeof spec.instruction === "string" ? spec.instruction : "";
    if (instruction) {
      // Show the raw template with mustache placeholders intact — Self
      // means "the doc you're editing", not the compiled prompt.
      blocks.push({ kind: "markdown", title: "AGENT.md (template)", body: instruction });
    }
    const meta: Array<{ label: string; value: string }> = [];
    if (typeof spec.model === "string") meta.push({ label: "model", value: spec.model });
    if (typeof spec.soul === "string") meta.push({ label: "soul", value: spec.soul });
    for (const f of ["skills", "guardrails", "tools"]) {
      const arr = spec[f];
      if (Array.isArray(arr) && arr.length > 0) {
        meta.push({ label: f, value: (arr as unknown[]).map(String).join(", ") });
      }
    }
    if (meta.length > 0) {
      blocks.push({ kind: "fields", title: "Metadata", fields: meta });
    }
    if (blocks.length === 0) {
      return [{ kind: "empty", title: `Agent ${doc.name}` }];
    }
    return blocks;
  }
}

// ---------------------------------------------------------------------------
// ActorKind
// ---------------------------------------------------------------------------

class ActorKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "Actor";
  readonly alias = "helix-actor";
  readonly origin = "github.com/ruinosus/dna/actor";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("actors");
  readonly graphStyle = { fill: "#EC4899", stroke: "#DB2777", textColor: "#fff" };
  readonly asciiIcon = "👤";
  readonly displayLabel = "Actors";
  readonly _sourceUrl = MOD_URL;
  readonly docs =
    "An Actor is a UML-canonical participant in the system — a human user, " +
    "an external system, or a time/schedule trigger. The actorType field " +
    "disambiguates human/system/time. Actors are referenced by UseCases and " +
    "Agents via dep_filters.actors but are not prompt targets.";
  readonly uiSchema = {
    role: { widget: "text", label: "Role", help: "Short job title or functional role.", order: 10 },
    actor_type: {
      widget: "select",
      label: "Actor type",
      help: "human = person/role; system = external service or upstream; time = scheduled trigger.",
      order: 20,
    },
    goals: { widget: "list-markdown", label: "Goals", help: "What this actor is trying to achieve.", order: 30 },
    pain_points: { widget: "list-markdown", label: "Pain points", order: 40 },
    preferences: { widget: "readonly", label: "Preferences", help: "Nested object; edit in YAML for now.", order: 90 },
  };

  schema() { return zodSpecToJsonSchema(ActorSpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    return ActorSchema.parse(raw);
  }

  summary() { return null; }

  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const fields: Array<{ label: string; value: string }> = [];
    if (typeof spec.role === "string") fields.push({ label: "role", value: spec.role });
    if (typeof spec.actor_type === "string") fields.push({ label: "actor_type", value: spec.actor_type });
    if (Array.isArray(spec.goals) && spec.goals.length > 0) {
      fields.push({
        label: "goals",
        value: (spec.goals as unknown[]).map((g) => `• ${String(g)}`).join("\n"),
      });
    }
    if (Array.isArray(spec.pain_points) && spec.pain_points.length > 0) {
      fields.push({
        label: "pain_points",
        value: (spec.pain_points as unknown[]).map((g) => `• ${String(g)}`).join("\n"),
      });
    }
    if (fields.length === 0) {
      return [{ kind: "empty", title: `Actor ${doc.name}` }];
    }
    return [{ kind: "fields", title: `Actor ${doc.name}`, fields }];
  }
}

// ---------------------------------------------------------------------------
// UseCaseKind
// ---------------------------------------------------------------------------

class UseCaseKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "UseCase";
  readonly alias = "helix-usecase";
  readonly origin = "github.com/ruinosus/dna/usecase";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("use_cases");
  readonly graphStyle = { fill: "#F59E0B", stroke: "#D97706", textColor: "#fff" };
  readonly asciiIcon = "📋";
  readonly displayLabel = "UseCases";
  readonly _sourceUrl = MOD_URL;
  readonly docs =
    "A UseCase is a UML-canonical use case: a goal-oriented interaction " +
    "between Actors and the system. It composes primary_actor, supporting " +
    "actors, agents, preconditions, main_flow, alternate_flows, " +
    "postconditions, and success_criteria. Purely declarative — not a " +
    "prompt target — consumed by tooling for traceability.";
  readonly uiSchema = {
    primary_actor: { widget: "text", label: "Primary actor", help: "Name of the Actor doc that initiates this use case.", order: 10 },
    supporting_actors: { widget: "tags", label: "Supporting actors", order: 20 },
    agents: { widget: "tags", label: "Agents", help: "Agents that fulfill this use case.", order: 30 },
    soul: { widget: "text", label: "Soul", help: "Name of the Soul that shapes the tone of this flow. Optional — overrides the agent's soul for this use case scope.", order: 40 },
    skills: { widget: "tags", label: "Skills", help: "Skills required by the agents to fulfill this use case.", order: 50 },
    tools: { widget: "tags", label: "Tools", help: "Tools the agents invoke during this use case.", order: 60 },
    guardrails: { widget: "tags", label: "Guardrails", help: "Guardrails that apply specifically to this use case.", order: 70 },
    preconditions: { widget: "list-markdown", label: "Preconditions", order: 80 },
    main_flow: { widget: "list-markdown", label: "Main flow", help: "Ordered steps describing the happy path.", order: 90 },
    alternate_flows: { widget: "readonly", label: "Alternate flows", help: "Named deviations. Nested object; edit in YAML.", order: 100 },
    postconditions: { widget: "list-markdown", label: "Postconditions", order: 110 },
    success_criteria: { widget: "list-markdown", label: "Success criteria", order: 120 },
  };

  depFilters() {
    return {
      primary_actor:     "helix-actor",
      supporting_actors: "helix-actor",
      agents:            "helix-agent",
      soul:              "soulspec-soul",
      skills:            "agentskills-skill",
      tools:             "helix-tool",
      guardrails:        "guardrails-guardrail",
    };
  }
  schema() { return zodSpecToJsonSchema(UseCaseSpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    return UseCaseSchema.parse(raw);
  }

  summary() { return null; }

  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const fields: Array<{ label: string; value: string }> = [];
    if (typeof spec.primary_actor === "string")
      fields.push({ label: "primary_actor", value: spec.primary_actor });
    for (const f of ["supporting_actors", "agents", "skills", "tools", "guardrails"]) {
      const arr = spec[f];
      if (Array.isArray(arr) && arr.length > 0) {
        fields.push({ label: f, value: (arr as unknown[]).map(String).join(", ") });
      }
    }
    if (Array.isArray(spec.preconditions) && spec.preconditions.length > 0) {
      fields.push({
        label: "preconditions",
        value: (spec.preconditions as unknown[]).map((s) => `• ${String(s)}`).join("\n"),
      });
    }
    if (Array.isArray(spec.main_flow) && spec.main_flow.length > 0) {
      fields.push({
        label: "main_flow",
        value: (spec.main_flow as unknown[]).map((s, i) => `${i + 1}. ${String(s)}`).join("\n"),
      });
    }
    if (Array.isArray(spec.success_criteria) && spec.success_criteria.length > 0) {
      fields.push({
        label: "success_criteria",
        value: (spec.success_criteria as unknown[]).map((s) => `• ${String(s)}`).join("\n"),
      });
    }
    if (fields.length === 0) {
      return [{ kind: "empty", title: `UseCase ${doc.name}` }];
    }
    return [{ kind: "fields", title: `UseCase ${doc.name}`, fields }];
  }
}

// ---------------------------------------------------------------------------
// AgentReader / AgentWriter
// ---------------------------------------------------------------------------

const KNOWN_DIRS = new Set(["scripts", "references", "assets"]);

// AGENT.md frontmatter passthrough allowlist.
//
// Derived from ``AgentSpecSchema`` so adding a field to the
// Zod schema automatically opens it in the reader and writer — no
// separate allowlist to keep in sync. Two recurring bugs (the
// ``shell_sandbox`` 2026-05-08 drift, and ``codegraph`` /
// ``tool_groups`` / ``tests`` shortly after) were caused by exactly
// that drift.
//
// ``instruction`` is excluded: the reader fills it from the AGENT.md
// body (or via ``instruction_file`` resolution), never from a top-
// level frontmatter key. Allowing it here would let an authoring
// mistake (frontmatter ``instruction:``) silently shadow the body.
const SPEC_FIELDS: ReadonlySet<string> = new Set(
  Object.keys(AgentSpecSchema.shape).filter((k) => k !== "instruction"),
);

// ---------------------------------------------------------------------------
// instruction_file resolver
// ---------------------------------------------------------------------------

function _resolveInstructionFile(
  fs: FSLike,
  bundlePath: string,
  rel: string,
): string {
  if (typeof rel !== "string" || rel.length === 0) {
    throw new Error("instruction_file must be a non-empty string");
  }
  if (rel.startsWith("/") || /^[A-Za-z]:/.test(rel)) {
    throw new Error(
      `instruction_file must be a relative path, got ${JSON.stringify(rel)}`,
    );
  }
  // Count '..' segments in the raw path to catch escape attempts
  const upCount = rel.split("/").filter((p) => p === "..").length;
  if (upCount > 3) {
    throw new Error(
      `instruction_file exceeds depth cap (up_count=${upCount}, max=3): ${JSON.stringify(rel)}`,
    );
  }
  // Resolve relative to the bundle directory (path.join handles '..' normalization)
  const resolved = pathJoin(bundlePath, rel);
  return fs.readFile(resolved);
}

export class AgentReader implements ReaderPort {
  constructor(private fs: FSLike = nodeFS) {}

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    return this.fs.exists(`${path}/AGENT.md`);
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const agentMd = this.fs.readFile(`${path}/AGENT.md`);
    const fm = this._parseFrontmatter(agentMd);
    const name = (fm.name as string) || path.split("/").pop() || "";
    const description = (fm.description as string) ?? "";
    const labels = fm.labels ?? null;

    // Extract body (after frontmatter)
    const body = agentMd.replace(/^---\n[\s\S]*?---\n?/, "").trim();

    const instructionFile = fm.instruction_file as string | undefined;
    let spec: Record<string, unknown>;
    if (instructionFile !== undefined) {
      if (fm.instruction) {
        throw new Error(
          `${path}: cannot set both frontmatter 'instruction' and 'instruction_file'`,
        );
      }
      if (body.trim() !== "") {
        throw new Error(
          `${path}: cannot set both AGENT.md body and instruction_file`,
        );
      }
      const content = _resolveInstructionFile(this.fs, path, instructionFile);
      spec = { instruction: content, instruction_file: instructionFile };
    } else {
      spec = { instruction: body };
    }
    for (const field of SPEC_FIELDS) {
      if (field in fm && field !== "instruction_file") {
        spec[field] = fm[field];
      }
    }

    // Collect known subdirectories
    for (const dirName of KNOWN_DIRS) {
      const sub = `${path}/${dirName}`;
      if (this.fs.isDirectory(sub)) {
        const files = collectDir(this.fs, sub, sub);
        if (Object.keys(files).length > 0) {
          spec[dirName] = files;
        }
      }
    }

    // Collect extra subdirectories
    const extras: Record<string, Record<string, string>> = {};
    const entries = this.fs.readDir(path);
    for (const entry of entries) {
      const full = `${path}/${entry}`;
      if (!this.fs.isDirectory(full) || KNOWN_DIRS.has(entry)) continue;
      const files = collectDir(this.fs, full, full);
      if (Object.keys(files).length > 0) {
        extras[entry] = files;
      }
    }
    if (Object.keys(extras).length > 0) {
      spec.extras = extras;
    }

    // Collect root-level extra files
    const rootFiles: Record<string, string> = {};
    for (const entry of entries) {
      const full = `${path}/${entry}`;
      if (!this.fs.isFile(full) || entry === "AGENT.md") continue;
      const text = readTextSafe(this.fs, full);
      if (text !== null) {
        rootFiles[entry] = text;
      }
    }
    if (Object.keys(rootFiles).length > 0) {
      spec.root_files = rootFiles;
    }

    const metadata: Record<string, unknown> = { name, description };
    if (labels) {
      metadata.labels = labels;
    }

    return {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata,
      spec,
    };
  }

  private _parseFrontmatter(text: string): Record<string, unknown> {
    const match = text.match(/^---\n([\s\S]*?)---\n?/);
    if (!match) return {};
    return (yaml.load(match[1]) as Record<string, unknown>) ?? {};
  }
}

export class AgentWriter implements WriterPort {
  constructor(private fs: FSLike = nodeFS) {}

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === "Agent";
  }

  write(bundle: BundleHandle, raw: Record<string, unknown>): void { const path = bundle.path ?? "";
    this.fs.mkdir(path);
    const spec = (raw.spec as Record<string, unknown>) ?? {};
    const meta = (raw.metadata as Record<string, unknown>) ?? {};

    const fm: Record<string, unknown> = {};
    fm.name = (meta.name as string) || path.split("/").pop() || "";
    if (meta.description) fm.description = meta.description;
    if (meta.labels) fm.labels = meta.labels;
    for (const field of SPEC_FIELDS) {
      if (field in spec && spec[field]) {
        fm[field] = spec[field];
      }
    }

    const frontmatter = yaml.dump(fm, {
      flowLevel: -1,
      forceQuotes: false,
      sortKeys: false,
    });
    const body = spec.instruction_file ? "" : ((spec.instruction as string) ?? "");
    this.fs.writeFile(`${path}/AGENT.md`, `---\n${frontmatter}---\n\n${body}`);

    // s-sync-s3 — emit the instruction_file FRAGMENT so the bundle is self-
    // contained (twin of Py AgentWriter). Source: carried source_files entry,
    // else the resolved inline instruction. Without this, writing to a fresh
    // bundle left no instruction.md → the agent's instruction resolved empty.
    const instructionFile = spec.instruction_file as string | undefined;
    const sourceFiles = (spec.source_files as Record<string, unknown>) ?? {};
    if (instructionFile) {
      const frag = sourceFiles[instructionFile] ?? (spec.instruction as string | undefined);
      if (frag != null) this.fs.writeFile(`${path}/${instructionFile}`, String(frag));
    }
    // Any remaining carried text source_files (binaries aren't handled by the
    // string-only FS shim here — covered by the Postgres net for the runtime).
    for (const [rel, content] of Object.entries(sourceFiles)) {
      if (rel === "AGENT.md" || rel === instructionFile) continue;
      if (typeof content === "string") this.fs.writeFile(`${path}/${rel}`, content);
    }

    // Write known subdirectories
    for (const dirName of ["scripts", "references", "assets"]) {
      const files = spec[dirName];
      if (files != null && typeof files === "object") {
        for (const [fname, fcontent] of Object.entries(files as Record<string, string>)) {
          this.fs.writeFile(`${path}/${dirName}/${fname}`, fcontent);
        }
      }
    }

    // Write extras
    const extras = spec.extras;
    if (extras != null && typeof extras === "object") {
      for (const [dirName, dirFiles] of Object.entries(extras as Record<string, Record<string, string>>)) {
        if (typeof dirFiles === "object") {
          for (const [fname, fcontent] of Object.entries(dirFiles)) {
            this.fs.writeFile(`${path}/${dirName}/${fname}`, fcontent);
          }
        }
      }
    }

    // Write root files
    const rootFiles = spec.root_files;
    if (rootFiles != null && typeof rootFiles === "object") {
      for (const [fname, fcontent] of Object.entries(rootFiles as Record<string, string>)) {
        this.fs.writeFile(`${path}/${fname}`, fcontent);
      }
    }
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const files: SerializedFile[] = [];
    const spec = (raw.spec as Record<string, unknown>) ?? {};
    const meta = (raw.metadata as Record<string, unknown>) ?? {};

    // 1. AGENT.md
    const fm: Record<string, unknown> = {};
    fm.name = (meta.name as string) || "";
    if (meta.description) fm.description = meta.description;
    if (meta.labels) fm.labels = meta.labels;
    for (const field of SPEC_FIELDS) {
      if (field in spec && spec[field]) fm[field] = spec[field];
    }
    const frontmatter = yaml.dump(fm, { flowLevel: -1, sortKeys: false });
    const serializeBody = spec.instruction_file ? "" : ((spec.instruction as string) ?? "");
    files.push({ relativePath: "AGENT.md", content: `---\n${frontmatter}---\n\n${serializeBody}` });

    // s-sync-s3 — emit the instruction_file fragment + carried text
    // source_files so the serialized bundle is self-contained (twin of write()).
    const serInstrFile = spec.instruction_file as string | undefined;
    const serSourceFiles = (spec.source_files as Record<string, unknown>) ?? {};
    if (serInstrFile) {
      const frag = serSourceFiles[serInstrFile] ?? (spec.instruction as string | undefined);
      if (frag != null) files.push({ relativePath: serInstrFile, content: String(frag) });
    }
    for (const [rel, content] of Object.entries(serSourceFiles)) {
      if (rel === "AGENT.md" || rel === serInstrFile) continue;
      if (typeof content === "string") files.push({ relativePath: rel, content });
    }

    // 2. Known sub-directories
    for (const dirName of ["scripts", "references", "assets"]) {
      const dirFiles = spec[dirName];
      if (dirFiles != null && typeof dirFiles === "object") {
        for (const [fname, fcontent] of Object.entries(dirFiles as Record<string, string>)) {
          files.push({ relativePath: `${dirName}/${fname}`, content: fcontent });
        }
      }
    }

    // 3. Extras
    const extras = spec.extras;
    if (extras != null && typeof extras === "object") {
      for (const [dirName, dirFiles] of Object.entries(extras as Record<string, Record<string, string>>)) {
        if (typeof dirFiles === "object") {
          for (const [fname, fcontent] of Object.entries(dirFiles)) {
            files.push({ relativePath: `${dirName}/${fname}`, content: fcontent });
          }
        }
      }
    }

    // 4. Root files
    const rootFiles = spec.root_files;
    if (rootFiles != null && typeof rootFiles === "object") {
      for (const [fname, fcontent] of Object.entries(rootFiles as Record<string, string>)) {
        files.push({ relativePath: fname, content: fcontent });
      }
    }

    return files;
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Composition profile — declares how Agent composes with other kinds
// ---------------------------------------------------------------------------

const HELIX_PROFILE: CompositionProfile = {
  orchestratorAlias: "helix-agent",
  label: "Helix Agent",
  slots: [
    {
      name: "soul",
      targetAlias: "soulspec-soul",
      cardinality: "one",
      order: 1,
      filterable: false,
      timeline: { label: "Soul", itemLabel: "personality loaded" },
      healthCheck: {
        rule: "at-least-one",
        severity: "warn",
        issueKey: "agents_without_soul",
        message: "Agent has no soul",
      },
      quadrant: null,
    },
    {
      name: "skills",
      targetAlias: "agentskills-skill",
      cardinality: "many",
      order: 2,
      filterable: true,
      timeline: { label: "Skills", itemLabel: "instruction loaded" },
      healthCheck: null,
      quadrant: { axis: "x", label: "Few Skills --> Many Skills", maxScale: 15 },
    },
    {
      name: "guardrails",
      targetAlias: "guardrails-guardrail",
      cardinality: "many",
      order: 3,
      filterable: true,
      timeline: { label: "Guardrails", itemLabel: "rules applied" },
      healthCheck: {
        rule: "at-least-one",
        severity: "warn",
        issueKey: "agents_without_guardrails",
        message: "Agent has no guardrails",
      },
      quadrant: { axis: "y", label: "Few Guardrails --> Many Guardrails", maxScale: 10 },
    },
    {
      name: "tools",
      targetAlias: "helix-tool",
      cardinality: "many",
      order: 4,
      filterable: false,
      timeline: null,
      healthCheck: null,
      quadrant: null,
    },
    {
      name: "actors",
      targetAlias: "helix-actor",
      cardinality: "many",
      order: 5,
      filterable: false,
      timeline: null,
      healthCheck: null,
      quadrant: null,
    },
  ],
};

// ---------------------------------------------------------------------------
// HelixExtension
// ---------------------------------------------------------------------------

export class HelixExtension implements Extension {
  readonly name = "helix";
  readonly version = "1.0.0";

  constructor(private fs: FSLike = nodeFS) {}

  register(kernel: ExtensionHost): void {
    // Phase 16 cleanup — ModuleKind class deleted. GenomeKind is the
    // canonical root identity Kind.
    kernel.kind(new GenomeKind());
    kernel.kind(new LayerPolicyKind());
    kernel.kind(new AgentKind());
    kernel.kind(new ActorKind());
    kernel.kind(new UseCaseKind());
    // Tool (helix-tool) ships as a descriptor — helix/kinds/tool.kind.yaml
    // (f-dna-tools-as-data / s-tool-kind-descriptor). It WAS a hand-written
    // ToolKind class; migrated to a record-plane descriptor per the repo's
    // own ratchet (record Kinds are data, not classes).
    for (const raw of loadDescriptors(import.meta.url, "helix/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
    // 2026-05-26 — absorbed from claude-code-templates catalog (MIT).
    // Setting rounds out the Claude-Code-customization primitives that
    // live alongside Skill / UA / Soul / Tool.
    kernel.kind(new SettingKind());
    kernel.kind(new ThemeKind());
    kernel.kind(new UserProfileKind());
    // s-jarvis-canvas (2026-05-27) — shared whiteboard JARVIS ↔ user.
    kernel.kind(new CanvasKind());
    kernel.reader(new AgentReader(this.fs));
    kernel.writer(new AgentWriter(this.fs));
    kernel.compositionProfile(HELIX_PROFILE);
    // s-write-path-despecialize — Agent write rules (platform-agent
    // fork guard, Kind-Writer contract) are pre_save VETO hooks owned by
    // this extension, not kernel special-cases.
    registerWriteGuards(kernel);
  }
}

