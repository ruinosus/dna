/**
 * `dna/memory/personal` — the personal / private per-user memory partition (TS twin).
 *
 * 1:1 mirror of `dna/memory/personal.py` (ADR-personal-memory). Personal memory
 * is the ONE DNA construct whose partition key is the *human*, not the
 * *workspace*: keyed on the durable Entra `oid`, it is literally the SAME
 * partition in workspace A, workspace B, and a bare MCP client — "your memory
 * follows *you*" as a primary-key value.
 *
 * This is the PURE core — no kernel / HTTP import — holding the reserved
 * `personal:<oid>` namespace, the {@link MemoryScope} selector, the
 * {@link resolveMemoryTenant} decision (ADR §5, fail-closed on a missing
 * identity), and {@link assertNoPersonalOverride} (INV-PERSONAL layer 4). Layer
 * 2 (the `tenant IN ('', X)` union predicate provably excludes `personal:*`) is
 * a source-adapter property; layer 3 (the validator reserves the `personal:`
 * scheme) lives in `kernel/protocols.ts` (`validateTenantSlug`).
 */

/**
 * The reserved tenant *scheme* (the segment before the first `:`) that marks a
 * personal partition. Reserved at the validator so no Workspace can be named to
 * shadow/alias it (ADR §3.4).
 */
export const PERSONAL_TENANT_SCHEME = "personal";

/** The concrete prefix a personal partition value carries: `personal:<oid>`. */
export const PERSONAL_TENANT_PREFIX = `${PERSONAL_TENANT_SCHEME}:`;

/**
 * The memory-targeting selector on every memory verb (ADR §3.1). `workspace` is
 * the default — every existing call keeps its behavior; `personal` is strictly
 * additive.
 */
export type MemoryScope = "workspace" | "personal";

export const WORKSPACE_SCOPE: MemoryScope = "workspace";
export const PERSONAL_SCOPE: MemoryScope = "personal";

/**
 * Thrown when `memory_scope=personal` is requested but NO identity could be
 * resolved server-side (no verified `oid`, and no offline `DNA_PERSONAL_ID`).
 * Personal memory REQUIRES an identity — it must never resolve to a null/blank
 * partition. Fail-closed.
 */
export class PersonalIdentityRequired extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "PersonalIdentityRequired";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Thrown when a caller supplies a raw `tenant` naming the reserved `personal:`
 * scheme (INV-PERSONAL layer 4, ADR §7.4). Personal partitions are reachable
 * ONLY through the `memory_scope=personal` selector, whose oid is derived
 * server-side — never through a raw `tenant` param.
 */
export class PersonalOverrideRejected extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "PersonalOverrideRejected";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * The identity family that keeps the BARE `personal:<id>` value (no family
 * segment) — Entra, the original lane. Keeping it bare means zero migration of
 * existing personal partitions (decision D6). Any OTHER family (e.g. `google`)
 * is namespaced as `personal:<family>:<id>` so the families never collide.
 */
export const PERSONAL_IMPLICIT_FAMILY = "entra";

/**
 * Build the reserved personal partition value for a durable identity.
 * Entra (default / `family="entra"`) → the bare `personal:<oid>` (no migration);
 * any other family (e.g. `family="google"`) → `personal:<family>:<id>`.
 * `personalTenant("abc") === "personal:abc"`;
 * `personalTenant("abc", "google") === "personal:google:abc"`. Throws {@link
 * PersonalIdentityRequired} for a blank/empty identity in any family.
 */
export function personalTenant(oid: string, family?: string | null): string {
  const clean = (oid ?? "").trim();
  if (!clean) {
    throw new PersonalIdentityRequired(
      "personal memory needs a non-empty identity to key the partition",
    );
  }
  const fam = (family ?? PERSONAL_IMPLICIT_FAMILY).trim().toLowerCase();
  if (fam === PERSONAL_IMPLICIT_FAMILY) {
    return `${PERSONAL_TENANT_PREFIX}${clean}`;
  }
  return `${PERSONAL_TENANT_PREFIX}${fam}:${clean}`;
}

/**
 * True when `tenant` names the reserved personal partition scheme
 * (`personal:<oid>`). `null` / a workspace id / base `''` → false.
 */
export function isPersonalTenant(tenant: string | null | undefined): boolean {
  return !!tenant && tenant.startsWith(PERSONAL_TENANT_PREFIX);
}

/**
 * The scheme segment of `tenant` (before the first `:`), or `null` when the
 * value carries no `:` (an ordinary workspace id / base `''`).
 */
export function tenantScheme(tenant: string | null | undefined): string | null {
  if (!tenant || !tenant.includes(":")) return null;
  return tenant.slice(0, tenant.indexOf(":"));
}

/**
 * Resolve the physical `tenant` a memory request runs against — the ADR §5
 * decision, pure and workspace-independent for the personal case.
 *
 * - `personal` → `personal:<oid>`, with `oid` resolved SERVER-SIDE (token claim
 *   / `DNA_PERSONAL_ID`). A missing oid FAILS CLOSED ({@link
 *   PersonalIdentityRequired}) — never a null partition. The result is the SAME
 *   partition in every workspace + client.
 * - `workspace` (default) → `workspaceTenant` unchanged (the current behavior).
 *
 * The oid is a parameter here only because this pure function does not read
 * tokens; the SURFACES derive it server-side and are the sole callers — a caller
 * can never inject the oid (INV-PERSONAL layer 1).
 */
export function resolveMemoryTenant(args: {
  memoryScope: MemoryScope;
  oid: string | null | undefined;
  workspaceTenant: string | null | undefined;
  family?: string | null;
}): string | null {
  const { memoryScope, oid, workspaceTenant, family } = args;
  if (memoryScope === PERSONAL_SCOPE) {
    if (oid === null || oid === undefined || !String(oid).trim()) {
      throw new PersonalIdentityRequired(
        "memory_scope=personal requires a server-resolved identity (oid) — " +
          "authenticated requests read it from the verified token; offline/stdio " +
          "reads DNA_PERSONAL_ID. None was available — access denied (fail-closed).",
      );
    }
    return personalTenant(String(oid), family);
  }
  return workspaceTenant ?? null;
}

/**
 * Reject a caller-supplied raw `tenant` that names the reserved `personal:`
 * scheme (INV-PERSONAL layer 4, ADR §7.4). No-op for `null` / a workspace id /
 * base `''`.
 */
export function assertNoPersonalOverride(
  tenant: string | null | undefined,
): void {
  if (isPersonalTenant(tenant)) {
    throw new PersonalOverrideRejected(
      `tenant ${JSON.stringify(tenant)} names the reserved 'personal:' scheme — ` +
        "personal memory is reachable only via memory_scope=personal (identity " +
        "derived server-side), never a raw tenant override — access denied.",
    );
  }
}
