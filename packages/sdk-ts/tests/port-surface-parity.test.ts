/**
 * s-dna-port-surface-parity — Py↔TS port-surface parity (TS side).
 *
 * The shared fixture `tests/parity-fixtures/port-surface-parity.json`
 * (repo root) lists, per port, the expected members on each side
 * (snake_case ↔ camelCase pairs) plus every INTENTIONAL asymmetry with a
 * `justification`. This suite locks the TS side by comparing the fixture's
 * `ts` member sets against `PORT_SURFACE` (src/kernel/port-surface.ts) —
 * which is keyof-BOUND to the real interfaces, so `tsc --noEmit` fails
 * when an interface member is added/removed without updating the manifest,
 * and THIS suite fails when the manifest and the fixture disagree.
 *
 * Py twin (introspects the real typing.Protocols):
 * packages/sdk-py/tests/test_port_surface_parity.py.
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { PORT_SURFACE } from "../src/kernel/port-surface.js";

interface FixtureMember {
  py: string | null;
  ts: string | null;
  justification?: string;
  note?: string;
}
interface FixturePort {
  doc?: string;
  members: FixtureMember[];
}
interface Fixture {
  ports: Record<string, FixturePort>;
  excluded_surfaces: Record<string, { justification: string }>;
}

const FIXTURE_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  "../../../tests/parity-fixtures/port-surface-parity.json",
);
const fixture: Fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf-8"));

/** Pure comparator (meta-tested below): actual TS surface vs fixture. */
export function diffSurface(
  actual: readonly string[],
  fixtureTsMembers: readonly string[],
): { undeclared: string[]; missing: string[] } {
  const fixtureSet = new Set(fixtureTsMembers);
  const actualSet = new Set(actual);
  return {
    // On the interface but NOT in the fixture → undocumented new member.
    undeclared: [...actualSet].filter((m) => !fixtureSet.has(m)).sort(),
    // In the fixture but NOT on the interface → member was removed (or
    // the fixture lies about the TS surface).
    missing: [...fixtureSet].filter((m) => !actualSet.has(m)).sort(),
  };
}

function tsMembers(port: FixturePort): string[] {
  return port.members.flatMap((m) => (m.ts !== null ? [m.ts] : []));
}

describe("port-surface parity (TS side)", () => {
  for (const [name, port] of Object.entries(fixture.ports)) {
    const expected = tsMembers(port);
    if (expected.length === 0) {
      test(`${name}: Py-only port stays absent from the TS manifest`, () => {
        expect(PORT_SURFACE[name]).toBeUndefined();
      });
      continue;
    }
    test(`${name}: TS interface surface == fixture`, () => {
      const actual = PORT_SURFACE[name];
      expect(actual).toBeDefined();
      const { undeclared, missing } = diffSurface(actual!, expected);
      expect(
        undeclared,
        `TS ${name} member(s) not tracked in port-surface-parity.json — ` +
        `add the pair (or a justified ts-only entry): ${undeclared.join(", ")}`,
      ).toEqual([]);
      expect(
        missing,
        `fixture lists TS ${name} member(s) the interface no longer has — ` +
        `port the removal to the fixture (and Py, or justify): ${missing.join(", ")}`,
      ).toEqual([]);
    });
  }

  test("every PORT_SURFACE port is tracked in the fixture", () => {
    const untracked = Object.keys(PORT_SURFACE).filter(
      (p) => !(p in fixture.ports),
    );
    expect(untracked).toEqual([]);
  });

  test("every one-sided member carries a non-empty justification", () => {
    const offenders: string[] = [];
    for (const [name, port] of Object.entries(fixture.ports)) {
      for (const m of port.members) {
        const oneSided = (m.py === null) !== (m.ts === null);
        if ((m.py === null && m.ts === null) || (oneSided && !(m.justification ?? "").trim())) {
          offenders.push(`${name}.${m.py ?? m.ts ?? "??"}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  test("excluded surfaces are justified, not silent", () => {
    const entries = Object.entries(fixture.excluded_surfaces);
    expect(entries.length).toBeGreaterThan(0);
    for (const [, v] of entries) {
      expect((v.justification ?? "").trim().length).toBeGreaterThan(0);
    }
  });

  // ── test-of-the-test (gate 5): removing a member from the fixture MUST
  // turn the comparison red — parity can't silently erode.
  test("meta: dropping a fixture member is detected as undeclared drift", () => {
    const full = tsMembers(fixture.ports.SourcePort);
    const mutilated = full.filter((m) => m !== "close");
    const { undeclared } = diffSurface(PORT_SURFACE.SourcePort, mutilated);
    expect(undeclared).toEqual(["close"]);
  });

  test("meta: a fixture member missing from the interface is detected", () => {
    const { missing } = diffSurface(
      PORT_SURFACE.SourcePort,
      [...tsMembers(fixture.ports.SourcePort), "phantomMember"],
    );
    expect(missing).toEqual(["phantomMember"]);
  });
});
