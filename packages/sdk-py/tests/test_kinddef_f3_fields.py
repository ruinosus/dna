"""F3: campos novos do KindDefinitionSpec (spec D2)."""
from types import SimpleNamespace

from dna.kernel.kind_base import KindBase
from dna.kernel.meta import DeclarativeKindPort
from dna.kernel.models import TypedKindDefinition
from dna.kernel.protocols import TenantScope

RAW_FULL = {
    "apiVersion": TypedKindDefinition.API_VERSION,
    "kind": TypedKindDefinition.KIND,
    "metadata": {"name": "kz"},
    "spec": {
        "target_api_version": "github.com/ruinosus/dna/sdlc/v1", "target_kind": "KaizenLike",
        "alias": "test-kaizenlike", "origin": "github.com/ruinosus/dna/sdlc",
        "storage": {"type": "yaml", "container": "kaizens"},
        "schema": {"type": "object", "required": ["body"],
                   "properties": {"body": {"type": "string"},
                                  "status": {"type": "string", "enum": ["observed", "routed"]},
                                  "labels": {"type": "array", "items": {"type": "string"}}}},
        # — campos F3 —
        "plane": "record",
        "tenant_scope": "global",
        "summary": {"status": "observed", "work_item": "", "labels": []},
        "embed": ["body", "labels"],
        "is_runtime_artifact": True,
        "prompt_target_priority": 0,
        # is_overlayable=False ≠ default True — pins the wiring (a True here
        # would pass even if from_raw dropped the field; C1 review carry-over)
        "scope_inheritable": False,
        "is_overlayable": False,
        "volatile_spec_fields": ["updated_at", "closed_at"],
    },
}


def test_f3_fields_parsed():
    t = TypedKindDefinition.from_raw(RAW_FULL)
    s = t.spec
    assert s.plane == "record"
    assert s.tenant_scope == "global"
    assert s.summary == {"status": "observed", "work_item": "", "labels": []}
    assert s.embed == ["body", "labels"]
    assert s.is_runtime_artifact is True
    assert s.prompt_target_priority == 0
    assert s.scope_inheritable is False
    assert s.is_overlayable is False
    assert s.volatile_spec_fields == ["updated_at", "closed_at"]


def test_f3_fields_defaults():
    raw = {**RAW_FULL, "spec": {k: v for k, v in RAW_FULL["spec"].items()
                                if k in ("target_api_version", "target_kind", "alias", "origin", "storage", "schema")}}
    s = TypedKindDefinition.from_raw(raw).spec
    assert s.plane == "composition"        # default = comportamento de hoje
    assert s.tenant_scope == "tenanted"
    assert s.summary is None
    assert s.embed is None
    assert s.is_runtime_artifact is False
    assert s.prompt_target_priority == 5   # preserva o hardcode atual como default
    assert s.scope_inheritable is True
    assert s.is_overlayable is True
    assert s.volatile_spec_fields is None


def test_summary_as_list_form():
    raw = {**RAW_FULL}
    raw["spec"] = {**RAW_FULL["spec"], "summary": ["status", "labels"]}
    s = TypedKindDefinition.from_raw(raw).spec
    # forma lista é normalizada pra dict com defaults por tipo do schema
    assert s.summary == {"status": "", "labels": []}


# ---------------------------------------------------------------------------
# Task 2 — DeclarativeKindPort consome os campos F3
# ---------------------------------------------------------------------------


def _minimal_raw():
    return {**RAW_FULL, "spec": {k: v for k, v in RAW_FULL["spec"].items()
                                 if k in ("target_api_version", "target_kind",
                                          "alias", "origin", "storage", "schema")}}


def test_port_consumes_f3_fields():
    port = DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(RAW_FULL))
    assert port.plane == "record"
    # tenant_scope declarado → port espelha o atributo `scope` das classes
    # (e.g. KaizenKind: `scope = TenantScope.GLOBAL`)
    assert port.scope is TenantScope.GLOBAL
    assert port.embed_fields == ["body", "labels"]
    assert port.is_runtime_artifact is True
    assert port.prompt_target_priority == 0
    assert port.scope_inheritable is False
    assert port.is_overlayable is False
    # declarados ∪ defaults da KindBase
    assert port.VOLATILE_SPEC_FIELDS >= {"updated_at", "closed_at",
                                         "version", "created_at"}


def test_port_summary_projects_declared_fields():
    port = DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(RAW_FULL))
    doc = SimpleNamespace(spec={"status": "routed"})
    # presentes vêm do spec, ausentes = default declarado
    assert port.summary(doc) == {"status": "routed", "work_item": "", "labels": []}


def test_port_f3_defaults_preserve_today():
    port = DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(_minimal_raw()))
    assert port.plane == "composition"
    assert port.summary(SimpleNamespace(spec={"status": "x"})) is None
    assert port.embed_fields is None
    assert port.is_runtime_artifact is False
    assert port.prompt_target_priority == 5
    assert port.scope_inheritable is True
    assert port.is_overlayable is True
    # tenant_scope NÃO declarado → permissivo (Phase 1 back-compat:
    # Kernel._kind_scope lê getattr(kp, "scope", None))
    assert getattr(port, "scope", None) is None
    assert port.VOLATILE_SPEC_FIELDS == {"updated_at", "version", "created_at"}


def test_kind_base_declares_embed_fields_default():
    # D4 precisa de embed_fields também nos kinds ainda-classe
    assert KindBase.embed_fields is None


def test_graph_style_accepts_camelcase_textcolor_fallback():
    """C4 review carry-over: canonical key is snake_case `text_color`, but
    camelCase `textColor` stays accepted (mirrors the TS twin meta.ts:
    `text_color ?? textColor ?? "#fff"`). Output key is ALWAYS snake_case."""
    raw = {**RAW_FULL}
    raw["spec"] = {
        **RAW_FULL["spec"],
        "graph_style": {"fill": "#111111", "stroke": "#222222", "textColor": "#000"},
    }
    from dna.kernel.meta import DeclarativeKindPort

    port = DeclarativeKindPort(TypedKindDefinition.from_raw(raw))
    assert port.graph_style == {
        "fill": "#111111", "stroke": "#222222", "text_color": "#000",
    }
    # snake_case wins when both are present
    raw["spec"]["graph_style"] = {
        "fill": "#111111", "stroke": "#222222",
        "text_color": "#abc", "textColor": "#000",
    }
    port2 = DeclarativeKindPort(TypedKindDefinition.from_raw(raw))
    assert port2.graph_style["text_color"] == "#abc"
