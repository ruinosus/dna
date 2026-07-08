/**
 * FederationExtension — Phase 14r MCP Federation (schema v2, 2026-07-07).
 *
 * Declares the `MCPFederation` Kind: an external MCP server whose tools
 * DNA agents consume via `Agent.spec.mcp_servers` (primary,
 * s-mcp-servers-on-agent) or via the DNA-as-MCP-server proxy
 * (legacy Phase 14r direction). Transports: stdio | streamable_http.
 * Auth carries env-var NAMES only — never secret values.
 *
 * Schema v2 is fully backward-compatible with v1 docs: `transport`
 * defaults to `stdio` and every new field is optional.
 *
 * 1:1 parity with python/dna/extensions/federation/__init__.py.
 * The TS SDK ships schema/Kind parity only — the agent runtime (and the
 * MCP client) is Python-only by design (spec §3).
 */

import type { Extension, KindPort } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";

const API_VERSION = "github.com/ruinosus/dna/federation/v1";

class MCPFederationKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "MCPFederation";
  readonly alias = "federation-mcp";
  readonly origin = "github.com/ruinosus/dna/federation";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("federations");
  readonly graphStyle = { fill: "#F97316", stroke: "#EA580C", textColor: "#fff" };
  readonly asciiIcon = "🛰️";
  readonly displayLabel = "MCP Federations";
  readonly docs =
    "An MCPFederation declares an external MCP server whose tools DNA " +
    "agents consume: a Agent lists the doc's name in " +
    "spec.mcp_servers and the harness loads the remote tools as " +
    "first-class agent tools (zero code, zero deploy). Transports: " +
    "stdio (command/args/env/cwd) or streamable_http (url). Auth " +
    "carries env-var NAMES only — never secret values. allowed_tools " +
    "bounds what any agent can get; enabled: false is the declarative " +
    "kill-switch. Docs in _lib/federations/ are inherited by every " +
    "scope. Also consumed by the DNA-as-MCP-server proxy (Phase 14r).";

  dependencies() { return null; }
  schema() {
    // v2 (spec 2026-07-07-mcp-first-tools-design.md §5.1). Back-compat:
    // every v1 doc (required command, stdio implied) stays valid —
    // transport defaults to stdio and command is enforced for stdio
    // (resp. url for streamable_http) via allOf/if-then instead of a
    // top-level required: [command].
    return {
      type: "object",
      additionalProperties: true,
      properties: {
        transport: {
          type: "string",
          enum: ["stdio", "streamable_http"],
          default: "stdio",
          description:
            "How to reach the server: stdio subprocess (default, v1) or Streamable HTTP.",
        },
        url: {
          type: "string",
          description: "Server endpoint. Required when transport=streamable_http.",
        },
        command: {
          type: "string",
          description:
            "Executable to run (resolved via PATH). Required when transport=stdio.",
        },
        args: { type: "array", items: { type: "string" }, default: [] },
        env: {
          type: "object",
          additionalProperties: { type: "string" },
          default: {},
          description: "Extra env vars merged onto os.environ for the subprocess.",
        },
        cwd: {
          type: ["string", "null"],
          description: "Working directory; null = scope dir.",
        },
        tool_prefix: {
          type: "string",
          description: "Prepended to every proxied tool name (e.g. 'graphify_').",
          default: "",
        },
        enabled: {
          type: "boolean",
          default: true,
          description:
            "Disable without deleting the doc — declarative kill-switch, no deploy.",
        },
        allowed_tools: {
          type: "array",
          items: { type: "string" },
          default: [],
          description:
            "Server-level allowlist of remote tool names (pre-prefix). Empty = all.",
        },
        timeout_s: {
          type: "integer",
          default: 30,
          description:
            "Per-call timeout default (seconds). Per-agent entry may override.",
        },
        auth: {
          type: "object",
          additionalProperties: false,
          description:
            "Auth by env-var NAME — the value is read from the process env at connect time and never stored in docs, logs, or events.",
          properties: {
            kind: {
              type: "string",
              enum: ["none", "bearer_env", "header_env"],
              default: "none",
            },
            env: {
              type: "string",
              description: "Name of the env var holding the secret value.",
            },
            header: {
              type: "string",
              description:
                "Header to carry the value (header_env only; bearer_env implies Authorization: Bearer).",
            },
          },
        },
        propagate_tenant: {
          type: "boolean",
          default: true,
          description:
            "HTTP transport: stamp X-DNA-Tenant-Effective / X-DNA-Scope / X-DNA-Agent headers.",
        },
        health_check: {
          type: "object",
          additionalProperties: true,
          properties: {
            interval_s: { type: "integer", default: 30 },
            timeout_s: { type: "integer", default: 5 },
          },
        },
        tags: { type: "array", items: { type: "string" }, default: [] },
      },
      allOf: [
        {
          // NOTE: required: [transport] inside the `if` is load-bearing —
          // without it an absent `transport` matches the const vacuously
          // and v1 docs would be forced to carry `url`.
          if: {
            properties: { transport: { const: "streamable_http" } },
            required: ["transport"],
          },
          then: { required: ["url"] },
          else: { required: ["command"] },
        },
      ],
    };
  }
  describe(doc: Document): string | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const transport = (spec.transport as string) || "stdio";
    const target =
      ((transport === "streamable_http" ? spec.url : spec.command) as string) ?? "?";
    const prefix = (spec.tool_prefix as string) ?? "";
    return `${target || "?"} (${prefix || "no-prefix"})`;
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      transport: (spec.transport as string) || "stdio",
      url: spec.url ?? "",
      command: spec.command ?? "",
      tool_prefix: spec.tool_prefix ?? "",
      enabled: spec.enabled ?? true,
      tags: spec.tags ?? [],
    };
  }
}

export class FederationExtension implements Extension {
  readonly name = "federation";
  readonly version = "1.0.0";

  register(kernel: unknown): void {
    const k = kernel as { kind(kp: KindPort): void };
    k.kind(new MCPFederationKind());
  }
}
