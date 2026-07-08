# DNA SDK v3 Kernel

## What is this

Composition-based SDK for declarative agent configuration via YAML/Markdown manifests. The kernel is a **mediator** that orchestrates 5 clean ports to load, parse, cache, resolve, and query manifest documents.

**Problem solved:** Prompts inside code require full SDLC (branch > code > review > deploy) for any change. The SDK externalizes all agent behavior to editable YAML/Markdown — no deploy needed.

**Architecture:** Microkernel + Extensions. The kernel is minimal (registry, ports, instance). Each family of kinds is an independent Extension.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      Kernel (Mediator)                  │
│                                                         │
│  source()  cache()  resolver()  scanner()  kind()       │
│     │         │         │          │          │         │
│     ▼         ▼         ▼          ▼          ▼         │
│  SourcePort CachePort ResolverPort ScannerPort KindPort │
│                                                         │
│  instance(scope) ──► ManifestInstance                   │
│  quick(scope)    ──► (auto-wires all ports)             │
└─────────────────────────────────────────────────────────┘
```

### The 5 Ports

| Port | Role | Question it answers | Methods |
|------|------|-------------------|---------|
| **SourcePort** | WHERE (primary) | Where are manifests stored? | `load_bootstrap_docs()`, `load_all()`, `resolve_ref()`, `load_layer()` |
| **CachePort** | WHERE (deps) | Where are installed dependencies cached? | `load_all()`, `store()`, `has()` |
| **ResolverPort** | FROM | How to fetch external dependencies? | `resolve()`, `cache_key()` |
| **ScannerPort** | WHAT | How to detect kind bundles on disk? | `detect()`, `scan()` |
| **KindPort** | WHO | What is this kind's identity and role? | `parse()`, `dep_filters()`, `describe()`, `summary()`, `prompt_template()` |

### Port / Adapter Triad

- **WHERE** (SourcePort + CachePort): filesystem, postgres, http, registry
- **HOW** (ScannerPort): detect + scan bundles on filesystem (SKILL.md, SOUL.md, AGENTS.md)
- **WHAT** (KindPort): identity + behavior + composition role per kind

The kernel queries KindPort generically — **zero hardcoded kind strings** in the kernel.

---

## Project Structure

```
python/dna/v3/
├── kernel/
│   ├── __init__.py          # Kernel class (mediator)
│   ├── protocols.py         # 5 port Protocols + shared types
│   ├── document.py          # Document wrapper (universal)
│   ├── lock.py              # Lockfile v3 (read/write/sha256)
│   └── instance.py          # ManifestInstance (public API)
├── adapters/
│   ├── filesystem/
│   │   ├── source.py        # FilesystemSource (SourcePort)
│   │   └── cache.py         # FilesystemCache (CachePort)
│   └── resolvers/
│       ├── local.py         # LocalResolver (ResolverPort)
│       └── github.py        # GitHubResolver (ResolverPort)
└── extensions/
    ├── helix/             # Genome + Agent + Persona
    ├── agentskills/         # Skill + SkillScanner
    ├── soulspec/            # Soul + SoulScanner
    ├── agentsmd/            # AgentContext + AgentContextScanner
    └── github/              # CopilotInstructions + CopilotInstructionsScanner
```

---

## Quick Start

### Minimal (3 lines)

```python
from dna.v3.kernel import Kernel

mi = Kernel.quick("my-module", base_dir=".dna")
print(mi.summary())
```

`Kernel.quick()` auto-wires:
- `FilesystemSource` + `FilesystemCache` (filesystem adapters)
- `LocalResolver` + `GitHubResolver` (dependency resolvers)
- All 5 built-in extensions (Helix, AgentSkills, SoulSpec, AgentsMd, GitHub)

### Manual wiring

```python
from dna.v3.kernel import Kernel
from dna.v3.adapters.filesystem import FilesystemSource, FilesystemCache
from dna.v3.adapters.resolvers import LocalResolver
from dna.v3.extensions.helix import HelixExtension
from dna.v3.extensions.agentskills import AgentSkillsExtension

