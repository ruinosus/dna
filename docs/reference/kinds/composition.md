# Composition-plane Kinds

**Composition-plane** Kinds are behaviour that composes into an agent's prompt (skills, souls, guardrails, …) — resolved through the layer/tenant overlay engine.

!!! info "Generated from the registered Kinds"

    Introspected from `Kernel.auto()` by `scripts/gen_kinds_docs.py`.
    Each Kind's spec fields come from its own `schema()`.

## Actor

- **Alias:** `helix-actor`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition

An Actor is a UML-canonical participant in the system: a human user, an external system, or a time/schedule trigger. Actors describe who (or what) initiates or collaborates with agents. The actor_type field disambiguates: 'human' for people/roles, 'system' for external services or upstream systems, 'time' for scheduled triggers. Stored as a flat yaml file under actors/<name>.yaml.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor_type` | string |  |  |
| `instruction` | string |  |  |
| `role` | string |  |  |
| `traits` | array |  |  |

## Agent

- **Alias:** `helix-agent`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition
- **Flags:** prompt-target

A Agent is the primary prompt target: it's what actually runs when the user talks to the system. It declares an instruction (usually in a bundle AGENT.md or an agents/<name>.md file), a model to call, and dep_filters listing which Soul, Skills, and Guardrails to compose into its system prompt. The Soul, Skills, and Guardrails are all composed into the prompt every turn (a DeepAgents harness may additionally expose Skills via progressive disclosure). Priority 10 means Agent wins over other prompt targets when the harness has to pick one.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_kind` | string |  |  |
| `creative_slots` | array |  |  |
| `delegation_target_for` | any |  |  |
| `guardrails` | array |  |  |
| `input_schema` | object |  |  |
| `instruction` | string |  |  |
| `instruction_file` | string |  |  |
| `invoked_by_engine` | string |  |  |
| `layout` | string |  |  |
| `locale_strings` | object |  |  |
| `mandatory_tool_calls` | array |  |  |
| `max_turns` | integer |  |  |
| `mcp_servers` | array |  |  |
| `model` | string |  |  |
| `objective` | string |  |  |
| `promptTemplate` | string |  |  |
| `prompt_format` | string |  |  |
| `reads` | object |  |  |
| `reflect_before_write` | boolean |  |  |
| `rubric` | string |  |  |
| `rubric_max_iterations` | integer |  |  |
| `shell_sandbox` | boolean |  |  |
| `skills` | array |  |  |
| `soul` | string |  |  |
| `system_slots` | object |  |  |
| `tags` | array |  |  |
| `target_scopes` | array |  |  |
| `team_members` | array |  |  |
| `tool_groups` | array |  |  |
| `tools` | array |  |  |
| `type` | string |  |  |
| `voice_persona` | any |  |  |
| `writes_kind` | string |  |  |
| `writes_kinds` | object |  |  |

## AgentDefinition

- **Alias:** `agentsmd-agent`
- **apiVersion:** `agents.md/v1`
- **Plane:** composition
- **Flags:** prompt-target

An AgentDefinition is a standalone AGENTS.md file following the agents.md/v1 standard — prose that describes an agent's identity, conventions, tools, and behavior. Unlike a Soul (which is personality only) or a Skill (which is an on-demand capability), an AgentDefinition is the full archetype: when present it is flattened into every prompt (flatten_in_context=True) and is never filtered by dep_filters. Use it when you want an agent fully described in a single portable markdown file, independent of the helix module.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `content` | string |  |  |

## Canvas

- **Alias:** `helix-canvas`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition

