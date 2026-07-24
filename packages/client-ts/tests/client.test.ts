/**
 * Usage test for the DNA REST client — drives every named read method against a
 * STUB `fetch` (no live server), asserting the client builds the right method,
 * URL, path substitution, query params (incl. client-level defaults), and the
 * bearer header, and that it unwraps success + throws {@link DnaApiError} on a
 * non-2xx. This is the client's behavioral contract; the OpenAPI-derived types
 * (src/schema.ts) are checked separately by `bun run typecheck`.
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { DnaApiError, DnaClient, createDnaClient } from "../src/index.js";

/** A fetch stub that records each request and returns a canned JSON body.
 * openapi-fetch invokes `fetch(new Request(url, init))`, so the first arg is a
 * `Request`; we read url/method/headers off it. */
function stub(body: unknown, status = 200) {
  const calls: {
    url: string;
    method: string;
    headers: Headers;
    body: string | null;
  }[] = [];
  const fetchImpl = (async (input: string | URL | Request, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(input, init);
    const sent = await req
      .clone()
      .text()
      .then((t) => t || null)
      .catch(() => null);
    calls.push({ url: req.url, method: req.method, headers: req.headers, body: sent });
    return new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  }) as unknown as typeof fetch;
  return { fetchImpl, calls };
}

const BASE = "http://dna.test";

