# Microsoft On-Behalf-Of — the DNA MCP server acts on your M365

The [MCP server](mcp-server.md) already validates the inbound Entra bearer token
and maps it to a DNA tenant/workspace. **On-Behalf-Of (OBO)** is the next hop: the
same verified token is a *delegated user token*, and a confidential middle tier can
exchange it at Microsoft Entra for a **downstream Microsoft Graph token** minted
for the same user. That lets DNA MCP tools read the signed-in user's **Microsoft
365** — starting with their **calendar** — on their behalf, with **no new
sign-in**.

The full design (and why this is spec-aligned, not the forbidden token-passthrough
pattern) is [ADR-mcp-obo](https://github.com/ruinosus/dna/blob/main/docs/adr/ADR-mcp-obo.md).
This guide is the operator recipe:
enable it, wire the Entra app, and call `ms_calendar_list`.

> **Off by default, opt-in, HTTP-only.** With no `graph:` block in
> `dna.config.yaml` not one `ms_*` tool is registered — the OSS / stdio /
> self-host path never touches Microsoft. OBO needs a bearer token to exchange, so
> it is only available over `--transport http`.

## The shape

```text
MCP client ──token A (aud = api://dna-mcp-dnacloud)──▶ DNA MCP server
                                                        │  (confidential client)
                                                        │  OBO exchange at the
                                                        │  token's HOME tenant
                                                        ▼
                                              Microsoft Entra ── token B (aud = graph)
                                                        │
                                              ms_calendar_list ──Bearer token B──▶ Microsoft Graph
                                                        │            GET /me/calendarView
                                              shaped events ◀────────┘   (token B never persisted)
```

Token B lives only for the request: it is used on the one outbound Graph call and
dropped. It is **never** logged, persisted, cached, or returned to the client.

## 1. Enable it — the `graph:` config block

Add a `graph:` section to `dna.config.yaml` (sibling to `auth:`). It is the
**ceiling**: which tool-groups are on and the exact delegated scopes each may
request. The confidential-client credential is referenced by the **NAME** of the
env var that holds it — never the secret value itself.

```yaml
# dna.config.yaml
source: postgresql://…                    # your source (unchanged)
auth:                                     # the inbound IdP layer (unchanged)
  providers:
    - type: entra
      issuer: https://login.microsoftonline.com/common/v2.0
      audience: api://dna-mcp-dnacloud

graph:                                    # ← absent ⇒ OBO entirely off (default)
  enabled: true
  client_id_env:  DNA_MCP_CLIENT_ID       # env var holding the app-reg id
  credential_env: DNA_MCP_CLIENT_SECRET   # env var holding the client secret
  groups:
    calendar:
      enabled: true
      scopes: [ "Calendars.Read" ]        # read-only, the first group
```

Fail-closed guarantees the parser enforces:

- **`enabled` defaults to `false`.** A present block with `enabled: false` (or a
  disabled group) registers nothing.
- **The scope allow-list is static.** A tool can only ever request a scope its
  group declared; anything else is refused *before* any exchange
  (`OboScopeNotAllowedError`).
- **`*_env` fields must be env-var NAMES.** A value that looks like an inline
  secret (contains `~ . / = @` …) is rejected — a guard against pasting a secret
  into config.

Then run the server with the credentials in the environment:

```bash
export DNA_MCP_CLIENT_ID=ff09090f-79e3-4dfe-975c-1a8e007112b7
export DNA_MCP_CLIENT_SECRET='<the client secret>'      # from Entra (see §3)
dna mcp serve --transport http --auth config
# boot log: "graph (OBO): active groups — calendar"
#           "[dna-mcp] graph tool wired: ms_calendar_list"
```

## 2. Call it — `ms_calendar_list`

Once enabled and the caller signs in with an **Entra** identity, the tool appears
on the MCP surface:

```jsonc
// list_tools → includes:
{ "name": "ms_calendar_list",
  "description": "List the signed-in user's Microsoft 365 calendar events …" }

// call_tool ms_calendar_list
{ "start": "2026-07-15T00:00:00Z",   // optional; default = today 00:00 UTC
  "end":   "2026-07-22T00:00:00Z",   // optional; default = start + 7 days
  "top":   25 }                       // optional; 1–100, default 25

// → shaped result (never a token, never the raw Graph body)
{ "count": 2,
  "events": [
    { "id": "…", "subject": "Standup", "start": "2026-07-15T09:00:00",
      "end": "2026-07-15T09:15:00", "location": "Room 1", "organizer": "Alex",
      "web_link": "https://outlook.office365.com/…" }
  ] }
```

The tool's `description` + `input_schema` are a **governed Tool document**
(`ms_calendar_list.yaml`), so what the model sees is data — overlayable like any
[Tool](tools-as-data.md), not hardcoded.

### Honest failure modes

| Situation | What the caller gets |
|---|---|
| Non-Entra sign-in (Clerk/WorkOS/OIDC) or stdio | *"Microsoft Graph is not available for this identity"* — a capability gap, not a crash |
| Consent not granted (`AADSTS65001`) | *"Graph access for scope(s) … has not been consented — an admin or the user must grant it"* |
| Conditional Access / MFA step-up | The **claims challenge** is surfaced (not swallowed) so the client can step up |
| A scope outside the allow-list | Refused before any exchange (`OboScopeNotAllowedError`) |
| Bad credential / Graph 5xx | A sanitized error (an `AADSTS`/HTTP code at most) — never the raw body |

## 3. Entra setup — the one-time admin steps (Barna)

OBO needs the existing **`dna-mcp-dnacloud`** app-registration
(appId `ff09090f-79e3-4dfe-975c-1a8e007112b7`) to become a **confidential client**
with a **delegated Graph permission** and **consent**. Only an Entra admin can do
this. The code above works the moment these are done, and fails honestly until
then.

```bash
APP_ID=ff09090f-79e3-4dfe-975c-1a8e007112b7

# (a) Add a CLIENT SECRET → makes the app a confidential client (PoC credential;
#     certificate / ACA managed-identity federated credential is prod-hardening).
az ad app credential reset --id "$APP_ID" \
  --display-name "dna-obo-poc" --years 1 --query password -o tsv
#   ^ copy the printed secret into DNA_MCP_CLIENT_SECRET (store in a Key Vault in prod).

# (b) Add the DELEGATED Microsoft Graph permission Calendars.Read.
#     Graph resource appId = 00000003-0000-0000-c000-000000000000
#     Calendars.Read delegated scope id = 465a38f9-76ea-45b9-9f34-9e8b0d4b0b42  (Scope)
az ad app permission add --id "$APP_ID" \
  --api 00000003-0000-0000-c000-000000000000 \
  --api-permissions 465a38f9-76ea-45b9-9f34-9e8b0d4b0b42=Scope

# (c) CONSENT. Either admin-consent the tenant-wide grant …
az ad app permission admin-consent --id "$APP_ID"

#     … or send end users through the per-user incremental consent URL
#     (per-tool-group — only Calendars.Read is requested):
#   https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize
#     ?client_id=ff09090f-79e3-4dfe-975c-1a8e007112b7
#     &response_type=code
#     &redirect_uri=<your redirect>
#     &scope=https://graph.microsoft.com/Calendars.Read%20offline_access
#     &prompt=consent
```

Optional but recommended for a one-prompt combined consent (client→MCP and
MCP→Graph in a single sign-in): add the MCP client's appId to the DNA MCP
app-registration's **`knownClientApplications`** (ADR §4.3).

### Verify the live path (Barna's smoke — not CI)

The unit tests fake the exchange (no live Entra, no secret). To smoke the **real**
chain once the steps above are done:

1. `export DNA_MCP_CLIENT_ID=… DNA_MCP_CLIENT_SECRET=…`
2. Boot `dna mcp serve --transport http --auth config` with the `graph:` block on.
3. From an MCP client signed in as an Entra user in the consented tenant, call
   `ms_calendar_list` — you should get that user's real events back.
4. If you see the consent error, step (c) has not propagated yet (or the user
   hasn't consented); if you see the capability-gap error, the caller is not an
   Entra identity.

## Deferred (follow-on stories)

Not in this first slice, tracked as `s-mcp-obo-read-groups` +
`s-mcp-obo-prod-hardening`: the `files` / `mail` read groups, write tools
(`ms_mail_send`), a bounded in-memory token cache, the **certificate / ACA
managed-identity** credential (this slice uses a plain secret), the step-up
consent round-trip surfaced through to the client, and guest (B2B) / personal
(MSA) identity support.
