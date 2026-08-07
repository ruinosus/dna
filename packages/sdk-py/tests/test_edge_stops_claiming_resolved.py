"""i-131 — uma aresta cujo alvo sumiu tem de PARAR de dizer ``resolved: true``.

O defeito, medido pela fatia 2 da ``spec-topologia-do-grafo`` e reportado sem
conserto: apagada a instância alvo, a aresta continua na ``dna_edges`` **e
continua reportando ``resolved: true``**. Não é impreciso — é o OPOSTO,
entregue com a mesma confiança, para quem perguntou exatamente para distinguir
os dois casos.

⚠️ **O conserto NÃO é apagar a aresta junto**, e por isso o segundo teste deste
arquivo vale tanto quanto o primeiro. A decisão do founder de 06/08/2026 sobre
o ``AuditLog`` diz que uma linha de auditoria sobre uma instância apagada TEM
que continuar apontando — pendurar ali é o certo, e agora há vocabulário
(``on_target_delete: allow``). O defeito é MENTIR enquanto sobrevive.

**Cada asserção aqui nomeia um mutante, porque uma guarda que não sabe o que
veria mudar passa verde sobre conserto revertido.** Os mutantes, e onde morrem:

======================================================  ======================
mutante                                                 morre em
======================================================  ======================
o conserto é revertido (``resolved`` volta a ser         ``test_a_aresta_para_
``to_kind IS NOT NULL``)                                 de_dizer_resolvida``
o delete apaga a aresta de entrada "para consertar"      ``test_a_aresta_
                                                         sobrevive_ao_delete``
o delete zera ``to_kind`` em vez de marcar (perderia    ``test_pendurada_de_
o Kind, e a aresta sumiria da travessia ``in``)          nascenca_e_orfa``
o ``UPDATE`` perde o predicado ``to_name``               ``test_marca_so_o_
(marca as arestas de outros alvos)                       alvo_apagado``
a marca é permanente (a origem reescrita não             ``test_reescrever_a_
re-resolve)                                              origem_limpa``
alguém "recalcula por nome" (delete + recria com o       ``test_recriar_com_o_
mesmo nome volta a dizer resolvida)                      mesmo_nome``
o ``UPDATE`` usa ``_api_version_where`` (casamento        ``test_marca_alcanca_
exato) e pula as linhas pré-0009 com ``to_api_version``   aresta_sem_api_
NULL                                                     version``
a marca é feita no portão do ``on_target_delete``        ``test_marca_sem_
(que curto-circuita e não toca em loja nenhuma no        nenhuma_politica_
default ``allow`` — isto é, em todo delete de hoje)      declarada``
======================================================  ======================

Os dois dialetos, pela razão que os testes de travessia dão: o argumento
inteiro de uma CTE recursiva sobre um motor de grafo é que ela é SQL padrão, e
um argumento desses vale o que o segundo dialeto prova.
"""
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from dna.kernel import Kernel
from tests import _graph_store

_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"
SCOPE = "edge-honesty"


def _doc(kind: str, name: str, **spec: Any) -> dict[str, Any]:
    base = {"description": "d", "status": "todo"}
    base.update(spec)
    return {
        "apiVersion": _SDLC_API, "kind": kind,
        "metadata": {"name": name}, "spec": base,
    }


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    src, cleanup = await _graph_store.build_store(request.param, "honest")
    kernel = Kernel.auto()
    kernel.source(src)
    try:
        yield kernel, src
    finally:
        await cleanup()


async def _pair(kernel) -> None:
    """``Story/s-x → Feature/f-y`` — uma referência declarada e resolvida."""
    await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
    await kernel.write_instance(
        SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
    )


async def _edges_in(kernel, kind="Feature", name="f-y"):
    result = await kernel.graph_refs(SCOPE, kind, name, direction="in")
    return result


async def _rows(src, **where):
    e = src.edges
    async with src._engine.connect() as conn:
        cols = [c.name for c in e.columns]
        rows = (await conn.execute(sa.select(e).where(
            *[e.c[k] == v for k, v in where.items()]
        ))).all()
    return [dict(zip(cols, r)) for r in rows]


# ── O MUTANTE PRINCIPAL ─────────────────────────────────────────────────────


