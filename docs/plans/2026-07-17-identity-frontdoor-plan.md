# Identity Front-Door Implementation Plan (P1 → P3)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the two-lane OAuth 2.1 identity front-door so Claude connects zero-config to the DNA MCP (Lane A, Entra) with OBO preserved, and consumers sign up + bring their Google data (Lane B, Gmail via WorkOS) — across three independently-shippable phases.

**Architecture:** A spec-compliant **facade in front of Entra** (FastMCP `OAuthProxy`/`AzureProvider`), NOT a token mint — so the Entra assertion survives for OBO. Lane A authenticates directly against Entra (`AzureProvider` + issuer-relax); Lane B mounts **WorkOS AuthKit** on a second server mount. Identity is resolved per-provider-family and namespaced into the memory-partition key. Downstream data is consumed via **Entra OBO → Graph** (Lane A) and **Google incremental consent → Gmail/Drive/Calendar** (Lane B). Design: `docs/design/2026-07-17-identity-frontdoor-p1-design.md`.

**Tech Stack:** Python (dna-cli, FastMCP `AzureProvider`/`OAuthProxy`, MSAL for OBO), FastMCP multi-mount HTTP, WorkOS AuthKit (Lane B IdP), Google OAuth 2.0 (Lane B data), Entra ID (Lane A). TS twin for the memory-key change (byte-parity).

**Gate-0 (DONE, live-verified 2026-07-17):** `AzureProvider` boots the DNA MCP via `build_server(auth=...)`; DCR/CIMD/S256/401/PRM all served; issuer-relax fix works; OBO exchange mints a real Graph token B as the user. Rigs: `scratchpad/serve_azure_smoke.py`, `scratchpad/obo_smoke.py`. This plan turns those prototypes into shipped code.

---

## File Structure

**Lane A / P1 (Entra facade + zero-config):**
- Modify: `packages/cli/dna_cli/_mcp_auth.py` — add `azure_provider_from_env()` factory (next to `jwt_provider_from_env`, `:914`).
- Modify: `packages/cli/dna_cli/mcp_cmd.py` — add `azure` to `--auth` choices + branch (`:43`, `:100-124`).
- Modify: `packages/cli/dna_cli/_mcp_server.py` — `build_server(auth=...)` already accepts it (`:213`, attach `:364`); no change beyond passing the provider.
- Test: `packages/cli/tests/test_mcp_auth_azure.py` (new).

**Lane B / P2 (WorkOS mount + dual memory key):**
- Modify: `packages/cli/dna_cli/_mcp_auth.py` — namespaced identity resolution (`oid_from_token`/`resolve_personal_oid`/`enforce_oid_from_context`, `:278-331`, `:800-830`); `workos_provider_from_env()` factory.
- Modify: `packages/sdk-py/dna/memory/personal.py` — family-namespaced partition key (`personal_tenant`/`PERSONAL_TENANT_PREFIX`, `:38-88`).
- Modify: `packages/sdk-ts/src/memory/personal.ts` — TS twin (byte-parity).
- Modify: `packages/cli/dna_cli/_mcp_server.py` — second mount for Lane B in `build_http_app` (`:693-722`).
- Test: `packages/cli/tests/test_dual_memory_key.py`, `packages/sdk-ts/tests/personal-key.test.ts` (new).

**Lane B / P3 (Google data ingestion):**
- Create: `packages/cli/dna_cli/graph/_google.py` — Google delegated-token exchange (analog of `_obo.py`).
- Create: Google-source memory tools (Gmail/Drive/Calendar → memory), wired like the `ms_calendar_list` OBO tool.
- Test: `packages/cli/tests/test_google_delegation.py` (new).

---

## Chunk 1: P1 — Entra facade + zero-config (Lane A)

### Task 1: `azure_provider_from_env()` factory

**Files:**
- Modify: `packages/cli/dna_cli/_mcp_auth.py` (add factory near `:914`)
- Test: `packages/cli/tests/test_mcp_auth_azure.py`

- [ ] **Step 1: Write the failing test**

