/**
 * DNA SDK v3 — TypeScript entry point.
 *
 * Re-exports the microkernel (5-port architecture), adapters, and extensions.
 */

// Kernel
export { Kernel } from "./kernel/index.js";
export { Runtime } from "./kernel/runtime.js";
export { ManifestInstance } from "./kernel/instance.js";
export { materialize } from "./kernel/templates.js";
export type { Template, MaterializeOptions, OnConflict } from "./kernel/templates.js";
export type { PreviewBlock } from "./kernel/preview.js";
export { Document } from "./kernel/document.js";
export { Resource, type ResourceDep } from "./kernel/resource.js";
export { PromptBuilder } from "./kernel/prompt-builder.js";
export { CompositionEngine } from "./kernel/composition-resolver.js";
// Composition Engine V2 resolver module (twin of kernel/resolver.py).
export {
  BOOTSTRAP_KINDS,
  DEFAULT_NON_INHERITABLE_KINDS_V1,
  DEFAULT_INHERITABLE_KINDS_V1,
  MAX_RESOLUTION_DEPTH,
  ResolutionLayer,
  ResolutionPath,
  ResolvedDocument,
  mergeOverrideFull,
  mergeFieldLevel,
  type Contribution,
  // i-005 — Raw is the payload half of the exported Contribution tuple;
  // exporting it makes the public type self-describing (TypeDoc xref).
  type Raw,
} from "./kernel/resolver.js";
// Composition Engine V2 orchestration (twin of kernel/composition_resolver.py).
export { CompositionResolver } from "./kernel/composition-resolver.js";
export { Navigator } from "./kernel/navigator.js";
export {
  StudioUIMetadata,
  UI_METADATA_FIELDS,
  type ModeId,
  type UIAction,
  type LabelI18n,
  type UIMetadataField,
  type StudioUIMetadataInit,
} from "./kernel/studio_ui.js";
export { LockManager } from "./kernel/lock-manager.js";
export { ReportBuilder } from "./kernel/reports.js";
export { serializeRawToFiles } from "./kernel/serialize-to-files.js";

// Viz — diagram generators, health, matrix, ASCII tree
export * from "./viz/index.js";

// Opinionated bootstrap — extension wiring lives here, not in kernel/
export { createKernelWithBuiltins, quickInstance, createRuntimeWithBuiltins, quickManifest } from "./bootstrap.js";
export { HookRegistry, KNOWN_HOOK_NAMES } from "./kernel/hooks.js";
export type {
  HookContext,
  HookName,
  HookNameArg,
  Middleware,
  EventHandler,
  PreSaveContext,
  VetoHandler,
} from "./kernel/hooks.js";
export type {
  SourcePort,
  CachePort,
  ResolverPort,
  ReaderPort,
  WriterPort,
  KindPort,
  KindPresentation,
  Extension,
  ExtensionHost,
  CompositionResult,
  CacheItem,
  ResolvedItem,
  StorageDescriptor,
  StoragePattern,
  BodyMode,
  SerializedFile,
  SerializedDocument,
  WritableSourcePort,
  // Two-planes F2 — record-plane query surface
  QueryFilter,
  QueryOrder,
  CountResult,
  SourceQueryOpts,
  SourceCountOpts,
  RecordStorePort,
  RecordSearchProvider,
  // rec-embedding-port — text→dense-vector, sibling to RecordSearchProvider
  EmbeddingPort,
  // Tool port (s-dna-port-surface-parity — TS twin of the Py ToolPort)
  ToolPort,
} from "./kernel/protocols.js";
// i-005 — types REFERENCED by already-exported public API, previously
// broken xrefs in TypeDoc. Each is public surface a consumer needs to name:
//   TenantScope        — DeclarativeKindPort.scope (tenancy is a first-class
//                        kernel dimension; the Py twin exports it publicly)
//   PreviewResult      — return type of Kernel.previewDocument
//   PreviewBlockKind   — field type of the exported PreviewBlock
//   BuildPromptOpts    — opts of the blessed ManifestInstance.buildPrompt
//   SourceCapabilities — fixture-tracked port (port-surface-parity.json)
//   KindLike           — Resource.kindRef contract
//   AsyncEventHandler  — accepted by HookRegistry.on (sibling of EventHandler)
//   CompositionProfile — returned by ManifestInstance.profileFor, registered
//                        via the kernel's composition-profile registry
//   BundleHandle       — ReaderPort.detect/read param; readers/writers are a
//                        documented extension point (the Py twin re-exports
//                        it from dna.kernel.protocols for typing too)
//   LayerSource        — param of the exported DefaultLayerResolver.resolve
// None of these adds a ManifestInstance member or a port member, so the
// blessed_query_surface / port-surface fixtures are unaffected (type-only
// re-exports). Internals stay unexported via typedoc.json
// `intentionallyNotExported` (CompositionResolverHost, QueryableInstance,
// ManifestInstanceOpts, DeclarativeMarker).
export { TenantScope } from "./kernel/protocols.js";
export type { PreviewResult } from "./kernel/index.js";
export type { PreviewBlockKind } from "./kernel/preview.js";
export type { BuildPromptOpts } from "./kernel/instance.js";
export type { SourceCapabilities } from "./kernel/capabilities.js";
// … second-order xrefs: CompositionSlot is the element type of
// CompositionProfile.slots; sourceCapabilities/deriveCapabilities are the
// documented way a custom-source author obtains a SourceCapabilities.
export type {
  CompositionSlot,
  // the declarative viz-hint halves of the slot contract
  HealthCheckHint,
  QuadrantHint,
  TimelineHint,
} from "./kernel/composition-resolver.js";
export { sourceCapabilities, deriveCapabilities } from "./kernel/capabilities.js";
export type { KindLike } from "./kernel/resource.js";
export type { AsyncEventHandler } from "./kernel/hooks.js";
export type { CompositionProfile } from "./kernel/composition-resolver.js";
export type { BundleHandle } from "./kernel/bundle-handle.js";
export type { LayerSource } from "./kernel/layer-resolver.js";
export { ToolDefinition } from "./kernel/protocols.js";
// rec-embedding-port — zero-dep deterministic embedding floor (the default).
export {
  FakeEmbeddingProvider,
  fakeEmbedOne,
  FAKE_EMBEDDING_DIMS,
  FAKE_EMBEDDING_MODEL_ID,
} from "./kernel/embedding.js";
export {
  ToolRegistry,
  READ_UMBRELLA_GROUPS,
  expandGroupAliases,
} from "./kernel/tool-registry.js";
// Port-surface parity manifest (keyof-bound; see port-surface.ts)
export { PORT_SURFACE } from "./kernel/port-surface.js";
export {
  LayerPolicy,
  LayerPolicyViolationError,
  ResolveError,
  ResolveNotFoundError,
  ResolveAuthError,
  ResolveNetworkError,
  SD,
  // Two-planes F2 — pure helpers (shared by the FS adapter + parity fixture)
  QueryError,
  QUERY_OPS,
  resolveFieldPath,
  matchFilter,
  applyOrderBy,
  queryDocs,
  countDocs,
} from "./kernel/protocols.js";
export { documentHash } from "./kernel/lock.js";
export {
  readSpecString,
  readSpecStringArray,
  readSpecRecord,
  readSpecRecordArray,
} from "./kernel/spec-access.js";
export type { LockEntry, Lockfile } from "./kernel/lock.js";
export type { FSLike } from "./kernel/fs.js";
export { nodeFS, createMemoryFS } from "./kernel/fs.js";
export {
  MetadataSchema,
  GenomeSchema,
  LayerPolicySchema,
  AgentSchema,
  ActorSchema,
  UseCaseSchema,
  SkillSchema,
  SoulSchema,
  AgentDefinitionSchema,
  HookSchema,
  HookSpecSchema,
  SafetyPolicySchema,
  SafetyPolicySpecSchema,
  SafetyRuleSchema,
  RecognizerSchema,
  RecognizerSpecSchema,
  RecognizerPatternSchema,
} from "./kernel/models.js";

