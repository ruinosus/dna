# Readers & Writers — Bundle Format System

Readers detect and parse bundle directories on the filesystem. Writers serialize documents back to those directories. Together they enable the SDK's human-readable, git-friendly file formats.

---

## How It Works

When using a filesystem-based source, the SDK walks directories looking for bundles. Each Reader gets a chance to `detect()` a directory — if it matches, it `read()`s it into a raw dict.

```
.dna/my-module/
├── skills/
│   └── greeting/          ← SkillReader.detect() → True (SKILL.md exists)
│       ├── SKILL.md       ← SkillReader.read() → raw dict
│       ├── scripts/
│       │   └── run.py
│       └── references/
│           └── style.md
├── souls/
│   └── brad/              ← SoulReader.detect() → True (SOUL.md exists)
│       ├── SOUL.md
│       ├── IDENTITY.md
│       └── STYLE.md
└── agents/
    └── brad/              ← AgentReader.detect() → True (AGENT.md exists)
        └── AGENT.md
```

### Detection Priority

Readers are checked in registration order. The **first** Reader that returns `detect(path) → True` wins. This means if a directory has both `SOUL.md` and `AGENTS.md`, the SoulReader wins because SoulSpecExtension is loaded before AgentsMdExtension (and the AgentDefinitionReader explicitly skips soul bundles).

---

## Built-in Readers

### SkillReader — `SKILL.md` bundles

**Detects:** Directory contains `SKILL.md`

**Reads:**
- `SKILL.md` → frontmatter (name, description) + body (instruction)
- `scripts/` → collected as `spec.scripts` (dict of relative_path → content)
- `references/` → collected as `spec.references`
- `assets/` → collected as `spec.assets`
- Any other subdirectory → collected as `spec.extras`
- Root files (not SKILL.md) → collected as `spec.root_files`

**Example SKILL.md:**
```markdown
---
name: code-review
description: Review code for quality and bugs
---
When asked to review code:
1. Check for bugs and logic errors
2. Suggest improvements
3. Note any security concerns
```

**Produced raw dict:**
```python
{
    "apiVersion": "agentskills.io/v1",
    "kind": "Skill",
    "metadata": {"name": "code-review", "description": "Review code for quality and bugs"},
    "spec": {
        "instruction": "When asked to review code:\n1. Check for bugs...",
        "scripts": {"lint.sh": "#!/bin/bash\nruff check ."},
        "references": {"checklist.md": "## Review Checklist\n..."},
    }
}
```

### SoulReader — `SOUL.md` bundles

**Detects:** Directory contains `SOUL.md` or `soul.json`

**Reads:**
- `SOUL.md` → `spec.soul_content` (the main personality text)
- `soul.json` → `spec.soul_json` (structured personality data)
- `IDENTITY.md` → `spec.identity_content`
- `STYLE.md` → `spec.style_content`
- `HEARTBEAT.md` → `spec.heartbeat_content`
- `AGENTS.md` → `spec.agents_content` (agent context within soul)

**Example SOUL.md:**
```markdown
## Personality
Friendly and patient. Explains things clearly.

## Tone
Conversational but professional.

## Principles
- Always be helpful
- Keep responses concise
```

### AgentReader — `AGENT.md` bundles

**Detects:** Directory contains `AGENT.md`

**Reads:**
- `AGENT.md` → YAML frontmatter (name, description, model, skills, soul, tools, tags) + body (instruction)
- `scripts/`, `references/`, `assets/` → same as SkillReader
- Other subdirectories → `spec.extras`
- Root files → `spec.root_files`

**Example AGENT.md:**
```markdown
---
name: brad
description: Architect and mentor
model: openai/gpt-4o
skills: [brainstorming, writing-plans]
soul: brad
---

# Brad — Architect & Mentor

You are Brad, a senior software architect. You plan before you act.

## Approach
1. Ask before assuming
2. Propose 2-3 approaches with trade-offs
3. Design in sections, get approval before moving on
```

**Note:** AgentReader produces a Agent document — the same kind as `agents/*.yaml`. The difference is format: AGENT.md is a single-file bundle with frontmatter, while YAML is a structured document.

### AgentDefinitionReader — standalone `AGENTS.md`

**Detects:** Directory contains `AGENTS.md` AND does NOT contain `SOUL.md` or `soul.json` (to avoid conflicting with SoulReader)

**Reads:**
- `AGENTS.md` → `spec.content` (full file as string)

### CopilotInstructionsReader — `.github/copilot-instructions.md`

**Detects:** Directory contains `.github/copilot-instructions.md`

**Reads:**
- `.github/copilot-instructions.md` → `spec.content`

---

## Built-in Writers

Writers are the inverse of Readers — they serialize a raw dict back to a directory.

### SkillWriter

**Matches:** `raw.kind == "Skill"`

**Writes:**
- `SKILL.md` ← frontmatter (name, description) + instruction
- `scripts/`, `references/`, `assets/` ← from spec fields
- Extra subdirectories ← from `spec.extras`
- Root files ← from `spec.root_files`

