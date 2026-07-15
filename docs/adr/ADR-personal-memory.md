# ADR: Personal / Private Per-User Memory

- **Status**: Proposed
- **Date**: 2026-07-15
- **Deciders**: Barna (owner/architect) — pending review
- **Author**: claude-code
- **Tracking**: `f-personal-memory` (board `dna-development`, under epic `e-dna-portability`)
- **Relates to**: `f-ws-kinds` (Workspace + WorkspaceMembership — the `oid` identity this ADR keys on), `f-dna-hosting` (the MCP token→identity bridge), `e-dna-portability`

> **DESIGN ONLY.** No implementation, no deploy. This ADR proposes a model and a
> smallest-real-slice PoC for review. Nothing is built until Barna ratifies the
> open decisions in §9.

---

## 1. Context — the thesis, made literal at the identity level

DNA's thesis is **portable memory**: *your* memory follows *you* across every AI
client. Today DNA delivers that portability across **clients** — but bounded to a
**workspace**. The owner's own observation is the trigger for this ADR:

> His `@avanade` guest and his `@gmail` identity see the **same** memory, because
> both resolve to the **same tenant** (workspace). That is *correct* for
> collaboration — a workspace's memory is shared by its members by design.

But it exposes a missing axis. There is exactly one thing a member cannot do
today: keep a memory that is **theirs alone** — not shared with the workspace,
and carried with them when they move to a *different* workspace or a bare MCP
client. That is **personal memory**: keyed to the durable human identity (`oid`),
orthogonal to the workspace.

This is the thesis made literal at the identity level: workspace memory is
portable-across-clients-within-a-workspace; **personal memory is
portable-across-clients-AND-across-workspaces** — because its partition key is
the *person*, not the *workspace*. It is the only DNA construct whose key is the
human.

---

## 2. Current model — how memory is partitioned today (grounded in the code)

Memory in DNA is **not a subsystem** — it is the record Kinds DNA already has
(`LessonLearned`, `Research`, `Evidence`) written + recalled through the same
kernel + `RecordSearchProvider`. The five verbs
(`remember`/`recall`/`forget`/`consolidate`/`list`) live in
`packages/sdk-py/dna/memory/verbs.py`; the three faces (CLI, MCP, REST) are thin
adapters over one set of `*_impl` use-cases in
`packages/sdk-py/dna/application/runtime.py` (lines 879–1017).

**Isolation today is exactly TWO axes: `scope` + `tenant`.** Everything else on a
memory doc (`owner`, `actor`) is an **audit label**, not an isolation boundary:

- `remember`'s `owner` param defaults to the constant `"mcp"` / `"portal"` — a
  free-form string, never derived from identity
  (`_mcp_server.py:334`, `runtime.py:901`).
- `recall`'s `actor` is hardcoded `"mcp"` and used only for the `cues_history`
  reconsolidation trail (`verbs.py:212`), never for filtering.

**How `tenant` partitions storage** (the mechanism this ADR reuses):

- **Filesystem** (`adapters/filesystem/source.py`): tenant is a **path segment** —
  `tenants/<tenant>/scopes/<scope>/…`.
- **Postgres** (`adapters/sqlalchemy_/migrations.py`): tenant is a **column and
  part of the PRIMARY KEY** — `PRIMARY KEY (scope, kind, name, tenant)`; the
  empty string `''` is the **base/shared sentinel**.
- **Reads UNION base + overlay**: a request bound to tenant `X` filters
  `tenant IN ('', X)` (`source.py` `_load_view`/`query`). The composition
  resolver interleaves `(scope, X)` then `(scope, '')` per scope in the chain
  (`composition_resolver.py:357`).

**`TenantScope`** (`kernel/protocols.py:306`) has only two members: `TENANTED`
(write requires a tenant; reads filtered) and `GLOBAL` (shared; writes must NOT
pass a tenant). The write pipeline enforces this
(`write_pipeline.py:_resolve_tenant_arg`, precedence: explicit per-call `tenant`
arg > `Kernel.tenant` binding). `with_tenant(tenant)`
(`kernel/__init__.py:360`) returns a shallow-copy kernel bound to `tenant` so all
downstream reads/writes auto-stamp it.

