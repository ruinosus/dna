"""Helix-extras Kinds — Setting, Theme, UserProfile, Canvas.

Absorbed from ``claude-code-templates`` catalog patterns (MIT).
Spec inspiration: cli-tool/components/{commands,settings}/.

These are primitives for *Claude Code customization*, not SDLC artifacts.
They live alongside Skill / Agent / Soul (helix family) so
authoring a "complete Claude Code setup" is a single scope of docs.

Storage layout (all bundle Kinds):

    <scope>/settings/<name>/SETTING.md      → Setting bundle

Each marker file has YAML frontmatter + markdown body. The body is the
prose / usage / instructions; the frontmatter carries structured spec
fields.

Registered by ``HelixExtension.register()`` alongside the existing
Helix Kinds.
"""
from __future__ import annotations

from typing import Any

from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import StorageDescriptor, TenantScope


# ─────────────────────────────────────────────────────────────────
# Setting — declarative configuration snippet
# ─────────────────────────────────────────────────────────────────

SETTING_SCOPES = ("api", "auth", "environment", "git", "global", "hooks", "model")


class SettingKind(KindBase):
    """Setting — composable configuration snippet.

    Equivalent of ``cli-tool/components/settings/*`` in claude-code-templates.
    Each Setting carries env vars + nested config + setup instructions for
    one domain (e.g. ``vertex-configuration``, ``corporate-proxy``,
    ``model-routing``). The Studio + ``dna setting export`` compose
    selected settings into ``.claude/settings.json``.

    Storage: bundle ``settings/<name>/SETTING.md``.
    """

    api_version = "github.com/ruinosus/dna/v1"
    scope = TenantScope.GLOBAL
    kind = "Setting"
    alias = "helix-setting"
    model = dict
    origin = "github.com/ruinosus/dna"
    storage = StorageDescriptor.bundle("settings", "SETTING.md", body_field="body")
    graph_style = {"fill": "#8B5CF6", "stroke": "#7C3AED", "text_color": "#fff"}
    ascii_icon = "⚙️"
    display_label = "Settings"
    is_prompt_target = False
    flatten_in_context = False
    prompt_target_priority = 0
    description_fallback_field = "purpose"
    docs = (
        "A Setting is a reusable configuration snippet (env vars + nested "
        "config). Composed into .claude/settings.json or the runtime env. "
        "Use Setting for things like 'configure Vertex AI', 'corporate proxy', "
        "'enable model X for region Y'. Atomic, idempotent, version-pinned."
    )

    def dep_filters(self) -> dict[str, str]:
        return {}

    def dependencies(self) -> dict[str, str]:
        return self.dep_filters()

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "purpose"],
            "properties": {
                "title": {"type": "string"},
                "purpose": {
                    "type": "string",
                    "description": "What this setting does, in one line.",
                },
                "config_scope": {
                    "type": "string",
                    "enum": list(SETTING_SCOPES),
                    "default": "global",
                    "description": "Domain category (drives sidebar grouping + .claude/settings.json key).",
                },
                "env_vars": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                    "description": (
                        "Env vars set by this setting. Values may be literal or "
                        "${PLACEHOLDER} that the user fills."
                    ),
                },
                "config": {
                    "type": "object",
                    "default": {},
                    "description": (
                        "Nested config payload (merged into .claude/settings.json "
                        "under the appropriate key)."
                    ),
                },
                "instructions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Step-by-step setup checklist for the user.",
                },
                "verifies_with": {
                    "type": "string",
                    "description": "Shell command that verifies the setting is active (e.g. 'gcloud auth list').",
                },
                "tags": {
                    "type": "array", "items": {"type": "string"}, "default": [],
                },
                "owner": {"type": "string"},
                "body": {
                    "type": "string",
                    "description": "Markdown body — the SETTING.md prose.",
                },
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
            "additionalProperties": True,
        }

    def parse(self, raw: dict) -> dict:
        return raw

    def summary(self, doc: Any) -> dict[str, Any]:
        s = doc.spec if hasattr(doc, "spec") else doc
        s = s if isinstance(s, dict) else {}
        return {
            "title": s.get("title", ""),
            "config_scope": s.get("config_scope", "global"),
            "env_vars_count": len(s.get("env_vars") or {}),
        }

    def to_card(self, doc: Any) -> dict[str, Any]:
        s = doc.spec or {}
        return {
            "name": doc.name, "scope": doc.scope, "kind": "Setting",
            "title": s.get("title"), "config_scope": s.get("config_scope"),
        }

    def describe(self, doc: Any) -> str | None: return None
    def get_default_agent_name(self, doc: Any) -> str | None: return None
    def get_layer_policies(self, doc: Any) -> dict | None: return None


