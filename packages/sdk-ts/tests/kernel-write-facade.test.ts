// typescript/tests/kernel-write-facade.test.ts
//
// TS mirror of python/tests/test_kernel_write_facade.py (Tasks A.1-A.3).
// Covers: exported error types + PreviewResult interface, activeSource /
// activeWriters accessors, and the private _targetLocator helper.
//
// Deviation from the plan stub: TypeScript has no FilesystemWritableSource
// equivalent (only the WritableSourcePort interface used via stubs). The FS
// branch of _targetLocator only cares about the presence of `baseDir`, so
// FilesystemSource is used as the filesystem test subject.
import { describe, expect, test } from "bun:test";
import { Kernel, NotWritableError, type PreviewResult } from "../src/kernel/index.js";
import { FilesystemSource } from "../src/adapters/filesystem/source.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { KindDefinitionExtension } from "../src/extensions/kinddef.js";
import type { WriterPort, WritableSourcePort } from "../src/kernel/protocols.js";

describe("types", () => {
  test("NotWritableError extends Error", async () => {
    expect(new NotWritableError("x")).toBeInstanceOf(Error);
    expect(new NotWritableError("x").name).toBe("NotWritableError");
  });

  test("PreviewResult interface accepts string target + readonly files", async () => {
    // Structural typing — compile-time shape check at construction site.
    const pr: PreviewResult = {
      target: "sqlite://m/Skill/demo",
      files: [{ relativePath: "skills/demo/SKILL.md", content: "..." }],
      existsAlready: false,
    };
    expect(pr.target).toBe("sqlite://m/Skill/demo");
    expect(pr.files).toHaveLength(1);
    expect(pr.existsAlready).toBe(false);
  });

  test("PreviewResult existsAlready true signals overwrite", async () => {
    const pr: PreviewResult = {
      target: "/tmp/x/m/skills/demo",
      files: [],
      existsAlready: true,
    };
    expect(pr.existsAlready).toBe(true);
  });
});

describe("accessors", () => {
  test("activeSource is null by default", async () => {
    expect(new Kernel().activeSource).toBeNull();
  });

  test("activeSource reflects source() setter", async () => {
    const k = new Kernel();
    const s = new FilesystemSource("/tmp/x");
    k.source(s);
    expect(k.activeSource).toBe(s);
  });

  test("activeWriters is an empty frozen array by default", async () => {
    const snap = new Kernel().activeWriters;
    expect(Array.isArray(snap)).toBe(true);
    expect(snap).toHaveLength(0);
    expect(Object.isFrozen(snap)).toBe(true);
  });

  test("activeWriters reflects writer() setter", async () => {
    const k = new Kernel();
    const w: WriterPort = {
      canWrite: () => true,
      write: () => {},
    };
    k.writer(w);
    expect(k.activeWriters).toHaveLength(1);
    expect(k.activeWriters[0]).toBe(w);
  });

  test("activeWriters is a frozen snapshot — mutating it cannot poison the kernel", async () => {
    const k = new Kernel();
    const w: WriterPort = {
      canWrite: () => true,
      write: () => {},
    };
    k.writer(w);
    const got = k.activeWriters;
    expect(Object.isFrozen(got)).toBe(true);
    // Strict mode (ESM) makes frozen-array mutation throw.
    expect(() => {
      (got as WriterPort[]).push({
        canWrite: () => false,
        write: () => {},
      });
    }).toThrow();
  });
});

