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

## Workspace tenancy (Model B)

The identity→workspace boundary writes (see
[Tenancy layers](../concepts/tenancy-layers.md)). Auth is **by membership**: an
Owner/Admin of the workspace to manage it; the invitee (a verified email claim)
to accept. Under `--auth config` the actor is the verified token identity (which
wins over any body value); under `none`/`token` a trusted portal passes the
verified claims. These routes live under `/v1/workspaces/*` and are **exempt from
the config-auth workspace bind** — they name the workspace in the path and do
their own RBAC, so a caller who holds no active membership yet (an invitee, or the
founder before bootstrap) can still reach them.

- `POST /v1/workspaces/{id}/provision-owner` — the **first-login owner
  bootstrap**. Body `{claims: {oid, email, tid, …}}` (the verified identity). It
  makes the signed-in user the **owner of their own workspace**: it creates the
  `Workspace` (id == the verified `tid`, so existing rows keyed `tenant==tid` are
  already this workspace's data — **zero migration**) if absent, then a bound
  owner `WorkspaceMembership`, `active`. **Idempotent + first-owner-only**: a
  re-call by the same identity is a no-op returning the membership; a later
  *different* user does not auto-escalate (`owner_exists` no-op). The path `id`
  **must** equal the verified `tid` — a cross-`tid` caller is `403`'d (a verified
  identity from another org can never seize a `tid`-workspace).
- `POST /v1/workspaces/{id}/invites` — invite an identity by email (Owner/Admin);
  a `pending` `WorkspaceMembership`.
- `GET /v1/workspaces/{id}/members` — list the workspace's members (Owner/Admin).
- `POST /v1/workspaces/{id}/members/revoke` — **remove a member** (Owner/Admin).
  Body `{actor: {claims}, target_email | target_oid}`. RBAC is checked before the
  target is revealed (no existence oracle). **Policy: the last remaining owner can
  never be revoked** (`409`, fail-closed); a non-Owner/Admin is `403`; an unknown
  target is `404`.
- `POST /v1/workspaces/accept` — accept every pending invite the caller's verified
  sign-in claims (binds the durable `oid`, flips `pending → active`).

The RBAC + last-owner + first-owner + invite/accept decisions are the pure
`dna.tenancy` policy (`resolution` / `invites` / `ownership`), each with a 1:1
TypeScript twin gated by shared parity fixtures.
