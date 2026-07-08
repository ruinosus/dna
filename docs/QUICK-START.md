# Quick Start

Zero to a composed agent prompt in 5 minutes. If you'd rather read a
finished scope, [`examples/hello-genome/`](../examples/hello-genome/) is
this guide in runnable form.

## Prerequisites

- **Python 3.10+** with [uv](https://docs.astral.sh/uv/) — or **Bun 1.0+** for TypeScript

## Step 1: Install

```bash
# Python
cd packages/sdk-py && uv sync

# TypeScript
cd packages/sdk-ts && bun install
```

## Step 2: Create a scope

A **scope** is a directory of manifests under `.dna/<scope-name>/`. Create:

```bash
mkdir -p .dna/hello/agents .dna/hello/skills/greeting .dna/hello/souls/assistant
```

### Scope root (Genome)

Every scope is rooted by a `Genome` — its identity document.

**`.dna/hello/Genome.yaml`**
```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata:
  name: hello
  description: Hello World scope
spec:
  default_agent: assistant
```

### Agent

**`.dna/hello/agents/assistant.yaml`**
```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: Agent
metadata:
  name: assistant
  description: A friendly assistant that greets users
spec:
  instruction: |
    You are a helpful assistant named Alex.
    You help users with their questions clearly and concisely.
  skills: [greeting]
  soul: assistant
```

### Skill bundle (agentskills.io format)

**`.dna/hello/skills/greeting/SKILL.md`**
```markdown
---
name: greeting
description: Greet users warmly
---
When a user says hello, greet them warmly and ask how you can help.
Adapt your greeting to their language if possible.
```

### Soul (soulspec.org format)

**`.dna/hello/souls/assistant/SOUL.md`**
```markdown
## Personality
Friendly, approachable, and patient. Explains things clearly.

## Tone
Conversational but professional. Uses simple language.

## Principles
- Always be helpful
- Admit when you don't know something
- Keep responses concise
```

Note the namespaces: the Skill and the Soul are **market formats** — DNA
reads them natively under their owners' apiVersions (`agentskills.io/v1`,
`soulspec.org/v1`). Only `Genome` and `Agent` are DNA's own Kinds.

## Step 3: Load the scope

### Python

```python
from dna import Kernel

mi = Kernel.quick("hello", base_dir=".dna")

print(f"scope: {mi.scope}")
for d in mi.documents:
    print(f"  {d.api_version:32s} {d.kind:8s} {d.name}")
```

### TypeScript

```typescript
import { quickInstance } from "@dna/sdk";

const mi = await quickInstance("hello", ".dna");

console.log(`scope: ${mi.scope}`);
for (const d of mi.documents) {
  console.log(`  ${d.apiVersion.padEnd(32)} ${d.kind.padEnd(8)} ${d.name}`);
}
```

**Both print exactly:**
```
scope: hello
  agentskills.io/v1                Skill    greeting
  soulspec.org/v1                  Soul     assistant
  github.com/ruinosus/dna/v1       Genome   hello
  github.com/ruinosus/dna/v1       Agent    assistant
```

`Kernel.quick()` / `quickInstance()` auto-wire the filesystem source and
cache, the default resolvers (`local:`, `github:`, `http(s):`), and every
built-in extension.

> You may see a log line about the `_lib` parent scope: every scope can
> inherit shared documents from a sibling `.dna/_lib/` library scope.
> Create the (empty) directory to silence it, or put shared agents/skills
> there to actually use it.

## Step 4: Build a prompt

The SDK composes the agent's instruction with its soul (and any
template-driven sections) into a single system prompt:

### Python

```python
prompt = mi.build_prompt(agent="assistant")
print(prompt)
```

### TypeScript

```typescript
const prompt = await mi.buildPrompt({ agent: "assistant" });
console.log(prompt);
```

**Expected output (identical in both SDKs):**
```
You are a helpful assistant named Alex.
You help users with their questions clearly and concisely.


## Personality
Friendly, approachable, and patient. Explains things clearly.

## Tone
Conversational but professional. Uses simple language.

## Principles
- Always be helpful
- Admit when you don't know something
- Keep responses concise
```

The composition is driven by the Kind system: the Agent's `spec.soul`
reference selects the Soul via `dep_filters`, the Soul's
`flatten_in_context` flag promotes `soul_content` into the template
context, and the Agent's prompt template renders both. See
[KINDS-GUIDE.md](KINDS-GUIDE.md) for the full model.

## Step 5: Use with your LLM

Pass the prompt as the system message to any LLM:

```python
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": mi.build_prompt(agent="assistant")},
        {"role": "user", "content": "Hello!"},
    ],
)
print(response.choices[0].message.content)
```

That's it. Change the YAML/Markdown files to update behavior — no code
changes, no redeploy.

---

## Next Steps

- **[Kinds Guide](KINDS-GUIDE.md)** — the identity + composition model
- **[Kind Authoring](KIND-AUTHORING.md)** — ship your own Kind in 30 minutes
- **[Data Access](KIND-DATA-ACCESS.md)** — the unified way to read Document fields
- **[examples/hello-genome](../examples/hello-genome/)** — this guide as a runnable scope with a real marketplace skill
- **[scopes/market-integration](../scopes/market-integration/)** — 31 real marketplace skills loaded verbatim
