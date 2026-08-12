# The port catalogue

DNA's kernel is a **microkernel**: it knows how to store, validate, version and compose instances, and nothing else. Everything else is a `typing.Protocol` — a **port** — that something outside the core satisfies. There are **60** of them.

Most of this page exists to answer one question: *I want to change X — what do I implement?* **38** of the 60 are things you are meant to implement. The rest are listed anyway, marked as what they are, because a seam you cannot see is indistinguishable from a seam that does not exist — and guessing wrong costs more than being told no.

## What the three roles mean

| Role | Meaning |
| --- | --- |
| :material-power-plug: **extension point** | You implement it. A third party can ship one without touching the kernel. |
| :material-hand-extended: handed to you | The kernel implements it and passes it in. You call it; you never satisfy it. |
| :material-lock: internal seam | A back-reference between the kernel and one of its own collaborators, published as a Protocol so the decomposition stays honest and testable. Not a plug-in surface. |

## All 60 ports

### Storage & retrieval — where instances live (10)

The ports the kernel uses to answer *where is this, and how do I get it back*. This is the plane with the most shipped adapters and the only one with a full conformance battery, so it is also the best documented place to start if you are writing your first port.

| Port | Module | Role | What it decides | Shipped |
| --- | --- | --- | --- | --- |
| [BundleHandle](storage.md#bundlehandle) | `dna.kernel.bundle.handle` | extension point | Reading and writing one bundle's files | 2 |
| [CachePort](storage.md#cacheport) | `dna.kernel.protocols` | extension point | Where installed dependencies are cached | 1 |
| [EmbeddingPort](storage.md#embeddingport) | `dna.kernel.protocols` | extension point | Turning text into vectors | 2 |
| [KernelEventBus](storage.md#kerneleventbus) | `dna.kernel.boot.eventbus` | extension point | Cross-process cache invalidation | 1 |
| [ReaderPort](storage.md#readerport) | `dna.kernel.protocols` | extension point | How a bundle format is detected and parsed | 10 |
| [RecordSearchProvider](storage.md#recordsearchprovider) | `dna.kernel.protocols` | extension point | Semantic search over record-plane instances | 2 |
| [ResolverPort](storage.md#resolverport) | `dna.kernel.protocols` | extension point | How an external dependency is fetched | 5 |
| [SourcePort](storage.md#sourceport) | `dna.kernel.protocols` | extension point | Where instances are read from | 3 |
| [WritableSourcePort](storage.md#writablesourceport) | `dna.kernel.protocols` | extension point | …and how they are written back | 3 |
| [WriterPort](storage.md#writerport) | `dna.kernel.protocols` | extension point | …and how it is written back | 11 |

### Source capabilities — the optional slices (8)

A source adapter's **mandatory** contract is `WritableSourcePort`. Everything a store might additionally be able to do — keep versions, hold drafts, resolve overlays, store bundle entries — is a separate, opt-in Protocol here.

These exist so the kernel never has to ask `hasattr(source, ...)`. That matters more than it sounds: the kernel needs to know what your store *cannot* do **before** it reads, so a face can refuse honestly instead of serving a confident empty answer. Read [what your declaration turns on](capabilities.md#what-your-declaration-turns-on) before you implement any of them.

| Port | Module | Role | What it decides | Shipped |
| --- | --- | --- | --- | --- |
| [BundleEntryReadable](capabilities.md#bundleentryreadable) | `dna.kernel.capabilities` | extension point | Read one entry out of a bundle | — |
| [BundleEntryWritable](capabilities.md#bundleentrywritable) | `dna.kernel.capabilities` | extension point | Write or delete one entry in a bundle | — |
| [Draftable](capabilities.md#draftable) | `dna.kernel.capabilities` | extension point | Draft / publish lifecycle | — |
| [KernelAttachable](capabilities.md#kernelattachable) | `dna.kernel.capabilities` | extension point | Accept the kernel after construction | — |
| [LayerAware](capabilities.md#layeraware) | `dna.kernel.capabilities` | extension point | Writes accept a layer overlay | — |
| [Layered](capabilities.md#layered) | `dna.kernel.capabilities` | extension point | Overlay (tenant / layer) resolution | — |
| [TenantAware](capabilities.md#tenantaware) | `dna.kernel.capabilities` | extension point | Writes accept a first-class tenant | — |
| [Versionable](capabilities.md#versionable) | `dna.kernel.capabilities` | extension point | Per-Kind semver versioning | — |

### Kinds & extensions — what behaviour DNA knows about (7)

The kernel imports no extension. Every unit of identity and composition arrives through these ports, which is why adding a Kind never touches the core. (The kernel does NAME a small set of built-in Kinds in its own code — see Microkernel & ports for the measured extent and the guard that caps it.)

| Port | Module | Role | What it decides | Shipped |
| --- | --- | --- | --- | --- |
| [Extension](kinds.md#extension) | `dna.kernel.protocols` | extension point | A package of Kinds, readers, writers and hooks | 1 |
| [ExtensionHost](kinds.md#extensionhost) | `dna.kernel.protocols` | handed to you | The registration surface handed to an Extension | — |
| [KindPort](kinds.md#kindport) | `dna.kernel.protocols` | extension point | What a Kind is, and how it composes | 1 |
| [KindPresentation](kinds.md#kindpresentation) | `dna.kernel.protocols` | extension point | How a Kind previews and draws itself | — |
| [KindRelations](kinds.md#kindrelations) | `dna.kernel.protocols` | extension point | What a Kind points at | — |
| [TemplateProvider](kinds.md#templateprovider) | `dna.kernel.protocols` | extension point | Scaffold file trees shipped by an extension | 1 |
| [ToolPort](kinds.md#toolport) | `dna.kernel.protocols` | extension point | A tool an agent can invoke | — |

### Emit — materializing an agent into a runtime (2)

Where the storage ports face *inward*, these face **out**: the kernel composes a neutral agent, and an emitter turns it into the native artifact one specific runtime consumes. Author once, emit per runtime.

| Port | Module | Role | What it decides | Shipped |
| --- | --- | --- | --- | --- |
| [EmitterPort](emit.md#emitterport) | `dna.emit` | extension point | How a composed agent becomes a runtime's native artifact | 8 |
| [ScaffoldResolver](emit.md#scaffoldresolver) | `dna.emit.scaffold` | extension point | Where a scaffold template's source comes from | 1 |

### Runtime & threads — serving a live copilot (8)

Emitting produces a file. These ports produce a **running** agent, and the conversation state that outlives a single request. The thread ports are split along a real fault line — what the framework knows versus what only the host knows — and the split is the whole design.

| Port | Module | Role | What it decides | Shipped |
| --- | --- | --- | --- | --- |
| [AGUIApp](runtime.md#aguiapp) | `dna.runtime.port` | extension point | The mountable app a runtime adapter returns | — |
| [AgentHarnessPort](runtime.md#agentharnessport) | `dna.runtime.harness` | extension point | How a resolved agent runs inside a provider-owned SDK loop | 1 |
| [RuntimePort](runtime.md#runtimeport) | `dna.runtime.port` | extension point | How a composed agent becomes a *running* one | 2 |
| [ThreadIndexPort](runtime.md#threadindexport) | `dna.runtime.thread_store` | extension point | Whose conversation is this, and what are mine | 1 |
| [ThreadPurgePort](runtime.md#threadpurgeport) | `dna.runtime.thread_store` | extension point | Retention: find expired threads and drop them | 1 |
| [ThreadStorePort](runtime.md#threadstoreport) | `dna.runtime.thread_store` | extension point | The whole conversation contract | 1 |
| [ThreadTranscriptPort](runtime.md#threadtranscriptport) | `dna.runtime.thread_store` | extension point | Reading the messages of a conversation | 2 |
| [TranscriptPurgePort](runtime.md#transcriptpurgeport) | `dna.runtime.thread_store` | extension point | …and the half only the framework can delete | 1 |

### Judgement — where something decides (4)

Four seams where DNA deliberately declines to ship an opinion. Each is a place a model, a heuristic, or a human gets to be the authority — and DNA's position is that the authority is **yours to supply**, not ours to bundle.

| Port | Module | Role | What it decides | Shipped |
| --- | --- | --- | --- | --- |
| [Analyzer](judgement.md#analyzer) | `dna.extensions.intel.analyzer` | extension point | A pass over a source that proposes candidates | 2 |
| [ContradictionScribe](judgement.md#contradictionscribe) | `dna.memory.contradiction` | extension point | Deciding whether two memories actually contradict | — |
| [EvalTargetPort](judgement.md#evaltargetport) | `dna.extensions.eval.runner` | extension point | What an eval case is actually run against | 1 |
| [MergeScribe](judgement.md#mergescribe) | `dna.memory.merge` | extension point | Fusing two memories into one | — |

### Internal seams — not extension points (21)

These are Protocols, and they are not for you.

They exist because the kernel was decomposed into collaborators (instance builder, query engine, write pipeline, …) and each collaborator's back-reference to the kernel was published as a narrow, typed slice instead of passing the whole kernel around. That keeps the decomposition honest and testable — a collaborator can only reach what its slice names.

They are listed here for one reason: **invisible is worse than "this is not for you"**. If you go looking for the extension point and find twenty-two Protocols nobody explains, you cannot tell the seams from the scaffolding. Now you can. Implementing one of these means substituting a piece of the kernel for itself, which is a fork, not an extension.

| Port | Module | Role | What it decides | Shipped |
| --- | --- | --- | --- | --- |
| [BundleIOHost](internal.md#bundleiohost) | `dna.kernel.collaborator_ports` | internal seam | Everything bundle I/O needs | — |
| [CatalogCacheHost](internal.md#catalogcachehost) | `dna.kernel.collaborator_ports` | internal seam | Everything the catalog cache needs | — |
| [CompositionResolverHost](internal.md#compositionresolverhost) | `dna.kernel.collaborator_ports` | internal seam | Everything the composition resolver needs | — |
| [DocStore](internal.md#docstore) | `dna.kernel.collaborator_ports` | internal seam | The kernel's own instance-reading surface | — |
| [InheritanceCtx](internal.md#inheritancectx) | `dna.kernel.collaborator_ports` | internal seam | Scope inheritance and the resolution chain | — |
| [InstanceBuildCtx](internal.md#instancebuildctx) | `dna.kernel.collaborator_ports` | internal seam | Manifest-assembly internals | — |
| [InstanceBuilderHost](internal.md#instancebuilderhost) | `dna.kernel.collaborator_ports` | internal seam | Everything the instance builder needs | — |
| [InvalidationHost](internal.md#invalidationhost) | `dna.kernel.collaborator_ports` | internal seam | Cache-coherence state | — |
| [KindLookup](internal.md#kindlookup) | `dna.kernel.collaborator_ports` | internal seam | Kind identity, plane and storage, for kernel collaborators | — |
| [LayerObserverCtx](internal.md#layerobserverctx) | `dna.kernel.collaborator_ports` | internal seam | The reverse-dependency observer graph | — |
| [LayerPolicyHost](internal.md#layerpolicyhost) | `dna.kernel.collaborator_ports` | internal seam | Everything layer-policy enforcement needs | — |
| [NamespaceGateHost](internal.md#namespacegatehost) | `dna.kernel.collaborator_ports` | internal seam | Everything the namespace-ownership gate needs | — |
| [QueryEngineHost](internal.md#queryenginehost) | `dna.kernel.collaborator_ports` | internal seam | Everything the query engine needs | — |
| [RecordQuery](internal.md#recordquery) | `dna.kernel.collaborator_ports` | internal seam | The record-query push-down | — |
| [RegistryAccessorHost](internal.md#registryaccessorhost) | `dna.kernel.collaborator_ports` | internal seam | The three global registry reads | — |
| [RegistryHost](internal.md#registryhost) | `dna.kernel.collaborator_ports` | internal seam | Everything the Kind registry needs | — |
| [SearchEngineHost](internal.md#searchenginehost) | `dna.kernel.collaborator_ports` | internal seam | Everything the search engine needs | — |
| [SourceFacadeHost](internal.md#sourcefacadehost) | `dna.kernel.collaborator_ports` | internal seam | Read-only source introspection | — |
| [SourceSyncHost](internal.md#sourcesynchost) | `dna.kernel.collaborator_ports` | internal seam | Everything source sync needs | — |
| [WriteHost](internal.md#writehost) | `dna.kernel.collaborator_ports` | internal seam | Everything the write pipeline needs | — |
| [WriteOps](internal.md#writeops) | `dna.kernel.collaborator_ports` | internal seam | The kernel's write entry points | — |

## Before you implement one

Two house rules apply to every port on this page.

1. **If the thing you are adapting to has an official SDK, use it.** A port exists so DNA's core does not have to know your backend; it does not exist so you can re-derive somebody else's protocol from its specification. Conformance with a third party is the whole product, and a subtle misreading of a spec only surfaces when a real external client tries to talk to you.
2. **Search before you build.** Check whether an adapter already exists — in this tree, in a dependency this package already declares, or on GitHub — before you write the first line. Record the result either way; a port implementation that does not say whether it looked leaves the next reader unable to tell a decision from an oversight.