A Canvas is a shared whiteboard between JARVIS and the user — tldraw-backed. User draws with mouse/touch/3D hand; JARVIS reads shapes (JSON) + optionally vision-interprets free strokes, and writes back via discrete shape tools. Persisted as first-class Kind so it's searchable, retrievable, embeddable. Quebra a quarta parede da interação voice-only.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string |  |  |
| `created_by` | string |  | user_id who first opened this canvas. |
| `drawio_xml` | string |  | drawio mxGraph XML payload. engine=drawio. |
| `engine` | string |  | Whiteboard renderer (per-canvas, not convertible). 3 engines kept after exploration: - tldraw — rich UI, multi-page (commercial license for prod) - excalidraw — MIT, hand-drawn casual sketch - drawio — Apache 2.0, formal BPMN / architecture diagrams |
| `excalidraw_store` | object |  | Excalidraw scene (elements+appState). engine=excalidraw. |
| `last_drawn_by` | string |  | Who touched the canvas most recently. |
| `summary` | string |  | One-line description — what's on this canvas. |
| `tags` | array |  |  |
| `thumbnail_url` | string |  | Optional snapshot PNG URL (Asset Kind ref). Generated by client on save for list previews. |
| `title` | string | yes | Human-readable canvas name shown in listings. |
| `tldraw_store` | object |  | tldraw scene (shapes+bindings). engine=tldraw. |
| `updated_at` | string |  |  |

## Comment

- **Alias:** `collab-comment`
- **apiVersion:** `github.com/ruinosus/dna/collab/v1`
- **Plane:** composition

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `assignee` | string |  |  |
| `attachments` | array |  |  |
| `author` | string | yes |  |
| `body` | string | yes |  |
| `created_at` | string | yes |  |
| `edited_at` | string |  |  |
| `from_status` | string |  |  |
| `target_ref` | string | yes | Kind:name of the target document |
| `to_status` | string |  |  |
| `type` | string | yes |  |

## EvidencePolicy

- **Alias:** `evidence-policy`
- **apiVersion:** `github.com/ruinosus/dna/evidence/v1`
- **Plane:** composition

An EvidencePolicy controls which event types are automatically captured as Evidence documents. Declares the list of event types to watch, whether auto-capture is enabled, and retention period.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `auto_capture` | boolean |  |  |
| `events` | array | yes |  |
| `retention_days` | integer |  |  |

## Genome

- **Alias:** `helix-genome`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition
- **Flags:** root

A Genome is the scope-root identity document (Phase 16). It declares catalog identity (owner, owner_tenant, repository, visibility), versioning (version, changelog_url, deprecated), runtime defaults (default_agent, default_llm, budget, tags), and external dependencies. Replaces the legacy Module Kind. Layer policy moved out to LayerPolicy docs at <scope>/policies/. Custom Kinds moved out to KindDefinition docs at <scope>/kinds/.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `budget` | object |  |  |
| `capabilities` | array |  |  |
| `changelog_url` | string |  |  |
| `default_agent` | string |  |  |
| `default_llm` | string |  |  |
| `dependencies` | array |  |  |
| `deprecated` | boolean |  |  |
| `deprecated_message` | string |  |  |
| `global_scope` | boolean |  |  |
| `mandatory` | boolean |  |  |
| `owner` | string |  |  |
| `owner_tenant` | string |  |  |
| `parent_scope` | string |  |  |
| `repository` | string |  |  |
| `tags` | array |  |  |
| `version` | string |  |  |
| `visibility` | string |  |  |

## Guardrail

- **Alias:** `guardrails-guardrail`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition

A Guardrail is a safety or compliance rule set that shapes what an agent may produce. It has a severity (warn | error | hard) indicating how strictly the rule must be enforced, and a scope (input | output | both) indicating which side of the model call it applies to. Rules are declared as a markdown list of directives in GUARDRAIL.md. Guardrails are referenced by an agent's dep_filters and flattened into the system prompt so the model sees them on every turn. Use a Guardrail for hard constraints like 'never leak PII' or 'refuse destructive commands without confirmation'.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `rules` | array |  |  |
| `scope` | string |  |  |
| `severity` | string |  |  |

## Hook

- **Alias:** `helix-hook`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition

A Hook is a declarative lifecycle interceptor. It attaches to a kernel hook point (e.g. pre_build_prompt) and runs an action: inject_fields merges YAML key-value pairs into the prompt context, log emits a structured info message, and script executes inline Python code. Hooks are stored in HOOK.md bundles and are auto-registered when ManifestInstance.apply_hooks() is called.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | string |  |  |
| `body` | string |  |  |
| `fields` | object |  |  |
| `target` | string |  |  |
| `type` | string |  |  |

## KindDefinition

- **Alias:** `kinddef-kinddefinition`
- **apiVersion:** `github.com/ruinosus/dna/core/v1`
- **Plane:** composition

A KindDefinition declaratively defines a brand-new kind without writing Python code. Its spec carries the target apiVersion, kind name, alias, JSON Schema for the document spec, storage layout, and prompt flags. The kernel's 2-phase loader parses KindDefinitions first, synthesizes a DeclarativeKindPort for each, then parses the rest of the manifest so regular documents can reference the newly registered kind.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `alias` | string |  |  |
| `ascii_icon` | string |  |  |
| `default_agent` | string |  |  |
| `default_agent_field` | string |  |  |
| `dep_filters` | object |  |  |
| `describe` | object |  |  |
| `description_fallback_field` | string |  |  |
| `display_label` | string |  |  |
| `docs` | string |  |  |
| `embed` | array |  |  |
| `flatten_in_context` | boolean |  |  |
| `graph_style` | object |  |  |
| `is_overlayable` | boolean |  |  |
| `is_root` | boolean |  |  |
| `is_runtime_artifact` | boolean |  |  |
| `origin` | string |  |  |
| `plane` | string |  |  |
| `prompt_target` | boolean |  |  |
| `prompt_target_priority` | integer |  |  |
| `schema` | object |  |  |
| `schema_fragments` | array |  |  |
| `scope_inheritable` | boolean |  |  |
| `spec_defaults` | object |  |  |
| `storage` | object |  |  |
| `summary` | object |  |  |
| `target_api_version` | string |  |  |
| `target_kind` | string |  |  |
| `tenant_scope` | string |  |  |
| `tenant_scope_declared` | boolean |  |  |
| `ui` | object |  |  |
| `ui_schema` | object |  |  |
| `volatile_spec_fields` | array |  |  |
| `workitem_common` | boolean |  |  |

## LayerPolicy

- **Alias:** `policy-layer-policy`
- **apiVersion:** `github.com/ruinosus/dna/policy/v1`
- **Plane:** composition

A LayerPolicy declares overlay rules for one layer dimension (tenant, branch, region, etc.). Kernel reads these docs to enforce write policy when a tenant or other layer overlay is applied. Replaces the legacy Module.spec.layers field. Some Kinds are structurally non-overlayable (Genome, KindDefinition, LayerPolicy itself) — their policy is always locked regardless of doc contents.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `composition_rules` | object |  |  |
| `layer_id` | string |  |  |
| `policies` | object |  |  |

## Lesson

- **Alias:** `lesson-lesson`
- **apiVersion:** `github.com/ruinosus/dna/lesson/v1`
- **Plane:** composition

A Lesson is a short, structured educational activity the agent can run with a pre-reader child. Declarative — content is in YAML, edited by caregivers in Studio, no code review. Tools: start_lesson(subject) picks one; record_attempt (concept, correct) tracks performance into LessonLearned docs.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `approved_by` | array |  |  |
| `difficulty` | integer |  |  |
| `duration_seconds_max` | integer |  | Cap to respect TDAH attention budget. 60-180 typical for ages 8-12. |
| `labels` | array |  |  |
| `modality` | array |  |  |
| `on_no_response` | string |  | Phrase Lumi says after ~30s of no input. Always gentle, never pressuring. |
| `prompts` | array | yes | DEPRECATED v2: legacy flat list of Lumi-spoken prompts. Use `steps` instead. Kept for back-compat with v1 seeds — if `steps` is missing, runtime synthesizes a 1-step-per-prompt timeline. |
| `reinforcement` | string |  | How Lumi reacts to correct answers. 'celebrate' = set_pose celebrating + warm phrase. |
| `skill` | string |  |  |
| `steps` | array |  | Ordered list of LessonStep objects. Agent walks them in order, listening to Mateus between each, calling show_pictogram for visual anchor and record_attempt on test steps. |
| `subject` | string | yes | Short concept group ('cores-basicas', 'animais-conhecidos', 'rotina-comer'). |
| `success_criteria` | object |  | How to mark this lesson 'done well'. Example: {matches: 3, duration_min: 30}. |
| `target_concepts` | array | yes | Concept slugs that match Pictogram.spec.concept (azul, vermelho, etc). |
| `title` | string |  | Display title in PT-BR ('Cores básicas', 'Animais que você conhece'). |

