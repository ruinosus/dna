# Kinds reference

A **Kind** is DNA's unit of identity + composition — the equivalent of a Kubernetes CRD, but for agent behaviour. Every Kind is declared by a `*.kind.yaml` **KindDefinition** descriptor; the descriptor format is pinned by [`kind-definition.schema.json`](../../schemas/kind-definition.schema.json) and summarised below. The catalogue on this page is generated from the **live registered Kinds** (`Kernel.auto()`), so it cannot drift from the code.

## The KindDefinition descriptor

Declarative Kind descriptor — the format of builtin `kinds/*.kind.yaml` package descriptors AND per-scope `kinds/<name>/KIND.yaml` documents (one format, one funnel). Canonical copy: docs/schemas/kind-definition.schema.json; a byte-identical runtime copy ships as sdk-py package data (dna/kernel/schemas/) and backs the validation in TypedKindDefinition.from_raw. Parity-critical: the Python hand-rolled validators (models.py KindDefinitionSpec.from_raw) and the TS Zod schema (models.ts KindDefinitionSpecSchema) must accept exactly what this schema accepts (guarded by test_kind_definition_schema.py / kind-definition-schema.test.ts). Editor autocomplete: put `# yaml-language-server: $schema=<path-to-this-file>` on the first line of a .kind.yaml.

`spec` fields of a KindDefinition:

| Field | Required | Description |
| --- | --- | --- |
| `alias` | yes | Globally unique alias, convention `<owner>-<kebab(kind)>` (e.g. `sdlc-kaizen`). Used in dep_filters, templates and cross-kind refs — never bare Kind names. |
| `ascii_icon` |  | Single emoji or character for ASCII tree / compact views. |
| `created_at` |  | Runtime-stamped volatile field (never authored). |
| `default_agent` |  | Fixed Agent name returned by get_default_agent_name for every doc of this Kind. |
| `default_agent_field` |  | Spec field whose value is returned VERBATIM by get_default_agent_name (descriptor-expressiveness D6). |
| `dep_filters` |  | Cross-Kind references: spec field → target Kind ALIAS (never a bare Kind name). |
| `describe` |  | Per-doc one-liner: a template string ("{name} ({status})") or a projection mapping ({"path": "description"}) (descriptor-expressiveness D3). |
| `description_fallback_field` |  | Spec field acting as the Studio card description fallback when metadata.description is absent (D7). |
| `display_label` |  | Human-friendly plural label (e.g. "Kaizens"). |
| `docs` |  | Prose explanation of what this Kind IS at the concept level (surfaced by describe_kind). |
| `embed` |  | Spec fields composing the doc's embedding text (semantic search source, F3 D4). |
| `flatten_in_context` |  | True flattens the spec dict into the prompt context. |
| `graph_style` |  | Colors for mermaid/graph visualizations, e.g. {fill, stroke, text_color}. |
| `is_overlayable` |  | A tenant overlay may fork this Kind (false only for structural bootstrap Kinds). |
| `is_root` |  | True only for the scope-root identity Kind (one per scope). |
| `is_runtime_artifact` |  | True for Kinds whose docs are PRODUCED by runtime workflows (eval runs, findings, ...) rather than authored — replication/seed/export tools skip them. |
| `origin` | yes | Registry namespace label of the owning extension/package, e.g. `github.com/ruinosus/dna/sdlc`. |
| `plane` |  | composition = participates in agent composition (writes invalidate scope caches) · record = pure typed document (cacheless writes, never composes into prompts; cannot carry composition signals — the plane lint rejects contradictions). |
| `prompt_target` |  | True if documents of this Kind compose into LLM prompts. |
| `prompt_target_priority` |  | Ordering priority among prompt targets (lower first). |
| `schema` |  | JSON Schema of the Kind's spec dict. Drives Studio form generation + validate_on_parse. New Kinds should ship `additionalProperties: false` (s-strict-schema-lint ratchet). |
| `schema_fragments` |  | Namespaced schema fragment IDs merged into `schema` in order (e.g. ["sdlc/workitem-common"]). Python reference implementation only — the TS Zod schema does not consume it yet. |
| `scope_inheritable` |  | Documents of this Kind inherit across scopes (false for per-scope ledgers + structural Kinds). |
| `spec_defaults` |  | Shallow-merge defaults applied as {**spec_defaults, **spec} BEFORE schema validation in parse() (D5). |
| `storage` | yes | Where documents of this Kind live on disk (mirrors StorageDescriptor / storage_dict_to_descriptor). |
| `summary` |  | List-endpoint projection. Dict form {field: default} passes through; list form ["a", "b"] is normalized with per-schema-type defaults (array→[], boolean→false, number/integer→null, else ""). |
| `target_api_version` | yes | apiVersion namespace of the Kind being DEFINED (globally unique), e.g. `github.com/ruinosus/dna/sdlc/v1`. |
| `target_kind` | yes | CamelCase name of the Kind being defined, e.g. `Kaizen`. Must be unique across api_versions (i-195). |
| `tenant_scope` |  | Tenant enforcement for this Kind. Undeclared = permissive (base + per-tenant override). Máxima: an inheritable default-of-`_lib` Kind must NEVER be tenanted. |
| `ui` |  | StudioUIMetadata mapping — generates Studio routes/sidebar/sitemap. Keys are validated strictly (⊆ StudioUIMetadata dataclass fields) by the hand-rolled check AND here (D1). |
| `ui_schema` |  | Per-field widget-hint bag (field → {widget, label, help, language, height, order, ...}). Deliberately permissive — an explicitly UI-owned bag (D4). See docs/KIND-UI-HINTS.md. |
| `updated_at` |  | Runtime-stamped volatile field (never authored) — allowed so write-stamped documents keep validating. |
| `version` |  | Runtime-stamped volatile field (never authored). |
| `volatile_spec_fields` |  | Extra write-/runtime-stamped spec fields excluded from the canonical digest, unioned with the base set {updated_at, version, created_at}. |
| `workitem_common` |  | DEPRECATED back-compat shorthand for schema_fragments: ["sdlc/workitem-common"]. Python-only. |

