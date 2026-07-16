# Record-plane Kinds

**Record-plane** Kinds are queryable data rows (SDLC work items, research, evidence, audit log, …) — first-class documents you `query`/`count` rather than fold into a prompt.

!!! info "Generated from the registered Kinds"

    Introspected from `Kernel.auto()` by `scripts/gen_kinds_docs.py`.
    Each Kind's spec fields come from its own `schema()`.

## ADR

- **Alias:** `sdlc-adr`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An ADR captures ONE architectural decision with its context, rationale, and consequences. Convention: one ADR per file, immutable once accepted (subsequent decisions supersede). Follows Nygard / MADR template — Adopt on ThoughtWorks Tech Radar. Studio renders these as the decision log of the project; PMs/architects can scan rationale without reading code.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `alternatives_considered` | array |  | Other options weighed and rejected, with brief why-not. |
| `body` | string |  | Optional full markdown body (ADR.md). When present, takes precedence over the structured fields above for rendering. Useful when the ADR predates this schema. |
| `consequences` | string |  | What follows from this decision — positive AND negative. Future readers need to see the trade-offs, not just the wins. |
| `context` | string | yes | WHY we needed to decide. What forces are in play? What constraints (technical, business, team) shape the choice? 1-3 paragraphs. |
| `covers_features` | array |  | Feature names this decision affects. |
| `created_at` | string |  |  |
| `date` | string |  | Date the decision was accepted (ISO-8601). |
| `deciders` | array |  | Actor names who participated in the decision. |
| `decision` | string | yes | WHAT we decided. Active voice: 'We will X' or 'We chose X over Y'. 1-2 paragraphs. |
| `narrative_origin` | string |  | When extracted from a Narrative.decisions[] entry during Phase 2.2 migration, this points to the source Narrative slug for provenance. |
| `status` | string | yes | Lifecycle: proposed → accepted → deprecated\|superseded. Use `superseded` (not deprecated) when a newer ADR replaces this one — link via `superseded_by`. |
| `superseded_by` | string |  | ADR slug that supersedes this one (when status=superseded). |
| `supersedes` | array |  | ADR slugs this one replaces. |
| `tags` | array |  | Free-form tags (e.g. 'persistence', 'auth', 'ui'). |
| `title` | string | yes | Decision headline — start with imperative verb. |
| `updated_at` | string |  |  |

## AgentSession

- **Alias:** `sdlc-agent-session`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A AgentSession captures a developer↔AI coding conversation as a versioned project artifact. Tool-agnostic: works for Claude Code, Cursor, Cline, Codex, Aider via per-tool adapters. Schema is the LCD (lowest-common-denominator) of the major tools' export formats.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `applied_commits` | array |  | Git SHA refs touched in-session. |
| `body` | string |  | Rendered transcript markdown (stored in SESSION.md). |
| `cost_usd` | number |  |  |
| `ended_at` | string |  |  |
| `file_changes` | array |  | Repo-relative paths edited during session. |
| `journey_phase` | string |  | Universal journey phase. AgentSessions usually live in `discover` (brainstorming chats) or `build` (execution chats). The agent stamps this on capture. |
| `model` | string |  | AI model identifier (e.g. claude-opus-4-7, gpt-5-codex). |
| `participants` | array |  | Actor names (humans + agent identities). |
| `produced_artifacts` | array |  | Refs to docs created/modified during session. |
| `raw_source` | string |  | Provenance pointer — tool-native source path or URL (JSONL file path, sqlite URI, etc). Required for re-derivation. |
| `session_id` | string | yes | Tool-native session identifier (UUID/sqlite-rowid/etc). |
| `started_at` | string | yes |  |
| `summary` | string |  |  |
| `title` | string | yes | Human-readable session title (Jira-style summary). |
| `token_usage` | object |  | {input, output, cache_*} — adapter-specific shape. |
| `tool` | string | yes | Provenance — which AI coding tool produced this session. claude-code \| cursor \| cline \| codex \| aider \| specstory \| other. |
| `tool_specific` | object |  | Escape hatch for per-tool extras (Cline checkpoints, CC git snapshots, etc). |
| `tool_version` | string |  |  |
| `workspace_path` | string |  |  |

## ArchiveProposal

- **Alias:** `sdlc-archive-proposal`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `evidence` | string | yes | Plain-text justification. E.g. 'Unreferenced by any WorkflowEvent.methodology_artifact in 91 entries scanned. Last touch 73 days ago.' |
| `proposed_at` | string |  | Auto-stamped on creation. |
| `proposed_by` | string | yes | Oracle slug (typically 'cleanup-suggestions') or 'user'. |
| `reason` | string | yes | Why prune. orphan = no inbound refs; superseded = newer doc replaces; stale = no touch beyond threshold; contradicted = newer doc disagrees; duplicate = identical. |
| `review_deadline` | string | yes | Spec §15: default proposed_at + 14d. Stale proposals past this date should be re-evaluated (not auto-vetoed). |
| `reviewer` | string |  | Auto-stamped on approve/veto. Username or 'system'. |
| `reviewer_note` | string |  | Optional note explaining approval/veto reasoning. |
| `status` | string | yes | proposed → approved → executed (moves target to _forgotten/) OR proposed → vetoed (target stays). |
| `target_kind` | string | yes | Any Kind name (e.g. 'Plan', 'Story', 'Issue', 'Spec'). Self-references rejected at execution time. |
| `target_name` | string | yes | Slug of the doc being proposed for forgetting. |

## AuditLog

- **Alias:** `audit-auditlog`
- **apiVersion:** `github.com/ruinosus/dna/audit/v1`
- **Plane:** record

Immutable record of a role-gated HTTP endpoint invocation. Captures actor, roles claimed, operation, target Kind/name, scope/tenant, request_id, outcome, and timestamp. Used by compliance auditors + admins to answer 'who did what when' without parsing application logs.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor` | string | yes | Identity that made the request. From claims.email > claims.sub. 'dev-user' in dev-bypass, 'test-user' in test-header mode. |
| `captured_at` | string | yes | UTC ISO-8601 timestamp. |
| `detail` | object |  | Free-form context: which required roles failed, body size, durations, errors. Defensive about PII — don't include request bodies verbatim. |
| `operation` | string | yes | HTTP method + path template, e.g. 'PUT /scopes/{scope}/docs/Agent/{name}' or 'POST /assessments/{name}/run'. |
| `outcome` | string | yes | success = decorator + handler ran clean. denied = 403 from require_role. error = handler raised (500/422/...). |
| `remote_ip` | string |  | Best-effort client IP (X-Forwarded-For aware). |
| `request_id` | string |  | Correlation ID (UUIDv4) — joins logs. |
| `roles` | array | yes | Roles claimed at request time (from JWT or DNA_DEV_ROLES). Snapshot — does NOT reflect later role revocations. |
| `target_kind` | string |  | Kind of doc affected (when applicable). Null for non-doc ops like POST /sync/replicate. |
| `target_name` | string |  | Name of doc affected, when applicable. |
| `target_scope` | string |  | Scope of doc affected, when applicable. |
| `target_tenant` | string \| null |  | Tenant the operation routed to (claims.tenant + overrides resolved). Null = base layer write. |
| `user_agent` | string |  | HTTP User-Agent header. |

## Automation

- **Alias:** `dna-automation`
- **apiVersion:** `github.com/ruinosus/dna/automation/v1`
- **Plane:** record

An Automation declares background work as data — ``on`` picks the trigger (cron = 5-field schedule; hook = a kernel lifecycle hook name from KNOWN_HOOK_NAMES; tool = an async dispatch tool the host exposes to the model), ``runner`` picks what executes (an Agent or a Tool by name), plus the shared agent_directive / input / result templating / spoken copy / safety block. Adding or retargeting an automation is writing one YAML, zero deploy. The SDK validates and lists (see ``dna.extensions.automation.query.automations_for``); the HOST executes — the runner contract is an extension point, documented in docs/concepts/builtin-kinds.md.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_directive` | string |  | Dispatch instruction sent to an agent runner (with {arg} placeholders). Optional — a tool runner needs none. |
| `description` | string |  |  |
| `done_message` | string |  | Spoken/UI copy attached to the finished run. Supports {placeholders} from the args. |
| `enabled` | boolean |  | Disabled automations stay declared but hosts must not fire them (automations_for filters them out by default). |
| `input` | object |  | Structured input the host resolves into the runner's context. Hosts may support tokens such as {scope}, {now}, {utc_date}. |
| `labels` | array |  |  |
| `on` | object | yes | The trigger. type=cron → scheduled (5-field cron expression, validated at write); type=hook → a kernel lifecycle hook name (KNOWN_HOOK_NAMES vocabulary, validated at write); type=tool → an async dispatch tool the host exposes to the model. |
| `result_kind` | string |  | Kind the automation output should be persisted as (e.g. Research, Doc) when the runner produces a document. |
| `result_spec_template` | object |  | Deterministic persist template — when an agent runner synthesizes but does not persist a doc itself, the host creates a result_kind doc from this template ({arg} fills from the args, {output} from the agent synthesis). |
| `runner` | object | yes |  |
| `running_message` | string |  | Spoken/UI copy returned at dispatch (tool trigger). |
| `safety` | object |  | Loop-safety the HOST enforces for this automation. All fields optional — an absent field falls back to the host default. |

## Bug