k = Kernel()
k.source(FilesystemSource(".dna"))
k.cache(FilesystemCache(".dna"))
k.resolver("local", LocalResolver())
k.load(HelixExtension())
k.load(AgentSkillsExtension())

mi = k.instance("my-module")
```

---

## Kernel API

### Registration methods

| Method | Purpose | Port |
|--------|---------|------|
| `k.source(adapter)` | Set primary manifest source | SourcePort |
| `k.cache(adapter)` | Set dependency cache | CachePort |
| `k.resolver(scheme, adapter)` | Register resolver for URI scheme | ResolverPort |
| `k.scanner(adapter)` | Add bundle scanner | ScannerPort |
| `k.kind(adapter)` | Register a kind adapter | KindPort |
| `k.load(extension)` | Load extension (calls `ext.register(kernel)`) | Extension |

### Instance creation

| Method | Purpose |
|--------|---------|
| `k.instance(scope)` | Load scope, resolve deps, parse docs, return ManifestInstance |
| `Kernel.quick(scope, base_dir)` | One-liner: auto-wires all ports + loads 4 built-in extensions |

### instance() flow

```
1. load_bootstrap_docs(scope)    ← SourcePort  # Phase 16: Genome + KindDefinition + LayerPolicy
2. For each dep in spec.dependencies:
   a. resolver.cache_key(uri)    ← ResolverPort
   b. cache.has(scope, key)?     ← CachePort
   c. If miss: resolve(uri, dep) ← ResolverPort
   d. cache.store(scope, key)    ← CachePort
3. source.load_all(scope, scanners)  ← SourcePort + ScannerPort
4. cache.load_all(scope, scanners)   ← CachePort + ScannerPort
5. For each raw doc:
   a. kind_port.parse(raw)       ← KindPort (if registered)
   b. Document.from_raw(raw, typed)
6. Return ManifestInstance(scope, documents, kinds, source)
```

---

## ManifestInstance API

The public facade for querying a loaded manifest scope.

### Query

```python
mi.all("Skill")                          # All documents of kind "Skill"
mi.all("Agent")                   # All agents
mi.one("Agent", "brad")           # One document by kind + name
mi.root                                  # Root document (kind with is_root=True), cached
mi.default_agent()                       # Agent named in root's default_agent field
```

### Navigation (kubectl pattern)

```python
mi.list_kinds()                          # ["Genome", "Skill", "Soul", "Agent"]
mi.get()                                 # [{"kind": "Genome", "name": "x", "apiVersion": "..."}]
mi.get("Skill")                          # Filtered by kind
mi.describe("Skill", "mcp-builder")      # Human-readable description
mi.summary()                             # Multi-line summary for LLM context
```

### Prompt building

```python
mi.build_prompt(agent="brad")            # Build prompt for agent
mi.build_prompt(agent="brad", context={"repo": "my-repo"})  # With extra context
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `mi.scope` | `str` | Scope name (e.g. "my-module") |
| `mi.documents` | `list[Document]` | All loaded documents |
| `mi.resolve_errors` | `list[str]` | Dependency resolution errors |
| `mi.root` | `Document | None` | Root document (cached) |

---

## Document

Universal wrapper that eliminates `isinstance(doc, BaseKind)` vs `dict` checks.

```python
from dna.v3.kernel.document import Document

doc = Document.from_raw({
    "apiVersion": "github.com/ruinosus/dna/v1",
    "kind": "Genome",
    "metadata": {"name": "my-mod", "description": "test"},
    "spec": {"budget": {"daily_usd": 10}},
})

doc.api_version  # "github.com/ruinosus/dna/v1"
doc.kind         # "Genome"
doc.name         # "my-mod"
doc.metadata     # SpecDict — {"name": "my-mod", "description": "test"}
doc.spec         # SpecDict — {"budget": {"daily_usd": 10}}
doc.spec.budget  # Attribute access works (SpecDict is a dict with dot access)
doc.spec.get("budget")  # Dict access also works
doc.raw          # Original dict
doc.typed        # Parsed by KindPort.parse() or None
```

