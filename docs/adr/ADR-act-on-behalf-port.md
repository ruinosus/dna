# ADR: Provider-agnostic "act on behalf of the user" port for the DNA MCP server

- **Status**: Proposed
- **Date**: 2026-07-15
- **Deciders**: Barna (owner/architect)
- **Author**: claude-code
- **Tracking**: `f-act-on-behalf-port` (board `dna-development`, under epic `e-dna-portability`)
- **Builds on**: `ADR-mcp-obo.md` (`f-mcp-obo` — the Microsoft OBO reference design)
- **Relates to**: `f-dna-hosting` (MCP on ACA + Entra), `f-dna-mcp-server`,
  `MCPFederation` Kind (DNA-consumes-MCP, the inverse), the pluggable N-provider
  IdP layer (`_mcp_auth.parse_auth_providers`)

> **DESIGN ONLY.** This ADR proposes the shape. No app-registration change, no
> `az` / `gcloud` change, no code, no deploy has been made. Barna reviews before
> any build.

---

## 1. Vision — the vendor-neutral thesis, made real

DNA's thesis is *"author once, DNA operates your digital life in any AI client."*
The intelligence layer (compose_prompt / recall / SDLC) is already vendor-neutral:
it runs identically whichever IdP verified the caller and whichever MCP client
called it. The one place that thesis is **not yet true** is the *act-on-behalf*
surface. `ADR-mcp-obo.md` proposes reading the signed-in user's calendar / files /
mail — but exclusively through **Microsoft** machinery: Entra OBO
(`grant_type=jwt-bearer`, `requested_token_use=on_behalf_of`) → Microsoft Graph.
The tools it names (`ms_calendar_list`, `ms_files_search`) are Microsoft-shaped in
their *name*, their *token mechanism*, and their *API target*.

That is fine as a first provider and wrong as an architecture. "Read my calendar"
is a **capability** that is inherently vendor-neutral; *how* you obtain a
user-scoped credential and *which* API you call is **provider** detail. A user on
Google Workspace has a calendar too — DNA should read it the same way from the
model's point of view, differing only behind a seam.

**This ADR generalizes the Microsoft OBO into a pluggable `ActOnBehalfPort`** so
the same DNA capabilities (calendar / files / mail, read-first) work against
Microsoft 365 today and Google Workspace next — each provider implementing the
"act on behalf of the user" mechanism its own way, behind one contract. The
generalization is **purely additive**: the Microsoft OBO design becomes the
reference *implementation* of the port; nothing about it changes.

This mirrors a seam DNA already got right on the **inbound** side. `_mcp_auth.py`
made *identity* provider-agnostic: a provider is "a block of config, not a code
path" (Entra / Clerk / WorkOS / Auth0 / generic-OIDC all verified through one
`ProviderConfig` shape, the DNA tenancy bridge reading claims off whatever token
comes back). This ADR is the **outbound** twin: make *acting on the user's data*
equally provider-agnostic. Inbound identity is already pluggable; outbound action
is the missing half of the vendor-neutral story.

---

## 2. The shipped/reference Microsoft OBO (what we generalize)

`ADR-mcp-obo.md` (Proposed) is the concrete first provider. Its mechanism, in one
paragraph: DNA MCP already holds a **verified inbound user token** (`aud =
api://dna-mcp-...`, validated by `_mcp_auth.py`, `tid` → DNA tenant). For an
act-on-behalf tool, DNA — as a **confidential client** (secret/cert) — POSTs that
token as the `assertion` to the user's **home-tenant** Entra token endpoint with
`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer` +
`requested_token_use=on_behalf_of` + a downstream Graph scope
(`Calendars.Read`). Entra mints a **new** token (`aud = graph`) for the same user,
DNA calls Microsoft Graph `GET /me/events` with it, returns shaped domain data.
The downstream token is **per-request, never persisted, never returned**. Critically,
this is **not** token-passthrough (the inbound token never leaves DNA as a bearer
credential) — it is the confused-deputy-safe, audience-bound pattern the MCP spec
steers implementers toward.

