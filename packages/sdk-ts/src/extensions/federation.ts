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

import type { ExtensionHost, Extension } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";

const API_VERSION = "github.com/ruinosus/dna/federation/v1";

// ── RBAC (absorption phase 6a, design §6.4) ─────────────────────────────────
// Read/write tool governance + per-tool role floors, mirroring foundry-assured's
// McpServer registry (apps/backend/app/agents/mcp/registry.py) adapted to DNA's
// role ladder. Foundry uses a flat named-grant set (Reader/Author/Approver/Admin);
// DNA's ladder is rank-based (portfolio Role Kind: guest < member < admin < owner,
// "highest-role-wins compares rank"), so the floor is a RANK comparison, not set
// membership. PURE functions — no network/framework — 1:1 twin of
// dna/extensions/federation/__init__.py.
//
// Back-compat is SACRED: the flat allowed_tools allowlist is unchanged; the
// read/write split + role floors are ADDITIVE, OPTIONAL refinements. Undeclared
// split (both empty) => RBAC OFF, allowed_tools governs alone (as before).

/** The standard DNA ladder ranks (higher = more access). Custom rungs can be
 * injected via the `roleRanks` param; the pure default is this ladder. */
export const STANDARD_ROLE_RANKS: Record<string, number> = {
  guest: 0,
  member: 10,
  admin: 20,
  owner: 30,
};

type Spec = Record<string, unknown>;
type RoleRanks = Record<string, number>;

function specDict(spec: unknown): Spec {
  return (spec ?? {}) as Spec;
}

function rank(roleId: string, roleRanks?: RoleRanks): number {
  const ranks = roleRanks ?? STANDARD_ROLE_RANKS;
  return roleId in ranks ? ranks[roleId] : -1;
}

function maxRank(roles: Iterable<string>, roleRanks?: RoleRanks): number {
  const rs = [...roles].map((r) => rank(r, roleRanks));
  return rs.length ? Math.max(...rs) : -1;
}

function satisfies(
  roles: Iterable<string>,
  floor: string,
  roleRanks?: RoleRanks,
): boolean {
  const floorRank = rank(floor, roleRanks);
  if (floorRank < 0) return false; // unknown floor → deny (fail-closed)
  return maxRank(roles, roleRanks) >= floorRank;
}

/** 'read' | 'write'. Fail-closed: a tool on NEITHER list is a WRITE — an
 * unclassified new tool can't slip through as an open read. Mirrors foundry. */
export function classifyTool(spec: unknown, toolName: string): "read" | "write" {
  const s = specDict(spec);
  const reads = (s.read_tools as string[]) ?? [];
  return reads.includes(toolName) ? "read" : "write";
}

/** [reads, writes] this caller may see, gated by role. A no-role caller sees
 * nothing (fail-closed). Mirrors foundry's visible_tools. */
export function visibleTools(
  spec: unknown,
  roles: Iterable<string>,
  roleRanks?: RoleRanks,
): [string[], string[]] {
  const s = specDict(spec);
  const reads = ((s.read_tools as string[]) ?? []).slice();
  const writes = ((s.write_tools as string[]) ?? []).slice();
  const minRole = (s.min_role as string) || "guest";
  const minRoleWrite = (s.min_role_write as string) || "member";
  const visibleReads = satisfies(roles, minRole, roleRanks) ? reads : [];
  const visibleWrites = satisfies(roles, minRoleWrite, roleRanks) ? writes : [];
  return [visibleReads, visibleWrites];
}

export interface ResolvedTools {
  rbac: boolean;
  reads: string[];
  writes: string[];
  allowed: string[];
}

/** Effective tool governance for a caller against a federation doc.
 *
 * - rbac false (legacy / no split declared): allowed_tools is returned untouched
 *   (empty = all), reads/writes empty, NO role gating — the SACRED back-compat
 *   path, exactly as before.
 * - rbac true (split declared): reads/writes are the role-gated visible sets; a
 *   non-empty allowed_tools is an outer bound (stricter-of-both — tightens only),
 *   mirroring foundry's registry ∧ connection min-role. */
export function resolveTools(
  spec: unknown,
  roles?: Iterable<string>,
  roleRanks?: RoleRanks,
): ResolvedTools {
  const s = specDict(spec);
  const roleSet = new Set(roles ?? []);
  const readTools = (s.read_tools as string[]) ?? [];
  const writeTools = (s.write_tools as string[]) ?? [];
  const allowed = ((s.allowed_tools as string[]) ?? []).slice();
  const rbacOn = readTools.length > 0 || writeTools.length > 0;
  if (!rbacOn) {
    return { rbac: false, reads: [], writes: [], allowed };
  }
  let [reads, writes] = visibleTools(s, roleSet, roleRanks);
  if (allowed.length) {
    const aset = new Set(allowed);
    reads = reads.filter((t) => aset.has(t));
    writes = writes.filter((t) => aset.has(t));
  }
  return { rbac: true, reads, writes, allowed };
}

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
        read_tools: {
          type: "array",
          items: { type: "string" },
          default: [],
          description:
            "RBAC read set (§6.4): non-mutating tool names callable by roles at or above min_role. ADDITIVE optional refinement over allowed_tools — when read_tools and write_tools are both empty the split is undeclared, RBAC is OFF, and allowed_tools governs alone (back-compat). When declared, a tool in NEITHER read_tools nor write_tools is not exposed (fail-closed).",
        },
        write_tools: {
          type: "array",
          items: { type: "string" },
          default: [],
          description:
            "RBAC write set (§6.4): mutating tool names callable by roles at or above min_role_write. These are the tools routed through HITL confirmation. An unclassified tool is treated as a write (fail-closed).",
        },
        min_role: {
          type: "string",
          default: "guest",
          description:
            "Role floor for read_tools — the lowest ladder rung (guest<member<admin<owner; highest-role-wins compares rank) whose members may call read tools.",
        },
        min_role_write: {
          type: "string",
          default: "member",
          description:
            "Role floor for write_tools — the lowest ladder rung whose members may call write (mutating) tools.",
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

  register(kernel: ExtensionHost): void {
    kernel.kind(new MCPFederationKind());
  }
}
