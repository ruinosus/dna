# DNA — Domain Notation of Anything

[![python](https://github.com/ruinosus/dna/actions/workflows/python.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/python.yml)
[![typescript](https://github.com/ruinosus/dna/actions/workflows/typescript.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/typescript.yml)
[![guards](https://github.com/ruinosus/dna/actions/workflows/guards.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/guards.yml)

**Kubernetes CRDs, but for agentic behavior.**

DNA is a declarative, typed notation for everything that participates in an
agentic system — agents, skills, souls, guardrails, tools, policies. Every
participant is identified by `(apiVersion, kind)`, validated against a
per-Kind schema, and stored as versionable YAML/Markdown. Changing an agent
is a file edit, not a deploy.

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: Agent
metadata:
  name: greeter
spec:
  instruction: |
    You are Helio, a friendly assistant.
  skills: [verification-before-completion]   # a real marketplace skill
```

## The thesis

**The domain that created a standard owns its schema.** In Kubernetes, the
API group in `apiVersion` tells you who owns a resource's schema, and any
controller can consume it without translating it into something else. DNA
applies the same rule to agentic behavior: a Skill is identified as
`agentskills.io/v1 · Skill`, a Soul as `soulspec.org/v1 · Soul`, an
`AGENTS.md` as `agents.md/v1 · AgentDefinition` — the standard's owner keeps
the namespace and the format. Only the Kinds *we* invented live under
`github.com/ruinosus/dna/v1`.

**Behavior is data, not code.** Prompts, skill wiring, personas, guardrails
and composition rules live in YAML/Markdown files that are versioned,
diffed and reviewed like any other artifact. The SDK validates on write
(per-Kind JSON Schema) and composes on read (agent + soul + skills +
guardrails → one system prompt). Iterating on an agent never requires a
rebuild or redeploy of the software that runs it.

**The kernel knows no Kinds.** The runtime is a microkernel that mediates
five ports (source, cache, resolver, reader/writer, kind); *extensions*
register Kinds onto it. Adding a new Kind to your own domain is a
descriptor file or a small extension — no fork, no upstream PR, no
hardcoded kind strings anywhere in the kernel.

## Market fidelity

Standards DNA did not invent are consumed **byte-faithful, under their
owners' namespaces** — no conversion, no lossy import:

| Standard | apiVersion (owner) | Native bundle |
|---|---|---|
| Agent Skills | `agentskills.io/v1` | directory with `SKILL.md` (+ `scripts/`, `references/`) |
| Souls | `soulspec.org/v1` | `SOUL.md` + `IDENTITY.md` + `HEARTBEAT.md` (+ `soul.json`) |
| AGENTS.md | `agents.md/v1` | a plain `AGENTS.md` file |

This is enforced, not aspirational: the conformance suite runs against
**31 real marketplace Skills** (Anthropic + community, copied verbatim)
**plus the `openai/codex` `AGENTS.md`** and the soulspec starter templates —
scan → typed access → prompt composition → write round-trip, byte-identical.
Provenance: [`tests/market-fixtures/NOTICE.md`](tests/market-fixtures/NOTICE.md);
suites: `packages/sdk-py/tests/test_market_conformance.py` and
`packages/sdk-ts/tests/market-conformance.test.ts`; live fixture tree:
[`scopes/market-integration/`](scopes/market-integration/).

## Quick start

The snippets below run against [`examples/hello-genome`](examples/hello-genome/) —
a minimal scope with one `Genome`, one `Agent` and one real marketplace
Skill. Neither package is published to PyPI/npm yet; use them from the repo.

### Python

```bash
cd packages/sdk-py && uv sync
uv run python ../../examples/hello-genome/run.py
```

```python
from dna import Kernel

# Scan a scope: one call wires filesystem source/cache, resolvers,
# and every built-in extension. (Path relative to packages/sdk-py.)
mi = Kernel.quick("hello-genome", base_dir="../../examples/hello-genome/.dna")

for d in mi.documents:
    print(d.api_version, d.kind, d.name)

# Typed access to a real marketplace skill
skill = next(d for d in mi.documents if d.kind == "Skill")
print(skill.typed.metadata.description)

# Compose agent + skills into a system prompt
print(mi.build_prompt(agent="greeter"))
```

### TypeScript

```bash
cd packages/sdk-ts && bun install
bun run ../../examples/hello-genome/run.ts
```

```typescript
import { quickInstance } from "@dna/sdk";

// Path relative to packages/sdk-ts.
const mi = await quickInstance("hello-genome", "../../examples/hello-genome/.dna");

for (const d of mi.documents) {
  console.log(d.apiVersion, d.kind, d.name);
}

console.log(await mi.buildPrompt({ agent: "greeter" }));
```

Both print the same documents and the same composed prompt — behavioral
parity between the two SDKs is a test-enforced invariant, not a goal.

## Architecture in one screen

The kernel is a **mediator over five ports**:

| Port | Question it answers |
|---|---|
| **SourcePort** | Where do manifests live? (filesystem, SQLite, Postgres) |
| **CachePort** | Where are installed dependencies cached? |
| **ResolverPort** | How are external dependencies fetched? (`local:`, `github:`, `http(s):`) |
| **Reader/WriterPort** | How is a bundle format detected, scanned and written back? (`SKILL.md`, `SOUL.md`, `AGENTS.md`, YAML) |
| **KindPort** | What is this Kind's identity, schema and composition role? |

**Extensions register Kinds.** `kernel.load(ext)` is the only wiring step;
each extension contributes KindPorts (and readers/writers for bundle
formats). Record-style Kinds don't even need code — a `*.kind.yaml`
descriptor registers them declaratively, and the descriptor files are
byte-identical between the two SDKs (hash-enforced).

**Dual SDK, one behavior.** Python (`packages/sdk-py`) and TypeScript
(`packages/sdk-ts`) implement the same kernel 1:1 — same ports, same
composition rules, same outputs. Parity is enforced by shared fixtures,
descriptor hash checks and a kind-registry parity manifest that fails the
suite on undocumented drift.

## Kinds

Core Kinds (ours, `github.com/ruinosus/dna/...`):

| Kind | apiVersion | What it is |
|---|---|---|
| `Genome` | `github.com/ruinosus/dna/v1` | Scope root: identity, default agent, dependencies, layers |
| `Agent` | `github.com/ruinosus/dna/v1` | A prompt target: instruction + soul + skills + guardrails wiring |
| `Guardrail` | `github.com/ruinosus/dna/v1` | Safety/compliance rules composed into prompts |
| `Actor` / `UseCase` | `github.com/ruinosus/dna/v1` | Domain modeling: who interacts, and which flows exist |
| `Tool` | `github.com/ruinosus/dna/v1` | A callable capability an agent may invoke |
| `Hook` / `SafetyPolicy` / `Theme` / `Setting` / … | `github.com/ruinosus/dna/v1` | Runtime behavior, safety and UI preferences as data |
| `KindDefinition` | `github.com/ruinosus/dna/core/v1` | **A Kind that defines Kinds** — register new record Kinds with a YAML descriptor, no code |
| `LayerPolicy` | `github.com/ruinosus/dna/policy/v1` | Which layers (e.g. tenant overlays) may override which Kinds |
| `Tenant` / `TenantMembership` | `github.com/ruinosus/dna/tenant/v1` | First-class multi-tenancy, orthogonal to layers |
| `Evidence` / `AuditLog` / `Comment` / `MCPFederation` / `Recognizer` | various | Governance, audit, collaboration, federation, PII recognizers |

Market Kinds (theirs — native format, byte-faithful):

| Kind | apiVersion | Bundle |
|---|---|---|
| `Skill` | `agentskills.io/v1` | `SKILL.md` directory bundle |
| `Soul` | `soulspec.org/v1` | `SOUL.md` + companions |
| `AgentDefinition` | `agents.md/v1` | `AGENTS.md` |

## Your git log is your SDLC

This repo tracks its own lifecycle as DNA documents (`dna sdlc` — the
project's Stories/Features/Issues live in [`.dna/dna-development/`](.dna/dna-development/):
the repo IS the project, so its scope sits at the root, right where the
CLI's default source `./.dna` resolves). The git side of that loop is
closed by a versioned `prepare-commit-msg` hook:

```bash
dna sdlc hooks install        # one-time per clone → git config core.hooksPath scripts/git-hooks
dna sdlc story start s-my-story --plan "..."
git commit -m "feat: the actual work"   # ← stamped automatically
```

While a Story is active (`.dna/active-story.txt`, written by `story start`),
every commit is stamped with two trailers — a machine-readable link to the
work item, and the **dna sdlc tool identity** as co-author (a provenance
seal: "this commit was born under story governance — it has a plan, a
timeline, a test gate"; override via `DNA_SDLC_COAUTHOR`):

```
commit 3f2a9c1…
Author: You <you@example.com>

    feat(cli): stamp Work-Item trailers on commit

    Work-Item: Story/s-my-story
    Co-Authored-By: dna-sdlc[bot] <dna-sdlc[bot]@users.noreply.github.com>
```

No active Story → no stamp: absence is signal too. Merges, squashes and
amends are never rewritten. The way back needs no bookkeeping:
`dna sdlc story show s-my-story` lists the Story's commits via
`git log --grep "Work-Item: Story/s-my-story"`, and
`dna sdlc story commits s-my-story` merges that with commits recorded in
the Story timeline. `dna sdlc hooks status` shows the wiring;
`hooks uninstall` reverts to `.git/hooks`. Note that `install` makes
`scripts/git-hooks/` the clone's *only* hooks dir — keep personal hooks
there too, or wire the script by hand.

The same convention signs pull requests. Just as Claude Code signs the
PRs it generates, DNA signs the PRs born from its Stories:

```bash
dna sdlc story pr s-my-story          # gh pr create, pre-filled FROM the story
dna sdlc story pr s-my-story --dry-run   # print title + body, no gh call
dna sdlc pr-footer s-my-story         # just the footer, for hand-made PRs
```

`story pr` assembles the whole PR from the Story document — title
`feat(<first-label>): <story title> (<s-my-story>)`, body = the story
description plus the acceptance criteria as a task-list checklist, and
the attribution footer at the end (override the line via
`$DNA_SDLC_PR_FOOTER`):

```markdown
---
🧬 Tracked with [DNA SDLC](https://github.com/ruinosus/dna) — Work-Item: Story/s-my-story
```

`--base` / `--head` / `--draft` pass through to `gh`; on success the PR
URL is stamped back onto the Story timeline (`pr_opened`). The PR is
born from the story, not the other way around — and when it squash-merges,
the landed commit carries the `Work-Item:` trailer, so `story show`
lists it with zero bookkeeping.

## Repository layout

```
dna/
├── packages/
│   ├── sdk-py/          # Python SDK — kernel + adapters + extensions (import dna)
│   ├── sdk-ts/          # TypeScript SDK — 1:1 twin (@dna/sdk)
│   └── cli/             # `dna` binary — document CRUD + declarative SDLC (dna sdlc)
├── docs/                # Quick start, Kinds guide, Kind authoring, port contract
├── examples/
│   └── hello-genome/    # Minimal runnable scope (Genome + Agent + real Skill)
├── scopes/              # Fixture scopes, incl. 31 real marketplace skills
├── scripts/             # Repo guards + versioned git hooks (git-hooks/)
├── tests/               # Shared cross-SDK fixtures (parity + market conformance)
├── .dna/                # This repo's own SDLC scope (dna-development) — see above
└── LICENSE              # MIT
```

Docs: [Quick Start](docs/QUICK-START.md) ·
[Kinds Guide](docs/KINDS-GUIDE.md) ·
[Kind Authoring](docs/KIND-AUTHORING.md) ·
[Data Access](docs/KIND-DATA-ACCESS.md) ·
[Port Contract](docs/PORT-CONTRACT.md) ·
[Readers & Writers](docs/READERS-WRITERS-GUIDE.md)

## Status

This is the **extracted core of a production system**, not a greenfield
prototype: the kernel, the extension mechanism, multi-tenancy, layer
composition and the market-format readers/writers run in production today.
It is also **pre-1.0**: public APIs may still move, and the packages are
not yet on PyPI/npm. The full test suite (~2,900 tests across both SDKs,
including the market conformance suite) gates every change.

## License

[MIT](LICENSE)
