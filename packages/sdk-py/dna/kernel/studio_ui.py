"""StudioUIMetadata — UI declarations attached to KindPort.

Phase 2 of the route-manifest Big-Bang (s-studio-ui-metadata, 2026-05-16).

Anchors Studio UI metadata (mode, routes, labels, RBAC, i18n) in the
DNA SDK itself. Studio fetches `GET /kinds/manifest` at boot, merges
with its static TS-side manifest, and generates router + sidebar +
sitemap entries automatically.

Why anchor in the SDK?
  - Third-party extensions ship Kinds + UI metadata together. No
    Studio code change needed when a new Kind appears.
  - RBAC declared alongside the Kind (single source instead of
    Python KIND_WRITE_ROLES + TS requiredAnyRole duplicate).
  - i18n: labels can be a {locale: str} dict — Studio picks the
    user's locale at boot.
  - Schema-driven CRUD (Phase 3+): the same Kind.schema() that
    validates writes also drives form rendering.

Compatibility: `ui` is OPTIONAL. Existing ~30 Kinds without `ui`
populated remain invisible in Studio's manifest-driven surfaces.
The Phase 1 TS-side route-manifest.ts still defines app-shell +
mode-landing + workflow routes that aren't Kind-specific.

Backwards compat: schema is forward-compatible. New optional fields
can be added without breaking existing Kinds. Old Studio versions
ignore fields they don't understand (the harness response includes
``manifest_version`` for explicit checks).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ─────────────────────────────────────────────────────────────────────
# Type aliases
# ─────────────────────────────────────────────────────────────────────

ModeId = Literal["plan", "build", "quality", "govern", "cognitive"]
"""Studio mode this Kind primarily belongs to."""

UIAction = Literal["list", "detail", "edit", "create"]
"""CRUD action a route serves."""

LabelI18n = dict[str, str]
"""Locale → translated string. e.g. {'en': 'Eval Cases', 'pt-BR': 'Casos'}."""


# ─────────────────────────────────────────────────────────────────────
# StudioUIMetadata
# ─────────────────────────────────────────────────────────────────────

@dataclass
class StudioUIMetadata:
    """UI declarations for a Kind, consumed by Studio's manifest.

    Populate on a KindPort by setting `ui = StudioUIMetadata(...)`.
    Defaults are conservative: no mode, no sidebar, no routes — the
    Kind is invisible in Studio unless explicitly opted in.

    Example::

        class EvalExperimentKind(KindBase):
            kind = "EvalExperiment"
            alias = "eval-evalexperiment"
            ...
            ui = StudioUIMetadata(
                mode="quality",
                label={"en": "Experiments", "pt-BR": "Experimentos"},
                icon="🔬",
                in_sidebar=True,
                routes={
                    "list":   "eval/experiments",
                    "detail": "eval/experiments/:expId",
                },
                permissions={
                    "list":   "any",
                    "detail": "any",
                    "create": ["maker", "qa"],
                    "edit":   ["maker", "qa"],
                },
                breadcrumb=["Quality", "Experiments"],
                display_order=20,
            )
    """

    # ── Mode + sidebar placement ─────────────────────────────────────

    mode: ModeId | None = None
    """Studio mode this Kind belongs to. None = the Kind exists in
    the system but doesn't claim a mode (won't appear in mode
    sidebars even with in_sidebar=True)."""

    in_sidebar: bool = False
    """When True, the Kind's list route renders in the mode's Sidebar
    via the manifest. Detail/edit/create routes never go in sidebar."""

    display_order: int = 100
    """Sort order in the Sidebar (lower = higher). Cluster items
    semantically: e.g. 10–19 for primary, 20–29 for secondary."""

    # ── Labels (i18n-ready) ──────────────────────────────────────────

    label: str | LabelI18n | None = None
    """Display label. Either a plain string OR a {locale: str} dict.
    None falls back to KindPort.display_label (legacy) or Kind name."""

    icon: str | None = None
    """Emoji or icon identifier. None falls back to ascii_icon."""

    description: str | LabelI18n | None = None
    """Longer description for tooltips + sitemap. i18n-ready."""

    breadcrumb: list[str] | None = None
    """Breadcrumb fragments from app root to this Kind's list route.
    E.g. ['Quality', 'Lab', 'Cases'] for EvalCase."""

    # ── Routes (per CRUD action) ─────────────────────────────────────

    routes: dict[UIAction, str] = field(default_factory=dict)
    """Path pattern per action. Leading "/" = ABSOLUTE (root-level);
    no leading slash = scope-relative (prefix /scopes/:scope/).

    Examples::

        routes={
            "list":   "docs/Story",                        # /scopes/X/docs/Story
            "detail": "docs/Story/:name",                  # /scopes/X/docs/Story/foo
            "create": "kinds/Story/__new__",
        }
    """

    # ── RBAC ─────────────────────────────────────────────────────────

    permissions: dict[UIAction, list[str] | str] = field(default_factory=dict)
    """Per-action role requirements. Each value is either:

      - ``"any"`` — any logged-in user
      - ``"anonymous"`` — no auth required (rare, e.g. public Doc)
      - ``list[str]`` — at least one role match required;
        power-user bypasses every gate

    Missing actions default to ``"any"`` for list/detail and to
    ``["architect", "maker"]`` for create/edit — sensible defaults
    that match the Phase 1 KIND_WRITE_ROLES baseline.
    """

    # ── Future extensions ─────────────────────────────────────────────

    note: str | None = None
    """Free-form annotation — surfaces in /studio/sitemap admin page."""

    feature_flag: str | None = None
    """Optional env-flag gating (e.g. 'VITE_STUDIO_COGNITIVE').
    Studio hides the Kind in UI when the flag isn't set. Backend
    routes still work — this is purely a visibility hint."""

    # ─────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the /kinds/manifest JSON response.

        Omits None/empty fields so the wire payload stays small.
        """
        out: dict[str, Any] = {}
        if self.mode is not None:
            out["mode"] = self.mode
        if self.in_sidebar:
            out["in_sidebar"] = True
        if self.display_order != 100:
            out["display_order"] = self.display_order
        if self.label is not None:
            out["label"] = self.label
        if self.icon is not None:
            out["icon"] = self.icon
        if self.description is not None:
            out["description"] = self.description
        if self.breadcrumb is not None:
            out["breadcrumb"] = list(self.breadcrumb)
        if self.routes:
            out["routes"] = dict(self.routes)
        if self.permissions:
            out["permissions"] = {
                k: list(v) if isinstance(v, list) else v
                for k, v in self.permissions.items()
            }
        if self.note is not None:
            out["note"] = self.note
        if self.feature_flag is not None:
            out["feature_flag"] = self.feature_flag
        return out

    def resolve_label(self, locale: str = "en") -> str | None:
        """Resolve i18n label for the requested locale.

        Fallback order:
          1. Exact locale match (e.g. 'pt-BR').
          2. Language-only fallback (e.g. 'pt' from 'pt-BR').
          3. 'en' (project default).
          4. None.

        Plain-string label is returned as-is regardless of locale.
        """
        if self.label is None:
            return None
        if isinstance(self.label, str):
            return self.label
        if locale in self.label:
            return self.label[locale]
        if "-" in locale:
            base = locale.split("-", 1)[0]
            if base in self.label:
                return self.label[base]
        return self.label.get("en")


