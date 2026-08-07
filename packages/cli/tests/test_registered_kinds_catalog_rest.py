"""``GET /v1/kinds/registry`` — o CATÁLOGO de Kinds registrados.

O buraco medido em 06/08/2026 (dna-cloud): a capacidade de ENUMERAR o registry
existe desde que o catálogo existe (``list_kinds_impl``, servido pela face MCP
como ``list_kinds``), mas a read-API só tinha a porta SINGULAR
``/v1/kinds/registry/{kind}``. Sem a coleção, todo consumidor REST que
precisava da lista era obrigado a hardcodar uma — e lista hardcodada é
exatamente como um Kind registrado amanhã nasce invisível. Foi o defeito
medido: 121 instâncias em 9 Kinds sem nenhuma tela no portal.

O que este módulo prende:

* a coleção existe e ENUMERA — inclusive os Kinds BUILT-IN, que a porta de
  autorados (``GET /v1/kinds``) por desenho nunca lista;
* cada linha carrega o que decide uma ação ANTES de tentá-la — ``writable`` +
  ``write_refusal`` para um Kind BOOTSTRAP;
* a rota não é engolida por ``/v1/kinds/{kind}`` (ordem de declaração), o
  mesmo risco que a irmã singular já prende;
* ``tenant`` deriva o scope como toda rota de instância.

App real via ``TestClient`` — mesmo padrão de ``test_registered_kind_rest.py``.
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


def test_the_catalog_enumerates_the_registry(dna_dir):
    with _client(dna_dir) as c:
        r = c.get("/v1/kinds/registry")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scope"] == _SCOPE
        assert body["count"] == len(body["kinds"]) > 0
        by_kind = {k["kind"]: k for k in body["kinds"]}
        # Built-ins — a razão da rota existir. A porta de AUTORADOS nunca os
        # lista, então sem esta coleção eles são inalcançáveis por REST.
        for kind in ("Agent", "Research", "Plan", "TestGuide", "ADR"):
            assert kind in by_kind, f"{kind} registrado e ausente do catálogo"
        agent = by_kind["Agent"]
        assert agent["api_version"]
        assert agent["plane"] in {"composition", "record"}


def test_a_refused_write_is_visible_before_it_is_attempted(dna_dir):
    """Um Kind BOOTSTRAP (KindDefinition/Genome/LayerPolicy) não aceita a
    escrita genérica. A linha do catálogo diz isso COM o motivo — descobrir
    pela recusa custa uma ida ao servidor e uma unidade medida."""
    with _client(dna_dir) as c:
        by_kind = {k["kind"]: k for k in c.get("/v1/kinds/registry").json()["kinds"]}
        bootstrap = by_kind["KindDefinition"]
        assert bootstrap["writable"] is False
        assert bootstrap["write_refusal"], "um false sem motivo não é acionável"
        assert by_kind["Agent"]["writable"] is True
        assert by_kind["Agent"]["write_refusal"] is None


def test_the_catalog_is_not_swallowed_by_the_authored_kind_route(dna_dir):
    """``/v1/kinds/registry`` (3 segmentos) colide em FORMA com
    ``/v1/kinds/{kind}``. Só a ordem de declaração as separa — se ela
    regredir, este GET vira a busca de um Kind chamado ``registry`` e devolve
    o 404 filtrado da porta de autorados."""
    with _client(dna_dir) as c:
        catalog = c.get("/v1/kinds/registry")
        assert catalog.status_code == 200, catalog.text
        assert "kinds" in catalog.json() and "count" in catalog.json()
        # E a irmã singular continua respondendo (nenhuma das duas engole a outra).
        assert c.get("/v1/kinds/registry/Agent").status_code == 200


def test_the_catalog_is_not_the_authored_roster(dna_dir):
    """Duas perguntas diferentes, e confundi-las é o erro caro: autorados
    inclui os INERTES (a decisão de aprovação); o catálogo lista o que está
    REGISTRADO — um Kind não aprovado é, por definição, ausente dele."""
    with _client(dna_dir) as c:
        catalog = {k["kind"] for k in c.get("/v1/kinds/registry").json()["kinds"]}
        authored = {k["kind"] for k in c.get("/v1/kinds").json()["kinds"]}
        assert "Agent" in catalog and "Agent" not in authored


def test_tenant_param_deriva_o_scope_como_as_rotas_de_documentos(dna_dir):
    """Mesmo contrato da irmã singular (i-094): o portal só conhece o
    WORKSPACE, e derivar ``tenant -> default_scope`` server-side é o que o
    poupa de hardcodar a convenção ``tenant-<ws>``."""
    with _client(dna_dir) as c:
        sem = c.get("/v1/kinds/registry")
        com = c.get("/v1/kinds/registry", params={"tenant": "ws-qualquer"})
        assert com.status_code == 200, com.text
        assert com.json()["count"] == sem.json()["count"]
        assert c.get(
            "/v1/kinds/registry",
            params={"scope": _SCOPE, "tenant": "ws-qualquer"},
        ).status_code == 200


def test_plan_filtering_is_absent_on_this_face_and_says_so(dna_dir):
    """A face MCP encurta o catálogo para as famílias que o plano do chamador
    libera. Esta face não tem plano por requisição — então
    ``filtered_by_plan`` é sempre false AQUI, e nunca um false que signifique
    'filtrou mas não conto'."""
    with _client(dna_dir) as c:
        body = c.get("/v1/kinds/registry").json()
        assert body["filtered_by_plan"] is False
        assert body["filtered_out"] == 0


# ── i-121: o Kind Spec dizia a data e não dizia o que É ──────────────────────


def test_every_sdlc_artifact_row_answers_WHAT_KIND_OF_THING_IT_IS(dna_dir):
    """i-121, na porta que o defeito atravessou.

    As raias do board do portal derivam desta rota: ``lib/source/board-category.ts``
    lê ``traits`` de cada linha e classifica por ``sdlc.rollup`` / ``sdlc.decision``
    / ``sdlc.work-item``. ``Spec`` declarava só ``sdlc.dated`` — data, não
    natureza — então TODA spec caía na quarta raia, "sem classificação". Honesto
    e vazio: a lacuna era do vocabulário do SDK, não da tela.

    A asserção é DERIVADA do vocabulário do SDK (``sdlc_family``), não de uma
    lista escrita aqui, porque é exatamente a derivação que o portal faz — e
    ``Spec`` está no parametrize junto de ``ADR`` e dos work items justamente
    para que a guarda continue medindo a família e não um nome.
    """
    from dna.application import sdlc_family as F

    classifying = {F.TRAIT_ROLLUP, F.TRAIT_DECISION, F.TRAIT_WORK_ITEM}
    with _client(dna_dir) as c:
        rows = {k["kind"]: k for k in c.get("/v1/kinds/registry").json()["kinds"]}
    for kind in ("Spec", "ADR", "Story", "Feature"):
        declared = set(rows[kind]["traits"])
        assert declared & classifying, (
            f"{kind} atravessa a rota sem declarar o que é: {sorted(declared)}"
        )
    # E a classificação de Spec é a MESMA de ADR — as duas são decisão
    # registrada. Se um dia divergirem, é uma decisão, não um descuido.
    assert F.TRAIT_DECISION in set(rows["Spec"]["traits"])
    assert F.TRAIT_DECISION in set(rows["ADR"]["traits"])