```python
# test_mcp_auth_azure.py
import os
import pytest

def test_azure_provider_from_env_builds_multitenant_issuer_relaxed(monkeypatch):
    monkeypatch.setenv("DNA_MCP_AZURE_CLIENT_ID", "ff09090f-79e3-4dfe-975c-1a8e007112b7")
    monkeypatch.setenv("DNA_MCP_AZURE_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setenv("DNA_MCP_AZURE_TENANT", "organizations")
    monkeypatch.setenv("DNA_MCP_AZURE_BASE_URL", "http://localhost:8765")
    monkeypatch.setenv("DNA_MCP_AZURE_IDENTIFIER_URI", "api://dna-mcp-dnacloud")
    from dna_cli._mcp_auth import azure_provider_from_env
    p = azure_provider_from_env()
    # multi-tenant: issuer relaxed (the G0.2 fix), audience = [client-id GUID, identifier_uri]
    assert p._token_validator.issuer is None
    assert "ff09090f-79e3-4dfe-975c-1a8e007112b7" in p._token_validator.audience
    assert "api://dna-mcp-dnacloud" in p._token_validator.audience

def test_azure_provider_single_tenant_keeps_issuer(monkeypatch):
    monkeypatch.setenv("DNA_MCP_AZURE_CLIENT_ID", "ff09090f-79e3-4dfe-975c-1a8e007112b7")
    monkeypatch.setenv("DNA_MCP_AZURE_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setenv("DNA_MCP_AZURE_TENANT", "c5b891f7-65c2-4417-a5af-22cab24dc1d5")
    monkeypatch.setenv("DNA_MCP_AZURE_BASE_URL", "http://localhost:8765")
    from dna_cli._mcp_auth import azure_provider_from_env
    p = azure_provider_from_env()
    # single concrete tenant → issuer pinned (only multi-tenant relaxes it)
    assert p._token_validator.issuer is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=packages/sdk-py:packages/cli python -m pytest packages/cli/tests/test_mcp_auth_azure.py -v`
Expected: FAIL — `azure_provider_from_env` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# _mcp_auth.py — near jwt_provider_from_env (:914)
_AZURE_MULTITENANT = {"organizations", "consumers", "common"}

def azure_provider_from_env():
    """Build a FastMCP AzureProvider (OAuthProxy facade) from env — the Lane A
    (Entra) provider. Multi-tenant authorities relax issuer validation to
    audience+signature only (real Entra tokens carry the caller's own tenant GUID
    as `iss`, so a pinned issuer would reject every partner-org token — the same
    `verifier_issuer() is None` policy the `--auth config` path already uses)."""
    from fastmcp.server.auth.providers.azure import AzureProvider
    cid = os.environ["DNA_MCP_AZURE_CLIENT_ID"]
    secret = os.environ["DNA_MCP_AZURE_CLIENT_SECRET"]
    tenant = os.environ.get("DNA_MCP_AZURE_TENANT", "organizations")
    base_url = os.environ["DNA_MCP_AZURE_BASE_URL"]
    identifier_uri = os.environ.get("DNA_MCP_AZURE_IDENTIFIER_URI")
    scopes = [s for s in os.environ.get("DNA_MCP_AZURE_SCOPES", "").split(",") if s]
    kwargs = dict(client_id=cid, client_secret=secret, tenant_id=tenant, base_url=base_url)
    if identifier_uri:
        kwargs["identifier_uri"] = identifier_uri
    if scopes:
        kwargs["required_scopes"] = scopes
    p = AzureProvider(**kwargs)
    if tenant in _AZURE_MULTITENANT:
        p._token_validator.issuer = None  # G0.2 fix (fastmcp's own from_b2c pattern)
    return p
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add packages/cli/dna_cli/_mcp_auth.py packages/cli/tests/test_mcp_auth_azure.py
git commit -m "feat(mcp-auth): azure_provider_from_env — Entra facade w/ multi-tenant issuer relax"
```

### Task 2: `--auth azure` CLI branch

**Files:**
- Modify: `packages/cli/dna_cli/mcp_cmd.py` (`:43` choices, `:100-124` branch)
- Test: extend `packages/cli/tests/test_mcp_auth_azure.py`

- [ ] **Step 1: Write the failing test** — assert `dna mcp serve --auth azure --transport http` builds a server whose auth is an `AzureProvider` (via a monkeypatched `build_server` capturing the `auth=` arg, env set as Task 1).
- [ ] **Step 2: Run — FAIL** (`azure` not a valid `--auth` choice).
- [ ] **Step 3: Implement** — add `"azure"` to the `click.Choice` (`:43`); in the `if auth in (...)` block add `elif auth == "azure": from dna_cli._mcp_auth import azure_provider_from_env; auth_provider = azure_provider_from_env()`.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(cli): dna mcp serve --auth azure (Lane A Entra facade)`.

### Task 3: Discovery-surface integration test

**Files:**
- Test: `packages/cli/tests/test_azure_discovery.py` (new) — boots `build_server(auth=azure_provider_from_env())` via `build_http_app` in a test client, asserts the zero-config surface (mirrors the gate-0 curl).

