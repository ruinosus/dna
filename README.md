# DNA — Domain Notation of Anything

[![python](https://github.com/ruinosus/dna/actions/workflows/python.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/python.yml)
[![typescript](https://github.com/ruinosus/dna/actions/workflows/typescript.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/typescript.yml)
[![guards](https://github.com/ruinosus/dna/actions/workflows/guards.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/guards.yml)
[![docs](https://github.com/ruinosus/dna/actions/workflows/docs.yml/badge.svg)](https://github.com/ruinosus/dna/actions/workflows/docs.yml)
[![status: pre-1.0](https://img.shields.io/badge/status-pre--1.0-orange)](#status)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Define your agents as files. Version them in git. Serve them to any AI tool.**

Today an agent's behavior — its prompt, persona, guardrails, tools, memory —
usually lives buried in application code. Changing how the agent behaves means
a code change and a redeploy, and every runtime (Claude, Cursor, LangGraph,
your own app) needs its own copy.

DNA turns all of that into plain YAML/Markdown documents you keep in your
repo. You edit a file, and the change is live: the same definitions can be
composed into a system prompt, served to Claude or Cursor over MCP, exposed
as a REST API, or exported to a framework's native format. Skills from public
marketplaces install as-is, your team's workflow travels with the repo, and
agents get durable memory and semantic search with no external services.

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

## Install

```bash
pip install dna-sdk dna-cli      # the runtime: Python SDK + the `dna` CLI
npm install dna-client           # TypeScript client for the REST API
pip install dna-client           # Python client for the REST API
```

The runtime is Python; everything else talks to it over REST or MCP, so you
can use DNA from any language (see
[Use DNA from any language](#use-dna-from-any-language)).

## Quick start

Run the bundled example — one agent, one real marketplace skill — straight
from a repo checkout:

```bash
git clone https://github.com/ruinosus/dna && cd dna
cd packages/sdk-py && uv sync
uv run python ../../examples/hello-genome/run.py
```

You'll see the documents in the scope and the agent's composed system prompt.
The same thing in Python:

```python
from dna import Kernel

mi = Kernel.quick("hello-genome", base_dir="../../examples/hello-genome/.dna")

for d in mi.documents:
    print(d.api_version, d.kind, d.name)

# The prompt is derived from the documents — edit the YAML, get new behavior.
print(mi.build_prompt(agent="greeter"))
```

Walk through it step by step in
**[Your first Kind](https://ruinosus.github.io/dna/getting-started/first-kind/)**.

## What you can do with it

**Serve your agents to Claude, Cursor, or any MCP client.**
`dna mcp serve` exposes everything in your scope — agents composed live and
per-tenant, tools, memory, the work board — over MCP. Edit a document, and the
next call reflects it: no redeploy.
→ [The MCP server](https://ruinosus.github.io/dna/guides/mcp-server/)

**Change an agent by editing a file, not shipping code.**
Prompts, personas, guardrails and wiring are versioned documents, validated on
write and composed on read. A behavior change is a diff you can review.
→ [Authoring agents](https://ruinosus.github.io/dna/guides/authoring-agents/)

**Install skills and complete copilots from any repo.**
`dna install github:anthropics/skills/skills/pdf` pulls real marketplace
skills into your scope, validated as untrusted input with pinned provenance.
`dna copilot install <kit>` installs an entire guided flow — domain Kind,
agent, wizard — as documents, no code shipped.
→ [Installing bundles](https://ruinosus.github.io/dna/guides/installing-scopes/)
· [Copilot kits](https://ruinosus.github.io/dna/guides/copilot-kits/)

**Give your agents memory and semantic search — offline.**
`dna memory remember / recall / forget / consolidate`, plus hybrid semantic
search over every scope (`dna recall "..."`). No vector database service, no
embeddings API: one local file per scope, with Postgres/pgvector as the
same-contract scale adapter.
→ [Search & memory](https://ruinosus.github.io/dna/concepts/search-and-memory/)

**Track your team's work as files in git.**
`dna sdlc` runs a full lifecycle board (stories, features, issues, ADRs) as
documents in your repo, and a git hook stamps every commit with the story it
belongs to — tracing work back is a `git log` query. This repo tracks itself
this way ([`.dna/dna/`](.dna/dna/)).
→ [The SDLC loop](https://ruinosus.github.io/dna/guides/sdlc/)

**Export an agent to your framework's native format.**
`dna emit <agent> --target agent-framework` (or `agno`) turns a DNA agent
into the artifact that runtime consumes — useful when you need a static
build instead of a live server.
→ [Emitting to a runtime](https://ruinosus.github.io/dna/guides/emitting-to-a-runtime/)

**Make any repository agent-ready in one command.**
`dna init` projects a canonical `AGENTS.md` (read by 28+ tools) and the
story-first workflow into every agent tool's directory (`.claude/skills/`,
`.github/skills/`, …) and wires the git hooks — idempotent and regenerable.
Distribute your own conventions with `dna init --from github:owner/repo`.
→ [Make your project agent-ready](https://ruinosus.github.io/dna/getting-started/agent-onboarding/)

## Use DNA from any language

The runtime is Python; it serves two language-neutral faces, and everything
else is a client of them:

| Face | Serve it with | Consume it from |
|---|---|---|
| **REST** — typed read/write over HTTP, OpenAPI-described | `dna api serve` | `dna-client` for [TypeScript](packages/client-ts/) and [Python](packages/client-py/) — both generated from the same [`docs/openapi.json`](docs/openapi.json) — or any HTTP client |
| **MCP** — the tool face agents speak natively | `dna mcp serve` | Claude, Cursor, or any MCP client |

```typescript
import { DnaClient } from "dna-client";

const dna = new DnaClient({ baseUrl: "http://127.0.0.1:8080" });
const agents = await dna.listDocuments({ scope: "hello-genome", kind: "Agent" });
```

Agent-to-agent (A2A) is also covered: DNA mounts the official `a2a-sdk`
routes onto the served API (`dna-cli[a2a]` extra).

## Where things come from — and why they stay compatible

DNA doesn't reinvent formats it didn't create. A Skill is `agentskills.io/v1`,
an `AGENTS.md` is `agents.md/v1` — standards are consumed **byte-faithful**
under their owners' namespaces, enforced against 31 real marketplace bundles
in the test suite. What you install from the ecosystem works unmodified, and
what you author here stays portable.
→ [Market fidelity](https://ruinosus.github.io/dna/concepts/market-fidelity/)

## Documentation

The full site is organized by [Diátaxis](https://diataxis.fr/):

- **Tutorials** — [Your first Kind](https://ruinosus.github.io/dna/getting-started/first-kind/) · [Running the conformance kit](https://ruinosus.github.io/dna/getting-started/conformance-kit/) · [Make your project agent-ready](https://ruinosus.github.io/dna/getting-started/agent-onboarding/)
- **Concepts** — [The thesis](https://ruinosus.github.io/dna/concepts/thesis/) · [Kinds](https://ruinosus.github.io/dna/concepts/kinds/) · [Microkernel & ports](https://ruinosus.github.io/dna/concepts/microkernel-ports/) · [Market fidelity](https://ruinosus.github.io/dna/concepts/market-fidelity/) · [Tenancy & layers](https://ruinosus.github.io/dna/concepts/tenancy-layers/) · [Search & memory](https://ruinosus.github.io/dna/concepts/search-and-memory/)
- **How-to guides** — [A tour of the CLI](https://ruinosus.github.io/dna/guides/cli-tour/) · [Install bundles from a repo](https://ruinosus.github.io/dna/guides/installing-scopes/) · [Add a Kind](https://ruinosus.github.io/dna/guides/add-a-kind/) · [Semantic recall & memory](https://ruinosus.github.io/dna/guides/semantic-recall/) · [Evaluate agents](https://ruinosus.github.io/dna/guides/evaluating-agents/) · [the full list](https://ruinosus.github.io/dna/guides/)
- **Reference** — the [Python API](https://ruinosus.github.io/dna/reference/python/), the [CLI](https://ruinosus.github.io/dna/reference/cli/) and the [Kinds catalog](https://ruinosus.github.io/dna/reference/kinds/) — all generated from source on every build

For how the internals work — the kernel, its ports, the extension mechanism —
start at [Microkernel & ports](https://ruinosus.github.io/dna/concepts/microkernel-ports/)
and [`AGENTS.md`](AGENTS.md) (build/test commands, layout, conventions).

Building the site locally:

```bash
pip install -r requirements-docs.txt
mkdocs serve        # live preview at http://127.0.0.1:8000
```

## Repository layout

```
dna/
├── packages/
│   ├── sdk-py/          # THE runtime (import dna)
│   ├── cli/             # `dna` binary — CRUD, SDLC, init, install, mcp/api serve
│   ├── client-py/       # REST client for Python  ┐ both generated from
│   └── client-ts/       # REST client for TypeScript ┘ docs/openapi.json
├── docs/                # Diátaxis docs site (MkDocs + Material)
├── examples/
│   └── hello-genome/    # Minimal runnable scope (Genome + Agent + real Skill)
├── copilot-kits/        # Installable copilot flows (dna copilot install)
├── scopes/              # Fixture scopes, incl. 31 real marketplace skills
├── scripts/             # Repo guards + versioned git hooks (git-hooks/)
├── tests/               # Golden fixtures (behavioral + market conformance)
├── .dna/                # This repo's own SDLC scope (dna)
└── LICENSE              # MIT
```

## Status

DNA is the **extracted core of a production system**, not a greenfield
prototype: the definitions model, multi-tenancy, layer composition and the
market-format readers/writers run in production today.

It is also **pre-1.0**: `dna-sdk` + `dna-cli` publish to PyPI and
`dna-client` to npm and PyPI (see [RELEASING.md](RELEASING.md)), and until
1.0 the public API may still move between releases. The full test suite —
including the market-conformance suite against real marketplace bundles —
gates every change.

## License

[MIT](LICENSE)
