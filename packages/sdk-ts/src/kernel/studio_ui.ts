/**
 * StudioUIMetadata — UI declarations attached to a KindPort.
 *
 * Net-new TS twin of Python `dna.kernel.studio_ui.StudioUIMetadata`
 * (studio_ui.py:54-215), added for the descriptor-expressiveness `ui:` field
 * (spec 2026-06-11 D1). Reverses the previously-documented posture that `ui`
 * was "a Studio-backend concern… intentionally not mirrored"
 * (src/extensions/audit.ts) — byte-parity of `.kind.yaml` descriptors across
 * runtimes requires BOTH the Python and the TS DeclarativeKindPort to parse the
 * same `ui:` block into the same data and serialize it identically.
 *
 * Field-for-field mirror + `toDict()` (same omission rules as Python
 * `to_dict()`) + `resolveLabel()` (same i18n fallback order as Python
 * `resolve_label()`). There is no TS class golden for `ui` (TS Kind classes
 * never carried it); the parity pin is structural — `toDict()` parity with
 * Python via the shared fixture tests/fixtures/studio-ui-parity.json.
 */

/** Studio mode this Kind primarily belongs to. */
export type ModeId = "plan" | "build" | "quality" | "govern" | "cognitive";

/** CRUD action a route serves. */
export type UIAction = "list" | "detail" | "edit" | "create";

/** Locale → translated string. e.g. {en: 'Eval Cases', 'pt-BR': 'Casos'}. */
export type LabelI18n = Record<string, string>;

/**
 * Canonical, ordered set of StudioUIMetadata field names. Single source of
 * truth — `KindDefinitionSpec.from_raw`/zod validate `ui:` keys against THIS
 * list (no second hardcoded list). Mirrors the Python dataclass field order.
 */
export const UI_METADATA_FIELDS = [
  "mode",
  "in_sidebar",
  "display_order",
  "label",
  "icon",
  "description",
  "breadcrumb",
  "routes",
  "permissions",
  "note",
  "feature_flag",
] as const;

export type UIMetadataField = (typeof UI_METADATA_FIELDS)[number];

/** Constructor input — every field optional, mirroring the Python dataclass
 *  defaults (no mode, no sidebar, display_order 100, all others None/empty). */
export interface StudioUIMetadataInit {
  mode?: ModeId | null;
  in_sidebar?: boolean;
  display_order?: number;
  label?: string | LabelI18n | null;
  icon?: string | null;
  description?: string | LabelI18n | null;
  breadcrumb?: string[] | null;
  routes?: Record<string, string>;
  permissions?: Record<string, string[] | string>;
  note?: string | null;
  feature_flag?: string | null;
}

/**
 * UI declarations for a Kind, consumed by Studio's manifest. Defaults are
 * conservative: no mode, no sidebar, no routes — the Kind is invisible in
 * Studio unless explicitly opted in. 1:1 with Python `StudioUIMetadata`.
 */
export class StudioUIMetadata {
  readonly mode: ModeId | null;
  readonly in_sidebar: boolean;
  readonly display_order: number;
  readonly label: string | LabelI18n | null;
  readonly icon: string | null;
  readonly description: string | LabelI18n | null;
  readonly breadcrumb: string[] | null;
  readonly routes: Record<string, string>;
  readonly permissions: Record<string, string[] | string>;
  readonly note: string | null;
  readonly feature_flag: string | null;

  constructor(init: StudioUIMetadataInit = {}) {
    this.mode = init.mode ?? null;
    this.in_sidebar = init.in_sidebar ?? false;
    this.display_order = init.display_order ?? 100;
    this.label = init.label ?? null;
    this.icon = init.icon ?? null;
    this.description = init.description ?? null;
    this.breadcrumb = init.breadcrumb ?? null;
    this.routes = init.routes ?? {};
    this.permissions = init.permissions ?? {};
    this.note = init.note ?? null;
    this.feature_flag = init.feature_flag ?? null;
  }

  /** The canonical field-name set (single source of truth for `ui:` validation). */
  static fields(): readonly UIMetadataField[] {
    return UI_METADATA_FIELDS;
  }

  /**
   * Serialize for the /kinds/manifest JSON response. Omits None/empty fields
   * so the wire payload stays small — EXACTLY the Python `to_dict()` omission
   * rules (studio_ui.py:161-192):
   *   - mode: only if not null
   *   - in_sidebar: only if true
   *   - display_order: only if !== 100
   *   - label/icon/description/note/feature_flag: only if not null
   *   - breadcrumb: only if not null (an empty list IS kept, like Python)
   *   - routes/permissions: only if non-empty
   */
  toDict(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    if (this.mode !== null) out.mode = this.mode;
    if (this.in_sidebar) out.in_sidebar = true;
    if (this.display_order !== 100) out.display_order = this.display_order;
    if (this.label !== null) out.label = this.label;
    if (this.icon !== null) out.icon = this.icon;
    if (this.description !== null) out.description = this.description;
    if (this.breadcrumb !== null) out.breadcrumb = [...this.breadcrumb];
    if (Object.keys(this.routes).length > 0) out.routes = { ...this.routes };
    if (Object.keys(this.permissions).length > 0) {
      const perms: Record<string, string[] | string> = {};
      for (const [k, v] of Object.entries(this.permissions)) {
        perms[k] = Array.isArray(v) ? [...v] : v;
      }
      out.permissions = perms;
    }
    if (this.note !== null) out.note = this.note;
    if (this.feature_flag !== null) out.feature_flag = this.feature_flag;
    return out;
  }

  /**
   * Resolve i18n label for the requested locale. Fallback order (mirrors
   * Python `resolve_label`):
   *   1. Exact locale match (e.g. 'pt-BR').
   *   2. Language-only fallback (e.g. 'pt' from 'pt-BR').
   *   3. 'en' (project default).
   *   4. null.
   * A plain-string label is returned as-is regardless of locale.
   */
  resolveLabel(locale = "en"): string | null {
    if (this.label === null) return null;
    if (typeof this.label === "string") return this.label;
    if (locale in this.label) return this.label[locale];
    if (locale.includes("-")) {
      const base = locale.split("-", 1)[0];
      if (base in this.label) return this.label[base];
    }
    return this.label.en ?? null;
  }
}
