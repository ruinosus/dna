"""Descriptor expressiveness — the 6 new KindDefinitionSpec fields (D1/D3-D7).

ui, describe, ui_schema, spec_defaults, default_agent_field,
description_fallback_field. All optional with back-compat defaults (None).

Port-level behavior (DeclarativeKindPort consuming these) lives in the same
file once Task 3 lands — see the ``# --- Task 3 (port) ---`` section.
"""
from __future__ import annotations

import pytest

from dna.kernel.models import KindDefinitionSpec
from dna.kernel.studio_ui import StudioUIMetadata


def _base_raw(**extra):
    raw = {
        "target_api_version": "github.com/ruinosus/dna/expr/v1",
        "target_kind": "ExprThing",
        "alias": "expr-thing",
        "origin": "github.com/ruinosus/dna/expr",
        "storage": {"type": "yaml", "container": "expr-things"},
        "schema": {
            "type": "object",
            "properties": {
                "agent_ref": {"type": "string"},
                "description": {"type": "string"},
                "name": {"type": "string"},
                "status": {"type": "string"},
            },
        },
    }
    raw.update(extra)
    return raw


# ── all-6 parse with correct types ──────────────────────────────────────────

def test_all_six_fields_parse():
    spec = KindDefinitionSpec.from_raw(
        _base_raw(
            ui={
                "mode": "quality",
                "in_sidebar": True,
                "display_order": 20,
                "label": {"en": "Things", "pt-BR": "Coisas"},
                "icon": "🔬",
                "routes": {"list": "expr/things", "detail": "expr/things/:id"},
                "permissions": {"list": "any"},
            },
            describe="{name} ({status})",
            ui_schema={"name": {"widget": "input", "anything": "goes"}},
            spec_defaults={"status": "pending"},
            default_agent_field="agent_ref",
            description_fallback_field="description",
        )
    )
    assert isinstance(spec.ui, dict)
    assert spec.ui["mode"] == "quality"
    assert spec.describe == "{name} ({status})"
    assert spec.ui_schema == {"name": {"widget": "input", "anything": "goes"}}
    assert spec.spec_defaults == {"status": "pending"}
    assert spec.default_agent_field == "agent_ref"
    assert spec.description_fallback_field == "description"


def test_absent_fields_default_to_none():
    spec = KindDefinitionSpec.from_raw(_base_raw())
    assert spec.ui is None
    assert spec.describe is None
    assert spec.ui_schema is None
    assert spec.spec_defaults is None
    assert spec.default_agent_field is None
    assert spec.description_fallback_field is None


# ── ui validation: keys ⊆ StudioUIMetadata fields ───────────────────────────

def test_ui_unknown_key_raises():
    with pytest.raises(ValueError, match="ui"):
        KindDefinitionSpec.from_raw(_base_raw(ui={"mode": "quality", "bogus": 1}))


def test_ui_all_known_keys_accepted():
    # Every StudioUIMetadata field must be an accepted ui: key.
    ui = {f: None for f in StudioUIMetadata.__dataclass_fields__}
    ui["mode"] = "build"
    spec = KindDefinitionSpec.from_raw(_base_raw(ui=ui))
    assert set(spec.ui.keys()) <= set(StudioUIMetadata.__dataclass_fields__)


def test_ui_must_be_a_mapping():
    with pytest.raises(ValueError, match="ui"):
        KindDefinitionSpec.from_raw(_base_raw(ui=["mode"]))


# ── ui_schema is permissive ─────────────────────────────────────────────────

def test_ui_schema_unknown_keys_ok():
    spec = KindDefinitionSpec.from_raw(
        _base_raw(ui_schema={"any_field": {"widget": "made-up", "order": 9}})
    )
    assert spec.ui_schema == {"any_field": {"widget": "made-up", "order": 9}}


# ── describe accepts string OR {path} ───────────────────────────────────────

def test_describe_string_form():
    spec = KindDefinitionSpec.from_raw(_base_raw(describe="{name}"))
    assert spec.describe == "{name}"


