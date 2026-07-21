/**
 * `dna-client` — the official TypeScript client for the **DNA REST read-API**
 * (`dna api serve`).
 *
 * The client is GENERATED from the API's OpenAPI document (`docs/openapi.json`,
 * dumped from the FastAPI app by `scripts/dump_openapi.py`): the path/param/body
 * types in `./schema.ts` are produced by `openapi-typescript`, and this module
 * is a thin, typed wrapper over `openapi-fetch` bound to those types. Because
 * both this client and its Python twin (`packages/client-py`) are generated from
 * the SAME spec, they stay semantically in sync (spec-parity, not byte-parity),
 * and a drift test re-dumps the spec and fails if the API changed without
 * regenerating.
 *
 * FULL coverage: the named methods cover EVERY operation in the spec — the
 * `/v1/*` reads AND the writes (memory remember/delete, insight state, project
 * + workspace membership, workspace/project creation, invites, account-plan).
 * {@link DnaClient.raw}, the underlying `openapi-fetch` client, is still exposed
 * for direct access with the same generated types, but it is no longer the only
 * way to reach a write. Coverage is enforced by a test that reads the spec and
 * fails when an operation has no named method (`tests/client.test.ts`), mirroring
 * the Python twin's `test_openapi_drift.py`.
 *
 * RETURN TYPES: each `/v1/*` handler declares a Pydantic `response_model`, so the
 * OpenAPI response schemas — and these methods' return types, inferred through
 * `openapi-fetch` from the generated `schema.ts` — carry the real payload shape
 * (e.g. `listAgents()` → `{ scope, agents: { name, kind, description }[] }`).
 * Genuinely dynamic payloads stay loose by design: a memory recall `hit`, a
 * Document `spec`, an SDLC work-item's verbatim AC/DoD/timeline lists, and
 * status→count maps are typed as open records/`unknown`.
 */
import createClient, { type Client } from "openapi-fetch";
import type { paths } from "./schema.js";

export type { paths } from "./schema.js";

/** Configuration for a {@link DnaClient}. */
export interface DnaClientOptions {
  /** Base URL of a running DNA REST read-API, e.g. `http://127.0.0.1:8080`. */
  baseUrl: string;
  /**
   * Optional bearer token. When the API runs with `--auth token`/`--auth
   * config`, this is sent as `Authorization: Bearer <token>` on every request.
   */
  token?: string;
  /**
   * Optional default `tenant` query param applied to every call that accepts
   * one (a per-call `tenant` overrides it). Under `--auth config` the server
   * OVERWRITES `tenant` from the verified token's workspace membership, so this
   * is a convenience for `--auth none`/`--auth token` deployments.
   */
  tenant?: string;
  /** Optional default `scope` query param applied to every call that accepts one. */
  scope?: string;
  /** Custom `fetch` implementation (tests / non-browser runtimes). */
  fetch?: typeof fetch;
}

/** Thrown when the API responds with a non-2xx status. */
export class DnaApiError extends Error {
  constructor(
    readonly status: number,
    /** The API's `{detail: ...}` payload (or the raw error body). */
    readonly detail: unknown,
  ) {
    const message =
      detail && typeof detail === "object" && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `DNA REST API error (HTTP ${status})`;
    super(message);
    this.name = "DnaApiError";
  }
}

/** Query params shared by (almost) every read endpoint. */
export interface ScopeTenant {
  scope?: string;
  tenant?: string;
}

/**
 * A typed, read-first client for the DNA REST read-API.
 *
 * ```ts
 * const dna = new DnaClient({ baseUrl: "http://127.0.0.1:8080", token: "…" });
 * const { agents } = await dna.listAgents({ scope: "dna-development" });
 * const hits = await dna.searchMemories({ q: "tenancy invariant", k: 3 });
 * ```
 */
