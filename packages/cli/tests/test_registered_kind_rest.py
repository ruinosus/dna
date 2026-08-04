"""``GET /v1/kinds/registry/{kind}`` — the registered Kind's descriptor.

O buraco medido em 03/08/2026 (dna-cloud): nenhuma rota servia o JSON Schema
de um Kind REGISTRADO — ``GET /v1/kinds`` lista só os AUTORADOS e
``/v1/definitions/{kind}/{name}`` exige documento e omite o schema. O portal
copiava constraints à mão (o pior caso: a política de memória duplicava
min/max de ``neighbors``, o enum de ``engine`` e os triggers), e cada cópia é
deriva esperando release.

O que este módulo prende:

* o descritor sai com o NOME DE FIO ``schema`` (o mesmo das outras duas
  portas) e com o ``ui_schema`` que o editor já consome;
* a CONSTRAINT viaja — o formulário deriva ``minimum``/``enum`` em vez de
  copiá-los (o teste usa exatamente o campo que motivou a rota);
* Kind desconhecido → 404, e a rota ``registry/{kind}`` não é engolida pela
  rota irmã ``/v1/kinds/{kind}`` (autorados, filtrada por chamador).

App real via ``TestClient`` — mesmo padrão de ``test_definitions_rest.py``.
"""
from __future__ import annotations

import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _client(dna_dir) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE))


def test_registered_agent_descriptor_carries_schema_and_ui_schema(dna_dir):
    with _client(dna_dir) as c:
        r = c.get("/v1/kinds/registry/Agent")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "Agent"
        # O nome de FIO: ``schema``, como nas outras duas portas.
        assert isinstance(body["schema"], dict)
        assert isinstance(body["ui_schema"], dict)
        # O caso que motivou o widget kind-ref: o hint viaja no descritor.
        prompt_hint = body["ui_schema"].get("promptTemplate")
        assert prompt_hint is not None and prompt_hint.get("widget") == "kind-ref"


def test_cognitive_policy_constraints_travel(dna_dir):
    """O caso que MOTIVOU a rota: a política de memória. O portal copiava
    1–50 de ``neighbors`` e o enum de ``engine`` à mão; agora a constraint
    tem de chegar pelo descritor — se este teste quebrar, o formulário
    derivado volta a ficar cego."""
    with _client(dna_dir) as c:
        r = c.get("/v1/kinds/registry/CognitivePolicy")
        assert r.status_code == 200, r.text
        schema = r.json()["schema"]
        ing = schema["properties"]["ingestion"]["properties"]
        assert ing["neighbors"]["minimum"] == 1
        assert ing["neighbors"]["maximum"] == 50
        assert set(ing["engine"]["enum"]) == {"pipeline", "pipeline-agent", "agent"}


def test_unknown_kind_is_404(dna_dir):
    with _client(dna_dir) as c:
        r = c.get("/v1/kinds/registry/NoSuchKindXyz")
        assert r.status_code == 404, r.text
        assert "NoSuchKindXyz" in r.json()["detail"]


def test_registry_segment_is_not_swallowed_by_the_authored_kind_route(dna_dir):
    """``/v1/kinds/registry/Agent`` (4 segmentos) nunca deve casar com
    ``/v1/kinds/{kind}`` (3) nem com ``/{kind}/documents`` — se a ordem de
    declaração regredir, este GET devolveria o 404 filtrado da porta de
    autorados em vez do descritor."""
    with _client(dna_dir) as c:
        registry = c.get("/v1/kinds/registry/Agent")
        authored = c.get("/v1/kinds/Agent")
        assert registry.status_code == 200
        # A porta de AUTORADOS não conhece o Kind registrado Agent: 404 —
        # e é essa diferença que prova que são portas distintas.
        assert authored.status_code == 404


def test_tenant_param_deriva_o_scope_como_as_rotas_de_documentos(dna_dir):
    """i-094 (medido em 04/08 no wizard F4 do dna-cloud): o portal só conhece
    o WORKSPACE, e a rota só aceitava ``scope`` cru — obrigando o chamador a
    hardcodar a convenção ``tenant-<ws>``. Com ``tenant``, o scope é DERIVADO
    server-side (``live.default_scope``), o mesmo contrato de toda rota de
    documento. Aqui (single-workspace, sem vendor) default_scope devolve o
    base scope — o Kind registrado responde igual ao caminho sem tenant."""
    with _client(dna_dir) as c:
        sem = c.get("/v1/kinds/registry/Agent")
        com = c.get("/v1/kinds/registry/Agent", params={"tenant": "ws-qualquer"})
        assert com.status_code == 200, com.text
        assert com.json()["schema"] == sem.json()["schema"]
        # O contrato antigo não regride: ``scope`` explícito continua aceito
        # (Agent é Kind de EXTENSÃO — global — então qualquer filtro de scope
        # o resolve; a PRECEDÊNCIA scope>tenant é código de 1 linha na rota,
        # visível no teste de forma apenas indireta por este 200).
        r = c.get(
            "/v1/kinds/registry/Agent",
            params={"scope": _SCOPE, "tenant": "ws-qualquer"},
        )
        assert r.status_code == 200