Everything in that ADR — the security model (per-request tokens, scope
minimization, incremental consent, honest failure modes), the "built-in execution
+ data surface + config enablement" hybrid, the read-first tool set — is the
**reference implementation** of the port this ADR defines. The port must
generalize it **without breaking a line of it**.

---

## 3. Provider realities (fetched 2026-07-15)

The whole design hinges on one fact: the "get a user-scoped credential" step is
**genuinely different** per provider, while the "call the user's API" step has a
**common shape**. The table below is the evidence.

| | **Microsoft 365** | **Google Workspace** | **AWS** |
|---|---|---|---|
| Has user productivity data? | ✅ Calendar / Mail / OneDrive-SharePoint / Teams | ✅ Calendar / Gmail / Drive-Docs-Sheets-Slides | ❌ **None** — infra only |
| "Act as user" mechanism | **OAuth 2.0 On-Behalf-Of**: exchange the inbound user token for a downstream token | **(a) OAuth 2.0 auth-code** (user consents; app holds access+refresh tokens) · **(b) Domain-Wide Delegation** (service account impersonates a domain user) | STS `AssumeRole` — assumes an **IAM role** (infra identity), never a person's mailbox/calendar |
| Grant / protocol | `grant_type=jwt-bearer` + `requested_token_use=on_behalf_of`; `assertion` = **the inbound user's token** | auth-code: standard OAuth redirect+consent → refresh token. DWD: `grant_type=jwt-bearer` where `assertion` = a **self-signed service-account JWT** carrying `sub=<user-email>` (impersonation, *not* an inbound-token exchange) | `sts:AssumeRole` (SigV4), returns temporary infra creds |
| Token endpoint | `https://login.microsoftonline.com/<tid>/oauth2/v2.0/token` | `https://oauth2.googleapis.com/token` (both auth-code refresh and DWD assertion) | `sts.amazonaws.com` |
| Trust prerequisite | Confidential client + delegated Graph perms + consent (`knownClientApplications` / admin) | auth-code: OAuth client + user consent. DWD: super-admin enables domain-wide delegation for the service account's client-id + scopes | IAM trust policy |
| Example read scopes | `Calendars.Read`, `Files.Read`, `Mail.Read` | `.../auth/calendar.readonly`, `.../auth/drive.readonly`, `.../auth/gmail.readonly` | — |
| API called as the user | Microsoft Graph (`GET /me/events`, `/me/drive/root/search`, `/me/messages`) | Google APIs (Calendar `events.list`, Drive `files.list`, Gmail `users.messages.list`) | — |

**Two conclusions drive the whole design:**

1. **The mechanisms genuinely differ — do not force one shape.** Microsoft OBO
   *exchanges an inbound user token*. Google auth-code *has no inbound token to
   exchange* — it relies on a previously-consented refresh token. Google DWD does
   use `jwt-bearer`, but the assertion is a **self-signed service-account JWT
   naming the user in `sub`**, not the caller's token. So the "acquire a
   user-scoped credential" step is **irreducibly provider-specific**. A naive
   "generalize OBO" that assumed every provider exchanges an inbound token would
   be wrong for Google. The port must abstract *the outcome* (a way to call the
   API as the user), not *the mechanism*.