`LessonLearned` sits in the **non-inheritable denylist**
(`resolver.py:DEFAULT_NON_INHERITABLE_KINDS_V1`) — per-scope, NOT inherited from
`_lib` — but **still honors a tenant overlay** (the denylist tail comment at
`resolver.py:447` is explicit). Memory docs have unique `rem-<hash>` names, so
the tenant "overlay" for memory is a **UNION of distinct docs**, never a
field-level merge of a shared name — an important simplification this ADR leans
on.

**Consolidation / "insights"**: `consolidate` (`verbs.py:400`) is a
deterministic decay pass — recompute Ebbinghaus retention, report/soft-forget
stale memories, `NO LLM`. It already takes `tenant` and partitions by it. The
LLM-driven scribe (the real "insight" synthesis) is deliberately **external +
optional** and not in the SDK core today.

**Identity — Model B, already shipped as DATA (`f-ws-kinds`, last commit)**:

- `Workspace` (`tenant-workspace`, GLOBAL, `_lib`): its opaque, immutable
  `workspace_id` **IS** the physical `tenant` column value on every row it owns.
- `WorkspaceMembership` (`tenant-workspace-membership`, GLOBAL, `_lib`) binds a
  **verified identity** to a workspace:
  - `identity_email` — the invite handle (mutable).
  - `identity_oid` — **the durable Entra `oid`, bound on first verified sign-in;
    the durable key — post-bind re-auth keys on THIS, never the mutable email.**
  - `identity_tid` — the Azure org, **provenance only under Model B** (`tid` is
    no longer the DNA tenant; `workspace_id` is).

**The gap this ADR fills** (the clean seam): `oid` is fully specified as data and
is **already available on the verified token** inside every MCP tool call
(`_mcp_auth.py:enforce_tenant_from_context` reads `token.claims`, which carries
`oid`) — but it is **discarded**: the bridge reads only the *tenant* claim
(`tid`), never `oid`, and no read/write path is keyed by a user. There is no
"current user distinct from current tenant" anywhere server-side yet. **Personal
memory is the first feature to plumb `oid` down into a data path.**

The nearest prior art for "a second orthogonal axis read off the same verified
token with a defined default" is the **tier/plan** axis in `_mcp_auth.py`
(`resolve_tier`): a missing tenant fails **closed**, a missing tier falls to the
**Free floor** — a deliberate, defined default rather than an ambiguous null.
This ADR mirrors that discipline.

---

## 3. The personal-memory model

### 3.1 Core decision — a reserved partition namespace, NOT a new column

Personal memory is modeled as a **reserved value-namespace inside the EXISTING
`tenant` partition** — the string `personal:<oid>` — surfaced through a new
**public selector** on the memory verbs. Concretely:

- A new selector `MemoryScope ∈ { workspace, personal }` on every memory verb.
- `workspace` → the current behavior: `tenant = <resolved workspace tenant>`.
- `personal` → `tenant = "personal:<oid>"`, where **`<oid>` is resolved
  SERVER-SIDE from the verified identity** — never a caller-supplied param.

The public surface stays honest (**workspace vs personal**); the storage reuses
the tenant partition. This is deliberately the **cheapest correct** shape.

**Why reuse the tenant column instead of adding an `owner_oid` axis?**

| | Reserved `personal:<oid>` tenant namespace (chosen) | New `owner_oid` partition column/segment (rejected) |
|---|---|---|
| Schema change | **Zero** — tenant column/path already exists | Migration on **every** doc table + FS path; breaks Py↔TS parity |
| Blast radius | Only the memory verbs learn a selector | Every Kind grows a dimension it doesn't need |
| Privacy | **By construction** (see §7) — the base+overlay predicate `tenant IN ('', X)` provably cannot select a `personal:*` partition from a workspace request | Requires new filter logic everywhere, new places to get it wrong |
| Portability | `personal:<oid>` is the same partition in every workspace + client | Same, but at far higher cost |
| Composition | Rides the existing resolver / `with_tenant` / write-guard unchanged | New composition rules |