class TestOQueAArestaAfirma:
    @pytest.mark.anyio
    async def test_a_aresta_para_de_dizer_resolvida(self, store):
        """⭐ O teste da issue, e o que fica VERMELHO se o conserto for revertido.

        Antes: ``resolved`` era ``to_kind IS NOT NULL`` — um fato do instante
        da ESCRITA, servido como um fato do instante da LEITURA. Reverter o
        conserto faz a segunda asserção voltar a ``True``.
        """
        kernel, _ = store
        await _pair(kernel)

        antes = await _edges_in(kernel)
        assert [e["resolved"] for e in antes.edges] == [True], (
            "a montagem tem de partir de uma aresta REALMENTE resolvida — sem "
            "isso o teste passaria por não haver aresta nenhuma"
        )

        await kernel.delete_instance(SCOPE, "Feature", "f-y")

        depois = await _edges_in(kernel)
        assert [(e["from_kind"], e["from_name"]) for e in depois.edges] == [
            ("Story", "s-x"),
        ], "a aresta tem de continuar visível — pendurar é o certo"
        assert depois.edges[0]["resolved"] is False, (
            "apagado o alvo, não há mais o que resolver: dizer `true` aqui é a "
            "informação OPOSTA, com a mesma confiança de sempre"
        )
        assert depois.dangling == depois.edges

    @pytest.mark.anyio
    async def test_a_aresta_sobrevive_ao_delete(self, store):
        """⚠️ O conserto NÃO é apagar a aresta junto (decisão do founder,
        ``AuditLog``): a aresta pertence a OUTRA instância, que continua
        dizendo o que disse. Um "conserto" que apaga a linha passa no teste
        acima e morre aqui."""
        kernel, src = store
        await _pair(kernel)
        await kernel.delete_instance(SCOPE, "Feature", "f-y")

        rows = await _rows(src, scope=SCOPE, from_kind="Story", from_name="s-x")
        assert len(rows) == 1, "a aresta de ENTRADA do alvo não é do alvo"
        assert rows[0]["to_kind"] == "Feature", (
            "zerar `to_kind` apagaria QUAL Kind a referência achou — e tiraria "
            "a aresta da travessia `in`, que casa por `to_kind`"
        )
        assert rows[0]["to_name"] == "f-y"
        assert rows[0]["to_deleted_at"] is not None

    @pytest.mark.anyio
    async def test_pendurada_de_nascenca_e_orfa_sao_estados_DIFERENTES(self, store):
        """``resolved: false`` sozinho junta dois problemas com donos
        diferentes: um erro de quem AUTOROU (um nome que nunca existiu) e um
        delete que passou por cima de referência viva. ``to_deleted_at``
        separa, e ``orphaned`` é a leitura pronta."""
        kernel, _ = store
        await _pair(kernel)
        # nunca resolveu: nenhum Feature chamado `fantasma` jamais existiu
        await kernel.write_instance(
            SCOPE, "Story", "s-z", _doc("Story", "s-z", feature="fantasma"),
        )
        await kernel.delete_instance(SCOPE, "Feature", "f-y")

        orfa = (await _edges_in(kernel)).edges[0]
        nunca = (await _edges_in(kernel, "Feature", "fantasma")).edges

        assert orfa["resolved"] is False and orfa["to_deleted_at"] is not None
        # A pendurada de nascença não tem `to_kind`, então a travessia `in` por
        # `Feature/fantasma` não a acha — ela aparece na travessia `out` da
        # origem, que é onde a diferença fica visível.
        assert nunca == []
        saindo = await kernel.graph_refs(SCOPE, "Story", "s-z", direction="out")
        pendurada = saindo.edges[0]
        assert pendurada["resolved"] is False
        assert pendurada["to_deleted_at"] is None, (
            "nada foi apagado aqui: o alvo nunca existiu. Carimbar um instante "
            "seria inventar um delete que não houve"
        )
        assert saindo.orphaned == [], "pendurada de nascença não é órfã"

        de_volta = await _edges_in(kernel)
        assert de_volta.orphaned == de_volta.edges


# ── o UPDATE não pode ser mais largo do que o delete ────────────────────────


