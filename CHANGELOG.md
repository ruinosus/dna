# Changelog

All notable changes to DNA are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Pre-1.0 notice.** DNA has not yet reached 1.0. Until then the public API
> may change between releases without a major-version bump; SemVer guarantees
> apply from 1.0.0 onward. The packages are not yet published to PyPI/npm —
> consume them from the repository.

## [Unreleased]

Everything below is the extracted public core as it stands today — the
baseline that the first tagged release will draw from.

### Added

- **Microkernel + extensions core.** A kernel that mediates five ports —
  source, cache, resolver, reader/writer, and kind — and knows no Kinds
  itself; extensions register Kinds onto it via `kernel.load(ext)`.
- **Dual SDK, one behavior.** Python (`packages/sdk-py`, `import dna`) and
  TypeScript (`packages/sdk-ts`, `@dna/sdk`) implementing the same kernel 1:1,
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
- **Source adapters** — filesystem (the default for development), SQLite, and
  Postgres — behind a capability-aware `SourcePort`.
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

[Unreleased]: https://github.com/ruinosus/dna/commits/main
