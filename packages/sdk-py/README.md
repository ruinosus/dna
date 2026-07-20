# dna-sdk (Python)

Python SDK for **DNA — Domain Notation of Anything**: a microkernel +
extensions runtime for declarative agent notation. See the
[repository README](https://github.com/ruinosus/dna#readme) for the thesis, the architecture and
the full Kind catalog.

## Install

```bash
pip install dna-sdk        # or: uv add dna-sdk
```

Pre-release / exact-pin alternative — from the repo:

```bash
cd packages/sdk-py
uv sync            # or: pip install -e .
```

Optional extras: `postgres`, `sqlite`, `sql` (SqlAlchemySource — one
adapter for both SQL dialects, same tables; see docs/PORT-CONTRACT.md
§ "Using the SQLAlchemy adapter"), `tools`
(langchain `@dna_tool` decorator), `safety-ml` (PII/toxicity models),
`all`, `dev`.

## Minimal example

```python
from dna import Kernel

# Scan a scope (directory of YAML/Markdown manifests under .dna/)
mi = Kernel.quick("hello-genome", base_dir="examples/hello-genome/.dna")

# Every document is identified by (apiVersion, kind, name)
for d in mi.documents:
    print(d.api_version, d.kind, d.name)

# Compose agent + soul + skills + guardrails into one system prompt
print(mi.build_prompt(agent="greeter"))
```

Runnable version: [`examples/hello-genome/run.py`](https://github.com/ruinosus/dna/blob/main/examples/hello-genome/run.py).

## Layout

```
dna/
├── kernel/       # Kernel (mediator over 5 ports), Document, ManifestInstance
├── adapters/     # filesystem (core); sqlite/postgres/sqlalchemy_ via extras
├── extensions/   # helix (core Kinds) + market formats + governance
├── sync/         # lockfile + document hashing
└── safety/       # safety pipeline (optional ML extras)
```

## Tests

```bash
uv run pytest tests/ -v
```

The suite includes the market-fidelity conformance tests
(`tests/test_market_conformance.py`) and the Py↔TS parity fixtures shared
with the TypeScript twin.
