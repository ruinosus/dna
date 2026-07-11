# Python ↔ TypeScript parity matrix

!!! info "Generated — not hand-kept"

    This page is **generated** by `scripts/gen_parity_matrix.py` from the same fixtures that the CI parity suites enforce
    (`tests/parity-fixtures/port-surface-parity.json` and `packages/sdk-ts/kind-registry-parity.json`). The docs build regenerates it,
    so the published matrix and the enforced contract cannot drift. Do not edit it by hand.

DNA ships a Python SDK and a TypeScript SDK that are **behaviorally identical**. This matrix is the published proof — in the spirit of the OpenTelemetry spec-compliance matrix, it lists each contract member as a row and each language as a column, so "1:1 parity" is *shown*, not asserted.

**Legend**

- ✅ — implemented on this side.
- ⚠️ — intentionally absent on this side; the asymmetry is documented (see the Notes column). Undocumented drift reds the parity suite in CI.
- ➖ — not applicable / shaped differently by design.

**Summary:** **152** shared members across the tracked contracts, **39** documented asymmetries. Python is the semantic reference: a gap is closed by porting to TypeScript, or justified in the fixture — never by silence.

## Ports — the microkernel contract

Each port is a `typing.Protocol` (Python) / `interface` (TypeScript). Rows are the contract members; a ✅ in both columns means the twin exists (Python members are `snake_case`, their TypeScript twins `camelCase`). The Python suite introspects the real Protocol members; the TypeScript suite is `keyof`-bound to the real interfaces, so `tsc` fails on drift.

### `SourcePort`

WHERE — load documents from storage. Py: dna/kernel/protocols.py · TS: src/kernel/protocols.ts

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `supports_readers` | ✅ | ✅ |  |
| `load_bootstrap_docs` | ✅ | ✅ |  |
| `load_all` | ✅ | ✅ |  |
| `resolve_ref` | ✅ | ✅ |  |
| `load_layer` | ✅ | ✅ |  |
| `close` | ✅ | ✅ | ℹ️ Py lists close in SOURCE_PORT_CORE_MEMBERS (boot gate); TS declares it optional — the kernel treats a missing close as a no-op. FS adapters implement a documented no-op; the SQL adapters end what they own (Py SqlAlchemySource disposes its engine; TS raw PostgresSource closes its pool). |
| `list_doc_refs` | ✅ | ✅ | ℹ️ L1 granular read, capability-mediated on both sides (SourceCapabilities.granular_list / granularList). |
| `load_one` | ✅ | ✅ |  |
| `query` | ✅ | ✅ |  |
| `count` | ✅ | ✅ |  |
| `capabilities` | ⚠️ | ✅ | TS declares capabilities() on the READ port so read-only adapters (FilesystemSource TS has no write half) can declare explicitly; Py declares it on WritableSourcePort because every in-repo Py adapter is writable. Same contract, different attachment point — see the WritableSourcePort py-only twin entry. |

### `WritableSourcePort`

SourcePort + write/versioning half. OWN members only (inherited SourcePort members are tracked above).

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `save_document` | ✅ | ✅ |  |
| `delete_document` | ✅ | ✅ |  |
| `list_versions` | ✅ | ✅ |  |
| `get_version` | ✅ | ✅ |  |
| `publish` | ✅ | ✅ | ℹ️ PG TS is a documented single-step no-op (no draft state); the member exists so Draftable-style flows type-check. |
| `save_manifest` | ✅ | ⚠️ | Py-only: whole-manifest persistence backs the Py scope-seed/sync machinery (source_sync, dna doc apply). The TS SDK has no manifest-write pipeline — adding the member without the machinery would be a lying surface. |
| `load_drafts` | ✅ | ⚠️ | Py-only: the draft→publish lifecycle (Draftable capability) exists only in the Py adapters. TS adapters declare drafts:false in SourceCapabilities; PG TS publish() is a documented single-step no-op. |
| `list_scopes` | ✅ | ⚠️ | Py-only: consumed by the Catalog tier scan and scope enumeration endpoints (kinds-api), which are Py-only runtime surfaces. No TS consumer exists (composition parity case 10 is skip_ts for the same reason). |
| `capabilities` | ✅ | ⚠️ | Cross-attachment twin of the SourcePort ts-only `capabilities` entry: TS declares capabilities() on SourcePort (read-only adapters declare too); Py declares it here. One contract, tracked once per side. |

### `CachePort`

WHERE — store/retrieve installed deps.

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `load_all` | ✅ | ✅ |  |
| `load_key` | ✅ | ✅ |  |
| `store` | ✅ | ✅ |  |
| `has` | ✅ | ✅ |  |