### SoulWriter

**Matches:** `raw.kind == "Soul"`

**Writes:**
- `SOUL.md` ← `spec.soul_content`
- `IDENTITY.md` ← `spec.identity_content`
- `STYLE.md` ← `spec.style_content`
- `HEARTBEAT.md` ← `spec.heartbeat_content`
- `AGENTS.md` ← `spec.agents_content`

### AgentWriter

**Matches:** `raw.kind == "Agent"`

**Writes:**
- `AGENT.md` ← YAML frontmatter (name, description, model, skills, soul, etc.) + instruction body
- `scripts/`, `references/`, `assets/` ← from spec fields
- Extra subdirectories ← from `spec.extras`
- Root files ← from `spec.root_files`

---

## The Protocols

Readers and writers operate on a `BundleHandle` — an abstraction over
"where the bundle lives" (filesystem directory, Postgres bundle-entry rows,
in-memory dict). The same reader works against any backend.

Implementations MUST inherit the Protocol explicitly (Python) / declare
`implements` (TypeScript) — the same convention source adapters follow.
The kernel's registration gate (`kernel.reader(...)` / `kernel.writer(...)`)
rejects objects that don't satisfy the port.

### ReaderPort

```python
class ReaderPort(Protocol):
    #: Optional container this Reader's Kind is rooted at (e.g. "skills").
    #: The scanner tries container-owned readers first and unscoped readers
    #: (the inherited None default) as fallback. Formal port member —
    #: TS twin: `readonly _ownerContainer?: string`.
    _owner_container: str | None = None

    def detect(self, bundle: BundleHandle) -> bool:
        """Does this bundle contain a marker I can read?"""
        ...

    def read(self, bundle: BundleHandle) -> dict[str, Any]:
        """Read the bundle into a raw document dict."""
        ...
```

> **Detect on your marker alone.** `detect()` must claim every bundle your
> own writer emits — including a doc-level re-emit that carries only the
> marker (heavy payloads travel as bundle entries, not through spec).
> A reader that additionally requires a payload file will reject its own
> writer's output and let a generic reader capture it with the wrong shape
> (this was a live bug in GraphifyArtifact).

### WriterPort

```python
class WriterPort(Protocol):
    def can_write(self, raw: dict) -> bool:
        """Do I own this document's kind?"""
        ...

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        """Persist the document into the bundle."""
        ...

    def serialize(self, raw: dict) -> list[dict[str, Any]]:
        """The entries write() would emit, WITHOUT writing.

        Text entry:   {"relativePath": str, "content": str}
        Binary entry: {"relativePath": str, "content_bytes": bytes}
        """
        ...
```

`serialize` is **part of the contract** (since `s-dna-rw-roundtrip-suite`) —
`kernel.serialize_document` (the HTTP/MCP preview + write paths) calls it on
the first writer whose `can_write` claims the kind. **`write` and `serialize`
must stay coherent**: the canonical implementation builds the entry list once
and writes it through the shared helper:

```python
from dna.kernel.writer_helpers import write_entries_to_handle

class MyWriter(WriterPort):
    def serialize(self, raw: dict) -> list[dict]:
        return [{"relativePath": "MY_KIND.md", "content": ...}]

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        write_entries_to_handle(bundle, self.serialize(raw))
```

TypeScript twin: `serialize(raw): SerializedFile[]` (required member of
`WriterPort` in `src/kernel/protocols.ts`; `SerializedFile` carries
`content` or `contentBytes`).

---

## Writing a Reader/Writer — with the conformance suite as your net

The round-trip invariant is the thesis of the notation: **the writer
re-emits what the reader read, and emit→read→emit is a fixpoint** (the
first write is the only normalization that ever happens). You don't hand-roll
tests for that — the SDK ships a generic suite that enforces it for every
registered pair:

```python
# tests/test_my_extension_rw.py
import pytest
from dna.kernel import Kernel
from dna.testing import CaseNotApplicable, reader_writer_conformance_suite

def _kernel():
    k = Kernel()
    k.load(MyExtension())
    return k

CASES = reader_writer_conformance_suite(
    _kernel,
    # Optional: per-kind fixture override when the synthetic default
    # (metadata + body_field) doesn't satisfy your writer:
    fixtures={"Config": {"apiVersion": "mycompany.io/v1", "kind": "Config",
                         "metadata": {"name": "rw-fixture"},
                         "spec": {"region": "us-east-1"}}},
    # Optional: real bundles on disk gain fixpoint cases too:
    real_bundle_roots=["tests/fixtures/my-scope"],
)

@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_rw_conformance(case):
    try:
        case.run()
    except CaseNotApplicable as skip:
        pytest.skip(str(skip))
```

Per kind the suite generates: `serialize_shape` (well-formed entries),
`write_serialize_coherent` (the two surfaces emit identical trees),
`writer_output_readable` (a registered reader detects + reads back the same
kind and name, container-aware) and `round_trip_fixpoint` (§2.1 idempotence).
The in-repo wiring (`tests/test_rw_conformance_kit.py` + the TS mirror
`tests/rw-conformance.test.ts`) runs it over the full builtin registration
and the real marketplace bundles in `scopes/market-integration`.