- **Alias:** `sdlc-bug`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Bug captures a factual defect: repro_steps, severity, environment, status. Distinct from Postmortem (incident — sev1-sev5 outage analysis) e Issue umbrella (enhancement/question/other).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actual` | string |  |  |
| `body` | string |  |  |
| `created_at` | string |  |  |
| `description` | string |  |  |
| `environment` | string |  |  |
| `expected` | string |  |  |
| `fix_adr` | string |  |  |
| `fix_summary` | string |  |  |
| `found_at` | string |  |  |
| `labels` | array |  |  |
| `owner` | string |  |  |
| `priority` | string |  |  |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `related_feature` | string |  |  |
| `related_finding` | string |  |  |
| `related_story` | string |  |  |
| `reporter` | string |  |  |
| `repro_steps` | array |  |  |
| `resolved_at` | string |  |  |
| `root_cause` | string |  |  |
| `severity` | string | yes |  |
| `status` | string | yes |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `title` | string | yes |  |
| `updated_at` | string |  |  |

## Changelog

- **Alias:** `sdlc-changelog`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Changelog records release notes per semver version per Keep a Changelog 1.1.0 convention. Six sections: Added, Changed, Deprecated, Removed, Fixed, Security. Latest entry at top (reverse chronological). [Unreleased] section tracks work in flight.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  | Optional full markdown CHANGELOG.md. |
| `created_at` | string |  |  |
| `description` | string |  |  |
| `title` | string | yes | Project name typically. |
| `updated_at` | string |  |  |
| `versions` | array |  | Reverse-chronological list of versions. |

## CognitivePolicy

- **Alias:** `sdlc-cognitive-policy`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `affect` | object |  | Affect vocabulary for the memory/affect engine (ex-AffectPalette). The active palette steers engraphy affect tags. |
| `allocation` | object |  | Engram allocation (dedup/archival) knobs (ex-AllocationPolicy). |
| `created_at` | string |  |  |
| `decay` | object |  | Memory retention/forgetting knobs (ex-DecayPolicy). |
| `embedding` | object |  | Embedding model + dimension + search weights (ex-EmbeddingProfile). ONLY meaningful on the _lib doc — the embedding space is intrinsically global (stored vectors and every query must share one model+dimension); kernel.embedding_profile reads _lib directly and never a scope override. `recall.calibrated_for` points back here. |
| `engram_strength` | object |  | Initial-strength rules per engraphy trigger (ex-EngramStrengthPolicy). |
| `generation` | object |  | Operational params for the memory-gen engines (the ORIGINAL CognitivePolicy body, now one section among peers). |
| `memory` | object |  | Agent-memory governance (ex-MemoryPolicy). Each entry in `policies` keeps the old multi-doc matcher semantics — merged most-specific-wins by dna_shared.cognitive.memory_policy. |
| `owner` | string |  |  |
| `pagination` | object |  | REST list pagination defaults/caps (ex-PaginationPolicy). Data-plane ownership — read by dna_shared.pagination_policy, not the cognitive engines. |
| `recall` | object |  | Recall-tuning knobs for the ecphory engine (ex-RecallPolicy). |
| `updated_at` | string |  |  |

## Copilot

- **Alias:** `helix-copilot`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** record

A Copilot is a declarative, servable AG-UI copilot backend — a binder that composes one-or-more mounted Agents (each with its own Tools and optional MCPFederation) into a single servable ``/agui`` app. It carries only the copilot-level concerns that don't belong on any single Agent ``mounts`` (where agents serve), ``serving`` (the transport), ``tenant`` (inbound-tenant propagation), ``hitl`` (the approval card for gated write tools), ``knowledge`` (RAG collections it may read), and ``frontend`` (console hints). Instructions and persona stay on the mounted Agent — a Copilot never re-declares them. One document emits a servable backend (Agno today), the single evolution point DNA Cloud's copilots consume. Stored as ``copilots/<name>.yaml`` — marketplace-shareable as a bundle.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `frontend` | object |  | Frontend console hints for the emitted copilot UI. |
| `hitl` | object |  | Human-in-the-loop approval surface for write tools the mounted agents gate. |
| `knowledge` | object |  | RAG the copilot may read. Optional — a pure-action copilot declares none. |
| `mounts` | array | yes | The Agents this copilot serves, each at a mount path. At least one is required. |
| `serving` | object | yes | How the copilot backend is served. |
| `tenant` | object |  | Inbound-tenant handling. When propagate is true, the emitted serving layer derives tenant/oid from request headers into run-state for the mounted tools to read. |

## Doc

- **Alias:** `dna-doc`
- **apiVersion:** `github.com/ruinosus/dna/doc/v1`
- **Plane:** record

A Doc is one page of in-product documentation. The marker is ``docs/<name>/DOC.md`` — YAML frontmatter (icon, subtitle, summary, order, locale, enabled, kind_of, category, tags) plus a markdown body that lands in ``spec.body``. The page title is ``metadata.description``. ``kind_of`` follows Diátaxis (tutorial/how_to/reference/explanation); ``category`` groups the sidebar; ``locale`` lets one corpus serve multiple languages. This is the Kind behind ``dna docs list/show``.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string | yes | Markdown body of the page — the DOC.md content below the frontmatter. |
| `category` | string \| null |  | Free-form sidebar grouping (e.g. "Getting started"). Null falls back to a flat list. |
| `enabled` | boolean |  | If false, the page is hidden from listings. |
| `icon` | string |  | Emoji or short string shown next to the title. |
| `kind_of` | enum |  | Diátaxis classification (learning- / task- / information- / understanding-oriented). Null = uncategorized. |
| `locale` | string |  | Content locale (e.g. pt-BR, en). ``dna docs`` filters on it. |
| `order` | integer |  | Sort order in the sidebar (ascending). |
| `subtitle` | string |  | One-line subtitle shown under the title. |
| `summary` | string |  | 1-2 sentences for the topic header card / previews. |
| `tags` | array |  | Free-form labels for filtering and search. |

## Epic

- **Alias:** `sdlc-epic`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An Epic groups Features under a single business goal (Jira/ADO terminology). May optionally carry a target_date + target_package + target_version when the Epic is also a dated release; otherwise it's a pure aggregation umbrella. status moves through planning → in-progress → done.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `business_value` | number |  |  |
| `cancelled_reason` | string |  |  |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `definition_of_done` | array |  |  |
| `description` | string |  |  |
| `features` | array |  |  |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. |
| `labels` | array |  |  |
| `priority` | string |  |  |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `reporter` | string |  |  |
| `status` | string | yes |  |
| `target_date` | string |  |  |
| `target_package` | string |  | owner/name reference to a Genome |
| `target_version` | string |  | Semver to match Genome.spec.version when done |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `title` | string |  | Human-readable display name (Jira 'summary'). Falls back to description, then to metadata.name slug. |
| `updated_at` | string |  |  |
| `watchers` | array |  |  |

## EvalBaseline

- **Alias:** `eval-eval-baseline`
- **apiVersion:** `github.com/ruinosus/dna/eval/v1`
- **Plane:** record

An EvalBaseline pins one EvalRun as the "known good" reference for an EvalSuite. `dna eval run <suite> --baseline <name>` compares the fresh run against the pinned run and reports regressions (passed → now failing), improvements and unchanged cases — with an exit code a user's CI can gate on. Pin with `dna eval pin <run>`.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `label` | string |  | Human note on why this run is the reference. |
| `pinned_at` | string |  |  |
| `run_name` | string | yes | Name of the pinned EvalRun document. |
| `suite` | string | yes | Name of the EvalSuite this baseline belongs to. |

## EvalCase

- **Alias:** `eval-eval-case`
- **apiVersion:** `github.com/ruinosus/dna/eval/v1`
- **Plane:** record

An EvalCase is one declarative evaluation scenario. It names a target (default = the kernel's own prompt composition via build_prompt, deterministic and offline; custom targets such as a live LLM are host-registered EvalTargetPorts) and a list of deterministic checks (contains/regex/equals/length) applied to the text the target produced. Grouped by an EvalSuite; executed by the local runner (`dna eval run`), which persists an EvalRun.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `checks` | array | yes | Deterministic assertions applied to the text the target produced. ALL checks must pass for the case to pass. |
| `description` | string |  | What this case verifies (one line). |
| `expected` | string |  | Human-readable note of the expected outcome (shown in reports; not machine-checked). |
| `input` | string |  | Free-form input for custom targets (e.g. the user message an LLM target sends). The prompt target ignores it. |
| `skip` | boolean |  | Declared but not executed (reported as skipped). |
| `skip_reason` | string |  |  |
| `tags` | array |  |  |
| `target` | object |  | What to evaluate. Omitted → the suite's target → {type = prompt}. type=prompt composes the agent's system prompt via build_prompt (deterministic, offline); any other type must be registered by the host as an EvalTargetPort. |

## EvalRun

- **Alias:** `eval-eval-run`
- **apiVersion:** `github.com/ruinosus/dna/eval/v1`
- **Plane:** record

An EvalRun is the persisted result of one local execution of an EvalSuite — pass/fail/error/skip counts, timestamps, the resolved target, and per-case results with the outcome of every declared check. Written by `dna eval run --save`; compared against a pinned EvalBaseline to detect regressions (`dna eval run --baseline`).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `errored` | integer |  |  |
| `failed` | integer | yes |  |
| `finished_at` | string |  |  |
| `passed` | integer | yes |  |
| `results` | array | yes | Per-case outcomes, in execution order. |
| `skipped` | integer |  |  |
| `started_at` | string |  |  |
| `suite` | string | yes | Name of the EvalSuite that was executed. |
| `target` | object |  | The suite-level target the run resolved (per-case overrides are recorded on each result row). |
| `total` | integer | yes |  |

## EvalSuite

- **Alias:** `eval-eval-suite`
- **apiVersion:** `github.com/ruinosus/dna/eval/v1`
- **Plane:** record

An EvalSuite groups EvalCase documents and configures how the local runner executes them — the case list (empty = all cases in the scope), a default target the cases inherit, and stop_on_fail. Run it with `dna eval run <suite>`; each execution can be persisted as an EvalRun and compared against a pinned EvalBaseline.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `cases` | array |  | EvalCase names to run, in order. Empty/omitted = every EvalCase in the scope. |
| `description` | string |  | What this suite evaluates (one line). |
| `labels` | array |  |  |
| `stop_on_fail` | boolean |  | Stop executing remaining cases after the first failed/errored case. Default false. |
| `target` | object |  | Default target for cases that do not declare their own (same shape as EvalCase.target). |

## Evidence

- **Alias:** `evidence-evidence`
- **apiVersion:** `github.com/ruinosus/dna/evidence/v1`
- **Plane:** record

An Evidence document is an immutable audit event record. Captures the event type, SHA-256 hash of the referenced content, timestamp, author, and optional snapshot. Used by the GAIA report pipeline to provide a verifiable audit trail.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `author` | string |  |  |
| `captured_at` | string |  |  |
| `created_at` | string |  |  |
| `document_ref` | string |  |  |
| `event_type` | string | yes |  |
| `notes` | string |  |  |
| `payload` | object |  |  |
| `sha256` | string |  |  |
| `snapshot` | object |  |  |
| `source_kind` | string |  |  |
| `source_name` | string |  |  |
| `suite` | string |  |  |

## Feature

- **Alias:** `sdlc-feature`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Feature is a shippable unit. It implements one or more UseCases, decomposes into Stories, and is owned by an Actor. Its status reflects the development pipeline: discovery → in-development → done.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `acceptance_criteria` | array |  | Feature-level AC (parent of Story-level AC). |
| `as_a` | string |  | Role: 'As a <role>'. INVEST/user-story format slot. |
| `blocked_reason` | string |  |  |
| `business_value` | number |  |  |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `definition_of_done` | array |  |  |
| `description` | string | yes |  |
| `epic` | string |  | Parent Epic name |
| `estimate` | string |  | T-shirt size or story points (free-form) |
| `i_want` | string |  | Goal: 'I want <goal>'. INVEST/user-story format slot. |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. |
| `labels` | array |  |  |
| `mockups` | array |  |  |
| `narrative_line` | string |  | One-sentence agent-curated prose summary of what this Feature has been DOING (past-tense, semantic) — shown next to the Feature in Studio's narrative swimlane. Updated by the working agent as scope evolves. Distinct from `description` (intent / problem statement, written once at file-time). |
| `owner` | string |  | Actor name |
| `priority` | string |  |  |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `release_target` | string |  |  |
| `reporter` | string |  |  |
| `so_that` | string |  | Benefit: 'so that <benefit>'. INVEST/user-story format slot. |
| `sprint_ref` | string |  |  |
| `status` | string | yes |  |
| `stories` | array |  |  |
| `time_tracking` | object |  |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `title` | string |  | Human-readable display name (Jira 'summary'). |
| `updated_at` | string |  |  |
| `use_cases` | array |  |  |
| `watchers` | array |  |  |

## Forecast

- **Alias:** `sdlc-forecast`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

Forecast = falseable hypothesis. would_change predictions are verified at outcome_check_at by the cognitive/verification.py loop. Authored by oracles or user. Pair with SynthesisRun (oneiric artefact, non-falseable processing).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `drafted_at` | string |  |  |
| `evidence_from_present` | array | yes |  |
| `forecaster` | string | yes | Author — oracle slug or 'user'. |
| `generated_by` | string |  |  |
| `lens` | string |  | Optional perspective tag (optimism\|risk\|friction\|opportunity\|neutral). |
| `outcome_check_at` | string | yes |  |
| `resolved_at` | string |  |  |
| `scenario` | string | yes | Prose framing of the hypothesis. |
| `scope_ref` | string | yes |  |
| `source_oracle` | string |  |  |
| `status` | string | yes |  |
| `timeframe` | string | yes |  |
| `verifications` | array |  | Audit trail appended by verification loop. |
| `would_change` | array | yes | Predictions checked by verification.py. |

## HtmlArtifact

- **Alias:** `sdlc-html-artifact`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An HtmlArtifact stores an HTML page as a first-class, linkable output of a work item (Story/Feature/Epic/Spike). It is a bundle: ARTIFACT.html holds the raw HTML verbatim (byte-faithful round-trip) plus an optional artifact.json companion with structured metadata (title, description, source, created_at) — the same shape as a Soul's SOUL.md + soul.json. Attach one to a work item with ``dna sdlc produces add <WiKind>/<wi> HtmlArtifact/<name>`` so a design doc, roteiro, or report that used to live in chat becomes traceable on the board.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `artifact_json` | object |  | Structured metadata: title, description, source, created_at. |
| `html` | string |  | The raw HTML document (byte-faithful). |

## Initiative

- **Alias:** `sdlc-initiative`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An Initiative is a strategic investment unit (1-2 quarters) that groups Epics under a measurable outcome. Sits between Theme/OKR (annual) and Epic (multi-sprint). For enterprise roadmaps where Theme→Epic skip loses too much resolution.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  |  |
| `business_value` | number |  |  |
| `created_at` | string |  |  |
| `description` | string |  |  |
| `epics` | array |  | Epic names this initiative groups. |
| `horizon_end` | string |  |  |
| `horizon_start` | string |  |  |
| `labels` | array |  |  |
| `outcome_metric` | string |  | What KR/metric this initiative is targeted at. |
| `owner` | string |  | Actor name (PM / Product Lead). |
| `priority` | string |  |  |
| `status` | string | yes |  |
| `target_value` | string |  | e.g. '+30% MAU' or '<200ms p95'. |
| `theme_ref` | string |  | Optional Theme/OKR Objective slug. |
| `title` | string | yes |  |
| `updated_at` | string |  |  |

## Insight

- **Alias:** `sdlc-insight`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An Insight binds a perpetual question to a target UA (oracle-X). The UA owns the persona + heuristics + LLM selection. The runner iterates active Insights and dispatches each to its target_ua, which emits an StatusReport via create_status_report tool.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `active` | boolean |  | False to disable without deleting. |
| `cadence_hours` | integer |  | How often the runner re-dispatches the target_ua. 0 disables auto-run (manual only via /agent endpoint). |
| `description` | string |  | Optional 1-2 sentence human description of what this oracle answers. The INSIGHT.md body. |
| `evidence_kinds` | array |  | Hint of which Kinds the target_ua should read. Informational — the UA itself decides via its tools. |
| `icon` | string |  | Single emoji shown next to the oracle. |
| `question` | string | yes | The perpetual question this oracle pursues. |
| `tags` | array |  |  |
| `target_ua` | string | yes | Slug of the Agent that runs this oracle (e.g. 'oracle-health'). The UA owns the persona, tools, and LLM config — Insight only points. |

## IntelInsight

- **Alias:** `intel-insight`
- **apiVersion:** `github.com/ruinosus/dna/intel/v1`
- **Plane:** record

An IntelInsight is the dissemination unit of the intelligence layer — a ranked, actionable insight produced from an IntelSource, carrying its headline, cited fact, suggested action, actionability score, matched PIRs, citations, evidence rating and feedback state. The ranker sets the score; the digest suppresses insights below the source threshold; the feedback stage records the state (new/actioned/dismissed/snoozed). Embeddable so a later dedup stage can recall semantically similar insights.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | string \| null |  | The single suggested action. |
| `citations` | array |  | Sources backing the fact — each a {url, title} pair. |
| `created_at` | string \| null |  | ISO-8601 timestamp, stamped by the writer (not defaulted here). |
| `evidence_rating` | string |  | How well-grounded the fact is — evidence-based, opinion/practice, or anecdotal. |
| `fact` | string | yes | What happened / the cited fact. |
| `pirs` | array |  | Which Priority Intelligence Requirements this insight matches. |
| `score` | number | yes | Actionability score (0..1). The ranker sets this; the digest suppresses insights scoring below the source's threshold. |
| `source_ref` | string \| null |  | The IntelSource name this insight came from. |
| `state` | string | yes | The feedback disposition — the reader's response to the insight. |
| `title` | string | yes | The insight headline. |
| `why` | string \| null |  | Why it matters to this source. |

## IntelSource

- **Alias:** `intel-source`
- **apiVersion:** `github.com/ruinosus/dna/intel/v1`
- **Plane:** record

An IntelSource declares one watched portfolio source (a repo, a scope, or an external URL) the DNA observes — its research cadence, actionability threshold, Priority Intelligence Requirements (PIRs) and mute state, as per-tenant declarative data. It is the Direction stage of the intelligence layer — the research → ranked insights → feedback pipeline reads active IntelSources and researches each on its cadence.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `cadence` | string |  | How often the source is researched — manual (on demand), event (on a trigger), daily, or weekly. |
| `muted` | boolean |  | True to pause research on this source without deleting it. |
| `name` | string | yes | The source name, e.g. copiloto-medico. The doc name SHOULD equal this. |
| `notes` | string \| null |  | Free-form operator notes. |
| `pirs` | array |  | Priority Intelligence Requirements — focus areas that get prioritized when researching this source. |
| `threshold` | number |  | Actionability threshold (0..1) below which insights from this source are suppressed. Insights scoring under it are not disseminated. |
| `type` | string | yes | What kind of source this is — a code repo, a DNA scope, or an external URL/feed. |
| `uri` | string \| null |  | Path / URL / scope id the source points at. Null when the name alone identifies it. |

## Issue

- **Alias:** `sdlc-issue`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An Issue is a human-authored ticket — bug, enhancement, question, or task. Tracked across open → triaged → in-progress → resolved. Optional links to a parent Feature (work it belongs to) and a related Finding (eval-detected origin).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actual_behavior` | string |  |  |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `description` | string | yes |  |
| `expected_behavior` | string |  |  |
| `github_number` | integer |  | GitHub issue number this doc is bridged to. |
| `github_state` | string |  | Last observed GitHub-side state. |
| `github_synced_at` | string |  | When the GitHub side was last observed/synced. |
| `github_url` | string |  | Canonical https URL of the GitHub issue. |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. |
| `labels` | array |  |  |
| `owner` | string |  | Actor name |
| `priority` | string |  |  |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `related_feature` | string |  | Feature name |
| `related_finding` | string |  | Finding name |
| `reporter` | string |  |  |
| `reproduction_steps` | array |  |  |
| `resolution` | string |  |  |
| `severity` | string | yes |  |
| `status` | string | yes |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `title` | string |  | Human-readable display name (Jira 'summary'). |
| `type` | string | yes |  |
| `updated_at` | string |  |  |
| `watchers` | array |  |  |

