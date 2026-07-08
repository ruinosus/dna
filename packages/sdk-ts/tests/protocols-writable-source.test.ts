import { describe, test, expect } from "bun:test";
import type { WritableSourcePort, SourcePort } from "../src/kernel/protocols.js";

describe("WritableSourcePort shape (compile-time)", () => {
  test("extends SourcePort", async () => {
    // If WritableSourcePort doesn't extend SourcePort, the cast below fails at compile time.
    const ws = {} as WritableSourcePort;
    const s: SourcePort = ws;
    expect(s).toBeDefined();
  });

  test("declares saveDocument / deleteDocument as REQUIRED and listVersions as optional", async () => {
    // Structural check: a minimal document-level adapter (saveDocument +
    // deleteDocument, no listVersions) must satisfy the interface. The
    // legacy file-level methods (writeFile/deleteFile/deleteDirectory/exists)
    // were removed in Chunk 5 of the alignment plan — adapters now operate
    // purely at the document level.
    const ws: WritableSourcePort = {
      // Existing required SourcePort members (sync signatures).
      supportsReaders: false,
      loadBootstrapDocs: async () => [],
      loadAll: () => [],
      resolveRef: () => "",
      loadLayer: () => [],
      // Required document-level write methods (Promise-based).
      saveDocument: async () => "1",
      deleteDocument: async () => {},
    };
    expect(typeof ws.saveDocument).toBe("function");
    expect(typeof ws.deleteDocument).toBe("function");
    expect(ws.listVersions).toBeUndefined();
  });
});
