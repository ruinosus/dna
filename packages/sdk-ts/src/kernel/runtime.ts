/**
 * Runtime — public facade over Kernel.
 *
 * Provides the new vocabulary: storage() instead of source(),
 * manifest() instead of instance(). Extends Kernel for full
 * backwards compatibility during the transition.
 */
import { Kernel } from "./index.js";
import type { SourcePort } from "./protocols.js";
import type { ManifestInstance } from "./instance.js";

export class Runtime extends Kernel {
  /** Register a storage backend. Alias for source(). */
  storage(s: SourcePort): void {
    this.source(s);
  }

  /** Load a manifest for a scope. Alias for instance(). */
  async manifest(scope: string, layers?: Record<string, string>): Promise<ManifestInstance> {
    return this.instance(scope, layers);
  }
}
