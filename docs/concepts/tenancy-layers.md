# Tenancy and layers

DNA separates *what a scope declares* from *who overrides it and how*. Two
orthogonal mechanisms do that work: **layers** (overlays that override a
base) and **tenants** (a first-class dimension for multi-tenant deployments).
A [`LayerPolicy`](#layerpolicy-which-layers-may-override-which-kinds) governs
which overrides are allowed.

This page is the conceptual overview. The mechanics of *storing* overlays
live in the source adapters — see [How to write a source
adapter](../guides/write-a-source-adapter.md).

## Scopes and the shared library

A **scope** is a directory of manifests — the unit you load with
`Kernel.quick(scope)`. Scopes are not islands: every scope can inherit shared
documents from a sibling `.dna/_lib/` **library scope**. Put an agent, skill
or theme in `_lib` and every scope sees it, unless the scope overrides it.

This is the base of the override model: `_lib` provides shared defaults; a
scope specialises them.

## Layers — overlays over a base

A **layer** is an overlay: a set of documents that override the base for some
dimension without editing the base. The base stays the shared product; a
layer carries only the *diffs*.

The canonical use is a **tenant overlay** — a per-tenant set of overrides
composed on top of the shared base at read time. The adapter resolves a
`load_layer(tenant)` view that merges the tenant's overrides over the base;
the base document is never mutated. A tenant that overrides nothing sees the
base unchanged.

The merge is by `(kind, name)` — an overlay document shadows its base twin,
everything else passes through:

```mermaid
flowchart LR
    subgraph base ["base scope"]
        B1["Agent greeter"]
        B2["Skill review"]
    end
    subgraph overlay ["tenant overlay"]
        O1["Agent greeter (override)"]
    end
    B1 --> M{"merge by<br/>(kind, name)"}
    B2 --> M
    O1 -->|shadows base| M
    M --> V["tenant view<br/>greeter (overlay) + review (base)"]
```

## Tenants — a first-class dimension

Tenancy is **orthogonal to layers**, not a special case of them. DNA models
it with its own Kinds under the `tenant/v1` namespace:

| Kind | apiVersion | What it is |
|---|---|---|
| `Tenant` | `github.com/ruinosus/dna/tenant/v1` | A first-class tenant identity |
| `TenantMembership` | `github.com/ruinosus/dna/tenant/v1` | Who belongs to which tenant |
| `Workspace` | `github.com/ruinosus/dna/tenant/v1` | A named, collaborative tenancy space (alias `tenant-workspace`) |
| `WorkspaceMembership` | `github.com/ruinosus/dna/tenant/v1` | An identity's role in a `Workspace` (alias `tenant-workspace-membership`) |
| `KindNamespace` | `github.com/ruinosus/dna/tenant/v1` | Which workspace owns which `apiVersion` namespace (alias `tenant-kind-namespace`) |
| `WorkspaceScopeGrant` | `github.com/ruinosus/dna/tenant/v1` | One extra scope a `Workspace` may read (alias `tenant-workspace-scope-grant`) |

Because tenant is a kernel dimension rather than a naming convention, a
tenant overlay for one scope does not leak into another — the base for a
scope belongs to that scope, and each tenant sees the base plus its own
diffs.

## Reaching a second scope — `WorkspaceScopeGrant`

A resolved workspace reads exactly one scope: its own. That is the right
default and it stays the default. What it made unreachable is a legitimate
case — one person whose hosted door binds them to workspace A while board B is
also theirs — and the only lever used to be a process-wide environment variable
that applies to the *credential*, not to the workspace.

A **`WorkspaceScopeGrant`** is that permission as **data**: one row per
`(workspace, scope)` pair, in the `_lib` scope alongside `Workspace` and
`WorkspaceMembership`, carrying a reason, an author and a timestamp.

```yaml
apiVersion: github.com/ruinosus/dna/tenant/v1
kind: WorkspaceScopeGrant
metadata:
  name: ws-acme--research-archive
spec:
  workspace_id: ws-acme
  scope: research-archive
  status: active          # `revoked` keeps the row and its history
  access: read            # read-only; widening it is a schema change
  reason: the shared research archive both teams cite
  granted_by: ana@example.com
```

Three properties are load-bearing:

* **A read grant is a read grant.** `access` is enforced, not merely written
  down: the scope binder carries a read/write axis and asks the row what it
  permits, so the grant that opens a second scope for *reading* refuses a
  *write* to it and names the level the row records. The enum has one member on
  purpose — a cross-workspace write is a different decision from a
  cross-workspace read and must not arrive as a value nobody noticed.
* **Nothing is derived.** The scope binder checks *membership* against the
  rows — no prefix rule, no "same account" inference, and deliberately **no
  wildcard**. A leak is therefore always a row somebody wrote, which can be
  listed, diffed and revoked; not a rule nobody can see. (The `*` sentinel that
  `DNA_TOKEN_SCOPES` honours for a *workspace-less* service credential is
  refused here by name: in a data row, one typo would grant every scope in the
  deployment.)
* **No grant means today's behavior, exactly.** A deployment that writes no
  rows is unchanged.

Revoking flips `status` to `revoked` rather than deleting the document — the
evidence that access once existed is the half of an audit trail that matters
after an incident.

## Workspaces — collaborative, identity-based tenancy

A **`Workspace`** is a named tenancy space that is *decoupled* from any
external identity-provider tenant id. Where a `Tenant` keys the dimension to a
single organization, a `Workspace` is a first-class DNA space that people from
**different organizations** can share. The tenancy key the kernel resolves is
the workspace id — not the caller's home-org id.

A **`WorkspaceMembership`** maps a *verified identity* (its stable subject id
plus email) to a `Workspace` and a role. Membership — never the caller's
org id — decides what a request may read or write: every read/write is served
only if the authenticated identity holds an *active* membership in that
workspace, resolved before the source is touched. An active grant may exist
*before* its holder ever signs in — this is exactly how both the zero-migration
founder seed and a **cross-organization invite** work: the grant is created
*unbound* (email only) and binds to the holder's stable `oid` on their first
verified sign-in (see [Invites](#invites-the-cross-org-join) below).

The two Kinds mirror `Tenant` / `TenantMembership`, but keyed on a
portable workspace id and a cross-organization identity rather than a single
org. A `Workspace` whose id equals a pre-existing tenant id inherits all of
that tenant's data with **zero migration** — the workspace simply becomes the
new name for the same rows.

### How the workspace is resolved (identity → membership)

The resolution is a pure, transport-agnostic policy (`dna.tenancy.resolution`,
with a 1:1 TypeScript twin — both driven by shared parity fixtures):

1. A verified token is distilled to an **identity** — the durable subject, the
   verified `email` (from `email` / `preferred_username` / `upn`), and the `tid`
   as *provenance only*. The `tid` is deliberately **not** the tenant.
   **Which claim carries the durable subject is per provider**
   (`dna.tenancy.identity_claim_key`), read from the provider stamp the verifier
   writes: Entra keys on `oid`, a consumer-lane IdP (WorkOS, Clerk, Auth0,
   Google) on its `sub` — the same providers, and the same durability claim,
   that the billing person lane rests on. A token whose provider is unstamped or
   unknown keeps `oid`, so a single-lane deployment is unaffected. Entra is
   deliberately *not* `sub`-keyed: its `sub` is pairwise (per user *per app*).
2. The identity is matched against the `WorkspaceMembership` grants. An **active**
   grant matches on the durable subject once bound; while still unbound (a freshly
   seeded owner, or a not-yet-accepted invite that is already active) it matches
   on the **verified email**. A `pending` invite authorizes nothing.
3. The resolved workspace id is the tenancy key. A caller may *select* among the
   workspaces it belongs to (e.g. a per-workspace MCP URL), but the selector is
   re-verified against membership — a workspace the identity is not an active
   member of is denied. With no membership at all, the request is denied
   (fail-closed).

At the MCP edge this replaces the older "org id is the tenant" step. A source
that has **no `WorkspaceMembership` grants at all** has not opted into workspaces
(the OSS / self-host case) and keeps its prior single-tenant behaviour unchanged;
workspace resolution engages only once grants exist. Beneath the resolver, the
physical `(scope, tenant = workspace_id)` key gives defence in depth: a resolved
workspace defaults to — and may name — only its own scope, so even a bug upstream
cannot read another workspace's rows.

### Opting out of the boundary (`DNA_WORKSPACE_ENFORCEMENT`)

Fail-closed is the right default, and for a **single-operator deployment** it is
also a door with no key: the one person the deployment serves is denied the whole
tenant-scoped surface — shared memory, the registry, the SDLC board — until they
grant themselves a membership. `DNA_WORKSPACE_ENFORCEMENT` is the explicit way
out.

| Value | Effect |
|---|---|
| *(unset — the default)* | Enforce. Everything above, unchanged. |
| `enforce` | The same thing, said out loud. |
| `open` | The membership boundary stops **denying**. |
| anything else | Enforce, and the door logs that it ignored the value. |

**It is not a boolean.** `0`, `false`, `off`, `1`, `true` and every misspelling
all *enforce* — exactly one literal opens the boundary, because "`=0`" reads as
"enforcement off" to one operator and "not open" to another, and only one of
those misreadings is safe.

With `open`, resolution still runs — only its denial is disarmed. An identity
that unambiguously belongs to a workspace still resolves to it (and to its
account's plan), so nothing has to be flipped back when memberships appear. Three
denials become a fall-through to the caller's *unverified* workspace selector:
holding no active membership at all, naming a workspace you are not a member of,
and belonging to several while naming none.

Everything else stands. The token is still verified, the durable subject is still
derived per provider, personal memory still fails closed on a missing identity,
the scope binding still applies, and **every call is still metered**: a request
that resolves no workspace meters against the caller's own verified identity
(the reserved `personal:` partition), never a shared bucket. A token carrying no
durable subject cannot be attributed to anyone and is therefore still denied —
pooling those calls would count one identity's usage against another's.

Both doors share the switch — the MCP bridge and the REST `--auth config`
middleware — so an operator never gets one face working and the other refusing.
A door running with the boundary open says so at boot, at `WARNING`. Restoring
the boundary is unsetting the variable; nothing else changes.

### Billing keys on the account, not the workspace

**The subscription belongs to the billing account.** An
[`PlanBinding`](../reference/kinds/record.md#planbinding) (`cloud-plan-binding`)
maps an `account_id` to its current `PricingPlan`, and that one assignment covers *every*
workspace the account owns — creating a second workspace is not a second charge.
DNA Cloud's Stripe webhook writes it (`PUT /v1/account-plan`); the MCP quota guard
resolves **workspace → `account_id` → plan**, taking the account from the
`Workspace` doc the request already keys on.

Access and billing are therefore two different axes, deliberately. Access is
resolved by *membership* (you see a workspace because you were granted it);
billing is resolved by *ownership* (a workspace is paid for by the account that
created it). Collapsing them is what made the previous per-workspace model
unworkable: enumerating "the account's workspaces" through membership sweeps in
every workspace somebody else founded and invited you into, and paying for those
would hand a tier to an account that never bought one.

`Workspace.account_id` is stamped once, at creation, from the caller's verified
claims (`dna.tenancy.account_id_from_claims`). **An account is an organization or
a person, and both can be sold to:**

* **organization** — whatever the IdP block's `tenant_claim` names (Entra `tid`,
  WorkOS/Clerk/Auth0 `org_id`, Google Workspace `hd`);
* **person** — when the sign-in belongs to no organization (the consumer lane),
  the identity's durable `sub`. Before this, such a sign-in resolved to no
  account at all: permanent Free with no way to buy, which is not a plan for a
  product whose wedge is an individual story.

The id is **namespaced by provider and by account kind** — `entra-org:<tid>`,
`workos-org:<org_id>`, `workos-user:<sub>`, and the same `-org`/`-user` pair for
`clerk`, `auth0` and `google`; `tenant:<value>` when the provider cannot be
named. This buys exactly two things: a `tid` and a `sub` that happen to share a
literal value can never be the same account, and an id read in a Stripe record or
a support ticket says what kind of account it is. **The prefix is not a parsing
surface** — nothing branches on it to decide authorization or entitlement; the
authorization input is the verified claim, never a substring of an id DNA minted.

Entra has no person lane on purpose: its `sub` is *pairwise* (unique per user
*per application*), so the same human presents a different `sub` to a different
app registration. Its durable id is `oid`, but making a personal Microsoft
account billable is a separate product decision — so the shared-MSA tenant
(`9188040d-…`, which *every* personal Microsoft account presents as its `tid`)
stays refused outright rather than becoming one giant shared account.

A workspace with no resolvable account falls to the **Free floor**: fail-closed,
never another account's tier. There is deliberately no rule that treats an
account-less workspace as its own account — that would resurrect per-workspace
billing as a silent default.

(The per-workspace `PUT /v1/workspace-plan` route and its `WorkspacePlan` Kind
were retired; the Kind remains a write-block tombstone so a stale caller fails
loudly instead of writing docs nothing reads.)

### Picking a workspace by URL (`/w/<id>/mcp`)

An MCP client (VS Code) connects with only a bearer token — there is no
interactive picker. It selects its workspace **by URL**: the per-workspace
endpoint `https://…/w/<workspace-id>/mcp` names the workspace in the path, while
the bare `…/mcp` falls back to the identity's sole / default membership. The
path is only ever a *selector*: the auth bridge reads `<workspace-id>` from it and
**re-verifies** it against membership (a non-member is denied), so the workspace
is a named, verified claim — never trusted blind. The REST face has the mirror
mechanism: under `--auth config` a verified bearer JWT is resolved to a workspace
by membership, and that workspace **overwrites** the request's `tenant` argument
(a caller can no longer forge it).

## Invites — the cross-org join

The point of workspaces is collaboration *across* organizations. A workspace
Owner or Admin invites a person from **any** org **by email**, and that person's
first verified sign-in joins them — the GitHub/Slack shape.

1. **Invite.** An Owner/Admin creates a `WorkspaceMembership` with `status:
   pending`, `identity_email` set to the invited address, and `identity_oid`
   *null* — no account has to exist yet. Only an Owner/Admin of *that* workspace
   may invite, and only an Owner may invite another Owner.
2. **Accept (bind on first sign-in).** The invitee authenticates from their own
   org. The server matches the token's **verified** email claim against the
   pending invite, **binds** the durable `oid` (recording the `tid` as
   provenance), and flips `status: active`. Email is the *handle*; `oid` is the
   *key*.

The accept step is impersonation-proof by construction:

- Matching is only ever on a **verified** email claim (Entra's
  `email`+`email_verified`, or the verified `preferred_username`/`upn` UPN) — never
  a caller-supplied field. An unverified email accepts nothing (fail-closed).
- The bind key is the durable subject (`oid` for Entra, `sub` for a consumer-lane
  IdP — see step 1 above). Once a grant is bound, it matches *only* on that
  value — so a different identity that later controls the same email can **not**
  hijack the membership. A token carrying no durable subject binds nothing. The
  key is derived in one place in the core, so the id written when a workspace is
  *created* is byte-identical to the one the MCP and REST doors later derive from
  the token.
- The whole decision is the pure `dna.tenancy.invites` policy (with a 1:1
  TypeScript twin, driven by shared parity fixtures), so both runtimes agree.

REST endpoints expose the flow: `POST /v1/workspaces/{id}/invites` (Owner/Admin),
`GET /v1/workspaces/{id}/members` (Owner/Admin), and `POST /v1/workspaces/accept`
(the verified invitee). The accept route is exempt from the workspace bind — an
invitee is still `pending` and by definition holds no active membership yet.

### Shipped, and what's still roadmap

The Model-B workspace stack above is **shipped and live** end to end:
`Workspace` + `WorkspaceMembership` and the zero-migration seed (F1);
membership-decides-access resolution (F2); `PlanBinding` billing (F4); and the
cross-org invite flow plus `/w/<id>/mcp` URL selection (F3). Every claim on this
page traces to merged code in the DNA SDK.

The one piece still **on the roadmap** is the end-user *console* for it: the DNA
Cloud **portal invite UI** (the buttons that call `POST /v1/workspaces/{id}/invites`
and surface the member list) lives in the hosted product, not this SDK. The DNA
side — the Kinds, the resolution/invite policies, the REST endpoints — is done;
the portal screens that drive them are tracked separately in DNA Cloud.

## LayerPolicy — which layers may override which Kinds

Not every Kind should be overridable by every layer. A **`LayerPolicy`**
(`github.com/ruinosus/dna/policy/v1 · LayerPolicy`) declares *which layers may
override which Kinds* — the guardrail on the override model. It is data, like
everything else: a policy document, validated and versioned.

## `overlayable_fields` — which *fields* of a Kind a layer may change

`LayerPolicy` answers *whether* a layer may override a Kind. A Kind can go one
level finer and declare *which of its spec fields* a layer may change, right
next to `ui_schema` in its `.kind.yaml` descriptor:

```yaml
spec:
  target_kind: Agent
  # …
  overlayable_fields: [instruction, model]
```

The two compose by **conjunction** and neither widens the other: a layer write
must satisfy the operator's `LayerPolicy` *and* the Kind author's field list. A
write that changes any other top-level spec key is refused with
`LayerPolicyViolationError`.

Three things worth knowing before you reach for it:

- **Omitting it is the default and means *unrestricted*** — every spec field is
  overlayable. Only declare the key when a field genuinely must not move; a
  schema-driven editor renders exactly the fields you list as editable, so an
  over-eager list is a form nobody can fill in.
- **Writing a listed-out field back at its inherited value is not a change**,
  so submitting a whole effective spec (read-only fields included) stays a
  no-op rather than an error.
- **It gates authoring, not composition.** The check runs on the write path.
  Overlay documents already stored are merged as written — enforcing the list
  on merge would retroactively rewrite content nobody edited.

## Namespaces — who may declare a Kind

A Kind's identity is the pair `(apiVersion, kind)`: both halves are the
registry key. So when a workspace authors its own Kind, the `apiVersion` is
what keeps it apart from everyone else's — two workspaces declaring `Deal`
under one `apiVersion` are *the same Kind*, and the second one's documents
would be validated against the first one's schema.

DNA therefore gives a workspace its own `apiVersion` **namespace**, and the
namespace is a **claimed, owned name** — `acme.example/v1`, not
`tenant.<workspace-id>/v1`. The distinction matters because the `apiVersion`
participates in the identity of every document: baking a database id into it
would mean renaming, migrating or consolidating a workspace changes the
identity of everything that workspace owns. A namespace is what every API
versioning scheme already uses — the organisation's name, not its row id.

A **`KindNamespace`** document records one claim: a namespace and the
`workspace_id` that owns it. Three rules follow from it, all enforced on the
write path (the same boundary as `LayerPolicy`, so one gate governs both):

- **A claim is a prefix.** Claiming `acme.example` covers `acme.example/v1`,
  `acme.example/v2` and `acme.example/crm/v1`. The most specific claim wins, so
  delegating a sub-namespace is a longer claim. One workspace may own several
  namespaces; two workspaces may never own one — two conflicting claims refuse
  every write under that namespace rather than picking a winner.
- **Reserved namespaces are not a list.** A namespace is reserved when a Kind
  registered *from code* already lives in it — so `github.com/ruinosus/dna/**`
  and every standard DNA consumes byte-faithful under its owner's name
  (`agents.md`, `agentskills.io`, `soulspec.org`, `presidio`, `mif-spec.dev`)
  are protected the day their Kind registers. Nothing to maintain, nothing to
  drift. Per-scope Kinds reserve nothing, or the first Kind a workspace declared
  would lock its own owner out of the second.
- **Unclaimed is refused, not first-come.** A workspace that has claimed
  nothing cannot declare a Kind anywhere. Who owns a name stays a recorded
  decision instead of a race between writers.

The check applies to *declaring* a Kind (writing a `KindDefinition`), never to
using one — writing a `Story` under the `sdlc` namespace is ordinary traffic. A
refusal is a `NamespaceOwnershipError`, a `LayerPolicyViolationError` (HTTP
403) that names which namespace, which owner and why.

`KindNamespace` is GLOBAL, `_lib`-resident and non-overlayable: the claim
registry sits *above* any single workspace, so no layer may fork it and the
generic write-any-document path refuses it. Claiming is a provisioning act,
like minting a workspace id.

## The maxim: inheritable ⇒ never per-tenant-only

A design invariant worth stating plainly: a Kind that is an **inheritable
default** — one a scope inherits from `_lib` and may override — must be
writable at the shared base. Reading such a Kind promises a base default that
overlays can specialise; a storage mode that forbids writing that base would
contradict the read contract. So inheritable Kinds use a **permissive** or
**global** tenancy model, never a strictly per-tenant one. Per-tenant-only
storage is reserved for data that has *no* shared default (audit logs, per-user
profiles, and the like).

## Where to go next

- [The microkernel and its five ports](microkernel-ports.md) — where source
  adapters (and their layer support) plug in.
- [How to write a source adapter](../guides/write-a-source-adapter.md) — the
  per-tenant overlay capability in the port contract.
- [Kinds](kinds.md) — the identity model these dimensions apply to.
