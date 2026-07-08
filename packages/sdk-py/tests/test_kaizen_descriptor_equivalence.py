"""F3 P2: porta sintetizada do kaizen.kind.yaml ≡ KaizenKind (classe extinta).

Phase A deste teste rodou com a CLASSE viva como golden — toda asserção
deep-equal passou (schema, summary ×3 docs, dep_filters, storage, flags,
identity). Phase B (este arquivo): a classe Py/TS foi DELETADA; o golden
está congelado abaixo como literais inline e este arquivo é o teste de
regressão do descriptor (absorve também o extinto test_kaizen_kind.py).

Semântica CANÔNICA é a do PORT (NOTA do plano, carry-over review C1) —
deltas intencionais vs a classe extinta, pinados nos testes:
  - summary projeta ``spec.get(campo, default)`` — só campo AUSENTE cai no
    default; presente-mas-falsy (labels: null) volta as-is. A classe
    coalescia falsy (``or []``) só em labels.
  - summary exige doc objeto (``.spec``); bare-dict NÃO é Document e
    projeta os defaults. A classe aceitava bare-dict defensivamente (todos
    os call-sites reais — viz/health, viz/ascii, list endpoints — passam
    Document).
  - parse VALIDA contra o schema (a classe era pass-through,
    validate_on_parse=False) — upgrade de validação; no kernel um doc
    inválido vira typed=None + evento parse_error, nunca crash de load.
  - embed_fields=["body", "labels"] declarado (a classe nunca declarou —
    Kaizen vivia no frozenset legado EMBEDDABLE_KINDS + branch hardcoded
    de source_text_for; a declaração alimenta a derivação D4).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from dna.extensions.sdlc import SdlcExtension
from dna.kernel import Kernel
from dna.kernel.descriptor_loader import load_descriptors
from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import StoragePattern, TenantScope

# ---------------------------------------------------------------------------
# GOLDEN — frozen from the deleted KaizenKind class (sdlc/__init__.py@0d252df1
# :5116-5217), byte-equal to what KaizenKind().schema() / .docs returned.
# ---------------------------------------------------------------------------

GOLDEN_SCHEMA = {
    "type": "object",
    "required": ["body", "status"],
    "properties": {
        "body": {
            "type": "string",
            "description": "The kaizen observation (what could be better).",
        },
        "work_item": {
            "type": "string",
            "description": "Kind/slug of the work item where this was observed (polymorphic — Story/Spike/Issue).",
        },
        "issue": {
            "type": "string",
            "description": "Issue/Story slug tracking the fix.",
        },
        "status": {
            "type": "string",
            "enum": ["observed", "routed", "resolved"],
            "default": "observed",
            "description": "Observation arc: observed (flagged) → routed (fix tracked in `issue`) → resolved (fix shipped).",
        },
        "actor": {
            "type": "string",
            "description": "Who flagged it.",
        },
        "labels": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Free-form theme tags (weighted into semantic-search source text).",
        },
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
    },
    "additionalProperties": False,
}

GOLDEN_DOCS = (
    "A Kaizen is a continuous-improvement observation noticed while "
    "working on something else — a smell, friction, a manual step, a "
    "missing test — captured as a first-class doc WITHOUT derailing "
    "the task at hand. Arc: observed → routed (an Issue/Story tracks "
    "the fix) → resolved (fix shipped). Twin of the `kaizen` timeline "
    "event on the originating work item (which carries a ref back to "
    "this doc)."
)

GOLDEN_SUMMARY_DEFAULTS = {
    "status": "observed",
    "work_item": "",
    "issue": "",
    "actor": "",
    "labels": [],
}


def _descriptor_raw() -> dict:
    raws = [
        r for r in load_descriptors("dna.extensions.sdlc")
        if r.get("spec", {}).get("target_kind") == "Kaizen"
    ]
    assert len(raws) == 1, f"expected exactly one kaizen descriptor, got {len(raws)}"
    return raws[0]


@pytest.fixture(scope="module")
def port():
    """The port as the EXTENSION registers it (the real funnel — absorbed
    from test_kaizen_kind.py::test_kaizen_registered_via_extension)."""
    k = Kernel()
    k.load(SdlcExtension())
    return k._kinds[("github.com/ruinosus/dna/sdlc/v1", "Kaizen")]


def _doc(spec: dict) -> SimpleNamespace:
    return SimpleNamespace(spec=spec)


_FULL_SPEC = {
    "body": "step is manual",
    "work_item": "Story/s-x",
    "issue": "i-042",
    "status": "routed",
    "actor": "claude-code",
    "labels": ["dx"],
}


# --- identity ---------------------------------------------------------------

def test_identity_matches_golden(port):
    assert port.api_version == "github.com/ruinosus/dna/sdlc/v1"
    assert port.kind == "Kaizen"
    assert port.alias == "sdlc-kaizen"
    assert port.origin == "github.com/ruinosus/dna/sdlc"
    assert port.display_label == "Kaizens"
    assert port.ascii_icon == "♻️"
    assert port.graph_style == {
        "fill": "#10B981", "stroke": "#047857", "text_color": "#fff",
    }
    assert port.docs == GOLDEN_DOCS


# --- flags ------------------------------------------------------------------

def test_flags_match_golden(port):
    assert port.plane == "record"  # F1 two-planes: SDLC kinds are records
    assert port.scope == TenantScope.GLOBAL  # project-level, not per-tenant
    assert port.is_prompt_target is False
    assert port.flatten_in_context is False
    assert port.prompt_target_priority == 0
    assert port.scope_inheritable is True
    assert port.is_overlayable is True
    assert port.is_runtime_artifact is False
    assert port.is_root is False
    assert getattr(port, "is_schema_affecting", False) is False
    assert port.VOLATILE_SPEC_FIELDS == KindBase.VOLATILE_SPEC_FIELDS


def test_embed_fields_declared(port):
    # Intentional F3 D4 declaration — same fields as the legacy
    # source_text_for branch (body + labels).
    assert port.embed_fields == ["body", "labels"]


def test_descriptor_port_is_builtin_marked(port):
    assert getattr(port, "__builtin_descriptor__", False) is True
    assert isinstance(getattr(port, "__descriptor_digest__", None), str)


# --- storage ----------------------------------------------------------------

def test_storage_yaml_kaizens(port):
    assert port.storage.pattern == StoragePattern.YAML
    assert port.storage.container == "kaizens"
    assert port.storage.marker is None


# --- schema -----------------------------------------------------------------

def test_schema_deep_equals_golden(port):
    assert port.schema() == GOLDEN_SCHEMA


def test_schema_required_and_enum(port):
    # absorbed from test_kaizen_kind.py — the enum lives ONLY in the
    # descriptor YAML now (KAIZEN_STATUSES removed).
    schema = port.schema()
    assert set(schema["required"]) == {"body", "status"}
    assert schema["properties"]["status"]["enum"] == ["observed", "routed", "resolved"]
    assert schema["properties"]["status"]["default"] == "observed"
    # strict per s-strict-schema-lint ratchet (new Kinds ship strict)
    assert schema["additionalProperties"] is False
    for field in ("body", "work_item", "issue", "actor", "labels", "created_at"):
        assert field in schema["properties"], field


# --- dep_filters --------------------------------------------------------------

def test_dep_filters_issue_only(port):
    """`work_item` is polymorphic (Kind/slug) — no dep_filter for it."""
    assert port.dep_filters() == {"issue": "sdlc-issue"}


# --- summary ------------------------------------------------------------------

def test_summary_full_doc(port):
    assert port.summary(_doc(dict(_FULL_SPEC))) == {
        "status": "routed",
        "work_item": "Story/s-x",
        "issue": "i-042",
        "actor": "claude-code",
        "labels": ["dx"],
    }


def test_summary_partial_doc(port):
    assert port.summary(_doc({"body": "x", "status": "observed"})) == (
        GOLDEN_SUMMARY_DEFAULTS
    )


def test_summary_empty_doc(port):
    assert port.summary(_doc({})) == GOLDEN_SUMMARY_DEFAULTS


def test_summary_falsy_present_port_semantics_canonical(port):
    """NOTA do plano: presente-mas-falsy volta as-is (só AUSENTE cai no
    default). A classe extinta coalescia falsy em labels (`or []`) — a
    semântica canônica é a do port."""
    spec = {"body": "x", "status": "observed", "labels": None, "work_item": ""}
    s = port.summary(_doc(spec))
    assert s["labels"] is None      # stored as-is — canonical (class gave [])
    assert s["work_item"] == ""     # stored as-is (equals default anyway)
    assert s["status"] == "observed"


def test_summary_bare_dict_port_semantics_canonical(port):
    """NOTA do plano: bare-dict não é Document — sem `.spec`, projeta os
    defaults declarados. A classe extinta lia o dict direto; canônico é o
    port (call-sites reais passam Document)."""
    assert port.summary(dict(_FULL_SPEC)) == GOLDEN_SUMMARY_DEFAULTS


# --- parse --------------------------------------------------------------------

def _envelope(spec: dict) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "Kaizen",
        "metadata": {"name": "kz-001"},
        "spec": spec,
    }


def test_parse_valid_accepted(port):
    raw = _envelope({"body": "step is manual", "status": "observed"})
    assert port.parse(dict(raw)) == raw


def test_parse_invalid_rejected(port):
    """O PORT valida contra o schema (a classe extinta era pass-through —
    upgrade intencional): sem `body` → ValueError; no kernel isso vira
    typed=None + evento parse_error, nunca crash de load."""
    with pytest.raises(ValueError, match="body"):
        port.parse(_envelope({"status": "observed"}))


def test_parse_rejects_unknown_property(port):
    # additionalProperties: false — strict-schema ratchet preserved.
    with pytest.raises(ValueError, match="nope"):
        port.parse(_envelope({"body": "x", "status": "observed", "nope": 1}))