describe("_targetLocator", () => {
  test("filesystem source returns absolute path string", async () => {
    const k = new Kernel();
    k.source(new FilesystemSource("/tmp/x"));
    // Private method called via index access — matches plan spec line 915.
    const got = (k as unknown as {
      _targetLocator: (s: string, k: string, n: string) => string;
    })._targetLocator("m", "Skill", "demo");
    expect(got).toBe("/tmp/x/m/skills/demo");
  });

  test("non-filesystem source returns synthetic URL with urlScheme", async () => {
    const k = new Kernel();
    const stub = {
      urlScheme: "sqlite",
      supportsReaders: false,
      loadBootstrapDocs: async () => [],
      loadAll: () => [],
      resolveRef: () => "",
      loadLayer: () => [],
      writeFile: async () => {},
      deleteFile: async () => {},
      deleteDirectory: async () => {},
    } as WritableSourcePort & { urlScheme: string };
    k.source(stub);
    const got = (k as unknown as {
      _targetLocator: (s: string, k: string, n: string) => string;
    })._targetLocator("m", "Skill", "demo");
    expect(got).toBe("sqlite://m/Skill/demo");
  });

  test("non-filesystem source falls back to class-name scheme when urlScheme is undefined", async () => {
    class NoSchemeSource {
      supportsReaders = false;
      async loadBootstrapDocs() { return []; }
      loadAll() { return []; }
      resolveRef() { return ""; }
      loadLayer() { return []; }
    }
    const k = new Kernel();
    k.source(new NoSchemeSource() as unknown as WritableSourcePort);
    const got = (k as unknown as {
      _targetLocator: (s: string, k: string, n: string) => string;
    })._targetLocator("m", "Skill", "demo");
    expect(got).toBe("noscheme://m/Skill/demo");
  });

  test("filesystem source uses lowercase-pluralised fallback for unknown kinds", async () => {
    const k = new Kernel();
    k.source(new FilesystemSource("/tmp/x"));
    const got = (k as unknown as {
      _targetLocator: (s: string, k: string, n: string) => string;
    })._targetLocator("m", "CustomThing", "one");
    expect(got).toBe("/tmp/x/m/customthings/one");
  });

  test("filesystem source uses storage.container for custom kinds (KindDefinition → kinds/)", async () => {
    // KindDefinitionExtension declares storage.container="kinds". The
    // legacy _KIND_SUBDIRS map never listed KindDefinition, so without
    // storageForKind routing it would fall back to "kinddefinitions/".
    const k = new Kernel();
    k.load(new KindDefinitionExtension());
    k.source(new FilesystemSource("/tmp/x"));
    const got = (k as unknown as {
      _targetLocator: (s: string, k: string, n: string) => string;
    })._targetLocator("m", "KindDefinition", "ticket");
    expect(got).toBe("/tmp/x/m/kinds/ticket");
  });
});

describe("previewDocument", () => {
  test("returns target + files + existsAlready=false for new doc", async () => {
    const k = new Kernel();
    k.load(new HelixExtension());
    k.writableSource({
      writeFile: async () => {},
      deleteFile: async () => {},
      deleteDirectory: async () => {},
      loadAll: () => [],
      loadBootstrapDocs: async () => [],
      resolveRef: () => "",
      loadLayer: () => [],
      supportsReaders: false,
      listVersions: async () => [],
      baseDir: "/tmp/x",
    } as unknown as WritableSourcePort);

    const pr = await k.previewDocument("m", "Agent", "alice", {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "alice" },
      spec: { instruction: "x" },
    });
    expect(pr.files.length).toBeGreaterThanOrEqual(1);
    expect(pr.existsAlready).toBe(false);
    expect(typeof pr.target).toBe("string");
  });

  test("existsAlready=true when listVersions returns a non-empty array", async () => {
    const k = new Kernel();
    k.load(new HelixExtension());
    k.writableSource({
      writeFile: async () => {},
      deleteFile: async () => {},
      deleteDirectory: async () => {},
      loadAll: () => [],
      loadBootstrapDocs: async () => [],
      resolveRef: () => "",
      loadLayer: () => [],
      supportsReaders: false,
      listVersions: async () => [{ id: "v1" }],
    } as unknown as WritableSourcePort);

    const pr = await k.previewDocument("m", "Agent", "alice", {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "alice" },
      spec: { instruction: "x" },
    });
    expect(pr.existsAlready).toBe(true);
  });

  test("existsAlready=false when listVersions absent", async () => {
    const k = new Kernel();
    k.load(new HelixExtension());
    k.writableSource({
      writeFile: async () => {},
      deleteFile: async () => {},
      deleteDirectory: async () => {},
      loadAll: () => [],
      loadBootstrapDocs: async () => [],
      resolveRef: () => "",
      loadLayer: () => [],
      supportsReaders: false,
    } as unknown as WritableSourcePort);

    const pr = await k.previewDocument("m", "Agent", "alice", {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "alice" },
      spec: { instruction: "x" },
    });
    expect(pr.existsAlready).toBe(false);
  });
});