## MCPFederation

- **Alias:** `federation-mcp`
- **apiVersion:** `github.com/ruinosus/dna/federation/v1`
- **Plane:** composition

An MCPFederation declares an external MCP server whose tools DNA agents consume: a Agent lists the doc's name in spec.mcp_servers and the harness loads the remote tools as first-class agent tools (zero code, zero deploy). Transports: stdio (command/args/env/cwd) or streamable_http (url). Auth carries env-var NAMES only — never secret values. allowed_tools bounds what any agent can get; enabled: false is the declarative kill-switch. Docs in _lib/federations/ are inherited by every scope. Also consumed by the DNA-as-MCP-server proxy (Phase 14r).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `allowed_tools` | array |  | Server-level allowlist of remote tool names (pre-prefix). Empty = all. |
| `args` | array |  |  |
| `auth` | object |  | Auth by env-var NAME — the value is read from the process env at connect time and never stored in docs, logs, or events. |
| `command` | string |  | Executable to run (resolved via PATH). Required when transport=stdio. |
| `cwd` | string \| null |  | Working directory; null = scope dir. |
| `enabled` | boolean |  | Disable without deleting the doc — declarative kill-switch, no deploy. |
| `env` | object |  | Extra env vars merged onto os.environ for the subprocess. |
| `health_check` | object |  |  |
| `propagate_tenant` | boolean |  | HTTP transport: stamp X-DNA-Tenant-Effective / X-DNA-Scope / X-DNA-Agent headers. |
| `tags` | array |  |  |
| `timeout_s` | integer |  | Per-call timeout default (seconds). Per-agent entry may override. |
| `tool_prefix` | string |  | Prepended to every proxied tool name (e.g. 'graphify_'). |
| `transport` | string |  | How to reach the server: stdio subprocess (default, v1) or Streamable HTTP. |
| `url` | string |  | Server endpoint. Required when transport=streamable_http. |

## Recognizer

- **Alias:** `presidio-recognizer`
- **apiVersion:** `presidio/v1`
- **Plane:** composition

A Recognizer is a Presidio ad-hoc recognizer that detects PII entities using regex patterns or deny lists. Recognizers are referenced by SafetyPolicy documents and exported to LiteLLM/Presidio at runtime.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `context` | array |  |  |
| `deny_list` | array |  |  |
| `entity_type` | string |  |  |
| `language` | string |  |  |
| `patterns` | array |  |  |

## Research

- **Alias:** `research-research`
- **apiVersion:** `github.com/ruinosus/dna/research/v1`
- **Plane:** composition

