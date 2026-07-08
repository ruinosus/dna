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

### ReaderPort

```python
class ReaderPort(Protocol):
    def detect(self, path: Path) -> bool:
        """Does this directory contain a bundle I can read?"""
        ...

    def read(self, path: Path) -> dict[str, Any]:
        """Read the bundle into a raw document dict."""
        ...
```

### WriterPort

```python
class WriterPort(Protocol):
    def can_write(self, raw: dict) -> bool:
        """Can I serialize this document?"""
        ...

    def write(self, path: Path, raw: dict) -> None:
        """Serialize the document to a directory."""
        ...
```

---

## Creating a Custom Reader/Writer

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
from pathlib import Path
from typing import Any

class ConfigReader:
    """Detects and reads CONFIG.toml bundles."""

    def detect(self, path: Path) -> bool:
        return (path / "CONFIG.toml").exists()

    def read(self, path: Path) -> dict[str, Any]:
        import tomllib  # Python 3.11+ (or tomli for <3.11)

        with open(path / "CONFIG.toml", "rb") as f:
            data = tomllib.load(f)

        return {
            "apiVersion": "mycompany.io/v1",
            "kind": "Config",
            "metadata": data.get("metadata", {"name": path.name}),
            "spec": data.get("spec", {}),
        }
```

**2. Create a Writer**

```python
class ConfigWriter:
    """Writes Config documents back to CONFIG.toml."""

    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == "Config"

    def write(self, path: Path, raw: dict) -> None:
        path.mkdir(parents=True, exist_ok=True)

        # Build TOML content
        import tomli_w  # pip install tomli-w
        data = {
            "metadata": raw.get("metadata", {}),
            "spec": raw.get("spec", {}),
        }
        with open(path / "CONFIG.toml", "wb") as f:
            tomli_w.dump(data, f)
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

**4. Use it**

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
| **ReaderPort** | Detects and reads bundle directories into raw dicts |
| **WriterPort** | Serializes raw dicts back to bundle directories |
| **detect(path)** | Returns True if the directory contains a recognized bundle |
| **read(path)** | Parses the bundle into `{apiVersion, kind, metadata, spec}` |
| **can_write(raw)** | Returns True if the writer handles this document kind |
| **write(path, raw)** | Creates/updates the bundle directory from the raw dict |
| **supports_readers** | Source property — True for filesystem, False for databases |
