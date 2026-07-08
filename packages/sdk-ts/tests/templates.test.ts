/**
 * Phase 0 — Template contract tests (TypeScript parity with Python).
 */
import { describe, test, expect } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, sep } from "node:path";

import {
  type Template,
  materialize,
} from "../src/kernel/templates.js";
import type { Extension } from "../src/kernel/protocols.js";
// Template should also be re-exported from protocols for API convenience
import type { Template as TemplateFromProtocols } from "../src/kernel/protocols.js";
import { Kernel } from "../src/kernel/index.js";

function tmpDir(prefix = "dna-tpl-"): string {
  return mkdtempSync(join(tmpdir(), prefix));
}

function posix(p: string): string {
  return sep === "/" ? p : p.split(sep).join("/");
}

// ---------------------------------------------------------------------------
// Template shape
// ---------------------------------------------------------------------------

describe("Template", () => {
  test("has 8-field shape parity with Python dataclass", async () => {
    const t: Template = {
      id: "gaia/privacy",
      label: "Privacy Assessment",
      kind: "Assessment",
      description: "GAIA privacy eval bundle",
      filesRoot: "/fake/path",
      ownerExtension: "gaia",
    };
    expect(t.id).toBe("gaia/privacy");
    expect(t.kind).toBe("Assessment");
    expect(t.filesRoot).toBe("/fake/path");
    expect(t.ownerExtension).toBe("gaia");
    expect(t.postInitHint).toBeUndefined();
    expect(t.upstreamRef).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// materialize()
// ---------------------------------------------------------------------------

describe("materialize", () => {
  test("copies files to target preserving directory structure", async () => {
    const src = tmpDir();
    const dst = tmpDir();

    writeFileSync(join(src, "program.md"), "hello");
    mkdirSync(join(src, "sub"));
    writeFileSync(join(src, "sub", "nested.txt"), "world");

    const t: Template = {
      id: "test/demo",
      label: "Demo",
      kind: "X",
      description: "",
      filesRoot: src,
      ownerExtension: "test",
    };
    const written = materialize(t, { targetRoot: dst });

    expect(readFileSync(join(dst, "program.md"), "utf-8")).toBe("hello");
    expect(readFileSync(join(dst, "sub", "nested.txt"), "utf-8")).toBe("world");
    const rel = written
      .map((p) => posix(relative(dst, p)))
      .sort();
    expect(rel).toEqual(["program.md", "sub/nested.txt"]);
  });

  test("throws on existing destination by default (onConflict=error)", async () => {
    const src = tmpDir();
    const dst = tmpDir();
    writeFileSync(join(src, "program.md"), "new");
    writeFileSync(join(dst, "program.md"), "existing");

    const t: Template = {
      id: "test/demo",
      label: "Demo",
      kind: "X",
      description: "",
      filesRoot: src,
      ownerExtension: "test",
    };
    expect(() => materialize(t, { targetRoot: dst })).toThrow(/destination exists/);
  });

  test("overwrites existing destination when onConflict=overwrite", async () => {
    const src = tmpDir();
    const dst = tmpDir();
    writeFileSync(join(src, "program.md"), "new");
    writeFileSync(join(dst, "program.md"), "existing");

    const t: Template = {
      id: "test/demo",
      label: "Demo",
      kind: "X",
      description: "",
      filesRoot: src,
      ownerExtension: "test",
    };
    materialize(t, { targetRoot: dst, onConflict: "overwrite" });
    expect(readFileSync(join(dst, "program.md"), "utf-8")).toBe("new");
  });

  test("skips existing destination when onConflict=skip", async () => {
    const src = tmpDir();
    const dst = tmpDir();
    writeFileSync(join(src, "program.md"), "new");
    writeFileSync(join(dst, "program.md"), "existing");

    const t: Template = {
      id: "test/demo",
      label: "Demo",
      kind: "X",
      description: "",
      filesRoot: src,
      ownerExtension: "test",
    };
    const written = materialize(t, { targetRoot: dst, onConflict: "skip" });
    expect(readFileSync(join(dst, "program.md"), "utf-8")).toBe("existing");
    expect(written).toEqual([]);
  });

  test("preserves binary files byte-for-byte", async () => {
    const src = tmpDir();
    const dst = tmpDir();
    const payload = Uint8Array.from({ length: 256 }, (_, i) => i);
    writeFileSync(join(src, "logo.png"), payload);

    const t: Template = {
      id: "test/demo",
      label: "Demo",
      kind: "X",
      description: "",
      filesRoot: src,
      ownerExtension: "test",
    };
    materialize(t, { targetRoot: dst });

    const out = readFileSync(join(dst, "logo.png"));
    expect(out.length).toBe(256);
    for (let i = 0; i < 256; i++) {
      expect(out[i]).toBe(i);
    }
  });

  test("throws when filesRoot does not exist", async () => {
    const dst = tmpDir();
    const t: Template = {
      id: "test/demo",
      label: "Demo",
      kind: "X",
      description: "",
      filesRoot: join(tmpdir(), "definitely-not-a-real-dir-xyz-12345"),
      ownerExtension: "test",
    };
    expect(() => materialize(t, { targetRoot: dst })).toThrow(
      /filesRoot does not exist/,
    );
  });

  test("rejects invalid onConflict value", async () => {
    const src = tmpDir();
    const dst = tmpDir();
    writeFileSync(join(src, "f.txt"), "x");

    const t: Template = {
      id: "test/demo",
      label: "Demo",
      kind: "X",
      description: "",
      filesRoot: src,
      ownerExtension: "test",
    };
    expect(() =>
      materialize(t, {
        targetRoot: dst,
        // @ts-expect-error — intentional invalid value for runtime validation
        onConflict: "overwite",
      }),
    ).toThrow(/unknown onConflict/);
  });
});

// ---------------------------------------------------------------------------
// Extension contract (Task 2.2)
// ---------------------------------------------------------------------------

describe("Extension.templates (optional)", () => {
  test("legacy extension without templates() is still a valid Extension", async () => {
    class LegacyExt implements Extension {
      readonly name = "legacy";
      readonly version = "1.0.0";
      register(_kernel: unknown): void {
        // intentionally empty — no templates() method declared
      }
    }

    const ext: Extension = new LegacyExt();
    expect(ext.templates).toBeUndefined();
    expect(typeof (ext as Extension).templates).toBe("undefined");
  });

  test("modern extension with templates() returns a Template[]", async () => {
    class ModernExt implements Extension {
      readonly name = "modern";
      readonly version = "1.0.0";
      register(_kernel: unknown): void {}
      templates(): Template[] {
        return [
          {
            id: "modern/one",
            label: "One",
            kind: "X",
            description: "",
            filesRoot: "/tmp",
            ownerExtension: "modern",
          },
        ];
      }
    }

    const ext = new ModernExt();
    const out = ext.templates!();
    expect(out).toHaveLength(1);
    expect(out[0]!.id).toBe("modern/one");
  });

  test("Template type is re-exported from kernel/protocols", async () => {
    // Compile-time assertion: the two imports refer to the same shape.
    const t: TemplateFromProtocols = {
      id: "reexport/check",
      label: "L",
      kind: "K",
      description: "",
      filesRoot: "/x",
      ownerExtension: "o",
    };
    const u: Template = t;
    expect(u.id).toBe("reexport/check");
  });
});

// ---------------------------------------------------------------------------
// Kernel.listTemplates() + Kernel.scaffold() (Task 2.3)
// ---------------------------------------------------------------------------

describe("Kernel templates API", () => {
  test("listTemplates() aggregates from every loaded extension", async () => {
    const filesRoot = tmpDir();
    writeFileSync(join(filesRoot, "manifest.yaml"), "kind: Demo\n");

    class DemoExt implements Extension {
      readonly name = "demo";
      readonly version = "1.0.0";
      register(_kernel: unknown): void {}
      templates(): Template[] {
        return [
          {
            id: "demo/one",
            label: "One",
            kind: "Demo",
            description: "",
            filesRoot,
            ownerExtension: "demo",
          },
        ];
      }
    }

    const k = new Kernel();
    k.load(new DemoExt());

    const ts = k.listTemplates();
    expect(ts).toHaveLength(1);
    expect(ts[0]!.id).toBe("demo/one");
  });

  test("listTemplates() skips legacy extensions without templates()", async () => {
    class LegacyExt implements Extension {
      readonly name = "legacy";
      readonly version = "1.0.0";
      register(_kernel: unknown): void {}
    }

    const k = new Kernel();
    k.load(new LegacyExt());
    expect(k.listTemplates()).toEqual([]);
  });

  test("listTemplates() survives a misbehaving extension", async () => {
    class BadExt implements Extension {
      readonly name = "bad";
      readonly version = "1.0.0";
      register(_kernel: unknown): void {}
      templates(): Template[] {
        throw new Error("boom");
      }
    }
    const filesRoot = tmpDir();
    class GoodExt implements Extension {
      readonly name = "good";
      readonly version = "1.0.0";
      register(_kernel: unknown): void {}
      templates(): Template[] {
        return [
          {
            id: "good/one",
            label: "One",
            kind: "Demo",
            description: "",
            filesRoot,
            ownerExtension: "good",
          },
        ];
      }
    }

    const k = new Kernel();
    k.load(new BadExt());
    k.load(new GoodExt());

    const ts = k.listTemplates();
    // Good ext's entry still surfaces; BadExt's throw was swallowed.
    expect(ts.map((t) => t.id)).toEqual(["good/one"]);
  });

  test("scaffold() materializes a template by id", async () => {
    const filesRoot = tmpDir();
    writeFileSync(join(filesRoot, "manifest.yaml"), "kind: Demo\n");
    const target = join(tmpDir(), "dst");

    class DemoExt implements Extension {
      readonly name = "demo";
      readonly version = "1.0.0";
      register(_kernel: unknown): void {}
      templates(): Template[] {
        return [
          {
            id: "demo/one",
            label: "One",
            kind: "Demo",
            description: "",
            filesRoot,
            ownerExtension: "demo",
          },
        ];
      }
    }

    const k = new Kernel();
    k.load(new DemoExt());
    const written = k.scaffold("demo/one", { targetRoot: target });

    expect(readFileSync(join(target, "manifest.yaml"), "utf-8")).toBe(
      "kind: Demo\n",
    );
    expect(written.map((p) => posix(relative(target, p)))).toEqual([
      "manifest.yaml",
    ]);
  });

  test("scaffold() throws on unknown template id", async () => {
    const k = new Kernel();
    expect(() =>
      k.scaffold("ghost/missing", { targetRoot: tmpDir() }),
    ).toThrow(/template not found: ghost\/missing/);
  });
});
