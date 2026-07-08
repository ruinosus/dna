/**
 * s-blessed-query-surface — blessed query surface lock (TypeScript side).
 *
 * The shared fixture `tests/parity-fixtures/port-surface-parity.json`
 * (repo root, section `blessed_query_surface`) declares:
 *
 *   - `blessed`: the ONE documented read/query surface (what docs/,
 *     README and examples teach). Members must exist and calling the
 *     cheap ones must be silent (no deprecation console.warn).
 *   - `deprecated`: still work, but `console.warn` ONCE per process
 *     naming the exact replacement and the removal release (1.0),
 *     mirroring the Python `DeprecationWarning`.
 *   - `public_surface`: EXACT set of public members on an instantiated
 *     ManifestInstance — adding/removing/renaming a public member
 *     without editing the fixture turns this suite red, so every
 *     public-surface change is a conscious decision.
 *
 * Python twin: `packages/sdk-py/tests/test_blessed_query_surface.py`.
 */

import { afterEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import path from "node:path";

import {
  ManifestInstance,
  _resetDeprecationWarnings,
} from "../src/kernel/instance.js";
import { Kernel } from "../src/kernel/index.js";

const FIXTURE_PATH = path.resolve(
  import.meta.dir,
  "../../../tests/parity-fixtures/port-surface-parity.json",
);

interface Member {
  py: string | null;
  ts: string | null;
  note?: string;
  justification?: string;
  replacement?: string;
  removal?: string;
}

interface SurfaceSection {
  ManifestInstance: {
    blessed: Member[];
    deprecated: Member[];
    public_surface: { py: string[]; ts: string[] };
  };
  Kernel: { blessed: Member[]; deprecated: Member[] };
}

const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf-8"));
const surface = fixture.blessed_query_surface as SurfaceSection;

function makeMi(): ManifestInstance {
  return new ManifestInstance({ scope: "t", documents: [], kinds: new Map() });
}

function publicMembers(obj: object): Set<string> {
  const names = new Set<string>();
  for (const n of Object.getOwnPropertyNames(obj)) names.add(n);
  for (const n of Object.getOwnPropertyNames(Object.getPrototypeOf(obj))) {
    names.add(n);
  }
  names.delete("constructor");
  return new Set([...names].filter((n) => !n.startsWith("_")));
}

/** Capture console.warn calls during fn() — restores afterwards. */
function captureWarns(fn: () => void): string[] {
  const calls: string[] = [];
  const orig = console.warn;
  console.warn = (...args: unknown[]) => {
    calls.push(args.map(String).join(" "));
  };
  try {
    fn();
  } finally {
    console.warn = orig;
  }
  return calls;
}

afterEach(() => _resetDeprecationWarnings());

describe("blessed query surface (fixture section exists)", () => {
  test("fixture declares blessed_query_surface", () => {
    expect(surface).toBeDefined();
    expect(surface.ManifestInstance).toBeDefined();
    expect(surface.Kernel).toBeDefined();
  });
});

describe("existence — blessed + deprecated members are real", () => {
  test("blessed MI members exist", () => {
    const mi = makeMi();
    for (const m of surface.ManifestInstance.blessed) {
      if (m.ts === null) {
        expect(m.justification ?? "").not.toBe("");
        continue;
      }
      expect(m.ts in mi).toBe(true);
    }
  });

  test("deprecated MI members exist and carry replacement + removal", () => {
    const mi = makeMi();
    for (const m of surface.ManifestInstance.deprecated) {
      expect(m.replacement ?? "").not.toBe("");
      expect(m.removal).toBe("1.0");
      expect(m.ts).not.toBeNull();
      expect(m.ts! in mi).toBe(true);
    }
  });

  test("blessed Kernel members exist", () => {
    const k = new Kernel();
    for (const m of surface.Kernel.blessed) {
      if (m.ts === null) {
        expect(m.justification ?? "").not.toBe("");
        continue;
      }
      expect(m.ts in k).toBe(true);
    }
  });

  test("one-sided members carry a justification", () => {
    for (const cls of ["ManifestInstance", "Kernel"] as const) {
      for (const group of ["blessed", "deprecated"] as const) {
        for (const m of surface[cls][group] ?? []) {
          if (m.py === null || m.ts === null) {
            expect(m.justification ?? "").not.toBe("");
          }
        }
      }
    }
  });
});

describe("public-surface exact lock — conscious decisions only", () => {
  test("MI public surface is exactly the fixture", () => {
    const expected = new Set(surface.ManifestInstance.public_surface.ts);
    const actual = publicMembers(makeMi());
    const added = [...actual].filter((n) => !expected.has(n)).sort();
    const removed = [...expected].filter((n) => !actual.has(n)).sort();
    expect(
      { added, removed },
      "ManifestInstance public surface drifted from the fixture — if " +
        "intentional, update blessed_query_surface.ManifestInstance." +
        "public_surface in tests/parity-fixtures/port-surface-parity.json " +
        "(both ts AND py sides — this is a parity decision).",
    ).toEqual({ added: [], removed: [] });
  });
});

describe("deprecation behavior — deprecated warns once, blessed is silent", () => {
  test("mi.all() console.warns with the blessed replacement", () => {
    const warns = captureWarns(() => makeMi().all("Skill"));
    expect(warns.length).toBe(1);
    expect(warns[0]).toContain("will be removed in 1.0");
    expect(warns[0]).toContain("mi.documents");
    expect(warns[0]).toContain("kernel.query");
  });

  test("mi.one() console.warns with the blessed replacement", () => {
    const warns = captureWarns(() => makeMi().one("Skill", "x"));
    expect(warns.length).toBe(1);
    expect(warns[0]).toContain("will be removed in 1.0");
    expect(warns[0]).toContain("mi.documents");
  });

  test("deprecation warning fires once per method per process", () => {
    const warns = captureWarns(() => {
      const mi = makeMi();
      mi.all("Skill");
      mi.all("Soul");
      mi.one("Skill", "x");
      mi.one("Soul", "y");
    });
    expect(warns.length).toBe(2); // one for all(), one for one()
  });

  test("blessed surface is silent", () => {
    const warns = captureWarns(() => {
      const mi = makeMi();
      void mi.documents;
      void mi.root;
      void mi.defaultAgent();
      void mi.findAgent("nope");
      void mi.resolve(undefined);
    });
    expect(warns).toEqual([]);
  });

  test("internal twins _all/_one are silent", () => {
    const warns = captureWarns(() => {
      const mi = makeMi();
      expect(mi._all("Skill")).toEqual([]);
      expect(mi._one("Skill", "x")).toBeNull();
    });
    expect(warns).toEqual([]);
  });
});