# ─────────────────────────────────────────────────────────────────
# Theme — Studio color palette as data
# ─────────────────────────────────────────────────────────────────

THEME_VIBES = (
    "neutral", "playful", "professional", "warm", "cool",
    "minimal", "vibrant", "high-contrast",
)


class ThemeKind(KindBase):
    """Theme — declarative color palette + typography for DNA Studio.

    Lets users pick / extend the Studio look without touching CSS.
    Each Theme doc carries a full palette (primary + accent + success)
    in light AND dark mode HSL coordinates, plus optional font / radius
    overrides. The Studio's ThemeApplier reads the active theme from
    localStorage, fetches the doc, and sets CSS custom properties on
    ``:root`` — change happens instantly, no rebuild.

    Tenants can ship their own brand theme by writing a Theme doc with
    their colors. Multi-tenant overlays work too (each tenant can have
    its own ``themes/brand.yaml``).

    Storage: yaml ``themes/<name>.yaml``.
    """

    api_version = "github.com/ruinosus/dna/v1"
    # Permissivo (sem scope): Theme é default de _lib herdável; tenants
    # podem ter tema próprio (override per-tenant). s-inheritable-kinds-tenancy-invariant.
    kind = "Theme"
    alias = "helix-theme"
    model = dict
    origin = "github.com/ruinosus/dna"
    storage = StorageDescriptor.yaml("themes")
    graph_style = {"fill": "#A855F7", "stroke": "#7E22CE", "text_color": "#fff"}
    ascii_icon = "🎨"
    display_label = "Themes"
    is_prompt_target = False
    flatten_in_context = False
    prompt_target_priority = 0
    description_fallback_field = "tagline"
    docs = (
        "A Theme declares a Studio color palette (primary/accent/success "
        "in light + dark HSL) + optional typography. ThemeApplier reads "
        "the active theme from localStorage and writes CSS variables on "
        ":root — instant switch, no rebuild. Tenants can ship a brand "
        "theme by publishing themes/brand.yaml in their scope."
    )

    def dep_filters(self) -> dict[str, str]:
        return {}

    def dependencies(self) -> dict[str, str]:
        return self.dep_filters()

    def schema(self) -> dict[str, Any]:
        hsl_triplet = {
            "type": "object",
            "required": ["h", "s", "l"],
            "properties": {
                "h": {"type": "integer", "minimum": 0, "maximum": 360, "description": "Hue 0-360"},
                "s": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Saturation 0-100%"},
                "l": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Lightness 0-100%"},
            },
        }
        palette_pair = {
            "type": "object",
            "required": ["light", "dark"],
            "properties": {
                "light": hsl_triplet,
                "dark": hsl_triplet,
            },
            "description": "Same color, two lightness/saturation tweaks for light vs dark mode.",
        }
        return {
            "type": "object",
            "required": ["display_label", "palette"],
            "properties": {
                "display_label": {
                    "type": "string",
                    "description": "Human-readable theme name (e.g. 'Cobre', 'Indigo Linear').",
                },
                "tagline": {
                    "type": "string",
                    "description": "One-line vibe summary (shown in switcher dropdown + card description).",
                },
                "vibe": {
                    "type": "string",
                    "enum": list(THEME_VIBES),
                    "default": "neutral",
                    "description": "Visual vibe tag for grouping.",
                },
                "inspiration": {
                    "type": "string",
                    "description": "Reference (e.g. 'claude-code-templates', 'Linear', 'Stripe', 'custom').",
                },
                "palette": {
                    "type": "object",
                    "required": ["primary"],
                    "properties": {
                        "primary": palette_pair,
                        "accent": {**palette_pair, "description": "Defaults to primary if omitted."},
                        "success": {**palette_pair, "description": "Defaults to primary if omitted."},
                        "warning": palette_pair,
                        "destructive": palette_pair,
                        "info": palette_pair,
                    },
                },
                "radius": {
                    "type": "string",
                    "description": "Default border radius (e.g. '0.5rem'). Maps to --radius.",
                },
                "font_sans": {
                    "type": "string",
                    "description": "Sans-serif font stack override (CSS font-family string).",
                },
                "font_mono": {
                    "type": "string",
                    "description": "Monospace font stack override.",
                },
                "preview_swatch_hex": {
                    "type": "string",
                    "description": (
                        "Optional explicit hex for the switcher swatch. "
                        "Computed from palette.primary.light if omitted."
                    ),
                },
                "tags": {
                    "type": "array", "items": {"type": "string"}, "default": [],
                },
                "owner": {"type": "string"},
                "body": {
                    "type": "string",
                    "description": (
                        "Optional markdown description — when to use, "
                        "design rationale, brand notes."
                    ),
                },
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
            "additionalProperties": True,
        }

    def parse(self, raw: dict) -> dict:
        return raw

    def summary(self, doc: Any) -> dict[str, Any]:
        s = doc.spec if hasattr(doc, "spec") else doc
        s = s if isinstance(s, dict) else {}
        palette = s.get("palette") or {}
        primary = (palette.get("primary") or {}).get("light") or {}
        return {
            "display_label": s.get("display_label", ""),
            "vibe": s.get("vibe", "neutral"),
            "hue": primary.get("h"),
        }

    def to_card(self, doc: Any) -> dict[str, Any]:
        s = doc.spec or {}
        return {
            "name": doc.name, "scope": doc.scope, "kind": "Theme",
            "display_label": s.get("display_label"),
            "vibe": s.get("vibe"),
            "tagline": s.get("tagline"),
        }

    def describe(self, doc: Any) -> str | None: return None
    def get_default_agent_name(self, doc: Any) -> str | None: return None
    def get_layer_policies(self, doc: Any) -> dict | None: return None


# ─────────────────────────────────────────────────────────────────
# UserProfile — per-user personalization data for AI agents
# ─────────────────────────────────────────────────────────────────
#
# Responsible-AI requirement (s-jarvis-user-profile, 2026-05-26):
# Personalization MUST NOT come from hardcoded prompts (anyone logging
# in would see another user's personal data). Each user has their own
# UserProfile doc; the agent reads it at session boot via
# ``get_my_profile()`` and injects only THAT user's context.
#
# Storage layout:
#
#     <scope>/users/<user-slug>/PROFILE.yaml
#
# The doc ``name`` is the user slug (deterministic from user_id —
# typically email-derived, e.g. ``jefferson-barnabe-gmail-com``). The
# tool layer is responsible for resolving the slug from the active
# request's user_id; users cannot read each other's profiles (the
# server-side ``get_my_profile`` ignores any name arg and uses the
# request user_id).
#
# Consent model: ``consent.profile_used_in_prompts`` MUST be true for
# the orchestrator to inject the profile block into a system prompt.
# Even if the doc exists, consent=false makes it inert. Users can
# revoke at any time by setting the flag false.

PROFILE_LANGUAGES = (
    "pt-BR", "en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP", "zh-CN",
)


class UserProfileKind(KindBase):
    """UserProfile — per-user data the agent uses to personalize.

    Required for any agent that addresses the user by name, adapts tone
    to their preferences, or references their projects/family/context.
    The orchestrator's prompt builder reads the current request's user_id
    + this doc + ``consent.profile_used_in_prompts=true`` to decide
    whether to inject a profile block. Without consent OR without a doc,
    the agent treats the user as anonymous and SHOULD offer to onboard
    (verbal opt-in then ``update_my_profile``).

    Storage: yaml ``users/<user-slug>/PROFILE.yaml``.
    """

    api_version = "github.com/ruinosus/dna/v1"
    scope = TenantScope.TENANTED  # per-tenant, NOT global
    kind = "UserProfile"
    alias = "helix-user-profile"
    model = dict
    origin = "github.com/ruinosus/dna"
    storage = StorageDescriptor.yaml("users")
    graph_style = {"fill": "#0EA5E9", "stroke": "#0284C7", "text_color": "#fff"}
    ascii_icon = "👤"
    display_label = "User Profiles"
    is_prompt_target = False
    flatten_in_context = False
    prompt_target_priority = 0
    description_fallback_field = "display_name"
    docs = (
        "A UserProfile holds per-user personalization data for AI agents "
        "(display name, language preference, communication style, opt-in "
        "personal/project context). Consent-gated: agents only inject the "
        "block when consent.profile_used_in_prompts is true. Each user "
        "can read/write only their own profile via the get_my_profile / "
        "update_my_profile tools — never another user's."
    )

    def dep_filters(self) -> dict[str, str]:
        return {}

    def dependencies(self) -> dict[str, str]:
        return self.dep_filters()

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["user_id", "display_name"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": (
                        "Stable identifier from the IdP (email / sub claim). "
                        "Server-side stamp — clients cannot forge."
                    ),
                },
                "display_name": {
                    "type": "string",
                    "description": "How the user wants to appear ('Jefferson Barnabé').",
                },
                "preferred_name": {
                    "type": "string",
                    "description": "What the agent should call them in conversation ('Jeff', 'Jefferson').",
                },
                "pronouns": {
                    "type": "string",
                    "description": "Optional pronoun preference ('ele/dele', 'she/her', 'they/them').",
                },
                "languages": {
                    "type": "object",
                    "properties": {
                        "default": {
                            "type": "string",
                            "enum": list(PROFILE_LANGUAGES),
                            "default": "pt-BR",
                            "description": "Default response language.",
                        },
                        "accepted": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(PROFILE_LANGUAGES)},
                            "default": [],
                            "description": "Languages the user is comfortable being addressed in.",
                        },
                        "switch_on_request": {
                            "type": "boolean",
                            "default": True,
                            "description": (
                                "When true, agent honors mid-session language switches "
                                "('fala em inglês'). When false, sticks to default."
                            ),
                        },
                    },
                },
                "communication_style": {
                    "type": "string",
                    "description": (
                        "Free text — what tone/length/formality the agent should use "
                        "('curto e direto, humor seco OK', 'formal por default')."
                    ),
                },
                "personal_context": {
                    "type": "string",
                    "description": (
                        "OPT-IN free text — family, locale, hobbies. Only injected "
                        "when consent.profile_used_in_prompts is true. The user owns "
                        "and can clear this at any time."
                    ),
                },
                "project_context": {
                    "type": "string",
                    "description": (
                        "OPT-IN free text — projects they own/care about, current focus. "
                        "Helps the agent resolve 'meu projeto', 'aquela feature'."
                    ),
                },
                "do_not_share": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": (
                        "Topics the agent must NEVER volunteer or surface unprompted. "
                        "User-defined privacy boundary."
                    ),
                },
                "consent": {
                    "type": "object",
                    "required": ["profile_used_in_prompts"],
                    "properties": {
                        "profile_used_in_prompts": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "Master gate. False = profile exists but agents treat "
                                "user as anonymous. True = injected into system prompt."
                            ),
                        },
                        "memory_persistence": {
                            "type": "boolean",
                            "default": True,
                            "description": (
                                "False = agents DO NOT write Remembrances/LessonLearned "
                                "stamped with this user_id. Existing memories stay."
                            ),
                        },
                        "voice_recording_consent": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "Per local law (GDPR / LGPD), explicit opt-in for "
                                "VoiceEpisode transcript persistence."
                            ),
                        },
                    },
                },
                "created_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Server-stamped on first create.",
                },
                "updated_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Server-stamped on every update.",
                },
                "last_seen_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Server-stamped on each session bootstrap.",
                },
                "tags": {
                    "type": "array", "items": {"type": "string"}, "default": [],
                },
            },
            "additionalProperties": True,
        }

    def parse(self, raw: dict) -> dict:
        return raw

    def summary(self, doc: Any) -> dict[str, Any]:
        s = doc.spec if hasattr(doc, "spec") else doc
        s = s if isinstance(s, dict) else {}
        return {
            "display_name": s.get("display_name", ""),
            "default_language": (s.get("languages") or {}).get("default", "pt-BR"),
            "consent_active": bool((s.get("consent") or {}).get("profile_used_in_prompts")),
        }

    def to_card(self, doc: Any) -> dict[str, Any]:
        s = doc.spec or {}
        return {
            "name": doc.name, "scope": doc.scope, "kind": "UserProfile",
            "display_name": s.get("display_name"),
            "preferred_name": s.get("preferred_name"),
        }

    def describe(self, doc: Any) -> str | None: return None
    def get_default_agent_name(self, doc: Any) -> str | None: return None
    def get_layer_policies(self, doc: Any) -> dict | None: return None