Adding a whole new partition column to serve **one** Kind family is overkill; the
tenant column is already a generic partition string, and reusing it makes the
privacy invariant fall out of the machinery that already exists.

### 3.2 Storage layout (no migration)

Personal memory lands in the SAME stores, at the reserved namespace:

- **FS**: `tenants/personal:<oid>/scopes/<scope>/…`
- **PG**: rows with `tenant = "personal:<oid>"` — a first-class value in the
  existing `(scope, kind, name, tenant)` primary key.

Physically **disjoint** from workspace rows (`tenant = <workspace_id>`) and from
base (`tenant = ''`).

### 3.3 The write/read paths (reuse `with_tenant`)

- **Write** (`remember` personal): resolve `oid` → `write_kernel =
  kernel.with_tenant("personal:<oid>")` → the existing bi-temporal write guard +
  hooks fire unchanged. `LessonLearned` is permissive/overlay-honoring, so no
  `TenantScope` conflict.
- **Read** (`recall`/`list` personal): `kernel.search / query` bound to
  `tenant = "personal:<oid>"` → the union predicate is `tenant IN ('',
  "personal:<oid>")` → returns the user's personal memory **plus** the `_lib`
  base defaults, and **nothing** from any workspace (see §5, §7).

### 3.4 Reserve the namespace at the validator (privacy hardening)

Add the `personal:` scheme (and any chosen sigil) to the reserved-tenant set in
`validate_tenant_slug` (`kernel/protocols.py:391`, currently reserves
`{_global, _legacy, _system, ""}`). Consequence: **no `Workspace` can ever be
created or renamed with a `personal:`-prefixed `workspace_id`**, so no workspace
can be made to *shadow* or *alias* a personal partition. Since a real
`workspace_id` is an Azure `tid` (a GUID) and `personal:` is not a legal slug,
collision is impossible by construction — this just makes it enforced, not
incidental.

---

## 4. Insights — personal consolidation runs over the personal partition only

`consolidate` already takes `tenant`, so **personal consolidation is
`consolidate` bound to `tenant = "personal:<oid>"`** — it recomputes decay and
reports/soft-forgets stale memories over the personal partition **only**, never
touching workspace memory. Zero new partitioning logic.

Personal **insights** (the LLM scribe that synthesizes "your own patterns" —
"you keep hitting this class of bug", "you prefer X over Y") is the same external
+ optional scribe DNA already defers, now pointed at the personal partition and
keyed per `oid`. The engine partitions by the same tenant key it already uses.
**Personal insights are DEFERRED from the PoC** (see §8) — the *partitioning* is
in scope; the *LLM synthesis* is not.

Because workspace and personal are disjoint partitions, workspace insights and
personal insights **never cross-contaminate**: a workspace-scoped consolidate
never sees personal memories, and vice-versa.

---

## 5. Portability — how the resolver picks personal-vs-workspace per request

The partition key for personal memory is the **identity**, not the workspace, so
the resolver's choice is trivial and workspace-independent:

```
resolve_memory_tenant(request):
    if request.memory_scope == "personal":
        oid = verified_oid(request)          # from token claim / DNA_PERSONAL_ID
        if oid is None: FAIL-CLOSED           # personal requires an identity
        return f"personal:{oid}"
    else:  # workspace (default)
        return resolve_workspace_tenant(request)   # current behavior (tid → workspace)
```

The consequence is the whole point:

- In **workspace A**, personal target → `personal:<oid>`.
- In **workspace B**, personal target → `personal:<oid>` — **the same partition**.
- In a **bare MCP client** (no workspace at all), personal target →
  `personal:<oid>` — **still the same partition**.

Workspace context is **irrelevant** to which personal partition you reach —
because the key is `oid`. That is the literal, storage-level realization of "your
memory follows *you*". Over MCP the `oid` rides the verified token
(`token.claims["oid"]`, already in hand at
`enforce_tenant_from_context`); across clients the token differs but the `oid`
claim is the same durable Entra object id — so the partition is identical.

---

## 6. Surfaces — targeting personal vs workspace (CLI · MCP · Portal)

One core (`*_impl` in `runtime.py`) learns the `memory_scope` selector + the
oid-resolution seam; all three faces inherit it.