A Research is a curated synthesis of N external sources (Reference docs) with objective, methodology, evidence-rated findings, and priority recommendations. Designed for auditability + agent consumption. Use Reference for a single external source; use Research to consolidate multiple References into a position with recommendations.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `audience_context` | string |  | Recipe phase: context block fed to the LLM. |
| `brief_notes` | string |  | Recipe phase: author notes about the recipe. |
| `cited_by` | array |  | Kind/name of docs that cite this Research as a grounding source. Auto-maintained by `dna sdlc cite Research/<name> --from <Kind>/<name>` — don't author by hand. |
| `conducted_at` | string |  | When the research was synthesized. |
| `conducted_by` | string |  | Actor who ran the synthesis: claude-code, jefferson, auto-synth, ... |
| `created_at` | string |  |  |
| `executive_summary` | string |  | TL;DR — 200-500 words. What this research concludes + what to do. Goes prominently at top of viewer + listing card preview. |
| `findings` | array |  | Discrete claims extracted from sources. Each has an evidence rating that gates how the recommendation is presented. |
| `key_takeaways` | array |  | 3-7 bullets — 'if you read nothing else'. Most surfaceable in dashboards. |
| `last_reviewed_at` | string |  | Most recent human review of this research (for living reviews). |
| `methodology` | string | yes |  |
| `next_review_due` | string |  | When this research should be re-validated (literature evolves). |
| `objective` | string | yes | Why this research was conducted. 1-3 sentences. |
| `output_constraints` | array |  | Recipe phase: extra output constraints. |
| `overall_confidence` | string |  | GRADE-inspired confidence rating. Computable: high if >=80% findings evidence-based, moderate 60-80, low 40-60, very-low <40. Author can override. |
| `owner` | string |  | Who owns/maintains the doc. |
| `recommendations` | array |  | Actionable proposals derived from findings, ranked by priority. Items marked `clinical_decision: true` require human sign-off before implementation. |
| `reference_baselines` | array |  | Recipe phase: Research names to NOT duplicate. |
| `research_blocks` | array |  | Recipe phase: structured question blocks. Each block has title + list of questions. |
| `retracted_reason` | string |  | Why this Research was retracted (audit trail). |
| `scope_ref` | string |  | Scope this research informs (e.g. 'dna-development'). |
| `sources` | array |  | Reference doc names this research synthesizes from. Each entry should resolve to a Reference doc (sdlc-reference Kind). |
| `status` | string | yes | Lifecycle: brief\|ready (recipe phase) → draft\|published (output phase) → superseded\|retracted (terminal). |
| `superseded_by` | string |  | Name of newer Research that replaces this one. |
| `tags` | array |  |  |
| `title` | string | yes | Short human title in PT-BR or EN. |
| `updated_at` | string |  |  |
| `visibility` | string |  | scope-private = only this scope sees it. shared = discoverable across scopes. |

## SafetyPolicy

- **Alias:** `helix-safety-policy`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition

A SafetyPolicy declares runtime enforcement rules for input and/or output. Rules are organized by type (pii, content_safety, topic_restriction, prompt_injection, banned_words, custom_regex) and enforced via a tiered scanner pipeline. Tier 1 (regex) is built-in and handles CPF, CNPJ, email, phone, credit card masking plus prompt injection heuristics. Higher tiers (ML, API, LLM judge) are opt-in via pip extras. Actions: mask replaces detected text inline, block rejects the message entirely, log passes through with violation metadata attached.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | string |  |  |
| `backend` | string |  |  |
| `budget_ms` | any |  |  |
| `categories` | array |  |  |
| `engine` | string |  |  |
| `mask_char` | string |  |  |
| `model` | string |  |  |
| `recognizers` | array |  |  |
| `rules` | array |  |  |
| `scope` | string |  |  |
| `severity` | string |  |  |
| `threshold` | any |  |  |

## Setting

- **Alias:** `helix-setting`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition

A Setting is a reusable configuration snippet (env vars + nested config). Composed into .claude/settings.json or the runtime env. Use Setting for things like 'configure Vertex AI', 'corporate proxy', 'enable model X for region Y'. Atomic, idempotent, version-pinned.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  | Markdown body — the SETTING.md prose. |
| `config` | object |  | Nested config payload (merged into .claude/settings.json under the appropriate key). |
| `config_scope` | string |  | Domain category (drives sidebar grouping + .claude/settings.json key). |
| `created_at` | string |  |  |
| `env_vars` | object |  | Env vars set by this setting. Values may be literal or ${PLACEHOLDER} that the user fills. |
| `instructions` | array |  | Step-by-step setup checklist for the user. |
| `owner` | string |  |  |
| `purpose` | string | yes | What this setting does, in one line. |
| `tags` | array |  |  |
| `title` | string | yes |  |
| `updated_at` | string |  |  |
| `verifies_with` | string |  | Shell command that verifies the setting is active (e.g. 'gcloud auth list'). |

