# Your first Kind

In about ten minutes you will load a DNA **scope**, get typed access to a
real marketplace **Skill**, and compose an **Agent**'s system prompt — all
from YAML/Markdown files, with no code change to alter behavior.

Everything here runs against
[`examples/hello-genome`](https://github.com/ruinosus/dna/tree/main/examples/hello-genome),
a minimal scope with one `Genome`, one `Agent`, and one real marketplace
Skill. The Python and TypeScript SDKs do exactly the same thing — that
parity is the point, so this tutorial shows both side by side.

## Prerequisites

=== "Python"

    - **Python 3.12+** with [uv](https://docs.astral.sh/uv/).

    ```bash
    cd packages/sdk-py && uv sync
    ```

=== "TypeScript"

    - **Bun 1.0+**.

    ```bash
    cd packages/sdk-ts && bun install
    ```

The packages are not published to PyPI/npm yet — use them from the repo.

## Step 1 — A scope is a directory of manifests

A **scope** is a directory of documents under `.dna/<scope-name>/`. The
`hello-genome` scope looks like this:

```
.dna/
└── hello-genome/
    ├── Genome.yaml            # scope root: identity + default agent
    ├── agents/
    │   └── greeter.yaml       # kind: Agent — instruction + skill wiring
    └── skills/
        └── verification-before-completion/
            └── SKILL.md        # kind: Skill — a real marketplace bundle
```

Three documents, three Kinds. Note the namespaces: `Genome` and `Agent` are
DNA's own Kinds (`github.com/ruinosus/dna/v1`), while the Skill is a **market
format** — DNA reads it byte-faithful under its owner's namespace,
`agentskills.io/v1`. (Why that matters: [Market
fidelity](../concepts/market-fidelity.md).)

### The scope root (Genome)

Every scope is rooted by exactly one `Genome` — its identity document.

```yaml title=".dna/hello-genome/Genome.yaml"
apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata:
  name: hello-genome
spec:
  default_agent: greeter
```

### The Agent

The Agent declares an instruction and *references* a skill by name. It does
not inline the skill's text — that composition happens on read.

```yaml title=".dna/hello-genome/agents/greeter.yaml"
apiVersion: github.com/ruinosus/dna/v1
kind: Agent
metadata:
  name: greeter
spec:
  instruction: |
    You are Helio, a friendly assistant.
  skills: [verification-before-completion]
```

## Step 2 — Load the scope

`Kernel.quick()` / `quickInstance()` auto-wire the filesystem source and
cache, the default resolvers (`local:`, `github:`, `http(s):`), and every
built-in extension. One call gives you a `ManifestInstance` (`mi`) — the
query surface over the loaded scope.

=== "Python"

    ```python
    from dna import Kernel

    mi = Kernel.quick("hello-genome", base_dir="examples/hello-genome/.dna")

    print(f"scope: {mi.scope}")
    for d in mi.documents:
        print(f"  {d.api_version:32s} {d.kind:8s} {d.name}")
    ```

=== "TypeScript"

    ```typescript
    import { quickInstance } from "@dna/sdk";

    const mi = await quickInstance("hello-genome", "examples/hello-genome/.dna");

    console.log(`scope: ${mi.scope}`);
    for (const d of mi.documents) {
      console.log(`  ${d.apiVersion.padEnd(32)} ${d.kind.padEnd(8)} ${d.name}`);
    }
    ```

Both print exactly the same thing — every document identified by
`(apiVersion, kind, name)`:

```
scope: hello-genome
  agentskills.io/v1                Skill    verification-before-completion
  github.com/ruinosus/dna/v1       Genome   hello-genome
  github.com/ruinosus/dna/v1       Agent    greeter
```

!!! tip "The `_lib` parent scope"

    You may see a log line about a `_lib` parent scope: every scope can
    inherit shared documents from a sibling `.dna/_lib/` library scope.
    Create the (empty) directory to silence it, or put shared agents/skills
    there to actually use it. See [Tenancy and
    layers](../concepts/tenancy-layers.md).

## Step 3 — Typed access to a Kind

`mi.documents` is the [blessed query surface](../guides/read-document-data.md):
filter by `kind` and `name`, then read typed fields.

=== "Python"

    ```python
    skill = next(d for d in mi.documents if d.kind == "Skill")
    print(skill.typed.metadata.name)
    print(skill.typed.metadata.description)
    ```

=== "TypeScript"

    ```typescript
    const skill = mi.documents.find((d) => d.kind === "Skill")!;
    console.log(skill.name);
    ```

The Skill's frontmatter was parsed into a typed model — you did not need to
know anything about the `agentskills.io` format to read it.

## Step 4 — Compose a prompt

Now the payoff. The Agent references a skill; the SDK composes the Agent's
instruction with its wired-in Kinds into a single system prompt, on read:

=== "Python"

    ```python
    print(mi.build_prompt(agent="greeter"))
    ```

=== "TypeScript"

    ```typescript
    console.log(await mi.buildPrompt({ agent: "greeter" }));
    ```

You never wrote that composed prompt down — it is *derived* from the
authored `spec`. That is the [thesis](../concepts/thesis.md) in one call: the
document is intent; the prompt is the observed state the kernel reconciles
into.

## Step 5 — Change behavior with a file edit

Open `agents/greeter.yaml`, change the instruction or the wired skills, and
re-run Step 4. The prompt changes — with **no rebuild and no redeploy**.
That is the whole of it: behavior is data.

## Run the finished example

The steps above are packaged as a runnable script in the repo, exercised by
both SDKs' test suites so it can never silently rot:

=== "Python"

    ```bash
    cd packages/sdk-py && uv sync
    uv run python ../../examples/hello-genome/run.py
    ```

=== "TypeScript"

    ```bash
    cd packages/sdk-ts && bun install
    bun run ../../examples/hello-genome/run.ts
    ```

## Next steps

- **[Kinds — the identity and composition model](../concepts/kinds.md)** —
  how `dep_filters` and templates drive the composition you just saw.
- **[How to add a Kind](../guides/add-a-kind.md)** — ship your own Kind in
  thirty minutes.
- **[How to read document data](../guides/read-document-data.md)** — the
  unified read surface across both SDKs.
- **[How to use semantic recall & memory](../guides/semantic-recall.md)** —
  search the scope you just loaded with `dna recall`, offline.
- **[Running the conformance kit](conformance-kit.md)** — prove the
  byte-faithful, dual-SDK claims for yourself.