**Default**: an **explicit selector with `workspace` as the default** (non-breaking
— every current call keeps its behavior). Flagged as an open decision (§9.2).

- **CLI** (`dna memory …`): add `--personal` (sugar for `--memory-scope
  personal`). Offline/stdio has no verified token, so the CLI resolves `oid` from
  a new `DNA_PERSONAL_ID` env (single-user local identity). Without it,
  `--personal` fails closed with a clear message.
  ```
  dna memory remember "I always misread cron day-of-week" --personal   # private to me
  dna memory recall  "cron" --personal
  dna memory remember "our deploy runbook step 3" --area Feature/deploy  # workspace (default)
  ```
- **MCP**: add a `personal: bool = False` param to `recall`/`remember`/
  `consolidate`/`list_memories`/`forget`. A new `enforce_oid_from_context()`
  (mirror of `enforce_tenant_from_context`) reads `token.claims["oid"]`. On
  authenticated HTTP with no `oid` claim → fail closed. On stdio → fall back to
  `DNA_PERSONAL_ID` or reject.
- **Portal** (external repo — the Memory tab): two **clearly separated,
  honestly-labeled** sections:
  - **"Personal — only you"** (`personal:<oid>`), with a lock affordance.
  - **"Workspace — shared with N members"** (`<workspace_id>`).
  A "remember" action offers an explicit **"Keep private" vs "Share to
  workspace"** choice. Never blend the two lists. **Portal UI is DEFERRED** (§8)
  — it also depends on the REST token→identity bridge (§9, the `_rest_api.py`
  `TODO(hosted)`).

---

## 7. Privacy invariant (enforced, fail-closed)

> **INV-PERSONAL:** A personal memory written by identity **X** (`oid=X`) is
> **NEVER** readable by identity **Y** (`oid≠X`), nor by **ANY** workspace-scoped
> query — including a workspace **owner's or admin's**. There is no override.
> Fail-closed.

This holds by **four independent, layered** mechanisms (defense in depth — any
one alone would suffice for the common case; together they close the edges):

1. **Server-derived oid.** The `oid` is ALWAYS resolved from the verified token
   (or `DNA_PERSONAL_ID` locally), **never** from a request param. User Y has no
   way to *name* X's partition — the only personal partition a request can reach
   is the caller's own.
2. **Physically disjoint partition + union predicate.** A workspace request
   filters `tenant IN ('', <workspace_id>)`. This predicate **provably cannot**
   return a `personal:*` row — there is no code path where a workspace query's
   tenant set includes a `personal:` value. Privacy by construction, not by a
   check that could be forgotten.
3. **Reserved namespace at the validator.** `validate_tenant_slug` rejects
   `personal:`-prefixed workspace ids (§3.4), so no workspace can be created to
   *alias* a personal partition and back-door it via the overlay union.
4. **Reject raw personal-tenant override.** The memory surfaces (and the
   `_guard`/`resolve_tenant` seam) **reject any caller-supplied `tenant` whose
   value matches the reserved `personal:` scheme** unless it equals the
   server-derived `personal:<own-oid>`. Personal partitions are reachable ONLY
   through the `memory_scope=personal` selector, which derives the oid
   server-side — never through the raw `tenant` param. This closes the "pass
   `tenant=personal:<victim-oid>` directly" attack.

**Guard test idea** (`test_personal_memory_privacy.py`, Py + TS twin):

- `remember(personal, oid=A)` → `recall(workspace, owner)` returns **0 hits**;
  `list(workspace)` never shows it.
- `recall(personal, oid=B)` returns **0 hits**; `recall(personal, oid=A)`
  returns the hit.
- Passing `tenant="personal:<A>"` directly as a raw override while
  authenticated as B → **denied** (`CrossTenantError`).
- `validate_tenant_slug("personal:whatever")` → **rejected** (cannot name a
  workspace that).
- `consolidate(personal, oid=A)` evaluates only A's partition; a
  `consolidate(workspace)` never touches `personal:*`.

---

## 8. PoC scope — the smallest real slice

**In scope (the vertical slice that proves the model + the invariant):**

