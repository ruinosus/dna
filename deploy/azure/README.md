# Host the DNA MCP server on Azure Container Apps + Microsoft Entra

This is the **self-host recipe** for the DNA MCP server — the runtime face that
serves the *live* DNA (`dna mcp serve`) over the Model Context Protocol. It runs
`dna mcp serve --transport http` in a container on **Azure Container Apps**,
behind an **HTTPS ingress**, authenticated with **Microsoft Entra** bearer
tokens, so any remote/web MCP client (Claude web, ChatGPT, a hosted agent) can
reach everything DNA stores — composed live, tenant-aware, no deploy.

It is **Phase A of DNA-hosted**: one `azd up` stands up your own instance, and
the same recipe is the base the multi-tenant *DNA Cloud* offering builds on.

Everything is **keyless**: the image pull uses a user-assigned **Managed
Identity**, and Entra tokens are validated against Entra's **public JWKS** — no
secret lives in the template or the container.

```
┌────────────┐   HTTPS + Entra JWT   ┌──────────────────────────────┐
│ MCP client │ ────────────────────▶ │ Azure Container App           │
│ (web/agent)│   Bearer <token>      │  dna mcp serve --transport    │
└────────────┘                       │    http --auth jwt (port 8080)│
      ▲                              │  User-assigned Managed Identity│
      │ OAuth 2.1 / PKCE             │  ← reads DNA source (/mnt/dna) │
      ▼                              └──────────────┬───────────────┘
┌────────────┐  validate via JWKS                   │ AcrPull (identity)
│  Microsoft │ ◀────────────────────────────────────┤
│   Entra    │                                      ▼
└────────────┘                              Azure Container Registry
```

---

## What gets provisioned

`infra` (`main.bicep` → `resources.bicep`) creates, in a fresh resource group:

| Resource | Why |
|---|---|
| Log Analytics workspace | the Container App log stream sink |
| Container Apps managed environment | the ACA environment |
| Azure Container Registry (Basic) | holds the image `azd` builds + pushes |
| **User-assigned Managed Identity** | pulls the image from ACR (`AcrPull`) — no registry secret |
| Storage account + **Azure Files share** (`dna-source`) | the DNA source, mounted **read-only** at `/mnt/dna` |
| **Container App** (`mcp`) | external HTTPS ingress on **8080**, runs the image as the identity, with the Entra-JWT auth env wired |

Scale-to-zero is on (`minReplicas: 0`) — idle costs nothing; the first request
after idle pays a cold start.

---

## Prerequisites

- [Azure Developer CLI (`azd`)](https://aka.ms/azd) and the [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli), logged in (`az login`) to the target subscription.
- Rights to create resources in the subscription, and (for auth) to create an **Entra app registration** in your tenant.
- Docker is **not** required locally — `remoteBuild: true` builds the image in ACR.

---

## Step 1 — Register the MCP server in Microsoft Entra

The Container App is an OAuth 2.1 **Resource Server**: it validates the bearer
JWT a client presents and, via the DNA auth↔tenancy bridge, scopes every tool to
the token's tenant. Entra is the identity provider that issues those tokens.

1. **Portal → Microsoft Entra ID → App registrations → New registration.** Name
   it e.g. `dna-mcp`. Single- or multi-tenant per your audience. Register.
2. Note the **Directory (tenant) ID** and the **Application (client) ID**.
3. **Expose an API:**
   - *Expose an API → Application ID URI* → accept the default `api://<client-id>`
     (this is your **audience**).
   - *Add a scope* → e.g. `access_as_user`, admin+user consent, enabled. This is
     the scope MCP clients request.
4. *(Optional, for client apps that log a user in)* under **Authentication** add
   the client's redirect URI, or rely on the client's own registration.

You now have the three values the deploy needs:

| Value | Where it came from | azd env var |
|---|---|---|
| Tenant (directory) ID | step 2 | `ENTRA_TENANT_ID` |
| Audience (`api://<client-id>`) | step 3 | `ENTRA_MCP_AUDIENCE` |
| Tenant claim (optional) | `tenant` default, or `tid` to bind each Entra directory to a DNA tenant | `DNA_MCP_TENANT_CLAIM` |

> **The token IS the tenancy.** The bridge maps a verified token's claim
> (`DNA_MCP_TENANT_CLAIM`, default `tenant`) or a `tenant:<x>` scope to a **DNA
> tenant**, and enforces it: `compose_prompt` / `recall` / `list_stories` read
> only that tenant's layer; a cross-tenant or tenant-less request is denied
> (fail closed). To bind each **Entra directory** to a DNA tenant, set the claim
> to `tid` (Entra always stamps the directory id in `tid`). To carry an
> app-specific tenant, add a claim/scope via an Entra **app role** or an optional
> claim and leave the default `tenant`.

---

## Step 2 — `azd up`

```console
$ cd deploy/azure
$ azd auth login
$ azd env new dna-mcp-prod

# Feed the Entra values (skip these two for an OPEN dev deploy — see below):
$ azd env set ENTRA_TENANT_ID   <your-entra-tenant-guid>
$ azd env set ENTRA_MCP_AUDIENCE api://<your-mcp-app-client-id>
$ azd env set DNA_MCP_TENANT_CLAIM tid       # optional; default is `tenant`

$ azd up
```

`azd up` provisions the stack, builds the image from `deploy/azure/Dockerfile`
(build context = repo root, so the from-source install reaches `packages/`),
pushes it to the ACR, and deploys it. On success it prints the outputs:

```
MCP_URL       https://ca-dna-mcp-<token>.<region>.azurecontainerapps.io
MCP_ENDPOINT  https://ca-dna-mcp-<token>.<region>.azurecontainerapps.io/mcp/
AUTH_MODE     jwt
```

> **Open dev deploy:** omit `ENTRA_TENANT_ID` and the app provisions with
> `AUTH_MODE=none` (unauthenticated). Never do this for anything reachable —
> it exposes your DNA to anyone with the URL.

---

## Step 3 — Seed your DNA source

A fresh provision serves the tiny demo scope **baked into the image**
(`hosted-demo`, one agent) so the endpoint is queryable immediately. To serve
**your** DNA, push a local `.dna` tree onto the mounted share and restart the
revision:

```console
$ ./scripts/push-scope.sh ../../.dna        # or any path to a .dna directory
```

The runtime only ever **reads** `/mnt/dna`; publishing is always this
out-of-band push (upload + revision restart). For a database-backed source
instead of the file share, set `azd env set DNA_SOURCE_URL postgresql://…` and
redeploy — `DNA_SOURCE_URL` takes precedence over the mounted `DNA_BASE_DIR`.

---

## Step 4 — Post-deploy smoke test

**a) The server is up (unauthenticated probe).** With auth on, an unauthenticated
call is correctly **rejected**, and the RFC 9728 discovery doc is served:

