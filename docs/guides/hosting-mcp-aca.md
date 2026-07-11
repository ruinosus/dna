# How to host the MCP server on Azure Container Apps

The [MCP server](mcp-server.md) has a local face (stdio) and a **remote** face
(Streamable HTTP + OAuth). This guide is the recipe for the remote face: running
`dna mcp serve --transport http` **hosted** on **Azure Container Apps**, behind an
HTTPS ingress, authenticated with **Microsoft Entra** — so a web/agent MCP client
reaches your live DNA over the network, composed live and scoped to the caller's
tenant by the token.

It is **Phase A of DNA-hosted**: one `azd up` stands up your own instance, and the
same recipe is the base the multi-tenant *DNA Cloud* offering builds on. The full,
runnable recipe (Dockerfile + bicep + runbook) lives in
[`deploy/azure/`](https://github.com/ruinosus/dna/tree/main/deploy/azure); this
page is the map.

## The shape

Everything is **keyless**. The image pull uses a user-assigned **Managed
Identity**; Entra tokens are validated against Entra's **public JWKS**. No secret
lives in the template or the container.

| Piece | What it is |
|---|---|
| `Dockerfile` | `dna mcp serve --transport http` on `python:3.12-slim`, non-root, port **8080** |
| `resources.bicep` | Log Analytics + Container Apps env + ACR + **user-assigned Managed Identity** (AcrPull) + Azure Files share (the DNA source, mounted read-only at `/mnt/dna`) + the **Container App** (external HTTPS ingress, Entra-JWT auth env) |
| `azure.yaml` | the `azd` project — one service `mcp`, `remoteBuild: true` (no local Docker needed) |
| `scripts/push-scope.sh` | seed / update the mounted DNA source, then restart the revision |

## Auth — Microsoft Entra as the IdP

The Container App is an OAuth 2.1 **Resource Server**. You register the MCP server
as an **Entra app registration**, *Expose an API* with a scope, and the app
validates presented bearer JWTs against Entra's JWKS. The
[auth↔tenancy bridge](mcp-server.md#the-tenancy-bridge-a-token-composes-only-what-is-its-tenants)
then maps the token's claim to a **DNA tenant** and enforces it.

The bicep derives the Entra endpoints from your tenant id (nothing to hand-copy)
and wires them as the `--auth jwt` environment:

```text
DNA_MCP_JWKS_URI      https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys
DNA_MCP_JWT_ISSUER    https://login.microsoftonline.com/<tenant>/v2.0
DNA_MCP_JWT_AUDIENCE  api://<mcp-app-client-id>
DNA_MCP_RESOURCE_URL  https://<the-app>            # advertised in PRM (RFC 9728)
DNA_MCP_AUTH_SERVERS  https://login.microsoftonline.com/<tenant>/v2.0
DNA_MCP_TENANT_CLAIM  tenant                       # or `tid` to bind each Entra directory to a DNA tenant
```

The login host is derived via Bicep's `environment()`, so the template is correct
across Azure clouds (Public / Gov / China). A **declarative** front-end for the
same wiring (`dna.config.yaml` with `auth.providers: [entra]`) is sketched in
`deploy/azure/dna.config.sample.yaml`.

## Deploy it

```console
$ cd deploy/azure
$ azd env set ENTRA_TENANT_ID   <your-entra-tenant-guid>
$ azd env set ENTRA_MCP_AUDIENCE api://<your-mcp-app-client-id>
$ azd up
```

`azd up` provisions the stack, builds the image in ACR, and deploys it. Its
outputs give you `MCP_ENDPOINT` (`https://…/mcp/`) and `AUTH_MODE`.

Then seed your real DNA source (a fresh provision serves a tiny baked demo scope
so the endpoint is queryable immediately):

```console
$ ./scripts/push-scope.sh ../../.dna
```

## Prove it

```console
# Discovery doc served (expect 200):
$ curl -s https://<the-app>/.well-known/oauth-protected-resource/mcp | jq .

# Unauthenticated call denied (expect 401):
$ curl -i -X POST https://<the-app>/mcp/ -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"s","version":"0"}}}'

# With an Entra token (expect 200, server "dna"):
$ TOKEN=$(az account get-access-token --scope api://<client-id>/.default --query accessToken -o tsv)
$ curl -s -X POST https://<the-app>/mcp/ -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"s","version":"0"}}}'
```

The step-by-step runbook — the Entra app registration, the owner checklist, and
`azd down` — is [`deploy/azure/README.md`](https://github.com/ruinosus/dna/tree/main/deploy/azure/README.md).

## Why this matters

`dna emit` materializes DNA into a runtime's static artifact; the MCP server is
the *live* face. Hosting it on Container Apps + Entra makes that live face
**reachable, authenticated, and multi-tenant** — the same server the CLI serves
over stdio, now a networked endpoint that scopes each client to its own tenant by
the token. That is the base the DNA Cloud offering is built on.
