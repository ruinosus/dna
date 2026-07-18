# Identity Front-Door — P1 (facade + zero-config) — Design

**Status:** proposed · **Feature:** `f-identity-frontdoor` · **Phase:** P1
**Date:** 2026-07-17 · **Author:** claude-code (with Barna)
**Supersedes/relates:** [ADR-mcp-obo](../adr/ADR-mcp-obo.md) · design intent visual:
Identity Front-Door artifact (two-lane facade)

> **Goal (one sentence):** Put a spec-compliant OAuth 2.1 **facade in front of Entra**
> so Claude's connector auto-connects **zero-config** to the DNA MCP, **without losing
> On-Behalf-Of (OBO)** access to the user's downstream data — shipped by swapping the
> existing FastMCP auth provider, not by building a new service.

---

## 1. Context & problem

The DNA MCP (streamable HTTP, already FastMCP-based) is today an **Entra-guarded
resource server**: issuer `/organizations`, audience `api://dna-mcp-dnacloud/user_impersonation`,
per-user bearer forwarded, personal memory keyed by the Entra `oid`. Two product gaps,
both rooted in the same fact — **Entra supports neither Dynamic Client Registration (DCR)
nor consumer signup**:

1. **No zero-config Claude connect.** Claude's connector auto-registers via DCR (RFC 7591)
   / CIMD; Entra refuses, so a user must paste a `client_id` by hand.
2. **No consumer (Gmail) signup.** Issuer `/organizations` = org accounts only.

These decouple. **P1 solves gap #1 for the Entra (org) lane.** The Gmail lane (gap #2) is
P2/P3 and is *designed for* here but *not built* in P1.

### The non-negotiable: OBO must survive

DNA's thesis is consuming the user's data across tools. For org users that means the MCP
runs **Entra OBO** (`jwt-bearer`) to exchange the user's MCP-audienced token for a
downstream token (Microsoft Graph — M365 mail/calendar/OneDrive/Teams) **as the user**.
OBO requires the token reaching the MCP to be an **Entra-issued token audienced to the
MCP app**. Any design that hands the MCP a self-minted token breaks OBO. This constraint
drives every decision below.

---

## 2. Decisions (locked)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | The facade is a **spec-compliant facade in front of Entra, NOT an independent token mint**. | MCP spec forbids token passthrough; Entra rejects RFC 8693 token-exchange (`AADSTS70003`). OBO needs the Entra assertion to reach the MCP. |
| D2 | **Reference/implementation = FastMCP `OAuthProxy` / `AzureProvider`** (already a dependency-compatible fit — our MCP is FastMCP). | Source-verified: it adds DCR/PRM/AS-metadata/S256/401 for free **and preserves the Entra assertion** (see §5.3). Near-drop-in. |
| D3 | **Routing = Option X** (per-lane native provider). Lane A → `AzureProvider` (Entra-direct); Lane B → WorkOS AuthKit on a **separate mount**. | Option Y (WorkOS as single upstream federating Entra) **breaks OBO** for org users — WorkOS issues its own JWT and discards the Entra assertion. Verified against WorkOS docs. |
| D4 | **Consumer IdP = WorkOS AuthKit** (P2). | 1M MAU free, native DCR + CIMD + RFC 9728, Entra-federation flagship. (Not exercised in P1.) |
| D5 | **First ship = P1 (facade + zero-config), no manual-`client_id` deliverable.** | Product call (Barna): "não vou usar até o zero-config". P0 (manual client_id) is an internal test foundation only. |
| D6 | **Memory-partition key stays backward-compatible.** Existing/Entra identities keep `personal:<oid>` (implicitly the Entra family — **no data migration**); the Gmail family (P2) gets `personal:google:<sub>`. | Avoids migrating live personal-memory keys; the family namespace is only introduced where a collision could occur. |

---

## 3. Architecture — P1 scope

```
Claude connector ──(PKCE S256, DCR)──▶  DNA MCP  (FastMCP, auth = AzureProvider)
                                          │
             serves for free:            │  on each tool call, the auth layer
             /.well-known/oauth-protected-resource   swaps the FastMCP wire JWT
             /.well-known/oauth-authorization-server  back to the retained UPSTREAM
             /register (DCR)              │  Entra token → get_access_token().token
             401 + WWW-Authenticate       │  = real Entra assertion (aud = MCP app)
                                          ▼
                              DNA OBO (graph/_obo.py, UNCHANGED)
                                          ▼
                              Microsoft Graph — M365 (as the user)
```

