# dna-client (Python)

The **official Python client for the DNA REST read-API** (`dna api serve`).
Spec-parity twin of the TypeScript [`dna-client`](https://www.npmjs.com/package/dna-client):
both cover the same read surface, derived from the same OpenAPI document
(`docs/openapi.json`, dumped from the FastAPI app) — so consumers stop
hand-rolling HTTP.

- **Typed inputs**, `httpx`-based, sync, context-manageable.
- **Read-first** — named methods for the `/v1/*` GET read surface; the full
  surface (incl. the few writes) is reachable via `client.request(...)`.
- A **drift test** re-dumps the live schema and fails CI if the committed spec
  is stale — keeping the client in sync with the API.

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

    # The full surface (incl. writes) via the low-level request()
    dna.request("DELETE", "/v1/memories/s-foo", params={"tenant": "acme"})
```

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