### Example: `CONFIG.toml` bundle

Say your company uses TOML files for configuration documents:

```toml
# CONFIG.toml
[metadata]
name = "production"
description = "Production environment config"

[spec]
environment = "production"
region = "us-east-1"
max_replicas = 10
features = ["caching", "metrics"]
```

**1. Create a Reader**

```python
from typing import Any
from dna.kernel.bundle_handle import BundleHandle
from dna.kernel.protocols import ReaderPort


class ConfigReader(ReaderPort):
    """Detects and reads CONFIG.toml bundles."""

    def detect(self, bundle: BundleHandle) -> bool:
        return bundle.exists("CONFIG.toml")

    def read(self, bundle: BundleHandle) -> dict[str, Any]:
        import tomllib  # Python 3.11+ (or tomli for <3.11)

        data = tomllib.loads(bundle.read_text("CONFIG.toml"))
        return {
            "apiVersion": "mycompany.io/v1",
            "kind": "Config",
            "metadata": data.get("metadata", {"name": bundle.name}),
            "spec": data.get("spec", {}),
        }
```

**2. Create a Writer** — build the entries once, share them between
`serialize` and `write`:

```python
from dna.kernel.protocols import WriterPort
from dna.kernel.writer_helpers import write_entries_to_handle


class ConfigWriter(WriterPort):
    """Writes Config documents back to CONFIG.toml."""

    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == "Config"

    def serialize(self, raw: dict) -> list[dict]:
        import tomli_w  # pip install tomli-w
        data = {
            "metadata": raw.get("metadata", {}),
            "spec": raw.get("spec", {}),
        }
        return [{"relativePath": "CONFIG.toml", "content": tomli_w.dumps(data)}]

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        write_entries_to_handle(bundle, self.serialize(raw))
```

**3. Register via Extension**

```python
class ConfigExtension:
    name = "config"
    version = "1.0.0"

    def register(self, kernel):
        kernel.kind(ConfigKind())
        kernel.reader(ConfigReader())
        kernel.writer(ConfigWriter())
```

**4. Use it** (and wire the conformance suite from the section above — that
is your definition of done for the pair)

```python
k = Kernel()
k.load(ConfigExtension())
# ...
mi = k.instance("my-module")
configs = mi.all("Config")
for c in configs:
    print(f"{c.name}: region={c.spec.region}, replicas={c.spec.max_replicas}")
```

---

## When are Readers/Writers Used?

| Operation | Uses Readers? | Uses Writers? |
|-----------|--------------|--------------|
| `kernel.instance()` with FilesystemSource | Yes — to detect and read bundles | No |
| `kernel.instance()` with SQLiteSource | No — documents are self-contained JSON | No |
| Admin portal "Save" with filesystem backend | No | Yes — writes back to disk |
| Admin portal "Save" with SQLite backend | No | No — stores as JSON |
| `source.load_all(scope, readers=...)` | Yes | No |

**Key insight:** Readers and Writers only matter for **filesystem-based** sources. When using SQLite or PostgreSQL, documents are stored as JSON blobs — no bundle detection needed. The `supports_readers` property on SourcePort indicates this:

```python
class FilesystemSource:
    supports_readers = True   # Uses readers to detect bundles

class SqliteSource:
    supports_readers = False  # Documents are self-contained JSON
```

---

## Bundle Directory Structure

Readers follow a common pattern for rich bundles:

```
my-bundle/
├── MARKER.md          ← Main file (SKILL.md, SOUL.md, AGENT.md)
├── scripts/           ← Executable scripts
│   ├── run.py
│   └── test.sh
├── references/        ← Reference documents
│   ├── style-guide.md
│   └── api-spec.yaml
├── assets/            ← Static assets
│   └── diagram.png
├── custom-dir/        ← Any other directory → spec.extras
│   └── data.json
└── extra-file.txt     ← Root-level files → spec.root_files
```

This structure is shared by SkillReader and AgentReader. SoulReader uses a simpler companion-file pattern (IDENTITY.md, STYLE.md, etc.).

## Summary

| Concept | What it does |
|---------|-------------|
| **ReaderPort** | Detects and reads bundles into raw dicts |
| **WriterPort** | Serializes raw dicts back to bundles |
| **detect(bundle)** | Returns True if the bundle carries this Kind's marker |
| **read(bundle)** | Parses the bundle into `{apiVersion, kind, metadata, spec}` |
| **_owner_container** | Optional container the reader is scoped to (scanner routing) |
| **can_write(raw)** | Returns True if the writer handles this document kind |
| **write(bundle, raw)** | Creates/updates the bundle from the raw dict |
| **serialize(raw)** | The entries write() would emit — REQUIRED, must match write() |
| **supports_readers** | Source property — True for filesystem, False for databases |
| **reader_writer_conformance_suite** | Ship-with-the-SDK net enforcing the round-trip invariant per pair |
