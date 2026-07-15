/**
 * CloudExtension — DNA Cloud pricing + billing→enforcement registry.
 *
 * 1:1 parity with Python `dna.extensions.cloud`.
 *
 * Registers 2 Kinds, from descriptors (F3 — record Kinds are data, not
 * classes):
 *
 *   - Tier (`cloud-tier`) — one DNA Cloud plan's hard caps
 *     (`calls_per_day`, `rate_per_sec`, `max_tenants`) + the feature
 *     families it unlocks + price, as a first-class GLOBAL Kind so limits
 *     are project data, not implicit knowledge. NOT named `Plan` — that
 *     alias belongs to the SDLC implementation-plan Kind; a pricing plan is
 *     a Tier. Free / Pro / Enterprise are tiers.
 *   - WorkspacePlan (`cloud-workspace-plan`) — the workspace→Tier assignment:
 *     which Tier a given workspace is currently on (ADR "Model B" — billing
 *     keys on the workspace, not an identity/Azure org). The billing→enforcement
 *     bridge: dna-cloud's Stripe webhook writes it on subscribe/cancel; the MCP
 *     server reads it via `kernel.workspacePlan(workspaceId)` when a token
 *     carries no explicit plan claim. The OSS SDK only READS — zero Stripe code.
 *
 * CONTRACT — never hardcode caps. The single source of truth for a plan's
 * limits is its Tier doc (`_lib` scope, `tiers/<tier_id>.yaml`), resolved
 * via `kernel.tier(idOrAlias)`. The quota enforcer reads calls/day, rate
 * and tenant caps from there — a cap literal in code is a bug.
 */

import type { ExtensionHost, Extension } from "../kernel/protocols.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";

export class CloudExtension implements Extension {
  name = "cloud";
  version = "1.0.0";

  register(kernel: ExtensionHost) {
    // F3: Tier ships as kinds/tier.kind.yaml package data (byte-identical
    // Py↔TS mirror), registered through the SAME funnel as per-scope
    // KindDefinitions (plane lint + digest idempotency + builtin conflict
    // marker).
    for (const raw of loadDescriptors(import.meta.url, "cloud/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
  }
}
