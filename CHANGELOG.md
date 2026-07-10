# Changelog

All notable changes to DNA are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Pre-1.0 notice.** DNA has not yet reached 1.0. Until then the public API
> may change between releases without a major-version bump; SemVer guarantees
> apply from 1.0.0 onward.

## [Unreleased]

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

[Unreleased]: https://github.com/ruinosus/dna/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ruinosus/dna/releases/tag/v0.1.0
