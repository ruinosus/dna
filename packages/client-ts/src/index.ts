/**
 * `dna-client` — the official TypeScript client for the **DNA REST read-API**
 * (`dna api serve`).
 *
 * The client is GENERATED from the API's OpenAPI instance (`docs/openapi.json`,
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
 * Instance `spec`, an SDLC work-item's verbatim AC/DoD/timeline lists, and
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

  /** The derived Genome view of a scope: identity + ships (the scope's own
   * contents) + the tenant LayerPolicy, composed live. */
  async genomeView(query?: ScopeTenant) {
    return this.unwrap(await this.raw.GET("/v1/genome", { params: { query: this.q(query) } }));
  }

  /**
   * Read one definition as the tenant sees it: the effective (composed)
   * spec, the inherited base spec, whether the tenant has an override, and
   * the Kind's edit schema (`ui_schema` + overlayable fields) — what a
   * customization editor renders. 404 for an unknown (kind, name).
   */
  async readDefinition(kind: string, name: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.GET("/v1/definitions/{kind}/{name}", {
        params: { path: { kind, name }, query: this.q(query) },
      }),
    );
  }

  // ── definitions (writes) ──────────────────────────────────────────────────

  /**
   * Persist a tenant override of a definition (the editor's Save) — a
   * tenant-layer write. A LOCKED Kind/field is vetoed by the kernel's
   * LayerPolicy check and surfaces as a 403 {@link DnaApiError}.
   */
  async applyDefinition(
    kind: string,
    name: string,
    spec: Record<string, unknown>,
    query?: ScopeTenant,
  ) {
    return this.unwrap(
      await this.raw.PUT("/v1/definitions/{kind}/{name}", {
        params: { path: { kind, name }, query: this.q(query) },
        body: { spec },
      }),
    );
  }

  /**
   * Revert a tenant override — deletes the tenant-layer doc so reads fall
   * back to the inherited base (the editor's "Reset to default").
   */
  async revertDefinition(kind: string, name: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.DELETE("/v1/definitions/{kind}/{name}", {
        params: { path: { kind, name }, query: this.q(query) },
      }),
    );
  }

  // ── Kind authoring (a workspace declares its OWN Kind) ───────────────────

  /**
   * Author a Kind for the calling workspace — a `KindDefinition` instance
   * written WITHOUT an approval marker, under the workspace's own assigned
   * apiVersion namespace.
   *
   * What comes back is INERT: `approved` is always `false`, and an unapproved
   * Kind never enters the registry, so it neither validates instances nor
   * routes their storage. Approval is a separate act with its own verified
   * actor (`approveKind`) — this call cannot perform it, and there is
   * deliberately no parameter for an approver. The instance records
   * `proposed_by`: the server-verified identity of THIS call, stamped here
   * because a proposer cannot be back-filled onto an instance that never
   * recorded one.
   *
   * `kind` must be a CamelCase identifier — a CAPITAL letter followed by up to
   * 63 letters or digits, nothing else. It is the one value that reaches a
   * path, and the initial capital is required so `Contrato` and `contrato`
   * cannot collide on a case-insensitive filesystem.
   *
   * 400 for a missing tenant, or a `kind` that is not such an identifier; 403
   * when the workspace does not own the target namespace; 503 when the store's
   * namespace-registry scope has not been provisioned.
   */
  async authorKind(
    kind: string,
    schema: Record<string, unknown>,
    traits?: string[],
    query?: ScopeTenant,
  ) {
    return this.unwrap(
      await this.raw.POST("/v1/kinds", {
        params: { query: this.q(query) },
        body: { kind, schema, traits },
      }),
    );
  }

  /**
   * Approve an authored Kind — the act that puts it INTO EFFECT.
   *
   * Registration is what confers schema validation and storage routing, and
   * the registry withholds it until `approved_by` names someone, so this is
   * not a flag with a promise attached: it is the only thing that lets the
   * next load take the Kind at all.
   *
   * The approver is the caller's server-VERIFIED identity; there is
   * deliberately no parameter for it, and an `approved_by` in the payload
   * would reach nothing. The instance's `proposed_by` is preserved, so the
   * response names both acts. The two MAY be the same identity — a solo author
   * approving their own proposal is two credentials, and the audit reports the
   * coincidence rather than refusing it.
   *
   * 404 when no such Kind was authored in this scope (approval acts on an
   * existing instance and creates none); 400 for a missing tenant, a malformed
   * `kind`, or a Kind declared under two namespaces at once; 403 when the
   * namespace gate refuses the write; 409 when the Kind was edited between the
   * read and this call (re-read, then approve again).
   *
   * It is also the UNDO of {@link revokeKind}: approving again clears the
   * revocation, and every existing instance is valid once more with nothing to
   * migrate.
   */
  async approveKind(kind: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.POST("/v1/kinds/{kind}/approve", {
        params: { path: { kind }, query: this.q(query) },
      }),
    );
  }

  /**
   * Revoke an authored Kind — the act that WITHDRAWS its effect.
   *
   * Deliberately NOT the inverse of {@link approveKind}. Un-approving would
   * return the Kind to *never approved*, and a Kind that never registered is
   * the PERMISSIVE state — its instances are accepted with no validation at
   * all — so clearing the approval would switch the gate off rather than close
   * it. Revoked is a THIRD state:
   *
   * | state          | existing instances | new instances                |
   * | -------------- | ------------------ | ---------------------------- |
   * | never approved | —                  | accepted WITHOUT validation  |
   * | approved       | valid, routed      | validated against the schema |
   * | revoked        | INVALID            | REFUSED                      |
   *
   * Nothing is deleted. Existing instances stay readable and come back MARKED
   * (`status.valid === false`), and in a listing they appear marked rather
   * than vanishing — so this can never be used to hide data without deleting
   * it. New instances of the Kind are refused outright, conforming ones
   * included: what was withdrawn is the Kind, not a schema.
   *
   * Reversible in one call — {@link approveKind} clears the revocation.
   * `approved_by` survives here, because revoking is a third act and not an
   * erasure of the second.
   *
   * The revoker is the caller's server-VERIFIED identity; there is
   * deliberately no parameter for it.
   *
   * 404 when no such Kind was authored in this scope, and equally when it
   * belongs to another workspace; 400 for a missing tenant or a malformed
   * `kind`; 409 when the instance moved since it was read; 403 when the
   * namespace gate refuses the write.
   */
  async revokeKind(kind: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.POST("/v1/kinds/{kind}/revoke", {
        params: { path: { kind }, query: this.q(query) },
      }),
    );
  }

  /**
   * List the scope's authored Kinds with their approval state — the audit
   * view. Reads INSTANCES, not the registry: an unapproved Kind is precisely
   * the one the registry does not have.
   *
   * Each row carries BOTH actors (`proposed_by`/`proposed_at` and
   * `approved_by`/`approved_at`): a reviewer deciding whether to confer effect
   * needs to see who asked for it without leaving the list.
   */
  async listAuthoredKinds(query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.GET("/v1/kinds", { params: { query: this.q(query) } }),
    );
  }

  /**
   * Read ONE authored Kind in full — the listing's row PLUS the `schema` and
   * the `traits`.
   *
   * The roster (`listAuthoredKinds`) deliberately omits the schema, which left
   * a reviewer unable to see what they would be conferring effect ON.
   * Registration is what gives a Kind schema validation and storage routing, so
   * "should this take effect?" is a question about the schema; this is the call
   * that answers it.
   *
   * Filtered to the CALLER: a Kind authored by another workspace in a shared
   * scope is a **404**, the same answer a Kind nobody ever authored gets — "it
   * exists but is not yours" would be a probe for what the neighbours are
   * authoring, and this call would answer that probe with their data model.
   *
   * 400 for a `kind` that is not a CamelCase identifier, or a Kind declared
   * under two of the caller's own namespaces at once; 404 when no such Kind is
   * the caller's; 403 for a namespace two claims give to different owners; 503
   * when the namespace registry cannot be read.
   */
  async getAuthoredKind(kind: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.GET("/v1/kinds/{kind}", {
        params: { path: { kind }, query: this.q(query) },
      }),
    );
  }

  /**
   * The descriptor of a REGISTERED Kind — its JSON `schema` plus the
   * `ui_schema` widget hints.
   *
   * The registry sibling of {@link getAuthoredKind}: a registered Kind is the
   * PRODUCT's data model (the same for every caller, holding nobody's
   * content), so this door does not filter. It exists so a form can DERIVE
   * validation (min/max, enums, required) from the schema instead of
   * hand-copying constraints that then drift from the kernel's.
   *
   * 404 for a Kind the runtime does not register.
   */
  async getRegisteredKind(kind: string, query?: { scope?: string; tenant?: string }) {
    return this.unwrap(
      await this.raw.GET("/v1/kinds/registry/{kind}", {
        params: { path: { kind }, query },
      }),
    );
  }

  /**
   * The SCHEMA graph of the registered Kinds — which Kind may point at which,
   * through which field, in ONE call.
   *
   * The SET sibling of {@link getRegisteredKind}, and the reason it exists:
   * answering "which Kinds reference which here?" through the per-Kind door
   * costs one request per Kind and gets slower as a workspace grows. Same
   * projection that generates `docs/reference/data-model.md`, served as JSON.
   *
   * Returns `kinds` (nodes), `edges`
   * (`from_kind`/`field`/`to_kind`/`cardinality`/`tier`/`polymorphic`/`by`/
   * `enforced`/`inverse_of`), the gap list `unresolved`, and a `coverage`
   * block.
   *
   * **`tier === "declared"` is NOT the same as `enforced`.** The kernel
   * resolves a relation at write time only when it has a concrete target Kind
   * addressed by instance name (`by === "name"`). A relation addressed by a
   * spec field of the target (`by: "workspace_id"`) or carrying its Kind in
   * the value (`to_kind === "*"`) is fully declared and deliberately not
   * followed. Filter on `enforced` — never on the tier — when the question is
   * "what does the runtime check?".
   *
   * **Rank `unresolved` by `origin`, never by `reason`.** `declared`,
   * `composition` and `inverse` rows are declarations the model cannot honour
   * — an authoring error, and `inverse` specifically means two Kinds each
   * claim to be half of one relation while disagreeing about it.
   * `undeclared` rows are fields whose NAME looks like a reference and which
   * nothing declares; they are usually not references at all (an OAuth
   * `client_id`, a Stripe customer id). `coverage.declared_origins` names the
   * ones worth alarm, so the ranking is derived from the answer instead of
   * re-typed in a screen — and `reason` stays English prose nobody has to
   * translate.
   *
   * **Read the coverage block.** `coverage.enforced` says how much of the
   * graph the runtime actually checks, and `limits` names what the graph
   * structurally cannot see. The first limit is the one that matters most:
   * these edges are SCHEMA — which Kinds MAY reference which. Which INSTANCES
   * reference which is a different graph, and this call does not answer it.
   *
   * No 404: a scope with nothing registered is an empty graph whose
   * `coverage.kinds` is 0, which is an answer.
   */
  async kindGraph(query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.GET("/v1/graph/kinds", { params: { query: this.q(query) } }),
    );
  }

  /**
   * The Kind CATALOG of a scope — every Kind the registry serves here.
   *
   * The collection sibling of {@link getRegisteredKind}, and the answer to
   * "what can I act on?" without hardcoding a list. A hardcoded list is how a
   * Kind registered tomorrow stays invisible; the enumeration belongs to the
   * registry, not to each caller.
   *
   * Not {@link listAuthoredKinds}, which lists the caller's own KindDefinition
   * INSTANCES *including the unapproved ones* — the audit roster behind an
   * approval decision. This lists what is REGISTERED and therefore in force,
   * built-ins included.
   */
  async listRegisteredKinds(query?: { scope?: string; tenant?: string }) {
    return this.unwrap(
      await this.raw.GET("/v1/kinds/registry", { params: { query } }),
    );
  }

  // ── the generic, kubernetes-shaped instance write ────────────────────────

  /**
   * List the instances of `kind` — the READ face of the generic door.
   *
   * The write ({@link writeKindInstance}) accepted any Kind, but reading back
   * only worked for the Kinds someone had hand-written a route for
   * (`/v1/memories`, `/v1/projects`, …). Whoever wrote through the generic
   * door could not read through it, and found that out AFTER writing.
   *
   * `fields` (dotted paths; an unprefixed one resolves under `spec.`) pushes
   * the PROJECTION down to the kernel. Without it, answering "which ones are
   * open" costs 1 + N calls — list the names, then read each. On Postgres the
   * projection becomes a SELECT and the row travels trimmed.
   *
   * An unknown Kind is 404 NAMING it, the same answer the write gives. An
   * empty list from a Kind that exists is 200 with `instances: []` — "exists
   * and holds nothing" is an answer, and conflating it with "does not exist"
   * would make a screen say *error* where it should say *none yet*.
   *
   * Like the write, no `scope` parameter: identity and scope are never caller
   * input on this route.
   */
  async listKindInstances(
    kind: string,
    opts?: {
      tenant?: string;
      apiVersion?: string;
      limit?: number;
      offset?: number;
      fields?: string[];
      orderBy?: string[];
    },
  ) {
    return this.unwrap(
      await this.raw.GET("/v1/kinds/{kind}/instances", {
        params: {
          path: { kind },
          query: {
            tenant: opts?.tenant,
            api_version: opts?.apiVersion,
            limit: opts?.limit,
            offset: opts?.offset,
            // CSV on the wire: the server splits on comma. An absent list stays
            // `undefined` so an omitted projection means "the whole instance",
            // not "no fields" — an empty CSV would read as the latter.
            fields: opts?.fields?.length ? opts.fields.join(",") : undefined,
            order_by: opts?.orderBy?.length ? opts.orderBy.join(",") : undefined,
          },
        },
      }),
    );
  }

  /**
   * Read ONE instance of `kind`, VERBATIM — what the list cannot give. The
   * projected list travels through the readers' view when the Kind is
   * bundle-producible (Agent, Skill…), and the view NORMALIZES: real spec
   * fields written through the generic door can simply not travel through it
   * (measured 2026-08-05: an Agent's `description` and
   * `tools_requiring_confirmation`). This is the verbatim read, as the
   * caller's layer sees the instance, with the optimistic-concurrency `etag`
   * for a follow-up `writeKindInstance` `ifMatch`.
   *
   * 404 names what is missing — the unknown Kind or the instance.
   */
  async getKindInstance(
    kind: string,
    name: string,
    opts?: { tenant?: string; apiVersion?: string },
  ) {
    return this.unwrap(
      await this.raw.GET("/v1/kinds/{kind}/instances/{name}", {
        params: {
          path: { kind, name },
          query: { tenant: opts?.tenant, api_version: opts?.apiVersion },
        },
      }),
    );
  }

  /**
   * Resolve an instance by its short **id**, without knowing its Kind.
   *
   * The id (i-114) is 12 chars of `[a-z2-7]`, minted on write and carried in
   * frontmatter as `x-dna-id`. It is prefix-resolvable: **four characters or
   * more** is accepted, and an ambiguous prefix is REFUSED rather than
   * arbitrated — two instances matching is a fact the caller needs, not a
   * coin toss the server should make for them.
   *
   * This is the lookup that exists because the NAME is the authored address
   * and the ID is the durable one. A name that moved leaves every authored
   * reference pointing at the old one — that is why `dna rename` exists — but
   * a machine-written edge carries the id and still resolves. This method is
   * how a TS caller follows that half.
   *
   * ⚠️ Not every instance has one: rows written before the id was minted
   * answer 404, which reads as "no instance with this id", never as "no
   * instance". A store that cannot look up by id at all answers **501**.
   */
  async resolveInstance(id: string, opts?: { scope?: string }) {
    return this.unwrap(
      await this.raw.GET("/v1/instances/{id}", {
        params: { path: { id }, query: { scope: opts?.scope } },
      }),
    );
  }

  /**
   * "What points at this instance?" — the derived reference graph.
   *
   * `direction: "in"` (the default, and the product question) returns the
   * instances pointing AT this one; `"out"` what it points at; `"both"` the
   * union. `depth` walks further and is clamped server-side — two of the
   * declared references are self-referential by design, so an unbounded walk
   * is not on offer.
   *
   * Each edge carries `resolved`: `false` is a DANGLING reference — declared,
   * written, and resolving to nothing. Those rows are the list of what is
   * broken and are never filtered out.
   *
   * `stop` says why the walk ended (`complete` / `depth_reached` /
   * `truncated`) and `graph_producer` reports whether the producer is even on.
   * A server whose store keeps no edge graph answers **501**, not an empty
   * list — "nothing points at this" is a claim only a store that records edges
   * may make.
   */
  async graphRefs(
    kind: string,
    name: string,
    opts?: {
      direction?: "in" | "out" | "both";
      depth?: number;
      tenant?: string;
      apiVersion?: string;
    },
  ) {
    return this.unwrap(
      await this.raw.GET("/v1/kinds/{kind}/instances/{name}/refs", {
        params: {
          path: { kind, name },
          query: {
            tenant: opts?.tenant,
            api_version: opts?.apiVersion,
            direction: opts?.direction ?? "in",
            depth: opts?.depth ?? 1,
          },
        },
      }),
    );
  }

  /**
   * Write one instance of `kind` — the generic door, kubernetes-shaped: the
   * endpoint names the Kind (applying a CRD creates the endpoint that serves
   * it; `kind` is inferred from where the client submits, never re-stated
   * ambiguously), the body is exactly `{ metadata, spec }` plus an optional
   * provenance citation.
   *
   * `metadata.name` is REQUIRED — a blank/absent one is 400. The server
   * validates `spec` against the Kind's REGISTERED JSON Schema before writing
   * (like the Kubernetes API server since 1.25), and names the offending
   * field on refusal (400 — unknown property, or a missing required one). A
   * BOOTSTRAP Kind (Genome / LayerPolicy / KindDefinition) is refused (403) —
   * the generic write's own gate, untouched here. An authored-but-unapproved
   * Kind and a Kind nobody ever authored answer the SAME 404 naming it: there
   * is no third, more-specific answer visible from this door. A stale
   * `ifMatch` is 409.
   *
   * `sourceSha256` (optional) cites the `SourceArtifact` (by content address)
   * this instance was extracted from; the server closes the `derived_refs`
   * provenance edge, preserving every OTHER instance already recorded there
   * and updating THIS one's own entry in place on a re-write rather than
   * duplicating it. A citation naming no registered artifact under `tenant`
   * is 400.
   *
   * There is deliberately no `scope` parameter and no `claims` parameter
   * here — identity and scope are never caller input on this route (see the
   * server route's docstring). Hence a bespoke options type rather than
   * {@link ScopeTenant}: `scope` has no home on this call.
   */
  async writeKindInstance(
    kind: string,
    metadata: Record<string, unknown>,
    spec: Record<string, unknown>,
    opts?: {
      sourceSha256?: string;
      tenant?: string;
      apiVersion?: string;
      merge?: boolean;
      ifMatch?: string;
    },
  ) {
    return this.unwrap(
      await this.raw.POST("/v1/kinds/{kind}/instances", {
        params: {
          path: { kind },
          query: {
            tenant: opts?.tenant,
            api_version: opts?.apiVersion,
            merge: opts?.merge,
            if_match: opts?.ifMatch,
          },
        },
        body: { metadata, spec, source_sha256: opts?.sourceSha256 },
      }),
    );
  }

  // ── definitions (bundle entries — fork a bundle-file, plane B) ───────────

  /**
   * List a bundle instance's entry files (base ∪ tenant overlay), each
   * flagged `overridden` — whether THIS tenant forked that specific file.
   */
  async listBundleEntries(kind: string, name: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.GET("/v1/definitions/{kind}/{name}/entries", {
        params: { path: { kind, name }, query: this.q(query) },
      }),
    );
  }

  /**
   * Read one bundle entry's effective content (tenant overlay wins over
   * base), plus whether this tenant forked it and whether it's binary.
   */
  async readBundleEntry(kind: string, name: string, entry: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.GET("/v1/definitions/{kind}/{name}/entries/{entry}", {
        params: { path: { kind, name, entry }, query: this.q(query) },
      }),
    );
  }

  /**
   * Fork one bundle entry into the tenant layer. A LOCKED Kind is vetoed by
   * the kernel's LayerPolicy check and surfaces as a 403 {@link DnaApiError}.
   */
  async writeBundleEntry(
    kind: string,
    name: string,
    entry: string,
    content: string,
    query?: ScopeTenant,
  ) {
    return this.unwrap(
      await this.raw.PUT("/v1/definitions/{kind}/{name}/entries/{entry}", {
        params: { path: { kind, name, entry }, query: this.q(query) },
        body: { content },
      }),
    );
  }

  /**
   * Revert a tenant's fork of one bundle entry — reads fall back to the
   * inherited base file.
   */
  async revertBundleEntry(kind: string, name: string, entry: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.DELETE("/v1/definitions/{kind}/{name}/entries/{entry}", {
        params: { path: { kind, name, entry }, query: this.q(query) },
      }),
    );
  }

  // ── reconcile (2-way diff of a tenant's forks vs base-NOW, plane B2) ────

  /**
   * For each of the tenant's forked bundle-entry files, diff the fork's
   * content against the base's CURRENT content — READ-only. A file the
   * tenant forked that the base has since changed underneath it comes back
   * `"diverged"` even if the fork itself is untouched; a tenant-added file
   * (no base at all) is always `"diverged"` with `base: null`. Resolve with
   * the EXISTING bundle-entry primitives: keep = no-op, take-base =
   * {@link DnaClient.revertBundleEntry}, edit = {@link DnaClient.writeBundleEntry}.
   */
  async reconcileForks(kind: string, name: string, query?: ScopeTenant) {
    return this.unwrap(
      await this.raw.GET("/v1/definitions/{kind}/{name}/reconcile", {
        params: { path: { kind, name }, query: this.q(query) },
      }),
    );
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

  /**
   * RETIRE a memory — the lane `deleteMemory` refuses and names.
   *
   * A memory is never hard-deleted (`record.invalidate-only`): this stamps
   * `valid_to` so it drops out of default recall, and the row stays —
   * auditable and point-in-time reconstructable. Idempotent: an already
   * retired memory keeps its ORIGINAL `valid_to`, so a retry finishes an
   * interrupted edit instead of rewriting when it stopped being true.
   *
   * `supersededBy` records WHICH memory replaces this one, and is what turns
   * an edit into one intent instead of two unrelated writes. The portal edits
   * by writing the new memory FIRST and retiring the old one with this
   * pointer — write-first on purpose, so the bad outcome is TWO memories,
   * never zero.
   */
  async forgetMemory(
    name: string,
    opts?: ScopeTenant & { supersededBy?: string },
  ) {
    const { supersededBy, ...query } = opts ?? {};
    return this.unwrap(
      await this.raw.POST("/v1/memories/{name}/forget", {
        params: { path: { name }, query: this.q(query) },
        body: supersededBy ? { superseded_by: supersededBy } : undefined,
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
   * Record the ORIGINAL a projection will be derived from.
   *
   * SECURITY: the caller must hold an ACTIVE `WorkspaceMembership` in
   * `workspace_id` — without one it is **403**. The write scope is DERIVED from
   * the workspace; the route refuses to accept one.
   *
   * `uri` names WHERE the bytes live and is stored verbatim. It must NOT be a
   * signed URL: an instance carrying one would BE the access to its own
   * original, and would hand that access to anyone the instance reaches.
   *
   * IDEMPOTENT by content address — the same `sha256` updates the same
   * artifact, and any `derived_refs` already extracted from it survive the
   * call. A retried upload leaves no second row and erases no projection.
   */
  async registerArtifact(body: {
    workspace_id: string;
    sha256: string;
    uri: string;
    filename?: string | null;
    mime?: string | null;
    size_bytes?: number | null;
    claims?: Record<string, unknown> | null;
  }) {
    return this.unwrap(await this.raw.POST("/v1/artifacts", { body }));
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
