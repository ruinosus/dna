# Changelog

All notable changes to DNA are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Pre-1.0 notice.** DNA has not yet reached 1.0. Until then the public API
> may change between releases without a major-version bump; SemVer guarantees
> apply from 1.0.0 onward.

## [Unreleased]

### Added

- **The `EmitterPort` as a first-class, documented DNA port + the scaffold
  mechanism for code-first runtimes** (epic `e-dna-portability`, feature
  `f-dna-emitters`, story `s-emit-port-contract`). Elevates the emit layer to a
  documented contract on the same footing as the kernel's ports, and lays the
  base the next code-first emitters (langgraph / agno / deepagents) are built on:
    - **The port contract, made explicit.** `EmitterPort` is a documented
      Protocol/interface with two surfaces — `build_emit_context(mi, agent)` (the
      kernel-facing half: compose + project to the neutral `EmitContext`) and
      `emit(ctx) -> EmitResult` (the runtime-facing half a target implements) —
      plus `target` / `file_extension`. Py↔TS parity of the contract.
    - **The byte-equal invariant, made inheritable.** The composed instruction in
      an emitted artifact MUST be byte-equal to `build_prompt`. A new contract
      hook, `extract_instructions(artifact)`, recovers it from any target's own
      artifact, and one generic test (`test_emit_contract` /
      `emit-contract.test.ts`) runs the byte-equal assertion over **every**
      registered target — so a new emitter inherits the check the moment it
      registers. Implemented on all three existing config emitters.
    - **Two emitter flavors.** *config-declarative* (map onto a runtime's
      published YAML/JSON schema — the shipped agent-framework / bedrock / vertex)
      and *scaffold-code* (fill a curated template for a code-first runtime).
    - **The scaffold mechanism (`ScaffoldEmitter`).** A code-first runtime has no
      schema to map onto, so the emitter emits *source code* by **filling a
      curated template, never generating code ad-hoc**. The template library is
      indexed by `{framework × case}` (`emit/scaffolds/<framework>/<case>.py.tmpl`)
      and a case classifier (`select_scaffold`) routes from the DNA signals in the
      context — no tools → `prompt-only`; tools → `with-tools`; `output_schema` →
      `structured-output` — falling back down a generality chain (and recording
      the fallback as a loss) when a framework does not ship a case. A subclass
      stays thin: template + variable mapping; selection, fill, and the byte-equal
      hook are inherited. Templates are read through an abstract resolution seam
      (`resolve_scaffold` / `ScaffoldResolver`), NOT a hardcoded path — the MVP
      resolver reads package-data, but a host can swap in another source with no
      emitter change. That is where the future first-class **Scaffold Kind**
      (declarative, versioned, tenant-overridable — story `s-scaffold-as-kind`)
      plugs in: the DNA thesis applied to DNA's own de-para.
    - **First code-first target: `openai-agents`** (OpenAI Agents SDK). Ships two
      case templates (`prompt-only`, `with-tools`) proving selection + the
      byte-equal instruction + syntactically valid (`py_compile`) output. The next
      three code-first emitters are then just "a couple of templates + a small
      mapping".
    - **Docs.** New guide *How to write an emitter* (both flavors + the *Passo 0*
      decision + how to add a case), the EmitterPort documented alongside the
      kernel ports in *The microkernel and its ports*, and the OpenAI Agents
      scaffold added to *Emitting to a runtime*.
- **`dna mcp serve` Phase 2 — remote transport + OAuth 2.1 auth bound to DNA
  tenancy** (feature `f-dna-mcp-server`, stories `s-mcp-remote-transport` +
  `s-mcp-oauth-auth`; ADR `adr-dna-mcp-runtime-face`). The *same* MCP server the
  MVP serves over stdio (local: Claude Code/Cursor/Copilot) is now hostable and
  authenticated for **remote/web** clients (Claude web, ChatGPT):
  - **Streamable HTTP transport** — `dna mcp serve --transport {stdio|http|sse}`
    with `--host/--port/--path`. FastMCP-native (MCP spec 2025-06-18) — a flag,
    not new transport code; the endpoint is `http://<host>:<port>/mcp/`.
  - **OAuth 2.1 Resource Server** — `--auth jwt` verifies signed bearer JWTs
    (env `DNA_MCP_JWT_PUBLIC_KEY` | `DNA_MCP_JWKS_URI` + issuer/audience) and
    advertises Protected Resource Metadata (RFC 9728) when wrapped as a Resource
    Server (`DNA_MCP_RESOURCE_URL` + `DNA_MCP_AUTH_SERVERS`). Conforms to the MCP
    Authorization spec revision 2025-11-25 (PKCE, RFC 9728/8707/8414/7591); a
    WorkOS/Auth0 `OAuthProxy` slots into the same provider seam.
  - **The auth↔tenancy bridge** (`dna_cli._mcp_auth`) — maps the verified token's
    claim (`tenant`, configurable) or scope (`tenant:<x>`) to a **DNA tenant** and
    enforces it: every tool (`compose_prompt`/`recall`/`list_stories`/…) is
    **tenant-scoped by the token**; a cross-tenant or tenant-less request is denied
    (fail closed); with no auth (stdio) the bridge is an identity, so the base path
    is untouched. Auth + multi-tenant in one mechanism. HTTP/auth are optional
    extras that never break the stdio/base install. Guide: *The MCP server — DNA as
    a live layer → Remote + authenticated*.