## Kaizen

- **Alias:** `sdlc-kaizen`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Kaizen is a continuous-improvement observation noticed while working on something else — a smell, friction, a manual step, a missing test — captured as a first-class doc WITHOUT derailing the task at hand. Arc: observed → routed (an Issue/Story tracks the fix) → resolved (fix shipped). Twin of the `kaizen` timeline event on the originating work item (which carries a ref back to this doc).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor` | string |  | Who flagged it. |
| `body` | string | yes | The kaizen observation (what could be better). |
| `created_at` | string |  |  |
| `issue` | string |  | Issue/Story slug tracking the fix. |
| `labels` | array |  | Free-form theme tags (weighted into semantic-search source text). |
| `status` | string | yes | Observation arc: observed (flagged) → routed (fix tracked in `issue`) → resolved (fix shipped). |
| `updated_at` | string |  |  |
| `work_item` | string |  | Kind/slug of the work item where this was observed (polymorphic — Story/Spike/Issue). |

## LessonLearned

- **Alias:** `sdlc-lesson-learned`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `affect` | string | yes | Emotional tone. Evocative palette (Spec §15 decision): triumph, regret, surprise, wistful, ominous. |
| `affect_evidence_refs` | array |  | Concrete refs (rem-X, verdict-Y, Story/s-Z) that back the affect choice. Required for high-stakes affects so the LLM's claim is auditable against actual artifacts in the manifest. |
| `affect_reason` | string |  | Story s-remembrance-affect-reason-required. Concrete justification for the chosen affect — names specific slugs/SHAs/AC counts/state. NOT generic ('Story closed', 'shipped successfully'). Validator rejects writes that lack reason OR have boilerplate. Required for high-stakes affects (regret/ominous/surprise); optional for triumph/wistful but encouraged. |
| `area` | string | yes | Scoped target: Feature/X, Epic/Y, or Roadmap/Z. The LessonLearned surfaces when this area is touched. |
| `confidence_score` | number |  | Semon engram intensity. Multiplies BM25 score in retrieval. Bumps when homophonic LessonsLearned (same area) are filed — engrams reinforce each other. Decays with surface_count for hygiene. |
| `cues_history` | array |  | Semon ecforia trace. Each time the LessonLearned is surfaced via remember(), the cue (query + actor + timestamp) is appended. History of WHY this memory kept getting recalled. |
| `encoding_context` | object |  | Snapshot of the conditions at engraphy. semon-recaller scores ecphory candidates by partial-match against this dict. |
| `homophonic_links` | array |  | Semon homophony — engrams sharing substrate features. Each link records target + resonance score + basis. semon-recaller propagates a small strength boost (+0.02) to neighbors on ecphory (resonance). |
| `last_surfaced` | string |  | Auto-stamped on each surfacing; null until first surface. |
| `memory_type` | string |  | CoALA taxonomy — ORTHOGONAL to the Semon EngramState (type vs state): episodic = what happened (instance/sequence); semantic = a generalized fact about the world/user; procedural = how to act (a skill/rule). Absent = untyped (legacy). |
| `owner` | string |  | ATTRIBUTION: which agent authored this memory (e.g. claude-code, jarvis). Orthogonal to scope + to tenant (tenant separates USERS, owner separates AGENTS). Recall AUDIENCE is governed by `visibility`, NOT by owner (s-agent-memory-phase-0-bridge, 2026-06-02 — supersedes the 2026-05-17 owner-implies-private semantics). When absent: an unowned/project lesson (shared). |
| `relevance_decay_seed` | number |  | Multiplicative decay factor applied per 24h. Default 0.95 (~30% relevance after 14 days). |
| `revisions` | array |  | Reconsolidation log (Nader 2000 / neo-Semon). Append-only when a recall reawakens the engram and the consumer updates the summary. |
| `source_refs` | array | yes | Pointers to source artifacts (Narrative/X, WorkflowEvent/Y, etc.) that this memory derives from. |
| `summary` | string | yes | 1-2 sentence 'Lembre-se de...' — the recalled essence. |
| `superseded_by_memory` | string |  | Name of the memory that invalidated this one (not `superseded_by` — that's an ADR dep_filter token). Pairs with valid_to for point-in-time audit. |
| `surface_count` | integer |  | Increments on each surface. Damps re-surfacing via scoring formula in retrieval.py. |
| `surface_when` | array | yes | Triggers that surface this LessonLearned. Mirrors how human recall fires unbidden in context. |
| `tags` | array |  |  |
| `valid_from` | string |  | World-time validity start (Zep bi-temporal). Default: created_at. |
| `valid_to` | string |  | World-time validity end. Set when superseded/contradicted — the memory is INVALIDATED, never hard-deleted. Default recall excludes valid_to<now. |
| `visibility` | string |  | Recall audience (the customization axis): shared = all agents in scope recall it (cross-agent knowledge, default); private = only `owner` recalls it (an agent's raw working memory); pinned = always injected into working memory at bootstrap, bypassing recall scoring (the Letta 'memory block'); archived = retained + auditable but excluded from default recall (soft-forget). Humans audit ALL regardless of visibility (audit != recall). Phase 0 (2026-06-02). |

## Membership

- **Alias:** `portfolio-membership`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

A Membership is the RBAC join — a user's role at an org- or project-scope within a tenant's portfolio. It carries the user (email / id), the scope_type (org / project) and scope_ref it applies to, the role from the standard ladder (owner > admin > member > guest, highest-role-wins, org-owner superuser), and an invitation status (invited / active), as per-tenant declarative data. It is distinct from the platform-level TenantMembership (which links a user to a provisioning Tenant); this grants access inside the tenant's own Organization / Project graph.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `invited_at` | string \| null |  | ISO-8601 timestamp of the invite, stamped by the writer (not defaulted here). |
| `role` | string | yes | The role granted at this scope — the standard ladder (owner > admin > member > guest). Resolution is highest-role-wins across a user's memberships, with the org owner a superuser. |
| `scope_ref` | string | yes | The Organization or Project name this grant applies to (paired with scope_type). |
| `scope_type` | string | yes | What the grant is scoped to — an Organization (org) or a single Project (project). |
| `status` | string |  | Invitation lifecycle — invited (pending acceptance) or active. |
| `user` | string | yes | The member's identity — an email or stable user id. |

## ModelProfile

- **Alias:** `modelreg-model-profile`
- **apiVersion:** `github.com/ruinosus/dna/modelreg/v1`
- **Plane:** record

A ModelProfile records one LLM model's hard limits and capabilities (instruction_token_cap, context_window, tools_cap, modalities, cost). It is the single source of truth the prompt-budget write guard reads — never hardcode token caps in code; read them from the ModelProfile registry via kernel.model_profile().

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `aliases` | array |  | Alternate ids that resolve to this profile (deployment names, dated snapshots). kernel.model_profile() matches these on pass 2. |
| `context_window` | integer |  | Total context window in tokens. |
| `cost_per_1m_input_usd` | number \| null |  | USD per 1M input tokens (informational). |
| `cost_per_1m_output_usd` | number \| null |  | USD per 1M output tokens (informational). |
| `deprecated` | boolean |  | True when the model is scheduled for removal. |
| `deprecated_message` | string \| null |  | Human guidance shown when a deprecated model is used. |
| `family` | string \| null |  | Model family/lineage for grouping, e.g. 'gpt-realtime'. |
| `instruction_token_cap` | integer \| null |  | Hard cap for the system-instruction/persona in tokens. Null = no cap known (the guard fails open). THE value the prompt-budget guard enforces — never hardcode it in code. |
| `max_output_tokens` | integer \| null |  | Max completion/output tokens per response. |
| `modalities` | array |  | Supported modalities, e.g. [text], [text, audio], [text, image]. |
| `model_id` | string | yes | Canonical model identifier, e.g. 'gpt-realtime-2'. The doc name SHOULD equal the model_id; kernel.model_profile() matches on this field first. |
| `notes` | string \| null |  | Free-form operator notes. |
| `provider` | string | yes | Who serves the model — 'openai', 'anthropic', 'azure', a proxy alias, etc. |
| `realtime` | boolean |  | True for realtime voice models. STRICT marker: the prompt-budget guard VETOES an over-cap write against a realtime profile (voice sessions silently degrade past the cap); chat profiles only warn. |
| `tools_cap` | integer \| null |  | Max number of tools the model accepts per session. |

## Narrative

- **Alias:** `sdlc-narrative`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Narrative is a curated, human-readable summary of project activity. Stored as a NARRATIVE.md bundle with markdown body. Names usually encode the period (ISO date for daily, milestone slug for releases). Replaces ad-hoc 'what happened tonight?' chat scrolling — the agent stamps a Narrative at session end so future readers (CEO, customer, new-hire) can open one page and get the story.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor` | string |  | Who wrote this narrative (Actor name, 'claude-code', 'human', etc.). |
| `author_intent` | string |  | What kind of narrative this is. Drives how the morning panel groups multiple narratives — daily stack on the timeline, releases pin as marquee, retros surface in a 'lessons' filter. |
| `auto_generated` | boolean |  | true = LLM-generated draft; false = human or agent-curated prose. Studio shows a small badge so readers know what they're reading. |
| `body` | string | yes | Markdown body of the narrative (lives in NARRATIVE.md). Free-form — paragraphs, bullets, links to Stories/Features/commits. Should read like a human update, not a log dump. |
| `covers_epics` | array |  | Epic names this narrative discusses. |
| `covers_features` | array |  | Feature names this narrative discusses. |
| `covers_session` | string |  | AgentSession name this narrative was auto-derived from (Karpathy 'context ephemeral, files durable' pattern). Set by `dna sdlc session capture` when the post-capture narrative hook runs. |
| `covers_stories` | array |  | Story names this narrative discusses. |
| `created_at` | string |  |  |
| `decisions` | array |  | Ratified decisions made during the period covered by this narrative. Each captures the WHY, not just the WHAT — the decision-extractor pattern. |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. |
| `open_items` | array |  | Work that started but didn't close in this period. Studio's 'still open' section reads from this when present (otherwise computes heuristically from event diff). |
| `paragraphs` | array |  | Structured prose: list of past-tense paragraphs describing what shipped. Studio renders these as the hero block; falls back to `body` when empty. |
| `period_end` | string |  | End of the period (often the moment the narrative was written). |
| `period_start` | string |  | Start of the period this narrative covers (ISO-8601). |
| `summary` | string |  | Optional one-line tl;dr. When present, the Studio card shows this above the body for scanning. |
| `tags` | array |  | Free-form tags for filtering (daily, release, retro, ...). |
| `title` | string | yes | Headline for this narrative. Shown above the body. |
| `updated_at` | string |  |  |