### `ResolverPort`

FROM — fetch external deps.

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `resolve` | ✅ | ✅ |  |
| `cache_key` | ✅ | ✅ |  |

### `ReaderPort`

Reads a bundle and produces a raw dict.

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `detect` | ✅ | ✅ |  |
| `read` | ✅ | ✅ |  |
| `_owner_container` | ✅ | ✅ |  |

### `WriterPort`

Writes a raw dict back to a bundle. Inverse of ReaderPort.

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `can_write` | ✅ | ✅ |  |
| `write` | ✅ | ✅ |  |
| `serialize` | ✅ | ✅ |  |

### `KindPort`

WHO — identity + composition role.

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `api_version` | ✅ | ✅ |  |
| `kind` | ✅ | ✅ |  |
| `alias` | ✅ | ✅ |  |
| `origin` | ✅ | ✅ |  |
| `storage` | ✅ | ✅ |  |
| `is_root` | ✅ | ✅ |  |
| `is_prompt_target` | ✅ | ✅ |  |
| `prompt_target_priority` | ✅ | ✅ |  |
| `flatten_in_context` | ✅ | ✅ |  |
| `is_runtime_artifact` | ✅ | ✅ |  |
| `dep_filters` | ✅ | ✅ |  |
| `dependencies` | ✅ | ✅ |  |
| `schema` | ✅ | ✅ |  |
| `get_default_agent_name` | ✅ | ✅ |  |
| `get_layer_policies` | ✅ | ✅ |  |
| `parse` | ✅ | ✅ |  |
| `describe` | ✅ | ✅ |  |
| `summary` | ✅ | ✅ |  |
| `prompt_template` | ✅ | ✅ |  |
| `model` | ✅ | ⚠️ | Py-only: the Pydantic model class attribute drives Py's parse/validation. TS kinds hold their Zod schema internally and expose it via schema() — a `model` member would have no uniform TS meaning. |
| `scope` | ⚠️ | ✅ | TenantScope declaration. Py documents it as an optional duck-typed attr (kernel getattr's it; kept off the Protocol so isinstance stays permissive for third-party Kinds); TS interfaces express optional members natively. |
| `docs` | ⚠️ | ✅ | KindPresentation slice member — TS KindPort extends KindPresentation (keyof includes it, so the exhaustive manifest lists it here too); the Py twin lives on the KindPresentation capability Protocol, kept OFF the runtime_checkable KindPort so the H1 isinstance gate never requires it. Tracked as a py↔ts pair in the KindPresentation port below. |
| `isSchemaAffecting` | ⚠️ | ✅ | Kernel classification attr (s-kernel-kindport-classification-attrs). Py derives via getattr with defaults off KindBase; TS declares the optional member on the interface. |
| `isOverlayable` | ⚠️ | ✅ | Same classification-attrs rationale as isSchemaAffecting. |
| `scopeInheritable` | ⚠️ | ✅ | Same classification-attrs rationale as isSchemaAffecting. |
| `plane` | ⚠️ | ✅ | Two-planes marker (record\|composition). Py reads it duck-typed off descriptors/KindBase; TS declares the optional member. |
| `preview` | ⚠️ | ✅ | KindPresentation slice member — see the docs entry above; paired in the KindPresentation port below. |
| `graphStyle` | ⚠️ | ✅ | KindPresentation slice member — see the docs entry above; paired in the KindPresentation port below. |
| `asciiIcon` | ⚠️ | ✅ | KindPresentation slice member — see the docs entry above; paired in the KindPresentation port below. |
| `displayLabel` | ⚠️ | ✅ | KindPresentation slice member — see the docs entry above; paired in the KindPresentation port below. |
| `graphMeta` | ⚠️ | ✅ | KindPresentation slice member — see the docs entry above; paired in the KindPresentation port below. |
| `uiSchema` | ⚠️ | ✅ | KindPresentation slice member — see the docs entry above; paired in the KindPresentation port below. |
| `descriptionFallbackField` | ⚠️ | ✅ | KindPresentation slice member — see the docs entry above; paired in the KindPresentation port below. |
| `visibleInBackend` | ⚠️ | ✅ | KindPresentation slice member (was read via `(kp as any).visibleInBackend` before s-dna-kindport-descriptor-schema declared it) — see the docs entry above; paired in the KindPresentation port below. |

### `KindPresentation`

Optional presentation/UX capability of a Kind (s-dna-kindport-descriptor-schema). Py: typing-only capability Protocol (NOT runtime_checkable, NOT part of KindPort — the H1 isinstance gate must never require these; the is_runtime_artifact precedent). TS: interface that KindPort extends (native optional members). Every member is optional at runtime; KindBase carries the attribute defaults; consumers use typed access with a default (getattr(kp, name, None) / kp.member?.).

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `docs` | ✅ | ✅ |  |
| `description_fallback_field` | ✅ | ✅ |  |
| `ui_schema` | ✅ | ✅ |  |
| `graph_style` | ✅ | ✅ |  |
| `ascii_icon` | ✅ | ✅ |  |
| `display_label` | ✅ | ✅ |  |
| `visible_in_backend` | ✅ | ✅ |  |
| `preview` | ✅ | ✅ |  |
| `graph_meta` | ✅ | ✅ |  |

### `ToolPort`

An invocable tool exposed to agents + DNA discovery metadata (s-dna-tool-decorator; TS twin landed with s-dna-port-surface-parity).

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `name` | ✅ | ✅ |  |
| `group` | ✅ | ✅ |  |
| `description` | ✅ | ✅ |  |
| `summary` | ✅ | ✅ |  |
| `args_schema` | ✅ | ✅ |  |
| `hitl` | ✅ | ✅ |  |
| `scope` | ✅ | ✅ |  |
| `source` | ✅ | ✅ |  |
| `get_callable` | ✅ | ✅ |  |

### `ExtensionHost`

The registration-time surface the Kernel offers to Extension.register() (s-dna-extension-host-contract).

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `hooks` | ✅ | ✅ |  |
| `kind` | ✅ | ✅ |  |
| `kind_from_descriptor` | ✅ | ✅ |  |
| `reader` | ✅ | ✅ |  |
| `writer` | ✅ | ✅ |  |
| `on` | ✅ | ✅ |  |
| `on_veto` | ✅ | ✅ |  |
| `tool` | ✅ | ✅ |  |
| `composition_profile` | ✅ | ✅ |  |

### `Extension`

Registers kinds, readers, and writers on the Kernel.

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `name` | ✅ | ✅ |  |
| `version` | ✅ | ✅ |  |
| `register` | ✅ | ✅ |  |
| `templates` | ⚠️ | ✅ | Py keeps templates() OFF the Extension Protocol (separate TemplateProvider Protocol, feature-tested) so legacy pre-Phase-0 extensions keep satisfying isinstance(ext, Extension); TS expresses the same back-compat with a native optional member. See the TemplateProvider py-only port. |

### `TemplateProvider`

Optional Extension capability — ships scaffold file trees. Py-only Protocol; TS folds the member into Extension.templates?.

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `templates` | ✅ | ⚠️ | TS has no separate TemplateProvider interface: the optional Extension.templates? member IS the TS twin (tracked in the Extension port above). A second interface would add nothing in a structurally-typed language. |

### `RecordSearchProvider`

Two-planes F2 — semantic search over record docs, registered on the kernel at app boot.

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `search` | ✅ | ✅ |  |

### `EmbeddingPort`

rec-embedding-port — text→dense-vector, sibling to RecordSearchProvider. Fake floor is zero-dep + bit-exact Py↔TS; ONNX all-MiniLM-L6-v2 is an opt-in extra. Py: dna/kernel/protocols.py · TS: src/kernel/protocols.ts

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `model_id` | ✅ | ✅ |  |
| `dims` | ✅ | ✅ |  |
| `embed` | ✅ | ✅ |  |

### `SourceCapabilities`

Typed declaration of what a source adapter supports (s-sourceport-contract-cleanup). Members are dataclass fields (Py) / interface keys (TS).

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `source` | ✅ | ✅ |  |
| `drafts` | ✅ | ✅ |  |
| `versions` | ✅ | ✅ |  |
| `layers` | ✅ | ✅ |  |
| `bundle_read` | ✅ | ✅ |  |
| `bundle_write` | ✅ | ✅ |  |
| `kernel_attachable` | ✅ | ✅ |  |
| `granular_list` | ✅ | ✅ |  |
| `granular_one` | ✅ | ✅ |  |
| `query_pushdown` | ✅ | ✅ |  |
| `tenant_layer_writes` | ✅ | ⚠️ | Python-signature concept: optional kwargs must be probed via inspect.signature, so Py declares which write kwargs an adapter accepts. The TS write surface is an options bag — nothing to probe (already documented in capabilities.ts). |
| `write_kwargs` | ✅ | ⚠️ | Same rationale as tenant_layer_writes — Py kwarg vocabulary declaration; meaningless in TS. |
| `delete_kwargs` | ✅ | ⚠️ | Same rationale as tenant_layer_writes — Py kwarg vocabulary declaration; meaningless in TS. |

### `CapabilityProtocols`

Exported optional-capability Protocols (Py capabilities.py) / interfaces (TS capabilities.ts). Members here are the PROTOCOL NAMES, not method names.

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `BundleEntryReadable` | ✅ | ✅ |  |
| `KernelAttachable` | ✅ | ✅ |  |
| `Versionable` | ✅ | ✅ |  |
| `BundleEntryWritable` | ✅ | ⚠️ | Py-only: no TS adapter has a bundle-WRITE path (every TS SourceCapabilities declares bundleWrite:false). The interface lands together with the first TS bundle-write implementation, not before. |
| `Draftable` | ✅ | ⚠️ | Py-only: the draft store exists only in Py adapters (see WritableSourcePort.load_drafts justification). |
| `Layered` | ✅ | ⚠️ | Py-only: granular per-doc load_layer(scope, layer, kind, name) resolution consumed by the Py harness overlay reads; the TS SourcePort.loadLayer (whole-layer) covers the TS composition engine's needs. |
| `TenantAware` | ✅ | ⚠️ | Documentation/static-typing Protocol for Python's kwarg-level write contract — TS options-bag writes need no kwarg protocol (same rationale as SourceCapabilities.write_kwargs). |
| `LayerAware` | ✅ | ⚠️ | Same rationale as TenantAware. |

## Blessed query surface — the public read API

The `blessed` members are the ONE documented way to read manifest data; `deprecated` members still work but warn and are removed in 1.0. Adding, renaming or removing any public member without editing the fixture reds the suite.

### `ManifestInstance` — blessed

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `documents` | ✅ | ✅ | ℹ️ canonical in-memory read — filter/find by d.kind / d.name; what QUICK-START, READMEs and examples teach |
| `root` | ✅ | ✅ |  |
| `default_agent` | ✅ | ✅ |  |
| `find_agent` | ✅ | ✅ |  |
| `build_prompt` | ✅ | ✅ |  |
| `build_prompt_async` | ✅ | ⚠️ | Py sync/async split — TS buildPrompt is already async; Py needs an explicit async twin so event-loop callers keep pool-based sources loop-bound. |
| `resolve` | ✅ | ✅ |  |
| `resolve_async` | ✅ | ⚠️ | Py sync/async split — TS resolve is sync over in-memory layers; the Py async twin exists for the same loop-binding reason as build_prompt_async. |
| `all_async` | ✅ | ⚠️ | Py-only async bridge returning parsed Documents — record-plane, tenant and inheritance aware. TS has no lazy/record MI split; TS callers use mi.documents or kernel.query. |
| `one_async` | ✅ | ⚠️ | single-doc twin of all_async — delegates to kernel.get_document (L2-cached). |

### `ManifestInstance` — deprecated (removed in 1.0)

| Member | Python | TypeScript | Replacement |
|---|:---:|:---:|---|
| `all` | ✅ | ✅ | mi.documents (filter by d.kind) or kernel.query(scope, kind) |
| `one` | ✅ | ✅ | mi.documents (find by d.kind + d.name); Py also kernel.get_document(scope, kind, name), TS kernel.query with a filter |

The exact public `ManifestInstance` surface is pinned member-for-member by the fixture: **55 Python** members and **55 TypeScript** members. Any public addition/removal/rename on either side without a matching fixture edit reds the suite.

### `Kernel` — blessed

| Member | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `instance` | ✅ | ✅ | ℹ️ entry point — loads/returns the scope's ManifestInstance |
| `instance_async` | ✅ | ⚠️ | Py sync/async split — TS instance() is already async. |
| `query` | ✅ | ✅ | ℹ️ indexed / record-plane read — push-down to the source, raw rows |
| `count` | ✅ | ✅ | ℹ️ aggregation twin of query |
| `get_document` | ✅ | ⚠️ | TS kernel has no getDocument — TS single-doc reads go through mi.documents or kernel.query with a filter; port when a TS caller needs the L2-cached single-doc read. |
| `query_list_sync` | ✅ | ⚠️ | Py-only loop-safety wrapper returning parsed Documents for sync callers (CLI, workers). TS is async-native — no sync bridge needed. |
| `get_document_sync` | ✅ | ⚠️ | single-doc twin of query_list_sync. |

## Hook names — the shared event vocabulary

The `HookRegistry` hook-name vocabulary is identical on both sides (event names are wire vocabulary, not API casing).

| Hook | Python | TypeScript |
|---|:---:|:---:|
| `pre_build_prompt` | ✅ | ✅ |
| `post_build_prompt` | ✅ | ✅ |
| `pre_save` | ✅ | ✅ |
| `post_save` | ✅ | ✅ |
| `post_delete` | ✅ | ✅ |
| `kinddef_conflict` | ✅ | ✅ |
| `parse_error` | ✅ | ✅ |
| `extension_error` | ✅ | ✅ |

## Kind registry — class-backed Kinds

Class-backed builtin Kinds registered on both runtimes. **Descriptor-backed Kinds** (`*/kinds/*.kind.yaml`, byte-identical Py↔TS package data) are byte-parity by construction and deliberately absent from this list — they cannot drift. `py_only_allowlist` Kinds are registered in Python (entry-points) and intentionally not yet ported to TypeScript.

| Kind (alias) | Python | TypeScript | Notes |
|---|:---:|:---:|---|
| `agentskills-skill` | ✅ | ✅ | |
| `agentsmd-agent` | ✅ | ✅ | |
| `audit-userroleassignment` | ✅ | ✅ | |
| `evidence-policy` | ✅ | ✅ | |
| `federation-mcp` | ✅ | ✅ | |
| `guardrails-guardrail` | ✅ | ✅ | |
| `helix-actor` | ✅ | ✅ | |
| `helix-agent` | ✅ | ✅ | |
| `helix-canvas` | ✅ | ✅ | |
| `helix-genome` | ✅ | ✅ | |
| `helix-hook` | ✅ | ✅ | |
| `helix-safety-policy` | ✅ | ✅ | |
| `helix-setting` | ✅ | ✅ | |
| `helix-theme` | ✅ | ✅ | |
| `helix-usecase` | ✅ | ✅ | |
| `helix-user-profile` | ✅ | ✅ | |
| `kinddef-kinddefinition` | ✅ | ✅ | |
| `lesson-lesson` | ✅ | ✅ | |
| `policy-layer-policy` | ✅ | ✅ | |
| `presidio-recognizer` | ✅ | ✅ | |
| `research-research` | ✅ | ✅ | |
| `sdlc-agent-session` | ✅ | ✅ | |
| `sdlc-bug` | ✅ | ✅ | |
| `sdlc-epic` | ✅ | ✅ | |
| `sdlc-feature` | ✅ | ✅ | |
| `sdlc-html-artifact` | ✅ | ✅ | |
| `sdlc-initiative` | ✅ | ✅ | |
| `sdlc-issue` | ✅ | ✅ | |
| `sdlc-plan` | ✅ | ✅ | |
| `sdlc-reference` | ✅ | ✅ | |
| `sdlc-roadmap` | ✅ | ✅ | |
| `sdlc-spec` | ✅ | ✅ | |
| `sdlc-spike` | ✅ | ✅ | |
| `sdlc-story` | ✅ | ✅ | |
| `sdlc-task` | ✅ | ✅ | |
| `soulspec-soul` | ✅ | ✅ | |
| `tenant-membership` | ✅ | ✅ | |
| `tenant-tenant` | ✅ | ✅ | |
| `testkit-test-guide` | ✅ | ✅ | |
| `testkit-test-run` | ✅ | ✅ | |
| `collab-comment` | ✅ | ⚠️ | Python-only (entry-point registered); documented in the registry allowlist, not yet ported to TypeScript. |

## Excluded surfaces — deliberately not parity-tracked

Surfaces where member parity is intentionally NOT enforced, each with a recorded reason. `➖` marks the side where the surface is absent or shaped differently on purpose.

| Surface | Python | TypeScript | Reason |
|---|:---:|:---:|---|
| `collaborator-ports` | ✅ | ✅ | Kernel INTERNALS, not public contract: these are the narrow mediator slices from the kernel-decomposition epic (e-kernel-decomposition). Each language decomposed its own god-object along its own seams (Py ~15 slices, TS 3) — forcing member parity here would couple internal refactors across languages for zero user-facing value. |
| `dna_tool-decorator` | ✅ | ➖ | The @dna_tool decorator + pending-tools harvest is langchain glue (wraps langchain_core.tools.tool for langgraph/deepagents). The TS SDK has no langchain runtime; the portable part — ToolPort/ToolDefinition + ToolRegistry + kernel.tool()/getTools() and the read-umbrella group aliases — IS ported and surface-tracked above. |

## Behavioral proof — the conformance kit

This matrix proves the two SDKs expose the **same surface**. That they **behave** the same is proven separately by the `dna.testing` conformance kits — source and reader/writer conformance suites that run the identical scenarios against both runtimes. See [Running the conformance kit](../getting-started/conformance-kit.md), and the guides on [reading document data](../guides/read-document-data.md) and [writing a source adapter](../guides/write-a-source-adapter.md) for the contracts these tables enforce.