class TestOAlcanceDaMarca:
    @pytest.mark.anyio
    async def test_marca_so_o_alvo_apagado(self, store):
        """Um ``UPDATE`` sem o predicado ``to_name`` marcaria as arestas de
        TODOS os Features do scope — e a travessia passaria a mentir na direção
        contrária, que é o defeito que este conserto existe para não criar."""
        kernel, _ = store
        await _pair(kernel)
        await kernel.write_instance(SCOPE, "Feature", "f-vive", _doc("Feature", "f-vive"))
        await kernel.write_instance(
            SCOPE, "Story", "s-vive", _doc("Story", "s-vive", feature="f-vive"),
        )

        await kernel.delete_instance(SCOPE, "Feature", "f-y")

        viva = (await _edges_in(kernel, "Feature", "f-vive")).edges
        assert [e["resolved"] for e in viva] == [True]
        assert viva[0]["to_deleted_at"] is None

    @pytest.mark.anyio
    async def test_marca_alcanca_aresta_sem_api_version_do_alvo(self, store):
        """``to_api_version`` é NULL em toda linha anterior à revisão 0009 e em
        toda aresta cujo produtor não soube dizer. Um ``UPDATE`` casando por
        igualdade EXATA pularia justamente as mais antigas — que são as mais
        prováveis de apontar para algo prestes a sumir.

        ⚠️ **O delete tem de vir PINADO**, e isso não é detalhe do teste: com
        ``api_version=None`` o predicado exato some inteiro e o mutante
        sobrevive — medido. A porta real pina sempre
        (``delete_instance_impl`` EXIGE ``api_version``), então um teste
        despinado estaria medindo um caminho que nenhum chamador usa.
        """
        kernel, src = store
        await _pair(kernel)
        e = src.edges
        async with src._engine.begin() as conn:
            await conn.execute(e.update().where(
                e.c.scope == SCOPE, e.c.from_name == "s-x",
            ).values(to_api_version=None))

        await kernel.delete_instance(
            SCOPE, "Feature", "f-y", api_version=_SDLC_API)
        assert (await _edges_in(kernel)).edges[0]["resolved"] is False

    @pytest.mark.anyio
    async def test_marca_sem_nenhuma_politica_declarada(self, store):
        """A marca NÃO pode morar no portão do ``on_target_delete``.

        ``plan_target_delete`` curto-circuita em ``enforcers_for`` e **não toca
        em loja nenhuma** quando nenhuma relação declara política — que é todo
        delete deste registro hoje (``Story.feature`` não declara nada, e este
        teste é justamente esse caso). Marcar lá dentro daria um conserto que
        só funciona onde alguém já declarou algo.
        """
        from dna.kernel.write.target_delete import enforcers_for, registry_relations

        kernel, _ = store
        rels = registry_relations(kernel.kind_ports())
        assert enforcers_for(rels, "Feature") == [], (
            "a premissa deste teste é que o portão NÃO roda para Feature — se "
            "alguém declarar uma política, escolha outro Kind, não apague o teste"
        )
        await _pair(kernel)
        await kernel.delete_instance(SCOPE, "Feature", "f-y")
        assert (await _edges_in(kernel)).edges[0]["resolved"] is False


# ── a marca é um fato, não um estado permanente ────────────────────────────


class TestAMarcaEUmFato:
    @pytest.mark.anyio
    async def test_reescrever_a_origem_limpa_a_marca(self, store):
        """A marca vale até a origem ser re-derivada. ``_replace_edges`` é
        DELETE+INSERT, então a próxima escrita da instância de ORIGEM produz um
        conjunto novo pelo produtor VIVO — que teve o alvo na mão."""
        kernel, _ = store
        await _pair(kernel)
        await kernel.delete_instance(SCOPE, "Feature", "f-y")
        assert (await _edges_in(kernel)).edges[0]["resolved"] is False

        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        de_novo = (await _edges_in(kernel)).edges
        assert [e["resolved"] for e in de_novo] == [True]
        assert de_novo[0]["to_deleted_at"] is None

    @pytest.mark.anyio
    async def test_recriar_com_o_mesmo_nome_nao_ressuscita_a_aresta(self, store):
        """⭐ A razão pela qual a marca vence um recálculo POR NOME na leitura.

        Apagar e recriar sob o mesmo nome produz um objeto DIFERENTE — é
        literalmente por isso que a ``ownerReference`` do Kubernetes carrega
        ``uid`` além de ``name``, e por isso a 0008 gravou ``to_id``. Esta
        aresta resolveu para o id ANTIGO. Um ``LEFT JOIN`` por ``(kind, name)``
        diria ``resolved: true`` sobre um objeto que ela nunca viu; a marca
        continua verdadeira até a origem ser re-derivada.
        """
        kernel, _ = store
        await _pair(kernel)
        antes = (await _edges_in(kernel)).edges[0]["to_id"]
        await kernel.delete_instance(SCOPE, "Feature", "f-y")
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))

        agora = await kernel.get_instance(SCOPE, "Feature", "f-y")
        novo_id = (agora or {}).get("metadata", {}).get("id")
        assert novo_id and novo_id != antes, (
            "a premissa: recriar sob o mesmo nome mint a um id NOVO. Sem isso "
            "este teste não estaria medindo identidade"
        )
        aresta = (await _edges_in(kernel)).edges[0]
        assert aresta["to_id"] == antes
        assert aresta["resolved"] is False, (
            "a aresta resolveu para o objeto antigo, e ele continua apagado"
        )