## Skill

- **Alias:** `agentskills-skill`
- **apiVersion:** `agentskills.io/v1`
- **Plane:** composition

A Skill is a reusable capability bundle an agent composes into its prompt. It follows the agents.md SKILL.md convention: one markdown file (frontmatter + body instruction) plus optional scripts/, references/, and assets/ subdirectories. A Skill referenced by an Agent (spec.skills) has its SKILL.md body inlined into the composed system prompt — the same way a Soul or Guardrail composes (i-031) — so it reaches build_prompt and every emitted runtime artifact. A DeepAgents harness may additionally expose Skills via progressive disclosure (SkillsMiddleware loads full content on demand). Use a Skill for reusable procedural know-how shared across agents.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `assets` | object |  |  |
| `extras` | object |  |  |
| `instruction` | string |  |  |
| `references` | object |  |  |
| `root_files` | object |  |  |
| `scripts` | object |  |  |

## Soul

- **Alias:** `soulspec-soul`
- **apiVersion:** `soulspec.org/v1`
- **Plane:** composition
- **Flags:** prompt-target

A Soul defines an agent's personality, voice, and guiding principles as prose (not code). It is stored as a bundle — SOUL.md plus optional IDENTITY.md, STYLE.md, HEARTBEAT.md, AGENTS.md and soul.json — following the soulspec.org open standard. When an agent references a Soul via its dep_filters, the Soul content is flattened directly into the agent's system prompt (flatten_in_context=True). Use a Soul when multiple agents should share the same character or ethos.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agents_content` | string |  |  |
| `soul_content` | string |  |  |
| `soul_json` | object |  |  |
| `style_content` | string |  |  |

## Tenant

- **Alias:** `tenant-tenant`
- **apiVersion:** `github.com/ruinosus/dna/tenant/v1`
- **Plane:** composition

A Tenant is the identity of an organization/team/individual that owns scopes and the documents within them. Stored as bundle (TENANT.md frontmatter = spec) under the special `_lib` scope. Slug rules match the runtime tenant claim format ([a-z0-9-]{1,253}). Created by platform admins via POST /tenants. Suspended via PATCH; soft-deleted via DELETE (status=deleted, 30d grace period before physical purge by background cron). Member management lives in Phase B (separate TenantMembership kind).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string |  | ISO timestamp when the Tenant was provisioned. |
| `deleted_at` | string |  | Set on soft-delete. Cron purges ~30d later. |
| `display_name` | string | yes | Human-readable name shown in Studio. |
| `member_count_cached` | integer |  | Denormalized count. Refreshed by membership mutations (Phase B). Eventually-consistent. |
| `metadata` | object |  | Free-form metadata (region, lgpd_consent, billing_account_id, etc). Forward-compatible. |
| `owner_email` | string | yes | Email of the human that provisioned this tenant. First member of the tenant by default. |
| `plan` | string |  | Billing/feature tier. |
| `slug` | string | yes | Tenant identity. Used as the value of dna_documents.tenant for every doc owned by this tenant. Must match the runtime tenant claim format. |
| `status` | string | yes | Lifecycle state. `deleted` is soft — docs stay in PG until the purge cron runs (~30d later). |
| `suspended_at` | string |  |  |

## TenantMembership

- **Alias:** `tenant-membership`
- **apiVersion:** `github.com/ruinosus/dna/tenant/v1`
- **Plane:** composition

Links a user to a Tenant with a role. One row per (tenant, user) pair. Created when an admin invites a member via POST /tenants/{slug}/members. Deleted by DELETE on same path. Tenant.spec.member_count_cached is updated by the route handler on each mutation (eventually-consistent).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `invited_by` | string |  | Email of the admin who invited this member. |
| `joined_at` | string | yes | ISO timestamp when the membership was created. |
| `role` | string | yes | Per-tenant role. `owner` is the user who provisioned the tenant (set by POST /tenants). `admin` can manage members + tenant settings. `member` can read/write scope docs. `viewer` is read-only. |
| `status` | string |  | `pending` for invites awaiting first login; `active` after first login (route handler transitions); `revoked` after admin removes. |
| `tenant_slug` | string | yes | Slug of the Tenant this user belongs to. |
| `user_email` | string | yes | Email identity of the user. |
| `user_id` | string |  | Stable user identifier from the IdP (Clerk sub, OIDC sub, etc). May be absent for invites pending first login — in that case user_email is the key. |
| `view_preset` | string |  | Optional override of Studio's auto-detected view. When set, the UI renders the curated menu/mode-tab subset matching this preset instead of deriving from the user's roles. Lets a power-user temporarily 'see as' a consumer/educator. Auto-detect from roles is the default when this is null. Values follow the same vocabulary as Role (consumer, maker, qa, po, pm, architect, tech-lead, compliance, power-user, tenant-admin, tenant-owner, platform-admin) — pick the single most-relevant intent. |

## TestGuide

- **Alias:** `testkit-test-guide`
- **apiVersion:** `github.com/ruinosus/dna/testkit/v1`
- **Plane:** composition

A TestGuide is a declarative test SCRIPT: an ordered list of steps (action → expected) that validates one or more work items. A versioned, schema-validated, re-runnable doc — the roteiro that used to live in chat or a generic HtmlArtifact. Links to its Story via ``verifies`` (and the Story's ``produces[]``).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string |  |  |
| `description` | string | yes | What this guide validates (one line or short paragraph). |
| `kind_of_test` | string | yes |  |
| `labels` | array |  |  |
| `owner` | string |  | Actor who owns this guide. |
| `prerequisites` | array |  | Setup needed before running, e.g. ['make up', 'tenant acme selected']. |
| `scope_hint` | string |  | Target area/scope for the run. |
| `status` | string |  |  |
| `steps` | array | yes |  |
| `updated_at` | string |  |  |
| `verifies` | array |  | Work items this guide verifies, as 'Kind/name' refs (e.g. 'Story/s-x'). |

## TestRun

- **Alias:** `testkit-test-run`
- **apiVersion:** `github.com/ruinosus/dna/testkit/v1`
- **Plane:** composition

A TestRun is an EXECUTION record of a TestGuide: the outcome (pass/fail/partial/blocked), who ran it, per-step results and evidence. Producing one stamps an ``artifact_produced`` event on the work item's timeline (surfaces in FOCUS); a passing run whose ``verifies`` points at a Story drives the derived journey's ``verify`` phase.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `evidence` | array |  | Refs/links backing the outcome, e.g. ['HtmlArtifact/ha-x', urls]. |
| `executed_at` | string |  |  |
| `executed_by` | string |  | Actor who ran it. |
| `guide_ref` | string | yes | Name of the TestGuide that was executed. |
| `labels` | array |  |  |
| `notes` | string |  |  |
| `outcome` | string | yes |  |
| `screenshots` | array |  | Run-level evidence prints, Asset-backed (asset name + blob path), NOT inline base64. |
| `step_results` | array |  |  |
| `verifies` | array |  | Work items this run verifies (inherited from the guide); drives journey 'verify'. |

## Theme

- **Alias:** `helix-theme`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition

A Theme declares a Studio color palette (primary/accent/success in light + dark HSL) + optional typography. ThemeApplier reads the active theme from localStorage and writes CSS variables on :root — instant switch, no rebuild. Tenants can ship a brand theme by publishing themes/brand.yaml in their scope.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  | Optional markdown description — when to use, design rationale, brand notes. |
| `created_at` | string |  |  |
| `display_label` | string | yes | Human-readable theme name (e.g. 'Cobre', 'Indigo Linear'). |
| `font_mono` | string |  | Monospace font stack override. |
| `font_sans` | string |  | Sans-serif font stack override (CSS font-family string). |
| `inspiration` | string |  | Reference (e.g. 'claude-code-templates', 'Linear', 'Stripe', 'custom'). |
| `owner` | string |  |  |
| `palette` | object | yes |  |
| `preview_swatch_hex` | string |  | Optional explicit hex for the switcher swatch. Computed from palette.primary.light if omitted. |
| `radius` | string |  | Default border radius (e.g. '0.5rem'). Maps to --radius. |
| `tagline` | string |  | One-line vibe summary (shown in switcher dropdown + card description). |
| `tags` | array |  |  |
| `updated_at` | string |  |  |
| `vibe` | string |  | Visual vibe tag for grouping. |

## UseCase

- **Alias:** `helix-usecase`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition

A UseCase is a UML-canonical use case: a goal-oriented interaction between actors and the system. It composes one primary actor, supporting actors, and the agents that fulfill the goal. Use cases carry preconditions, a main flow of steps, alternate flows, postconditions, and success criteria. Not a prompt target — purely declarative composition/documentation. Stored as a flat yaml file under use_cases/<name>.yaml.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agents` | array |  |  |
| `alternate_flows` | array |  |  |
| `guardrails` | array |  |  |
| `main_flow` | array |  |  |
| `postconditions` | array |  |  |
| `preconditions` | array |  |  |
| `primary_actor` | string |  |  |
| `skills` | array |  |  |
| `soul` | string |  |  |
| `success_criteria` | array |  |  |
| `supporting_actors` | array |  |  |
| `tools` | array |  |  |