## Organization

- **Alias:** `portfolio-org`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

An Organization is the tenant's own org profile — the enterprise-familiar top-level container (as in GitHub / Azure DevOps) whose portfolio of Projects the DNA Cloud console aggregates. It carries the org name, a URL-safe slug, an optional display name, and a plan_ref to the DNA Cloud Tier / WorkspacePlan the org is on, as per-tenant declarative data. One Organization per tenant; it is distinct from the platform-level Tenant provisioning identity Kind (the editable org profile inside the tenant's own portfolio, not the GLOBAL identity row).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string \| null |  | ISO-8601 timestamp, stamped by the writer (not defaulted here). |
| `display_name` | string \| null |  | Human-facing name shown in the console. Falls back to name. |
| `name` | string | yes | The organization's canonical name. The doc name SHOULD equal this. |
| `plan_ref` | string \| null |  | The DNA Cloud Tier / WorkspacePlan this org is on (a Tier tier_id or WorkspacePlan name). Null falls back to Free. The billing→enforcement bridge reads it; the OSS SDK only stores it. |
| `slug` | string | yes | URL-safe identity for the org, e.g. acme-corp. Used in routes and as a stable handle for the tenant's portfolio. |

## PatternInsight

- **Alias:** `cognitive-pattern-insight`
- **apiVersion:** `github.com/ruinosus/dna/cognitive/v1`
- **Plane:** record

