# Tools as data

The DNA already governs an agent's persona, instruction and guardrails
declaratively. **Tools as data** closes the last gap: the *agent-facing surface*
of a tool — the `description` a tool-calling model reads to decide whether to
call it, and the JSON Schema of its `parameters` — moves out of hard-coded
`@tool` functions and into a `Tool` document. Versioned, testable, tenant-
overridable, and read identically by a Python backend **and** a TypeScript
frontend from **one** source of truth.

## The `Tool` Kind

A Tool is one declarative document stored at `tools/<name>.yaml`:

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: Tool
metadata:
  name: generate-artifact
  # The AGENT-FACING description — the text the model reads.
  description: Render a self-contained HTML or Markdown document into a
    shareable artifact. Returns the artifact's URL.
spec:
  type: builtin
  # The "parameters" surface — the JSON Schema of the arguments.
  input_schema:
    type: object
    required: [title, content]
    properties:
      title:   { type: string, description: Short title for the artifact. }
      content: { type: string, description: The HTML or Markdown body. }
  read_only: false
```

`Tool` is a **record-plane descriptor Kind** (`helix/kinds/tool.kind.yaml`,
byte-identical Python↔TypeScript). Agents reference tools by name via
`dep_filters.tools`; the invocation metadata (`type` / `endpoint` / `mcp_*` /
`python_*` / `shell_command` / auth) is the host's runtime concern — the
*surface* below is what the model sees.

Scaffold one with the CLI:

```bash
dna new tool generate-artifact -d "Render HTML/Markdown into a shareable artifact."
```

## The one-liner: `load_tools`

```python
from dna import load_tools

tools = load_tools("tools-demo")            # boots a filesystem kernel for the scope
surface = tools["generate-artifact"]        # or raises ToolNotFound
surface.description                          # the text the model reads
surface.parameters                           # the args JSON Schema (== spec.input_schema)
```

`load_tools` returns a `ToolLibrary` — a lazy, cached, read-only mapping from
tool name to its `ToolSurface` (`{description, parameters}`). Ask for a tool
that does not exist and you get a typed error, never an empty surface.

```python
"generate-artifact" in tools     # True — cheap; does not project the surface
tools.names()                    # ['generate-artifact', ...] (every Tool doc)
```

`base_dir` follows the `Kernel.quick` convention — omit it and it falls back to
the `DNA_BASE_DIR` environment variable, then `.dna` in the working directory.

=== "TypeScript"

    Reading a record document needs no async work, so `get` is **sync** (only
    `loadTools`, which boots the kernel, is async):

    ```ts
    import { loadTools } from "@ruinosus/dna";

    const tools = await loadTools("tools-demo");
    const surface = tools.get("generate-artifact");  // or throws ToolNotFound
    surface.description;                              // the text the model reads
    surface.parameters;                              // the args JSON Schema
    ```

## Fail loud: `ToolNotFound`

`load_tools` **raises** when a tool is missing, instead of returning an empty
surface that could silently reach a model as a tool with no description:

```python
from dna import ToolNotFound

try:
    surface = tools["search"]
except ToolNotFound as exc:
    # exc.name == "search"; exc.available lists the tools the scope does ship.
    raise
```

`ToolNotFound` is a `LookupError` (so `except LookupError` catches it too); in
TypeScript it is an `Error` subclass with `.toolName` / `.scope` / `.available`.

## One source, two runtimes (the dogfood)

Because a Tool is one document read through one byte-identical Kind descriptor,
the **same** surface is served to a Python `@tool` backend and a TypeScript
CopilotKit `useCopilotAction` frontend. The example under
`examples/tools_as_data/` proves it: `read_py.py` and `read_ts.ts` load the
same `generate-artifact` Tool and print **byte-identical** `{description,
parameters}` JSON — asserted against one committed oracle
(`expected-surface.json`) by both the Python and TypeScript test suites.

```bash
python examples/tools_as_data/read_py.py     # Python surface
bun   run examples/tools_as_data/read_ts.ts  # identical TypeScript surface
```

## Tenant overrides (the SaaS hook)

A `Tool` is an overlayable Kind, so a tenant overlay of a tool's description or
parameters wins for that tenant while the base stays intact — no code change:

```
<root>/shop/tools/search.yaml                          # base description
<root>/tenants/acme/scopes/shop/tools/search.yaml      # ACME's override
```

```python
from dna.kernel import Kernel
from dna.adapters.filesystem.source import FilesystemSource
from dna.tools import ToolLibrary

k = Kernel.auto(source=FilesystemSource(root))
base = ToolLibrary(k.instance("shop"))
acme = ToolLibrary(k.with_tenant("acme").instance("shop"))

base["search"].description   # the shared base
acme["search"].description   # ACME's override — base untouched
```

## When you need more than the surface

`load_tools` is a thin convenience over the kernel. For the full Tool document
(invocation metadata, auth, `output_schema`) or other kinds, reach for the
manifest instance directly (`tools.mi`) or build your own with `Kernel.quick` /
[`Kernel.from_config`](configuring-ports.md) and use the
[blessed query surface](read-document-data.md).