1. The reserved `personal:<oid>` partition + the oid-resolution seam
   (`enforce_oid_from_context` for MCP; `DNA_PERSONAL_ID` for CLI/stdio).
2. `remember` + `recall` targeting **personal**, on the surfaces where an
   identity exists today: **MCP** (verified `oid`) and **CLI** (env `oid`).
3. The **privacy invariant (§7)** + its guard test — all four checks.
4. The namespace reservation in `validate_tenant_slug` + the raw-override
   rejection.
5. Py + TS parity for the core seam.

**Deferred (tracked as separate stories, NOT in the PoC):**

- **Personal insights consolidation** (the LLM scribe over the personal
  partition) — partitioning is in the PoC; synthesis is later.
- **Portal Memory-tab UI** (two-section personal/workspace view) — external repo
  + blocked on the REST token→identity bridge.
- **REST personal parity** — `_rest_api.py` still takes `tenant` as a forgeable
  query param and has no verified identity (`TODO(hosted)`); personal-over-REST
  must wait for that bridge (it CANNOT be safe until then — a forgeable tenant
  param would break INV-PERSONAL).
- `forget` / `list` / `consolidate` personal wiring on all faces (trivial once
  the seam lands, but out of the proving slice).

---

## 9. Open decisions for Barna

1. **Key: `oid` alone, or `oid` + client?**
   Recommend **`oid` alone**. Keying on `oid+client` would fragment your personal
   memory per AI tool — the opposite of the portability thesis. One identity, one
   personal memory, every client.
2. **Default target: personal or workspace?**
   Recommend **explicit selector, `workspace` default** for the PoC — zero
   behavior change for every existing call; personal is strictly additive. (A
   later "personal-first" default is a product call once the surfaces exist.)
3. **Storage: reuse the tenant partition, or a separate personal store?**
   Recommend **reuse** (`personal:<oid>` namespace, zero migration, privacy by
   construction). A separate physical store buys stronger isolation-at-rest but
   costs a whole new adapter path + sync story — only justified if a compliance
   requirement demands physical separation of personal data. Flagging it because
   "personal data in its own store" is a defensible privacy posture.
4. **`_lib` interaction: does personal recall UNION the base `''` `_lib`
   defaults, or be pure-personal?**
   Recommend **union base** — the base carries shared *platform* lessons
   (harmless, useful), and personal is additive over base, never over workspace.
   If you want personal to be hermetic (nothing but your own), we special-case
   the personal read to skip the `''` union. (Cheap either way.)
5. **stdio / CLI identity — `DNA_PERSONAL_ID`?**
   No verified `oid` exists offline. Recommend `DNA_PERSONAL_ID` env for the
   local single-user case, and **deny personal on authenticated HTTP that
   carries no `oid` claim** (fail-closed, matching the tier/tenant discipline).
   Question for you: should a purely-local (no-token) user get personal memory at
   all, or is personal a hosted-only feature?

---

## 10. Rough size

**Small-to-medium — one focused SDK PR for the core + two faces, plus a TS
parity mirror.**

- Core seam (`runtime.py` + `verbs.py`): thread `memory_scope`, add
  `resolve_memory_tenant` + oid resolution. ~small.
- MCP face (`_mcp_server.py` + `enforce_oid_from_context` in `_mcp_auth.py`):
  add the `personal` param + the oid read. ~small.
- CLI face (`memory_cmd.py`): add `--personal` + `DNA_PERSONAL_ID`. ~small.
- Validator reservation + raw-override rejection: ~tiny.
- Guard test (Py + TS): ~small-medium (the four checks).

Estimate **~300–500 LOC + tests** for the PoC slice. Personal insights, portal
UI, and REST parity are **separate follow-on stories**, each its own PR.

---

## 11. The single strongest argument

**Personal memory keyed on `oid` is the only DNA construct whose partition key
is the human, not the workspace — so it is literally the *same* partition in
workspace A, workspace B, and a bare MCP client.** Workspace memory is portable
across clients but *bounded to a workspace*; personal memory is portable across
clients **and** across workspaces, because it follows the identity itself. That
is DNA's portability thesis made physical at the storage layer — "your memory
follows *you*" stops being a slogan and becomes a primary-key value.
