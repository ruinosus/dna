/**
 * MCPFederation read/write + min-role RBAC — TS twin of
 * packages/sdk-py/tests/test_mcp_federation_rbac.py (keep field lists,
 * RBAC semantics, and back-compat cases in sync).
 *
 * Absorption phase 6a (copilot-absorption design §6.4): extend the flat
 * allowed_tools allowlist with read/write tool governance + per-tool role
 * floors, mirroring foundry-assured's McpServer registry, adapted to DNA's
 * rank-based role ladder (guest < member < admin < owner, highest-role-wins).
 *
 * Back-compat is SACRED: allowed_tools is unchanged; the split + floors are
 * additive/optional — a legacy doc behaves exactly as before.
 */
import { describe, expect, test } from "bun:test";

import {
  FederationExtension,
  STANDARD_ROLE_RANKS,
  classifyTool,
  resolveTools,
  visibleTools,
} from "../src/extensions/federation.js";
import type { KindPort } from "../src/kernel/protocols.js";

function federationKind(): KindPort {
  let captured: KindPort | undefined;
  new FederationExtension().register({
    kind(kp: KindPort) {
      captured = kp;
    },
  });
  if (!captured) throw new Error("FederationExtension registered no kind");
  return captured;
}

describe("MCPFederation RBAC schema fields", () => {
  const schema = federationKind().schema() as Record<string, any>;

  test("rbac fields present with DNA-ladder defaults", () => {
    const props = schema.properties as Record<string, any>;
    for (const f of ["read_tools", "write_tools", "min_role", "min_role_write"]) {
      expect(props).toHaveProperty(f);
    }
    expect(props.read_tools.default).toEqual([]);
    expect(props.write_tools.default).toEqual([]);
    expect(props.min_role.default).toBe("guest");
    expect(props.min_role_write.default).toBe("member");
  });

  test("v2 fields untouched (extension is additive)", () => {
    const props = schema.properties as Record<string, any>;
    for (const f of [
      "transport", "url", "command", "args", "env", "cwd",
      "tool_prefix", "enabled", "allowed_tools", "timeout_s",
      "auth", "propagate_tenant", "health_check", "tags",
    ]) {
      expect(props).toHaveProperty(f);
    }
  });
});

describe("standard role ladder", () => {
  test("standard ranks", () => {
    expect(STANDARD_ROLE_RANKS).toEqual({
      guest: 0, member: 10, admin: 20, owner: 30,
    });
  });
});

describe("classifyTool (fail-closed)", () => {
  const spec = { read_tools: ["search"], write_tools: ["deploy"] };
  test("read tool → read", () => {
    expect(classifyTool(spec, "search")).toBe("read");
  });
  test("write tool → write", () => {
    expect(classifyTool(spec, "deploy")).toBe("write");
  });
  test("unclassified → write (fail-closed)", () => {
    expect(classifyTool(spec, "mystery_new_tool")).toBe("write");
  });
});

describe("visibleTools (role-gated)", () => {
  const SPEC = {
    read_tools: ["search", "fetch"],
    write_tools: ["deploy"],
    min_role: "guest",
    min_role_write: "member",
  };

  test("guest sees reads, not writes", () => {
    const [reads, writes] = visibleTools(SPEC, ["guest"]);
    expect(reads).toEqual(["search", "fetch"]);
    expect(writes).toEqual([]);
  });

  test("member sees reads and writes", () => {
    const [reads, writes] = visibleTools(SPEC, ["member"]);
    expect(reads).toEqual(["search", "fetch"]);
    expect(writes).toEqual(["deploy"]);
  });

  test("below min_role denied read", () => {
    const [reads] = visibleTools({ ...SPEC, min_role: "admin" }, ["member"]);
    expect(reads).toEqual([]);
  });

  test("below min_role_write denied write", () => {
    const [, writes] = visibleTools(SPEC, ["guest"]);
    expect(writes).toEqual([]);
  });

  test("no role sees nothing", () => {
    const [reads, writes] = visibleTools(SPEC, []);
    expect(reads).toEqual([]);
    expect(writes).toEqual([]);
  });

  test("highest-role-wins", () => {
    const [reads, writes] = visibleTools(SPEC, ["guest", "admin"]);
    expect(reads).toEqual(["search", "fetch"]);
    expect(writes).toEqual(["deploy"]);
  });

  test("unknown floor is fail-closed", () => {
    const [reads] = visibleTools({ ...SPEC, min_role: "wizard" }, ["owner"]);
    expect(reads).toEqual([]);
  });

  test("role_ranks override honors a custom ladder", () => {
    const spec = { read_tools: ["search"], min_role: "auditor" };
    const [reads] = visibleTools(spec, ["auditor"], {
      guest: 0, auditor: 5, member: 10,
    });
    expect(reads).toEqual(["search"]);
  });
});

describe("resolveTools back-compat (SACRED)", () => {
  test("legacy allowed_tools behaves exactly as before", () => {
    const legacy = { allowed_tools: ["search", "deploy"] };
    const got = resolveTools(legacy, []);
    expect(got.rbac).toBe(false);
    expect(got.allowed).toEqual(["search", "deploy"]);
    expect(got.reads).toEqual([]);
    expect(got.writes).toEqual([]);
  });

  test("empty allowed means all, unchanged", () => {
    const got = resolveTools({}, []);
    expect(got.rbac).toBe(false);
    expect(got.allowed).toEqual([]);
  });

  test("split declared turns RBAC on", () => {
    const spec = {
      read_tools: ["search"],
      write_tools: ["deploy"],
      min_role_write: "member",
    };
    const got = resolveTools(spec, ["member"]);
    expect(got.rbac).toBe(true);
    expect(got.reads).toEqual(["search"]);
    expect(got.writes).toEqual(["deploy"]);
  });

  test("allowed_tools can only tighten the split (stricter-of-both)", () => {
    const spec = {
      read_tools: ["search", "fetch"],
      write_tools: ["deploy", "purge"],
      allowed_tools: ["search", "deploy"],
      min_role_write: "member",
    };
    const got = resolveTools(spec, ["member"]);
    expect(got.reads).toEqual(["search"]);
    expect(got.writes).toEqual(["deploy"]);
  });
});
