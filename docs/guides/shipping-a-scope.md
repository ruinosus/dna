# How to ship a scope with your app

When you deploy an app that composes prompts from a DNA scope, the scope has to
travel **inside the deployable** — the artifact you ship is the *app*, not the
repo. The robust way to do that is to treat the scope as **package data**: files
that ride along with your installed package, resolved from *inside* the package
via [`importlib.resources`](https://docs.python.org/3/library/importlib.resources.html)
(Python) or the package's own location (TypeScript).

This guide shows the deploy-safe pattern and contrasts it with the fragile one.

## The fragile pattern (don't do this)

Consumers reach for two brittle mechanisms and stitch them together:

```python
# 1. path navigation to find the scope relative to a source file
_BAKED_BASE_DIR = Path(__file__).resolve().parents[2] / ".dna"
mi = Kernel.quick("support", base_dir=str(_BAKED_BASE_DIR))
```

```dockerfile
# 2. a MANUAL copy of the scope into the image, because the image is the app,
#    not the repo — the .dna dir is not there unless you put it there
COPY .dna ./.dna
```

Both break silently:

- `parents[N]` hard-codes a directory depth. Move the file, install the package
  into `site-packages`, or run from a different working directory and the count
  is wrong — the scope is not found.
- The `COPY .dna` is invisible glue. Forget it (or restructure the image) and
  the app boots with **no scope** — no agents, no skills — and the failure only
  shows up at runtime. (This is a real bug: a pilot consumer's Docker image
  never copied its skills; every skill silently vanished in production.)

## The deploy-safe pattern: scope as package data

Declare the scope as package data so `pip install` / `uv build` (or
`npm install`) carries it into the wheel / tarball **and** into your Docker
image — then resolve it by an **anchor** (your package name), never by path.

There is a complete, runnable example in
[`examples/shipping-a-scope/`](https://github.com/ruinosus/dna/tree/main/examples/shipping-a-scope).

### 1. Put the scope inside your package

```
acme_support_bot/
├── __init__.py
└── .dna/
    └── support/
        ├── Genome.yaml
        └── agents/
            └── triage.yaml
```

### 2. Declare it as package data

=== "Python — Hatch"

    ```toml
    # pyproject.toml
    [tool.hatch.build.targets.wheel]
    packages = ["acme_support_bot"]
    # Hatch ships tracked files under the package by default. If your VCS
    # IGNORES `.dna` (many repos do), force it into the wheel with `artifacts`:
    artifacts = ["acme_support_bot/.dna/**"]
    ```

=== "Python — setuptools"

    ```toml
    # pyproject.toml
    [tool.setuptools.package-data]
    acme_support_bot = [".dna/**/*"]
    ```

    ```
    # MANIFEST.in  (belt-and-suspenders for the sdist)
    recursive-include acme_support_bot/.dna *
    ```

=== "TypeScript"

    ```jsonc
    // package.json — `files` is what npm packs into the published tarball
    {
      "name": "acme-support-bot",
      "files": ["dist", ".dna"],
      "exports": {
        ".": "./dist/index.js",
        "./package.json": "./package.json"
      }
    }
    ```

    Adding `"./package.json": "./package.json"` to `exports` lets DNA resolve
    the package root by name even when `exports` is otherwise restrictive.

### 3. Resolve it by anchor — no path navigation

=== "Python"

    ```python
    from dna import load_prompts

    # `anchor` is your package NAME. DNA finds `<package>/.dna/support` from
    # inside the installed package — works from a source checkout, a wheel,
    # and a Docker image alike.
    prompts = load_prompts("support", anchor="acme_support_bot")
    TRIAGE_INSTRUCTIONS = prompts["triage"]     # composed, clean, or raises
    ```

=== "TypeScript"

    ```ts
    import { loadPrompts } from "dna-sdk";

    const prompts = await loadPrompts("support", { anchor: "acme-support-bot" });
    export const TRIAGE = await prompts.get("triage");
    ```

Or wire it declaratively with the [`pkg://` source scheme](#the-pkg-source-scheme)
in a `dna.config.yaml`.

### 4. The Dockerfile — nothing special

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install .          # installs acme_support_bot INCLUDING its .dna data
CMD ["python", "-m", "acme_support_bot"]
```

There is **no `COPY .dna`** and **no path math**. `pip install` (or `uv sync`)
places the package — scope data included — onto the import path, and
`anchor="acme_support_bot"` finds it there regardless of the container's working
directory. TypeScript is the same story: `npm install` unpacks the `files` into
`node_modules`, and `anchor: "acme-support-bot"` resolves it by name.

## The `pkg://` source scheme

For the declarative path (`dna.config.yaml` + `Kernel.from_config`), the same
resolution is available as a **source URL**:

```yaml
# dna.config.yaml
source: pkg://acme_support_bot          # subpath defaults to .dna
# source: pkg://acme_support_bot/.dna   # explicit subpath, same result
```

```python
from dna import Kernel

kernel = Kernel.from_config()           # discovers ./dna.config.yaml
mi = kernel.instance("support")
prompt = mi.build_prompt(agent="triage")
```

`pkg://<package>[/<subpath>]` resolves the scopes-root embedded in the installed
package and boots the kernel over it. A missing package or subpath fails loud
with a packaging-oriented message, never a silent empty scope.

## Read-only by nature

A scope embedded as package data is **read-only**. Package data may be installed
in ways that are not a mutable working tree, and composition only ever *reads*
the scope. Both `anchor=` and `pkg://` give you a read path. To **write** a scope
(drafts, overlays, versioning), use a filesystem or Postgres source — see
[configuring ports](configuring-ports.md).

## Resolution precedence

`load_prompts` picks its scopes-root by this order (first one set wins), so an
explicit override or a deploy-time env var always beats the packaged default:

| Precedence | Source | Typical use |
|---|---|---|
| 1 | `base_dir=` / `baseDir` argument | tests, explicit overrides |
| 2 | `DNA_BASE_DIR` env var | mount a scope into a container at deploy time |
| 3 | `anchor=` (package data) | **the scope that ships with the app** |
| 4 | `.dna` in the CWD | local development from the repo |
