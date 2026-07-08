# Kind Authoring Guide

Step-by-step: write a new `Kind` + `Extension` for the DNA SDK.

This is the **procedural** companion to `KINDS-GUIDE.md` (which
covers the conceptual model). Read this when you want to ship a new
Kind in 30 minutes.

## Live reference

Every code snippet here cross-references **`PageIndexExtension`**
(the spike at `python/dna/extensions/pageindex/__init__.py`)
which is the canonical "minimal-but-realistic" Kind authored against
the strict v1.0 SDK contract (H1-H4 hardening). Read that file
side-by-side with this guide.

## Prerequisites

```bash
cd python && uv sync
cd ../python-harness && uv sync --extra pageindex   # Optional: pulls
                                                    # PyPI deps the
                                                    # PageIndex Kind
                                                    # uses for indexing
```

## What you're going to build

A new Kind `Hello`, persisted as YAML files at
`<scope>/hellos/<name>.yaml`. The Kind has 3 spec fields: `greeting`,
`recipient`, `created_at`. After this, `mi.all("Hello")` returns your
Hello docs, and `mi.one("Hello", "world")` fetches the named one.

## Step 1 — Pick the storage shape

Three patterns (`StorageDescriptor.bundle / yaml / root` factories
in `dna.kernel.protocols`):

| Pattern | When to use | Example Kind |
|---|---|---|
| `bundle` | Your Kind has a marker file (e.g. `SKILL.md`) **AND** sibling files (scripts, payloads, tests). | `Skill`, `Soul`, `GraphifyArtifact`, `PageIndexDocument` |
| `yaml` | One YAML file per doc, at `<scope>/<container>/<name>.yaml`. | `Agent`, `EvalCase` |
| `root` | Single file at scope root (`<scope>/manifest.yaml`). Only valid for `is_root=True` Kinds (one per Module). | `Module` |

For `Hello`: `yaml` pattern. Container = `hellos`.

## Step 2 — Author the KindPort

Create `python/dna/extensions/hello/__init__.py`:

```python
from __future__ import annotations
from typing import Any
from dna.kernel.protocols import StorageDescriptor


class HelloKind:
    # === Identity (mandatory) ============================================
    api_version = "hello.example/v1"        # globally unique namespace
    kind = "Hello"                          # CamelCase Kind name
    alias = "hello-greeting"                # globally unique alias
    model = dict                            # Pydantic model OR dict
    origin = "hello.example"                # registry namespace label
    storage = StorageDescriptor.yaml("hellos")

    # === Behavior flags (mandatory; sensible defaults) ===================
    is_root = False                         # only Module is True
    is_prompt_target = False                # True if this Kind's docs
                                            # contribute to LLM prompts
    prompt_target_priority = 0
    flatten_in_context = False              # True flattens spec dict into
                                            # the prompt context

    # === Behavior methods (mandatory; can return None defaults) =========
    def dep_filters(self) -> dict[str, str] | None:
        # Mapping from spec field → kind alias for cross-Kind references.
        # Example: {"agent": "helix-agent"} means spec.agent
        # is a name pointing at a Agent doc.
        return None

    def dependencies(self) -> dict[str, str] | None:
        return self.dep_filters()           # alias of dep_filters

    def schema(self) -> dict[str, Any] | None:
        # JSON Schema for the spec dict. Drives Studio's form generator
        # and validation in the harness REST endpoints.
        return {
            "type": "object",
            "required": ["greeting", "recipient"],
            "properties": {
                "greeting": {"type": "string"},
                "recipient": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
            },
        }

    def get_default_agent_name(self, doc: Any) -> str | None:
        return None

    def get_layer_policies(self, doc: Any) -> dict | None:
        return None

    def parse(self, raw: dict[str, Any]) -> Any:
        return raw                          # no Pydantic — keep as dict

    def describe(self, doc: Any) -> str | None:
        spec = doc.spec or {}
        return f"{spec.get('greeting', '?')} → {spec.get('recipient', '?')}"

    def summary(self, doc: Any) -> dict[str, Any] | None:
        return doc.spec

    def prompt_template(self) -> str | None:
        return None
```