2. **AWS is out of scope, by nature — not an omission.** The abstraction is about
   **user productivity data** (a person's calendar/files/mail). AWS has powerful
   delegation (`AssumeRole`/STS) but it delegates **infrastructure identity**, not
   a human's productivity suite — there is no user calendar, mailbox, or drive to
   read. AWS is therefore **N/A** for this port. (If DNA ever needs to *operate
   cloud infra* on the user's behalf, that is a **different** port — an
   `OperateInfraPort` — not this one. Keeping the two apart is the design
   discipline: this port is strictly "the user's productivity data".)

---

## 4. The port — `ActOnBehalfPort`

### 4.1 What it abstracts (and what it deliberately doesn't)

Split the flow into two steps and abstract only the first:

```
  (A) acquire a user-scoped credential      ← PROVIDER-SPECIFIC (OBO / OAuth / DWD)
  (B) call "the calendar API" as that user  ← COMMON contract, per-capability
```

The port abstracts **(A)** — "given a verified inbound identity + a requested
capability, hand me a live, user-scoped way to call the provider's API." **(B)** —
the actual calendar/files/mail call — is a **capability adapter** that consumes
whatever (A) returns. This is the key move: the mechanisms in §3 are all different
in (A) but all converge on "now I can call the user's API as them" — which is
exactly the seam.

### 4.2 The contract (Python sketch — illustrative, not code to build)

```python
@dataclass(frozen=True)
class ActContext:
    """The verified inbound request, provider-neutral. Built from the token the
    N-provider IdP layer already verified — reuses _mcp_auth's output, adds no
    new trust surface."""
    provider_hint: str          # which provider this identity maps to ("microsoft"/"google")
    tenant: str                 # the DNA tenant (from resolve_tenant — already computed)
    subject: str                # user oid / email — the principal to act as
    raw_token: str | None       # the inbound bearer (Microsoft OBO needs it as `assertion`;
                                #   Google auth-code/DWD do NOT — hence Optional)
    claims: dict                # verified claims, for providers that need more

class ActOnBehalfPort(Protocol):
    provider: str               # "microsoft" | "google"

    def supports(self, capability: str) -> bool:
        """Does this provider+deployment offer this capability (calendar/files/mail)?"""

    async def credential_for(
        self, ctx: ActContext, capability: str, scopes: list[str]
    ) -> "UserCredential":
        """Return a user-scoped credential for `capability` at least-privilege
        `scopes`. THIS is the provider-specific step:
          - Microsoft impl → OBO exchange (assertion = ctx.raw_token) → Graph token
          - Google impl    → resolve the user's consented OAuth token (refresh),
                             or mint a DWD-impersonated token (sub = ctx.subject)
        Raises ActOnBehalfUnavailable when this identity can't be acted upon
        (e.g. a non-Entra identity asking the Microsoft impl — honest gap, no crash)."""

@dataclass(frozen=True)
class UserCredential:
    """The common output of step (A): a bearer + the base URL of the provider's
    API. A capability adapter (step B) uses ONLY this — it never sees OBO vs OAuth
    vs DWD. Request-lifetime only; never persisted, never logged, never returned
    to the client (inherits the Microsoft-OBO security posture verbatim)."""
    bearer: str
    api_base: str               # graph.microsoft.com  |  www.googleapis.com
    expires_at: float
```

TS parity mirrors this (`ActOnBehalfPort` interface, camelCase) — but execution is
Python-side for the PoC (see §8); the *surface* is Py↔TS by construction (§7).

### 4.3 Why a port (not an `if provider == "google"` branch)

- **Additive, zero-blast-radius.** Microsoft OBO becomes `MicrosoftOboProvider`
  implementing the port; its behavior is byte-identical to `ADR-mcp-obo.md`. Google
  arrives as a **new class behind the same contract** — no capability adapter, no
  tool, no auth code changes.
- **Same ethos as the inbound seam.** `_mcp_auth` already made *providers = config
  blocks* for identity. The port makes *providers = pluggable classes* for action.
  One repo, one mental model on both sides of the request.
- **Honest capability gaps are structural.** `supports()` + `ActOnBehalfUnavailable`
  turn "this identity can't do that" (a non-Entra user asking for Graph; a Google
  tenant with no DWD) into a clean, testable branch — exactly the `CrossTenantError
  → ToolError` discipline already in the codebase.

---

## 5. Capabilities vs providers

Separate the **capability** (provider-neutral: *what*) from the **provider**
(*how*). A capability adapter is written **once** and dispatches to whatever port
the resolved provider supplies.

| Capability (neutral) | Microsoft (Graph) | Google (Workspace) | Read scope M / G |
|---|---|---|---|
| `calendar_list` | `GET /me/events` (or `/me/calendarView`) | Calendar `events.list` | `Calendars.Read` / `calendar.readonly` |
| `files_search` | `GET /me/drive/root/search(q=…)` | Drive `files.list?q=…` | `Files.Read` / `drive.readonly` |
| `mail_list` | `GET /me/messages?$search=…` | Gmail `users.messages.list` | `Mail.Read` / `gmail.readonly` |

**Tool naming — the central UX question (open decision, §10).** Two viable shapes:

- **Provider-neutral tool + auto-dispatch** — one `calendar_list` tool; DNA resolves
  the caller's provider (§6) and calls the right port. The model sees *one* calendar
  tool; agnosticism is invisible and total. This is the **thesis made literal**.
- **Provider-prefixed tools** — `ms_calendar_list`, `google_calendar_list`
  coexist; the model picks. Simpler, more explicit, matches `ADR-mcp-obo.md`'s `ms_*`
  naming, but leaks the vendor into the surface (the exact thing we're neutralizing).

**Recommendation: provider-neutral tool names with internal dispatch, with the
`ms_*`/`google_*` names retained as optional explicit aliases.** `ms_calendar_list`
from the OBO ADR becomes the Microsoft *binding* of the neutral `calendar_list`
capability — it still exists, still works, but is now one implementation the neutral
tool can resolve to. The neutral name is what makes "author once, operate anywhere"
true at the tool layer, not just the pitch layer.

---

## 6. Identity → provider mapping

The inbound identity already tells us which provider to act through — DNA doesn't
need a new sign-in or a new trust decision. The **provider that verified the token**
*is* the provider we act on behalf of.

- `_mcp_auth`'s N-provider composite already **routes each token to its provider
  and stamps** which one matched (`_dna_tenant_claim` marker on `token.claims`).
  Extend that stamp with a **provider-family** hint: `entra → "microsoft"`,
  `google/workspace-OIDC → "google"`. `ActContext.provider_hint` reads it. No new
  verification, no new trust surface — a label on an already-verified token.
- **Resolution rule:** the verified inbound provider selects the `ActOnBehalfPort`.
  A Microsoft-signed-in user (Entra `tid`) → `MicrosoftOboProvider`. A
  Google-signed-in user → `GoogleWorkspaceProvider`. This is deterministic and
  needs no config beyond "which providers are enabled".
- **The `raw_token` asymmetry is why the port doesn't assume token-exchange.**
  Microsoft OBO *needs* the inbound token (it's the `assertion`). Google auth-code
  does **not** — it uses a previously-consented refresh token keyed by the user;
  Google DWD signs its own assertion with `sub=<user>`. `ActContext` carries
  `raw_token` **optionally**, and each impl takes what it needs. This asymmetry,
  surfaced honestly in the contract, is the concrete proof the port abstracts the
  *outcome*, not Microsoft's *mechanism*.

**Mixed / multi-provider (a user with both a Microsoft and a Google identity).**
v1 keeps it simple and correct: **one inbound token = one provider = one act-on-
behalf path.** The user acts through whichever identity they signed in with. If a
user has *both* and wants "search across both my drives", that is a **fan-out over
two ports** — explicitly deferred (§8). The port makes it *possible* later (call N
providers, merge results) without any contract change; v1 does not build it.
Provider **linking** (associating a Google identity to a Microsoft-signed-in DNA
user, or vice-versa) is a whole account-model feature — out of scope, noted so we
don't accidentally design it away.

---

## 7. Config

Extend the OBO ADR's `graph:` block into a **provider-keyed** shape — the plural of
what already exists. Fail-closed and **secrets-by-env-name only** (the exact
pattern `MCPFederation` and `_mcp_auth` already use — the SDK core never holds a
secret value, only the *name* of the env var that does).

```yaml
# dna.config.yaml
act_on_behalf:                 # absent → the whole surface off (default; OSS/stdio untouched)
  providers:
    microsoft:                 # the reference impl (== today's `graph:` block, re-homed)
      enabled: true
      mechanism: obo
      client_id_env:  DNA_MS_CLIENT_ID
      credential_env: DNA_MS_CLIENT_SECRET   # secret (PoC) / cert or federated-cred (prod)
      capabilities:
        calendar: { enabled: true,  scopes: [ "Calendars.Read" ] }
        files:    { enabled: false, scopes: [ "Files.Read" ] }
        mail:     { enabled: false, scopes: [ "Mail.Read" ] }
    google:                    # the new provider — off until built + credentialed
      enabled: false
      mechanism: oauth         # "oauth" (per-user consent) | "dwd" (domain-wide delegation)
      client_id_env:     DNA_GOOGLE_CLIENT_ID
      credential_env:    DNA_GOOGLE_CLIENT_SECRET   # oauth: client secret
      # dwd only: service-account key by env NAME, + the delegated subject domain
      sa_key_env:        DNA_GOOGLE_SA_KEY_JSON
      capabilities:
        calendar: { enabled: false, scopes: [ "https://www.googleapis.com/auth/calendar.readonly" ] }
```

Design invariants:
- **`act_on_behalf:` absent → the entire surface is off.** stdio / OSS / self-host
  never touch Microsoft *or* Google. HTTP-only, opt-in, per `ADR-mcp-obo.md`.
- **Config is the scope ceiling.** A capability can only ever request a scope the
  config enabled for that provider — a static, fail-closed allow-list (unchanged
  from the OBO ADR, now per-provider).
- **Read-first.** Every default scope above is read-only. Write scopes
  (`Mail.Send`, `calendar.events`) are a separate, later, separately-consented tier.
- **Slots into existing machinery.** `dna.config.py` already treats `auth:` as an
  opaque validated passthrough; `act_on_behalf:` is a sibling block parsed by the
  consumer (`dna_cli`), never by the SDK core — same split as `auth:`.

---

## 8. PoC scope (smallest slice that *proves* agnosticism)

The PoC's job is not "ship Google" — it's **prove the port makes the layer
provider-agnostic** with the least code. That means: extract the port from the
Microsoft impl (proving nothing breaks) **and** stand up a Google skeleton behind
the *same* contract for *one* capability (proving a second provider fits).

**In the PoC:**
1. **Define `ActOnBehalfPort` + `ActContext` + `UserCredential`** (Py; TS interface
   parity).
2. **`MicrosoftOboProvider`** — the OBO exchange from `ADR-mcp-obo.md` refactored to
   *implement the port*. Behavior identical; this is the "nothing breaks" proof.
   (If OBO ships first as concrete code, this step is a **refactor-in-place**, not a
   rewrite.)
3. **`calendar_list` capability adapter** — one provider-neutral adapter (step B)
   that consumes a `UserCredential` and calls the resolved provider's calendar API.
   Microsoft binding fully wired.
4. **`GoogleWorkspaceProvider` skeleton** — implements the port for `calendar`
   only: `supports("calendar") → True`, `credential_for(...)` wired to the Google
   OAuth token path with the **mechanism stubbed at the network boundary** (returns
   a `UserCredential` from a fake/dev token in tests; real `gcloud`/consent setup is
   deferred). Enough to prove the neutral `calendar_list` tool dispatches to *either*
   provider by identity — the agnosticism claim, demonstrated.
5. **Identity→provider stamp** — extend the composite verifier's stamp with the
   provider-family hint; `ActContext.provider_hint` reads it.
6. **Tests** mirroring `test_mcp_auth.py`: fake both providers (no live Entra/Google),
   assert `calendar_list` resolves Microsoft-token → Microsoft port and
   Google-token → Google port, and that a non-supported identity yields a clean
   `ActOnBehalfUnavailable`. One optional live smoke per provider behind an env flag
   (manual, not CI).

**Deferred (explicitly NOT in the PoC):**
- **Full Google implementation** — real OAuth consent flow, refresh-token storage,
  and **Domain-Wide Delegation** (super-admin setup + service-account key). The PoC
  proves the *seam*, not a production Google integration.
- **files / mail capabilities**, and **all write** tools.
- **Multi-provider fan-out** (one user, both providers, merged results) and
  **provider linking** (§6).
- **Prod credential hardening** (cert / ACA managed-identity federated cred; Google
  Workload Identity Federation) and any **token caching**.
- Everything `ADR-mcp-obo.md` already defers (CA claims-challenge passthrough,
  incremental-consent UX, guest/MSA identities).

---

## 9. What stays, what generalizes

| | Before (OBO ADR) | After (this ADR) |
|---|---|---|
| Microsoft OBO exchange | The whole feature | `MicrosoftOboProvider` — reference impl of the port (**unchanged behavior**) |
| Tool `ms_calendar_list` | The tool | The Microsoft *binding* of neutral `calendar_list` (still callable) |
| Inbound auth (`_mcp_auth`) | N-provider identity | +one field: provider-family stamp (additive) |
| Config | `graph:` block | `act_on_behalf.providers.microsoft` (`graph:` re-homed 1:1) + `.google` sibling |
| Security posture | per-request token, never persisted, scope-min | **inherited verbatim** by the port for every provider |
| Google | — | New class behind the port; **zero** change to any of the above |

The generalization is a **superset**: every Microsoft decision in `ADR-mcp-obo.md`
survives; the port is the socket the second plug goes into.

---

## 10. Open decisions for Barna

1. **Neutral tool names vs provider-prefixed.** Recommend **provider-neutral
   `calendar_list` with internal identity→provider dispatch**, keeping `ms_*` as an
   explicit alias/binding. This is the thesis made literal at the tool layer — but
   it hides *which* backend ran, which some operators want visible. Confirm, or keep
   `ms_*` / `google_*` explicit.
2. **Google mechanism: per-user OAuth vs Domain-Wide Delegation.** Recommend
   **per-user OAuth (auth-code + refresh)** for v1 — it mirrors "the user consents,
   DNA acts as them" (the OBO shape) and needs no Workspace super-admin. **DWD** is
   more powerful (no per-user consent, whole-domain) but requires super-admin
   enablement and stores a high-value service-account key. Decide which is the v1
   Google path (the port supports both via `mechanism:` in config; this picks the
   default we *build*).
3. **How identity→provider resolves.** Recommend **the verified inbound provider
   selects the port** (Microsoft-signed-in → Microsoft; Google-signed-in → Google) —
   deterministic, no extra config. Confirm this over any explicit per-tool provider
   argument.
4. **Multi-provider users — now or never-in-v1.** Recommend **one token = one
   provider in v1**, with fan-out/linking deferred but not designed away (§6).
   Confirm we're not committing to cross-provider merge yet.
5. *(Minor)* **Is AWS truly out?** This ADR argues **yes** — AWS has no user
   productivity data; `AssumeRole` is infra identity, a *different* port if ever
   needed. Confirm we're not conflating "act on behalf of the user's data" with
   "operate the user's cloud".

---

## 11. Rough size

- **PoC** (port contract + Microsoft-as-port refactor + `calendar_list` neutral
  adapter + Google skeleton for calendar + provider stamp + unit tests):
  **~2 Stories**, ~3–4 days. Blast radius is small and additive — the Microsoft path
  is a refactor-behind-an-interface, Google is new-and-off, no change to the
  inbound auth/tenancy contract.
- **v1 Microsoft** (files + mail neutral capabilities, config surface, Tool docs):
  overlaps `f-mcp-obo`'s v1 — the two features share the capability adapters once
  the port exists.
- **v1 Google** (real OAuth consent + refresh storage for calendar, then files/mail):
  **~3–4 Stories**, gated on a Google Cloud project + OAuth client + (for DWD)
  Workspace super-admin — the same "the setup, not the code, is the dependency"
  pattern as OBO's app-registration gate.
- **Prod hardening** (cert / federated creds both sides, token caching, fan-out):
  separable, **~2–3 Stories**.

The dependency is **not** code — it's the **per-provider trust setup** (Entra app +
consent; Google OAuth client / DWD super-admin), which only Barna/an admin can do.
That gates the live smokes, not the port plumbing, which is buildable and testable
against fakes today.

---

## 12. The one-line thesis

`_mcp_auth` already proved DNA can *verify any identity* through one seam;
`ActOnBehalfPort` is the outbound twin that lets DNA *act on any provider's user
data* through one seam — the moment the calendar tool stops being `ms_*` and
becomes `calendar_list` that just works whether you signed in with Microsoft or
Google is the moment "author once, DNA operates your digital life in any AI client"
stops being a pitch and becomes the architecture.
