/**
 * Helix-extras Kinds — Setting, Theme, UserProfile, Canvas.
 *
 * 1:1 TS parity with dna.extensions.helix._extras (Py).
 * See that file for full documentation of each Kind's purpose.
 *
 * Absorbed from claude-code-templates catalog (MIT) — 2026-05-26.
 */

import { KindBase } from "../kernel/kind_base.js";
import type { Document } from "../kernel/document.js";
import type { PreviewBlock } from "../kernel/preview.js";
import { SD, TenantScope } from "../kernel/protocols.js";

const MOD_URL = import.meta.url;

const SETTING_SCOPES = ["api", "auth", "environment", "git", "global", "hooks", "model"] as const;

// ─────────────────────────────────────────────────────────────────
// Setting
// ─────────────────────────────────────────────────────────────────

export class SettingKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "Setting";
  readonly scope = TenantScope.GLOBAL;  // parity w/ Py (_extras) — i-180
  readonly alias = "helix-setting";
  readonly origin = "github.com/ruinosus/dna";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.bundle("settings", "SETTING.md", "text", "body");
  readonly graphStyle = { fill: "#8B5CF6", stroke: "#7C3AED", textColor: "#fff" };
  readonly asciiIcon = "⚙️";
  readonly displayLabel = "Settings";
  readonly _sourceUrl = MOD_URL;
  readonly descriptionFallbackField = "purpose";
  readonly docs =
    "A Setting is a reusable configuration snippet (env vars + nested config). " +
    "Composed into .claude/settings.json or the runtime env.";


  schema(): Record<string, unknown> {
    return {
      type: "object",
      required: ["title", "purpose"],
      properties: {
        title: { type: "string" },
        purpose: { type: "string" },
        config_scope: {
          type: "string",
          enum: [...SETTING_SCOPES],
          default: "global",
        },
        env_vars: {
          type: "object",
          additionalProperties: { type: "string" },
          default: {},
        },
        config: { type: "object", default: {} },
        instructions: { type: "array", items: { type: "string" }, default: [] },
        verifies_with: { type: "string" },
        tags: { type: "array", items: { type: "string" }, default: [] },
        owner: { type: "string" },
        body: { type: "string" },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
      additionalProperties: true,
    };
  }

  summary(doc: Document) {
    const s = (doc.spec ?? {}) as Record<string, unknown>;
    const env = (s.env_vars ?? {}) as Record<string, unknown>;
    return {
      title: (s.title as string) ?? "",
      config_scope: (s.config_scope as string) ?? "global",
      env_vars_count: Object.keys(env).length,
    };
  }

  preview(doc: Document): PreviewBlock[] {
    const s = (doc.spec ?? {}) as Record<string, unknown>;
    const body = typeof s.body === "string" ? s.body : "";
    if (!body) return [{ kind: "empty", title: `Setting ${doc.name}` }];
    return [{ kind: "markdown", title: "SETTING.md", body }];
  }
}

// ─────────────────────────────────────────────────────────────────
// Theme — Studio palette as data
// ─────────────────────────────────────────────────────────────────

const THEME_VIBES = [
  "neutral", "playful", "professional", "warm", "cool",
  "minimal", "vibrant", "high-contrast",
] as const;