def test_describe_path_form():
    spec = KindDefinitionSpec.from_raw(_base_raw(describe={"path": "description"}))
    assert spec.describe == {"path": "description"}


def test_describe_bad_type_raises():
    with pytest.raises(ValueError, match="describe"):
        KindDefinitionSpec.from_raw(_base_raw(describe=123))


# ─────────────────────────────────────────────────────────────────────────
# --- Task 3 (port): DeclarativeKindPort consumes the fields ---
# ─────────────────────────────────────────────────────────────────────────

from types import SimpleNamespace  # noqa: E402

from dna.kernel.meta import DeclarativeKindPort  # noqa: E402
from dna.kernel.models import TypedKindDefinition  # noqa: E402


def _port(**spec_extra) -> DeclarativeKindPort:
    raw = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "expr-thing"},
        "spec": _base_raw(**spec_extra),
    }
    typed = TypedKindDefinition.from_raw(raw)
    return DeclarativeKindPort.from_typed(typed)


def _doc(**spec):
    return SimpleNamespace(spec=spec)


# ── port.ui = reconstructed StudioUIMetadata ────────────────────────────────

def test_port_ui_reconstructed():
    port = _port(
        ui={
            "mode": "quality",
            "in_sidebar": True,
            "display_order": 20,
            "label": {"en": "Things", "pt-BR": "Coisas"},
            "icon": "🔬",
        }
    )
    assert isinstance(port.ui, StudioUIMetadata)
    assert port.ui.mode == "quality"
    assert port.ui.to_dict() == {
        "mode": "quality",
        "in_sidebar": True,
        "display_order": 20,
        "label": {"en": "Things", "pt-BR": "Coisas"},
        "icon": "🔬",
    }
    assert port.ui.resolve_label("pt-BR") == "Coisas"


def test_port_ui_none_when_absent():
    port = _port()
    assert port.ui is None


# ── pass-through attrs ──────────────────────────────────────────────────────

def test_port_ui_schema_passthrough():
    port = _port(ui_schema={"name": {"widget": "input", "order": 0}})
    assert port.ui_schema == {"name": {"widget": "input", "order": 0}}


def test_port_ui_schema_none_when_absent():
    port = _port()
    assert port.ui_schema is None


def test_port_description_fallback_field_passthrough():
    port = _port(description_fallback_field="description")
    assert port.description_fallback_field == "description"
    assert _port().description_fallback_field is None


# ── describe(doc) ───────────────────────────────────────────────────────────

def test_describe_template_substitutes_fields():
    port = _port(describe="{name} ({status})")
    assert port.describe(_doc(name="Foo", status="open")) == "Foo (open)"


def test_describe_template_missing_field_empty():
    port = _port(describe="{name} ({status})")
    # status missing → "" (not KeyError)
    assert port.describe(_doc(name="Foo")) == "Foo ()"


def test_describe_path_form_verbatim():
    port = _port(describe={"path": "description"})
    assert port.describe(_doc(description="hello world")) == "hello world"


def test_describe_path_form_missing_returns_none():
    port = _port(describe={"path": "description"})
    assert port.describe(_doc(name="Foo")) is None


def test_describe_none_when_absent():
    port = _port()
    assert port.describe(_doc(name="Foo")) is None


# ── parse(raw): spec_defaults shallow-merge + load-time lint ─────────────────

def _autolab_like_raw(**spec_extra):
    """Mirror autolab's real shape: schema with required:[program,
    max_iterations] + a partial _DEFAULTS that does NOT satisfy required."""
    raw = {
        "target_api_version": "github.com/ruinosus/dna/autolab/v1",
        "target_kind": "AutolabRunLike",
        "alias": "autolab-run-like",
        "origin": "local",
        "storage": {"type": "yaml", "container": "autolab-runs"},
        "schema": {
            "type": "object",
            "required": ["program", "max_iterations"],
            "additionalProperties": True,
            "properties": {
                "program": {"type": "string"},
                "max_iterations": {"type": "integer", "minimum": 1},
                "max_wall_clock_sec": {"type": "integer", "minimum": 60},
                "plateau_patience": {"type": "integer", "minimum": 1},
                "mode": {"type": "string", "enum": ["autonomous", "preview"]},
                "tasks_dir": {"type": "string"},
                "meta_agent": {"type": "string"},
            },
        },
    }
    raw.update(spec_extra)
    return raw