## [0.9.0] - 2026-07-11

### Added

- **`dna mcp serve` — the MCP runtime face (DNA as a live layer)** (epic
  `e-dna-portability`, feature `f-dna-mcp-server`, story `s-dna-mcp-server-mvp`;
  ADR `adr-dna-mcp-runtime-face`). The second face of DNA serving runtimes and
  the **inverse of `dna emit`**: where `emit` writes a *static* artifact (and
  drops composition structure, per-tenant overlay, and no-deploy change), the
  MCP server composes **live** on request — recovering exactly those axes. One
  thin server exposes **everything DNA stores** over the neutral MCP protocol,
  so any MCP client (Claude Code/Desktop, Cursor, GitHub Copilot,
  agent-framework, Bedrock AgentCore) can reach it: **definitions** —
  `compose_prompt(agent, scope?, tenant?)` (the killer surface: the live-composed
  Soul+Guardrail+instruction prompt, **tenant-aware**), `list_agents`,
  `list_tools`, `get_tool`; **SDLC** — `sdlc_digest` (reuses the same
  `build_digest` core), `list_stories`, `get_adr`; **memory** — `recall`,
  `remember`, `consolidate`; plus MCP **resources** (`dna://{scope}/manifest`,
  `dna://{scope}/agents`). The tools are thin adapters over already-tested pure
  cores — no new business logic. Built on **FastMCP** (the standalone `fastmcp`
  framework) for native stdio+HTTP transports and built-in OAuth 2.1 auth. The
  MVP is stdio (local clients); remote Streamable HTTP + OAuth-2.1-bound-to-DNA-
  tenancy are filed as Phase-2 stories (`s-mcp-remote-transport`,
  `s-mcp-oauth-auth`) — *enable + bridge*, not *build*, thanks to FastMCP. The
  `mcp` dependency is an **optional extra** (`pip install 'dna-cli[mcp]'`,
  imported lazily — the base install is unaffected). Guide: *The MCP server —
  DNA as a live layer*.
- **`dna sdlc gallery` — the board-native index of the HtmlArtifacts to review**
  (feature `f-sdlc-digest`, story `s-sdlc-gallery`). The sibling of `digest`:
  where the digest surfaces **events** ("what happened"), the gallery surfaces
  the visual **artifacts** ("the HtmlArtifacts to review"). `dna sdlc gallery
  [--html <out>] [--open] [--json] [--scope]` walks every work item's outputs
  (`produces[]` ∪ legacy back-refs) to find which work item produced each
  `HtmlArtifact`, then groups the artifacts by that work item's status —
  **👀 Precisa de avaliação** (Story in review / open PR), **🧭 Decisões**
  (produced by an ADR), **✅ Shipado** (terminal), **📈 Em andamento**, and
  **📎 Sem work item** (orphan). Because the index is generated from the board,
  it is always current — killing the "artifacts pasted into chat get lost"
  gap. `--html` writes **one self-contained** page (no CDN, theme-aware) with a
  card per artifact, a status chip, the producing work item, the published
  link, and open PRs; `--open` opens it. The aggregation core
  (`dna_cli._gallery.build_gallery` + `render_gallery_html`) is a pure,
  kernel-free function with 16 unit tests. CLI-only (Python). Guide: *Gallery —
  the artifacts you need to review*.
- **`HtmlArtifact` gains a `published_url`** — the canonical hosted location
  (e.g. a claude.ai artifact link), set via `dna sdlc artifact create
  --published-url <url>`, surfaced in `artifact show`, the Kind `summary()`
  (Py↔TS parity), and rendered as the clickable **Abrir artifact ↗** on each
  gallery card. Lives in `artifact_json` (free-form), so no schema break.
- **Third runtime emitter — `dna emit --target vertex`** (epic
  `e-dna-portability`, feature `f-dna-emitters`, story `s-emit-vertex`). The
  portability thesis, proven a *third* way: the **same** DNA agent that emits a
  Microsoft agent-framework `PromptAgent` and an AWS CloudFormation
  `AWS::Bedrock::Agent` now also emits a **Google ADK Agent Config** YAML — the
  declarative, code-free way to define an ADK `LlmAgent`
  (`config_agent_utils.from_config(<path>.yaml)`). The emitted `instruction` is
  **byte-equal** to `build_prompt(agent)` — and identical to the agent-framework
  `instructions` and the Bedrock `Instruction`: **one source → three runtimes**,
  the same composed prompt. The de-para maps `agent_class: LlmAgent`,
  `metadata.name` → `name` (snake_cased to a valid Python identifier),
  `metadata.description` → `description`, `spec.model`/Genome default → `model`
  (Gemini id; DNA provider token stripped), and `spec.tools[]` → `tools[].name`
  (ADK binds tools by *code reference*, not a declarative schema). The artifact
  leads with a `# yaml-language-server` header binding it to the real published
  `AgentConfig.json`, so it validates structurally in any editor **without a GCP
  credential**. Honest `losses` surface the ADK-specific drops (tool binding is a
  code reference so a Tool's schema/description have no declarative slot;
  `output_schema` is a Pydantic-class reference; a non-Gemini model coordinate
  needs `model_code`/LiteLlm) on top of the three DNA-only axes (composition
  structure / tenant overlay / eval-as-contract). Python + TypeScript parity
  (`dna/emit/vertex.py` + `src/emit/vertex.ts`); the shared
  `examples/emitting-to-a-runtime/` now proves all **three** runtimes. Guide:
  *Emitting to a runtime* (with the ADK mapping table).

