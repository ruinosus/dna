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
§ "Using the SQLAlchemy adapter")
`safety-ml` (PII/toxicity models),
`github-copilot` (pure GitHub Copilot SDK binding),
`all`, `dev`.

## Minimal example

```python
from dna import Kernel

# Scan a scope (directory of YAML/Markdown manifests under .dna/)
mi = Kernel.quick("hello-genome", base_dir="examples/hello-genome/.dna")

# Every instance is identified by (apiVersion, kind, name)
for d in mi.instances:
    print(d.api_version, d.kind, d.name)

# Compose agent + soul + skills + guardrails into one system prompt
print(mi.build_prompt(agent="greeter"))
```

Runnable version: [`examples/hello-genome/run.py`](https://github.com/ruinosus/dna/blob/main/examples/hello-genome/run.py).

## Runtime-neutral definitions

Use `DnaClient` when an application owns the runtime but wants DNA to own its
declarative definitions. The client boots the configured source, resolves
KindDefinitions through the Kernel, applies scope/tenant composition, and
returns data-only contracts.

```python
from dna import DnaClient

client = await DnaClient.from_env(scope="development", tenant="acme")
async with client:
    # Uses Genome.spec.default_agent; pass a name only as an explicit override.
    definition = await client.resolve_agent()
    kinds = await client.kinds.list()
    tool_kind = await client.kinds.describe("Tool")
    tools = await client.instances.list("Tool")
```

Source selection is `DNA_SOURCE_URL` then `base_dir` / `DNA_BASE_DIR`, then
`./.dna`. `ResolvedAgent`, `ResolvedTool`, `ResolvedMcpServer`, and
`KindDescriptor` do not start a model, server, session, or event loop.

The optional GitHub Copilot binding converts one resolved definition while the
consumer retains lifecycle ownership:

```python
from dna.integrations.github_copilot import build_github_copilot_agent

agent = build_github_copilot_agent(
    definition,
    tools=[write_review_report],
    on_permission_request=permission_handler,
)

async with agent:
    session = agent.create_session()
    async for chunk in agent.run(prompt, session=session, stream=True):
        print(chunk.text or "", end="")
```

Install this binding with `pip install "dna-sdk[github-copilot]"`. It maps the
composed prompt, model, MCP federations and confirmation policy but does not own
the Copilot CLI or execute declared tools.

## Layout

```
dna/
├── kernel/       # Kernel (mediator over 5 ports), Instance, ManifestInstance
├── application/  # transport-neutral use cases and live source handle
├── adapters/     # filesystem (core); sqlite/postgres/sqlalchemy_ via extras
├── integrations/ # optional pure bindings to consumer-owned runtimes
├── extensions/   # helix (core Kinds) + market formats + governance
├── sync/         # lockfile + instance hashing
└── safety/       # safety pipeline (optional ML extras)
```

## Tests

```bash
uv run pytest tests/ -v
```

The suite includes the market-fidelity conformance tests
(`tests/test_market_conformance.py`) and the golden fixtures that freeze
behavior crossing a boundary (`tests/goldens/`, `tests/golden-fixtures/`).
