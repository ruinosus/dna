# ADR: Microsoft On-Behalf-Of (OBO) for the DNA MCP server

- **Status**: Accepted (2026-07-15 — Barna approved; §8 ratified to the recommended options)
- **Date**: 2026-07-15
- **Deciders**: Barna (owner/architect)
- **Author**: claude-code
- **Tracking**: `f-mcp-obo` (board `dna-development`, under epic `e-dna-portability`)
- **Relates to**: `f-dna-hosting` (the MCP server on ACA + Entra), `f-dna-mcp-server`,
  `f-dna-tools-as-data`, `MCPFederation` Kind (DNA-consumes-MCP, the inverse)

> **DESIGN ONLY.** This ADR proposes the shape. No app-registration change, no
> `az` change, no code, no deploy has been made. Barna reviews before any build.

---

## 1. Context — the opportunity

Today the DNA MCP server is a **pure OAuth 2.1 Resource Server**. Concretely
(`packages/cli/dna_cli/_mcp_auth.py` + `_mcp_server.py`):

- `dna mcp serve --transport http --auth jwt|config` builds a FastMCP
  `JWTVerifier` (single-env or the pluggable N-provider layer) that **validates**
  the inbound Entra bearer token — signature via JWKS, `aud = api://dna-mcp-dnacloud`,
  and for the Entra multi-tenant endpoints (`common`/`organizations`) audience-only
  since `iss` carries the caller's real tenant GUID.
- The auth↔tenancy bridge maps the token's `tid` claim → a **DNA tenant** and
  scopes every tool (`compose_prompt` / `recall` / `list_stories` / …) to that
  tenant. A cross-tenant or tenant-less authenticated request is denied.

DNA **validates and maps** the token. It does **not exchange** it. Every tool
today reads or composes *DNA's own* data (definitions, SDLC board, memory) —
nothing outside DNA is touched.

