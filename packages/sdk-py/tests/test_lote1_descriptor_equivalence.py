"""F3 lote-1: ports sintetizados dos descriptors ≡ classes extintas.

Kinds: WorkflowEvent · LessonLearned · Retrospective · PatternInsight ·
PreMortem (spec 2026-06-10-kinds-descriptor-f3 D5; receita do piloto
Kaizen — test_kaizen_descriptor_equivalence.py).

GOLDENS congelados em tests/goldens/lote1/<Kind>.golden.json — capturados
2026-06-10 das classes VIVAS (pré-deleção): identity, flags, storage,
dep_filters, schema (deep) e summary_cases. Phase A rodou com as classes
vivas (descriptor gerado programaticamente DELAS); Phase B (este arquivo) é
o teste de regressão pós-deleção.

Semântica CANÔNICA é a do PORT — deltas intencionais vs as classes,
pinados nos testes:
  - **summary**: as classes (exceto WorkflowEvent) herdavam o default do
    KindBase que ecoa o spec INTEIRO no navigator/viz — substituído por
    projeção curada declarada no descriptor (campos que a classe TS/
    to_card morto já elegiam). List endpoints (/docs/{kind},
    docs_service.list_docs) NÃO usam kp.summary() → payloads de produção
    inalterados. WorkflowEvent tinha summary explícito → reproduzido
    exatamente (defaults null).
  - **dep_filters**: LessonLearnedKind retornava {} — port retorna None
    (sem declaração). Ambos falsy; todos os call-sites fazem `or {}`.
  - **parse**: o port VALIDA contra o schema (classes eram pass-through,
    validate_on_parse=False) — upgrade intencional; no kernel um doc
    inválido vira typed=None + evento parse_error, nunca crash de load.
  - **to_card** (LessonLearned/PatternInsight): dead code, zero
    consumidores em produção — não migrado.
  - **drift Py↔TS curado**: as classes TS de LessonLearned (strict + sem
    affect_reason) / Retrospective (summary próprio, schema magro) /
    WorkflowEvent (summary com defaults "") divergiam do Py; o descriptor
    byte-idêntico unifica no canônico = superfície Py (produção).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dna.extensions.sdlc import SdlcExtension
from dna.kernel import Kernel
from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import TenantScope

GOLDEN_DIR = Path(__file__).parent / "goldens" / "lote1"

KINDS = ["WorkflowEvent", "LessonLearned", "Retrospective", "PatternInsight", "PreMortem"]

# Projeção curada declarada no descriptor (delta intencional — ver
# docstring). WorkflowEvent não está aqui: seu summary reproduz a classe.
CURATED_SUMMARY_DEFAULTS = {
    "LessonLearned": {
        "area": "", "affect": "", "summary": "", "surface_count": 0, "owner": None,
    },
    "Retrospective": {"title": "", "intent": "", "period_end": ""},
    "PatternInsight": {
        "dream_ref": "", "framework": "", "engine": "", "summary": "",
        "owner": None, "lens": None, "synthesizes": [],
    },
    "PreMortem": {
        "source_story": "", "source_outcome": "",
        "status": "drafted", "strength": "medium",
    },
}


def _golden(kind: str) -> dict:
    return json.loads((GOLDEN_DIR / f"{kind}.golden.json").read_text())


@pytest.fixture(scope="module")
def kernel():
    """Ports como a EXTENSÃO os registra (o funil real)."""
    k = Kernel()
    k.load(SdlcExtension())
    return k


def _port(kernel, kind: str):
    kp = kernel.kind_port_for(kind)
    assert kp is not None, f"{kind} not registered"
    return kp


def _doc(spec: dict) -> SimpleNamespace:
    return SimpleNamespace(spec=spec)


# --- identity ---------------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_identity_matches_golden(kernel, kind):
    g = _golden(kind)["identity"]
    port = _port(kernel, kind)
    assert port.api_version == g["api_version"]
    assert port.kind == g["kind"]
    assert port.alias == g["alias"]
    assert port.origin == g["origin"]
    assert port.display_label == g["display_label"]
    assert port.ascii_icon == g["ascii_icon"]
    assert port.graph_style == g["graph_style"]
    assert port.docs == g["docs"]


# --- flags ------------------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_flags_match_golden(kernel, kind):
    g = _golden(kind)["flags"]
    port = _port(kernel, kind)
    assert port.plane == g["plane"] == "record"
    assert port.scope == TenantScope(g["scope"])
    assert port.is_prompt_target is g["is_prompt_target"]
    assert port.flatten_in_context is g["flatten_in_context"]
    assert port.prompt_target_priority == g["prompt_target_priority"]
    assert port.scope_inheritable is g["scope_inheritable"]
    assert port.is_overlayable is g["is_overlayable"]
    assert port.is_runtime_artifact is g["is_runtime_artifact"]
    assert port.is_root is g["is_root"]
    assert getattr(port, "is_schema_affecting", False) is False
    assert sorted(port.VOLATILE_SPEC_FIELDS) == g["volatile_spec_fields"]
    assert port.VOLATILE_SPEC_FIELDS == KindBase.VOLATILE_SPEC_FIELDS


def test_lessonlearned_not_scope_inheritable(kernel):
    """A classe declarava scope_inheritable=False — alimenta o set derivado
    _NON_INHERITABLE_KINDS (test_kind_classification_attrs pina o oracle)."""
    assert _port(kernel, "LessonLearned").scope_inheritable is False


def test_builtin_descriptor_markers(kernel):
    for kind in KINDS:
        port = _port(kernel, kind)
        assert getattr(port, "__builtin_descriptor__", False) is True, kind
        assert isinstance(getattr(port, "__descriptor_digest__", None), str), kind


# --- storage ----------------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_storage_matches_golden(kernel, kind):
    g = _golden(kind)["storage"]
    sd = _port(kernel, kind).storage
    assert sd.pattern.value == g["pattern"]
    assert sd.container == g["container"]
    assert sd.marker == g["marker"]
    if g["pattern"] == "bundle":
        assert sd.body_field == g["body_field"]
        assert sd.body_as.value == g["body_as"]


# --- schema (deep) ----------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_schema_deep_equals_golden(kernel, kind):
    assert _port(kernel, kind).schema() == _golden(kind)["schema"]


def test_workflow_event_stays_strict(kernel):
    """sdlc-workflow-event é o kind-âncora strict do ratchet
    test_strict_schema_lint — o descriptor preserva."""
    assert _port(kernel, "WorkflowEvent").schema()["additionalProperties"] is False


# --- dep_filters ------------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_dep_filters_match_golden(kernel, kind):
    g = _golden(kind)["dep_filters"]
    got = _port(kernel, kind).dep_filters()
    if kind == "LessonLearned":
        # NOTA (delta intencional): a classe retornava {}, o port retorna
        # None (sem declaração). Ambos falsy — call-sites fazem `or {}`.
        assert g == {} and got is None
    else:
        assert got == g


# --- summary ------------------------------------------------------------------

def test_workflow_event_summary_matches_golden(kernel):
    """WorkflowEvent tinha summary explícito na classe — o descriptor o
    reproduz exatamente, incluindo defaults null pra campo ausente."""
    g = _golden("WorkflowEvent")["summary_cases"]
    port = _port(kernel, "WorkflowEvent")
    assert port.summary(_doc(dict(g["full"]["spec"]))) == g["full"]["out"]
    assert port.summary(_doc({})) == g["partial"]["out"]


@pytest.mark.parametrize("kind", sorted(CURATED_SUMMARY_DEFAULTS))
def test_curated_summary_projection(kernel, kind):
    """Delta intencional: projeção curada substitui o eco whole-spec do
    KindBase default (ver docstring do módulo). Presente vem do spec;
    ausente cai no default declarado."""
    port = _port(kernel, kind)
    defaults = CURATED_SUMMARY_DEFAULTS[kind]
    assert port.summary(_doc({})) == defaults
    full = _golden(kind)["summary_cases"]["full"]["spec"]
    out = port.summary(_doc(dict(full)))
    assert set(out) == set(defaults)
    for field in defaults:
        if field in full:
            assert out[field] == full[field], (kind, field)
        else:
            assert out[field] == defaults[field], (kind, field)


@pytest.mark.parametrize("kind", KINDS)
def test_summary_bare_dict_port_semantics(kernel, kind):
    """NOTA do piloto: bare-dict não é Document — sem `.spec`, projeta os
    defaults declarados (call-sites reais passam Document)."""
    port = _port(kernel, kind)
    full = _golden(kind)["summary_cases"]["full"]["spec"]
    out = port.summary(dict(full))
    expected = CURATED_SUMMARY_DEFAULTS.get(kind) or _golden(kind)["summary_cases"]["partial"]["out"]
    assert out == expected


# --- parse --------------------------------------------------------------------

def _envelope(kind: str, api_version: str, spec: dict) -> dict:
    return {
        "apiVersion": api_version,
        "kind": kind,
        "metadata": {"name": f"{kind.lower()}-001"},
        "spec": spec,
    }


@pytest.mark.parametrize("kind", KINDS)
def test_parse_valid_accepted(kernel, kind):
    g = _golden(kind)
    raw = _envelope(kind, g["identity"]["api_version"], dict(g["summary_cases"]["full"]["spec"]))
    port = _port(kernel, kind)
    assert port.parse(dict(raw)) == raw


@pytest.mark.parametrize("kind,missing", [
    ("WorkflowEvent", "phase"),
    ("LessonLearned", "area"),
    ("Retrospective", "title"),
    ("PatternInsight", "dream_ref"),
    ("PreMortem", "source_story"),
])
def test_parse_invalid_rejected(kernel, kind, missing):
    """O PORT valida contra o schema (classes eram pass-through — upgrade
    intencional): sem um required → ValueError; no kernel vira typed=None +
    evento parse_error, nunca crash de load."""
    g = _golden(kind)
    spec = dict(g["summary_cases"]["full"]["spec"])
    spec.pop(missing)
    port = _port(kernel, kind)
    with pytest.raises(ValueError, match=missing):
        port.parse(_envelope(kind, g["identity"]["api_version"], spec))


# --- embed (F3 D4) -----------------------------------------------------------

def test_lessonlearned_declares_embed_fields(kernel):
    """Mesmos campos do branch legado de source_text_for (summary + body) —
    substitui a entrada no frozenset EMBEDDABLE_KINDS (ratchet D4)."""
    assert _port(kernel, "LessonLearned").embed_fields == ["summary", "body"]


@pytest.mark.parametrize("kind", ["WorkflowEvent", "Retrospective", "PatternInsight", "PreMortem"])
def test_non_embeddable_kinds_stay_undeclared(kernel, kind):
    """Esses kinds NÃO eram embeddable antes do F3 — declarar embed aqui
    seria mudança de comportamento (custo de embedding), não migração."""
    assert _port(kernel, kind).embed_fields is None


# --- classes extintas ----------------------------------------------------------

def test_classes_are_gone():
    import dna.extensions.sdlc as mod
    for cls in ("WorkflowEventKind", "LessonLearnedKind", "RetrospectiveKind",
                "PatternInsightKind", "PreMortemKind"):
        assert not hasattr(mod, cls), f"{cls} ressurgiu — o descriptor é a fonte"