### Changed

- **`dna sdlc produces add` now accepts an `ADR`** as a producer (not only
  Story/Spike/Feature/Epic/Issue) — an ADR legitimately produces its
  decision-visualization `HtmlArtifact`, which is what buckets it under
  **Decisões** in the gallery.

## [0.8.0] - 2026-07-11

### Added

- **`dna sdlc digest` — a retrospective "what happened while you were away"**
  (feature `f-sdlc-digest`, story `s-sdlc-delegator-digest`). The backward-
  looking mirror of `brief`/`next`/`current` (which point *forward*): the
  surface for whoever **delegates** work and reviews the board at the end
  instead of watching it live. `dna sdlc digest [--since <ref>] [--scope]
  [--save] [--json]` aggregates every work-item timeline event in a window and
  groups it — **Concluído / Decidido / Achado / Avançou / Releases / Artefatos**
  — leading with a first-class, **not-windowed** *"Precisa de você"* section:
  blocked items (with reason), Stories in review (with their open PR numbers
  matched from `gh`), owner decisions (ADRs still `proposed`), and open
  questions (unanswered Spikes), plus a PMO-style RAG status. `--since` accepts
  an ISO-8601 timestamp, a relative span (`90m`/`24h`/`3d`/`2w`), or
  `last-digest` (tiles the timeline gaplessly from the previous digest);
  default is the last 24h. `--save` persists the digest as a queryable
  `StatusReport` named `digest-<date>` (its `verdict` + `heuristic_explanation`
  are embedded, so `dna cognitive search` recalls past digests). The
  aggregation core (`dna_cli._digest.build_digest`) is a pure, kernel-free
  function with 23 unit tests. CLI-only (Python) — the `dna` binary has no TS
  twin. Guide: *Digest — what happened while you were away*.
- **Second runtime emitter — `dna emit --target bedrock`** (epic
  `e-dna-portability`, feature `f-dna-emitters`, story `s-emit-bedrock`). The
  portability thesis, *proven*: the **same** DNA agent that emits a Microsoft
  agent-framework `PromptAgent` now also emits an AWS **CloudFormation**
  `AWS::Bedrock::Agent` template — one definition, two runtimes, swapped without a
  rewrite. Target chosen after investigating AWS's three agent surfaces (Bedrock
  Agents / Strands / AgentCore): only **Bedrock Agents** has a published
  *declarative* schema, and a CloudFormation artifact is lintable + deployable
  with **no AWS credential**. The de-para is structural: `metadata.name`→
  `AgentName`, `metadata.description`→`Description`, the composed prompt
  (`build_prompt`)→`Instruction` (**byte-equal**, identical to the
  agent-framework `instructions`), `spec.model`/Genome `default_llm`→
  `FoundationModel` (DNA provider token stripped; Bedrock-native ids / ARNs pass
  through), `spec.tools[]`→`ActionGroups[].FunctionSchema.Functions[]` with a flat
  `Parameters{Type,Description,Required}` map and a `CustomControl: RETURN_CONTROL`
  executor (client-side tools, no Lambda). Honest `losses` add the Bedrock-specific
  drops: tool-parameter depth (`default`/`enum`/nested/`items`), `output_schema`,
  and the model coordinate. Plugged into the existing `EmitterPort` registry — the
  CLI core is unchanged. Python + TypeScript parity on the emitted template object;
  the `examples/emitting-to-a-runtime` example now documents both runtimes.
- **`dna sdlc cite` now cites _any_ citable Kind — not just `Reference`**
  (epic `e-dna-portability`, feature `f-dna-sdlc-expressiveness`, story
  `s-cite-any-citable-kind`). The cited target accepts `<Kind>/<name>` —
  `dna sdlc cite Research/<name> --from ADR/<name>` (or from an Epic, Spec,
  Story, …) — while a bare `<name>` still defaults to `Reference` for
  backwards-compat. The citation stays **bidirectional**: the cited doc gains
  `spec.cited_by` (the back-ref) and the caller gains `spec.references`. This
  encodes the semantic the model had to bridge by hand during the pivot —
  **`cite` = a source that _grounds_ the work; `produces` = an output the work
  _authored_.** The `Research` Kind gains an explicit `cited_by` field (Py↔TS)
  for discoverability; other SDLC Kinds inherit it via their flexible specs.
  `uncite` is symmetric across Kinds.

### Fixed

- **`dna sdlc epic show` now lists an Epic's features** (feature
  `f-dna-sdlc-expressiveness`, story `s-epic-show-forward-features`). It read
  the forward `Epic.spec.features[]` list, which `feature create --epic X`
  never populates (it maintains only the back-ref `Feature.spec.epic`), so a
  correctly-linked Epic still printed "(no features linked)". Features are now
  resolved by **reverse-lookup** on `Feature.spec.epic == <epic>` — the back-ref
  is the single source of truth, mirroring how `feature show` finds its stories
  by `Story.spec.feature`. The forward link is intentionally _not_ populated
  (no duplicate source of truth). `dna sdlc epic ship` had the identical
  latent bug in its cascade-close and is fixed the same way.

