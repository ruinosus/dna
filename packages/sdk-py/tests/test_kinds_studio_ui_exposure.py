"""s-kinds-studio-ui-exposure — `ui=` exposure batch + the docs_ui() helper.

Slice 1: a prioritized batch of high-use, genuinely-invisible Build/Govern
Kinds gains Studio `ui` metadata via the new `docs_ui()` convention helper.
100% additive — `ui` is optional; a Kind without it stays invisible. The
Studio merge dedupes by route ID (use-merged-manifest), so adding `ui` never
collides with the static TS manifest.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.studio_ui import StudioUIMetadata, docs_ui


# The batch this slice exposes (Kind name → expected mode).
EXPOSED = {
    "Soul": "build", "Guardrail": "build", "Hook": "build", "Tool": "build",
    
    
    
    
    "SafetyPolicy": "govern", "Recognizer": "govern", 
}


# ──────────────────────────────────────────────────────────────────────
# docs_ui() convention helper
# ──────────────────────────────────────────────────────────────────────


def test_docs_ui_builds_generic_docs_routes():
    ui = docs_ui(
        "Soul", mode="build", label_en="Souls", label_pt="Almas",
        display_order=50, description_en="An agent soul.", description_pt="A alma.",
    )
    assert isinstance(ui, StudioUIMetadata)
    assert ui.mode == "build"
    assert ui.in_sidebar is True
    assert ui.display_order == 50
    # Universal docs surface — resolves for any Kind, no bespoke routing.
    assert ui.routes == {"list": "docs/Soul", "detail": "docs/Soul/:name"}
    # Read-only by default (no create/edit routes invented).
    assert "create" not in ui.routes and "edit" not in ui.routes
    assert ui.permissions == {"list": "any", "detail": "any"}


def test_docs_ui_i18n_label_resolves():
    ui = docs_ui("Tool", mode="build", label_en="Tools", label_pt="Ferramentas")
    assert ui.resolve_label("en") == "Tools"
    assert ui.resolve_label("pt-BR") == "Ferramentas"  # exact locale match
    assert ui.resolve_label("de") == "Tools"  # default-en fallback
    # Language-only fallback: locale "pt-BR" → base "pt" when only "pt" exists.
    ui_pt = StudioUIMetadata(label={"en": "Tools", "pt": "Ferramentas"})
    assert ui_pt.resolve_label("pt-BR") == "Ferramentas"


def test_docs_ui_icon_omitted_falls_back_to_ascii_icon():
    # icon defaults to None so Studio inherits the Kind's ascii_icon.
    ui = docs_ui("Hook", mode="build", label_en="Hooks", label_pt="Hooks")
    assert "icon" not in ui.to_dict()


def test_docs_ui_description_i18n_and_omitted():
    bare = docs_ui("X", mode="build", label_en="X", label_pt="X")
    assert "description" not in bare.to_dict()
    rich = docs_ui("X", mode="build", label_en="X", label_pt="X",
                   description_en="hi", description_pt="oi")
    assert rich.to_dict()["description"] == {"en": "hi", "pt-BR": "oi"}


# ──────────────────────────────────────────────────────────────────────
# The exposed batch (against the real registry)
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def kinds_by_name():
    k = Kernel.auto()
    return {getattr(kp, "kind", None): kp for kp in k._kinds.values()}


@pytest.mark.parametrize("kind_name,expected_mode", sorted(EXPOSED.items()))
def test_exposed_kind_has_wellformed_ui(kinds_by_name, kind_name, expected_mode):
    kp = kinds_by_name.get(kind_name)
    assert kp is not None, f"{kind_name} not registered"
    ui = getattr(kp, "ui", None)
    assert isinstance(ui, StudioUIMetadata), f"{kind_name} missing ui"
    assert ui.mode == expected_mode
    assert ui.in_sidebar is True
    # Generic docs routes resolve for any Kind (no 404 risk).
    assert ui.routes["list"] == f"docs/{kind_name}"
    assert ui.routes["detail"] == f"docs/{kind_name}/:name"
    # i18n labels resolve in both project locales.
    assert ui.resolve_label("en")
    assert ui.resolve_label("pt-BR")
    # to_dict is JSON-clean (what /kinds/manifest serializes).
    d = ui.to_dict()
    assert d["mode"] == expected_mode
    assert d["routes"]["list"] == f"docs/{kind_name}"
    assert d["label"]["pt-BR"]


def test_exposure_raised_the_visible_count(kinds_by_name):
    """The batch meaningfully increases Studio-visible Kinds (was 6)."""
    with_ui = {n for n, kp in kinds_by_name.items() if getattr(kp, "ui", None) is not None}
    # All batch members are now visible…
    assert EXPOSED.keys() <= with_ui
    # …and the total is at least the pre-existing 6 + the 16 remaining
    # (MediaItem + PageIndexDocument archived — s-prune fase C).
    assert len(with_ui) >= 7


def test_additive_no_route_collision_with_static_manifest(kinds_by_name):
    """The static TS manifest owns these Kind routes already; the SDK merge
    dedupes by ID, so the batch must NOT include any of them (avoids dup)."""
    static_owned = {
        "AuditLog", "Evidence", "HtmlTemplate", "LayerPolicy", "Engram",
        "Narrative", "PromptTemplate", "Reference", "Skill", "SynthesisRun",
        "Theme", "Agent", "WorkflowEvent",
    }
    assert EXPOSED.keys().isdisjoint(static_owned)