### Equality and hashing

Documents are equal if `(api_version, kind, name)` match. This means they can be used in sets and as dict keys.

---

## Protocols (protocols.py)

All ports are `@runtime_checkable` Protocols. Any class implementing the required methods satisfies the protocol — no inheritance needed.

### SourcePort

```python
@runtime_checkable
class SourcePort(Protocol):
    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict]: ...  # Phase 16: Genome + KindDefinition + LayerPolicy
    def load_all(self, scope: str, scanners: list[ScannerPort] | None = None) -> list[dict]: ...
    def resolve_ref(self, scope: str, ref: str) -> str: ...
    def load_layer(self, scope: str, layer_id: str, layer_value: str) -> list[dict]: ...
```

### CachePort

```python
@runtime_checkable
class CachePort(Protocol):
    def load_all(self, scope: str, scanners: list[ScannerPort] | None = None) -> list[dict]: ...
    def store(self, scope: str, key: str, items: list[CacheItem]) -> None: ...
    def has(self, scope: str, key: str) -> bool: ...
```

### ResolverPort

```python
@runtime_checkable
class ResolverPort(Protocol):
    def resolve(self, uri: str, dep: dict) -> list[ResolvedItem]: ...
    def cache_key(self, uri: str) -> str: ...
```

### ScannerPort

```python
@runtime_checkable
class ScannerPort(Protocol):
    def detect(self, path: Path) -> bool: ...
    def scan(self, path: Path) -> dict: ...
```

### KindPort

```python
@runtime_checkable
class KindPort(Protocol):
    api_version: str
    kind: str
    alias: str
    model: type
    origin: str | None

    is_root: bool
    is_prompt_target: bool
    flatten_in_context: bool

    def dep_filters(self) -> dict[str, str] | None: ...
    def get_default_agent_name(self, doc: Any) -> str | None: ...
    def parse(self, raw: dict) -> Any: ...
    def describe(self, doc: Any) -> str | None: ...
    def summary(self, doc: Any) -> dict | None: ...
    def prompt_template(self) -> str | None: ...
```

### Shared types

```python
@dataclass
class CacheItem:
    name: str
    kind: str
    content_path: Path
    raw: dict | None = None

@dataclass
class ResolvedItem:
    name: str
    kind: str
    source_path: Path

class ResolveError(Exception): ...
```

---

## Built-in Adapters

### FilesystemSource (SourcePort)

Loads manifest documents from `.dna/<scope>/` directories.

```python
from dna.v3.adapters.filesystem import FilesystemSource

source = FilesystemSource(".dna")
bootstrap = await source.load_bootstrap_docs("my-module")  # Genome + KindDefinition + LayerPolicy
docs = source.load_all("my-module", scanners=[...]) # All YAML docs + scanner bundles
content = source.resolve_ref("my-module", "agents/brad.md")  # File content
layer_docs = source.load_layer("my-module", "tenant", "team-b")  # Layer overlay
```

**YAML loading:** Recursively finds all `*.yaml` files with a `kind:` field. Skips `layers/` and `tenants/` directories.

**Scanner invocation:** After YAML loading, walks subdirectories and invokes registered scanners. First scanner that returns `detect(path) == True` wins.

### FilesystemCache (CachePort)

Stores installed dependencies in `.dna-cache/<scope>/<key>/<kind-plural>/<item-name>/`.

