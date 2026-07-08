/**
 * LockManager — namespace class extracting lockfile logic
 * from ManifestInstance.
 *
 * Usage: `mi.lock.generate()` — equivalent to `mi.generateLock()`.
 *
 * This is an extraction (Chunk 2 of the kernel simplification plan).
 * The original methods on ManifestInstance are preserved; both APIs
 * return identical results.
 */

import { documentHash, type LockEntry, type Lockfile } from "./lock.js";
import type { ManifestInstance } from "./instance.js";

// ---------------------------------------------------------------------------
// LockManager
// ---------------------------------------------------------------------------

export class LockManager {
  constructor(private host: ManifestInstance) {}

  /**
   * Generate a lockfile snapshot from the current documents.
   * Equivalent to `mi.generateLock()`.
   */
  generate(): Lockfile {
    const entries: LockEntry[] = this.host.documents.map((d) => {
      const sha = documentHash(d.raw);
      return {
        name: d.name,
        kind: d.kind,
        apiVersion: d.apiVersion,
        origin: d.origin,
        path: "",
        sha256: sha,
      };
    });

    return {
      scope: this.host.scope,
      documents: entries,
      lockVersion: 3,
      generatedAt: new Date().toISOString(),
    };
  }
}
