# dna-client (Python)

The **official Python client for the DNA REST API** (`dna api serve`).
Spec-parity twin of the TypeScript [`dna-client`](https://www.npmjs.com/package/dna-client):
both cover the same surface, derived from the same OpenAPI document
(`docs/openapi.json`, dumped from the FastAPI app) — so consumers stop
hand-rolling HTTP.

- **Typed inputs**, `httpx`-based, sync, context-manageable.
- **Complete** — a named method for EVERY operation in the spec, reads and
  writes alike. `client.request(...)` remains as a low-level escape hatch, but
  no route depends on it.
- **Guarded** — a drift test re-dumps the live schema and fails CI if the
  committed spec is stale, *and* fails if any operation (of any HTTP method)
  has no named method. Adding a write route cannot pass silently.

## Install

```bash
pip install dna-client        # or: uv add dna-client
```

Only runtime dep is `httpx`. Python >= 3.12.

## Usage

```python
from dna_client import DnaClient

with DnaClient(
    "http://127.0.0.1:8080",
    token="…",                 # optional — for --auth token/config
    scope="dna-development",    # optional default applied to every call
) as dna:
    agents = dna.list_agents()
    prompt = dna.agent_prompt("jarvis")
    hits = dna.search_memories("tenancy invariant", k=3)
    board = dna.get_board("dna-development", recent=6)

    # Writes are named methods too — no escape hatch needed.
    dna.remember_memory("a lesson worth keeping", area="ops")
    dna.delete_memory("s-foo")
    dna.set_insight_state("i-42", "actioned")

    # Workspace routes are identity-scoped: the boundary comes from the caller's
    # verified claims, so they never take the client's default scope/tenant.
    ws = dna.create_workspace("Acme")           # id is minted server-side
    dna.create_invite(ws["workspace_id"], "teammate@acme.com", role="member")
```

Routes with security semantics say so in their docstring — e.g.
`create_project()` is **403** without an active workspace membership, and
`revoke_workspace_member()` is **409** on the last remaining owner.

A non-2xx response raises `DnaApiError` (carrying `.status` and the API's
`{"detail": ...}` payload).

## Note on return types

Every DNA REST handler returns an untyped JSON object (`dict[str, Any]`), so the
OpenAPI **response** schemas are opaque. Request inputs (query/path params) are
typed; response bodies are `dict[str, Any]`. Tighten the API's response models to
tighten these.

## Parity

This client and the TypeScript twin are generated from the SAME
`docs/openapi.json` — spec-parity, not byte-parity. See
[Using the DNA client](https://ruinosus.github.io/dna/guides/using-the-client/).
