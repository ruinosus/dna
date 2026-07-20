# Using the DNA client — typed access to the REST read-API

The [REST read-API](rest-api.md) (`dna api serve`) is a plain HTTP surface, so
anything can call it with `fetch`/`requests`. But hand-rolling HTTP means
hand-maintaining URLs, query params, and response shapes — and re-doing it in
every consumer. The **official DNA clients** remove that: a typed client for
TypeScript and Python, **generated from the API's OpenAPI document**, so they
never drift from the live routes.

| Client | Package | Install |
|---|---|---|
| TypeScript | [`dna-client`](https://www.npmjs.com/package/dna-client) (npm) | `npm install dna-client` |
| Python | [`dna-client`](https://pypi.org/project/dna-client/) (PyPI) | `pip install dna-client` |

## How they stay in sync — one spec, two clients

`dna api serve` is a FastAPI app, and FastAPI auto-emits an OpenAPI document from
its routes. That document is dumped to `docs/openapi.json`
(`python scripts/dump_openapi.py`) and committed as the **single generation
source**:

- the **TypeScript** client generates its path/query/body types from it with
  [`openapi-typescript`](https://openapi-ts.dev/) and wraps
  [`openapi-fetch`](https://openapi-ts.dev/openapi-fetch/);
- the **Python** client is a thin `httpx` wrapper whose method surface + query
  params are derived from the same spec.

Because both come from the SAME spec, they stay semantically in sync —
**spec-parity**, not byte-parity (the two languages differ idiomatically). A
**drift test** re-dumps the schema from the live app and fails CI if
`docs/openapi.json` is stale, so a route change can't silently break the clients.

!!! note "Return types are intentionally loose"
    Every DNA REST handler returns an untyped JSON object (`dict[str, Any]`), so
    the OpenAPI **response** schemas are opaque (`Record<string, unknown>` in TS,
    `dict[str, Any]` in Python). Request inputs (query/path/body) **are** strongly
    typed; response bodies are not. Tighten the API's response models to tighten
    the clients for free.

## Full coverage — reads *and* writes

The clients expose a named method for **every operation in the spec**: the
`/v1/*` reads a dashboard needs (list agents, compose a prompt, browse memory,
read the board) *and* every write (memory remember/delete, insight state, project
and workspace membership, workspace/project creation, invites, workspace-plan).

The underlying client is still exposed — `.raw` in TS, `.request(...)` in Python
— but nothing requires it. That matters because the escape hatch was untyped in
Python and easy to get subtly wrong in both.

!!! note "Coverage is enforced, not aspirational"
    A guard in each client reads `docs/openapi.json` and fails if any operation
    — of **any** HTTP method — has no named method
    (`client-py/tests/test_openapi_drift.py`, `client-ts/tests/client.test.ts`).
    Its allowlist is keyed by `(method, path)` and is empty today, so adding a
    write route to the API breaks CI until the clients catch up. The earlier
    version of this guard enumerated GETs only, which is how `POST /v1/workspaces`
    and `POST /v1/projects` shipped uncovered.

### Security semantics are documented on the method

Several writes are tenancy boundaries, and their docstrings say what they refuse
— e.g. `createProject`/`create_project` is **403** without an *active* workspace
membership (a pending invite does not count), `revokeWorkspaceMember` is **409**
on the last remaining owner, and `createWorkspace` will not accept a
`workspace_id` at all because the server mints it. The workspace routes are
identity-scoped: they resolve the boundary from the caller's verified claims and
never receive the client's default `scope`/`tenant`.

## TypeScript

```typescript
import { DnaClient } from "dna-client";

const dna = new DnaClient({
  baseUrl: "http://127.0.0.1:8080",
  token: process.env.DNA_API_TOKEN,   // optional — for --auth token/config
  scope: "dna-development",            // optional default applied to every call
});

const { agents } = await dna.listAgents();
const prompt = await dna.agentPrompt("jarvis");
const hits = await dna.searchMemories({ q: "tenancy invariant", k: 3 });
const board = await dna.getBoard({ scope: "dna-development", recent: 6 });

// Writes are named methods too:
await dna.rememberMemory({ summary: "a lesson worth keeping", area: "ops" });
await dna.setInsightState("i-42", "actioned");
const ws = await dna.createWorkspace({ name: "Acme" });  // id minted server-side
await dna.createInvite(ws.workspace_id, { email: "teammate@acme.com" });

// `.raw` remains for direct, fully-typed access:
await dna.raw.DELETE("/v1/memories/{name}", { params: { path: { name: "s-foo" } } });
```

A non-2xx response throws `DnaApiError` (carrying `.status` and the API's
`{ detail }` payload).

## Python

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

    # Writes are named methods too:
    dna.remember_memory("a lesson worth keeping", area="ops")
    dna.set_insight_state("i-42", "actioned")
    ws = dna.create_workspace("Acme")            # id minted server-side
    dna.create_invite(ws["workspace_id"], "teammate@acme.com")

    # request() remains for direct access:
    dna.request("DELETE", "/v1/memories/s-foo", params={"tenant": "acme"})
```

A non-2xx response raises `DnaApiError` (same `.status` + `.detail`).

## Tenancy

Both clients accept an optional default `scope`/`tenant` applied to every call
that takes them (a per-call value wins). Under `--auth config` the server
**overwrites** `tenant` from the verified token's workspace membership, so the
default is a convenience for `--auth none` / `--auth token` deployments. See
[the REST read-API guide](rest-api.md) for the auth modes.

## Regenerating after an API change

```bash
python scripts/dump_openapi.py         # rewrite docs/openapi.json from the live app
cd packages/client-ts && bun run gen    # regenerate the TS types (src/schema.ts)
```

The Python client tracks the spec by hand (its drift test enforces the spec is
current); the TS types are regenerated by `bun run gen`. CI fails if either the
committed spec or the TS types are stale.
