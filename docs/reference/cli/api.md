# `dna api`

Expose the live DNA (definitions + memory) over a REST read-API.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna api --help`.

## `dna api serve`

Run the DNA REST read-API (the WEB face — a request/response HTTP API).


LOCAL (no auth):
  $ dna api serve --port 8080 --auth none
  $ curl -s localhost:8080/v1/agents


ENDPOINTS (read-focused; tenant-aware via a `tenant` query param):
  GET    /health                              -> {ok:true}
  GET    /v1/agents?scope=&tenant=            -> {scope, agents:[...]}
  GET    /v1/agents/{name}/prompt?scope=&tenant=  -> {scope, agent, prompt, ...}
  GET    /v1/tools?scope=&tenant=             -> {scope, tools:[...]}
  GET    /v1/memories?scope=&tenant=          -> {memories:[...]}
  GET    /v1/memories/search?q=&scope=&tenant=&k=5  -> {query, hits:[...]}
  DELETE /v1/memories/{name}?scope=&tenant=   -> delete from the tenant's OWN overlay
  GET    /v1/sources?scope=&tenant=           -> {sources:[...]}
  GET    /v1/insights?scope=&tenant=&state=&source=  -> {insights:[...]}
  GET    /v1/orgs?tenant=                      -> {orgs:[...]}
  GET    /v1/projects?tenant=                  -> {projects:[...]}
  GET    /v1/projects/{slug}?tenant=           -> {project, repos:[...]}
  GET    /v1/projects/{slug}/members?tenant=&viewer=  -> {members:[...], viewer}
  POST   /v1/projects/{slug}/members?tenant=   -> invite/set-role {user, role, actor} (RBAC)
  DELETE /v1/projects/{slug}/members/{user}?tenant=&actor=  -> remove (RBAC)
  GET    /v1/repos?tenant=                     -> {repos:[...]}
  GET    /v1/board?scope=&tenant=              -> {counts, totals, recent}
  PUT    /v1/tenant-plan                       -> billing->runtime TenantPlan write {tenant, tier_id, ...}

Every endpoint reads/writes through the SAME live kernel `dna` commands +
`dna mcp serve` use — this is a second HTTP face over one core, not a copy.

```text
dna api serve [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--auth` | Auth mode. `none` = local dev (no bearer). `token` = require `Authorization: Bearer <DNA_API_TOKEN>` on every route (the MVP shared token; the hosted OAuth 2.1 / per-tenant bearer slots into the same seam later). _(default: `none`)_ |
| `--base-dir` | Source directory override (else DNA_SOURCE_URL / DNA_BASE_DIR / ./.dna). |
| `--cors-origin` | Allowed browser origin for CORS (repeatable; else DNA_API_CORS_ORIGINS, else `http://localhost:3000`). |
| `--help` | Show this message and exit. |
| `--host` | Bind host. _(default: `127.0.0.1`)_ |
| `--port` | Bind port. _(default: `8080`)_ |
| `--scope` | Default scope for endpoints that omit one (else the sole/first scope). |
| `--token` | Expected bearer token for --auth token (else the DNA_API_TOKEN env var). |