export class DnaClient {
  /** The underlying `openapi-fetch` client — the FULL typed surface (incl. writes). */
  readonly raw: Client<paths>;
  private readonly defaults: ScopeTenant;

  constructor(opts: DnaClientOptions) {
    const headers: Record<string, string> = {};
    if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
    this.raw = createClient<paths>({
      baseUrl: opts.baseUrl,
      headers,
      fetch: opts.fetch,
    });
    this.defaults = { scope: opts.scope, tenant: opts.tenant };
  }

  /** Merge the client-level default scope/tenant under a per-call query object. */
  private q<T extends ScopeTenant>(query?: T): T {
    return {
      ...(this.defaults.scope !== undefined ? { scope: this.defaults.scope } : {}),
      ...(this.defaults.tenant !== undefined ? { tenant: this.defaults.tenant } : {}),
      ...(query ?? {}),
    } as T;
  }

  private unwrap<T>(res: { data?: T; error?: unknown; response: Response }): T {
    if (res.error !== undefined || !res.response.ok) {
      throw new DnaApiError(res.response.status, res.error);
    }
    return res.data as T;
  }

  // ── health ────────────────────────────────────────────────────────────────

  /** Liveness probe (unauthenticated). Returns `{ ok: true }`. */
  async health() {
    return this.unwrap(await this.raw.GET("/health"));
  }

  // ── definitions ─────────────────────────────────────────────────────────

  /** List a scope's prompt-target agents, tenant-aware. */
  async listAgents(query?: ScopeTenant) {
    return this.unwrap(await this.raw.GET("/v1/agents", { params: { query: this.q(query) } }));
  }

  /**
   * Compose one agent's system prompt LIVE (Soul + Guardrails + instruction).
   *
   * Pass `explain: true` (opt-in) to also get per-section provenance:
   * `sections` (source artifact, content hash, version, layer origin and
   * tenant-overlay marker per composed section) and `attribution`
   * (`"declared"` — kernel-owned template, section map correct by
   * construction; `"heuristic"` — the agent has a custom promptTemplate, the
   * map is fail-soft string matching and may omit/over-report sections). The
   * composed `prompt` is byte-identical with or without the flag; without it
   * the response shape is the historical plain compose.
   */
  async agentPrompt(name: string, query?: ScopeTenant & { explain?: boolean }) {
    return this.unwrap(
      await this.raw.GET("/v1/agents/{name}/prompt", {
        params: { path: { name }, query: this.q(query) },
      }),
    );
  }

  /** List a scope's Tool Kind surfaces (name + description), tenant-aware. */
  async listTools(query?: ScopeTenant) {
    return this.unwrap(await this.raw.GET("/v1/tools", { params: { query: this.q(query) } }));
  }

  // ── memory (reads) ────────────────────────────────────────────────────────

  /** List the tenant's memory — base + the tenant's OWN overlay. */
  async listMemories(query?: ScopeTenant) {
    return this.unwrap(await this.raw.GET("/v1/memories", { params: { query: this.q(query) } }));
  }

  /**
   * List the CALLER'S OWN personal memories — the read face of
   * {@link DnaClient.importMemories}.
   *
   * Same identity contract as the import: the `personal:<oid>` partition is
   * resolved SERVER-SIDE from the verified token, so there is deliberately
   * **no tenant or identity parameter** (and the client-level default `tenant`
   * is NOT merged). A shared bearer (`--auth token`) is not an identity — 403
   * always; a token carrying no identity claim is 403 too. Each item carries a
   * per-item `personal` flag: the caller's own memories say `true`, the shared
   * base memories riding along say `false`.
   */
  async listPersonalMemories(query?: { scope?: string }) {
    const scope = query?.scope ?? this.defaults.scope;
    return this.unwrap(
      await this.raw.GET("/v1/memories/personal", {
        params: { query: scope !== undefined ? { scope } : {} },
      }),
    );
  }

