/**
 * ToolRegistry — the kernel's tool-definition registry. TS twin of the Py
 * `dna.kernel.tool_registry.ToolRegistry`, including READ_UMBRELLA_GROUPS /
 * expand_group_aliases. Landed with s-dna-port-surface-parity (closes the
 * "TS kernel has no tool registry" gap the ExtensionHost contract had to
 * footnote).
 *
 * Both sides are now symmetric: registrants construct `ToolDefinition`s
 * directly and call `kernel.tool(td)` inside `Extension.register()`. (The Py
 * `@dna_tool` langchain decorator that once harvested definitions at
 * function-definition time was removed as dead code — it decorated nothing.)
 *
 * Tools are global (not tenant-scoped), so one registry is safely shared
 * across `withTenant` shallow copies — same posture as the Py twin.
 */

import type { ToolDefinition } from "./protocols.js";

/**
 * 'read' umbrella group — not a real group on any tool; an alias that
 * expands to {code, manifest, docs, eval} at filter time. 1:1 with the Py
 * `READ_UMBRELLA_GROUPS`.
 */
export const READ_UMBRELLA_GROUPS: ReadonlySet<string> = new Set([
  "code", "manifest", "docs", "eval",
]);

/**
 * Expand the 'read' umbrella into its constituent groups. Other group
 * names pass through unchanged. 1:1 with the Py `expand_group_aliases`.
 */
export function expandGroupAliases(
  groups?: Iterable<string> | null,
): Set<string> {
  const out = new Set<string>();
  if (!groups) return out;
  for (const g of groups) {
    if (g === "read") {
      for (const u of READ_UMBRELLA_GROUPS) out.add(u);
    } else {
      out.add(g);
    }
  }
  return out;
}

/** Name → ToolDefinition registry with group-aware filtering. */
export class ToolRegistry {
  private readonly _tools = new Map<string, ToolDefinition>();

  /** Register a tool definition. Last-write-wins on same name (idempotent —
   *  factory-pattern registrants may re-register on every factory call). */
  register(td: ToolDefinition): void {
    this._tools.set(td.name, td);
  }

  /** Return a tool definition by name, or `null` if unknown. */
  get(name: string): ToolDefinition | null {
    return this._tools.get(name) ?? null;
  }

  /**
   * Return registered tool definitions, optionally filtered.
   *
   * - `{ group: "cognitive" }` — exactly that group
   * - `{ groups: ["cognitive", "manifest"] }` — union of groups
   * - `{ groups: ["read"] }` — expands via the 'read' umbrella alias
   *
   * Pass nothing to get the full catalog. 1:1 with the Py `get_many`.
   */
  getMany(opts: {
    group?: string | null;
    groups?: Iterable<string> | null;
  } = {}): ToolDefinition[] {
    const group = opts.group ?? null;
    const extra = opts.groups ? [...opts.groups] : [];
    if (group === null && extra.length === 0) {
      return [...this._tools.values()];
    }
    const wanted = expandGroupAliases([
      ...(group !== null ? [group] : []),
      ...extra,
    ]);
    return [...this._tools.values()].filter(
      (td) => td.group !== null && wanted.has(td.group),
    );
  }

  /** Reverse-build `{group: [toolNames…]}` (names sorted) from the registry. */
  groups(): Record<string, string[]> {
    const out: Record<string, string[]> = {};
    for (const td of this._tools.values()) {
      if (!td.group) continue;
      (out[td.group] ??= []).push(td.name);
    }
    for (const names of Object.values(out)) names.sort();
    return out;
  }
}
