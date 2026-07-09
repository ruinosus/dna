# DNA — Domain Notation of Anything

[![python](https://github.com/ruinosus/dna/actions/workflows/python.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/python.yml)
[![typescript](https://github.com/ruinosus/dna/actions/workflows/typescript.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/typescript.yml)
[![guards](https://github.com/ruinosus/dna/actions/workflows/guards.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/guards.yml)
[![docs](https://github.com/ruinosus/dna/actions/workflows/docs.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/docs.yml)
[![status: pre-1.0](https://img.shields.io/badge/status-pre--1.0-orange)](#status)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Kubernetes CRDs, but for agentic behavior.**

> DNA is a declarative, typed notation for everything that participates in an
> agentic system — agents, skills, souls, guardrails, tools, policies. Every
> participant is identified by `(apiVersion, kind)`, validated against a
> per-Kind schema, and stored as versionable YAML/Markdown. **The `spec` you
> author is intent; the composed prompt is derived. Changing an agent is a
> file edit, not a deploy.**

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

📖 **Full documentation: [ruinosus.github.io/dna](https://ruinosus.github.io/dna/)**
· [The thesis](https://ruinosus.github.io/dna/concepts/thesis/)
· [Your first Kind](https://ruinosus.github.io/dna/getting-started/first-kind/)

## Quick start

The snippets below run against [`examples/hello-genome`](examples/hello-genome/) —
a minimal scope with one `Genome`, one `Agent` and one real marketplace
Skill. Neither package is published to PyPI/npm yet; use them from the repo.
Python and TypeScript do the same thing — that parity is a test-enforced
invariant, not a goal.

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

# Compose agent + skills into a system prompt — the observed state,
# derived from the authored spec.
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

Both print the same documents and the same composed prompt. Walk through it
step by step in **[Your first Kind](https://ruinosus.github.io/dna/getting-started/first-kind/)**.

## The idea in four claims

| Claim | Read more |
|---|---|
| **The owner names the schema.** A Skill is `agentskills.io/v1`, a Soul `soulspec.org/v1`, an `AGENTS.md` `agents.md/v1` — standards DNA didn't invent are consumed **byte-faithful** under their owners' namespaces, enforced against 31 real marketplace bundles. | [Market fidelity](https://ruinosus.github.io/dna/concepts/market-fidelity/) |
| **Behavior is data, not code.** Prompts, personas and wiring are versioned documents — validated on write, composed on read. Iterating never rebuilds the runtime. | [The thesis](https://ruinosus.github.io/dna/concepts/thesis/) |
| **The kernel knows no Kinds.** A microkernel mediates five ports (source, cache, resolver, reader/writer, kind); extensions register Kinds onto it. A record Kind is a descriptor file — no fork, no code. | [Microkernel & ports](https://ruinosus.github.io/dna/concepts/microkernel-ports/) |
| **Dual SDK, one behavior.** Python (`import dna`) and TypeScript (`@dna/sdk`) implement the same kernel 1:1 — parity enforced by shared fixtures and descriptor hash checks. | [Concepts](https://ruinosus.github.io/dna/concepts/) |

## Your git log is your SDLC

This repo tracks its own lifecycle as DNA documents (`dna sdlc`): its
Stories/Features/Issues live in [`.dna/dna-development/`](.dna/dna-development/),
and a versioned `prepare-commit-msg` hook stamps every commit born under a
Story with a `Work-Item:` trailer — so tracing the work back is a `git log`
query, not bookkeeping. The same convention signs the PRs.
→ **[The SDLC loop](https://ruinosus.github.io/dna/guides/sdlc/)**.

## Semantic search & memory, embedded

Every scope is semantically searchable, and agents get durable memory
(`remember` / `recall` / `forget` / `consolidate`) — offline, inside the SDK.
No vector database service, no embeddings API: sqlite-vec + FTS5 + RRF in one
file per scope, with pgvector as the same-contract scale adapter.

```console
$ dna recall "reciprocal rank fusion" --kind Story -k 1

🔎 hybrid (dense+lexical+RRF) · scope=dna-development · 'reciprocal rank fusion'
   1. Story/s-search-pgvector  (0.0297)
```

→ **[Search & memory](https://ruinosus.github.io/dna/concepts/search-and-memory/)** (the model)
· **[How to use semantic recall](https://ruinosus.github.io/dna/guides/semantic-recall/)** (the recipe).

## Documentation

The full site is organized by [Diátaxis](https://diataxis.fr/):

- **Tutorials** — [Your first Kind](https://ruinosus.github.io/dna/getting-started/first-kind/) · [Running the conformance kit](https://ruinosus.github.io/dna/getting-started/conformance-kit/)
- **Concepts** — [The thesis](https://ruinosus.github.io/dna/concepts/thesis/) · [Kinds](https://ruinosus.github.io/dna/concepts/kinds/) · [Microkernel & ports](https://ruinosus.github.io/dna/concepts/microkernel-ports/) · [Market fidelity](https://ruinosus.github.io/dna/concepts/market-fidelity/) · [Tenancy & layers](https://ruinosus.github.io/dna/concepts/tenancy-layers/) · [Search & memory](https://ruinosus.github.io/dna/concepts/search-and-memory/)
- **How-to guides** — [Add a Kind](https://ruinosus.github.io/dna/guides/add-a-kind/) · [Read document data](https://ruinosus.github.io/dna/guides/read-document-data/) · [Write a source adapter](https://ruinosus.github.io/dna/guides/write-a-source-adapter/) · [Write a Reader/Writer](https://ruinosus.github.io/dna/guides/readers-and-writers/) · [Semantic recall & memory](https://ruinosus.github.io/dna/guides/semantic-recall/)
- **Reference** — per-language API, CLI and parity matrix, generated from source *(coming soon)*

Building the site locally:

```bash
pip install -r requirements-docs.txt
mkdocs serve        # live preview at http://127.0.0.1:8000
```

## Repository layout

```
dna/
├── packages/
│   ├── sdk-py/          # Python SDK — kernel + adapters + extensions (import dna)
│   ├── sdk-ts/          # TypeScript SDK — 1:1 twin (@dna/sdk)
│   └── cli/             # `dna` binary — document CRUD + declarative SDLC (dna sdlc)
├── docs/                # Diátaxis docs site (MkDocs + Material)
├── examples/
│   └── hello-genome/    # Minimal runnable scope (Genome + Agent + real Skill)
├── scopes/              # Fixture scopes, incl. 31 real marketplace skills
├── scripts/             # Repo guards + versioned git hooks (git-hooks/)
├── tests/               # Shared cross-SDK fixtures (parity + market conformance)
├── .dna/                # This repo's own SDLC scope (dna-development)
└── LICENSE              # MIT
```

## Status

DNA is the **extracted core of a production system**, not a greenfield
prototype: the kernel, the extension mechanism, multi-tenancy, layer
composition and the market-format readers/writers run in production today.

It is also **pre-1.0**: public APIs may still move, and the packages are not
yet on PyPI/npm. The full test suite (~2,900 tests across both SDKs,
including the market-conformance suite) gates every change.

## License

[MIT](LICENSE)