  /** Recall the tenant's memory for `q` (hybrid/bi-temporal or lexical). */
  async searchMemories(query: { q: string; scope?: string; tenant?: string; k?: number }) {
    return this.unwrap(await this.raw.GET("/v1/memories/search", { params: { query: this.q(query) } }));
  }

  // ── memory (writes) ───────────────────────────────────────────────────────

  /**
   * Persist ONE memory (an `Engram`) into the tenant's OWN overlay.
   *
   * Writes only to the caller's overlay — never the base scope, never another
   * tenant. 400 on a blank `summary`. The deterministic name it returns is the
   * id {@link DnaClient.deleteMemory} targets to undo the write.
   */
  async rememberMemory(
    body: {
      summary: string;
      area?: string;
      tags?: string[] | null;
      affect?: string;
      owner?: string;
    },
    query?: ScopeTenant,
  ) {
    return this.unwrap(
      await this.raw.POST("/v1/memories", {
        params: { query: this.q(query) },
        body: {
          area: "general",
          affect: "triumph",
          owner: "portal",
          ...body,
        },
      }),
    );
  }

  /**
   * Import a MIF bundle into the CALLER'S OWN personal memory.
   *
   * `bundle` takes any shape the export side emits: a JSON-LD
   * `{ "@graph": [...] }`, a bare array of Memory Units, or one Memory Unit.
   * `as` picks verbatim storage (`passthrough`), the recallable `Engram`
   * projection (`native`), or both (default); `dedupe` makes a re-import
   * idempotent by MIF id.
   *
   * There is deliberately **no tenant or identity parameter**: the write always
   * lands in the caller's own `personal:<oid>` partition, with the identity
   * derived server-side from the token (INV-PERSONAL) — which is also why the
   * client-level default `tenant` is NOT merged here. A malformed bundle is a
   * 400 with nothing written, an oversized one a 413, and a token carrying no
   * identity a 403. The returned counts always reconcile with `received`, so a
   * partial import is never silent.
   */
  async importMemories(
    body: {
      bundle: unknown;
      as?: "passthrough" | "native" | "both";
      dedupe?: "id" | "content-hash" | "off";
    },
    query?: { scope?: string },
  ) {
    const scope = query?.scope ?? this.defaults.scope;
    return this.unwrap(
      await this.raw.POST("/v1/memories/import", {
        params: { query: scope !== undefined ? { scope } : {} },
        body: { as: "both", dedupe: "id", ...body },
      }),
    );
  }