# ─────────────────────────────────────────────────────────────────────
# docs_ui — convention helper (s-kinds-studio-ui-exposure)
# ─────────────────────────────────────────────────────────────────────

def docs_ui(
    kind: str,
    *,
    mode: ModeId,
    label_en: str,
    label_pt: str,
    icon: str | None = None,
    display_order: int = 60,
    description_en: str | None = None,
    description_pt: str | None = None,
    breadcrumb: list[str] | None = None,
    in_sidebar: bool = True,
    read: list[str] | str = "any",
) -> StudioUIMetadata:
    """Build a StudioUIMetadata for a Kind on Studio's GENERIC docs surface.

    Cuts the per-Kind boilerplate to a single call: routes are the universal
    scope-relative docs routes (``docs/<Kind>`` list + ``docs/<Kind>/:name``
    detail) — the SAME shape AuditLog uses, so they resolve for ANY Kind
    without bespoke Studio routing (no 404 risk). Read-only surface (list +
    detail); create/edit routes are intentionally omitted — those need
    Kind-specific forms and can be added per-Kind later.

    i18n labels are built from ``label_en`` + ``label_pt`` (Studio resolves the
    user's locale at boot). ``icon`` should usually pass the Kind's
    ``ascii_icon`` so the manifest matches the tree view.
    """
    label: LabelI18n = {"en": label_en, "pt-BR": label_pt}
    description: LabelI18n | None = None
    if description_en is not None:
        description = {"en": description_en, "pt-BR": description_pt or description_en}
    return StudioUIMetadata(
        mode=mode,
        in_sidebar=in_sidebar,
        display_order=display_order,
        label=label,
        icon=icon,
        description=description,
        breadcrumb=breadcrumb,
        routes={"list": f"docs/{kind}", "detail": f"docs/{kind}/:name"},
        permissions={"list": read, "detail": read},
    )
