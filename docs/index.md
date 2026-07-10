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

DNA ships as a **dual SDK** — Python (`import dna`) and TypeScript
(`dna-sdk`) — that implement the same kernel 1:1. Behavioral parity between
them is a test-enforced invariant, not a goal.

## Start here

These docs follow the [Diátaxis](https://diataxis.fr/) framework — four
kinds of documentation, each with one job.

<div class="grid cards" markdown>

- :material-school: **[Tutorials](getting-started/index.md)**

    Learning-oriented. Build your [first Kind and composed agent
    prompt](getting-started/first-kind.md) in ten minutes, Python and
    TypeScript side by side.

- :material-lightbulb-on: **[Concepts](concepts/index.md)**

    Understanding-oriented. Start with **[the thesis](concepts/thesis.md)** —
    "CRDs, but for agentic behavior" — then the Kinds model, the five ports,
    and market fidelity.

- :material-wrench: **[Guides](guides/index.md)**

    Task-oriented. How to [add a Kind](guides/add-a-kind.md), [write a source
    adapter](guides/write-a-source-adapter.md), [read document
    data](guides/read-document-data.md), and more.

- :material-file-document: **[Reference](reference/index.md)**

    Information-oriented. Per-language API reference, the CLI, and the parity
    matrix — *coming soon* (generated from source).

</div>

## The shape of the idea

| Claim | Where it lives |
|---|---|
| **The owner names the schema.** Standards DNA didn't invent are consumed byte-faithful under their owners' `apiVersion`. | [Market fidelity](concepts/market-fidelity.md) |
| **Behavior is data, not code.** Prompts, personas and wiring are versioned documents, validated on write and composed on read. | [The thesis](concepts/thesis.md) |
| **The kernel knows no Kinds.** A microkernel mediates five ports; extensions register Kinds onto it. | [Microkernel & ports](concepts/microkernel-ports.md) |
| **Your git log is your SDLC.** This repo tracks its own lifecycle as DNA documents, stamped onto every commit. | [The SDLC loop](guides/sdlc.md) |

## Status

DNA is the **extracted core of a production system**, not a greenfield
prototype: the kernel, the extension mechanism, multi-tenancy, layer
composition and the market-format readers/writers run in production today.

It is also **pre-1.0**: public APIs may still move, and the packages are not
yet on PyPI/npm. The full test suite (~2,900 tests across both SDKs,
including the market-conformance suite) gates every change.

The source lives at
[github.com/ruinosus/dna](https://github.com/ruinosus/dna).