  /**
   * Delete ONE memory from the tenant's OWN overlay.
   *
   * Refuses anything outside that overlay: a base-scope memory, or another
   * tenant's, is a 404 — the delete cannot reach across the isolation.
   */
  async deleteMemory(name: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.DELETE("/v1/memories/{name}", {
        params: { path: { name }, query: this.q(query) },
      }),
    );
  }

  // ── intel (reads) ─────────────────────────────────────────────────────────

  /** List the tenant's watched IntelSource docs (the Direction stage). */
  async listSources(query?: ScopeTenant) {
    return this.unwrap(await this.raw.GET("/v1/sources", { params: { query: this.q(query) } }));
  }

  /** List the tenant's IntelInsight docs (ranked), filterable by state/source. */
  async listInsights(query?: {
    scope?: string;
    tenant?: string;
    state?: string;
    source?: string;
    source_ref?: string;
  }) {
    return this.unwrap(await this.raw.GET("/v1/insights", { params: { query: this.q(query) } }));
  }

  /** The feedback KPIs (precision + noise rate) over the tenant's insight stream. */
  async insightMetrics(query?: { scope?: string; tenant?: string; source_ref?: string }) {
    return this.unwrap(
      await this.raw.GET("/v1/insights/metrics", { params: { query: this.q(query) } }),
    );
  }

  // ── intel (write) ─────────────────────────────────────────────────────────

  /**
   * Set an insight's feedback state — the reader's disposition.
   *
   * `state` is one of `new|actioned|dismissed|snoozed`; anything else is a 400.
   * An insight unknown to this (scope, tenant) is a 404.
   */
  async setInsightState(name: string, state: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.PATCH("/v1/insights/{name}/state", {
        params: { path: { name }, query: this.q(query) },
        body: { state },
      }),
    );
  }

  // ── portfolio (reads) ─────────────────────────────────────────────────────

  /** List the tenant's Organization docs (the console's top-level container). */
  async listOrgs(query?: ScopeTenant) {
    return this.unwrap(await this.raw.GET("/v1/orgs", { params: { query: this.q(query) } }));
  }

  /** List the tenant's Project docs. */
  async listProjects(query?: ScopeTenant) {
    return this.unwrap(await this.raw.GET("/v1/projects", { params: { query: this.q(query) } }));
  }

  /** One project's detail + its RESOLVED repos. 404 → {@link DnaApiError}. */
  async getProject(slug: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.GET("/v1/projects/{slug}", {
        params: { path: { slug }, query: this.q(query) },
      }),
    );
  }

  /** List a project's members with their RESOLVED role, tenant-scoped. */
  async listProjectMembers(slug: string, query?: { scope?: string; tenant?: string; viewer?: string }) {
    return this.unwrap(
      await this.raw.GET("/v1/projects/{slug}/members", {
        params: { path: { slug }, query: this.q(query) },
      }),
    );
  }

  /** List the tenant's Repo docs (code repositories the portfolio references). */
  async listRepos(query?: ScopeTenant) {
    return this.unwrap(await this.raw.GET("/v1/repos", { params: { query: this.q(query) } }));
  }

  // ── portfolio (writes) ────────────────────────────────────────────────────

  /**
   * Create a Project inside `workspace_id`.
   *
   * SECURITY: the caller must hold an ACTIVE `WorkspaceMembership` in that
   * workspace — a caller without one is **403**, and a pending invite does not
   * count. The write scope and the project's `board_scope` are DERIVED from the
   * workspace + slug; the route refuses to accept either from the caller. 400 on
   * a blank `workspace_id`/`name`.
   *
   * `claims` is the caller's identity for a trusted server-side call under
   * `--auth none`/`--auth token`. Under `--auth config` the VERIFIED token claims
   * always win and it is ignored. Takes no scope/tenant: the boundary comes from
   * the body's `workspace_id`, not from a query hint.
   */
  async createProject(body: {
    workspace_id: string;
    name: string;
    slug?: string | null;
    claims?: Record<string, unknown> | null;
  }) {
    return this.unwrap(await this.raw.POST("/v1/projects", { body }));
  }

  /**
   * Invite / set a user's PROJECT-scope role (upserts one Membership doc).
   *
   * SECURITY: `actor` must be Owner/Admin of the project or its org, and only an
   * Owner may grant `owner` — **403** otherwise. 404 for an unknown project; 422
   * for an unknown role.
   */
  async setProjectMember(
    slug: string,
    body: { user: string; role: string; actor?: string | null },
    query?: ScopeTenant,
  ) {
    return this.unwrap(
      await this.raw.POST("/v1/projects/{slug}/members", {
        params: { path: { slug }, query: this.q(query) },
        body,
      }),
    );
  }

  /**
   * Remove a user's PROJECT-scope grant.
   *
   * SECURITY: `actor` must be Owner/Admin, and removing an Owner requires Owner —
   * **403** otherwise. Deletes ONLY the project-scope grant; an inherited
   * org-scope grant is untouched (the user may still resolve to a role
   * afterwards). 404 when the user holds no project grant here.
   */
  async removeProjectMember(
    slug: string,
    user: string,
    query?: { actor?: string; scope?: string; tenant?: string },
  ) {
    return this.unwrap(
      await this.raw.DELETE("/v1/projects/{slug}/members/{user}", {
        params: { path: { slug, user }, query: this.q(query) },
      }),
    );
  }

  /**
   * First-owner bootstrap: make `user` Owner of tenant `tid` when it has no Owner
   * yet (org- + project-scope grants).
   *
   * SECURITY: FIRST-owner only and idempotent — once ANY Owner exists this is a
   * no-op, so a later user cannot auto-escalate into an established tenant. This
   * is a trusted server-side call (the portal's shared bearer), not a user-facing
   * one. 400 on a missing tenant/user.
   */
  async provisionTenantOwner(tid: string, user: string, query?: { scope?: string }) {
    return this.unwrap(
      await this.raw.POST("/v1/tenants/{tid}/provision-owner", {
        params: { path: { tid }, query: { scope: query?.scope ?? this.defaults.scope } },
        body: { user },
      }),
    );
  }

  // ── board (reads) ─────────────────────────────────────────────────────────

  /** A compact SDLC summary for a project's `board_scope`. `scope` is required. */
  async getBoard(query: { scope: string; tenant?: string; recent?: number }) {
    return this.unwrap(await this.raw.GET("/v1/board", { params: { query: this.q(query) } }));
  }

  /** One board work-item's FULL doc (the console's item-detail drawer). */
  async getBoardItem(query: { scope: string; name: string; tenant?: string; kind?: string }) {
    return this.unwrap(await this.raw.GET("/v1/board/item", { params: { query: this.q(query) } }));
  }

  // ── workspaces (reads) ────────────────────────────────────────────────────
  // The workspace boundary is identity-scoped: it is resolved from the caller's
  // VERIFIED claims, never from a `tenant` query hint, so none of the routes
  // below take the client-level scope/tenant defaults.

  /**
   * List the workspaces the caller holds an ACTIVE membership in — the workspace
   * switcher's data source.
   *
   * Enumerates by membership, never by tenant provenance: a pending invite does
   * not appear, and an unknown identity gets an empty list rather than somebody
   * else's workspaces.
   */
  async listWorkspaces(query?: { actor_oid?: string; actor_email?: string }) {
    return this.unwrap(
      await this.raw.GET("/v1/workspaces", { params: { query: query ?? {} } }),
    );
  }

  /** List a workspace's members (grants). RBAC: the actor must be Owner/Admin. */
  async listWorkspaceMembers(
    workspaceId: string,
    query?: { actor_oid?: string; actor_email?: string },
  ) {
    return this.unwrap(
      await this.raw.GET("/v1/workspaces/{workspace_id}/members", {
        params: { path: { workspace_id: workspaceId }, query: query ?? {} },
      }),
    );
  }

  // ── workspaces (writes) ───────────────────────────────────────────────────
  // Under `--auth config` the verified token's claims WIN over any `claims` /
  // `actor` argument below; those exist for a TRUSTED server-side caller running
  // the API under `--auth none`/`--auth token` (the portal, holding the shared
  // bearer), which vouches for the session it already verified.

  /**
   * Create a workspace and its first OWNER, in one call.
   *
   * SECURITY: the `workspace_id` is MINTED SERVER-SIDE and cannot be supplied —
   * there is deliberately no field for it, so a caller cannot name a workspace
   * into existence and race its real owner for it. The caller's verified identity
   * becomes the active owner. `slug` defaults to a slugified `name` and is made
   * unique. 400 on a blank name or a missing oid/email claim.
   */
  async createWorkspace(body: {
    name: string;
    slug?: string | null;
    claims?: Record<string, unknown> | null;
  }) {
    return this.unwrap(await this.raw.POST("/v1/workspaces", { body }));
  }

  /**
   * Invite an identity (by email) into a workspace — a `pending`
   * `WorkspaceMembership` that only {@link DnaClient.acceptInvites} can activate.
   *
   * SECURITY: the actor must be Owner/Admin of the workspace, and only an Owner
   * may invite an Owner — **403** otherwise. 422 on an unknown role.
   */
  async createInvite(
    workspaceId: string,
    body: { email: string; role?: string; actor?: Record<string, unknown> | null },
  ) {
    return this.unwrap(
      await this.raw.POST("/v1/workspaces/{workspace_id}/invites", {
        params: { path: { workspace_id: workspaceId } },
        body: { role: "member", ...body },
      }),
    );
  }

  /**
   * Accept EVERY pending invite matching the caller's verified sign-in claims —
   * binds the durable `oid` and flips `pending` → `active`.
   *
   * SECURITY: matches on a VERIFIED email claim only, and refuses to hijack a
   * grant already bound to a different `oid`. Takes no workspace argument by
   * design: a caller cannot accept an invite that was not addressed to them.
   */
  async acceptInvites(body?: { claims?: Record<string, unknown> | null }) {
    return this.unwrap(
      await this.raw.POST("/v1/workspaces/accept", { body: body ?? {} }),
    );
  }

  /**
   * Reconcile the verified identity's membership in `workspaceId` — the portal's
   * every-sign-in idempotent no-op.
   *
   * SECURITY: since decision **D5** this CREATES NOTHING. It REQUIRES an existing
   * ACTIVE `WorkspaceMembership` and merely returns it (back-filling a missing
   * Workspace identity doc for an owner). A caller holding no active membership
   * here — a stranger included — is **403**. To create a workspace use
   * {@link DnaClient.createWorkspace}, which mints its own id. 400 on a missing
   * oid/email claim.
   */
  async provisionWorkspaceOwner(
    workspaceId: string,
    body?: { claims?: Record<string, unknown> | null },
  ) {
    return this.unwrap(
      await this.raw.POST("/v1/workspaces/{workspace_id}/provision-owner", {
        params: { path: { workspace_id: workspaceId } },
        body: body ?? {},
      }),
    );
  }

  /**
   * Revoke (remove) a member's `WorkspaceMembership`.
   *
   * SECURITY: the actor must be Owner/Admin — **403** otherwise. The LAST
   * remaining owner can NEVER be revoked (**409**, fail-closed), so a workspace
   * cannot be orphaned. A target holding no grant here is 404. Name the target by
   * `target_email` or `target_oid` (oid wins when both are given).
   */
  async revokeWorkspaceMember(
    workspaceId: string,
    body: {
      target_email?: string | null;
      target_oid?: string | null;
      actor?: Record<string, unknown> | null;
    },
  ) {
    return this.unwrap(
      await this.raw.POST("/v1/workspaces/{workspace_id}/members/revoke", {
        params: { path: { workspace_id: workspaceId } },
        body,
      }),
    );
  }

  // ── billing (write) ───────────────────────────────────────────────────────

  /**
   * Upsert the `AccountPlan` assigning `account_id` → `tier_id` — the
   * billing→enforcement bridge.
   *
   * The subscription belongs to the BILLING ACCOUNT: this ONE call covers every
   * workspace whose `account_id` matches, so a customer's second workspace needs
   * no billing write and is never a second charge.
   *
   * SECURITY: this route ASSIGNS a plan and performs no membership check of its
   * own; it is a trusted server-side call (the portal's Stripe webhook handler,
   * holding the shared bearer) and must never be exposed to an end user.
   * Idempotent under Stripe retries. 400 on a missing account_id/tier_id.
   */
  async setAccountPlan(body: {
    account_id: string;
    tier_id: string;
    source?: string;
    stripe_customer_id?: string | null;
    stripe_subscription_id?: string | null;
    status?: string | null;
  }) {
    return this.unwrap(
      await this.raw.PUT("/v1/account-plan", { body: { source: "stripe", ...body } }),
    );
  }
}

/** Functional constructor — `createDnaClient(opts)` ≡ `new DnaClient(opts)`. */
export function createDnaClient(opts: DnaClientOptions): DnaClient {
  return new DnaClient(opts);
}