That's the Kind. Hello world.

## Step 3 — Author the Extension

Same file, append:

```python
class HelloExtension:
    name = "hello"
    version = "0.1.0"

    def register(self, kernel) -> None:
        kernel.kind(HelloKind())
        # No custom Reader/Writer needed for `yaml` storage —
        # kernel._ensure_generic_readers_writers() auto-registers
        # GenericYamlReader + GenericYamlWriter for any kind without
        # a custom Reader/Writer registered. (`bundle` pattern Kinds
        # need explicit Reader+Writer because the bundle structure is
        # Kind-specific — see PageIndex extension as reference.)
```

## Step 4 — Wire the entry-point

In `python/pyproject.toml`, find `[project.entry-points."dna.extensions"]`
and add:

```toml
hello = "dna.extensions.hello:HelloExtension"
```

## Step 5 — Sanity check

```bash
cd python && uv pip install -e .
uv run python -c "
from dna.kernel import Kernel
k = Kernel.auto()
print('Hello registered:', ('hello.example/v1', 'Hello') in k._kinds)
print('alias:', k._kinds[('hello.example/v1', 'Hello')].alias)
"
```

Expected output:
```
Hello registered: True
alias: hello-greeting
```

If you see `KindRegistrationError` instead, the boot-time validation
(H1) caught a problem. Common causes:

- **Duplicate `(api_version, kind)`**: another extension already
  declares `("hello.example/v1", "Hello")`. Pick a different
  `api_version` namespace.
- **Duplicate `alias`**: another Kind uses `hello-greeting`. Pick
  another.
- **Doesn't satisfy `KindPort` Protocol**: missing one of the 19
  required attributes/methods. The error message lists them all.

## Step 6 — Run the contract test

The cross-adapter port contract suite (`H4`) makes sure your new
Kind round-trips through every supported source adapter:

```bash
cd python && uv run pytest tests/test_port_contract.py -v -k Hello
# Or for full suite (PageIndex, Skill, Module + your new Hello):
uv run pytest tests/test_port_contract.py -v
```

Expected: 16 tests pass on Filesystem + SQLite. Postgres tests skip
unless `DATABASE_URL` is set.

If your Kind uses `bundle` storage, see the PageIndex extension for
how to write a custom Reader (`detect()` + `read()`) and Writer
(`can_write()` + `write()` + `serialize()`). Set
`_owner_container = "hellos"` on the Reader so the H3 container-aware
scanner routes to it (avoids marker collision with other bundle
Kinds).

## Step 7 — Optional: UI integration

Expose the Kind through your own service/UI layer — the kernel's
JSON-Schema introspection gives form generators everything they
need (see the schema helpers on the kernel surface).

## Step 8 — Type-safe spec access (recommended)

`Document.spec` is a `SpecDict` (dict + attribute access). Without
extra annotations, your IDE shows `spec.foo` as `Any` — no
autocomplete, no typo detection. Two patterns close that gap.
Choose based on the shape of your spec:

### Pattern A — dataclass spec (richer Kinds)

When your spec has structured fields, define a dataclass-based typed
model. The canonical Kinds use this: `TypedSkill`, `TypedSoul`,
`TypedModule`, `TypedAgent`, `TypedActor` (see
`dna/kernel/models.py`).

```python
from dataclasses import dataclass

@dataclass
class HelloSpec:
    greeting: str
    recipient: str
    created_at: str | None = None

@dataclass
class TypedHello:
    metadata: dict
    spec: HelloSpec

class HelloKind(KindBase):
    api_version = "hello.example/v1"
    kind = "Hello"
    alias = "hello-greeting"
    model = TypedHello       # ← canonical pattern
    storage = StorageDescriptor.yaml("hellos")

    def parse(self, raw):
        return TypedHello(
            metadata=raw.get("metadata", {}),
            spec=HelloSpec(**raw.get("spec", {})),
        )
```

