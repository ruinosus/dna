/**
 * TenantExtension — multi-tenant identity Kinds (TS twin).
 *
 * 1:1 parity with python/dna/extensions/tenant/__init__.py. Two GLOBAL
 * bundle Kinds:
 *   - Tenant (tenant-tenant) — org/team identity (TENANT.md).
 *   - TenantMembership (tenant-membership) — user↔tenant link (MEMBERSHIP.md).
 * Both strict-detect on apiVersion; envelope (fm.spec) reader with flat fallback.
 */
import yaml from "js-yaml";

import type { Extension, ReaderPort, SerializedFile, WriterPort, KindPort } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD, TenantScope } from "../kernel/protocols.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import type { Document } from "../kernel/document.js";
import { popSourceFilesAsEntries, writeEntriesToHandle } from "../kernel/writer-helpers.js";

const API_VERSION = "github.com/ruinosus/dna/tenant/v1";

function parseFrontmatter(text: string): { fm: Record<string, unknown>; body: string } {
  const m = text.match(/^---\n([\s\S]*?)---\n?([\s\S]*)$/);
  if (!m) return { fm: {}, body: text };
  try {
    const parsed = yaml.load(m[1]!) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { fm: parsed as Record<string, unknown>, body: (m[2] ?? "").replace(/^\n+/, "") };
    }
  } catch {
    // fall through
  }
  return { fm: {}, body: text };
}

function cleanSpecMeta(raw: Record<string, unknown>): { cleanSpec: Record<string, unknown>; cleanMeta: Record<string, unknown> } {
  const spec = (raw["spec"] ?? {}) as Record<string, unknown>;
  const meta = (raw["metadata"] ?? {}) as Record<string, unknown>;
  const cleanSpec: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(spec)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v) && v.length === 0) continue;
    if (typeof v === "object" && !Array.isArray(v) && Object.keys(v as object).length === 0) continue;
    cleanSpec[k] = v;
  }
  const cleanMeta: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(meta)) {
    if (v !== null && v !== undefined) cleanMeta[k] = v;
  }
  return { cleanSpec, cleanMeta };
}

// ---------------------------------------------------------------------------
// Tenant
// ---------------------------------------------------------------------------

class TenantKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "Tenant";
  readonly alias = "tenant-tenant";
  readonly origin = "github.com/ruinosus/dna/tenant";
  // GLOBAL — the Tenant kind is itself global, no tenant overlay.
  readonly scope = TenantScope.GLOBAL;
  readonly storage = SD.bundle("tenants", "TENANT.md");
  readonly graphStyle = { fill: "#0EA5E9", stroke: "#0369A1", textColor: "#fff" };
  readonly asciiIcon = "🏢";
  readonly displayLabel = "Tenants";
  readonly isPromptTarget = false;
  readonly flattenInContext = false;
  readonly docs =
    "A Tenant is the identity of an organization/team/individual that owns scopes " +
    "and the documents within them. Stored as bundle (TENANT.md frontmatter = spec) " +
    "under the special `_lib` scope. Slug rules match the runtime tenant claim " +
    "format ([a-z0-9-]{1,253}). Created by platform admins via POST /tenants. " +
    "Suspended via PATCH; soft-deleted via DELETE (status=deleted, 30d grace period " +
    "before physical purge by background cron). Member management lives in Phase B " +
    "(separate TenantMembership kind).";

  dependencies() { return null; }

  schema() {
    return {
      type: "object",
      required: ["slug", "display_name", "owner_email", "status"],
      additionalProperties: true,
      properties: {
        slug: { type: "string", pattern: "^[a-z0-9-]{1,253}$", description: "Tenant identity. Used as the value of dna_documents.tenant for every doc owned by this tenant. Must match the runtime tenant claim format." },
        display_name: { type: "string", minLength: 1, maxLength: 200, description: "Human-readable name shown in Studio." },
        owner_email: { type: "string", format: "email", description: "Email of the human that provisioned this tenant. First member of the tenant by default." },
        status: { type: "string", enum: ["active", "suspended", "deleted"], default: "active", description: "Lifecycle state. `deleted` is soft — docs stay in PG until the purge cron runs (~30d later)." },
        plan: { type: "string", enum: ["free", "pro", "enterprise"], default: "free", description: "Billing/feature tier." },
        created_at: { type: "string", format: "date-time", description: "ISO timestamp when the Tenant was provisioned." },
        suspended_at: { type: "string", format: "date-time" },
        deleted_at: { type: "string", format: "date-time", description: "Set on soft-delete. Cron purges ~30d later." },
        member_count_cached: { type: "integer", minimum: 0, default: 0, description: "Denormalized count. Refreshed by membership mutations (Phase B). Eventually-consistent." },
        metadata: { type: "object", additionalProperties: true, description: "Free-form metadata (region, lgpd_consent, billing_account_id, etc). Forward-compatible." },
      },
    };
  }

  describe(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const name = (spec.display_name as string) || (spec.slug as string) || "?";
    return `${name} [${(spec.status as string) ?? "?"} · ${(spec.plan as string) ?? "?"}]`;
  }

  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      slug: (spec.slug as string) ?? "",
      display_name: (spec.display_name as string) ?? "",
      status: (spec.status as string) ?? "active",
      plan: (spec.plan as string) ?? "free",
      member_count: (spec.member_count_cached as number) ?? 0,
    };
  }
}

