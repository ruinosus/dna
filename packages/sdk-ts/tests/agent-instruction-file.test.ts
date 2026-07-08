/**
 * Agent instruction_file — TS parity with Python test suite.
 */

import { describe, expect, test } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { AgentReader, AgentWriter } from "../src/extensions/helix.js";

function tmp(): string {
  return mkdtempSync(join(tmpdir(), "uaif-"));
}

function writeAgent(bundle: string, frontmatter: string, body = ""): void {
  mkdirSync(bundle, { recursive: true });
  writeFileSync(join(bundle, "AGENT.md"), `---\n${frontmatter}---\n\n${body}`);
}

describe("Agent instruction_file (TS parity)", () => {
  test("resolves relative path and populates instruction", async () => {
    const root = tmp();
    mkdirSync(join(root, "prompts"), { recursive: true });
    writeFileSync(join(root, "prompts", "x.md"), "CANONICAL");
    const bundle = join(root, "agents", "a");
    writeAgent(bundle, "name: a\ninstruction_file: ../../prompts/x.md\n");
    const raw = new AgentReader().read(new FilesystemBundleHandle(bundle));
    expect((raw.spec as any).instruction).toBe("CANONICAL");
    expect((raw.spec as any).instruction_file).toBe("../../prompts/x.md");
  });

  test("rejects absolute path", async () => {
    const bundle = join(tmp(), "agents", "a");
    writeAgent(bundle, "name: a\ninstruction_file: /etc/passwd\n");
    expect(() => new AgentReader().read(new FilesystemBundleHandle(bundle))).toThrow(/relative/);
  });

  test("rejects > 3 '..' segments", async () => {
    const bundle = join(tmp(), "agents", "a");
    writeAgent(bundle, "name: a\ninstruction_file: ../../../../etc/passwd\n");
    expect(() => new AgentReader().read(new FilesystemBundleHandle(bundle))).toThrow(/depth/);
  });

  test("rejects non-empty body + instruction_file", async () => {
    const root = tmp();
    writeFileSync(join(root, "p.md"), "X");
    const bundle = join(root, "agents", "a");
    writeAgent(bundle, "name: a\ninstruction_file: ../p.md\n", "ILLEGAL");
    expect(() => new AgentReader().read(new FilesystemBundleHandle(bundle))).toThrow(/instruction_file/);
  });

  test("rejects legacy frontmatter instruction + instruction_file", async () => {
    const root = tmp();
    writeFileSync(join(root, "p.md"), "X");
    const bundle = join(root, "agents", "a");
    writeAgent(bundle, "name: a\ninstruction: LEGACY\ninstruction_file: ../p.md\n");
    expect(() => new AgentReader().read(new FilesystemBundleHandle(bundle))).toThrow(/frontmatter/);
  });

  test("writer round-trips instruction_file with empty body", async () => {
    const root = tmp();
    writeFileSync(join(root, "p.md"), "X");
    const src = join(root, "in", "agents", "a");
    writeAgent(src, "name: a\ninstruction_file: ../../../p.md\n");
    const raw = new AgentReader().read(new FilesystemBundleHandle(src));

    const dst = join(root, "out", "agents", "a");
    mkdirSync(dst, { recursive: true });
    new AgentWriter().write(new FilesystemBundleHandle(dst), raw);
    const text = readFileSync(join(dst, "AGENT.md"), "utf-8");
    expect(text).toMatch(/instruction_file:/);
    const body = text.replace(/^---\n[\s\S]*?---\n?/, "").trim();
    expect(body).toBe("");
  });
});