```python
from dna.v3.adapters.filesystem import FilesystemCache
from dna.v3.kernel.protocols import CacheItem

cache = FilesystemCache(".dna")
cache.store("my-mod", "local-shared", [
    CacheItem(name="my-skill", kind="Skill", content_path=Path("/source/my-skill")),
])
cache.has("my-mod", "local-shared")  # True
docs = cache.load_all("my-mod", scanners=[...])
```

**Scope isolation:** Each scope has its own cache namespace. `mod-a` cache is invisible to `mod-b`.

**Layout:** `.dna-cache/<scope>/<key>/<kind>s/<name>/` — e.g. `.dna-cache/my-mod/local-shared/skills/brainstorming/SKILL.md`

### LocalResolver (ResolverPort)

Resolves `local:` URIs by copying bundles from local filesystem paths.

```python
from dna.v3.adapters.resolvers import LocalResolver

resolver = LocalResolver(base_dir=Path("."))
items = resolver.resolve("local:../shared/.dna/shared-mod", dep)
key = resolver.cache_key("local:../shared/.dna/shared-mod")
```

**Bundle detection:** Looks for marker files — `SKILL.md` (Skill), `SOUL.md`/`soul.json` (Soul), `AGENTS.md` (AgentContext).

**Filtering:** If `dep["items"]` is set, only imports named items. Otherwise imports everything.

### GitHubResolver (ResolverPort)

Resolves `github:` URIs by shallow-cloning repositories.

```python
from dna.v3.adapters.resolvers import GitHubResolver

resolver = GitHubResolver()
items = resolver.resolve("github:anthropics/skills/skills@main", dep)
```

**URI format:** `github:<owner>/<repo>[/<path>][@<ref>]`

**Implementation:** `git clone --depth 1`, then delegates to `LocalResolver._resolve_all()` or `_resolve_filtered()`.

---

## Extensions

Extensions register kinds and scanners on the Kernel. Protocol: `name`, `version`, `register(kernel)`.

### HelixExtension

Registers 3 KindPorts for the Helix platform:

| Kind | Alias | is_root | is_prompt_target | dep_filters |
|------|-------|---------|-----------------|-------------|
| **Genome** | `helix-genome` | True | False | — |
| **Agent** | `helix-agent` | False | True | `{"soul": "soulspec-soul", "skills": "agentskills-skill"}` |
| **Persona** | `helix-persona` | False | False | — |

```python
from dna.v3.extensions.helix import HelixExtension
k.load(HelixExtension())
```

**Genome** — root document. Declares `spec.default_agent`, `spec.budget`, `spec.dependencies`, `spec.layers`.

**Agent** — prompt target. References Soul via `spec.soul` and Skills via `spec.skills`. Default template: `{{agent.instruction}}`.

**Persona** — passive kind, not a prompt target.

### AgentSkillsExtension

Registers Skill kind + SkillScanner.

| Kind | Alias | Scanner marker |
|------|-------|---------------|
| **Skill** | `agentskills-skill` | `SKILL.md` |

```python
from dna.v3.extensions.agentskills import AgentSkillsExtension
k.load(AgentSkillsExtension())
```

**SkillScanner** detects directories containing `SKILL.md`. Scans:
- Frontmatter (name, description) from `SKILL.md`
- Body as `spec.instruction`
- `scripts/` directory files as `spec.scripts` dict
- `references/` directory files as `spec.references` dict

**Skill bundle structure:**
```
my-skill/
├── SKILL.md            # Frontmatter + instruction
├── scripts/            # Optional executable scripts
│   └── validate.py
└── references/         # Optional reference docs
    └── api-spec.md
```

### SoulSpecExtension

Registers Soul kind + SoulScanner.

| Kind | Alias | Scanner markers | flatten_in_context |
|------|-------|-----------------|--------------------|
| **Soul** | `soulspec-soul` | `SOUL.md` or `soul.json` | True |

```python
from dna.v3.extensions.soulspec import SoulSpecExtension
k.load(SoulSpecExtension())
```

