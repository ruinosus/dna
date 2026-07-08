/**
 * MCPFederation schema v2 + Agent.spec.mcp_servers — TS twin of
 * packages/sdk-py/tests/test_mcp_federation_v2.py (keep assertions in sync).
 *
 * Story: s-mcp-servers-on-agent (f-declarative-tools-mcp).
 * Spec: docs/superpowers/specs/2026-07-07-mcp-first-tools-design.md §5.1.
 */
import { describe, expect, test } from "bun:test";

import { FederationExtension } from "../src/extensions/federation.js";
import { AgentSpecSchema } from "../src/kernel/models.js";
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

describe("MCPFederation schema v2", () => {
  const schema = federationKind().schema() as Record<string, any>;

  test("v2 fields present", () => {
    const props = schema.properties as Record<string, any>;
    for (const f of [
      "transport", "url", "command", "args", "env", "cwd",
      "tool_prefix", "enabled", "allowed_tools", "timeout_s",
      "auth", "propagate_tenant", "health_check", "tags",
    ]) {
      expect(props).toHaveProperty(f);
    }
    expect(props.transport.enum).toEqual(["stdio", "streamable_http"]);
    expect(props.transport.default).toBe("stdio");
    expect(props.timeout_s.default).toBe(30);
  });

  test("auth carries env-var NAMES only (no secret-value field)", () => {
    const auth = schema.properties.auth;
    expect(auth.additionalProperties).toBe(false);
    expect(Object.keys(auth.properties).sort()).toEqual(["env", "header", "kind"]);
    expect(auth.properties.kind.enum).toEqual(["none", "bearer_env", "header_env"]);
  });

  test("conditional required guards both transports (v1 back-compat)", () => {
    // The `required: [transport]` inside the `if` is load-bearing —
    // absent transport must fall to the else (stdio) branch so v1 docs
    // (command only) stay valid. Assert the exact shape.
    expect(schema.allOf).toEqual([
      {
        if: {
          properties: { transport: { const: "streamable_http" } },
          required: ["transport"],
        },
        then: { required: ["url"] },
        else: { required: ["command"] },
      },
    ]);
    // And no top-level required survives from v1.
    expect(schema.required).toBeUndefined();
  });

  test("describe/summary handle both transports", () => {
    const kind = federationKind() as any;
    const httpDoc = {
      spec: {
        transport: "streamable_http",
        url: "https://mcp.draw.io/mcp",
        tool_prefix: "drawio_",
      },
      metadata: {},
    };
    expect(kind.describe(httpDoc)).toBe("https://mcp.draw.io/mcp (drawio_)");
    expect(kind.summary(httpDoc).transport).toBe("streamable_http");

    const v1Doc = { spec: { command: "npx", tool_prefix: "g_" }, metadata: {} };
    expect(kind.describe(v1Doc)).toBe("npx (g_)");
    expect(kind.summary(v1Doc).transport).toBe("stdio");
  });
});

describe("Agent.spec.mcp_servers", () => {
  test("parses string and object entries", () => {
    const spec = AgentSpecSchema.parse({
      instruction: "x",
      mcp_servers: [
        "web-search",
        { ref: "drawio", allowed_tools: ["search_shapes"], timeout_s: 20 },
      ],
    });
    expect(spec.mcp_servers).toEqual([
      "web-search",
      { ref: "drawio", allowed_tools: ["search_shapes"], timeout_s: 20 },
    ]);
  });

  test("defaults to empty", () => {
    expect(AgentSpecSchema.parse({}).mcp_servers).toEqual([]);
  });

  test("object entries require ref", () => {
    expect(() =>
      AgentSpecSchema.parse({ mcp_servers: [{ allowed_tools: ["x"] }] }),
    ).toThrow();
  });
});