// Adapters
export { FilesystemSource } from "./adapters/filesystem/source.js";
export { FilesystemCache } from "./adapters/filesystem/cache.js";
export { LocalResolver } from "./adapters/resolvers/local.js";

// Extensions
export { HelixExtension } from "./extensions/helix.js";
export { AgentSkillsExtension } from "./extensions/agentskills.js";
export { SoulSpecExtension } from "./extensions/soulspec.js";
export { AgentsMdExtension } from "./extensions/agentsmd.js";
export { GuardrailExtension } from "./extensions/guardrails.js";
export { HookExtension } from "./extensions/hooks.js";
export { SafetyPolicyExtension } from "./extensions/safety.js";
export { RecognizerExtension } from "./extensions/recognizer.js";
export { KindDefinitionExtension, KindDefinitionReader, KindDefinitionWriter } from "./extensions/kinddef.js";
export { EvidenceExtension, shouldCapture } from "./extensions/evidence.js";
export { DocExtension } from "./extensions/doc.js";
export { ResearchExtension } from "./extensions/research.js";
export { CollabExtension } from "./extensions/collab.js";
// s-export-unwired-ts-extensions — these 9 had an *Extension class but were
// never exported (external consumers couldn't import them) and 3 of them
// (Community/Research/Sdlc) were loaded by no bootstrap at all. See bootstrap.ts.
export { FederationExtension } from "./extensions/federation.js";
export { SdlcExtension } from "./extensions/sdlc.js";
// s-tier-a-modelprofile — ModelProfile registry + the prompt-budget
// machinery its write guard runs on (consumers need the error class to
// catch the veto; never hardcode token caps — read the ModelProfile).
export { ModelRegExtension } from "./extensions/modelreg.js";
// s-tier-a-automation — the Automation Kind (declare-in-data, host
// executes). Hosts import the query helpers to list what to run and the
// cron validator to pre-check expressions in their own surfaces.
export { AutomationExtension } from "./extensions/automation.js";
export { EvalExtension } from "./extensions/eval.js";
export {
  automationsFor,
  triggerKey,
  TRIGGER_TYPES,
} from "./extensions/automation/query.js";
export type { TriggerType } from "./extensions/automation/query.js";
export {
  validateCronExpression,
  automationTriggerGuard,
} from "./extensions/automation/write-guards.js";
export {
  CHARS_PER_TOKEN,
  estimateTokens,
  evaluateInstructionBudget,
  PromptBudgetExceededError,
} from "./kernel/prompt-budget.js";
export type { BudgetVerdict } from "./kernel/prompt-budget.js";
export { DeclarativeKindPort, storageDictToDescriptor } from "./kernel/meta.js";
export { KindDefinitionSchema, KindDefinitionSpecSchema, KIND_DEFINITION_API_VERSION, KIND_DEFINITION_KIND } from "./kernel/models.js";
export type { TypedKindDefinition } from "./kernel/models.js";
export { DefaultLayerResolver, deepMerge } from "./kernel/layer-resolver.js";
