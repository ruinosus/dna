# Kind Data Access Pattern

The DNA SDK has a unified way to read data from Documents of any kind.
Follow it so your code doesn't break when kinds evolve, and so you
don't need to know a kind's typed model to work with it.

## The blessed query surface (pre-1.0 contract)

There is exactly ONE documented way to read manifest data
(s-blessed-query-surface). Everything the docs and examples teach uses
these members — and the parity fixture
`tests/parity-fixtures/port-surface-parity.json` (section
`blessed_query_surface`) locks them on both sides:

| Read | Python | TypeScript |
|---|---|---|
| All loaded docs (in-memory) | `mi.documents` | `mi.documents` |
| Docs of a kind | `[d for d in mi.documents if d.kind == "Skill"]` | `mi.documents.filter((d) => d.kind === "Skill")` |
| Single doc | `next((d for d in mi.documents if d.kind == "Skill" and d.name == "x"), None)` | `mi.documents.find((d) => d.kind === "Skill" && d.name === "x") ?? null` |
| Indexed / record-plane query | `await kernel.query(scope, kind, ...)` | `for await (... of kernel.query(scope, kind, opts))` |
| Aggregation | `await kernel.count(scope, kind, ...)` | `await kernel.count(scope, kind, opts)` |
| Single doc, indexed (L2-cached) | `await kernel.get_document(scope, kind, name)` | — (use `kernel.query` with a filter) |
| Root / default agent | `mi.root` / `mi.default_agent()` / `mi.find_agent(name)` | `mi.root` / `mi.defaultAgent()` / `mi.findAgent(name)` |
| Prompt composition | `mi.build_prompt(...)` (`build_prompt_async` from a loop) | `await mi.buildPrompt(...)` |
| Layer overlays | `mi.resolve(layers)` (`resolve_async` from a loop) | `mi.resolve(layers)` |

Rule of thumb: `mi.documents` for the scope you already loaded;
`kernel.query`/`kernel.count` when you need push-down filtering,
pagination, tenant overlays, or record-plane kinds that are not part of
the loaded manifest.

**Deprecated (removed in 1.0):** `mi.all(kind)` and `mi.one(kind, name)`
still work but warn — Python raises a `DeprecationWarning`, TypeScript
`console.warn`s once per process — always naming the replacement above.
Don't use them in new code; don't teach them.

## Python

Two coexisting forms. Pick based on whether you already hold a
`Document` reference.

### Form 1: `mi.read_spec(...)` — sugar for single-field reads

Use when you only need one field and don't want to keep a Document
around:

```python
# GOOD — one-liner facade on ManifestInstance
soul_ref = mi.read_spec("Agent", "foo", "soul")
skills = mi.read_spec_list("Agent", "foo", "skills")
description = mi.read_metadata("Agent", "foo", "description")
```

Raises `KeyError` if the `(kind, name)` doesn't resolve. Returns the
`default` (or `None`) for missing fields.

### Form 2: `Document.spec.get(...)` — when you already hold a handle

Use when you need multiple fields from the same doc, or when the code
already holds a `Document` reference (from `mi.documents` or a
`kernel.query` row):

```python
# GOOD — kind-agnostic, works for any Document
agent = next(d for d in mi.documents if d.kind == "Agent" and d.name == "foo")
soul_ref = agent.spec.get("soul")
skills = agent.spec.get("skills") or []
description = agent.metadata.get("description")

# AVOID — attribute form is technically supported, but hides the fact
# that 'soul' is a raw spec key (not a real Python attribute). New devs
# reading the code assume it's a typed model attribute.
soul_ref = agent.spec.soul

# AVOID — getattr() is equivalent to .get() but more verbose
soul_ref = getattr(agent.spec, "soul", None)

# FOR INTERNAL CODE ONLY — raw typed Pydantic model. Use only inside
# extensions that own the kind.
soul_ref = agent.typed.soul
```

### Rule of thumb

- **One field, no existing handle:** `mi.read_spec(...)`
- **Multiple fields OR existing Document handle:** `doc.spec.get(...)`
- **Inside the extension that owns the kind:** `doc.typed.field` is fine

## TypeScript

Same two-form model as Python.

### Form 1: `mi.readSpec*(...)` — sugar

```typescript
const soul = mi.readSpecString("Agent", "foo", "soul");
const skills = mi.readSpecStringArray("Agent", "foo", "skills");
```

Throws if the `(kind, name)` pair doesn't resolve.

### Form 2: `readSpec*(doc, field)` — when you hold a Document

```typescript
import { readSpecString, readSpecStringArray, readSpecRecord } from "@dna/sdk";

const agent = mi.documents.find((d) => d.kind === "Agent" && d.name === "foo");
if (!agent) return;
const soul = readSpecString(agent, "soul");
const skills = readSpecStringArray(agent, "skills");

// AVOID — ad-hoc casts scatter type knowledge across the codebase
const soul = agent.spec.soul as string;
const skills = agent.spec.skills as string[];
```

The helpers throw a clear `TypeError` on type mismatch, so a malformed
manifest fails loud instead of silently miscasting.

## When typed access IS correct

Inside the extension that defines the kind (e.g. the `helix`
extension's own `HelixKind.parse(...)`), you own the typed model
and should use it directly. The access rules above apply to consumer
code — tools, readers, writers, renderers, examples.
