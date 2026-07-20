# shipping-a-scope — ship a DNA scope with your deployed app

A minimal app package, `acme_support_bot`, that embeds a DNA scope (`support`)
as **package data** and resolves it *from inside the installed package* — so the
scope travels with the app into a wheel and into a Docker image, with **no**
`Path(__file__).parents[N]` path math and **no** manual `COPY .dna`.

```
acme_support_bot/
├── __init__.py            # triage_prompt() → load_prompts("support", anchor="acme_support_bot")
├── package.json           # `files: [".dna"]` ships the scope in the npm tarball
└── .dna/support/          # the embedded scope (Genome + triage agent)
pyproject.toml             # hatch: ships acme_support_bot/.dna into the wheel
dna.config.yaml            # source: pkg://acme_support_bot  (declarative path)
```

## Run it (Python)

```python
from acme_support_bot import triage_prompt
print(triage_prompt())          # composed system prompt for the triage agent
```

or declaratively, via the `pkg://` source scheme:

```python
from dna import Kernel
mi = Kernel.from_config("dna.config.yaml").instance("support")
print(mi.build_prompt(agent="triage"))
```

## The point

The resolution works from a source checkout, an installed wheel, and a container
whose working directory is **not** the repo — proven by
`packages/sdk-py/tests/test_scope_as_package_data.py`, which materializes this
package at an install location and resolves the scope from an empty CWD (the
Docker scenario). See the guide **"How to ship a scope with your app"**.
