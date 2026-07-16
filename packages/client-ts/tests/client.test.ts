/**
 * Usage test for the DNA REST client — drives every named read method against a
 * STUB `fetch` (no live server), asserting the client builds the right method,
 * URL, path substitution, query params (incl. client-level defaults), and the
 * bearer header, and that it unwraps success + throws {@link DnaApiError} on a
 * non-2xx. This is the client's behavioral contract; the OpenAPI-derived types
 * (src/schema.ts) are checked separately by `bun run typecheck`.
 */
import { describe, expect, test } from "bun:test";
import { DnaApiError, DnaClient, createDnaClient } from "../src/index.js";

/** A fetch stub that records each request and returns a canned JSON body.
 * openapi-fetch invokes `fetch(new Request(url, init))`, so the first arg is a
 * `Request`; we read url/method/headers off it. */
function stub(body: unknown, status = 200) {
  const calls: { url: string; method: string; headers: Headers }[] = [];
  const fetchImpl = (async (input: string | URL | Request, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(input, init);
    calls.push({ url: req.url, method: req.method, headers: req.headers });
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
});