```console
# Protected Resource Metadata — tells a client WHERE to authorize (expect 200):
$ curl -s https://<your-app>/.well-known/oauth-protected-resource/mcp | jq .

# An unauthenticated tool call is denied (expect 401 with a WWW-Authenticate challenge):
$ curl -i -X POST https://<your-app>/mcp/ \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
```

**b) A real client connects with an Entra token.** Point a remote MCP client at
the endpoint; it drives the OAuth flow off the PRM document, gets an Entra token,
and calls the tools. To test by hand, mint a token for the exposed scope and call
`initialize` then `compose_prompt`:

```console
$ TOKEN=$(az account get-access-token \
    --scope api://<your-mcp-app-client-id>/.default \
    --query accessToken -o tsv)

$ curl -s -X POST https://<your-app>/mcp/ \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
# → 200, a server-sent `initialize` result naming server "dna".
```

A `compose_prompt` call then returns a **live-composed** prompt, scoped to the
token's tenant — the whole point of the hosted server.

---

## Owner checklist — the real `azd up`

Everything above the smoke test is validated locally in CI-friendly ways
(`az bicep build`, the from-source install, `dna mcp serve` booting + enforcing
auth). The steps that require **your** Azure subscription + Entra tenant are
yours to run:

- [ ] `az login` / `azd auth login` to the target subscription.
- [ ] Create the Entra **app registration**, expose an API scope, note tenant id + audience (Step 1).
- [ ] `azd env set ENTRA_TENANT_ID …` / `ENTRA_MCP_AUDIENCE …` (Step 2).
- [ ] `azd up` — provision + build + deploy.
- [ ] `./scripts/push-scope.sh <your .dna>` — seed your real source (Step 3).
- [ ] Run the post-deploy smoke (Step 4) — PRM 200, unauth 401, authed `initialize` 200.
- [ ] Register the endpoint URL in your MCP client(s).
- [ ] `azd down` when you are finished, to deprovision.

---

## Files in this recipe

| File | Role |
|---|---|
| `Dockerfile` | containerizes `dna mcp serve --transport http` (python:3.12-slim, non-root, port 8080) |
| `entrypoint.sh` | turns the container env into the `dna mcp serve` invocation |
| `azure.yaml` | the `azd` project (service `mcp` → Dockerfile, `infra` → this dir) |
| `main.bicep` / `main.parameters.json` | subscription-scoped entry: resource group + module |
| `resources.bicep` | the stack: Log Analytics + ACA env + ACR + Managed Identity + Files share + Container App |
| `dna-scope/` | the demo scope baked into the image (queryable before you seed your own) |
| `dna.config.sample.yaml` | reference for the forthcoming declarative `auth.providers: [entra]` config |
| `scripts/push-scope.sh` | seed / update the mounted DNA source, then restart the revision |

## How the auth is wired (env, today)

The Container App runs `--auth jwt`, configured from the environment the bicep
sets from your Entra values (`resources.bicep`):

| Env var | Value on the app |
|---|---|
| `DNA_MCP_JWKS_URI` | `https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys` (derived) |
| `DNA_MCP_JWT_ISSUER` | `https://login.microsoftonline.com/<tenant>/v2.0` (derived) |
| `DNA_MCP_JWT_AUDIENCE` | your `api://<client-id>` |
| `DNA_MCP_RESOURCE_URL` | the app's own HTTPS URL (advertised in PRM) |
| `DNA_MCP_AUTH_SERVERS` | the Entra authority (advertised in PRM) |
| `DNA_MCP_TENANT_CLAIM` | the claim mapped to a DNA tenant (`tenant` / `tid`) |

The login host is derived via Bicep's `environment()` function, so the template
stays correct across Azure clouds (Public / Gov / China). A **declarative**
front-end for the same wiring (`dna.config.yaml` with `auth.providers: [entra]`)
is documented in `dna.config.sample.yaml`.

See the guide [Hosting the MCP server on Azure](../../docs/guides/hosting-mcp-aca.md)
and [The MCP server — DNA as a live layer](../../docs/guides/mcp-server.md) for
the full picture, including the auth↔tenancy bridge.
