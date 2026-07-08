"""StudioUIMetadata dataclass + KindBase.ui field.

P2L1 of f-kind-driven-routing (s-studio-ui-metadata, 2026-05-16).
"""
from __future__ import annotations

import pytest

from dna.kernel.studio_ui import StudioUIMetadata
from dna.kernel.kind_base import KindBase


def test_kind_base_ui_defaults_to_none():
    """Existing 30+ Kinds without `ui` populated stay invisible in
    Studio — strict back-compat."""
    class MyKind(KindBase):
        pass
    assert MyKind().ui is None


def test_studio_ui_metadata_minimal():
    """Empty dataclass round-trips through to_dict cleanly."""
    ui = StudioUIMetadata()
    assert ui.to_dict() == {}


def test_studio_ui_metadata_full_serialization():
    """All fields populated → JSON includes everything."""
    ui = StudioUIMetadata(
        mode="quality",
        in_sidebar=True,
        display_order=10,
        label={"en": "Eval Cases", "pt-BR": "Casos de Eval"},
        icon="🧪",
        description="Test scenarios for agents.",
        breadcrumb=["Quality", "Lab", "Cases"],
        routes={
            "list": "eval/lab",
            "detail": "eval/lab/cases/:caseName",
        },
        permissions={
            "list": "any",
            "create": ["maker", "qa"],
        },
        note="primary editing surface",
    )
    d = ui.to_dict()
    assert d["mode"] == "quality"
    assert d["in_sidebar"] is True
    assert d["display_order"] == 10
    assert d["label"] == {"en": "Eval Cases", "pt-BR": "Casos de Eval"}
    assert d["icon"] == "🧪"
    assert d["breadcrumb"] == ["Quality", "Lab", "Cases"]
    assert d["routes"]["list"] == "eval/lab"
    assert d["permissions"]["create"] == ["maker", "qa"]


def test_studio_ui_metadata_omits_defaults():
    """Default values are dropped from serialization to keep wire
    payload small. display_order=100 (default) → omitted."""
    ui = StudioUIMetadata(mode="build", label="Skills")
    d = ui.to_dict()
    assert "mode" in d
    assert "label" in d
    # Defaults stripped:
    assert "in_sidebar" not in d
    assert "display_order" not in d
    assert "routes" not in d
    assert "permissions" not in d
    assert "icon" not in d


def test_studio_ui_metadata_plain_string_label():
    """Non-i18n use case: label is just a string."""
    ui = StudioUIMetadata(label="Eval Cases")
    d = ui.to_dict()
    assert d["label"] == "Eval Cases"


def test_resolve_label_exact_locale():
    ui = StudioUIMetadata(label={"en": "Cases", "pt-BR": "Casos"})
    assert ui.resolve_label("en") == "Cases"
    assert ui.resolve_label("pt-BR") == "Casos"


def test_resolve_label_language_fallback():
    """'pt-BR' requested but only 'pt' available → fallback to 'pt'."""
    ui = StudioUIMetadata(label={"en": "Cases", "pt": "Casos"})
    assert ui.resolve_label("pt-BR") == "Casos"


def test_resolve_label_en_fallback():
    """Unknown locale → fallback to 'en'."""
    ui = StudioUIMetadata(label={"en": "Cases", "pt-BR": "Casos"})
    assert ui.resolve_label("es") == "Cases"


def test_resolve_label_string_ignores_locale():
    """Plain string label is locale-agnostic."""
    ui = StudioUIMetadata(label="Cases")
    assert ui.resolve_label("pt-BR") == "Cases"
    assert ui.resolve_label("en") == "Cases"
    assert ui.resolve_label("zh-CN") == "Cases"


def test_resolve_label_none_when_unset():
    ui = StudioUIMetadata()
    assert ui.resolve_label("en") is None


def test_kind_base_subclass_with_ui_populated():
    """Subclasses can declare ui as a class attribute (the canonical
    pattern shown in the dataclass docstring)."""
    class StoryKind(KindBase):
        api_version = "github.com/ruinosus/dna/sdlc/v1"
        kind = "Story"
        alias = "sdlc-story"
        ui = StudioUIMetadata(
            mode="plan",
            in_sidebar=True,
            label="Stories",
            icon="📋",
            routes={"list": "docs/Story", "detail": "docs/Story/:name"},
        )
    k = StoryKind()
    assert k.ui is not None
    assert k.ui.mode == "plan"
    assert k.ui.in_sidebar is True


def test_permissions_with_anonymous():
    """Public Kinds: permission can be 'anonymous'."""
    ui = StudioUIMetadata(
        permissions={"list": "anonymous", "detail": "anonymous"},
    )
    d = ui.to_dict()
    assert d["permissions"]["list"] == "anonymous"
    assert d["permissions"]["detail"] == "anonymous"


def test_routes_absolute_vs_scope_relative():
    """Convention: leading '/' = absolute; else scope-relative."""
    ui = StudioUIMetadata(
        routes={
            "list": "docs/Story",        # scope-relative
            "detail": "/admin/users",    # absolute (artificial example)
        },
    )
    d = ui.to_dict()
    assert d["routes"]["list"] == "docs/Story"
    assert d["routes"]["detail"] == "/admin/users"