PatternInsight = output of a dream-interp engine. Multiple interpretations per SynthesisRun OK — engines are complementary lenses, not exclusive. Hill engine produces exploration/insight/action structure; Jung produces amplifications + archetypes; Gestalt produces identifications.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | object |  | Hill: stage 3 — what would you DO differently? May propose concrete docs (ArchiveProposal, Story, PreMortem) for HITL approval. |
| `amplifications` | array |  | Jung: each symbol expanded by association. |
| `drafted_at` | string |  |  |
| `dream_ref` | string | yes | Slug of the SynthesisRun being interpreted. |
| `engine` | string | yes | Engine name from registry (e.g. 'hill-interp'). |
| `engine_params` | object |  | Params passed to the engine. |
| `exploration` | object |  | Hill: stage 1 — re-reading, associations, trigger, affect layer. |
| `framework` | string | yes | Interpretation school applied. |
| `generated_by` | string |  |  |
| `identifications` | array |  | Gestalt: voice of each element as the dreamer. |
| `individuation_question` | string |  | Jung: integration question opening reflection. |
| `insight` | object |  | Hill: stage 2 — what does the dream MEAN? Level in {waking, phenomenological, past, parts-of-self}. |
| `lens` | string |  | Perspectiva da interpretação. Valores convencionais: 'hill', 'jung', 'gestalt', 'pattern', um slug de Agent (ex: 'jarvis', 'architect'), ou 'synthesis-by-<agent>' pra meta-synthesis. Pode coincidir com framework — lens é o ponto de vista, framework é a metodologia. Phase: cognitive-reflection. |
| `owner` | string |  | Slug reference to a Agent. When set, this PatternInsight is PRIVATE to that agent. When null, it is GENERAL. Phase: cognitive-reflection. |
| `summary` | string | yes | 1-3 sentence overview of the interpretation. |
| `synthesizes` | array |  | PatternInsight IDs (names/slugs) que esta interpretação sintetiza. Vazia pra interpretações de 1ª camada (hill, jung, agent-interp). Não-vazia pra synthesis engines (agent-synthesis) que lêem N interps + SynthesisRun e produzem leitura final. Phase: cognitive-reflection. |
| `tags` | array |  |  |

## Plan

- **Alias:** `sdlc-plan`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Plan is a pointer to an implementation plan document on disk. Usually descends from a Spec (`spec_ref`). Pattern-agnostic — DNA tracks pointer + metadata + refs, not the structure of the plan itself.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `authors` | array |  |  |
| `body` | string |  | Markdown body (stored in PLAN.md). |
| `date` | string | yes |  |
| `epic` | string |  |  |
| `journey_phase` | string |  | Universal journey phase. A Plan typically lives in `plan` (decomposition) and may transition to `build` once Stories start landing. |
| `methodology` | string |  | Which planning methodology produced this plan (superpowers \| bmad \| spec-kit \| ...). Opt-in; lets the journey show the plan's origin honestly. The SDLC stays methodology-agnostic — this only records it. |
| `origin` | string |  | Optional audit-only origin path. |
| `pattern` | string |  |  |
| `spec_ref` | string |  | Name of the Spec this plan implements. |
| `status` | string | yes |  |
| `summary` | string |  |  |
| `tags` | array |  |  |
| `title` | string | yes |  |

## Postmortem

- **Alias:** `sdlc-postmortem`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Postmortem captures a factual analysis of an incident that happened — timeline, root cause, contributing factors, action items, lessons learned. Google SRE convention: blameless. Distinct from PreMortem (hypothetical) and Retrospective (recurring period summary).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action_items` | array |  | Concrete follow-ups to prevent recurrence. |
| `blameless` | boolean |  | Google SRE requirement — should always be true. |
| `body` | string |  |  |
| `contributing_factors` | array |  | Secondary factors that worsened the incident. |
| `created_at` | string |  |  |
| `impact` | string |  | Customer-facing impact in plain language (downtime, errors, etc.). |
| `incident_at` | string | yes | When incident started. |
| `lessons_learned` | array |  | Insights that generalize beyond this incident. |
| `related_features` | array |  |  |
| `related_stories` | array |  | Story slugs related to root cause or action items. |
| `resolved_at` | string |  | When incident was mitigated. |
| `root_cause` | string | yes | Primary cause (1-3 paragraphs). |
| `severity` | string | yes | Incident severity (sev1=full outage, sev5=cosmetic). |
| `tags` | array |  |  |
| `timeline` | array |  | Chronological event log. |
| `title` | string | yes | Short incident headline. |
| `updated_at` | string |  |  |
| `what_went_well` | array |  | Detection / response things that worked. |
| `what_went_wrong` | array |  | Detection / response things that didn't work. |

## PreMortem

- **Alias:** `cognitive-pre-mortem`
- **apiVersion:** `github.com/ruinosus/dna/cognitive/v1`
- **Plane:** record

A PreMortem rewinds a Story's history and asks what would have happened on the other branch. Generated by a deep-sleep hindsight hook after Stories ship/cancel. Verifiable: would_have_changed predictions are compared against current state at outcome_check_at — same verifier as SynthesisRun.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `alternative` | string | yes | Prose: 'If instead of <outcome>, the Story had <other path>, then...'. 2-4 sentences. |
| `divergence_point` | string | yes | Decision/event that branched the timeline. Cite a date or trigger event. |
| `drafted_at` | string |  |  |
| `evidence_against` | array |  | Doc refs that complicate the counterfactual. |
| `evidence_for` | array |  | Doc refs supporting the counterfactual. |
| `generated_by` | string |  |  |
| `outcome_check_at` | string |  | When to verify (same loop as SynthesisRun). |
| `source_outcome` | string | yes | What ACTUALLY happened to source_story. |
| `source_story` | string | yes | Slug of the Story being rewritten (e.g. 's-foo-bar'). |
| `status` | string |  |  |
| `strength` | string |  |  |
| `tags` | array |  |  |
| `verifications` | array |  | Verification trace (auto-populated by the verifier). |
| `would_have_changed` | array | yes | Predictions same shape as SynthesisRun.would_change. Verifiable via same measure_metrics path. |

## Project

- **Alias:** `portfolio-project`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

A Project is the multi-repo development-space container — the key Kind of the portfolio model. It owns a SDLC board scope (convention <slug>-development), one or more IntelSources the intelligence layer observes, and scoped memory, and it is the permission boundary. Repos are attached BY REFERENCE via repo_refs (an N—N edge kept on the Project side — a repo can belong to many projects without duplication; Repo carries no project back-ref). A Project has a visibility (private / shared) and an org_ref to its Organization, as per-tenant declarative data.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `board_scope` | string \| null |  | The SDLC scope this project owns (convention <slug>-development). Where its Stories / Issues / Epics live. |
| `created_at` | string \| null |  | ISO-8601 timestamp, stamped by the writer (not defaulted here). |
| `intel_source_refs` | array |  | IntelSource names the intelligence layer observes for this project (the sources feeding its insight stream). |
| `name` | string | yes | The project's canonical name. The doc name SHOULD equal this. |
| `org_ref` | string \| null |  | The Organization (name) this project belongs to. Null while unassigned. |
| `repo_refs` | array |  | Repo names attached to this project (the N—N edge — a repo may appear on multiple projects). The edge lives on the Project side only. |
| `slug` | string | yes | URL-safe identity for the project, e.g. copiloto-medico. Used in routes and to derive the board_scope by convention. |
| `visibility` | string |  | Who can see the project — private (org-internal) or shared (visible across the portfolio). |

## PromptTemplate

- **Alias:** `sdlc-prompt-template`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A PromptTemplate is a versioned, overlayable user-prompt template owned by the kernel — the declarative answer to 'where does the user prompt live?'. Callers (typically Python helpers or HTTP endpoints) fetch the template by name and format() it with per-call variables. Tenants can override the template body without touching code. Templates can ship versioned with their consuming Kind (Narrative, StatusReport, etc.) so prompt-engineering changes are reviewable diffs, not commits to call sites.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string | yes | Template text with {var} placeholders. |
| `default_locale` | string |  |  |
| `description` | string |  |  |
| `tags` | array |  |  |
| `variables` | array |  | Names of placeholders body expects. |

## Reference

- **Alias:** `sdlc-reference`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `cited_by` | array |  | Auto-maintained by `dna sdlc cite`. Don't author by hand. |
| `content_path` | string |  | Optional path to rich-content sidecar (e.g. docs/superpowers/research/<slug>.md) |
| `created_at` | string |  |  |
| `fetched_at` | string |  |  |
| `key_quotes` | array |  |  |
| `kind_of` | string | yes |  |
| `owner` | string |  |  |
| `relevance` | string |  | Why this matters for THIS project. |
| `summary` | string | yes | 1-2 sentence what this source says. |
| `tags` | array |  |  |
| `title` | string | yes |  |
| `updated_at` | string |  |  |
| `url` | string |  |  |

## Repo

- **Alias:** `portfolio-repo`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

A Repo is a code repository the portfolio references — its name, url, provider (github / gitlab / azure-devops / other) and default_branch, as per-tenant declarative data. It is attached to N Projects via Project.repo_refs (the N—N edge lives on the Project side); a Repo carries no project back-ref, so a repo shared across projects is never duplicated. "Which projects use this repo" is a query over Projects, not a stored reverse list.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string \| null |  | ISO-8601 timestamp, stamped by the writer (not defaulted here). |
| `default_branch` | string \| null |  | The repo's default branch, e.g. main. Null when unknown. |
| `name` | string | yes | The repo name, e.g. copiloto-medico. The doc name SHOULD equal this; Project.repo_refs point at it. |
| `provider` | string |  | Where the repo is hosted — github, gitlab, azure-devops, or other. |
| `url` | string \| null |  | Clone / browse URL of the repository. Null when the name alone identifies it. |

## Retrospective

- **Alias:** `sdlc-retrospective`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Retrospective captures lessons + action items from a period of work. Schema follows Atlassian 4 Ls (Loved/Loathed/Longed for/Learned) — what_went_well, what_didnt, action_items. Adopt for sprint retros, release retros, incident retros. For one architectural decision, use ADR. For one incident factual analysis, use Postmortem (Phase 3 — TBD).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action_items` | array |  | Concrete next-steps surfaced by the retro. |
| `actor` | string |  | Who wrote this retro (Actor name, 'claude-code', 'human', ...). |
| `auto_generated` | boolean |  | true = LLM-generated draft; false = human-curated. |
| `body` | string |  | Optional full markdown body (RETROSPECTIVE.md). Falls back from structured fields when present. |
| `covers_epics` | array |  | Epic names this retro discusses. |
| `covers_features` | array |  | Feature names this retro discusses. |
| `covers_session` | string |  | AgentSession name (Karpathy pattern). |
| `covers_stories` | array |  | Story names this retro discusses. |
| `created_at` | string |  |  |
| `intent` | string |  | What kind of retro this is. Drives Studio grouping — daily stack on timeline, releases pin as marquee, incidents surface in alert filter. |
| `learned` | array |  | Learned — insights surfaced during the period. Atlassian 4 Ls bucket #4. Feeds future ADRs. |
| `longed_for` | array |  | Longed for — capabilities/conditions wished for but absent. Atlassian 4 Ls bucket #3. |
| `narrative_origin` | string |  | When extracted from a Narrative during Phase 2.2 migration, this points to the source Narrative slug for provenance. |
| `open_items` | array |  | Work that started but didn't close — carry-over to next period. |
| `period_end` | string | yes | End of period covered. |
| `period_start` | string | yes | Start of period covered (ISO-8601). |
| `summary` | string |  | Optional one-line tl;dr (shown above body in Studio card). |
| `tags` | array |  | Free-form tags. |
| `title` | string | yes | Headline for this retrospective. |
| `updated_at` | string |  |  |
| `what_didnt` | array |  | Loathed / Lacked — things that didn't work or caused friction. Atlassian 4 Ls bucket #2. |
| `what_went_well` | array |  | Loved / Liked — things that worked in this period. Atlassian 4 Ls bucket #1. |

