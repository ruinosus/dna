/**
 * StudioUIMetadata TS twin — parity with Python dna.kernel.studio_ui.
 *
 * Drives off the SHARED fixture (tests/fixtures/studio-ui-parity.json) that a
 * Python companion test (tests/test_studio_ui_parity.py) reads too, so both
 * runtimes assert byte-identical toDict()/resolveLabel() output.
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { StudioUIMetadata } from "../src/kernel/studio_ui.js";

const fixtureUrl = new URL("./fixtures/studio-ui-parity.json", import.meta.url);
const fixture = JSON.parse(readFileSync(fileURLToPath(fixtureUrl), "utf-8")) as {
  cases: Array<{
    name: string;
    input: Record<string, unknown>;
    to_dict: Record<string, unknown>;
    resolve_label: Record<string, string | null>;
  }>;
};

describe("StudioUIMetadata", () => {
  for (const c of fixture.cases) {
    test(`toDict — ${c.name}`, () => {
      const ui = new StudioUIMetadata(c.input);
      expect(ui.toDict()).toEqual(c.to_dict);
    });

    test(`resolveLabel — ${c.name}`, () => {
      const ui = new StudioUIMetadata(c.input);
      for (const [locale, expected] of Object.entries(c.resolve_label)) {
        expect(ui.resolveLabel(locale)).toBe(expected);
      }
    });
  }

  test("resolveLabel defaults locale to 'en'", () => {
    const ui = new StudioUIMetadata({ label: { en: "Hi", "pt-BR": "Oi" } });
    expect(ui.resolveLabel()).toBe("Hi");
  });

  test("UI_METADATA_FIELDS is the canonical field set", () => {
    expect(new Set(StudioUIMetadata.fields())).toEqual(
      new Set([
        "mode",
        "in_sidebar",
        "display_order",
        "label",
        "icon",
        "description",
        "breadcrumb",
        "routes",
        "permissions",
        "note",
        "feature_flag",
      ]),
    );
  });
});