**SoulScanner** reads:
- `SOUL.md` as `spec.soul_content`
- `soul.json` as `spec.soul_json`
- Companion files: `IDENTITY.md`, `STYLE.md`, `HEARTBEAT.md`
- `AGENTS.md` inside soul bundle as `spec.agents_content`

Default template: `{{soul_content}}`

### AgentsMdExtension

Registers AgentContext kind + AgentContextScanner.

| Kind | Alias | Scanner marker | flatten_in_context |
|------|-------|----------------|--------------------|
| **AgentContext** | `agentsmd-context` | `AGENTS.md` (standalone) | True |

```python
from dna.v3.extensions.agentsmd import AgentsMdExtension
k.load(AgentsMdExtension())
```

**AgentContextScanner** detects standalone `AGENTS.md` files. Skips soul bundles (directories also containing `SOUL.md`).

Default template: `{{content}}`

### GitHubExtension

Registers CopilotInstructions kind + scanner.

| Kind | Alias | Scanner marker |
|------|-------|---------------|
| **CopilotInstructions** | `github-copilot` | `.github/copilot-instructions.md` |

```python
from dna.v3.extensions.github import GitHubExtension
k.load(GitHubExtension())
```

---

## KindPort — Composition Role Declarations

Each KindPort adapter declares its role in composition via declarative fields. The kernel queries these fields generically — **zero hardcoded kind strings**.

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `is_root` | bool | False | Root document (Genome). Used by `mi.root`, layer policies, template cascade |
| `is_prompt_target` | bool | False | Can be target of `build_prompt()`. Used by `mi.default_agent()`, `_find_agent()` |
| `flatten_in_context` | bool | False | Spec flattens in Mustache template context |
| `dep_filters()` | dict or None | None | `{spec_field: target_alias}` for filtering deps in prompt context |
| `get_default_agent_name(doc)` | str or None | None | Extract default agent from root doc |
| `prompt_template()` | str or None | None | Default Mustache template for this kind |

### Role matrix

| Kind | is_root | is_prompt_target | flatten_in_context | dep_filters |
|------|---------|-----------------|-------------------|-------------|
| Genome | **True** | False | False | — |
| Agent | False | **True** | False | `{"soul": "soulspec-soul", "skills": "agentskills-skill"}` |
| Persona | False | False | False | — |
| Soul | False | **True** | **True** | — |
| Skill | False | False | False | — |
| AgentContext | False | **True** | **True** | — |
| CopilotInstructions | False | False | False | — |

---

## Lockfile v3

Single flat document list with origin tracking. Generated by `dna_install()`.

### Format

```yaml
# Generated by dna install — DO NOT EDIT
lockVersion: 3
generated_at: '2026-03-30T12:00:00+00:00'
scope: my-module
documents:
- name: my-module
  kind: Genome
  apiVersion: github.com/ruinosus/dna/v1
  origin: local
  path: .dna/my-module/Genome.yaml
  sha256: abc123...
- name: brainstorming
  kind: Skill
  apiVersion: agentskills.io/v1
  origin: github:anthropics/skills@main
  path: .dna-cache/my-module/github-anthropics-skills/skills/brainstorming
  sha256: def456...
```

### API

```python
from dna.v3.kernel.lock import (
    LockEntry, Lockfile,
    write_lockfile, read_lockfile,
    file_sha256, dir_sha256,
)

# Create from Document
entry = LockEntry.from_document(doc, origin="local", path="...", sha256="...")

# Write
lock = Lockfile(scope="my-mod", documents=[entry1, entry2])
write_lockfile(lock, Path("dna.lock"))

# Read
lock = read_lockfile(Path("dna.lock"))

# SHA-256
file_sha256(Path("file.yaml"))    # Single file hash
dir_sha256(Path("skill-bundle/")) # Directory hash (all files, sorted)
```

**Sorting:** Documents are sorted by `(kind, name)` on write for deterministic output.

---

## Dependency Resolution