_AUTOLAB_DEFAULTS = {
    "max_wall_clock_sec": 3600,
    "plateau_patience": 3,
    "mode": "autonomous",
    "tasks_dir": "tasks/",
    "meta_agent": "meta-harness-engineer",
}


def test_parse_merges_spec_defaults_before_validation():
    raw_def = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "autolab-run-like"},
        "spec": _autolab_like_raw(spec_defaults=_AUTOLAB_DEFAULTS),
    }
    port = DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(raw_def))
    # A spec missing defaulted keys must validate AFTER merge (defaults fill in)
    out = port.parse({"spec": {"program": "p", "max_iterations": 3}})
    merged = out["spec"]
    assert merged["mode"] == "autonomous"  # from defaults
    assert merged["max_wall_clock_sec"] == 3600
    assert merged["program"] == "p"  # spec wins / present
    assert merged["max_iterations"] == 3


def test_parse_spec_overrides_defaults():
    raw_def = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "autolab-run-like"},
        "spec": _autolab_like_raw(spec_defaults=_AUTOLAB_DEFAULTS),
    }
    port = DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(raw_def))
    out = port.parse(
        {"spec": {"program": "p", "max_iterations": 3, "mode": "preview"}}
    )
    assert out["spec"]["mode"] == "preview"  # spec overrides default


def test_load_time_lint_accepts_autolab_partial_defaults():
    """autolab's real _DEFAULTS is a PARTIAL spec — it does NOT satisfy
    required:[program, max_iterations]. The lint must IGNORE required and
    only validate each default key against its property subschema → accepts."""
    raw_def = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "autolab-run-like"},
        "spec": _autolab_like_raw(spec_defaults=_AUTOLAB_DEFAULTS),
    }
    # Must NOT raise at construction.
    port = DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(raw_def))
    assert port.kind == "AutolabRunLike"


def test_load_time_lint_rejects_default_key_absent_from_schema():
    raw_def = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "autolab-run-like"},
        "spec": _autolab_like_raw(spec_defaults={"not_a_field": 1}),
    }
    with pytest.raises(ValueError, match="spec_defaults"):
        DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(raw_def))


def test_load_time_lint_rejects_default_value_violating_subschema():
    raw_def = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "autolab-run-like"},
        # mode must be enum autonomous|preview; "bogus" violates its subschema
        "spec": _autolab_like_raw(spec_defaults={"mode": "bogus"}),
    }
    with pytest.raises(ValueError, match="spec_defaults"):
        DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(raw_def))


def test_parse_no_spec_defaults_is_passthrough():
    port = _port()
    out = port.parse({"spec": {"name": "x"}})
    assert out["spec"] == {"name": "x"}


# ── get_default_agent_name VERBATIM ─────────────────────────────────────────

def test_get_default_agent_name_verbatim():
    port = _port(default_agent_field="agent_ref")
    assert port.get_default_agent_name(_doc(agent_ref="my-agent")) == "my-agent"


def test_get_default_agent_name_empty_string_verbatim_not_none():
    """Pin: returns "" (not None) when the field is "" — no `or None`."""
    port = _port(default_agent_field="agent_ref")
    assert port.get_default_agent_name(_doc(agent_ref="")) == ""


def test_get_default_agent_name_missing_field_none():
    port = _port(default_agent_field="agent_ref")
    assert port.get_default_agent_name(_doc(name="x")) is None


def test_get_default_agent_name_falls_back_to_default_agent_when_field_absent():
    # No default_agent_field declared → legacy static default_agent path.
    port = _port(default_agent="static-agent")
    assert port.get_default_agent_name(_doc()) == "static-agent"