export class ThemeKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "Theme";
  readonly alias = "helix-theme";
  readonly origin = "github.com/ruinosus/dna";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("themes");
  readonly graphStyle = { fill: "#A855F7", stroke: "#7E22CE", textColor: "#fff" };
  readonly asciiIcon = "🎨";
  readonly displayLabel = "Themes";
  readonly _sourceUrl = MOD_URL;
  readonly descriptionFallbackField = "tagline";
  readonly docs =
    "A Theme declares a Studio color palette (primary/accent/success in light + dark HSL) " +
    "+ optional typography. ThemeApplier reads the active theme from localStorage and writes " +
    "CSS variables on :root — instant switch, no rebuild.";


  schema(): Record<string, unknown> {
    const hslTriplet = {
      type: "object",
      required: ["h", "s", "l"],
      properties: {
        h: { type: "integer", minimum: 0, maximum: 360 },
        s: { type: "integer", minimum: 0, maximum: 100 },
        l: { type: "integer", minimum: 0, maximum: 100 },
      },
    };
    const palettePair = {
      type: "object",
      required: ["light", "dark"],
      properties: { light: hslTriplet, dark: hslTriplet },
    };
    return {
      type: "object",
      required: ["display_label", "palette"],
      properties: {
        display_label: { type: "string" },
        tagline: { type: "string" },
        vibe: { type: "string", enum: [...THEME_VIBES], default: "neutral" },
        inspiration: { type: "string" },
        palette: {
          type: "object",
          required: ["primary"],
          properties: {
            primary: palettePair,
            accent: palettePair,
            success: palettePair,
            warning: palettePair,
            destructive: palettePair,
            info: palettePair,
          },
        },
        radius: { type: "string" },
        font_sans: { type: "string" },
        font_mono: { type: "string" },
        preview_swatch_hex: { type: "string" },
        tags: { type: "array", items: { type: "string" }, default: [] },
        owner: { type: "string" },
        body: { type: "string" },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
      additionalProperties: true,
    };
  }

  summary(doc: Document) {
    const s = (doc.spec ?? {}) as Record<string, unknown>;
    const palette = (s.palette ?? {}) as Record<string, unknown>;
    const primary = ((palette.primary ?? {}) as Record<string, unknown>).light as
      | Record<string, number> | undefined;
    return {
      display_label: (s.display_label as string) ?? "",
      vibe: (s.vibe as string) ?? "neutral",
      hue: primary?.h,
    };
  }

  preview(doc: Document): PreviewBlock[] {
    const s = (doc.spec ?? {}) as Record<string, unknown>;
    return [{ kind: "fields", title: `Theme ${doc.name}`, fields: [
      { label: "vibe", value: String(s.vibe ?? "neutral") },
      { label: "label", value: String(s.display_label ?? "") },
    ] }];
  }
}


// ───────────────────────────────────────────────────────────────
// UserProfile — per-user personalization data for AI agents
// ───────────────────────────────────────────────────────────────
//
// Responsible-AI requirement (s-jarvis-user-profile, 2026-05-26):
// Personalization MUST NOT come from hardcoded prompts. Each user has
// their own UserProfile doc; agents inject only THAT user's context at
// session bootstrap via the get_my_profile tool. Server-side stamps
// the user_id from the request; clients cannot forge.

export const PROFILE_LANGUAGES = [
  "pt-BR", "en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP", "zh-CN",
] as const;

export class UserProfileKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "UserProfile";
  readonly scope = TenantScope.TENANTED;  // per-tenant data — parity w/ Py — i-180
  readonly alias = "helix-user-profile";
  readonly origin = "github.com/ruinosus/dna";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("users");
  readonly graphStyle = { fill: "#0EA5E9", stroke: "#0284C7", textColor: "#fff" };
  readonly asciiIcon = "👤";
  readonly displayLabel = "User Profiles";
  readonly _sourceUrl = MOD_URL;
  readonly descriptionFallbackField = "display_name";
  readonly docs =
    "A UserProfile holds per-user personalization data for AI agents (display name, " +
    "language preference, communication style, opt-in personal/project context). " +
    "Consent-gated: agents only inject the block when consent.profile_used_in_prompts " +
    "is true. Each user can read/write only their own profile via get_my_profile / " +
    "update_my_profile — never another user's.";


  schema(): Record<string, unknown> {
    return {
      type: "object",
      required: ["user_id", "display_name"],
      properties: {
        user_id: { type: "string", description: "Stable IdP identifier (email/sub claim). Server-stamped." },
        display_name: { type: "string", description: "How the user wants to appear." },
        preferred_name: { type: "string", description: "What the agent should call them." },
        pronouns: { type: "string", description: "Optional pronoun preference." },
        languages: {
          type: "object",
          properties: {
            default: { type: "string", enum: [...PROFILE_LANGUAGES], default: "pt-BR" },
            accepted: { type: "array", items: { type: "string", enum: [...PROFILE_LANGUAGES] }, default: [] },
            switch_on_request: { type: "boolean", default: true },
          },
        },
        communication_style: { type: "string", description: "Free-text tone/length/formality preference." },
        personal_context: { type: "string", description: "OPT-IN free text — family/locale/hobbies." },
        project_context: { type: "string", description: "OPT-IN free text — projects + current focus." },
        do_not_share: {
          type: "array", items: { type: "string" }, default: [],
          description: "Topics the agent must NEVER volunteer unprompted.",
        },
        consent: {
          type: "object",
          required: ["profile_used_in_prompts"],
          properties: {
            profile_used_in_prompts: { type: "boolean", default: false },
            memory_persistence: { type: "boolean", default: true },
            voice_recording_consent: { type: "boolean", default: false },
          },
        },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
        last_seen_at: { type: "string", format: "date-time" },
        tags: { type: "array", items: { type: "string" }, default: [] },
      },
      additionalProperties: true,
    };
  }


  summary(doc: Document) {
    const s = (doc.spec ?? {}) as Record<string, unknown>;
    const languages = (s.languages ?? {}) as Record<string, unknown>;
    const consent = (s.consent ?? {}) as Record<string, unknown>;
    return {
      display_name: (s.display_name as string) ?? "",
      default_language: (languages.default as string) ?? "pt-BR",
      consent_active: Boolean(consent.profile_used_in_prompts),
    };
  }

  preview(doc: Document): PreviewBlock[] {
    const s = (doc.spec ?? {}) as Record<string, unknown>;
    return [{ kind: "fields", title: `Profile ${doc.name}`, fields: [
      { label: "display_name", value: String(s.display_name ?? "") },
      { label: "preferred_name", value: String(s.preferred_name ?? "") },
    ] }];
  }
}


