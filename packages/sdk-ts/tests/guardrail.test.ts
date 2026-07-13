import { describe, test, expect, beforeEach } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { mkdtempSync, writeFileSync, mkdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { GuardrailExtension, GuardrailReader, GuardrailWriter } from "../src/extensions/guardrails.js";
import { Kernel } from "../src/kernel/index.js";

// ---------------------------------------------------------------------------
// GuardrailExtension
// ---------------------------------------------------------------------------

describe("GuardrailExtension", () => {
  test("registers kind, reader, and writer on the kernel", async () => {
    const k = new Kernel();
    k.load(new GuardrailExtension());

    const kindPort = k._kinds.get("github.com/ruinosus/dna/v1\0Guardrail");
    expect(kindPort).toBeDefined();
    expect(kindPort?.alias).toBe("guardrails-guardrail");
  });

  test("kind has correct properties", async () => {
    const k = new Kernel();
    k.load(new GuardrailExtension());

    const kp = k._kinds.get("github.com/ruinosus/dna/v1\0Guardrail")!;
    expect(kp.apiVersion).toBe("github.com/ruinosus/dna/v1");
    expect(kp.kind).toBe("Guardrail");
    expect(kp.alias).toBe("guardrails-guardrail");
    expect(kp.origin).toBe("github.com/ruinosus/dna/guardrails");
    expect(kp.isRoot).toBe(false);
    expect(kp.isPromptTarget).toBe(false);
    expect(kp.promptTargetPriority).toBe(0);
    expect(kp.flattenInContext).toBe(false);
  });

  test("null-returning methods return null", async () => {
    const k = new Kernel();
    k.load(new GuardrailExtension());
    const kp = k._kinds.get("github.com/ruinosus/dna/v1\0Guardrail")!;

    expect(kp.depFilters()).toBeNull();
    expect(kp.getDefaultAgentName(null)).toBeNull();
    expect(kp.getLayerPolicies(null)).toBeNull();
    expect(kp.describe(null)).toBeNull();
    // summary now returns {severity, scope, rules} for Guardrail docs
    const sum = kp.summary({ spec: { severity: "hard", scope: "output", rules: ["a"] } } as never);
    expect(sum).not.toBeNull();
    expect(sum?.severity).toBe("hard");
    expect(sum?.scope).toBe("output");
    expect(sum?.rules).toBe(1);
    expect(kp.promptTemplate()).toBeNull();
  });

  test("parse returns typed Guardrail object", async () => {
    const k = new Kernel();
    k.load(new GuardrailExtension());
    const kp = k._kinds.get("github.com/ruinosus/dna/v1\0Guardrail")!;

    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Guardrail",
      metadata: { name: "test-guardrail" },
      spec: { rules: ["no PII", "no profanity"], severity: "error", scope: "input" },
    };

    const typed = kp.parse(raw) as Record<string, unknown>;
    expect(typed.kind).toBe("Guardrail");
    expect(typed.apiVersion).toBe("github.com/ruinosus/dna/v1");
    const spec = typed.spec as Record<string, unknown>;
    expect(spec.rules).toEqual(["no PII", "no profanity"]);
    expect(spec.severity).toBe("error");
    expect(spec.scope).toBe("input");
  });

  test("parse applies defaults when spec is empty", async () => {
    const k = new Kernel();
    k.load(new GuardrailExtension());
    const kp = k._kinds.get("github.com/ruinosus/dna/v1\0Guardrail")!;

    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Guardrail",
      metadata: { name: "minimal" },
    };

    const typed = kp.parse(raw) as Record<string, unknown>;
    const spec = typed.spec as Record<string, unknown>;
    expect(spec.rules).toEqual([]);
    expect(spec.severity).toBe("warn");
    expect(spec.scope).toBe("both");
  });
});

// ---------------------------------------------------------------------------
// GuardrailReader
// ---------------------------------------------------------------------------

