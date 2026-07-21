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
- `GET /v1/agents/{name}/prompt` — compose an agent's system prompt **live**.
  `?explain=true` (opt-in) also returns per-section provenance — the
  `dna explain` map (source artifact, content hash, version, layer origin and
  tenant-overlay marker per composed section) plus an `attribution` honesty
  marker (`declared` = kernel-owned template, the section map is correct by
  construction; `heuristic` = the agent has its own `promptTemplate`, section
  detection is fail-soft string matching and may omit/over-report sections).
  The composed `prompt` is byte-identical with or without the flag; without it
  the response shape is unchanged.
- `GET /v1/tools` — the Tool surfaces in a scope
- `GET /v1/memories` — the tenant's stored memories (`Engram`)
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

- `POST /v1/workspaces` — **create a workspace and its first owner**. Body
  `{name, slug?, claims: {oid, email, tid, …}}`. The `workspace_id` is **minted by
  the server** — opaque, unguessable, never derived from the Azure `tid`, and
  there is deliberately **no request field for it** (decision **D5**). That is the
  anti-takeover mechanism: an id nobody can name is an id nobody can race you to.
  `slug` defaults to a slugified `name` and is made unique. The caller's verified
  identity becomes the active `owner` (its `tid` is stored as provenance only).
  Requires no pre-existing membership — a brand-new user belongs to nothing yet.
- `GET /v1/workspaces` — **the workspaces the caller belongs to** (the workspace
  switcher's source). Enumerates by **ACTIVE membership**, never by `tid`; a
  `pending` invite is not listed, and an unknown identity gets an empty list.
  Under `--auth config` the caller is the verified token identity; under
  `none`/`token` pass `actor_oid` / `actor_email`.
- `POST /v1/projects` — **create a Project inside a workspace** (decision **A1**:
  the owning `workspace_id` is an explicit field on the Project). Body
  `{workspace_id, name, slug?, claims}`. The caller must hold an **active**
  `WorkspaceMembership` there, else `403`. The write scope and the project's
  `board_scope` are **derived** from the workspace + slug and are not accepted
  from the caller.
- `POST /v1/workspaces/{id}/provision-owner` — the **sign-in reconcile**. Body
  `{claims: {oid, email, tid, …}}` (the verified identity). Since **D5** it
  **creates nothing**: it requires an **active** `WorkspaceMembership` in `{id}`
  and returns it (`already_member`), back-filling the `Workspace` identity doc only
  for an owner whose doc is missing. **Idempotent** — safe on every dashboard load.
  A caller holding no active membership here is `403`'d, so a verified identity
  from another org can never seize a workspace; the `tid` is not consulted at all.
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
