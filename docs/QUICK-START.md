# Quick Start

Get from zero to a working agent prompt in 5 minutes.

## Prerequisites

- **Python 3.9+** with [uv](https://docs.astral.sh/uv/) — or **Bun 1.0+** for TypeScript

## Step 1: Install

```bash
# Python
cd python && uv sync

# TypeScript
cd typescript && bun install
```

## Step 2: Create a manifest

Create the following directory structure:

```bash
mkdir -p .dna/hello/agents .dna/hello/skills/greeting .dna/hello/souls/assistant
```

### Module root

**`.dna/hello/manifest.yaml`**
```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: Module
metadata:
  name: hello
  description: Hello World module
spec:
  default_agent: assistant
```

### Agent definition

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

### Skill bundle

**`.dna/hello/skills/greeting/SKILL.md`**
```markdown
---
name: greeting
description: Greet users warmly
---
When a user says hello, greet them warmly and ask how you can help.
Adapt your greeting to their language if possible.
```

### Soul (personality)

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

## Step 3: Load the manifest

### Python

```python
from dna.kernel import Kernel

# Load the manifest
mi = Kernel.quick("hello", base_dir=".dna")

# Query documents
print(f"Module: {mi.scope}")
print(f"Agents: {[a.name for a in mi.all('Agent')]}")
print(f"Skills: {[s.name for s in mi.all('Skill')]}")
print(f"Souls:  {[s.name for s in mi.all('Soul')]}")
```

**Expected output:**
```
Module: hello
Agents: ['assistant']
Skills: ['greeting']
Souls:  ['assistant']
```

### TypeScript

```typescript
import { Kernel } from "dna-sdk";

const mi = Kernel.quick("hello", ".dna");

console.log(`Module: ${mi.scope}`);
console.log(`Agents: ${mi.all("Agent").map(a => a.name)}`);
console.log(`Skills: ${mi.all("Skill").map(s => s.name)}`);
console.log(`Souls:  ${mi.all("Soul").map(s => s.name)}`);
```

## Step 4: Build a prompt

The SDK composes the agent's instruction with its soul into a single system prompt:

### Python

```python
prompt = mi.build_prompt(agent="assistant")
print(prompt)
```

**Expected output:**
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

### TypeScript

```typescript
const prompt = mi.buildPrompt({ agent: "assistant" });
console.log(prompt);
```

The prompt is composed from:
1. **Agent instruction** (`spec.instruction` from Agent)
2. **Soul content** (`soul_content` from the Soul referenced by `spec.soul`)

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

That's it. Change the YAML/Markdown files to update behavior — no code changes, no redeploy.

---

## Next Steps

- **[API Reference (Python)](../python/dna/README.md)** — Full Kernel, ManifestInstance, Document API
- **[API Reference (TypeScript)](../typescript/README.md)** — TypeScript equivalent
- **[Architecture](ARCHITECTURE-REVIEW.md)** — Deep dive into the 5-port microkernel
- **[Examples](../examples/)** — Real-world manifest fixtures
- **[Layers](CENARIO-TESTE-LAYERS.md)** — Multi-tenant overlays
