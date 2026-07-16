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
 * Read-first: the named methods cover the `/v1/*` GET read surface (the shape
 * dna-cloud's hand-rolled `lib/rest-client.ts` consumes today). The FULL typed
 * surface — including the handful of writes (memory remember/delete, insight
 * state, membership, workspace-plan) — is reachable through {@link DnaClient.raw},
 * the underlying `openapi-fetch` client, with the same generated types.
 *
 * NOTE ON RETURN TYPES: every DNA REST handler returns an untyped JSON object
 * (`dict[str, Any]`), so the OpenAPI response schemas are opaque
 * (`Record<string, unknown>`). Request inputs (query/path/body) ARE strongly
 * typed; response bodies are `unknown`-shaped and documented per method. Tighten
 * the API's response models to tighten these for free.
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

  /** Compose one agent's system prompt LIVE (Soul + Guardrails + instruction). */
  async agentPrompt(name: string, query?: ScopeTenant) {
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

  /** Recall the tenant's memory for `q` (hybrid/bi-temporal or lexical). */
  async searchMemories(query: { q: string; scope?: string; tenant?: string; k?: number }) {
    return this.unwrap(await this.raw.GET("/v1/memories/search", { params: { query: this.q(query) } }));
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

  // ── board (reads) ─────────────────────────────────────────────────────────

  /** A compact SDLC summary for a project's `board_scope`. `scope` is required. */
  async getBoard(query: { scope: string; tenant?: string; recent?: number }) {
    return this.unwrap(await this.raw.GET("/v1/board", { params: { query: this.q(query) } }));
  }

  /** One board work-item's FULL doc (the console's item-detail drawer). */
  async getBoardItem(query: { scope: string; name: string; tenant?: string; kind?: string }) {
    return this.unwrap(await this.raw.GET("/v1/board/item", { params: { query: this.q(query) } }));
  }

  // ── workspaces (read) ─────────────────────────────────────────────────────

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
}

/** Functional constructor — `createDnaClient(opts)` ≡ `new DnaClient(opts)`. */
export function createDnaClient(opts: DnaClientOptions): DnaClient {
  return new DnaClient(opts);
}