- [ ] **Step 1: Write the failing test** — using FastMCP's in-memory/Starlette test client, GET `/.well-known/oauth-authorization-server` → assert `registration_endpoint` present, `code_challenge_methods_supported == ["S256"]`, `client_id_metadata_document_supported is True`, `"none" in token_endpoint_auth_methods_supported`; POST `/mcp` without a token → 401 with `WWW-Authenticate` containing `resource_metadata`; GET the PRM → `scopes_supported` contains the user_impersonation URI.
- [ ] **Step 2: Run — FAIL** (until env/test-fixture wired).
- [ ] **Step 3: Implement** — a fixture that sets the Task-1 env + builds the app; no product code change (proves §5.2 in CI).
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `test(mcp): zero-config discovery surface under AzureProvider`.

### Task 4: Docs + spec fold-back

- [ ] Update `docs/design/2026-07-17-identity-frontdoor-p1-design.md` §5.2: CIMD **is** advertised on fastmcp 3.4.4 (drop the "DCR-only" caveat); §4 gate-0 → mark G0.1 zero-config + OBO and G0.2 as live-passed with the rig references.
- [ ] Add `docs/guides/mcp-server.md` section: `--auth azure` env vars (`DNA_MCP_AZURE_*`), the OBO note (keep `graph/_obo.py`, do NOT route OBO through the provider's built-in `organizations` tenant).
- [ ] Commit `docs(auth): --auth azure guide + gate-0 results`.

### P1 external gate (Barna) — before the facade goes fully live
- [ ] Register a redirect URI on the `dna-mcp-dnacloud` app-reg for the facade callback (prod host + any local `http://localhost:8765/auth/callback` for the full-flow smoke).
- [ ] Ensure the app-reg has a `client_secret`/cert (already per ADR-mcp-obo §8).
- [ ] ACA ingress: allow Claude connector egress `160.79.104.0/21` to the facade host.
- [ ] **Full-flow smoke:** connect Claude to the deployed MCP with NO manual client_id; confirm DCR auto-registration + a tool call + an OBO round-trip in a real M365 tenant (this session's smoke used a dev tenant with Exchange disabled).

---

## Chunk 2: P2 — WorkOS mount + dual memory key (Lane B login)

### Task 5: Family-namespaced memory-partition key (Py)

**Files:**
- Modify: `packages/sdk-py/dna/memory/personal.py` (`:38-88`)
- Test: `packages/cli/tests/test_dual_memory_key.py`

- [ ] **Step 1: Write the failing test** — `personal_tenant("oid123", family="entra") == "personal:entra:oid123"` (or the agreed scheme); `personal_tenant("sub456", family="google") == "personal:google:sub456"`; **back-compat**: `personal_tenant("oid123")` (no family) stays `"personal:oid123"` (no migration of existing Entra keys). Collision guard: entra:X and google:X are distinct partitions.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — add an optional `family` param; when given, insert `<family>:` after the prefix; default (None) preserves the current bare `personal:<id>` (Entra implicit). Keep INV-PERSONAL guards (server-derived, fail-closed).
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(memory): family-namespaced personal partition key (dual-lane, back-compat)`.

### Task 6: TS twin (byte-parity)

**Files:**
- Modify: `packages/sdk-ts/src/memory/personal.ts`
- Test: `packages/sdk-ts/tests/personal-key.test.ts`

- [ ] TDD the same behavior in TS; run the parity check (the repo's Py↔TS parity discipline). Commit `feat(memory): TS twin of family-namespaced key`.

### Task 7: Resolve identity per provider family at the auth edge

**Files:**
- Modify: `packages/cli/dna_cli/_mcp_auth.py` (`oid_from_token`/`resolve_personal_oid`/`enforce_oid_from_context`, `:278-331`, `:800-830`)
- Test: `packages/cli/tests/test_dual_memory_key.py`

- [ ] **Step 1: Write the failing test** — given a token stamped Entra family → resolves `oid` → key `personal:oid`; given a token stamped Google family (`_DNA_PROVIDER_FAMILY_MARKER == "google"`) with a `sub` → resolves to `personal:google:<sub>`; a token with NO identity → still fail-closed (`PersonalIdentityRequired`). Reuse the existing `act_context_from_context` oid-or-sub fallback (`act_on_behalf/_dispatch.py:82`) as the model.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — read the family marker; branch the identity claim (Entra `oid`, Google `sub`) and prepend the family into the partition key; keep fail-closed.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(mcp-auth): per-family identity resolution → dual-lane memory key`.

### Task 8: `workos_provider_from_env()` + second mount

**Files:**
- Modify: `packages/cli/dna_cli/_mcp_auth.py` (factory), `packages/cli/dna_cli/_mcp_server.py` (`build_http_app` second mount, `:693-722`)
- Test: `packages/cli/tests/test_workos_mount.py`

- [ ] **Step 1: Write the failing test** — `workos_provider_from_env()` builds a FastMCP OAuth provider pointed at WorkOS AuthKit (client id/secret/authkit-domain from env); `build_http_app(..., lane_b=provider)` mounts a second discovery+auth surface (e.g. `/consumer/mcp`) whose PRM advertises the WorkOS AS. Assert both mounts serve independent well-knowns.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — the factory (using FastMCP's `OAuthProxy` with WorkOS endpoints, or WorkOS's documented AuthKit MCP integration); extend `build_http_app` to accept an optional Lane-B provider and add its mount. Reuse the existing multi-mount pattern.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(mcp): WorkOS AuthKit mount (Lane B consumer login)`.

### P2 external gate (Barna)
- [ ] Create a **WorkOS** account/project; enable **AuthKit** + the **Google** social connection; note client id/secret + AuthKit domain.
- [ ] Configure WorkOS redirect URIs (facade callback) + DCR/CIMD (AuthKit exposes these natively).
- [ ] Decide account-linking policy (v1 recommendation: **no linking** — Entra and Google are distinct identities/partitions; linking is a later feature).
- [ ] Smoke: sign up with a Gmail account through the Lane-B mount → confirm a `personal:google:<sub>` memory partition is created + isolated from any Entra partition.

---

## Chunk 3: P3 — Google incremental consent → data ingestion (Lane B data)

### Task 9: Google delegated-token exchange (`_google.py`)

**Files:**
- Create: `packages/cli/dna_cli/graph/_google.py`
- Test: `packages/cli/tests/test_google_delegation.py`

- [ ] **Step 1: Write the failing test** — an `exchange_google(*, refresh_token|auth_code, client_id, client_secret, scopes, allowed_scopes)` (mirroring `_obo.exchange_on_behalf_of`'s fail-closed + scope-allow-list shape) returns a Google access token via an injectable `acquire` seam (fake in the test — no live Google). Scope outside the allow-list → refused before any call; missing credential → clean error; never logs a token.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — copy `_obo.py`'s structure (scope allow-list, injectable seam, sanitized errors), swapping the MSAL OBO call for the Google OAuth token endpoint (incremental consent / refresh-token exchange). Reuse the same error taxonomy where it maps.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(google): delegated token exchange (Lane B data, _obo.py analog)`.

### Task 10: Google-source memory tools (Gmail/Drive/Calendar → memory)

**Files:**
- Create: the Google read tools wired like `ms_calendar_list` (the OBO tool), gated on Lane-B identity + the consented Google scopes.
- Test: `packages/cli/tests/test_google_tools.py`

- [ ] **Step 1: Write the failing test** — a `google_gmail_list` (or `google_calendar_list`) tool, given a Lane-B context, calls `exchange_google` (faked) + a faked Google API and returns a `tool_result()` shape; fail-closed when the identity is not Google-family or the scope isn't consented.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — the tool(s), registered in `_mcp_server.py` alongside the Graph OBO tool, behind a `google:` config block analogous to the `graph:` block; ingestion writes into the user's `personal:google:<sub>` memory.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(google): Gmail/Drive/Calendar read tools → memory (Lane B)`.

### P3 external gate (Barna)
- [ ] Create a **Google Cloud** OAuth 2.0 client (Web) for DNA Cloud; configure the consent screen + the scopes (`gmail.readonly`, `drive.readonly`, `calendar.readonly` to start — readonly first).
- [ ] Register redirect URIs; publish the consent screen (or add test users).
- [ ] Decide the initial scope set (recommendation: **readonly** across Gmail/Drive/Calendar for v1).
- [ ] Smoke: as a Gmail user, grant incremental consent → a Google read tool ingests a real item into `personal:google:<sub>` memory.

---

## Execution notes

- **Order:** Chunk 1 (P1) ships first and is independently deployable. Chunk 2 (P2) depends on Task 5–7 landing before Task 8's mount is useful. Chunk 3 (P3) depends on P2's Lane-B identity + dual key.
- **Parity:** Task 6 (TS twin) must land with Task 5 to keep the byte-parity gate green.
- **Secrets:** never print tokens; env-var NAMES in config, VALUES as deployment secrets (mirror the `graph:`/OBO pattern).
- **Each phase = a PR** (or a small stack); mark the SDLC Story `review` on PR open, `done` on merge.
- **The external gates are Barna's** — the code lands + tests pass in CI without them; the live smoke per phase needs the corresponding Entra/WorkOS/Google config.

## Plan review

- [ ] Dispatch plan-document-reviewer on each chunk; fix + re-dispatch until approved.
- [ ] Barna reviews before execution.
