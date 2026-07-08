/**
 * Navigator — namespace class extracting navigation/display logic
 * from ManifestInstance.
 *
 * Usage: `mi.nav.describe(...)`, `mi.nav.summary()`, `mi.nav.inventory()`, etc.
 *
 * This is an extraction (Chunk 2 of the kernel simplification plan).
 * The original methods on ManifestInstance are preserved as one-line
 * delegates; the canonical logic lives here.
 */

import type { KindPort } from "./protocols.js";
import { genericSpecDump, type PreviewBlock } from "./preview.js";
import type { ManifestInstance } from "./instance.js";

// ---------------------------------------------------------------------------
// Navigator
// ---------------------------------------------------------------------------

export class Navigator {
  constructor(private host: ManifestInstance) {}

  /**
   * Describe a single document.
   * Equivalent to `mi.describe(kind, name)`.
   */
  describe(kind: string, name: string): string {
    const doc = this.host.one(kind, name);
    if (!doc) return `${kind}/${name} not found`;

    const kinds = (this.host as any)._kinds as Map<string, KindPort>;
    const kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
    if (kp) {
      const custom = kp.describe(doc);
      if (custom) return custom;
    }

    const lines = [
      `Name:       ${doc.name}`,
      `Kind:       ${doc.kind}`,
      `ApiVersion: ${doc.apiVersion}`,
    ];
    const desc = doc.metadata.description;
    if (desc) {
      lines.push(`Description: ${desc}`);
    }
    return lines.join("\n");
  }

  /**
   * Produce a text summary of the manifest.
   * Equivalent to `mi.summary()`.
   */
  summary(): string {
    const kinds = this.host.listKinds();
    const lines = [`Scope: ${this.host.scope}`, `Kinds: ${kinds.length}`];
    for (const k of kinds) {
      const docs = this.host.all(k);
      lines.push(
        `  ${k}: ${docs.length} (${docs.map((d) => d.name).join(", ")})`,
      );
    }
    return lines.join("\n");
  }

  /**
   * Produce a structured inventory of the manifest.
   * Equivalent to `mi.inventory()`.
   */
  inventory(): Record<string, unknown> {
    const kinds = (this.host as any)._kinds as Map<string, KindPort>;
    const kindsData: Record<string, unknown> = {};

    for (const kindName of this.host.listKinds()) {
      const docs = this.host.all(kindName);
      const docEntries: Record<string, unknown>[] = [];

      for (const doc of docs) {
        const entry: Record<string, unknown> = {
          name: doc.name,
          description: (doc.metadata as Record<string, unknown>).description ?? "",
        };

        const key = `${doc.apiVersion}\0${doc.kind}`;
        const kp = kinds.get(key);
        if (kp) {
          const filters = kp.depFilters();
          if (filters) {
            const refs: Record<string, unknown> = {};
            const spec = doc.spec as Record<string, unknown>;
            for (const [specField] of Object.entries(filters)) {
              const val = spec[specField];
              if (val != null) {
                refs[specField] = val;
              }
            }
            if (Object.keys(refs).length > 0) {
              entry.refs = refs;
            }
          }

          const extra = kp.summary(doc);
          if (extra) {
            Object.assign(entry, extra);
          }
        }

        docEntries.push(entry);
      }

      kindsData[kindName] = {
        count: docs.length,
        documents: docEntries,
      };
    }

    const comp = this.host.compositionResult;
    return {
      scope: this.host.scope,
      total_documents: this.host.documents.length,
      kinds: kindsData,
      composition: {
        valid: comp.missing.length === 0,
        resolved: comp.resolved,
        missing: comp.missing,
        warnings: comp.warnings,
        deferred: comp.deferred,
      },
    };
  }

  /**
   * Polymorphic per-kind preview.
   * Equivalent to `mi.renderDoc(kind, name)`.
   */
  renderDoc(kind: string, name: string): PreviewBlock[] {
    const doc = this.host.one(kind, name);
    if (!doc) return [];
    const kinds = (this.host as any)._kinds as Map<string, KindPort>;
    const kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
    if (kp && typeof kp.preview === "function") {
      return kp.preview(doc);
    }
    return genericSpecDump(doc);
  }
}
