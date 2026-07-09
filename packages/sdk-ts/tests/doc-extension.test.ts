/**
 * Doc Kind (s-tier-a-doc-kind) — builtin descriptor registration, TS side.
 *
 * Py twin: packages/sdk-py/tests/test_doc_kind.py. The descriptor FILE is
 * byte-identical package data (descriptor-hash-parity.test.ts); this pins
 * the registration surface `dna docs` depends on in the TS runtime too.
 */
import { describe, it, expect } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";

const kernel = createKernelWithBuiltins();
const port = kernel.kindPortFor("Doc") as unknown as Record<string, unknown>;

describe("DocExtension (builtin descriptor)", () => {
  it("registers Doc from the descriptor with the dna-doc alias", () => {
    expect(port).toBeTruthy();
    expect(port.alias).toBe("dna-doc");
    expect(port.plane).toBe("record");
    expect(port.__declarative__).toBe(true);
    expect(port.__builtin_descriptor__).toBe(true);
  });

  it("keeps the DOC.md bundle authoring shape", () => {
    const sd = port.storage as { container: string; marker: string; bodyField?: string; body_field?: string };
    expect(sd.container).toBe("docs");
    expect(sd.marker).toBe("DOC.md");
    expect(sd.bodyField ?? sd.body_field).toBe("body");
  });

  it("ships a strict schema with the fields the CLI consumes", () => {
    const schema = (port.schema as () => Record<string, unknown>).call(port);
    expect(schema.additionalProperties).toBe(false);
    const props = Object.keys(schema.properties as Record<string, unknown>);
    for (const f of ["body", "icon", "order", "locale", "kind_of", "category", "subtitle", "summary", "enabled", "tags"]) {
      expect(props).toContain(f);
    }
  });

  it("parse applies the upstream defaults and validates Diátaxis kind_of", () => {
    const parse = (port.parse as (raw: Record<string, unknown>) => Record<string, unknown>).bind(port);
    const parsed = parse({ metadata: { name: "welcome" }, spec: { body: "# hi" } });
    const spec = (parsed as { spec: Record<string, unknown> }).spec;
    expect(spec.locale).toBe("pt-BR");
    expect(spec.order).toBe(999);
    expect(spec.enabled).toBe(true);
    expect(() => parse({ metadata: { name: "bad" }, spec: { body: "x", kind_of: "guide" } })).toThrow();
  });
});