## Registered Kinds (71)

### Composition plane

**Composition-plane** Kinds are behaviour that composes into an agent's prompt (skills, souls, guardrails, …) — resolved through the layer/tenant overlay engine.

| Kind | Alias | apiVersion |
| --- | --- | --- |
| [Actor](composition.md#actor) | `helix-actor` | `github.com/ruinosus/dna/v1` |
| [Agent](composition.md#agent) | `helix-agent` | `github.com/ruinosus/dna/v1` |
| [AgentDefinition](composition.md#agentdefinition) | `agentsmd-agent` | `agents.md/v1` |
| [Canvas](composition.md#canvas) | `helix-canvas` | `github.com/ruinosus/dna/v1` |
| [Comment](composition.md#comment) | `collab-comment` | `github.com/ruinosus/dna/collab/v1` |
| [EvidencePolicy](composition.md#evidencepolicy) | `evidence-policy` | `github.com/ruinosus/dna/evidence/v1` |
| [Genome](composition.md#genome) | `helix-genome` | `github.com/ruinosus/dna/v1` |
| [Guardrail](composition.md#guardrail) | `guardrails-guardrail` | `github.com/ruinosus/dna/v1` |
| [Hook](composition.md#hook) | `helix-hook` | `github.com/ruinosus/dna/v1` |
| [KindDefinition](composition.md#kinddefinition) | `kinddef-kinddefinition` | `github.com/ruinosus/dna/core/v1` |
| [LayerPolicy](composition.md#layerpolicy) | `policy-layer-policy` | `github.com/ruinosus/dna/policy/v1` |
| [Lesson](composition.md#lesson) | `lesson-lesson` | `github.com/ruinosus/dna/lesson/v1` |
| [MCPFederation](composition.md#mcpfederation) | `federation-mcp` | `github.com/ruinosus/dna/federation/v1` |
| [Recognizer](composition.md#recognizer) | `presidio-recognizer` | `presidio/v1` |
| [Research](composition.md#research) | `research-research` | `github.com/ruinosus/dna/research/v1` |
| [SafetyPolicy](composition.md#safetypolicy) | `helix-safety-policy` | `github.com/ruinosus/dna/v1` |
| [Setting](composition.md#setting) | `helix-setting` | `github.com/ruinosus/dna/v1` |
| [Skill](composition.md#skill) | `agentskills-skill` | `agentskills.io/v1` |
| [Soul](composition.md#soul) | `soulspec-soul` | `soulspec.org/v1` |
| [Tenant](composition.md#tenant) | `tenant-tenant` | `github.com/ruinosus/dna/tenant/v1` |
| [TenantMembership](composition.md#tenantmembership) | `tenant-membership` | `github.com/ruinosus/dna/tenant/v1` |
| [TestGuide](composition.md#testguide) | `testkit-test-guide` | `github.com/ruinosus/dna/testkit/v1` |
| [TestRun](composition.md#testrun) | `testkit-test-run` | `github.com/ruinosus/dna/testkit/v1` |
| [Theme](composition.md#theme) | `helix-theme` | `github.com/ruinosus/dna/v1` |
| [UseCase](composition.md#usecase) | `helix-usecase` | `github.com/ruinosus/dna/v1` |
| [UserProfile](composition.md#userprofile) | `helix-user-profile` | `github.com/ruinosus/dna/v1` |
| [UserRoleAssignment](composition.md#userroleassignment) | `audit-userroleassignment` | `github.com/ruinosus/dna/audit/v1` |

### Record plane

**Record-plane** Kinds are queryable data rows (SDLC work items, research, evidence, audit log, …) — first-class documents you `query`/`count` rather than fold into a prompt.

| Kind | Alias | apiVersion |
| --- | --- | --- |
| [ADR](record.md#adr) | `sdlc-adr` | `github.com/ruinosus/dna/sdlc/v1` |
| [AgentSession](record.md#agentsession) | `sdlc-agent-session` | `github.com/ruinosus/dna/sdlc/v1` |
| [ArchiveProposal](record.md#archiveproposal) | `sdlc-archive-proposal` | `github.com/ruinosus/dna/sdlc/v1` |
| [AuditLog](record.md#auditlog) | `audit-auditlog` | `github.com/ruinosus/dna/audit/v1` |
| [Automation](record.md#automation) | `dna-automation` | `github.com/ruinosus/dna/automation/v1` |
| [Bug](record.md#bug) | `sdlc-bug` | `github.com/ruinosus/dna/sdlc/v1` |
| [Changelog](record.md#changelog) | `sdlc-changelog` | `github.com/ruinosus/dna/sdlc/v1` |
| [CognitivePolicy](record.md#cognitivepolicy) | `sdlc-cognitive-policy` | `github.com/ruinosus/dna/sdlc/v1` |
| [Doc](record.md#doc) | `dna-doc` | `github.com/ruinosus/dna/doc/v1` |
| [Epic](record.md#epic) | `sdlc-epic` | `github.com/ruinosus/dna/sdlc/v1` |
| [EvalBaseline](record.md#evalbaseline) | `eval-eval-baseline` | `github.com/ruinosus/dna/eval/v1` |
| [EvalCase](record.md#evalcase) | `eval-eval-case` | `github.com/ruinosus/dna/eval/v1` |
| [EvalRun](record.md#evalrun) | `eval-eval-run` | `github.com/ruinosus/dna/eval/v1` |
| [EvalSuite](record.md#evalsuite) | `eval-eval-suite` | `github.com/ruinosus/dna/eval/v1` |
| [Evidence](record.md#evidence) | `evidence-evidence` | `github.com/ruinosus/dna/evidence/v1` |
| [Feature](record.md#feature) | `sdlc-feature` | `github.com/ruinosus/dna/sdlc/v1` |
| [Forecast](record.md#forecast) | `sdlc-forecast` | `github.com/ruinosus/dna/sdlc/v1` |
| [HtmlArtifact](record.md#htmlartifact) | `sdlc-html-artifact` | `github.com/ruinosus/dna/sdlc/v1` |
| [Initiative](record.md#initiative) | `sdlc-initiative` | `github.com/ruinosus/dna/sdlc/v1` |
| [Insight](record.md#insight) | `sdlc-insight` | `github.com/ruinosus/dna/sdlc/v1` |
| [Issue](record.md#issue) | `sdlc-issue` | `github.com/ruinosus/dna/sdlc/v1` |
| [Kaizen](record.md#kaizen) | `sdlc-kaizen` | `github.com/ruinosus/dna/sdlc/v1` |
| [LessonLearned](record.md#lessonlearned) | `sdlc-lesson-learned` | `github.com/ruinosus/dna/sdlc/v1` |
| [ModelProfile](record.md#modelprofile) | `modelreg-model-profile` | `github.com/ruinosus/dna/modelreg/v1` |
| [Narrative](record.md#narrative) | `sdlc-narrative` | `github.com/ruinosus/dna/sdlc/v1` |
| [PatternInsight](record.md#patterninsight) | `cognitive-pattern-insight` | `github.com/ruinosus/dna/cognitive/v1` |
| [Plan](record.md#plan) | `sdlc-plan` | `github.com/ruinosus/dna/sdlc/v1` |
| [Postmortem](record.md#postmortem) | `sdlc-postmortem` | `github.com/ruinosus/dna/sdlc/v1` |
| [PreMortem](record.md#premortem) | `cognitive-pre-mortem` | `github.com/ruinosus/dna/cognitive/v1` |
| [PromptTemplate](record.md#prompttemplate) | `sdlc-prompt-template` | `github.com/ruinosus/dna/sdlc/v1` |
| [Reference](record.md#reference) | `sdlc-reference` | `github.com/ruinosus/dna/sdlc/v1` |
| [Retrospective](record.md#retrospective) | `sdlc-retrospective` | `github.com/ruinosus/dna/sdlc/v1` |
| [RiskRegister](record.md#riskregister) | `sdlc-risk-register` | `github.com/ruinosus/dna/sdlc/v1` |
| [Roadmap](record.md#roadmap) | `sdlc-roadmap` | `github.com/ruinosus/dna/sdlc/v1` |
| [SavedView](record.md#savedview) | `sdlc-saved-view` | `github.com/ruinosus/dna/sdlc/v1` |
| [Spec](record.md#spec) | `sdlc-spec` | `github.com/ruinosus/dna/sdlc/v1` |
| [Spike](record.md#spike) | `sdlc-spike` | `github.com/ruinosus/dna/sdlc/v1` |
| [StatusReport](record.md#statusreport) | `sdlc-status-report` | `github.com/ruinosus/dna/sdlc/v1` |
| [Story](record.md#story) | `sdlc-story` | `github.com/ruinosus/dna/sdlc/v1` |
| [SynthesisRun](record.md#synthesisrun) | `sdlc-synthesis-run` | `github.com/ruinosus/dna/sdlc/v1` |
| [SynthesizerState](record.md#synthesizerstate) | `sdlc-synthesizer-state` | `github.com/ruinosus/dna/sdlc/v1` |
| [Task](record.md#task) | `sdlc-task` | `github.com/ruinosus/dna/sdlc/v1` |
| [Tool](record.md#tool) | `helix-tool` | `github.com/ruinosus/dna/v1` |
| [WorkflowEvent](record.md#workflowevent) | `sdlc-workflow-event` | `github.com/ruinosus/dna/sdlc/v1` |