## [0.7.0] - 2026-07-11

### Added

- **Vendor-neutral emitters — `dna emit` + the `dna.emit` port/registry**
  (epic `e-dna-portability`, feature `f-dna-emitters`, story
  `s-emit-agent-framework`). The pivot's first concrete step: DNA is a
  vendor-neutral **definition** layer that authors an agent **once** (Agent +
  Soul + Guardrail + Tool Kinds) and **materializes the native artifact each
  runtime consumes** — "author once, emit per runtime". New CLI:
  `dna emit <agent> --target <t> [--scope --out --model --provider --json]` and
  `dna emit --list-targets`. First proven target: **Microsoft agent-framework**
  (`--target agent-framework`) — emits the declarative `PromptAgent` YAML that
  `AgentFactory` loads. The de-para is **structural**, not a string dump:
  `metadata.name`→`name` (CamelCase), `metadata.description`→`description`,
  the composed prompt (`build_prompt`: Soul + guardrails + instruction)→
  `instructions` (**byte-equal**), `spec.model`/Genome `default_llm`→
  `model.{id,provider}`, `spec.tools[]` (the `Tool` Kind)→`tools[]`
  (`kind: function`, carrying each tool's description + input JSON Schema),
  `spec.output_schema`→`outputSchema`. Axes with no target slot (composition
  structure, tenant overlay, eval-as-contract) are reported honestly in
  `EmitResult.losses`. Targets are a **pluggable registry** (`EmitterPort` +
  `register_emitter`) — a new one (bedrock/vertex/openai) is a class + one call,
  the CLI core never changes. Exposed from the package root on both runtimes
  (`dna.emit_agent` / `emitAgent`); the pure de-para is Py↔TS parity-checked.
  Committed example + fixture: `examples/emitting-to-a-runtime/`. Proof: the
  emitted `instructions` is byte-equal to `build_prompt` and the artifact loads
  into a live agent-framework `Agent` (a gated test that skips without the
  runtime). Guide: **How-to → Emitting to a runtime (the de-para)**.

## [0.6.0] - 2026-07-11

### Added

- **Tools as data — `load_tools` + the `Tool` Kind as a descriptor**
  (feature `f-dna-tools-as-data`). The agent-facing surface of a tool — the
  `description` a model reads to decide whether to call it, and the JSON Schema
  of its `parameters` — is now consumable as data, the twin of `load_prompts`:
  `dna.load_tools(scope)` / `loadTools(scope)` returns a `ToolLibrary` mapping a
  tool name to its `ToolSurface` (`{description, parameters}` =
  `{metadata.description, spec.input_schema}`), lazy + cached, exported from the
  package root on both runtimes. A miss raises the typed, exported
  `ToolNotFound` (a `LookupError`) — never an empty surface. New CLI: `dna new
  tool <name> [-d --type]` scaffolds a valid Tool through `kernel.write_document`
  (idempotent; `--force`). Overlay-aware: a tenant overlay of a tool's
  description/parameters wins for that tenant while the base stays intact.
  Cross-language dogfood under `examples/tools_as_data/` — the **same** Tool
  document read by Python and TypeScript yields **byte-identical** surfaces
  (asserted against one committed oracle by both suites): the first place the
  Py↔TS descriptor parity pays off in a real consumer. Guide: **How-to → Tools
  as data**.

### Changed

- **The `Tool` Kind migrated from a hand-written class to a record-plane
  descriptor** (`helix/kinds/tool.kind.yaml`, byte-identical Py↔TS), per the
  repo's own ratchet (record Kinds are data, not classes). The alias
  (`helix-tool`), storage (`tools/<name>.yaml`), schema, Studio UI metadata and
  agent references (`dep_filters.tools`) are unchanged. Because a Tool is not a
  prompt target, it now correctly lives on the **record** plane: writing a Tool
  no longer invalidates the composition schema cache, and an agent's `tools:`
  ref pointing at a not-yet-shipped Tool is resolved lazily (host-resolved)
  instead of being flagged as a missing composition input.
- **Ship a scope with your app — resolve a scope as PACKAGE DATA** (feature
  `f-dna-scope-packaging`; stories `s-scope-as-package-data`,
  `s-pkg-source-scheme`). A deployed app can now let its DNA scope TRAVEL inside
  the deployable, resolved from *inside* the installed package — no fragile
  `Path(__file__).resolve().parents[N] / ".dna"` navigation and no manual
  `COPY .dna` in the Dockerfile (the image is the app, not the repo; forget the
  copy and the app boots with no scope — a real pilot bug). Two surfaces, in
  Python↔TypeScript parity:
  - `load_prompts(scope, *, anchor="mypkg")` / `loadPrompts(scope, { anchor })`
    — `anchor` is a package name; the scope is resolved via
    `importlib.resources` (Py) / the package's own location (TS), so it works
    identically from a source checkout, an installed wheel, and a Docker image.
    Precedence: `base_dir` arg > `$DNA_BASE_DIR` > `anchor` (package data) >
    `.dna` (cwd).
  - A `pkg://<package>[/<subpath>]` **source scheme** for `dna.config.yaml` /
    `Kernel.from_config` (subpath defaults to `.dna`), resolving the embedded
    scope to a **read-only** filesystem source. Both surfaces fail loud with a
    packaging-oriented message on a missing package/subpath.
  - New helper `dna.anchor_scopes_root` / `anchorScopesRoot` (+
    `PackageScopeNotFound`) exposes the resolution directly.
  - New guide **"How to ship a scope with your app"** (Hatch / setuptools / npm
    packaging + the Docker contrast) and a runnable example
    (`examples/shipping-a-scope/`) with a test that installs the example and
    resolves the scope from a DIFFERENT working directory — the Docker scenario.

### Fixed

- **CLI boot now wires the `LocalResolver` — `dna eval run` resolves `local:`
  deps identically to the SDK** (s-cli-localresolver-consistency, kaizen
  `kz-001`; feature `f-dna-dx-configure`). The `dna` CLI built its kernel via
  `Kernel.auto()` **without a source** and attached the source afterwards, so
  `build_auto_kernel`'s resolver-wiring branch (guarded by `source is not None`)
  never ran — the CLI kernel had **zero resolvers**. A dependency declared as
  `local:<scope>` therefore resolved through `Kernel.quick` (which wires the
  resolvers) but silently **failed to resolve** through `dna eval run` and every
  other CLI command: same composition, two results. The resolver set is now
  wired by one shared recipe (`kernel_bootstrap.wire_filesystem_resolvers`) used
  by `Kernel.quick`, `Kernel.auto`/`Kernel.from_config` (filesystem source), and
  the CLI boot path. Non-filesystem sources (SQLite/Postgres) have no
  scopes-root directory, so `LocalResolver` is a documented no-op there. As a
  side benefit, the `auto`/`from_config` path now also registers the `github` /
  `http` / `https` / `registry` / `helix` resolvers (previously `local`-only),
  matching `Kernel.quick` and the TypeScript `fromConfig`. The `dna` CLI is
  Python-only; the TypeScript `quickInstance` / `fromConfig` already wired their
  resolvers, so there was no TS-side gap to fix.

## [0.5.0] - 2026-07-11

### Added

- **`HtmlArtifact` Kind — an HTML page as a first-class work-item output**
  (s-dx-html-artifact-kind, epic `e-dna-dx`). A bundle Kind (record plane,
  alias `sdlc-html-artifact`) registered by the `sdlc` extension in both
  runtimes: `ARTIFACT.html` stores the raw HTML **byte-faithful** (the writer
  never injects frontmatter or re-escapes — a design doc / roteiro / rendered
  report round-trips untouched), plus an optional `artifact.json` companion
  with structured metadata (`title`, `description`, `source`, `created_at`) —
  the same mechanic as a Soul's `SOUL.md` + `soul.json`. Custom reader/writer
  with proven Py↔TS round-trip parity. New CLI: `dna sdlc artifact create
  <name> --from <file.html> [--title --description --source]`, plus `artifact
  list` / `artifact show [--html]`. Attach one to the board with `dna sdlc
  produces add <WiKind>/<wi> HtmlArtifact/<name>`. DNA dogfoods it — the
  `e-dna-dx` epic **produces** its own design doc as
  `HtmlArtifact/ha-e-dna-dx-design`. Guide: **SDLC → Work items produce
  artifacts**.
- **Named composition layouts — order the persona by name, no Mustache**
  (s-dx-named-layouts, epic `e-dna-dx` / feature `f-dna-dx-author`). An Agent
  spec now accepts a `layout:` field: `persona-first` puts the Soul before the
  instruction, `instruction-first` (a.k.a. `default`, the historic order) keeps
  it after. The kernel resolves the name to an embedded template via a new
  KindPort extension point (`layout_template()` / `layoutTemplate()`), so the
  common case never hand-writes `{{{soul_content}}}` / `{{#guardrails-guardrail}}`.
  A raw `promptTemplate` still wins over `layout` (the poweruser escape hatch);
  an unknown layout fails loud with the new `UnknownLayout` error (exported from
  the package root, Py + TS). Guardrails always compose last. Py↔TS 1:1. Guide:
  **Authoring agents**.
- **`dna new agent|soul|guardrail <name>` — scaffold a valid skeleton**
  (s-dx-new-scaffolding). Writes the correct envelope + bundle shape into a
  scope through `kernel.write_document` (every write guard runs), leaving only
  the prose to fill in. `dna new agent` pre-fills `--soul` / `--guardrails` /
  `--layout` / `--model`; `dna new soul` emits a single-file `SOUL.md`. Idempotent
  (never clobbers without `--force`). Guide: **Authoring agents**.

### Changed

- **Single-file souls are a first-class authoring path** (s-dx-single-file-soul).
  A Soul authored as a lone `SOUL.md` (minimal frontmatter or none) reads and
  composes — `soul.json` is now optional, not required. The two-file
  soulspec.org bundle (`SOUL.md` + `soul.json` manifest) stays fully supported
  and byte-faithful on round-trip (market-conformance suite unchanged); the
  single-file form is the convenience on-ramp. Py↔TS 1:1.
- **TS composition now includes the guardrails block** (aligns the TypeScript
  Agent default template to Python, which was the semantic reference — closing
  the latent i-213/i-011 divergence where TS `promptTemplate()` omitted it).
  Composed prompts in the TS SDK now carry the same guardrail policy section as
  Python.

## [0.4.0] - 2026-07-11

### Added

- **`dna.load_prompts(scope, base_dir=None)` — compose prompts in one line**
  (s-dx-load-prompts-helper, epic `e-dna-dx`). Returns a `PromptLibrary`, a
  lazy/cached read-only mapping from agent name to its composed, already-clean
  system prompt; a missing agent raises `AgentNotFound`. Collapses the
  ~166-line defensive prompt shim a real consumer wrote (boot kernel + resolve
  base dir + `mi.one("Agent", x) is None` guard + `.rstrip("\n")`) down to
  `prompts = load_prompts(scope); TRIAGE = prompts["triage"]`. TS twin
  `loadPrompts` / `PromptLibrary` (composition is async, so `await
  prompts.get("triage")`). Guide: **Consuming prompts**.
- **`dna.config.yaml` + `Kernel.from_config(path=None)` — declarative port
  wiring** (s-dx-kernel-from-config). A language-agnostic config file selects
  the `source` (`file://` / `sqlite://` / `postgresql://`), and optionally the
  `search` (`pgvector` / `sqlite-vec` / `off`) and `embedding` (`onnx` /
  `fake` / `off`) providers; `Kernel.from_config` resolves every port to its
  adapter and returns the wired kernel. No config present → the current
  filesystem `.dna` behavior, unchanged. TS twin `fromConfig`. The URL→source
  factory is now a **public** surface (`dna.adapters.source_from_url` /
  `sourceFromUrl`) that actually supports `sqlite://` / `postgresql://` via the
  existing `SqlAlchemySource`; the `dna` CLI consumes the same factory (so
  `DNA_SOURCE_URL=sqlite://…` / `postgresql://…` now Just Works). `sqlite://`
  is Python-only in the TS runtime and fails loud there. Guide: **Configuring
  ports**.
- **`dna sdlc epic create <name>`** (s-dx-epic-create) — closes the last CRUD
  gap in the SDLC CLI. Story and Feature had `create`; an Epic previously had
  to be hand-authored via `dna doc apply`. Mirrors `feature create` (same
  flags, same `kernel.write_document` path, same initial timeline event).

### Changed

- **BREAKING — `build_prompt` fails loud on a missing agent**
  (s-dx-build-prompt-fail-loud). `mi.build_prompt(agent=X)` (and its async /
  record-plane twins, and the TS `mi.buildPrompt`) now **raise**
  `AgentNotFound` (Python: a `LookupError`; TS: an `Error` with `.agent`)
  instead of RETURNING the string `"Agent 'X' not found"`. The old behavior
  let a missing/renamed agent sail through an `if not text` check and become
  the literal instruction — every consumer wrote the same `mi.one("Agent", x)
  is None` guard to defend against it. `AgentNotFound` is exported from the
  package root. Migration: replace the guard + `.rstrip` shim with a
  `try/except AgentNotFound` (or just let it propagate) — or adopt
  `load_prompts`, which does it for you.
- **BREAKING — `build_prompt` returns clean output**
  (s-dx-clean-composition-output). Composed prompts no longer carry trailing
  newlines leaked from template sections; the builder strips them. Consumers
  that hand-wrote `.rstrip("\n")` can drop it. If you pinned an exact composed
  string that ended in `\n`, update the expectation.

## [0.3.1] - 2026-07-10

### Fixed

- **`dna install` no longer hides sibling documents when a reader claims the
  tree root** (s-install-scan-fixes, closes i-016). A claim now consumes its
  *bundle* — whose authoritative extent is the paired writer's
  `serialize()` — instead of the whole subtree, so a root `AGENTS.md`
  coexists with `skills/` (mixed trees install completely) while Skill
  bundles still yield exactly one document. Claims without a paired writer
  keep the old conservative subtree semantics. `dna init --from` now
  delegates to the fixed scan (its PR #41 workaround was removed), and a
  `requires_network` test consumes the public `examples/onboarding-pack`
  from the default branch (closes i-017).

## [0.3.0] - 2026-07-10

### Added

- **`dna init --from` — distributed onboarding packs**
  (s-onboarding-genome-install, closes i-015). `dna init` can now source its
  assets from a remote pack instead of the embedded Genome:
  `dna init --from github:owner/repo[/subdir][@ref]` (or a local path). Every
  valid Skill in the pack is projected per `--tools`; a root `AGENTS.md`
  replaces the embedded one (absent → embedded fallback, noted). `--from`
  only projects to tool directories — `dna install` remains the channel that
  writes documents to the source; the two compose over the same ref. Pack
  content is untrusted and goes through the same install defenses
  (registered Kinds, JSON Schema, slug-only names). A public example pack
  ships in `examples/onboarding-pack/`.
- **Memory conformance kit** (s-memory-conformance-kit). `dna.testing` now
  ships a public conformance suite for memory: 10 verb invariants
  (remember→recall roundtrip, bi-temporal forget with no hard deletes,
  idempotent consolidate, strictly decreasing Ebbinghaus retention under
  simulated time, text-hash-idempotent backfill, honest lexical fallback)
  plus 7 pure scoring invariants mirrored 1:1 in `dna-sdk/testing` for
  TypeScript (ecphory weights/threshold, RRF fusion, cosine ordering).
  Runs against the builtin providers (filesystem, sqlite-vec, pgvector)
  and against custom `RecordSearchProvider`/`EmbeddingPort` implementations
  via the public factory API.

### Changed

- `dna-cli` now depends on `dna-sdk>=0.3,<0.4`.

## [0.2.0] - 2026-07-10

### Added

- **`dna init` — multi-tool agent-ready onboarding** (s-dna-init-agent-ready).
  One command scaffolds a consumer project for AI-assisted development: a
  `.dna/<scope>` board, a canonical `AGENTS.md` (agents.md/v1), the
  `dna-sdlc-cli` skill materialized per tool directory
  (`--tools claude,copilot,cursor,opencode`, default `claude,copilot`,
  `all` supported), and the `Work-Item:` git hooks. The skill ships inside
  the package as a real Kind and is projected byte-faithfully by the
  agentskills writer — one Kind, N projections. Idempotent: existing files
  are never overwritten without `--force`; the board is never rewritten.
  See the [agent onboarding guide](docs/getting-started/agent-onboarding.md).
- **Semantic recall in memory** (s-memory-semantic-recall). `recall` now
  feeds the previously inert semantic path of the ecphory scorer: when an
  `EmbeddingPort` + `RecordSearchProvider` are configured, results blend the
  existing hybrid retrieval with ecphory×cosine ranking via RRF. Opt-out
  with `--no-semantic`; without a provider the behavior is byte-identical
  to previous releases (offline-first, no schema migration — lazy backfill
  indexes older memories on demand). See the
  [semantic recall guide](docs/guides/semantic-recall.md).

### Changed

- `dna-cli` now depends on `dna-sdk>=0.2,<0.3`.

## [0.1.0] - 2026-07-10

The first tagged release — the extracted public core, published to the
registries: **PyPI** ([`dna-sdk`](https://pypi.org/project/dna-sdk/),
[`dna-cli`](https://pypi.org/project/dna-cli/)) and **npm**
([`dna-sdk`](https://www.npmjs.com/package/dna-sdk)).

### Added

- **Published packages** (s-publish-registries). `pip install dna-sdk dna-cli`
  and `npm install dna-sdk` are now the primary install paths (the repo
  remains the pre-release/exact-pin alternative). The TypeScript package was
  renamed `@dna/sdk` → `dna-sdk` (unscoped, mirroring PyPI) and gained a
  publication build — compiled ESM JS + type declarations in `dist/`,
  including the runtime `*.kind.yaml` descriptors and `DOCS*.md` kind docs
  that the extensions load relative to their own compiled modules. `dna-cli`
  now depends on `dna-sdk>=0.1,<0.2` (resolved from PyPI in published
  artifacts; the dev workspace keeps the editable path source). Releases are
  cut by pushing a `vX.Y.Z` tag: tag-triggered workflows (`release.yml` +
  `release-cli.yml` — one PyPI project per workflow file, a PyPI
  pending-publisher dedup constraint) build sdist+wheel for both Python
  packages and publish them via PyPI trusted publishing (OIDC, no long-lived
  token), and publish the npm package with provenance via npm OIDC trusted
  publishing (no token; the first npm publish is manual). See `RELEASING.md`.
- **Write-path schema validation** (i-008). `write_document` /
  `writeDocument` now validate the doc's `spec` against the Kind's declared
  `schema()` **before persisting** — previously schemas were only checked at
  scan/read (fail-soft), so a shape-broken doc persisted and exploded later,
  far from the author. Kinds without a schema stay permissive; descriptor
  `spec_defaults` fill before validation; the veto error is didactic (field,
  violation, `dna kind show <Kind>` hint). Escape hatches:
  `DNA_WRITE_VALIDATION=warn|off` (default `enforce`). The Automation write
  guard dropped its now-redundant local shape check and keeps only its
  Kind-specific cures (YAML-1.1 `on:` heal, cron/hook semantics).
- **Microkernel + extensions core.** A kernel that mediates five ports —
  source, cache, resolver, reader/writer, and kind — and knows no Kinds
  itself; extensions register Kinds onto it via `kernel.load(ext)`.
- **Dual SDK, one behavior.** Python (`packages/sdk-py`, `import dna`) and
  TypeScript (`packages/sdk-ts`, `dna-sdk`) implementing the same kernel 1:1,
  with a test-enforced Python↔TypeScript parity contract (port-surface parity,
  descriptor hash parity, kind-registry parity, composition parity).
- **Core Kinds** under `github.com/ruinosus/dna/...` — `Genome`, `Agent`,
  `Guardrail`, `Actor`/`UseCase`, `Tool`, `Hook`, `SafetyPolicy`, `Theme`,
  `Setting`, `LayerPolicy`, `Tenant`/`TenantMembership`, and governance Kinds
  (`Evidence`, `AuditLog`, `Comment`, `MCPFederation`, `Recognizer`).
- **`KindDefinition`** — a Kind that defines Kinds: register new record Kinds
  with a `*.kind.yaml` descriptor and no code. Descriptors are byte-identical
  across the two SDKs (hash-enforced).
- **Market-format fidelity.** Byte-faithful readers/writers for standards DNA
  did not invent, consumed under their owners' namespaces — Agent Skills
  (`agentskills.io/v1`, `SKILL.md` bundles), Souls (`soulspec.org/v1`,
  `SOUL.md` + companions), and `AGENTS.md` (`agents.md/v1`). Enforced by a
  conformance suite over real marketplace fixtures with byte-identical
  round-trip.
- **Source adapters** — filesystem (the default for development) and SQL
  (`SqlAlchemySource`: sqlite + postgres dialects, one adapter) — behind a
  capability-aware `SourcePort`.
- **Multi-tenancy and layer composition** — tenants as a first-class kernel
  dimension orthogonal to layers, with `LayerPolicy` governing which layers
  may override which Kinds.
- **The `dna` CLI** (`packages/cli`) — document CRUD (`dna doc`, `dna kind`,
  `dna scope`, `dna source`) plus a declarative, story-first SDLC
  (`dna sdlc`): Stories/Features/Issues tracked as DNA documents, versioned
  `prepare-commit-msg` commit-trailer hooks, and `dna sdlc story pr` that
  assembles a pull request from the Story.
- **The Research Kind** (`github.com/ruinosus/dna/research/v1`) — curated,
  multi-finding syntheses stored as documents, authored via `dna research`.
- **The public conformance kit** (`dna.testing`) — ship-with-the-SDK source
  and reader/writer compliance suites for adapter authors, in the spirit of
  the DB-API compliance suite.
- **Community-health baseline** — this CHANGELOG, plus `CONTRIBUTING`,
  `SECURITY`, `CODE_OF_CONDUCT`, issue forms, and a PR template.

### Changed

- **Python floor lowered to 3.12** (`requires-python = ">=3.12,<3.14"` for
  `dna-sdk` and `dna-cli`, s-py312-floor). The first real consumer of the
  SDK — a backend on Azure Container Apps pinned to `>=3.12,<3.13` — could
  not install it under the previous 3.13-only floor, a convenience decision
  from PR #1 whose single deliberate 3.13-ism was PEP 696
  `TypeVar(default=...)` in `dna/kernel/document.py`. That import is now
  version-gated: stdlib `typing` on 3.13+, `typing_extensions>=4.4` on 3.12
  (an env-markered dependency — zero cost on 3.13+ installs). A full-suite
  sweep under 3.12 found no other accidental 3.13-isms, and the CI matrix
  now runs sdk-py + cli on {3.12, 3.13} so the floor cannot regress
  silently. Ecosystem libraries support N-1.

### Removed

- **The raw Python SQL adapters** (`s-retire-raw-sql-adapters`). The
  asyncpg-based `PostgresSource` and the aiosqlite-based `SqliteSource` are
  gone; `SqlAlchemySource` (`dna.adapters.sqlalchemy_`) is the Python SDK's
  only SQL source. It binds to the **exact same tables and migrations** the
  raw adapters created, so **switching is pure instantiation — zero data
  migration**:

  ```python
  # before                                   # after
  SqliteSource(db_path="app.db")             SqlAlchemySource("sqlite+aiosqlite:///app.db")
  PostgresSource(pool, schema="public")      SqlAlchemySource("postgresql+asyncpg://…", schema="public")
  ```

  The `postgres` / `sqlite` extras keep their names and now install
  `sqlalchemy[asyncio]` plus that dialect's driver (`sql` is the umbrella
  for both); nothing in the default install imports sqlalchemy. The
  `PostgresEventBus` subscriber is unchanged (the pg dialect emits the same
  outbox + `kernel_writes` NOTIFY contract, now homed in
  `dna.kernel.eventbus`), and the pg dialect keeps the native COUNT
  push-down. Retiring the raw PG adapter also retires its two known
  defects (i-001 `_acquire_safe` connection leak, i-002 asyncpg
  pool-close hang) — the SQLAlchemy pool does not exhibit them. The
  TypeScript SDK is untouched: its raw `PostgresSource` remains the single
  TS SQL adapter (documented asymmetry — TS has no SQLAlchemy to
  consolidate onto).

### Fixed

- **`dna source diff`/`push` were blind to base-layer content** (i-006).
  `digest_manifest` read the base via `load_layer(scope, "tenant",
  "__base__")`, which real adapters treat strictly as a tenant-overlay
  read — both sides digested `{}` and every diff reported "in sync".
  The base now digests through `load_all` (the canonical base-read
  path); explicit `--tenant` overlays keep using `load_layer`. `push`
  additionally publishes drafts on draft-staged targets (SQLite) so
  pushed docs become visible, and relative `fs://./path` URLs resolve
  correctly instead of silently pointing at an absolute path. The
  source conformance kit now pins the contract: base content is served
  by `load_all`, never by a `load_layer` sentinel.

[Unreleased]: https://github.com/ruinosus/dna/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/ruinosus/dna/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/ruinosus/dna/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/ruinosus/dna/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/ruinosus/dna/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/ruinosus/dna/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ruinosus/dna/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/ruinosus/dna/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/ruinosus/dna/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ruinosus/dna/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ruinosus/dna/releases/tag/v0.1.0