class TenantReader implements ReaderPort {
  async detect(bundle: BundleHandle): Promise<boolean> {
    if (!(await bundle.exists("TENANT.md"))) return false;
    try {
      const { fm } = parseFrontmatter(await bundle.readText("TENANT.md"));
      return !!fm && fm["apiVersion"] === API_VERSION;
    } catch {
      return false;
    }
  }

  async read(bundle: BundleHandle): Promise<Record<string, unknown>> {
    const { fm } = parseFrontmatter(await bundle.readText("TENANT.md"));
    if ("spec" in fm) {
      const metadata = (fm["metadata"] as Record<string, unknown>) ?? {};
      if (!("name" in metadata)) metadata["name"] = bundle.name;
      return {
        apiVersion: (fm["apiVersion"] as string) ?? API_VERSION,
        kind: (fm["kind"] as string) ?? "Tenant",
        metadata,
        spec: (fm["spec"] as Record<string, unknown>) ?? {},
      };
    }
    const name = (fm["name"] as string) ?? bundle.name;
    delete fm["name"];
    return { apiVersion: API_VERSION, kind: "Tenant", metadata: { name }, spec: fm };
  }
}

class TenantWriter implements WriterPort {
  canWrite(raw: Record<string, unknown>): boolean {
    return raw["kind"] === "Tenant";
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const spec = (raw["spec"] ?? {}) as Record<string, unknown>;
    const extraEntries = popSourceFilesAsEntries(spec, "Tenant");
    const { cleanSpec, cleanMeta } = cleanSpecMeta(raw);
    const envelope = {
      apiVersion: (raw["apiVersion"] as string) ?? API_VERSION,
      kind: (raw["kind"] as string) ?? "Tenant",
      metadata: cleanMeta,
      spec: cleanSpec,
    };
    const fmYaml = yaml.dump(envelope, { lineWidth: 100, noRefs: true, sortKeys: false }).trimEnd();
    const slug = (cleanSpec["slug"] as string) ?? "?";
    const display = (cleanSpec["display_name"] as string) ?? "?";
    const status = (cleanSpec["status"] as string) ?? "active";
    const plan = (cleanSpec["plan"] as string) ?? "free";
    const body =
      `# Tenant — ${display} (\`${slug}\`)\n\n` +
      `**Status:** ${status} · **Plan:** ${plan}\n\n` +
      `Owner: \`${(cleanSpec["owner_email"] as string) ?? "?"}\` · ` +
      `Created: \`${(cleanSpec["created_at"] as string) ?? "?"}\`\n\n` +
      `All DNA documents that carry \`dna_documents.tenant = '${slug}'\` belong to ` +
      `this Tenant. Lifecycle managed by platform admins via \`POST /tenants\`, ` +
      `\`PATCH /tenants/{slug}\`, \`DELETE /tenants/{slug}\`.`;
    return [{ relativePath: "TENANT.md", content: `---\n${fmYaml}\n---\n\n${body}` }, ...extraEntries];
  }

  async write(bundle: BundleHandle, raw: Record<string, unknown>): Promise<void> {
    await writeEntriesToHandle(bundle, this.serialize(raw));
  }
}

// ---------------------------------------------------------------------------
// TenantMembership
// ---------------------------------------------------------------------------

class TenantMembershipKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "TenantMembership";
  readonly alias = "tenant-membership";
  readonly origin = "github.com/ruinosus/dna/tenant";
  readonly scope = TenantScope.GLOBAL;
  readonly storage = SD.bundle("tenant-memberships", "MEMBERSHIP.md");
  readonly graphStyle = { fill: "#8B5CF6", stroke: "#5B21B6", textColor: "#fff" };
  readonly asciiIcon = "👥";
  readonly displayLabel = "Tenant Memberships";
  readonly isPromptTarget = false;
  readonly flattenInContext = false;
  readonly docs =
    "Links a user to a Tenant with a role. One row per (tenant, user) pair. " +
    "Created when an admin invites a member via POST /tenants/{slug}/members. " +
    "Deleted by DELETE on same path. Tenant.spec.member_count_cached is updated " +
    "by the route handler on each mutation (eventually-consistent).";

  dependencies() { return null; }

  schema() {
    return {
      type: "object",
      required: ["tenant_slug", "user_email", "role", "joined_at"],
      additionalProperties: true,
      properties: {
        tenant_slug: { type: "string", pattern: "^[a-z0-9-]{1,253}$", description: "Slug of the Tenant this user belongs to." },
        user_email: { type: "string", format: "email", description: "Email identity of the user." },
        user_id: { type: "string", description: "Stable user identifier from the IdP (Clerk sub, OIDC sub, etc). May be absent for invites pending first login — in that case user_email is the key." },
        role: { type: "string", enum: ["owner", "admin", "member", "viewer"], default: "member", description: "Per-tenant role. `owner` is the user who provisioned the tenant (set by POST /tenants). `admin` can manage members + tenant settings. `member` can read/write scope docs. `viewer` is read-only." },
        joined_at: { type: "string", format: "date-time", description: "ISO timestamp when the membership was created." },
        invited_by: { type: "string", format: "email", description: "Email of the admin who invited this member." },
        status: { type: "string", enum: ["active", "pending", "revoked"], default: "active", description: "`pending` for invites awaiting first login; `active` after first login (route handler transitions); `revoked` after admin removes." },
        view_preset: { type: "string", description: "Optional override of Studio's auto-detected view. When set, the UI renders the curated menu/mode-tab subset matching this preset instead of deriving from the user's roles. Lets a power-user temporarily 'see as' a consumer/educator. Auto-detect from roles is the default when this is null. Values follow the same vocabulary as Role (consumer, maker, qa, po, pm, architect, tech-lead, compliance, power-user, tenant-admin, tenant-owner, platform-admin) — pick the single most-relevant intent." },
      },
    };
  }

  describe(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return `${(spec.user_email as string) ?? "?"} @ ${(spec.tenant_slug as string) ?? "?"} [${(spec.role as string) ?? "?"}]`;
  }

  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      tenant_slug: (spec.tenant_slug as string) ?? "",
      user_email: (spec.user_email as string) ?? "",
      role: (spec.role as string) ?? "member",
      status: (spec.status as string) ?? "active",
    };
  }
}

class TenantMembershipReader implements ReaderPort {
  async detect(bundle: BundleHandle): Promise<boolean> {
    if (!(await bundle.exists("MEMBERSHIP.md"))) return false;
    try {
      const { fm } = parseFrontmatter(await bundle.readText("MEMBERSHIP.md"));
      return !!fm && fm["apiVersion"] === API_VERSION && fm["kind"] === "TenantMembership";
    } catch {
      return false;
    }
  }

  async read(bundle: BundleHandle): Promise<Record<string, unknown>> {
    const { fm } = parseFrontmatter(await bundle.readText("MEMBERSHIP.md"));
    if ("spec" in fm) {
      const metadata = (fm["metadata"] as Record<string, unknown>) ?? {};
      if (!("name" in metadata)) metadata["name"] = bundle.name;
      return {
        apiVersion: (fm["apiVersion"] as string) ?? API_VERSION,
        kind: (fm["kind"] as string) ?? "TenantMembership",
        metadata,
        spec: (fm["spec"] as Record<string, unknown>) ?? {},
      };
    }
    const name = (fm["name"] as string) ?? bundle.name;
    delete fm["name"];
    return { apiVersion: API_VERSION, kind: "TenantMembership", metadata: { name }, spec: fm };
  }
}

class TenantMembershipWriter implements WriterPort {
  canWrite(raw: Record<string, unknown>): boolean {
    return raw["kind"] === "TenantMembership";
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const spec = (raw["spec"] ?? {}) as Record<string, unknown>;
    const extraEntries = popSourceFilesAsEntries(spec, "TenantMembership");
    const { cleanSpec, cleanMeta } = cleanSpecMeta(raw);
    const envelope = {
      apiVersion: (raw["apiVersion"] as string) ?? API_VERSION,
      kind: (raw["kind"] as string) ?? "TenantMembership",
      metadata: cleanMeta,
      spec: cleanSpec,
    };
    const fmYaml = yaml.dump(envelope, { lineWidth: 100, noRefs: true, sortKeys: false }).trimEnd();
    const userEmail = (cleanSpec["user_email"] as string) ?? "?";
    const tenantSlug = (cleanSpec["tenant_slug"] as string) ?? "?";
    const role = (cleanSpec["role"] as string) ?? "member";
    const body =
      `# Membership — \`${userEmail}\` @ \`${tenantSlug}\`\n\n` +
      `**Role:** ${role} · **Status:** ${(cleanSpec["status"] as string) ?? "active"}\n\n` +
      `Joined: \`${(cleanSpec["joined_at"] as string) ?? "?"}\` · ` +
      `Invited by: \`${(cleanSpec["invited_by"] as string) ?? "(self-provisioned)"}\``;
    return [{ relativePath: "MEMBERSHIP.md", content: `---\n${fmYaml}\n---\n\n${body}` }, ...extraEntries];
  }

  async write(bundle: BundleHandle, raw: Record<string, unknown>): Promise<void> {
    await writeEntriesToHandle(bundle, this.serialize(raw));
  }
}

export class TenantExtension implements Extension {
  name = "tenant";
  version = "1.0.0";
  register(kernel: { kind: (k: KindPort) => void; reader: (r: ReaderPort) => void; writer: (w: WriterPort) => void }) {
    kernel.kind(new TenantKind());
    kernel.reader(new TenantReader());
    kernel.writer(new TenantWriter());
    kernel.kind(new TenantMembershipKind());
    kernel.reader(new TenantMembershipReader());
    kernel.writer(new TenantMembershipWriter());
  }
}
