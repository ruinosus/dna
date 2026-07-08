# Kind Data Access Pattern

The DNA SDK has a unified way to read data from Documents of any kind.
Follow it so your code doesn't break when kinds evolve, and so you
don't need to know a kind's typed model to work with it.

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
already has a `Document` reference from `mi.one()` or `mi.all()`:

```python
# GOOD — kind-agnostic, works for any Document
agent = mi.one("Agent", "foo")
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

const agent = mi.one("Agent", "foo");
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