## UserProfile

- **Alias:** `helix-user-profile`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** composition

A UserProfile holds per-user personalization data for AI agents (display name, language preference, communication style, opt-in personal/project context). Consent-gated: agents only inject the block when consent.profile_used_in_prompts is true. Each user can read/write only their own profile via the get_my_profile / update_my_profile tools — never another user's.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `communication_style` | string |  | Free text — what tone/length/formality the agent should use ('curto e direto, humor seco OK', 'formal por default'). |
| `consent` | object |  |  |
| `created_at` | string |  | Server-stamped on first create. |
| `display_name` | string | yes | How the user wants to appear ('Jefferson Barnabé'). |
| `do_not_share` | array |  | Topics the agent must NEVER volunteer or surface unprompted. User-defined privacy boundary. |
| `languages` | object |  |  |
| `last_seen_at` | string |  | Server-stamped on each session bootstrap. |
| `personal_context` | string |  | OPT-IN free text — family, locale, hobbies. Only injected when consent.profile_used_in_prompts is true. The user owns and can clear this at any time. |
| `preferred_name` | string |  | What the agent should call them in conversation ('Jeff', 'Jefferson'). |
| `project_context` | string |  | OPT-IN free text — projects they own/care about, current focus. Helps the agent resolve 'meu projeto', 'aquela feature'. |
| `pronouns` | string |  | Optional pronoun preference ('ele/dele', 'she/her', 'they/them'). |
| `tags` | array |  |  |
| `updated_at` | string |  | Server-stamped on every update. |
| `user_id` | string | yes | Stable identifier from the IdP (email / sub claim). Server-side stamp — clients cannot forge. |

## UserRoleAssignment

- **Alias:** `audit-userroleassignment`
- **apiVersion:** `github.com/ruinosus/dna/audit/v1`
- **Plane:** composition

Persistent role assignment for a user inside a tenant. The doc name IS the user_id. Roles list is the source of truth for require_role decorators when Clerk webhook sync is enabled.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `email` | string |  |  |
| `note` | string |  | Free-form admin note (hire date, etc). |
| `roles` | array | yes | Authoritative role list. Backend require_role reads claims.roles which is set by Clerk via JWT — this Kind is the admin-managed mirror for Clerk's org membership. |
| `updated_at` | string | yes |  |
| `user_id` | string | yes | Identity claim (sub or email). |

