# Kind Authoring Guide

Step-by-step: write a new `Kind` + `Extension` for the DNA SDK.

This is the **procedural** companion to `KINDS-GUIDE.md` (which
covers the conceptual model). Read this when you want to ship a new
Kind in 30 minutes.

## Live references

Every pattern here has a shipped implementation to read side-by-side:

- `packages/sdk-py/dna/extensions/guardrails/__init__.py` — a complete
  **bundle** Kind (`GUARDRAIL.md` marker + custom Reader/Writer).
- `packages/sdk-py/dna/extensions/agentskills/__init__.py` — the Skill
  bundle Kind (market format, scripts/references sidecars).
- `packages/sdk-py/dna/extensions/helix/` — **yaml** Kinds (Agent, Actor,
  UseCase) and the **root** Kind (Genome).

## Prerequisites

```bash
cd packages/sdk-py && uv sync
```

## What you're going to build

A new Kind `Hello`, persisted as YAML files at
`<scope>/hellos/<name>.yaml`. The Kind has 3 spec fields: `greeting`,
`recipient`, `created_at`. After this, `mi.all("Hello")` returns your
Hello docs, and `mi.one("Hello", "world")` fetches the named one.

> **Record-style Kinds don't need a class at all.** If your Kind is plain
> data (no custom parse/compose behavior), write a `*.kind.yaml`
> descriptor instead and register it with `kernel.kind_from_descriptor()`
> — see the descriptor files under
> `packages/sdk-ts/src/extensions/*/kinds/` for the format. The class
> pattern below is for Kinds that need behavior.

## Step 1 — Pick the storage shape

Three patterns (`StorageDescriptor.bundle / yaml / root` factories
in `dna.kernel.protocols`):

| Pattern | When to use | Example Kind |
|---|---|---|
| `bundle` | Your Kind has a marker file (e.g. `SKILL.md`) **AND** sibling files (scripts, payloads, tests). | `Skill`, `Soul`, `Guardrail` |
| `yaml` | One YAML file per doc, at `<scope>/<container>/<name>.yaml`. | `Agent`, `Actor`, `UseCase` |
| `root` | Single file at scope root (`<scope>/Genome.yaml`). Only valid for `is_root=True` Kinds (one per scope). | `Genome` |

For `Hello`: `yaml` pattern. Container = `hellos`.

## Step 2 — Author the KindPort

Create `packages/sdk-py/dna/extensions/hello/__init__.py`:

```python
from __future__ import annotations
from typing import Any
from dna.kernel.protocols import StorageDescriptor


class HelloKind:
    # === Identity (mandatory) ============================================
    api_version = "hello.example/v1"        # globally unique namespace
    kind = "Hello"                          # CamelCase Kind name
    alias = "hello-greeting"                # globally unique alias
    model = dict                            # typed model OR dict
    origin = "hello.example"                # registry namespace label
    storage = StorageDescriptor.yaml("hellos")

    # === Behavior flags (mandatory; sensible defaults) ===================
    is_root = False                         # only Genome is True
    is_prompt_target = False                # True if this Kind's docs
                                            # contribute to LLM prompts
    prompt_target_priority = 0
    flatten_in_context = False              # True flattens spec dict into
                                            # the prompt context

    # === Behavior methods (mandatory; can return None defaults) =========
    def dep_filters(self) -> dict[str, str] | None:
        # Mapping from spec field → kind alias for cross-Kind references.
        # Example: {"agent": "helix-agent"} means spec.agent
        # is a name pointing at an Agent doc.
        return None

    def dependencies(self) -> dict[str, str] | None:
        return self.dep_filters()           # alias of dep_filters

    def schema(self) -> dict[str, Any] | None:
        # JSON Schema for the spec dict. Drives validation on write and
        # gives UI layers everything a form generator needs.
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
        return raw                          # no typed model — keep as dict

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
from dna.kernel.protocols import ExtensionHost


class HelloExtension:
    name = "hello"        # required — kernel.load() fail-loud validates it
    version = "0.1.0"     # required — ditto

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(HelloKind())
        # No custom Reader/Writer needed for `yaml` storage —
        # the kernel auto-registers GenericYamlReader + GenericYamlWriter
        # for any kind without a custom Reader/Writer. (`bundle` pattern
        # Kinds need explicit Reader+Writer because the bundle structure
        # is Kind-specific — see the guardrails extension as reference.)
```