## RiskRegister

- **Alias:** `sdlc-risk-register`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

One risk entry per RiskRegister doc. PMBOK 7 + ISO 31000:2018 compliant schema: cause→event→consequence description, category, likelihood × impact scoring, mitigation actions, residual score, owner, status lifecycle. Studio aggregates all RiskRegister docs into a heatmap.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  |  |
| `category` | string | yes | PMBOK 7 categorization. |
| `created_at` | string |  |  |
| `description` | string | yes | Risk in cause→event→consequence format. ISO 31000 convention: 'If <cause>, then <event> may occur, resulting in <consequence>'. |
| `impact` | integer | yes | 1=negligible, 5=catastrophic. |
| `inherent_score` | integer |  | likelihood × impact (auto-derivable). |
| `last_reviewed` | string |  |  |
| `likelihood` | integer | yes | 1=rare, 5=almost certain. |
| `mitigation_actions` | array |  |  |
| `next_review_due` | string |  |  |
| `owner` | string | yes | Actor name accountable for monitoring/mitigation. |
| `related_epics` | array |  |  |
| `related_features` | array |  |  |
| `residual_impact` | integer |  |  |
| `residual_likelihood` | integer |  | Likelihood after mitigation. |
| `residual_score` | integer |  |  |
| `response` | string |  | Strategy: avoid\|transfer\|mitigate\|accept. |
| `status` | string | yes | Lifecycle: identified → assessed → mitigated → (realized = risk happened) → closed. |
| `tags` | array |  |  |
| `title` | string |  | Short risk name (used as doc name typically). |
| `updated_at` | string |  |  |

## Roadmap

- **Alias:** `sdlc-roadmap`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Roadmap groups Epics across time horizons (e.g. Q1 2026, Q2 2026). Pure organizational doc — no status of its own; the rolled-up status comes from the Epics it lists.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `description` | string | yes |  |
| `horizons` | array | yes |  |
| `journey_phase` | string |  | Universal journey phase. Roadmaps typically live in `discover` or `specify` — they're the north star, not the build. |
| `links` | array |  | External URLs (Confluence, Notion, etc.) |
| `owner_team` | string |  |  |

## Role

- **Alias:** `portfolio-role`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

A Role is one rung of the RBAC ladder expressed as data — its role_id, display_name, rank (higher = more access), the capabilities it grants, and a can_delete flag protecting built-in rungs. Modelling the ladder as data (not a hardcoded enum) makes it extensible — a tenant can add a custom role without a code change, and highest-role-wins simply compares rank. The four standard rungs (owner / admin / member / guest) ship as per-tenant seed docs; the org owner is a superuser above the ladder.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `can_delete` | boolean |  | False for the built-in ladder rungs that must not be removed (e.g. owner); true for custom roles a tenant adds. |
| `capabilities` | array |  | The grants this role unlocks (e.g. project.write, member.invite, billing.manage). The permission checker reads them from here. |
| `display_name` | string | yes | Human-facing role name, e.g. Owner, Admin, Member, Guest. |
| `rank` | integer | yes | Ladder rank — higher = more access. highest-role-wins compares this across a user's memberships. |
| `role_id` | string | yes | Canonical role id, e.g. owner / admin / member / guest. The doc name SHOULD equal this; Membership.role references it. |

## SavedView

- **Alias:** `sdlc-saved-view`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

Named view persisting filter + groupBy + sort + layout for a given Kind in a scope. Linear/Notion/Plane pattern — views as first-class entities (não só URL state). Load via ViewToolbar dropdown.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  |  |
| `created_at` | string |  |  |
| `description` | string |  |  |
| `filters` | object |  | Filter spec — map property → value. E.g. {feature: 'f-X', owner: 'alice', created_window: '7d'}. |
| `group_by` | string |  | Property to group by (status\|feature\|owner\|priority\|sprint\|...). |
| `is_default` | boolean |  | Whether this view loads by default when opening the target Kind list. |
| `layout` | string | yes | Visual layout pra render (board=group-by-status, list=flat, ...). |
| `owner` | string |  | Actor name (creator). Determines edit permission. |
| `sort_by` | string |  | Property to sort by. |
| `sort_direction` | string |  |  |
| `tags` | array |  |  |
| `target_kind` | string | yes | Kind name this view targets (Story, Bug, Spike, ...). |
| `title` | string | yes | Human label (e.g. 'My open Stories', 'This sprint blocked'). |
| `updated_at` | string |  |  |
| `visibility` | string |  |  |
| `visible_columns` | array |  | Subset of properties shown (table layout). Empty = show all default columns. |

## Spec

- **Alias:** `sdlc-spec`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Spec is a top-level design artifact. Cross-cutting by default (may drive multiple Features). Pattern-agnostic — superpowers, BMAD, droid, RFC, ADR, Spec Kit all work. status is ADR-style (draft → proposed → accepted → deprecated/superseded); phase is the orthogonal SDLC view (brainstorm → spec → plan_ready → implementing → done). Linkage to work is via Story.spec_refs[] (M:N), NOT via Spec.feature — the axis flip preserves Jira/Confluence semantics.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `authors` | array |  |  |
| `body` | string |  | Markdown body of the spec (stored in SPEC.md). |
| `date` | string | yes |  |
| `epic` | string |  |  |
| `journey_phase` | string |  | Universal journey phase. A Spec typically lives in `specify`, but draft Specs may be `discover` and finalized ones referenced by Plans drift to `plan`. Coexists with `phase` (SDLC-view) — `journey_phase` is the methodology-agnostic layer. |
| `origin` | string |  | Optional audit trail — repo-relative path the body was harvested from (e.g. docs/superpowers/specs/X.md). Not used at runtime. |
| `pattern` | string |  | Spec-driven pattern this artifact follows (superpowers \| bmad \| droid \| rfc \| adr \| spec-kit \| custom). |
| `phase` | string |  | Where in the SDLC this spec's work sits. Orthogonal to status. |
| `status` | string | yes |  |
| `summary` | string |  | Short one-paragraph summary (auto-extracted). |
| `supersedes` | string |  | Name of the prior Spec this one replaces. |
| `tags` | array |  |  |
| `title` | string | yes |  |

## Spike

- **Alias:** `sdlc-spike`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Spike is a time-boxed technical investigation. ONE question + finite time budget + outcome handoff (findings → Story or ADR). Distinct from Story (work to ship) e ADR (decision já tomada).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  |  |
| `completed_at` | string |  |  |
| `created_at` | string |  |  |
| `feature` | string |  |  |
| `findings` | string |  |  |
| `follow_up_adr` | string |  |  |
| `follow_up_spec` | string |  |  |
| `follow_up_story` | string |  |  |
| `html_artifacts` | array |  | HtmlArtifact names attached to this Spike (rendered mockups, diagrams, design comparisons). |
| `labels` | array |  |  |
| `logged_hours` | number |  |  |
| `owner` | string |  |  |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `question_to_answer` | string | yes |  |
| `recommendation` | string |  |  |
| `references` | array |  | Free-form Reference names (papers, blog posts, library docs cited mid-spike). |
| `related_spikes` | array |  | Sibling Spikes investigating overlapping questions. |
| `research_refs` | array |  | Research names this Spike consulted (curated syntheses with N References). |
| `started_at` | string |  |  |
| `status` | string | yes |  |
| `time_box_hours` | number |  |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `title` | string | yes |  |
| `updated_at` | string |  |  |

## StatusReport