Consumers access via `doc.typed`:

```python
doc = mi.one("Hello", "world")
hello: TypedHello = doc.typed
print(hello.spec.greeting)  # type: str ✅ (mypy/pyright happy)
```

### Pattern B — TypedDict (dict-shaped Kinds)

When your spec is genuinely a free-form dict (often the case for
output/artifact Kinds: `GraphifyArtifact`, `PageIndexDocument`,
`KnowledgeArtifact`), declare a `TypedDict` mirror:

```python
from typing import NotRequired, TypedDict

class HelloSpec(TypedDict, total=False):
    greeting: str
    recipient: str
    created_at: NotRequired[str]
```

Consumers cast at the boundary:

```python
from typing import cast
from dna.extensions.hello import HelloSpec

doc = mi.one("Hello", "world")
spec = cast(HelloSpec, doc.spec)
print(spec["greeting"])  # type-checker knows this is str
```

`cast` is a no-op at runtime — purely a hint to mypy/pyright. The
SpecDict still works for both attribute and key access. Live
reference: `PageIndexSpec`, `PageIndexSummary`,
`PageIndexSourceRef` in `dna/extensions/pageindex/__init__.py`.

### Picking between A and B

| Use Pattern A (dataclass) when... | Use Pattern B (TypedDict) when... |
|---|---|
| Spec has structured fields with fixed shape | Spec carries dynamic / extension-driven data |
| Field-level validation matters at parse time | Validation happens via JSON Schema only |
| Sub-fields have their own types | Sub-fields are loose dicts |

> **v1.1 follow-up**: `Document[T]` generic so `mi.one[HelloSpec](kind, name)`
> returns a typed Document directly (skip the `cast`/`doc.typed`
> indirection). Plus TS↔Py parity. The current patterns bridge v1.0 →
> v1.1 without breaking changes.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `KindRegistrationError: BUNDLE storage already registered` | Two bundle Kinds use the same `(container, marker)` pair (e.g. both `MANIFEST.md`). | Pick distinct containers. If sharing is intentional (autoagent + autoresearch case), set `marker_shared_allowed = True` on BOTH Kinds AND have their Reader.detect() distinguish at read time. |
| `mi.all("MyKind")` returns empty after write | Writer ran but adapter didn't auto-publish (SQL adapters use draft → publish flow). | Call `await source.publish(scope, kind, name)` after `save_document`. The kernel's high-level write path doesn't auto-publish — that's deliberate to support draft workflows. |
| `Kernel.auto(source=SqliteSource(...))` silently drops bundle writes | Pre-H2 footgun. | Should not happen on v1.0+. If it does: confirm your source implements `KernelAttachable`. |
| `NotImplementedError: Source adapter X does not implement BundleEntryReadable` | Custom adapter missing `fetch_bundle_entry`. | Implement the method per the `BundleEntryReadable` Protocol in `dna.kernel.capabilities`. |
| Kind shows up as `kind=None` in mi.all queries | `parse()` returned a non-dict, or model class is wrong. | Return `raw` directly OR a Pydantic model; the universal `Document` wrapper handles both. |

## Reference reading

- `docs/KINDS-GUIDE.md` — conceptual overview of Kinds
- `docs/PORT-CONTRACT.md` — what every adapter must implement
- `python/dna/kernel/protocols.py` — Protocol definitions
- `python/dna/kernel/capabilities.py` — optional capability Protocols
- `python/dna/kernel/errors.py` — registration errors raised at boot
- `python/dna/extensions/pageindex/__init__.py` — minimal bundle Kind (ref impl)
- `python/dna/extensions/agentskills/__init__.py` — reference Skill bundle Kind
- `python/tests/test_port_contract.py` — what your Kind must round-trip through
