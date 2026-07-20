# dna-client (TypeScript)

The **official TypeScript client for the DNA REST API** (`dna api serve`).
It is **generated from the API's OpenAPI document** (`docs/openapi.json`, dumped
from the FastAPI app), so it never drifts from the live routes — consumers stop
hand-rolling `fetch`.

Since the TypeScript SDK was frozen, this is **the** TypeScript bridge to DNA:
speak REST to the server rather than reimplementing the kernel.

- **Typed** — path/query/body types are generated from the spec by
  [`openapi-typescript`](https://openapi-ts.dev/) (`src/schema.ts`); the client
  is a thin wrapper over [`openapi-fetch`](https://openapi-ts.dev/openapi-fetch/).
- **Complete** — a named method for EVERY operation in the spec, reads and
  writes alike. `client.raw` is still exposed for direct access, but no route
  depends on it.
- **Guarded** — a coverage test reads the spec and fails if any operation (of
  any HTTP method) has no named method. Adding a write route cannot pass
  silently.
- **Spec-parity with the Python twin** (`dna-client` on PyPI): both are generated
  from the SAME `docs/openapi.json`, and both enforce the same coverage guard.

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

// Writes are named methods too — no escape hatch needed
await dna.rememberMemory({ summary: "a lesson worth keeping", area: "ops" });
await dna.deleteMemory("s-foo");
await dna.setInsightState("i-42", "actioned");

// Workspace routes are identity-scoped: the boundary comes from the caller's
// verified claims, so they never take the client's default scope/tenant.
const ws = await dna.createWorkspace({ name: "Acme" }); // id minted server-side
await dna.createInvite(ws.workspace_id, { email: "teammate@acme.com" });

// `raw` is still there for direct, fully-typed access
const { data, error } = await dna.raw.DELETE("/v1/memories/{name}", {
  params: { path: { name: "s-foo" } },
});
```

A non-2xx response throws `DnaApiError` (carrying `.status` and the API's
`{detail}` payload). Routes with security semantics say so in their TSDoc — e.g.
`createProject()` is **403** without an active workspace membership, and
`revokeWorkspaceMember()` is **409** on the last remaining owner.

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