`ExtensionHost` is the explicit registration-time contract — everything an
extension may call while loading (`kind`, `kind_from_descriptor`, `reader`,
`writer`, `on`, `on_veto`, `tool`, `composition_profile`, `hooks`). The
TypeScript twin is the `ExtensionHost` interface in
`src/kernel/protocols.ts` (same surface, camelCase).

## Step 4 — Wire the entry-point

In `packages/sdk-py/pyproject.toml`, find
`[project.entry-points."dna.extensions"]` and add:

```toml
hello = "dna.extensions.hello:HelloExtension"
```

## Step 5 — Sanity check

```bash
cd packages/sdk-py && uv pip install -e .
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
caught a problem. Common causes:

- **Duplicate `(api_version, kind)`**: another extension already
  declares `("hello.example/v1", "Hello")`. Pick a different
  `api_version` namespace.
- **Duplicate `alias`**: another Kind uses `hello-greeting`. Pick
  another.
- **Doesn't satisfy `KindPort` Protocol**: missing one of the
  required attributes/methods. The error message lists them all.

## Step 6 — Run the contract test

The cross-adapter port contract suite makes sure your new Kind
round-trips through every supported source adapter:

```bash
cd packages/sdk-py && uv run pytest tests/test_port_contract.py -v -k Hello
# Or the full suite:
uv run pytest tests/test_port_contract.py -v
```

Expected: green on Filesystem + SQLite. Postgres tests skip unless
`DATABASE_URL` is set.

If your Kind uses `bundle` storage, see the guardrails extension for
how to write a custom Reader (`detect()` + `read()`) and Writer
(`can_write()` + `write()` + `serialize()`). Set
`_owner_container = "hellos"` on the Reader so the container-aware
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
`TypedGenome`, `TypedAgent`, `TypedActor` (see
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

class HelloKind:
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
output/artifact Kinds), declare a `TypedDict` mirror:

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
SpecDict still works for both attribute and key access.

### Picking between A and B

| Use Pattern A (dataclass) when... | Use Pattern B (TypedDict) when... |
|---|---|
| Spec has structured fields with fixed shape | Spec carries dynamic / extension-driven data |
| Field-level validation matters at parse time | Validation happens via JSON Schema only |
| Sub-fields have their own types | Sub-fields are loose dicts |

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `KindRegistrationError: BUNDLE storage already registered` | Two bundle Kinds use the same `(container, marker)` pair (e.g. both `MANIFEST.md`). | Pick distinct containers. If sharing is intentional, set `marker_shared_allowed = True` on BOTH Kinds AND have their Reader.detect() distinguish at read time. |
| `mi.all("MyKind")` returns empty after write | Writer ran but adapter didn't auto-publish (SQL adapters use draft → publish flow). | Call `await source.publish(scope, kind, name)` after `save_document`. The kernel's high-level write path doesn't auto-publish — that's deliberate to support draft workflows. |
| `NotImplementedError: Source adapter X does not implement BundleEntryReadable` | Custom adapter missing `fetch_bundle_entry`. | Implement the method per the `BundleEntryReadable` Protocol in `dna.kernel.capabilities`. |
| Kind shows up as `kind=None` in mi.all queries | `parse()` returned a non-dict, or model class is wrong. | Return `raw` directly OR a typed model; the universal `Document` wrapper handles both. |

## Reference reading

- `docs/KINDS-GUIDE.md` — conceptual overview of Kinds
- `docs/PORT-CONTRACT.md` — what every adapter must implement
- `packages/sdk-py/dna/kernel/protocols.py` — Protocol definitions
- `packages/sdk-py/dna/kernel/capabilities.py` — optional capability Protocols
- `packages/sdk-py/dna/kernel/errors.py` — registration errors raised at boot
- `packages/sdk-py/dna/extensions/guardrails/__init__.py` — minimal bundle Kind (ref impl)
- `packages/sdk-py/dna/extensions/agentskills/__init__.py` — reference Skill bundle Kind
- `packages/sdk-py/tests/test_port_contract.py` — what your Kind must round-trip through
