# How to consume prompts

Your app externalizes its agent instructions into a DNA scope. This guide is
about the *other* side of that: how the app **reads** the composed prompts back
out, cleanly, at boot.

## The one-liner

```python
from dna import load_prompts

prompts = load_prompts("helpdesk")          # boots a filesystem kernel for the scope
TRIAGE_INSTRUCTIONS = prompts["triage"]     # composed, clean — or raises
RESOLVE_INSTRUCTIONS = prompts["resolve"]
```

`dna load_prompts` returns a `PromptLibrary` — a lazy, cached, read-only mapping
from agent name to its **composed** system prompt. Each lookup runs the full
template cascade (Soul + Guardrails + Skills + the agent's own delta) and
returns the result already stripped of trailing whitespace. Ask for an agent
that does not exist and you get a typed error, never a placeholder string.

```python
"triage" in prompts     # True — cheap; does not compose
prompts.names()         # ['resolve', 'retrieve', 'triage', ...] (prompt-target docs)
```

`base_dir` follows the `Kernel.quick` convention — the directory that holds
`<scope>/` (your `.dna` scopes root). Omit it and it falls back to the
`DNA_BASE_DIR` environment variable, then `.dna` in the working directory:

```python
prompts = load_prompts("helpdesk", base_dir="/mnt/dna")   # explicit
prompts = load_prompts("helpdesk")                         # DNA_BASE_DIR or ./.dna
```

=== "TypeScript"

    Composition is async in TypeScript, so `get` returns a `Promise`:

    ```ts
    import { loadPrompts } from "@ruinosus/dna";

    const prompts = await loadPrompts("helpdesk");
    export const TRIAGE = await prompts.get("triage");   // composed, clean — or throws
    ```

## Fail loud: `AgentNotFound`

`build_prompt` — and therefore `load_prompts` — **raises** when an agent is
missing, instead of returning the string `"Agent 'X' not found"`:

```python
from dna import AgentNotFound

try:
    text = prompts["triage"]
except AgentNotFound as exc:
    # exc.agent == "triage"; a renamed/unparseable agent can never silently
    # become the literal instruction.
    raise
```

`AgentNotFound` is a `LookupError`, so `except LookupError` catches it too. In
TypeScript it is an `Error` subclass with an `.agent` property.

!!! note "Why this matters"
    Before this contract, a missing agent returned a placeholder string that
    passed a naive `if not text:` check and became the agent's actual
    instruction. Consumers defended against it by hand — booting the kernel,
    guarding every lookup with `mi.one("Agent", x) is None`, and `.rstrip("\n")`-ing
    every result. That ~166-line shim is exactly what `load_prompts` deletes.

## When you need more than prompts

`load_prompts` is a thin convenience over the kernel. When you need the full
surface — querying other kinds, tenant overlays, writes — reach for the
manifest instance directly (`prompts.mi`, or build your own with
`Kernel.quick` / [`Kernel.from_config`](configuring-ports.md)) and use the
[blessed query surface](read-document-data.md).