- **Alias:** `sdlc-status-report`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ascended_from` | string |  | If the previous verdict's confidence differs from this one, this is the previous level. Empty string when it's the first verdict. |
| `bumped_remembrances` | array |  | Phase 2B (squishy-jumping-nebula): audit trail written by oracle_cue_hook listing the LessonLearned slugs whose cue history was bumped because this report cited them. Bidirectional pairing with LessonLearned.cues_history. Empty when the run had nothing to bump (the field is omitted, not stored as []). |
| `confidence` | string | yes | How firm the verdict is. `insufficient` = the heuristic didn't have enough data — the LLM was NOT called and the verdict is a stock message. |
| `evidence_refs` | array |  | Doc refs (Kind/name) cited as evidence for this verdict. Studio renders these as navigable links. |
| `generated_at` | string |  |  |
| `generated_by` | string |  | Model + actor (e.g. 'claude-sonnet-4-6'). |
| `heuristic_explanation` | string |  | Plain-text walkthrough of HOW the heuristic computed the metrics and decided the confidence. Transparency: a reader can audit the math. |
| `insight` | string | yes | Name of the Insight that produced this report. |
| `metrics` | object |  | Deterministic numbers the heuristic computed (cycle counts, frequencies, averages). Free-form object — schema varies per oracle. |
| `owner` | string |  | Slug reference to a Agent. When set, this StatusReport is PRIVATE to that agent. When null, it is GENERAL. Phase: cognitive-reflection. |
| `question` | string |  | Echo of the oracle's question at run time. |
| `rag_status` | string |  | PMO-standard RAG status (Red/Amber/Green) for executive dashboards. Red = action needed; Amber = watch; Green = healthy. Optional — heuristics that map metrics → RAG should populate this. |
| `thresholds` | object |  | Self-describing thresholds the heuristic used (e.g. `to_certain: 'pattern_freq > 0.9 AND n>=5'`). Lets the reader know what would change the verdict. |
| `verdict` | string | yes | Human-readable answer (1-3 sentences pt-BR). Synthesized by the LLM from the heuristic numbers. |

## Story

- **Alias:** `sdlc-story`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Story is a granular task: one developer, one PR, one estimate. Lists acceptance criteria, dependencies (other Stories that must land first), and rolls up to a Feature.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `acceptance_criteria` | array |  | Acceptance criteria. Legacy: list[str]. New (s-ac-dod-checklist-state): list[{text, done?, done_at?, done_by?}] for per-item state tracking. |
| `as_a` | string |  | Role: 'As a <role>'. INVEST/user-story format slot. |
| `blocked_reason` | string |  |  |
| `business_value` | number |  | WSJF-style scalar for relative prioritization. |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `definition_of_done` | array |  | Per-Story DoD. Same union shape as acceptance_criteria — legacy list[str] OR list[{text, done?, done_at?, done_by?}]. |
| `dependencies` | array |  | Other Story names that must land first |
| `description` | string | yes |  |
| `estimate` | number |  | Fibonacci story points (1, 2, 3, 5, 8, 13, 21) |
| `feature` | string |  | Parent Feature name |
| `i_want` | string |  | Goal: 'I want <goal>'. INVEST/user-story format slot. |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. |
| `labels` | array |  | Free-form tags for swim lanes / filters. |
| `mockups` | array |  | URLs/paths to design artifacts. |
| `owner` | string |  | Actor name |
| `priority` | string |  | Board priority. Jira-aligned. |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `release_target` | string |  | Epic name OR 'owner/pkg@semver' identifying the release this Story unblocks. |
| `reporter` | string |  | Actor who filed it (vs `owner` who works on it). |
| `so_that` | string |  | Benefit: 'so that <benefit>'. INVEST/user-story format slot. |
| `spec_refs` | array |  | Spec docs (kind=Spec) this Story implements. M:N linkage between the planning axis (Story) and the design axis (Spec) — Jira/Confluence-shaped. |
| `sprint_ref` | string |  | Sprint identifier (free-form, e.g. '2026-Q2-S2'). |
| `status` | string | yes |  |
| `time_tracking` | object |  |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `title` | string |  | Human-readable display name (Jira 'summary'). |
| `updated_at` | string |  |  |
| `watchers` | array |  | Actor names subscribed to changes. |

## SynthesisRun

- **Alias:** `sdlc-synthesis-run`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

SynthesisRun = oneiric artefact. Surreal recombination of project memory (fragments lifted from LessonLearned/Story/ArchiveProposal/WorkflowEvent) + impossible juxtapositions + dominant affect + one captured symbol. NOT falseable, NOT a prediction. Pair with Forecast for the predictive dimension.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `affect` | string | yes | Dominant emotional register of the dream. |
| `belief_updates` | array |  | Belief deltas the dream proposes. Each is a before/after pair with reasoning. Scribe downstream may apply, reject, or queue for human review. |
| `confidence` | number |  | Self-rated confidence in the dream's claims. 0.0 = pure imagination; 1.0 = ≥3 strong source_event_ids per claim + critic-pass clean. Used by ranker + clinical-guardrails. |
| `contradictions` | array |  | Detected contradictions between source_event_ids the dream surfaced. NOT auto-resolved — flagged for human or scribe arbitration. |
| `drafted_at` | string |  |  |
| `dreamer` | string | yes | Author — UA slug ('oneiric-scribe') or 'user'. |
| `echo` | array |  | Engram slugs activated (resonance, not analytic weight). |
| `fragments` | array | yes | 3-5 pieces of real project memory that got recombined to form the dream. Like ecforia cues. |
| `generated_by` | string |  |  |
| `insight_candidates` | array |  | Discrete proposals to promote into StatusReport / LessonLearned / Skill via downstream scribes. Each item is independently rankable + verifiable. |
| `juxtapositions` | array |  | Impossible / surreal combinations of fragments. Ex: 'rem-X encontra forget-Y e oferece uma troca.' Optional but encouraged. |
| `lens` | string |  | SynthesisRunLens.name used to frame this dream (e.g. 'hindsight-cf', 'future-projection', 'skill-extractor'). Null = generated from SynthesizerState voice alone. |
| `owner` | string |  | Slug reference to a Agent. When set, this SynthesisRun is PRIVATE to that agent (gerado a partir de LessonsLearned com mesmo owner). When null, the SynthesisRun is GENERAL. Phase: cognitive-reflection. S5 (dream-engines-v2): also matches a SynthesizerState.role when the dream came from hybrid-topn engine. |
| `scenario` | string | yes | Imagistic prose, 3-6 sentences. The scene unfolding. Can have dialogue, surreal events, affect-loaded imagery. NOT a prediction or hedge. |
| `skill_candidates` | array |  | Voyager-style skill seeds. Each is a name + trigger condition + procedural sketch. skill-synthesis engine consumes these. |
| `source_event_ids` | array |  | Doc refs of the memories this dream is grounded in. Required for every claim in insight_candidates + belief_updates. Provenance for critic-pass + eval-suite. |
| `source_oracle` | string |  |  |
| `symbol` | string | yes | 1-line metaphor that captures the dream as a whole. Image-based, not analytic. Ex: 'A Feature corre por um corredor que se estreita sem fim.' |
| `tags` | array |  |  |
| `woke_thought` | string |  | Optional. The single thought lingering on waking. Where reflection might begin, not a prediction. |

## SynthesizerState

- **Alias:** `sdlc-synthesizer-state`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

SynthesizerState = persona contract for a dream-gen agent. Declares role + goal + backstory + method + voice_markers + non_goals + memory_policy + constitution + examples. Read by hybrid-topn engine to drive voice + memory routing. Pairs 1:1 with a Agent (scribe-engram, oracle-risk, ...). Multiple co-exist; SynthesisRunTriggerPolicy routes events.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `backstory` | string |  | Narrative background (CrewAI pattern). 2-4 sentences. Anchors voice + perspective. Stored as bundle body so it can grow long. |
| `constitution` | array |  | Constitutional AI principles (DSI/Anthropic pattern). Ex: ['ground every claim in source_event_ids', 'mark speculation as such', 'prefer evidence over invention']. Critic-pass evaluates dream output against these. |
| `drafted_at` | string |  |  |
| `drafted_by` | string |  |  |
| `dreamer_memory_stream_ref` | string \| null |  | Reference to this dreamer's persistent memory stream — coleção dos SynthesisRuns anteriores deste dreamer (cross-session continuity). Generative Agents (Park 2023) evidence: voz individuada emerge de memory stream + reflexão, NÃO de voice_markers adjetivos. Hybrid-topn engine deve injetar últimos N dreams + reflexões no prompt context. Format esperado: '<scope>/SynthesisRunCollection/<dreamer-slug>' OR simples slug-name resolvido contra um SynthesisRunCollection Kind (a definir). Cross-synth ref: f-unique-voice-is-memory-not-prompt. |
| `examples_negative` | array |  | 2-3 anti-patterns. Critic-pass uses these as explicit negative examples (what to avoid). |
| `examples_positive` | array |  | 2-3 exemplary dreams in this dreamer's voice. Few-shot prompts to anchor style. |
| `goal` | string | yes | What this dreamer is FOR. Ex: 'consolidate episódios em padrões reutilizáveis' (scribe), 'flag tail-risks antes que cristalizem em incidente' (oracle-risk). |
| `linked_agent` | string |  | Optional Agent slug this SynthesizerState pairs with (1:1 — same persona, two surfaces: agent runs synchronous, dreamer runs offline). |
| `memory_policy` | object |  | Routing hints for memory retrieval. Hybrid- topn engine respects these when assembling memory_subset. Empty dict = match-all. |
| `method` | string | yes | How this dreamer reasons. analogical = compare-and-contrast; causal = chain of events; surreal = juxtaposition; structural = patterns/relations; narrative = arc; counterfactual = 'what if'; metaphorical = imagistic transfer. |
| `non_goals` | array |  | What this dreamer MUST NOT do. Used as explicit critic-pass guardrails. Ex: 'never make diagnostic claims', 'never name living people in dreams'. |
| `role` | string | yes | Short label for this dreamer. Usually matches a Agent slug. Ex: 'scribe-engram', 'oracle-risk', 'narrative-historian'. |
| `tags` | array |  |  |
| `voice_markers` | array | yes | Words/structures/cadence that mark this dreamer's voice. Ex: ['vestígio', 'arquivo subterrâneo', 'frase nominal curta', 'metáfora geológica']. Used by ranker for voice fingerprint match (anti-drift). |

## Task

- **Alias:** `sdlc-task`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Task is a granular work item (horas-dias) typically as sub-item of a Story. For multi-day deliverables use Story.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `blocked_reason` | string |  |  |
| `body` | string |  |  |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `description` | string |  |  |
| `due` | string |  |  |
| `estimate_hours` | number |  |  |
| `labels` | array |  |  |
| `logged_hours` | number |  |  |
| `owner` | string |  |  |
| `priority` | string |  |  |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `status` | string | yes |  |
| `story_ref` | string |  |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `title` | string | yes |  |
| `updated_at` | string |  |  |

## Tier

- **Alias:** `cloud-tier`
- **apiVersion:** `github.com/ruinosus/dna/cloud/v1`
- **Plane:** record

A Tier declares one DNA Cloud plan's hard caps (calls/day, rate, tenants) and which feature families it unlocks, as GLOBAL declarative data so changing a limit is a file edit, not a redeploy. Resolve it via kernel.tier(id_or_alias); the quota enforcer reads the caps from here and never hardcodes them.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `aliases` | array |  | Alternate ids that resolve to this tier (legacy plan names). kernel.tier() matches these on pass 2. |
| `calls_per_day` | integer \| null |  | Daily call quota. Null = unlimited (enterprise). THE value the quota enforcer reads — never hardcode it in code. |
| `display_name` | string | yes | Human-facing plan name, e.g. Free, Pro, Enterprise. |
| `feature_families` | array |  | Tool families this tier unlocks, e.g. [definitions, sdlc, memory, emit]. |
| `max_tenants` | integer \| null |  | Number of tenants the plan allows. Null = unlimited. |
| `memory_mode` | string |  | Memory access level granted by the tier — none, read, or write. |
| `notes` | string \| null |  | Free-form operator notes. |
| `overage_per_1k_usd` | number \| null |  | USD charged per 1k calls above the daily quota. Null = no overage (hard cap). |
| `price_usd_month` | number |  | Flat monthly price in USD (0 for the free tier). |
| `rate_per_sec` | integer \| null |  | Per-second rate limit. Null = unmetered. |
| `sdlc_mode` | string |  | SDLC board access level granted by the tier — none, read, or write. Read = list/digest/ADR; write = create/transition/comment. |
| `sla` | boolean |  | True when the tier includes a support/uptime SLA (enterprise). |
| `tier_id` | string | yes | Canonical tier id, e.g. free, pro, enterprise. The doc name SHOULD equal the tier_id; kernel.tier() matches on this field first. |

## Tool

- **Alias:** `helix-tool`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** record

A Tool is a declarative, invocable capability an agent can call — an HTTP endpoint, an MCP server tool, a Python callable, a shell command, or a builtin. It bridges DNA with OpenAI/Anthropic tool-calling conventions. The agent-facing surface is its ``metadata.description`` (the text the model reads to decide to call it) and its ``spec.input_schema`` (the "parameters" JSON Schema of the arguments); ``dna.load_tools`` / ``loadTools`` serve exactly that surface, identically to Python and TypeScript consumers from this one source. It also declares an auth strategy and read_only / requires_confirmation flags the host honors at runtime. Agents reference Tools via ``dep_filters.tools``. Stored as ``tools/<name>.yaml`` — marketplace-shareable as standalone bundles.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `auth_env_var` | string |  | Environment variable holding the credential (e.g. GITHUB_TOKEN). |
| `auth_type` | string |  | Credential strategy for the invocation. |
| `endpoint` | string |  | URL called when type=http. Supports {placeholder} templating. |
| `examples` | array |  | Usage examples ([{input, output}]). |
| `input_schema` | object |  | JSON Schema of the arguments the agent passes when invoking the tool — the "parameters" the model fills in. Surfaced as ``parameters`` by ``dna.load_tools`` / ``loadTools``. |
| `mcp_server` | string |  | MCP server name when type=mcp. |
| `mcp_tool` | string |  | Tool name on the MCP server when type=mcp. |
| `method` | string |  | HTTP method when type=http (default POST). |
| `output_schema` | object |  | JSON Schema describing the shape of the tool's response. |
| `python_callable` | string |  | Attribute on the module (function or class) when type=python. |
| `python_module` | string |  | Dotted import path when type=python. |
| `read_only` | boolean |  | False = the tool may mutate state (DB writes, file changes, external side effects). |
| `requires_confirmation` | boolean |  | Force user approval before each invocation. |
| `shell_command` | string |  | Command template when type=shell. Never executed without confirmation. |
| `tags` | array |  | Free-form labels for filtering and search. |
| `type` | string |  | How the tool is executed. builtin \| http \| mcp \| python \| shell. |

## WorkflowEvent

- **Alias:** `sdlc-workflow-event`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

Append-only journey ledger. One entry per (artifact, phase) pair. Read together as a sequence, they form the trail from discover → reflect for a Roadmap/Epic/Feature. DNA's methodology-agnostic layer — Superpowers / BMAD / Spec Kit all map onto it via the `methodology` field.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor` | string |  | Who recorded the transition. |
| `artifact_kind` | string |  | Back-compat (deprecated): legacy Kind half of ``ref``. |
| `artifact_name` | string |  | Back-compat (deprecated): legacy name half of ``ref``. |
| `auto_emitted_by` | string |  | Back-compat (deprecated): legacy form of ``actor``. |
| `closes_cycle` | boolean |  | True on a `reflect` entry that has been closed by `journey close-cycle` — marks the boundary where the next discover starts cycle N+1. Set automatically; client may use as the explicit cycle delimiter. |
| `created_at` | string |  |  |
| `cycle_index` | integer |  | 1-based cycle number this entry belongs to. All entries within the same ouroboros loop share the same cycle_index. Incremented when `journey close-cycle` opens the next discover. Backend-explicit alternative to client-side heuristic cycle detection. |
| `decision_text` | string |  | Back-compat (deprecated): free-text decision on the entry. |
| `decisions` | string |  | Back-compat (deprecated): legacy decisions note on the entry. |
| `ended_at` | string |  | When the agent left this phase. Null while the phase is still active. |
| `epic_ref` | string |  | Back-compat (deprecated): legacy form of ``parent_ref`` (Epic). |
| `feature_ref` | string |  | Back-compat (deprecated): legacy form of ``parent_ref`` (Feature). |
| `methodology` | string |  | Which methodology the agent followed in this phase. ``ad-hoc`` is honest — Studio renders it with a 'no methodology' badge so we can spot where we cut corners. |
| `methodology_artifact` | string |  | Repo-relative path or URL to the methodology's external artifact, when applicable. E.g. ``docs/superpowers/plans/foo-plan.md`` for the Superpowers writing-plans output, ``.specify/foo/plan.md`` for Spec Kit, etc. |
| `owner` | string |  | Back-compat (deprecated): legacy owner of the entry. |
| `parent_ref` | string |  | Anchor doc grouping this entry with siblings. Typically ``Feature/<name>`` or ``Epic/<name>`` — everything in the journey of one Feature has the same parent_ref. |
| `phase` | string | yes | Which of the five universal phases this entry represents. |
| `rationale` | string |  | Back-compat (deprecated): free-text rationale on the entry. |
| `ref` | string |  | Doc this entry pins. Format: ``Kind/name`` (e.g. ``Spec/foo``, ``Plan/bar``, ``AgentSession/vs-baz``). |
| `seed_from` | string |  | Name of the prior cycle's `reflect` WorkflowEvent that seeded this entry. Set on `discover` entries created via `dna sdlc journey close-cycle` — the ouroboros bite, where reflect's lessons literally feed into the next discover. Distinct from `transitioned_from`: that's the immediate predecessor across phases; this is the cross-cycle inheritance link. |
| `skipped_phases` | array |  | Phases jumped over to get to this entry. E.g. discover → build means skipped ['specify', 'plan'] — Studio shows them in muted strikethrough so the trajectory stays honest. |
| `started_at` | string |  |  |
| `summary` | string |  | 1-2 sentence note about what happened in this phase. Optional — rendered as the entry's tooltip in Studio. |
| `tags` | array |  |  |
| `timestamp` | string |  | Back-compat (deprecated): legacy form of ``created_at``. |
| `transitioned_from` | string |  | Name of the previous WorkflowEvent in this trajectory (forms a linked list). Optional for the first entry of a trajectory. |

