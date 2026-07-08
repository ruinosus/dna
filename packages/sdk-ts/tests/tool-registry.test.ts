/**
 * s-dna-port-surface-parity — TS tool registry (twin of the Py
 * kernel/tool_registry.py + the portable half of tools.py).
 *
 * Covers: kernel.tool()/getTool()/getTools()/listToolGroups(), group
 * filtering + the 'read' umbrella expansion, last-write-wins
 * registration, ExtensionHost.tool inside register(), and the callable
 * pass-through contract (never wrapped).
 */
import { describe, expect, test } from "bun:test";

import { Kernel } from "../src/kernel/index.js";
import { ToolDefinition } from "../src/kernel/protocols.js";
import type { Extension, ExtensionHost } from "../src/kernel/protocols.js";
import {
  READ_UMBRELLA_GROUPS,
  expandGroupAliases,
} from "../src/kernel/tool-registry.js";

function td(name: string, group: string | null, extra: Partial<{
  hitl: boolean; callable: unknown; summary: string;
}> = {}): ToolDefinition {
  return new ToolDefinition({ name, group, ...extra });
}

describe("kernel tool registry", () => {
  test("register + lookup + full catalog", () => {
    const k = new Kernel();
    expect(k.getTool("nope")).toBeNull();
    k.tool(td("create_dream", "cognitive"));
    k.tool(td("read_manifest", "manifest"));
    expect(k.getTool("create_dream")?.group).toBe("cognitive");
    expect(k.getTools().map((t) => t.name).sort()).toEqual([
      "create_dream", "read_manifest",
    ]);
  });

  test("group filter: exact group + union of groups", () => {
    const k = new Kernel();
    k.tool(td("a", "cognitive"));
    k.tool(td("b", "manifest"));
    k.tool(td("c", "web"));
    k.tool(td("ungrouped", null));
    expect(k.getTools({ group: "cognitive" }).map((t) => t.name)).toEqual(["a"]);
    expect(
      k.getTools({ groups: ["cognitive", "web"] }).map((t) => t.name).sort(),
    ).toEqual(["a", "c"]);
    // Ungrouped tools appear only in the unfiltered catalog (Py parity).
    expect(k.getTools().map((t) => t.name)).toContain("ungrouped");
    expect(
      k.getTools({ groups: ["cognitive", "web"] }).map((t) => t.name),
    ).not.toContain("ungrouped");
  });

  test("'read' umbrella expands to code|manifest|docs|eval", () => {
    expect([...expandGroupAliases(["read"])].sort()).toEqual(
      [...READ_UMBRELLA_GROUPS].sort(),
    );
    expect([...expandGroupAliases(["read", "web"])].sort()).toEqual(
      [...READ_UMBRELLA_GROUPS, "web"].sort(),
    );
    const k = new Kernel();
    k.tool(td("code_tool", "code"));
    k.tool(td("eval_tool", "eval"));
    k.tool(td("web_tool", "web"));
    expect(
      k.getTools({ groups: ["read"] }).map((t) => t.name).sort(),
    ).toEqual(["code_tool", "eval_tool"]);
  });

  test("last-write-wins on same name (idempotent factory re-calls)", () => {
    const k = new Kernel();
    k.tool(td("dup", "manifest"));
    k.tool(td("dup", "cognitive"));
    expect(k.getTools().length).toBe(1);
    expect(k.getTool("dup")?.group).toBe("cognitive");
  });

  test("listToolGroups reverse-builds {group: [names…]} sorted", () => {
    const k = new Kernel();
    k.tool(td("z_tool", "cognitive"));
    k.tool(td("a_tool", "cognitive"));
    k.tool(td("m_tool", "manifest"));
    k.tool(td("ungrouped", null));
    expect(k.listToolGroups()).toEqual({
      cognitive: ["a_tool", "z_tool"],
      manifest: ["m_tool"],
    });
  });

  test("getCallable returns the registrant's invocable, never wrapped", () => {
    const k = new Kernel();
    const fn = async (x: string): Promise<string> => x;
    k.tool(td("passthrough", "code", { callable: fn }));
    expect(k.getTool("passthrough")?.getCallable()).toBe(fn);
  });

  test("extensions register tools through ExtensionHost.tool()", () => {
    const ext: Extension = {
      name: "tooling-ext",
      version: "1.0.0",
      register(kernel: ExtensionHost): void {
        kernel.tool(td("ext_tool", "docs", { summary: "from extension" }));
      },
    };
    const k = new Kernel();
    k.load(ext);
    expect(k.getTool("ext_tool")?.summary).toBe("from extension");
    expect(k.getTools({ groups: ["read"] }).map((t) => t.name)).toEqual([
      "ext_tool",
    ]);
  });

  test("ToolDefinition defaults mirror the Py dataclass", () => {
    const t = new ToolDefinition({ name: "bare" });
    expect(t.group).toBeNull();
    expect(t.description).toBe("");
    expect(t.summary).toBe("");
    expect(t.argsSchema).toEqual({});
    expect(t.hitl).toBe(false);
    expect(t.scope).toBeNull();
    expect(t.source).toBe("");
    expect(t.getCallable()).toBeNull();
  });
});
