# DNA — Domain Notation of Anything

**Kubernetes CRDs, but for agentic behavior.**

DNA is a declarative, typed notation for everything that participates in an
agentic system — agents, skills, souls, guardrails, tools, policies. Every
participant is identified by `(apiVersion, kind)`, validated against a
per-Kind schema, and stored as versionable YAML/Markdown. **Changing an
agent is a file edit, not a deploy.**

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: Agent
metadata:
  name: greeter
spec:
  instruction: "You are Helio, a friendly assistant."
  skills: [verification-before-completion]   # a real marketplace skill
```

The **runtime is Python** (`import dna`). Every other language reaches the
same kernel through the **REST** and **MCP** faces, with typed clients
generated from the OpenAPI spec — so a client cannot drift from the runtime.

## Start here

These docs follow the [Diátaxis](https://diataxis.fr/) framework — four
kinds of documentation, each with one job.

<div class="grid cards" markdown>

- :material-school: **[Tutorials](getting-started/index.md)**

    Learning-oriented. Build your [first Kind and composed agent
    prompt](getting-started/first-kind.md) in ten minutes.

- :material-lightbulb-on: **[Concepts](concepts/index.md)**

    Understanding-oriented. Start with **[the thesis](concepts/thesis.md)** —
    "CRDs, but for agentic behavior" — then the Kinds model, the five ports,
    and market fidelity.

- :material-wrench: **[Guides](guides/index.md)**

    Task-oriented. How to [add a Kind](guides/add-a-kind.md), [write a source
    adapter](guides/write-a-source-adapter.md), [read document
    data](guides/read-document-data.md), and more.

- :material-file-document: **[Reference](reference/index.md)**

    Information-oriented. The Python API, the CLI and the Kinds catalog —
    all generated from source.

</div>

## The shape of the idea

| Claim | Where it lives |
|---|---|
| **The owner names the schema.** Standards DNA didn't invent are consumed byte-faithful under their owners' `apiVersion`. | [Market fidelity](concepts/market-fidelity.md) |
| **Behavior is data, not code.** Prompts, personas and wiring are versioned documents, validated on write and composed on read. | [The thesis](concepts/thesis.md) |
| **The kernel knows no Kinds.** A microkernel mediates five ports; extensions register Kinds onto it. | [Microkernel & ports](concepts/microkernel-ports.md) |
| **Your git log is your SDLC.** This repo tracks its own lifecycle as DNA documents, stamped onto every commit. | [The SDLC loop](guides/sdlc.md) |
| **Composes with Spec Kit, doesn't compete.** DNA names GitHub Spec Kit *the* supported spec-driven flow and sits beneath it — capturing a run's spec/plan/tasks + constitution as durable Kinds with memory, governance and board tracking. | [Spec Kit — the supported flow](guides/spec-kit.md) |

## Status

DNA is the **extracted core of a production system**, not a greenfield
prototype: the kernel, the extension mechanism, multi-tenancy, layer
composition and the market-format readers/writers run in production today.

It is also **pre-1.0**: public APIs may still move, and the packages are not
yet on PyPI/npm. The full test suite (thousands of tests, including the
market-conformance suite and the golden fixtures) gates every change.

The source lives at
[github.com/ruinosus/dna](https://github.com/ruinosus/dna).