Dependencies declared in `spec.dependencies` of the root manifest.

### Manifest example

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata:
  name: my-module
spec:
  dependencies:
    - source: "local:../shared/.dna/shared-mod"
      items:
        - kind: Skill
          names: [brainstorming, writing-plans]
      souls: [brad]
    - source: "github:anthropics/skills/skills@main"
      items:
        - kind: Skill
          names: [claude-api]
```

### Resolution flow

1. Kernel reads `spec.dependencies` from manifest
2. For each dep, extracts URI scheme (`local:`, `github:`)
3. Finds registered `ResolverPort` for that scheme
4. Checks `CachePort.has(scope, key)` — skip if already cached
5. On cache miss: `resolver.resolve(uri, dep)` returns `list[ResolvedItem]`
6. `cache.store(scope, key, items)` copies to `.dna-cache/`
7. After all deps resolved: `cache.load_all()` includes cached docs

### Source URI formats

| Scheme | Format | Example |
|--------|--------|---------|
| `local:` | `local:<path>` | `local:../shared/.dna/shared-mod` |
| `github:` | `github:<owner>/<repo>[/<path>][@<ref>]` | `github:anthropics/skills@main` |

### Cache layout

```
.dna-cache/
└── my-module/                # scope
    └── local-shared-mod/     # sanitized cache key
        ├── skills/
        │   ├── brainstorming/SKILL.md
        │   └── writing-plans/SKILL.md
        └── souls/
            └── brad/SOUL.md
