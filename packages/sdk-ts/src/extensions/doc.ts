/**
 * DocExtension — the in-product documentation Kind.
 *
 * Registers 1 Kind:
 *   - Doc (dna-doc) — one page of in-product documentation: a markdown
 *     `body` + sidebar metadata (icon/subtitle/summary/order/locale/
 *     enabled/kind_of/category/tags). The corpus `dna docs list/show`
 *     reads is made of these.
 *
 * Pure descriptor extension (F3): the Kind is data — `doc/kinds/
 * doc.kind.yaml` — synthesized via `kernel.kindFromDescriptor`; the
 * bundle storage (`docs/<name>/DOC.md`, frontmatter + markdown body) is
 * handled by the generic reader/writer machinery. No models, no port
 * class. 1:1 parity with Python (the descriptor file is byte-identical
 * package data — see tests/descriptor-hash-parity.test.ts).
 *
 * Tier A port from the internal SDK's doc extension (s-tier-a-doc-kind);
 * see the descriptor header for the honest subset notes.
 */
import type { Extension, ExtensionHost } from "../kernel/protocols.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";

export class DocExtension implements Extension {
  readonly name = "doc";
  readonly version = "1.0.0";

  register(kernel: ExtensionHost): void {
    for (const raw of loadDescriptors(import.meta.url, "doc/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
  }
}