describe("GuardrailReader", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "guardrail-test-"));
  });

  test("detect returns false when GUARDRAIL.md is absent", async () => {
    const reader = new GuardrailReader();
    expect(reader.detect(new FilesystemBundleHandle(tmpDir))).toBe(false);
  });

  test("detect returns true when GUARDRAIL.md is present", async () => {
    writeFileSync(join(tmpDir, "GUARDRAIL.md"), "---\nname: test\n---\n");
    const reader = new GuardrailReader();
    expect(reader.detect(new FilesystemBundleHandle(tmpDir))).toBe(true);
  });

  test("reads name and description from frontmatter", async () => {
    const content = `---
name: pii-guard
desc: Prevent PII leakage
---

- No phone numbers
- No email addresses
`;
    writeFileSync(join(tmpDir, "GUARDRAIL.md"), content);
    const reader = new GuardrailReader();
    const raw = reader.read(new FilesystemBundleHandle(tmpDir));

    const meta = raw.metadata as Record<string, unknown>;
    expect(meta.name).toBe("pii-guard");
    expect(meta.description).toBe("Prevent PII leakage");
  });

  test("reads rules from bullet list in body", async () => {
    const content = `---
name: my-guard
---

- No profanity
- No violence
- No PII
`;
    writeFileSync(join(tmpDir, "GUARDRAIL.md"), content);
    const reader = new GuardrailReader();
    const raw = reader.read(new FilesystemBundleHandle(tmpDir));
    const spec = raw.spec as Record<string, unknown>;

    expect(spec.rules).toEqual(["No profanity", "No violence", "No PII"]);
  });

  test("reads severity and scope from frontmatter", async () => {
    const content = `---
name: strict-guard
severity: error
scope: input
---

- No leaks
`;
    writeFileSync(join(tmpDir, "GUARDRAIL.md"), content);
    const reader = new GuardrailReader();
    const raw = reader.read(new FilesystemBundleHandle(tmpDir));
    const spec = raw.spec as Record<string, unknown>;

    expect(spec.severity).toBe("error");
    expect(spec.scope).toBe("input");
  });

  test("applies defaults for severity and scope when absent", async () => {
    const content = `---
name: default-guard
---

- A rule
`;
    writeFileSync(join(tmpDir, "GUARDRAIL.md"), content);
    const reader = new GuardrailReader();
    const raw = reader.read(new FilesystemBundleHandle(tmpDir));
    const spec = raw.spec as Record<string, unknown>;

    expect(spec.severity).toBe("warn");
    expect(spec.scope).toBe("both");
  });

  test("sets apiVersion and kind correctly", async () => {
    writeFileSync(join(tmpDir, "GUARDRAIL.md"), "---\nname: test\n---\n");
    const reader = new GuardrailReader();
    const raw = reader.read(new FilesystemBundleHandle(tmpDir));

    expect(raw.apiVersion).toBe("github.com/ruinosus/dna/v1");
    expect(raw.kind).toBe("Guardrail");
  });
});

// ---------------------------------------------------------------------------
// GuardrailWriter
// ---------------------------------------------------------------------------