// ─────────────────────────────────────────────────────────────────
// Canvas — shared whiteboard JARVIS ↔ user (1:1 twin of Py CanvasKind)
// ─────────────────────────────────────────────────────────────────

export class CanvasKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "Canvas";
  readonly scope = TenantScope.TENANTED;  // per-tenant data — parity w/ Py — i-180
  readonly alias = "helix-canvas";
  readonly origin = "github.com/ruinosus/dna";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("canvases");
  readonly graphStyle = { fill: "#06B6D4", stroke: "#0891B2", textColor: "#fff" };
  readonly asciiIcon = "🎨";
  readonly displayLabel = "Canvases";
  readonly _sourceUrl = MOD_URL;
  readonly descriptionFallbackField = "title";
  readonly docs =
    "A Canvas is a shared whiteboard between JARVIS and the user — " +
    "tldraw-backed. User draws with mouse/touch/3D hand; JARVIS reads " +
    "shapes (JSON) + optionally vision-interprets free strokes, and " +
    "writes back via discrete shape tools.";

  depFilters() { return {}; }

  schema(): Record<string, unknown> {
    return {
      type: "object",
      required: ["title"],
      properties: {
        title: { type: "string" },
        summary: { type: "string" },
        engine: {
          type: "string",
          enum: ["tldraw", "excalidraw", "drawio"],
          default: "tldraw",
        },
        tldraw_store: { type: "object", additionalProperties: true },
        excalidraw_store: { type: "object", additionalProperties: true },
        drawio_xml: { type: "string" },
        thumbnail_url: { type: "string" },
        tags: { type: "array", items: { type: "string" }, default: [] },
        created_by: { type: "string" },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
        last_drawn_by: { type: "string", enum: ["user", "jarvis", "mixed"] },
      },
      additionalProperties: true,
    };
  }


  summary(doc: Document) {
    const s = (doc.spec ?? {}) as Record<string, unknown>;
    const store = (s.tldraw_store ?? {}) as Record<string, unknown>;
    const shapes = (store.shapes ?? {}) as Record<string, unknown>;
    return {
      title: (s.title as string) ?? "",
      shape_count: typeof shapes === "object" ? Object.keys(shapes).length : 0,
      last_drawn_by: (s.last_drawn_by as string) ?? "?",
    };
  }

  preview(doc: Document): PreviewBlock[] {
    const s = (doc.spec ?? {}) as Record<string, unknown>;
    return [{
      kind: "fields", title: `Canvas ${doc.name}`, fields: [
        { label: "title", value: String(s.title ?? "") },
        { label: "summary", value: String(s.summary ?? "") },
        { label: "last_drawn_by", value: String(s.last_drawn_by ?? "?") },
      ],
    }];
  }
}
