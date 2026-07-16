# dna-client (TypeScript)

The **official TypeScript client for the DNA REST read-API** (`dna api serve`).
It is **generated from the API's OpenAPI document** (`docs/openapi.json`, dumped
from the FastAPI app), so it never drifts from the live routes — consumers stop
hand-rolling `fetch`.

- **Typed** — path/query/body types are generated from the spec by
  [`openapi-typescript`](https://openapi-ts.dev/) (`src/schema.ts`); the client
  is a thin wrapper over [`openapi-fetch`](https://openapi-ts.dev/openapi-fetch/).
- **Read-first** — named methods cover the `/v1/*` GET read surface. The full
  typed surface (including the few writes) is reachable via `client.raw`.
- **Spec-parity with the Python twin** (`dna-client` on PyPI): both are generated
  from the SAME `docs/openapi.json`.

## Install

```bash
npm install dna-client        # or: bun add dna-client
```

ESM-only, Node >= 20 or Bun.

## Usage

```typescript
import { DnaClient } from "dna-client";

const dna = new DnaClient({
  baseUrl: "http://127.0.0.1:8080",
  token: process.env.DNA_API_TOKEN,   // optional — for --auth token/config
  scope: "dna-development",            // optional default applied to every call
});

// Reads (named, typed methods)
const { agents } = await dna.listAgents();
const prompt = await dna.agentPrompt("jarvis");
const hits = await dna.searchMemories({ q: "tenancy invariant", k: 3 });
const board = await dna.getBoard({ scope: "dna-development", recent: 6 });

// The full typed surface (incl. writes) via the underlying openapi-fetch client
const { data, error } = await dna.raw.DELETE("/v1/memories/{name}", {
  params: { path: { name: "s-foo" } },
});
```

A non-2xx response throws `DnaApiError` (carrying `.status` and the API's
`{detail}` payload).

## Note on return types

Every DNA REST handler returns an untyped JSON object (`dict[str, Any]`), so the
OpenAPI **response** schemas are opaque (`Record<string, unknown>`). Request
inputs (query/path/body) ARE strongly typed; response bodies are `unknown`.
Tighten the API's response models to tighten these for free.

## Regenerating

The generated types are committed. After the DNA REST API changes, re-dump the
spec and regenerate:

```bash
python scripts/dump_openapi.py     # rewrite docs/openapi.json (from repo root)
cd packages/client-ts && bun run gen   # regenerate src/schema.ts
```

A drift test (`packages/client-py/tests/test_openapi_drift.py`) fails CI if
`docs/openapi.json` is stale relative to the live routes.