## Workspace

- **Alias:** `tenant-workspace`
- **apiVersion:** `github.com/ruinosus/dna/tenant/v1`
- **Plane:** record

A Workspace is the DNA tenancy root — a first-class, named, DNA-native space that authenticates identities from any Azure org via Entra and decides visibility through WorkspaceMembership (Model B, the GitHub/Slack shape). Its opaque, immutable workspace_id is the physical `tenant` column value on every row it owns, so renaming never rewrites data; the founding workspace reuses the founder's Azure tid for a zero-migration cutover. GLOBAL declarative data in `_lib`.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string | yes | When the workspace was created (ISO 8601). |
| `created_by` | string | yes | Email of the identity that created the workspace (its first Owner). |
| `name` | string | yes | Human display name, e.g. "Barnabé Labs". Editable. |
| `plan_ref` | string \| null |  | The workspace's current Tier/WorkspacePlan key (billing attaches to the workspace, not to an identity or Azure org). Null = the Free floor. Resolved via kernel.workspace_plan(workspace_id). |
| `slug` | string |  | URL-safe handle (e.g. for `/w/<slug>` links). Editable; distinct from the immutable workspace_id. |
| `workspace_id` | string | yes | Opaque, immutable id — the physical value of the `tenant` column on every row this workspace owns. Never changes (renaming edits name/slug, never this). The doc name SHOULD equal it. The founding workspace's id == the founder's Azure tid (zero migration); new workspaces get fresh ids and never reuse a tid. |

## WorkspaceMembership

- **Alias:** `tenant-workspace-membership`
- **apiVersion:** `github.com/ruinosus/dna/tenant/v1`
- **Plane:** record

A WorkspaceMembership maps a verified identity (Entra oid + email + tid) to a workspace_id + role + status — the identity→workspace boundary of ADR Model B and the crown-jewel authorization check (an ACTIVE grant is required to touch a workspace; fail-closed otherwise). Invites are by email (the handle) and bind to the durable oid on first verified sign-in (two-phase), matching only on verified token claims. GLOBAL declarative data in `_lib`, distinct from the portfolio Membership (intra-workspace org/project RBAC).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `accepted_at` | string \| null |  | ISO-8601 timestamp when the invite was accepted and oid bound. |
| `identity_email` | string | yes | Normalized (lowercased) email — the INVITE HANDLE. You invite by email before the person has ever signed in; matching is only ever on a verified token email claim, never a caller-supplied value. |
| `identity_oid` | string \| null |  | The stable Entra `oid`, BOUND on first accepted sign-in (null while pending). The durable key — post-bind re-auth keys on this, never the mutable email. |
| `identity_tid` | string \| null |  | The Azure org (tenant id) the accepting identity came from — PROVENANCE only (no longer the DNA tenant under Model B). Bound on accept. |
| `invited_at` | string \| null |  | ISO-8601 timestamp of the invite (stamped by the writer). |
| `invited_by` | string \| null |  | Email of the Owner/Admin who created the invite. |
| `role` | string | yes | Workspace-level role — the standard ladder (owner > admin > member > guest, highest-role-wins). References the Role Kind. |
| `status` | string | yes | Invite lifecycle — pending (invited, oid not yet bound) → active (accepted, oid bound). No membership / non-active → no access. |
| `workspace_id` | string | yes | The workspace this grant is in — the tenant key (matches a Workspace.workspace_id). |

## WorkspacePlan

- **Alias:** `cloud-workspace-plan`
- **apiVersion:** `github.com/ruinosus/dna/cloud/v1`
- **Plane:** record

A WorkspacePlan maps one DNA workspace to its current Tier as GLOBAL declarative data, so enforcement follows billing state without a redeploy. Billing attaches to the workspace (not an identity or Azure org); dna-cloud's Stripe webhook writes it on subscribe/cancel; the MCP server reads it via kernel.workspace_plan(workspace_id) when the token carries no explicit plan claim — zero Stripe/billing code lives in the OSS SDK, which only reads the assignment.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `notes` | string \| null |  | Free-form operator notes. |
| `source` | string |  | Where the assignment came from, e.g. stripe / manual / trial. |
| `status` | string |  | The billing status of the assignment, e.g. active / past_due / canceled. |
| `stripe_customer_id` | string |  | The Stripe customer id backing the assignment (dna-cloud writes it; the OSS SDK never calls Stripe). |
| `stripe_subscription_id` | string |  | The Stripe subscription id backing the assignment (dna-cloud writes it; the OSS SDK never calls Stripe). |
| `tier_id` | string | yes | The assigned Tier's id, e.g. free, pro, enterprise. Resolved to caps via kernel.tier(tier_id) — never a literal in code. |
| `updated_at` | string |  | When dna-cloud last wrote this assignment (ISO 8601). |
| `workspace_id` | string | yes | The DNA workspace this assignment is for (the opaque, immutable id the kernel `tenant` column carries). The doc name SHOULD equal it; kernel.workspace_plan() matches on this field. |

