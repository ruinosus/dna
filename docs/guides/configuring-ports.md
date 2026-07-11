# How to configure ports (`dna.config.yaml`)

The kernel is a mediator over a handful of ports — where documents live
(source), how they are searched, how text is embedded. You can wire those
imperatively, or declare them once in a `dna.config.yaml` and let
`Kernel.from_config` do the wiring. The file is **language-agnostic**: the same
`dna.config.yaml` drives the Python and the TypeScript SDK.

## The file

```yaml
# dna.config.yaml
source: postgresql://dna:dna@localhost:5432/dna   # required
search: pgvector          # pgvector | sqlite-vec | off   (default: off)
embedding: onnx           # onnx | fake | off             (default: off / fake floor)
```

Only `source` is required. `dna.config.yaml` is parsed and **validated** —
an unknown key, a missing `source`, or an out-of-enum `search`/`embedding`
value fails loud with a didactic message rather than silently doing the wrong
thing.

### `source` — where documents live

| URL | Adapter |
|---|---|
| `file://<path>` (or a plain path) | filesystem (read + write on disk) |
| `pkg://<package>[/<subpath>]` | filesystem **read-only** over a scope embedded as **package data** — travels with your app (wheel / Docker). See [shipping a scope with your app](shipping-a-scope.md). |
| `sqlite:///<path>` | `SqlAlchemySource` (aiosqlite) — **Python only** |
| `postgresql://<user>:<pass>@<host>/<db>` | `SqlAlchemySource` (asyncpg) |

The URL→source resolution is a public surface in its own right —
`dna.adapters.source_from_url` (Python) / `sourceFromUrl` (TypeScript) — so a
host can use it without a config file. The `dna` CLI consumes the same factory,
which is why `DNA_SOURCE_URL=sqlite://…` and `postgresql://…` now work from the
CLI, not just `file://`.

## Booting from it

```python
from dna import Kernel

kernel = Kernel.from_config()              # discovers ./dna.config.yaml
kernel = Kernel.from_config("deploy/dna.config.yaml")   # explicit path

mi = kernel.instance("helpdesk")
prompt = mi.build_prompt(agent="triage")
```

With **no** `dna.config.yaml` present (and no path given), `from_config`
behaves exactly like the bare default — a filesystem `.dna` source — so it is
always safe to call.

`from_config` returns a wired `Kernel`; use `.instance(scope)` for the manifest.
For the Runtime vocabulary, `Runtime.from_config(...).manifest(scope)` returns a
`Runtime` (the class is threaded through, like `auto` / `quick`).

`from_config` is a **boot-time** factory: SQL sources run their schema
migrations while it builds, on a short-lived event loop. Call it during
startup, not from inside a running loop.

=== "TypeScript"

    ```ts
    import { fromConfig } from "@ruinosus/dna";

    const kernel = await fromConfig();                    // discovers ./dna.config.yaml
    const mi = await kernel.instance("helpdesk");
    const prompt = await mi.buildPrompt({ agent: "triage" });
    ```

    The TypeScript runtime ships the **filesystem** and **postgres** source
    adapters. A `sqlite://` source — or a `pgvector` search — is Python-only
    and fails loud in TypeScript with that explanation, so a shared
    `dna.config.yaml` never silently misbehaves across languages.

## `search` and `embedding`

These select opt-in providers and are wired only when you ask for them (so the
default install never pulls ONNX or sqlite-vec):

- `embedding: onnx` registers the real all-MiniLM embedding provider;
  `fake` / `off` leave the deterministic zero-dependency floor.
- `search: sqlite-vec` registers the offline sqlite-vec record-search provider;
  `pgvector` registers the Postgres one (Python), reusing the config's DSN;
  `off` leaves the lexical fallback.