# ─────────────────────────────────────────────────────────────────
# Canvas — shared whiteboard between user (mouse/touch/hand) + JARVIS
# ─────────────────────────────────────────────────────────────────
#
# Quebra da quarta parede (s-jarvis-canvas, 2026-05-27): user e agent
# trabalham no mesmo espaço visual. User desenha com mouse/touch/pincer;
# JARVIS lê (JSON + optional vision snapshot) e escreve (discrete shape
# tools — add_shape, add_text, add_arrow).
#
# Storage: yaml ``canvases/<name>.yaml``. Spec carries the tldraw store
# (JSON snapshot) + title + summary. Embeddings extract text shapes for
# semantic recall via search_documents("aquele canvas sobre X").


class CanvasKind(KindBase):
    """Canvas — whiteboard compartilhado JARVIS ↔ user.

    Renderer: tldraw embedded no JarvisSessionContext (workbench slot).
    Persistence: spec.tldraw_store = serialized tldraw snapshot JSON.
    Auto-save: client side, 3s idle debounce, PUT /docs/Canvas/X.

    JARVIS tools:
    - ``open_canvas(name?)`` — abre na bancada (cria novo se name omitido)
    - ``read_canvas(name, mode?)`` — JSON (default) ou snapshot PNG (vision)
    - ``canvas_add_shape(name, type, x, y, w, h, text?, color?)``
    - ``canvas_add_text(name, x, y, content, size?)``
    - ``canvas_add_arrow(name, from_id, to_id, label?)``

    Storage: yaml ``canvases/<name>.yaml``.
    """

    api_version = "github.com/ruinosus/dna/v1"
    scope = TenantScope.TENANTED
    kind = "Canvas"
    alias = "helix-canvas"
    model = dict
    origin = "github.com/ruinosus/dna"
    storage = StorageDescriptor.yaml("canvases")
    graph_style = {"fill": "#06B6D4", "stroke": "#0891B2", "text_color": "#fff"}
    ascii_icon = "🎨"
    display_label = "Canvases"
    is_prompt_target = False
    flatten_in_context = False
    prompt_target_priority = 0
    description_fallback_field = "title"
    docs = (
        "A Canvas is a shared whiteboard between JARVIS and the user — "
        "tldraw-backed. User draws with mouse/touch/3D hand; JARVIS reads "
        "shapes (JSON) + optionally vision-interprets free strokes, and "
        "writes back via discrete shape tools. Persisted as first-class "
        "Kind so it's searchable, retrievable, embeddable. Quebra a "
        "quarta parede da interação voice-only."
    )

    def dep_filters(self) -> dict[str, str]:
        return {}

    def dependencies(self) -> dict[str, str]:
        return self.dep_filters()

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title"],
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Human-readable canvas name shown in listings.",
                },
                "summary": {
                    "type": "string",
                    "description": "One-line description — what's on this canvas.",
                },
                "engine": {
                    "type": "string",
                    "enum": ["tldraw", "excalidraw", "drawio"],
                    "default": "tldraw",
                    "description": (
                        "Whiteboard renderer (per-canvas, not "
                        "convertible). 3 engines kept after exploration:\n"
                        "- tldraw — rich UI, multi-page (commercial license for prod)\n"
                        "- excalidraw — MIT, hand-drawn casual sketch\n"
                        "- drawio — Apache 2.0, formal BPMN / architecture diagrams"
                    ),
                },
                "tldraw_store": {
                    "type": "object",
                    "description": "tldraw scene (shapes+bindings). engine=tldraw.",
                    "additionalProperties": True,
                },
                "excalidraw_store": {
                    "type": "object",
                    "description": "Excalidraw scene (elements+appState). engine=excalidraw.",
                    "additionalProperties": True,
                },
                "drawio_xml": {
                    "type": "string",
                    "description": "drawio mxGraph XML payload. engine=drawio.",
                },
                "thumbnail_url": {
                    "type": "string",
                    "description": (
                        "Optional snapshot PNG URL (Asset Kind ref). "
                        "Generated by client on save for list previews."
                    ),
                },
                "tags": {
                    "type": "array", "items": {"type": "string"}, "default": [],
                },
                "created_by": {
                    "type": "string",
                    "description": "user_id who first opened this canvas.",
                },
                "created_at": {
                    "type": "string", "format": "date-time",
                },
                "updated_at": {
                    "type": "string", "format": "date-time",
                },
                "last_drawn_by": {
                    "type": "string",
                    "enum": ["user", "jarvis", "mixed"],
                    "description": "Who touched the canvas most recently.",
                },
            },
            "additionalProperties": True,
        }

    def parse(self, raw: dict) -> dict:
        return raw

    def summary(self, doc: Any) -> dict[str, Any]:
        s = doc.spec if hasattr(doc, "spec") else doc
        s = s if isinstance(s, dict) else {}
        store = s.get("tldraw_store") or {}
        shapes = (store.get("shapes") if isinstance(store, dict) else None) or {}
        return {
            "title": s.get("title", ""),
            "shape_count": len(shapes) if isinstance(shapes, dict) else 0,
            "last_drawn_by": s.get("last_drawn_by", "?"),
        }

    def to_card(self, doc: Any) -> dict[str, Any]:
        s = doc.spec or {}
        return {
            "name": doc.name, "scope": doc.scope, "kind": "Canvas",
            "title": s.get("title"),
            "summary": s.get("summary"),
            "thumbnail_url": s.get("thumbnail_url"),
        }

    def describe(self, doc: Any) -> str | None: return None
    def get_default_agent_name(self, doc: Any) -> str | None: return None
    def get_layer_policies(self, doc: Any) -> dict | None: return None
