/**
 * i-declarative-canonical-digest — a descriptor (F3) DeclarativeKindPort must
 * expose the SAME canonicalDigest contract as a hand-written KindBase record
 * Kind, so it digests byte-identically across the source-sync (FS↔Postgres)
 * boundary. Py twin: packages/sdk-py/tests/test_declarative_canonical_digest.py.
 *
 * TS has no source-sync consumer today (no digestManifest/pushScope), so this
 * is a latent-gap / parity guard rather than a crash fix — but the digest MUST
 * match KindBase for the day a TS source-sync path lands.
 */
import { describe, it, expect } from "bun:test";
import { KindBase } from "../src/kernel/kind_base.js";
import { Kernel } from "../src/kernel/index.js";
import { DeclarativeKindPort } from "../src/kernel/meta.js";
import { RAW_FULL } from "./fixtures/kinddef-f3-raw.js";

const doc = (spec: Record<string, unknown>, name = "a", kind = "KaizenLike") =>
  ({ kind, name, spec }) as never;

function descriptorPort(): DeclarativeKindPort {
  // RAW_FULL is a TypedKindDefinition-shaped raw; kindFromDescriptor validates
  // + registers, returning the synthesized DeclarativeKindPort.
  const k = new Kernel();
  return k.kindFromDescriptor(RAW_FULL) as DeclarativeKindPort;
}

describe("DeclarativeKindPort.canonicalDigest (i-declarative-canonical-digest)", () => {
  it("exists and returns a sha256 hex (no missing-method gap)", () => {
    const port = descriptorPort();
    const d = port.canonicalDigest(doc({ body: "hi", updated_at: "T1" }));
    expect(typeof d).toBe("string");
    expect(d).toHaveLength(64);
  });

  it("is stable across two calls for equal docs", () => {
    const port = descriptorPort();
    const d = doc({ body: "hi", labels: ["x", "y"] });
    expect(port.canonicalDigest(d)).toBe(port.canonicalDigest(d));
  });

  it("digests byte-identically to the equivalent hand-written KindBase", () => {
    const port = descriptorPort();
    class Ref extends KindBase {
      readonly apiVersion = "ref/v1";
      readonly kind = "KaizenLike";
      readonly alias = "test-kaizenlike";
      readonly storage = { pattern: "yaml", container: "kz" } as never;
      readonly volatileSpecFields = port.volatileSpecFields;
    }
    const ref = new Ref();
    const spec = { body: "content", labels: ["a"], updated_at: "T1", version: 3 };
    const d = doc(spec);
    expect(port.canonicalDigest(d)).toBe(ref.canonicalDigest(d));
  });

  it("ignores volatile stamps + source_files transport", () => {
    const port = descriptorPort();
    const base = { body: "same" };
    expect(
      port.canonicalDigest(doc({ ...base, updated_at: "T1", version: 1 })),
    ).toBe(
      port.canonicalDigest(
        doc({ ...base, updated_at: "T9", version: 42, source_files: { "x.md": "..." } }),
      ),
    );
  });
});