describe("DnaClient", () => {
  test("health() hits /health and unwraps the body", async () => {
    const { fetchImpl, calls } = stub({ ok: true });
    const dna = new DnaClient({ baseUrl: BASE, fetch: fetchImpl });
    const out = await dna.health();
    expect(out).toEqual({ ok: true });
    expect(calls[0]!.url).toBe(`${BASE}/health`);
  });

  test("bearer token is sent on every request", async () => {
    const { fetchImpl, calls } = stub({ scope: "s", agents: [] });
    const dna = new DnaClient({ baseUrl: BASE, token: "sekret", fetch: fetchImpl });
    await dna.listAgents({ scope: "s" });
    const headers = calls[0]!.headers;
    expect(headers.get("authorization")).toBe("Bearer sekret");
  });

  test("scope + tenant query params are passed through", async () => {
    const { fetchImpl, calls } = stub({ scope: "dna-development", agents: [] });
    const dna = new DnaClient({ baseUrl: BASE, fetch: fetchImpl });
    await dna.listAgents({ scope: "dna-development", tenant: "acme" });
    const url = new URL(calls[0]!.url);
    expect(url.pathname).toBe("/v1/agents");
    expect(url.searchParams.get("scope")).toBe("dna-development");
    expect(url.searchParams.get("tenant")).toBe("acme");
  });

  test("client-level default tenant/scope apply, per-call overrides win", async () => {
    const { fetchImpl, calls } = stub({ memories: [] });
    const dna = createDnaClient({ baseUrl: BASE, tenant: "acme", scope: "base", fetch: fetchImpl });
    await dna.listMemories(); // uses defaults
    await dna.listMemories({ tenant: "other" }); // overrides tenant
    expect(new URL(calls[0]!.url).searchParams.get("tenant")).toBe("acme");
    expect(new URL(calls[0]!.url).searchParams.get("scope")).toBe("base");
    expect(new URL(calls[1]!.url).searchParams.get("tenant")).toBe("other");
  });

  test("listPersonalMemories never sends a tenant (identity-scoped read)", async () => {
    // The partition comes from the TOKEN, server-side — the client-level
    // default `tenant` must not be merged; an explicit `scope` still travels.
    const { fetchImpl, calls } = stub({ scope: "base", partition: "personal", memories: [] });
    const dna = new DnaClient({ baseUrl: BASE, tenant: "acme", scope: "base", fetch: fetchImpl });
    await dna.listPersonalMemories({ scope: "concierge" });
    const url = new URL(calls[0]!.url);
    expect(url.pathname).toBe("/v1/memories/personal");
    expect(url.searchParams.get("tenant")).toBeNull();
    expect(url.searchParams.get("scope")).toBe("concierge");
  });

  test("path params are substituted (agentPrompt, getProject, board item)", async () => {
    const { fetchImpl, calls } = stub({ ok: 1 });
    const dna = new DnaClient({ baseUrl: BASE, fetch: fetchImpl });
    await dna.agentPrompt("jarvis", { scope: "s" });
    await dna.getProject("my-proj");
    await dna.searchMemories({ q: "hello", k: 3 });
    await dna.getBoard({ scope: "dna-development", recent: 5 });
    await dna.getBoardItem({ scope: "dna-development", name: "s-foo" });
    expect(new URL(calls[0]!.url).pathname).toBe("/v1/agents/jarvis/prompt");
    expect(new URL(calls[1]!.url).pathname).toBe("/v1/projects/my-proj");
    const search = new URL(calls[2]!.url);
    expect(search.pathname).toBe("/v1/memories/search");
    expect(search.searchParams.get("q")).toBe("hello");
    expect(search.searchParams.get("k")).toBe("3");
    expect(new URL(calls[3]!.url).searchParams.get("recent")).toBe("5");
    expect(new URL(calls[4]!.url).searchParams.get("name")).toBe("s-foo");
  });

  test("agentPrompt explain is opt-in (absent by default, sent when asked)", async () => {
    // Provenance on the wire (i-045): the default request carries NO explain
    // param (byte-identical to the historical plain compose); explain: true
    // sends explain=true.
    const { fetchImpl, calls } = stub({ prompt: "p" });
    const dna = new DnaClient({ baseUrl: BASE, fetch: fetchImpl });
    await dna.agentPrompt("jarvis", { scope: "s" });
    await dna.agentPrompt("jarvis", { scope: "s", explain: true });
    expect(new URL(calls[0]!.url).searchParams.has("explain")).toBe(false);
    expect(new URL(calls[1]!.url).searchParams.get("explain")).toBe("true");
  });

  test("importMemories posts the bundle and never sends a tenant", async () => {
    const { fetchImpl, calls } = stub({ imported: 1, skipped: 0, failed: 0, received: 1 });
    // A client-level default tenant is set on purpose: the import is
    // identity-scoped (the server derives the personal partition from the
    // token), so the default must NOT leak onto this request.
    const dna = new DnaClient({ baseUrl: BASE, tenant: "acme", scope: "base", fetch: fetchImpl });
    await dna.importMemories({ bundle: { "@graph": [{ id: "m-1" }] } });

    expect(calls[0]!.method).toBe("POST");
    const url = new URL(calls[0]!.url);
    expect(url.pathname).toBe("/v1/memories/import");
    expect(url.searchParams.get("tenant")).toBeNull();
    expect(url.searchParams.get("scope")).toBe("base");
    // The server-side defaults are mirrored so an omitted option is explicit.
    const body = JSON.parse(calls[0]!.body as string);
    expect(body.as).toBe("both");
    expect(body.dedupe).toBe("id");
    expect(body.bundle["@graph"][0].id).toBe("m-1");
  });

  test("non-2xx throws DnaApiError carrying the detail", async () => {
    const { fetchImpl } = stub({ detail: "unknown project 'nope'" }, 404);
    const dna = new DnaClient({ baseUrl: BASE, fetch: fetchImpl });
    let err: unknown;
    try {
      await dna.getProject("nope");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(DnaApiError);
    expect((err as DnaApiError).status).toBe(404);
    expect((err as DnaApiError).message).toContain("unknown project");
  });

  test("raw client exposes the full typed surface (incl. writes)", async () => {
    const { fetchImpl, calls } = stub({ deleted: "s-foo" });
    const dna = new DnaClient({ baseUrl: BASE, fetch: fetchImpl });
    // The write surface is reachable through .raw with the same generated types.
    await dna.raw.DELETE("/v1/memories/{name}", { params: { path: { name: "s-foo" } } });
    expect(calls[0]!.method).toBe("DELETE");
    expect(new URL(calls[0]!.url).pathname).toBe("/v1/memories/s-foo");
  });

  test("named write methods issue the right verb, path and body", async () => {
    const { fetchImpl, calls } = stub({ ok: 1 });
    const dna = new DnaClient({ baseUrl: BASE, fetch: fetchImpl });

    await dna.rememberMemory({ summary: "a lesson" }, { scope: "s" });
    expect(calls[0]!.method).toBe("POST");
    expect(new URL(calls[0]!.url).pathname).toBe("/v1/memories");

    await dna.deleteMemory("s-foo", { scope: "s" });
    expect(calls[1]!.method).toBe("DELETE");
    expect(new URL(calls[1]!.url).pathname).toBe("/v1/memories/s-foo");

    await dna.setInsightState("i-1", "dismissed");
    expect(calls[2]!.method).toBe("PATCH");
    expect(new URL(calls[2]!.url).pathname).toBe("/v1/insights/i-1/state");

    await dna.setAccountPlan({ account_id: "acct-1", tier_id: "pro" });
    expect(calls[3]!.method).toBe("PUT");
    expect(new URL(calls[3]!.url).pathname).toBe("/v1/account-plan");

    await dna.revokeWorkspaceMember("w1", { target_email: "a@b.c" });
    expect(calls[4]!.method).toBe("POST");
    expect(new URL(calls[4]!.url).pathname).toBe("/v1/workspaces/w1/members/revoke");

    await dna.removeProjectMember("proj", "user@x.y", { actor: "boss@x.y" });
    expect(calls[5]!.method).toBe("DELETE");
    // The `user` path segment is URL-encoded (an email is a legal member id).
    expect(new URL(calls[5]!.url).pathname).toBe("/v1/projects/proj/members/user%40x.y");
  });

  test("workspace-boundary routes do NOT receive the default scope/tenant", async () => {
    // The workspace boundary is resolved from the caller's VERIFIED identity, so
    // a client-level tenant default must never leak onto these routes and imply
    // the caller may pick their own boundary.
    const { fetchImpl, calls } = stub({ ok: 1 });
    const dna = new DnaClient({ baseUrl: BASE, tenant: "acme", scope: "base", fetch: fetchImpl });
    await dna.listWorkspaces();
    await dna.createWorkspace({ name: "Acme" });
    await dna.acceptInvites();
    await dna.createProject({ workspace_id: "w1", name: "P" });
    for (const call of calls) {
      const params = new URL(call.url).searchParams;
      expect(params.get("tenant")).toBeNull();
      expect(params.get("scope")).toBeNull();
    }
  });
});

/**
 * COVERAGE GUARD — the TypeScript twin of `client-py`'s
 * `test_openapi_drift.py::test_client_covers_every_operation`.
 *
 * Every operation in `docs/openapi.json` — of ANY HTTP method — must have a
 * named method on {@link DnaClient}. A Python-only guard cannot see this client:
 * that blind spot is why `listWorkspaces` was missing here long after the Python
 * side had it, and why the write surface was uncovered in both. The map is keyed
 * by `METHOD path`, never by path alone, so a new write on an already-covered
 * path (e.g. `POST` beside an existing `GET`) still trips it.
 */
const COVERED: Record<string, string> = {
  // -- reads --
  "GET /health": "health",
  "GET /v1/agents": "listAgents",
  "GET /v1/agents/{name}/prompt": "agentPrompt",
  "GET /v1/tools": "listTools",
  "GET /v1/genome": "genomeView",
  "GET /v1/memories": "listMemories",
  "GET /v1/memories/personal": "listPersonalMemories",
  "GET /v1/memories/search": "searchMemories",
  "GET /v1/sources": "listSources",
  "GET /v1/insights": "listInsights",
  "GET /v1/insights/metrics": "insightMetrics",
  "GET /v1/orgs": "listOrgs",
  "GET /v1/projects": "listProjects",
  "GET /v1/projects/{slug}": "getProject",
  "GET /v1/projects/{slug}/members": "listProjectMembers",
  "GET /v1/repos": "listRepos",
  "GET /v1/board": "getBoard",
  "GET /v1/board/item": "getBoardItem",
  "GET /v1/workspaces": "listWorkspaces",
  "GET /v1/workspaces/{workspace_id}/members": "listWorkspaceMembers",
  // -- writes --
  "POST /v1/memories": "rememberMemory",
  "POST /v1/memories/import": "importMemories",
  "DELETE /v1/memories/{name}": "deleteMemory",
  "PATCH /v1/insights/{name}/state": "setInsightState",
  "POST /v1/projects": "createProject",
  "POST /v1/projects/{slug}/members": "setProjectMember",
  "DELETE /v1/projects/{slug}/members/{user}": "removeProjectMember",
  "POST /v1/tenants/{tid}/provision-owner": "provisionTenantOwner",
  "PUT /v1/account-plan": "setAccountPlan",
  "POST /v1/workspaces": "createWorkspace",
  "POST /v1/workspaces/accept": "acceptInvites",
  "POST /v1/workspaces/{workspace_id}/invites": "createInvite",
  "POST /v1/workspaces/{workspace_id}/members/revoke": "revokeWorkspaceMember",
  "POST /v1/workspaces/{workspace_id}/provision-owner": "provisionWorkspaceOwner",
};

/**
 * Operations DELIBERATELY left without a named method, each with a stated reason.
 * Empty today — every operation in the spec is a single self-contained call a
 * named method can honestly express. An entry belongs here only if a named method
 * would LIE about how usable the route is.
 */
const UNCOVERED: Record<string, string> = {};

const HTTP_METHODS = new Set([
  "get", "put", "post", "delete", "options", "head", "patch", "trace",
]);

function specOperations(): string[] {
  const specPath = new URL("../../../docs/openapi.json", import.meta.url).pathname;
  const spec = JSON.parse(readFileSync(specPath, "utf-8")) as {
    paths: Record<string, Record<string, unknown>>;
  };
  const ops: string[] = [];
  for (const [path, item] of Object.entries(spec.paths)) {
    for (const verb of Object.keys(item)) {
      if (HTTP_METHODS.has(verb.toLowerCase())) ops.push(`${verb.toUpperCase()} ${path}`);
    }
  }
  return ops.sort();
}

describe("OpenAPI operation coverage", () => {
  test("every operation in the spec has a named client method", () => {
    const uncovered = specOperations().filter(
      (op) => !(op in COVERED) && !(op in UNCOVERED),
    );
    expect(
      uncovered,
      `operation(s) in the API with no named client method: ${uncovered.join(", ")} ` +
        "— add a named method to src/index.ts and map it in COVERED, or, if it " +
        "genuinely should not have one, add it to UNCOVERED with the reason.",
    ).toEqual([]);
  });

  test("every mapped method actually exists on DnaClient", () => {
    const proto = DnaClient.prototype as unknown as Record<string, unknown>;
    for (const [op, name] of Object.entries(COVERED)) {
      expect(typeof proto[name], `DnaClient.${name}() missing for ${op}`).toBe("function");
    }
  });

  test("the coverage map has no entries the spec dropped", () => {
    const ops = new Set(specOperations());
    const stale = [...Object.keys(COVERED), ...Object.keys(UNCOVERED)].filter(
      (op) => !ops.has(op),
    );
    expect(
      stale,
      `coverage map lists operation(s) absent from the spec: ${stale.join(", ")} ` +
        "— the route was removed/renamed; drop the entry (and its client method).",
    ).toEqual([]);
  });

  test("every UNCOVERED entry states a reason", () => {
    for (const [op, reason] of Object.entries(UNCOVERED)) {
      expect(reason.trim(), `UNCOVERED["${op}"] needs a stated reason`).not.toBe("");
    }
  });
});