describe("GuardrailWriter", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "guardrail-writer-test-"));
  });

  test("canWrite returns true for Guardrail kind", async () => {
    const writer = new GuardrailWriter();
    expect(writer.canWrite({ kind: "Guardrail" })).toBe(true);
  });

  test("canWrite returns false for other kinds", async () => {
    const writer = new GuardrailWriter();
    expect(writer.canWrite({ kind: "Skill" })).toBe(false);
    expect(writer.canWrite({ kind: "Genome" })).toBe(false);
    expect(writer.canWrite({})).toBe(false);
  });

  test("roundtrip: write then read produces same data", async () => {
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Guardrail",
      metadata: { name: "roundtrip-guard", description: "A roundtrip test" },
      spec: { rules: ["No PII", "No profanity"], severity: "warn", scope: "both" },
    };

    const bundleDir = join(tmpDir, "roundtrip-guard");
    const writer = new GuardrailWriter();
    writer.write(new FilesystemBundleHandle(bundleDir), raw);

    const reader = new GuardrailReader();
    expect(reader.detect(new FilesystemBundleHandle(bundleDir))).toBe(true);

    const readBack = reader.read(new FilesystemBundleHandle(bundleDir));
    const meta = readBack.metadata as Record<string, unknown>;
    const spec = readBack.spec as Record<string, unknown>;

    expect(meta.name).toBe("roundtrip-guard");
    expect(meta.description).toBe("A roundtrip test");
    expect(spec.rules).toEqual(["No PII", "No profanity"]);
    expect(spec.severity).toBe("warn");
    expect(spec.scope).toBe("both");
  });

  test("omits severity from GUARDRAIL.md when it is default (warn)", async () => {
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Guardrail",
      metadata: { name: "default-severity" },
      spec: { rules: ["a rule"], severity: "warn", scope: "both" },
    };

    const bundleDir = join(tmpDir, "default-severity");
    const writer = new GuardrailWriter();
    writer.write(new FilesystemBundleHandle(bundleDir), raw);

    const content = readFileSync(join(bundleDir, "GUARDRAIL.md"), "utf-8");
    expect(content).not.toContain("severity:");
    expect(content).not.toContain("scope:");
  });

  test("writes non-default severity and scope to GUARDRAIL.md", async () => {
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Guardrail",
      metadata: { name: "strict" },
      spec: { rules: ["a rule"], severity: "error", scope: "output" },
    };

    const bundleDir = join(tmpDir, "strict");
    const writer = new GuardrailWriter();
    writer.write(new FilesystemBundleHandle(bundleDir), raw);

    const content = readFileSync(join(bundleDir, "GUARDRAIL.md"), "utf-8");
    expect(content).toContain("severity: error");
    expect(content).toContain("scope: output");
  });

  test("creates directory if it does not exist", async () => {
    const bundleDir = join(tmpDir, "nested", "guardrail");
    const writer = new GuardrailWriter();
    writer.write(new FilesystemBundleHandle(bundleDir), {
      kind: "Guardrail",
      metadata: { name: "nested" },
      spec: { rules: [], severity: "warn", scope: "both" },
    });

    expect(existsSync(join(bundleDir, "GUARDRAIL.md"))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// i-validation-shallow — enum enforcement (parity with Python
// test_guardrail_extension.py::TestGuardrailSchemaEnum /
// TestGuardrailValidateDocument)
// ---------------------------------------------------------------------------

describe("Guardrail schema enum enforcement", () => {
  function kp() {
    const k = new Kernel();
    k.load(new GuardrailExtension());
    return k._kinds.get("github.com/ruinosus/dna/v1\0Guardrail")!;
  }

  test("severity/scope schema() emit enum (not bare string)", () => {
    const props = (kp().schema() as any).properties;
    expect(props.severity).toEqual({ type: "string", enum: ["warn", "error", "hard"] });
    expect(props.scope).toEqual({ type: "string", enum: ["input", "output", "both"] });
  });

  test("parse REJECTS severity: critical/garbage (read/compose path)", () => {
    const port = kp();
    for (const bad of ["critical", "garbage"]) {
      expect(() =>
        port.parse!({
          apiVersion: "github.com/ruinosus/dna/v1",
          kind: "Guardrail",
          metadata: { name: "g" },
          spec: { rules: ["x"], severity: bad },
        }),
      ).toThrow();
    }
  });

  test("parse ACCEPTS documented severities", () => {
    const port = kp();
    for (const good of ["warn", "error", "hard"]) {
      expect(() =>
        port.parse!({
          apiVersion: "github.com/ruinosus/dna/v1",
          kind: "Guardrail",
          metadata: { name: "g" },
          spec: { rules: ["x"], severity: good },
        }),
      ).not.toThrow();
    }
  });

  test("validateDocument rejects a bad severity BEFORE the write path", () => {
    const k = new Kernel();
    k.load(new GuardrailExtension());
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Guardrail",
      metadata: { name: "bad" },
      spec: { rules: ["x"], severity: "critical" },
    };
    expect(() => k.validateDocument("s", "Guardrail", "bad", raw)).toThrow();
  });

  test("validateDocument accepts a valid severity", () => {
    const k = new Kernel();
    k.load(new GuardrailExtension());
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Guardrail",
      metadata: { name: "ok" },
      spec: { rules: ["x"], severity: "hard", scope: "output" },
    };
    expect(() => k.validateDocument("s", "Guardrail", "ok", raw)).not.toThrow();
  });
});