**The opportunity (owner's framing):** the same verified inbound token is a
delegated *user* token in the caller's Entra tenant. A confidential middle-tier
service can present it to Microsoft Entra and receive a **downstream Microsoft
Graph token** minted *for the same user*. That would let DNA MCP tools read and
act on the signed-in user's **Microsoft 365** — calendar, mail, OneDrive/SharePoint
files, Teams — **on their behalf**, with zero new sign-in. DNA becomes not only
"the live, vendor-neutral intelligence layer" but *"the layer that also orchestrates
your Microsoft data on your behalf."*

This is the **OAuth 2.0 On-Behalf-Of (OBO)** flow. It builds directly **on top of**
what `_mcp_auth.py` already does — we already hold a *verified* inbound token whose
audience is us; OBO is the next hop.

---

## 2. OBO spec facts (so the design targets the real protocol)

Sources, fetched 2026-07-15:
- Microsoft Entra — *OAuth 2.0 On-Behalf-Of flow*
  (`learn.microsoft.com/entra/identity-platform/v2-oauth2-on-behalf-of-flow`)
- MCP spec — *Authorization* (draft)
  (`modelcontextprotocol.io/specification/draft/basic/authorization`)

### 2.1 The exchange (Entra)

The middle-tier (DNA MCP) POSTs to the **tenant-specific** token endpoint:

```
POST https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

grant_type            = urn:ietf:params:oauth:grant-type:jwt-bearer
client_id             = <dna-mcp app-registration id>
client_secret         = <secret>            # OR the certificate pair below
assertion             = <the inbound user token>   # aud MUST == dna-mcp app
scope                 = https://graph.microsoft.com/Calendars.Read offline_access
requested_token_use   = on_behalf_of
```

Certificate variant (recommended for prod) replaces `client_secret` with:

```
client_assertion_type = urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion      = <JWT signed with the app's registered cert private key>
```

**Success** → JSON with `access_token` (audience = `graph.microsoft.com`, the
*downstream* token), `expires_in`, and `refresh_token` **iff** `offline_access`
was requested.

### 2.2 Hard constraints the spec imposes

1. **OBO is delegated-only.** It works **only for user principals**. An app-only
   token (client-credentials) cannot be exchanged via OBO — "*Roles remain attached
   to the principal (the user) and never to the application.*" DNA MCP tokens are
   user tokens (interactive sign-in), so this fits.
2. **The `assertion` `aud` MUST be the middle-tier app.** "*Applications can't redeem
   a token for a different app.*" Our inbound token's `aud` is
   `api://dna-mcp-dnacloud` — exactly the app that will do the exchange. ✅ This is
   the precondition already satisfied by `_mcp_auth.py`.
3. **The middle-tier MUST be a confidential client** — it needs a **client secret
   or certificate**. The DNA MCP app-registration is today an essentially public-ish
   *resource* app; OBO requires adding a credential to it (see §4).
4. **No custom token-signing keys** on the middle-tier app (would break downstream
   signature validation). Standard app-reg, not an SSO enterprise app with a custom
   signing key.
5. **Consent must exist** for the middle-tier→Graph delegated permission. Three
   paths: **combined consent** (`knownClientApplications` + `.default`),
   **preauthorized applications**, or **admin consent**. Incremental (per-scope)
   consent is supported — request only what a tool-group needs.
6. **Conditional Access surfaces mid-exchange.** If the downstream resource has a CA
   policy (MFA, device), the exchange returns `interaction_required` with a *claims
   challenge*. The middle-tier must surface this to the client (401 +
   `WWW-Authenticate`), not swallow it.

### 2.3 The MCP spec's stance — OBO is the *correct*, not the forbidden, pattern

The MCP authorization spec is blunt about downstream tokens:

> "MCP servers **MUST** validate that access tokens were issued specifically for
> them as the intended audience … MCP servers **MUST NOT** accept or transit any
> other tokens."

At first read this looks like it *forbids* touching downstream APIs. It does the
opposite for OBO. The "no token passthrough" rule forbids **relaying** the inbound
token to a third party (the classic *confused-deputy* footgun). **OBO does not
relay the token.** The inbound token never leaves DNA as a bearer credential — it
is used **only** as the `assertion` in a server-to-server call to *DNA's own IdP*,
which mints a **brand-new** token with `aud = graph`. The Graph token is minted for
the user, scoped to exactly the delegated permissions DNA was consented, and DNA is
the confidential client that requested it. That is precisely the audience-bound,
confused-deputy-safe pattern the spec is steering implementers toward. **OBO is
spec-aligned; token passthrough is what's banned.** This distinction is the single
most important sentence in this ADR.

---

## 3. The OBO chain (drawn explicitly)

```
┌─────────────┐   (1) MCP call + Bearer token A            ┌──────────────────────┐
│  MCP client │ ─────────────────────────────────────────▶ │  DNA MCP server      │
│ (Claude web,│      aud(A) = api://dna-mcp-dnacloud        │  (confidential       │
│  Cursor, …) │                                             │   client: secret/cert)│
└─────────────┘                                             └──────────┬───────────┘
       ▲                                                               │
       │                                          (2) OBO token exchange│  POST /<tid>/oauth2/v2.0/token
       │                                                               │  grant_type=jwt-bearer
       │                                                               │  assertion = token A
       │                                                               │  requested_token_use = on_behalf_of
       │                                                               │  scope = graph/Calendars.Read
       │                                                               ▼
       │                                                    ┌──────────────────────┐
       │       (5) tool result                              │  Microsoft Entra ID  │
       │◀──────────────────────────────────────┐           │  token endpoint      │
       │                                        │           │  (user's home tenant)│
       │                              ┌─────────┴────────┐  └──────────┬───────────┘
       │                              │  DNA graph.* tool│             │ (3) token B
       │                              │  (built-in)      │             │   aud(B) = graph
       │                              └─────────┬────────┘             ▼   (per-request, never persisted)
       │                                        │  (4) GET /me/events  ┌──────────────────────┐
       └────────────────────────────────────────┼─────────────────────▶│  Microsoft Graph     │
                                                 │   Authorization:     │  acts AS the user    │
                                                 │   Bearer token B     └──────────────────────┘
```

1. Client calls a DNA MCP tool with **token A** (`aud = api://dna-mcp-dnacloud`).
   `_mcp_auth.py` validates it and maps `tid` → DNA tenant (already shipped).
2. For a `graph.*` tool, DNA (as a **confidential client** with a secret/cert)
   exchanges token A at the user's **home-tenant** token endpoint
   (`<tid>` from token A) with `requested_token_use=on_behalf_of` and the
   downstream Graph scope.
3. Entra returns **token B** (`aud = graph`), minted for the same user, scoped to
   exactly the consented delegated permission.
4. The tool calls Microsoft Graph with `Authorization: Bearer <token B>`.
5. Result flows back to the client. **Token B lives only for the request** and is
   never logged, never persisted, never returned to the client.

---

## 4. Security model

OBO turns DNA into a holder of *other people's* Microsoft credentials for the span
of a request. The security posture must be conservative.

### 4.1 Token handling
- **Per-request exchange, request-lifetime only.** Token B is acquired inside the
  tool call and dropped when it returns. **Never** persisted to the DNA source, a
  cache, a log line, or the tool's JSON result. (Follows the Entra warning: *"DO
  NOT send access tokens issued to the middle tier anywhere except the intended
  audience."*)
- **No token B in tool output.** Tools return domain data (events, files), never
  the raw token or the raw Graph error body verbatim (which can echo tokens).
- **Structured audit without secrets.** Log *that* an OBO exchange happened
  (tenant, tool, scope, success/failure, correlation id) — never the assertion or
  either token.
- **PoC uses no refresh token / no token cache.** A short-lived per-request token
  is simplest and safest. A bounded in-memory MSAL cache (keyed by user oid +
  scope, TTL ≤ token life) is a *deferred* optimization, explicitly out of the PoC
  (§6) — persistence of refresh tokens is a separate, higher-bar decision.

### 4.2 Scope minimization (least privilege)
- **Enabled tools drive requested scopes — nothing more.** The OBO `scope` for a
  given exchange is exactly the delegated permission that tool-group needs
  (`Calendars.Read` for calendar-read; not `.default`, not a broad grant).
- **Config declares the ceiling.** `dna.config.yaml`'s `graph:` block (see §5) lists
  which tool-groups a deployment opts into and their scopes. A tool cannot request a
  scope the config didn't enable — a static allow-list, fail-closed.
- **Read before write.** The PoC and first tool-group are **read-only**
  (`Calendars.Read`, `Files.Read`). Write scopes (`Mail.Send`, `Calendars.ReadWrite`)
  are a later, separately-consented group.

### 4.3 Consent model — incremental, per tool-group
- **Not one big `.default`.** Each tool-group carries its own delegated scope. A
  deployment enabling only calendar-read consents to `Calendars.Read` only. Enabling
  mail-send later triggers an *incremental* consent for `Mail.Send`.
- **Combined consent at first sign-in** via `knownClientApplications` on the DNA MCP
  app-reg gets client→MCP and MCP→Graph consent in one prompt for the enabled
  groups.
- **Admin consent** is the enterprise path: a tenant admin pre-consents the enabled
  Graph scopes for the DNA MCP app in their tenant, so end users never see a prompt.

### 4.4 Multi-tenant interaction — *whose* Graph does OBO hit?
The exchange targets `https://login.microsoftonline.com/<tid>/oauth2/v2.0/token`,
where `<tid>` is **the inbound token's home tenant**. So OBO always hits **the
Graph of the tenant that issued the token** — the same `tid` DNA already maps to a
DNA tenant. Clean alignment: the DNA-tenant boundary and the Graph boundary are the
*same* boundary for a member user. Cases:

| Inbound identity | `tid` | OBO target | Graph reached |
|---|---|---|---|
| **partner-org member** (Entra) | partner tenant GUID | partner tenant endpoint | that org's M365 (their calendar/files) ✅ |
| **Google/Clerk sign-in** (non-Entra) | — no Entra token | **N/A** | **OBO not available** — honest capability gap ⚠️ |
| **Personal Microsoft acct** (`@outlook`, MSA) | `consumers`/`9188…` | consumers endpoint | Personal Outlook/OneDrive (app must enable personal accounts) |
| **Guest (B2B)** in tenant A, home tenant B | A (resource tenant that issued the token) | tenant A endpoint | The **guest** identity's access *in tenant A* — limited/varies ⚠️ |

Design consequences:
- **OBO only lights up for Entra-issued inbound tokens.** DNA's pluggable IdP layer
  also accepts Clerk/WorkOS/OIDC tokens (`_mcp_auth.parse_auth_providers`). A tool
  invoked under a **non-Entra** token has no Entra assertion to exchange → the tool
  returns an honest "Microsoft Graph is not available for this identity" error, not
  a crash. The provider that verified the token is known (the composite stamps it),
  so this is a clean branch.
- **v1 targets member (own-identity) users.** Guest (B2B) and MSA/consumer are
  documented edges with degraded/variable behavior; not PoC targets.

### 4.5 Failure modes (all → an honest tool error, never a masked 500)
- **No credential on the app-reg / OBO disabled** → tool disabled, surfaced at
  `list_tools` (the group simply isn't registered).
- **Consent not granted** (`AADSTS65001` / `invalid_grant`) → tool returns
  *"Microsoft Graph access has not been consented for <scope> — an admin or the user
  must grant it,"* mirroring `CrossTenantError → ToolError` today.
- **Conditional Access / MFA** (`interaction_required` + claims challenge) → the
  challenge is surfaced back to the client per §2.2(6) so the user can step up; it
  is **not** swallowed.
- **Non-Entra identity** → capability-gap error (§4.4).
- **Graph 4xx/5xx** → mapped to a clean tool error with the Graph `code`/`message`
  (sanitized), never the raw body.

---

## 5. How it fits DNA's declarative "everything is data" model

This is the central design question. The honest reading of the codebase:

- **The tool *surface* is already data.** DNA has a `Tool` record-plane Kind
  (`packages/sdk-py/dna/tools.py`, `kinds/tool.kind.yaml`) — `description` +
  `input_schema` as an overlayable document. That is *what the model reads*, served
  identically to Py and TS.
- **The tool *execution* is code.** Every MCP tool today (`compose_prompt`,
  `recall`, …) is a built-in `@server.tool` Python function in `_mcp_server.py` — a
  thin adapter over a tested core. There is **no** declarative "execute this HTTP
  call as the user" engine, and inventing one for arbitrary Graph calls would be
  both over-engineering (YAGNI) and a **security footgun** (declarative arbitrary
  authenticated HTTP is an SSRF/scope-escape surface).
- **External-integration *config* is already data.** The `MCPFederation` Kind
  (`extensions/federation`) is the precedent: DNA describes an external MCP server
  declaratively, secrets are **env-var *names* only**, and the *connection lifecycle
  lives in code* ("*the Kind only declares configuration; lifecycle lives in the
  harness so the SDK core stays runtime-free*"). Graph-via-OBO is the same shape.

**Recommendation — a hybrid that matches the ethos where it actually belongs:**

| Layer | Declarative (data) or code? | Where |
|---|---|---|
| **Which groups/scopes a deployment enables** | **Config (data)** | `dna.config.yaml` → `graph:` block |
| **Each tool's description + input schema** | **Data** (`Tool` Kind, overlayable) | source docs, governed like every tool |
| **The OBO exchange + Graph call** | **Code** (built-in tool-group) | `_mcp_server.py` + a `graph` adapter |
| **Credential (secret/cert)** | **Env-var name only** (never in a doc) | mirrors `MCPFederation.auth` |

So: **built-in execution, data surface, config enablement.** The `graph.*` tools
are a built-in tool-group registered exactly like the existing ones; *whether*
they're on and *which* scopes they may request is declarative config; *what the
model sees* is a governed, overlayable Tool doc. Proposed config:

```yaml
# dna.config.yaml
graph:                      # absent → OBO entirely off (default; OSS/stdio untouched)
  enabled: true
  client_id_env:   DNA_MCP_CLIENT_ID       # the confidential-client app-reg id
  credential_env:  DNA_MCP_CLIENT_SECRET   # secret (PoC) — or cert thumbprint/key envs
  groups:
    calendar:
      enabled: true
      scopes: [ "Calendars.Read" ]         # read-only first group
    files:
      enabled: false
      scopes: [ "Files.Read" ]
    mail:
      enabled: false
      scopes: [ "Mail.Send" ]              # write — separate consent, deferred
```

This slots into the existing opaque `auth:`/config machinery (`dna.config.py`
already treats `auth:` as a validated passthrough; `graph:` is a sibling). Like
`--auth`, it is **HTTP-only** and **off by default** — the stdio/OSS/self-host path
never touches Microsoft.

---

## 6. First tools (concrete, with exact Graph endpoints + scopes)

Minimal, mostly read-only, one per M365 pillar to prove the pattern:

| Tool | Graph endpoint | Delegated scope | R/W | PoC? |
|---|---|---|---|---|
| `ms_calendar_list` | `GET /me/calendarView?startDateTime=…&endDateTime=…` (or `/me/events`) | `Calendars.Read` | read | **PoC ✅** |
| `ms_files_search` | `GET /me/drive/root/search(q='{q}')` | `Files.Read` | read | v1, post-PoC |
| `ms_mail_list` | `GET /me/messages?$search="…"` | `Mail.Read` | read | v1, post-PoC |
| `ms_mail_send` | `POST /me/sendMail` | `Mail.Send` | **write** | deferred (separate consent) |
| `ms_profile_get` | `GET /me` | `User.Read` | read | trivial smoke helper |

Each is a thin `@server.tool` adapter: `_guard()` (existing tenancy/quota seam) →
resolve inbound token → OBO exchange for the group's scope → Graph call → shaped
result. Naming `ms_*` (not `graph_*`) reads better to the model and namespaces the
group.

---

## 7. PoC scope (smallest real slice) + deferred

**PoC — prove the chain end-to-end with one read-only tool:**
1. **OBO exchanger** (`graph/_obo.py`): a per-request confidential-client exchange
   via **MSAL Python** (`ConfidentialClientApplication.acquire_token_on_behalf_of`)
   — the library Microsoft recommends over hand-rolling the POST. Reads app-reg id +
   secret from the env names in config. No cache, no persistence.
2. **One tool** `ms_calendar_list`, behind `graph.enabled` + `graph.groups.calendar`,
   requesting only `Calendars.Read`.
3. **Honest gating**: tool registered only when config enables it *and* the inbound
   identity is Entra; non-Entra / disabled → capability-gap error or absent from
   `list_tools`.
4. **Tests** mirroring `test_mcp_auth.py`: a fake OBO exchanger (no live Entra) +
   the gating/branching logic; one integration smoke behind an env flag against a
   real dev app-reg (manual, not CI).

**Deferred (explicitly NOT in the PoC):**
- Write tools (`ms_mail_send`), files/mail/Teams groups.
- Token/refresh caching (bounded in-memory MSAL cache).
- Certificate credential + ACA **managed-identity federated credential** (PoC uses
  a plain secret; prod hardening is its own story).
- Incremental / step-up consent UX and the CA claims-challenge round-trip surfaced
  through to the MCP client.
- Guest (B2B) and MSA/consumer identity support.
- TypeScript parity of any Graph client (execution is Python-side; the *surface*
  Tool docs are already Py↔TS by construction).

---

## 8. Decisions (ratified by Barna, 2026-07-15)

Barna approved the ADR and the recommended option on every point:
1. **Hybrid tool execution** — built-in Python + Tool-Kind data surface + config enablement. NOT a declarative execute-HTTP engine.
2. **First group: calendar-read** (`ms_calendar_list`, `Calendars.Read`).
3. **Secret for the PoC; certificate / ACA managed-identity for prod** (prod hardening is a fast-follow, not v1-blocking).
4. **Per-tool-group incremental consent** (not `.default`).
5. **Reuse the `dna-mcp-dnacloud` app-reg** (add credential + delegated Graph perms + `knownClientApplications`).

### (original recommendations, for the record)

1. **Built-in vs declarative tool execution.** This ADR **recommends the hybrid**:
   built-in Python execution + data surface (Tool Kind) + config enablement — *not*
   a declarative "execute-HTTP-as-user" engine (YAGNI + security footgun). Confirm
   this is the line, or push for more declarativeness.
2. **Which first tool-group.** Recommend **calendar-read** (`ms_calendar_list`,
   `Calendars.Read`) — highest signal, read-only, single scope. Alternative: `files`
   (search) if OneDrive/SharePoint is the more compelling demo.
3. **Secret vs certificate for the confidential client.** Recommend **secret for the
   PoC**, **certificate (or ACA managed-identity federated credential) for prod** —
   avoids a long-lived shared secret in the hosted deployment. Decide whether prod
   hardening is in-scope for v1 or a fast-follow.
4. **Consent granularity.** Recommend **per-tool-group incremental consent** (not one
   `.default`). Confirm, and decide the default enterprise story (admin-consent the
   enabled groups vs per-user prompt).
5. *(Minor)* **App-registration topology.** Reuse the existing `dna-mcp-dnacloud`
   app-reg (add a credential + delegated Graph perms + `knownClientApplications`)
   vs a separate dedicated middle-tier app. Recommend **reuse** — the inbound `aud`
   already equals this app, which is an OBO precondition.

---

## 9. Rough size

- **PoC** (OBO exchanger + `ms_calendar_list` + gating + unit tests): **~1 focused
  Story**, ~2–3 days incl. a live dev app-reg smoke. Small blast radius — new,
  additive, off-by-default; no change to the existing auth/tenancy path.
- **v1** (read groups: calendar/files/mail + config surface + Tool docs + docs):
  **~3–4 Stories.**
- **Prod hardening** (certificate/managed-identity cred, token cache, CA
  claims-challenge passthrough, incremental-consent UX): **~2–3 Stories**, separable.

The dependency is **not** code size — it's the **app-registration + consent** setup
(adding a credential and delegated Graph permissions to the DNA MCP app), which only
Barna/an Entra admin can do. That gates the live smoke, not the plumbing.