P1 changes the MCP's **auth provider** from today's `JWTVerifier` to `AzureProvider`
(FastMCP's `OAuthProxy` subclass for Entra). Nothing else in the request path — the
tenancy/tier bridge, the tool handlers, the OBO exchange — changes, because they all read
claims off `get_access_token()`, and the swapped-in token still carries `tid`/`oid`.

**Lane B (WorkOS/Gmail) is out of P1** but the mount architecture (§5.5) is chosen so P2
adds a second mount without re-architecting P1.

---

## 4. Gate-0 — DONE (live-verified 2026-07-17)

The spike verified the design **from source**; the two live-only claims were then
confirmed by booting the real DNA MCP with `AzureProvider` locally.
**Status: both PASS** (rigs: `scratchpad/serve_azure_smoke.py`, `scratchpad/obo_smoke.py`).

- **G0.1 — Live OBO smoke — ✓ PASS.** A real Entra user token (`aud=ff09090f`,
  `scp=user_impersonation`) fed to `graph/_obo.py exchange_on_behalf_of` minted a real
  Graph token B (`aud=graph.microsoft.com`, `scp=Calendars.Read`) as the user — OBO
  preserved end-to-end. (The final `/me/events` read returned AADSTS500014 = the dev test
  tenant has Exchange disabled — a data-availability limit, not an auth/OBO defect.) The
  zero-config surface (DCR/CIMD/S256/401/PRM) was served live by the facade.
- **G0.2 — Multi-tenant authority — ✓ PASS (with a 1-line fix, now shipped).**
  `AzureProvider(tenant_id="organizations")` pins the issuer to the literal
  `.../organizations/v2.0`; `azure_provider_from_env()` sets `_token_validator.issuer = None`
  for multi-tenant authorities (fastmcp's own `from_b2c` mutation), reproducing DNA's
  `verifier_issuer() is None` policy. Verified live: issuer relaxed, audience
  `['ff09090f-…','api://dna-mcp-dnacloud']`.

Residual (low-risk, source-verified): the token-swap inside a full facade OAuth flow — the
gate-0 token was fetched via `az`, not through the facade's `/authorize`; the swap itself is
source-verified and the verifier config is live-verified. Closed by the P1 external gate
(a redirect-URI app-reg + a real-M365-tenant connect).

- **G0.1 — Live OBO smoke under `AzureProvider`.** The token-swap (§5.3) is code-verified,
  not run end-to-end. Prove: Claude (or a scripted OAuth client) → `AzureProvider` → a DNA
  tool → `entra_obo_assertion_from_context()` (`_mcp_auth.py:773`) receives a valid Entra
  token with `aud = api://dna-mcp-dnacloud` and a `tid`, and `graph/_obo.py` exchanges it
  to a Graph token successfully. **Highest-value validation.**
- **G0.2 — Multi-tenant authority check.** DNA is multi-tenant (partner-org OBO to each
  home tenant). Confirm `AzureProvider` supports a multi-tenant authority
  (`tenant_id=organizations`/`common`) + audience-only / issuer-relaxed validation the way
  DNA's `--auth config` Entra path does. If it hardwires a single tenant, that's a real
  gap to close (subclass / config) before build.

If either fails, the spec is revised (not the build patched around it).

---

## 5. Component design

### 5.1 `AzureProvider` integration (the drop-in)

- **Attach point:** `build_server(...)` at `packages/cli/dna_cli/_mcp_server.py:364`
  already does `FastMCP("dna", auth=auth, …)`. The class chain
  `AzureProvider ⊂ OAuthProxy ⊂ OAuthProvider ⊂ AuthProvider` makes an `AzureProvider`
  instance a valid `auth=`. FastMCP auto-mounts `/authorize`, `/token`, `/register`, both
  well-knowns, and the auth middleware.
- **Provider factory + CLI branch:** add an `azure_provider_from_env()` factory next to
  `jwt_provider_from_env()` in `_mcp_auth.py:914` (the module header already anticipates
  *"a WorkOS/Auth0 `OAuthProxy` slots into this same factory later"*), and an `--auth azure`
  branch in `mcp_cmd.py:100-124` (alongside `none|jwt|config`).
- **Config:** `AzureProvider(client_id=…, client_secret=…, tenant_id=…, base_url=…,
  required_scopes=[…])`. `client_secret`/cert on the `dna-mcp-dnacloud` app-reg is required
  by both OBO and AzureProvider (already tracked in ADR-mcp-obo §8).

### 5.2 Zero-config discovery (what FastMCP gives free)

Verified present in FastMCP `OAuthProxy` + pinned `mcp` SDK: DCR `/register`; RFC 9728
protected-resource-metadata; RFC 8414 AS-metadata; `code_challenge_methods_supported:
["S256"]`; and the **401 + `WWW-Authenticate: Bearer … resource_metadata="…"`** challenge
that Claude's auto-discovery keys on. **CIMD is also advertised** on fastmcp 3.4.4
(`client_id_metadata_document_supported: true` in the AS-metadata — verified live in gate-0;
the earlier spike read an older fastmcp where it was absent). So both DCR *and* CIMD are
served free — no gap. (WorkOS advertises CIMD natively for Lane B too.)

### 5.3 OBO preservation (the mechanism — why the fear was wrong)

`OAuthProxy` issues its **own** HS256 wire JWT (not the Entra token) — but it **retains the
upstream Entra token server-side** (`UpstreamTokenSet`, JTI→token map) and, on every tool
call, `load_access_token` resolves the wire JWT's JTI back to the upstream token and returns
an `AccessToken` whose `.token` **is the real Entra assertion**. For Azure the verifier is
audienced to `[client_id, identifier_uri]` — exactly the OBO precondition. DNA's
`entra_obo_assertion_from_context()` reads `get_access_token().token` + `claims["tid"]`, so
**DNA's existing MSAL OBO (`graph/_obo.py`) works unchanged.** We do **not** adopt FastMCP's
`EntraOBOToken` — DNA already has the equivalent. (Control cross-check: Cloudflare
`workers-oauth-provider` uses the same retain-upstream pattern; `atrawog/mcp-oauth-gateway`
discards it and is not OBO-capable — confirming FastMCP's is the OBO-friendly mainstream.)

### 5.4 Memory-partition key

Today: `personal:<oid>` via `personal_tenant(oid)` (`packages/sdk-py/dna/memory/personal.py:38`),
`oid` resolved only from the Entra `oid` claim, fail-closed if absent
(`resolve_personal_oid`, `_mcp_auth.py:299`). For P1 (Entra-only) this is **unchanged** —
`AzureProvider` still yields an `oid`. The dual-family seam already exists
(`_DNA_PROVIDER_FAMILY_MARKER`, `_mcp_auth.py:81`; `act_context_from_context` already does an
oid-or-sub fallback, `act_on_behalf/_dispatch.py:82`) and is **wired in P2**, when the Gmail
family gets `personal:google:<sub>` while Entra keeps bare `personal:<oid>` (no migration).
Guards preserved throughout: identity is **server-derived only** (never a caller arg) and
**fail-closed** on a missing identity.

### 5.5 Lane B second mount (P2 — designed-for, NOT built in P1)

Option X needs Lane B on its own mount wrapping WorkOS AuthKit. Reuse the existing
multi-mount pattern in `build_http_app` (`_mcp_server.py:693-722`). P1 leaves a single
mount (Lane A); P2 adds the WorkOS mount + the family-namespaced memory key. Documenting it
here so P1's mount/auth wiring doesn't foreclose it.

---

## 6. Integration points (file:line)

| Concern | File | Change |
|---|---|---|
| Auth provider attach | `packages/cli/dna_cli/_mcp_server.py:364` | `auth=azure_provider_from_env()` |
| Provider factory | `packages/cli/dna_cli/_mcp_auth.py:914` | add `azure_provider_from_env()` |
| CLI `--auth` branch | `packages/cli/dna_cli/mcp_cmd.py:100-124` | add `azure` |
| OBO assertion read (verify only) | `packages/cli/dna_cli/_mcp_auth.py:773` | unchanged; asserted by G0.1 |
| OBO exchange (verify only) | `packages/cli/dna_cli/graph/_obo.py:52` | unchanged |
| Memory key (P2) | `dna/memory/personal.py:38`, `_mcp_auth.py:299` + TS twin | namespace `google:<sub>` (P2) |
| Lane B mount (P2) | `_mcp_server.py:693-722` | second mount (P2) |

---

## 7. Out of scope (P1)

- Lane B / Gmail signup, WorkOS wiring, Google incremental consent (→ P2/P3).
- The family-namespaced memory key (→ P2; P1 keeps `personal:<oid>`).
- (CIMD is already advertised free by fastmcp 3.4.4 — no longer a scoped-out item.)
- Any change to the copilot, portal, or the tool handlers.

---

## 8. Risks

1. **OBO-under-`AzureProvider` is code-verified, not yet live** — mitigated by gate G0.1
   (blocks build).
2. **Multi-tenant authority on `AzureProvider` unverified** — mitigated by gate G0.2.
3. **AzureProvider OBO needs a `client_secret`/cert and is disabled for B2C** — standard
   Entra only; consistent with our setup (ADR-mcp-obo §8).
4. **Claude egress `160.79.104.0/21` must reach the facade host** — ACA ingress allowlist
   note (deployment, not architecture; current hosting is public ACA ingress).
5. **`main`-branch drift in FastMCP/`mcp` SDK** — re-confirm the free-metadata claims
   against the pinned versions at build time.

---

## 9. Phasing recap

| Phase | Scope | Ship? |
|---|---|---|
| **P0** | Manual `client_id` + PKCE (Entra) — internal test foundation | no (internal) |
| **P1** | **This spec** — `AzureProvider` facade + zero-config, OBO preserved (Lane A) | **first ship** |
| P2 | WorkOS mount + Gmail login + family-namespaced memory key (Lane B) | later |
| P3 | Google incremental consent → Gmail/Drive/Calendar ingestion (Lane B data) | later |

---

## Next

1. **Gate-0** (G0.1 live OBO smoke + G0.2 multi-tenant check) — before any implementation.
2. On gate pass → implementation plan (`docs/plans/`) → build P1.
3. Spec review + Barna sign-off before gate-0 execution.