```

---

## Manifest Directory Structure

```
.dna/<module-id>/
├── Genome.yaml              # Root manifest (kind: Genome)
├── agents/
│   ├── <agent-id>.yaml        # Agent YAML
│   └── <agent-id>.md          # Agent instruction (ref'd by spec.instruction)
├── skills/
│   └── <skill-id>/
│       ├── SKILL.md           # Skill instruction + frontmatter
│       ├── scripts/*.py       # Optional scripts
│       └── references/*.md    # Optional reference docs
├── souls/
│   └── <soul-id>/
│       ├── SOUL.md            # Soul definition
│       ├── IDENTITY.md        # Optional identity
│       ├── STYLE.md           # Optional style
│       └── HEARTBEAT.md       # Optional heartbeat
├── layers/
│   └── <layer-id>/<value>/
│       ├── overlay.yaml       # Layer overlay (any kind)
│       └── agents/*.yaml      # Layer-specific agents
└── AGENTS.md                  # Optional agents.md context
```

---

## Writing Custom Extensions

### Custom KindPort

```python
class PipelineKind:
    api_version = "myco.io/v1"
    kind = "Pipeline"
    alias = "myco-pipeline"
    model = dict
    origin = "myco.io"
    is_root = False
    is_prompt_target = False
    flatten_in_context = False

    def dep_filters(self): return None
    def get_default_agent_name(self, doc): return None
    def parse(self, raw): return raw
    def describe(self, doc): return None
    def summary(self, doc): return None
    def prompt_template(self): return None
```

### Custom ScannerPort

```python
class PipelineScanner:
    def detect(self, path: Path) -> bool:
        return (path / "pipeline.yaml").exists()

    def scan(self, path: Path) -> dict:
        import yaml
        data = yaml.safe_load((path / "pipeline.yaml").read_text())
        return {
            "apiVersion": "myco.io/v1",
            "kind": "Pipeline",
            "metadata": {"name": path.name},
            "spec": data,
        }
```

### Custom Extension

```python
class PipelineExtension:
    name = "pipeline"
    version = "1.0.0"

    def register(self, kernel):
        kernel.kind(PipelineKind())
        kernel.scanner(PipelineScanner())
```

### Usage

```python
k = Kernel()
k.source(FilesystemSource(".dna"))
k.cache(FilesystemCache(".dna"))
k.load(HelixExtension())
k.load(PipelineExtension())
mi = k.instance("my-module")
pipelines = mi.all("Pipeline")
```

---

## Writing Custom Adapters

### Custom SourcePort (e.g. Postgres)

```python
class PostgresSource:
    def __init__(self, pool):
        self._pool = pool

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT content FROM dna_documents "
            "WHERE scope=$1 AND kind = ANY($2::text[]) AND tenant=''",
            scope, ["Genome", "KindDefinition", "LayerPolicy"],
        )
        return [json.loads(r["content"]) for r in rows]

    def load_all(self, scope, scanners=None):
        rows = await self._pool.fetch(
            "SELECT yaml_content FROM manifests WHERE scope=$1", scope
        )
        return [yaml.safe_load(r["yaml_content"]) for r in rows]

    def resolve_ref(self, scope, ref):
        return ""  # No file refs in DB

    def load_layer(self, scope, layer_id, layer_value):
        return []  # Layers not supported in DB
```

---

## Testing

### Run all v3 tests

```bash
cd python && uv run python -m pytest tests/test_v3/ -v
```

### Test counts (as of 2026-03-30)

| Suite | Tests |
|-------|-------|
| Protocols + Document | 13 |
| Lockfile v3 | 7 |
| Adapters (Source, Cache, Resolvers) | 14 |
| Kernel | 4 |
| ManifestInstance | 6 |
| Extensions (5) | 12 |
| Integration (real open-swe) | 5 |
| **Total v3** | **61** |

### v2 compatibility

v3 lives in `python/dna/v3/` — completely isolated from v2. All 385 v2 tests continue to pass.

---

## Design Decisions

**Microkernel + Extensions** — Kernel is minimal (ports, registration, instance creation). Kinds are registered by Extensions, not hardcoded. Extensions are declarative: name, version, register(kernel).

**Port/Adapter triad** — WHERE (SourcePort + CachePort), HOW (ScannerPort), WHAT (KindPort). The kernel queries KindPort generically via protocol fields — zero hardcoded kind strings.

**Document as universal wrapper** — Eliminates `isinstance(doc, BaseKind)` vs `dict` checks everywhere. All code accesses `doc.name`, `doc.spec`, `doc.metadata` uniformly.

**Kind as bundle** — Aligned with agentskills.io (SKILL.md + scripts/ + references/) and soulspec.org (SOUL.md + IDENTITY.md). Scanner per kind.

**Mandatory alias with owner** — Avoids ambiguous `Skill` vs `Skill`. `agentskills-skill` vs `helix-persona` is explicit. Alias identifies the kind in Mustache template context.

**dep_filters uses aliases** — Globally unique aliases instead of kind names for cross-extension decoupling.

**Lockfile v3** — Single `documents[]` list with origin tracking. No duplicate sections. SHA-256 per entry for change detection.

**Runtime-checkable Protocols** — No base classes needed. Any class implementing the methods satisfies the protocol. Duck typing with type safety.

---

## Comparison: v2 vs v3

| Aspect | v2 | v3 |
|--------|----|----|
| **Kernel** | Monolith with registry + hooks + instance | Mediator connecting 5 ports |
| **Documents** | BaseKind (Pydantic) + raw dict mix | Document wrapper (uniform) |
| **KindRegistry** | Global singleton, side-effect registration | Per-kernel, explicit via `k.kind()` |
| **Filesystem** | `FilesystemAdapter` (all-in-one) | `FilesystemSource` + `FilesystemCache` (separated) |
| **Dependencies** | `dna_install()` + `.dna-cache/` | ResolverPort + CachePort (pluggable) |
| **Lockfile** | v2 with `snapshot` + `resolved` sections | v3 single `documents` list |
| **Extensions** | `name`, `version`, `depends`, `register(kernel)` | Same protocol, cleaner separation |
| **Instance** | 803-line god file | Clean facade with Document list |
| **Tests** | 385 | 61 (growing) |
