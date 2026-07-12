# The REST read-API — DNA's HTTP face for web apps

DNA has two HTTP faces over the same core, for two different kinds of consumer:

| Face | Consumer | Shape |
|---|---|---|
| **MCP** (`dna mcp serve`) | AI clients — Claude, ChatGPT, Cursor | stateful session (tools + streaming) |
| **REST** (`dna api serve`) | web apps — a dashboard, a portal | plain request/response (cacheable) |

A web app should **not** open an MCP session per page render — MCP is a stateful
agent protocol, not a data-fetch API. For a dashboard that lists agents, composes
a prompt, or browses memory, run the REST read-API instead.

## Run it

```bash
dna api serve --port 8080 --base-dir ./.dna --scope _lib --auth none
```

`dna api serve` mirrors `dna mcp serve` (`--host` / `--port` / `--scope` /
`--base-dir` / `--auth [none|token]`). With `--auth token` it requires
`Authorization: Bearer $DNA_API_TOKEN`; a `# TODO(hosted)` OAuth 2.1 / per-tenant
bearer seam matches the MCP tenancy model.

## Endpoints (read + one guarded delete)

Every endpoint is tenant-scoped via a `tenant` query param (base + that tenant's
overlay only — never another tenant's data):

- `GET /health`
- `GET /v1/agents` — list the prompt-target agents in a scope
- `GET /v1/agents/{name}/prompt` — compose an agent's system prompt **live**
- `GET /v1/tools` — the Tool surfaces in a scope
- `GET /v1/memories` — the tenant's stored memories (`LessonLearned`)
- `GET /v1/memories/search?q=…` — recall (semantic when indexed, else lexical)
- `DELETE /v1/memories/{name}` — the tenant deletes one of its own memories

The definitions + search endpoints call the **same** `*_impl` functions the MCP
server uses — one core, two faces, zero duplicated logic.
