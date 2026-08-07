"""O grafo COMO ELE ERA em T — a fatia 4 de ``spec-topologia-do-grafo``.

O eixo de TRANSAÇÃO já existia para UMA instância (``get_instance(as_of=…)``,
degrau 0) e não existia para o grafo. A leitura óbvia — filtrar ``dna_edges``
por ``from_version`` — foi medida e MORREU antes de virar código:

```
banco do dna-cloud, 07/08/2026
  arestas                                            33
  from_version < versão atual da instância (STALE)    0   ← ⭐
```

Zero, e não por frescor: ``_replace_edges`` APAGA e reinsere o conjunto inteiro
a cada escrita, então uma linha stale não pode existir. A tabela de arestas não
tem história **por construção**. Filtrá-la por tempo devolveria o presente com
carimbo do passado — a mentira confiante que esta suíte existe para prender.

Então a travessia ``as_of`` **re-deriva** o grafo dos envelopes de
``dna_versions``, e esta suíte mede as três coisas que isso pode errar:

1. **fidelidade** — ``as_of=agora`` tem de devolver EXATAMENTE o grafo vivo. É a
   asserção mais valiosa do arquivo, porque ela é uma COMPARAÇÃO e não um
   literal: qualquer divergência entre a CTE e a re-derivação (ciclo, dedup,
   ``resolved``, escopo herdado, profundidade) fica vermelha aqui sem que
   ninguém tenha de prevê-la;
2. **história** — o grafo de ontem tem de ser o de ONTEM, inclusive as arestas
   que sumiram desde então (que é justamente o que uma tabela sem história não
   sabe dizer);
3. **as recusas** — 501 sem história, 410 com história podada, 404 quando não
   existia ainda. E o meio-termo: um nó ALCANÇADO e ilegível vira nome em
   ``as_of_truncated``, não uma travessia derrubada nem um silêncio.

Nos DOIS dialetos, como toda a família do grafo: a re-derivação usa
``row_number()`` numa janela, e "funciona em SQLite" não é evidência sobre
Postgres.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from dna.kernel import Kernel
from dna.memory.as_of import AsOfTruncated, AsOfUnsupported, normalize_as_of
from tests import _graph_store

_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"
SCOPE = "graph-as-of"


def _doc(kind: str, name: str, **spec: Any) -> dict[str, Any]:
    base = {"description": "d", "status": "todo"}
    base.update(spec)
    return {
        "apiVersion": _SDLC_API, "kind": kind,
        "metadata": {"name": name}, "spec": base,
    }


def _mark() -> str:
    """O instante ENTRE duas escritas — "agora", com o passado já gravado.

    ⚠️ Não use um instante no FUTURO para isto. A primeira versão desta suíte
    usava ``agora + 5s`` em todo lugar, e nos testes de história isso caía
    DEPOIS da segunda escrita — a asserção "o passado é diferente do presente"
    passava a comparar o presente consigo mesmo e teria ficado verde sobre uma
    travessia que ignorasse ``as_of`` por completo. Marco entre escritas é
    ``_mark``; "depois de tudo" é ``_later``, e os dois nomes existem para que a
    escolha errada seja visível na linha."""
    return normalize_as_of(datetime.now(timezone.utc))


def _later() -> str:
    """Um instante seguramente DEPOIS de tudo que já foi escrito — só para os
    testes de FIDELIDADE, onde "o mesmo instante que o vivo" é o ponto."""
    return normalize_as_of(datetime.now(timezone.utc) + timedelta(seconds=5))


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    monkeypatch.delenv("DNA_GRAPH_MAX_DEPTH", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    src, cleanup = await _graph_store.build_store(request.param, "asof")
    kernel = Kernel.auto()
    kernel.source(src)
    try:
        yield kernel, src
    finally:
        await cleanup()


def _key(e: dict[str, Any]) -> tuple:
    """A identidade de UMA aresta na resposta, sem os campos de caminhada.

    ``depth`` e ``closes_cycle`` ficam de fora das comparações de conjunto e
    entram nas suas próprias asserções: misturá-los faria um teste de fidelidade
    falhar por ordem de visita em vez de por conteúdo."""
    return (
        e["direction"], e["from_api_version"], e["from_kind"], e["from_name"],
        e["source_field"], e["ordinal"], e["to_kind"], e["to_name"],
        e["to_api_version"], e["to_scope"], e["to_id"], e["resolved"],
        tuple(e["declared_to"]), e["from_version"],
    )


async def _chain(kernel) -> None:
    """``Task/t-1 → Story/s-x → Feature/f-y → Epic/e-1`` — três saltos."""
    await kernel.write_instance(SCOPE, "Epic", "e-1", _doc("Epic", "e-1"))
    await kernel.write_instance(
        SCOPE, "Feature", "f-y", _doc("Feature", "f-y", epic="e-1"),
    )
    await kernel.write_instance(
        SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
    )
    await kernel.write_instance(
        SCOPE, "Task", "t-1", _doc("Task", "t-1", story_ref="s-x"),
    )


# ── 1. FIDELIDADE: as_of=agora É o grafo vivo ──────────────────────────────


class TestAsOfAgoraEIgualAoGrafoVivo:
    """A guarda que nenhuma outra substitui, e o motivo é o método.

    A travessia viva é uma CTE recursiva em SQL; a ``as_of`` é uma caminhada em
    Python sobre envelopes de versão. São dois MECANISMOS para uma resposta, e
    dois mecanismos que podem discordar sempre discordam — foi exatamente por
    isso que ``resolve_relations`` existe como função ÚNICA no write path.
    Aqui não dá para unificar o mecanismo (um lê arestas, o outro re-deriva),
    então a unificação é feita onde importa: **na resposta**.

    Um literal escrito à mão passaria numa re-derivação que tivesse crescido a
    sua própria forma — outro dedup, outro ``resolved``, outro escopo. A
    comparação não passa.
    """

    @pytest.mark.anyio
    @pytest.mark.parametrize("direction", ["in", "out", "both"])
    @pytest.mark.parametrize("depth", [1, 2, 3])
    async def test_as_mesmas_arestas_nas_9_combinacoes(
        self, store, direction, depth,
    ):
        kernel, _ = store
        await _chain(kernel)
        instant = _later()
        vivo = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction=direction, depth=depth,
        )
        historico = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction=direction, depth=depth,
            as_of=instant,
        )
        assert {_key(e) for e in historico.edges} == {
            _key(e) for e in vivo.edges
        }, (
            "a re-derivação e a CTE discordam sobre o MESMO instante — uma das "
            "duas está errada, e a resposta histórica é a que ninguém confere"
        )

    @pytest.mark.anyio
    @pytest.mark.parametrize("direction", ["in", "out", "both"])
    async def test_a_profundidade_de_cada_aresta_tambem_bate(
        self, store, direction,
    ):
        """``depth`` não é decoração: a tela desenha a distância com ele, e uma
        re-derivação que achasse as mesmas arestas um salto adiante renderizaria
        um grafo com outra forma."""
        kernel, _ = store
        await _chain(kernel)
        vivo = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction=direction, depth=3,
        )
        historico = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction=direction, depth=3,
            as_of=_later(),
        )
        assert {(_key(e), e["depth"]) for e in historico.edges} == {
            (_key(e), e["depth"]) for e in vivo.edges
        }

    @pytest.mark.anyio
    async def test_o_stop_e_o_mesmo_vocabulario(self, store):
        """``complete`` / ``depth_reached`` / ``truncated`` — a coisa que
        distingue "isto é tudo" de "aqui eu parei". Um eixo novo que perdesse o
        ``stop`` transformaria toda resposta histórica em "isto é tudo"."""
        kernel, _ = store
        await _chain(kernel)
        instant = _later()
        for depth in (1, 2, 3, 5):
            vivo = await kernel.graph_refs(
                SCOPE, "Feature", "f-y", direction="in", depth=depth)
            hist = await kernel.graph_refs(
                SCOPE, "Feature", "f-y", direction="in", depth=depth,
                as_of=instant)
            assert hist.stop == vivo.stop, depth

    @pytest.mark.anyio
    async def test_o_ciclo_fecha_igual_nas_duas(self, store):
        """``Story.dependencies → Story`` é auto-referente por desenho, então o
        ciclo é dado ordinário e não corrupção. A aresta que FECHA é reportada
        (esconder o ciclo seria pior que sobreviver a ele) e não é expandida —
        as duas travessias têm de concordar nos dois lados disso."""
        kernel, _ = store
        # ⚠️ Três escritas para dois documentos, e a terceira é o teste
        # funcionando: a aresta VIVA guarda o que a ESCRITA achou, então ``s-a``
        # escrito antes de ``s-b`` existir fica dangling para sempre. Reescrever
        # ``s-a`` no fim é o que faz as duas arestas resolverem — e a diferença
        # tem o seu próprio teste em ``TestOQueCadaUmaDasDuasResponde``.
        await kernel.write_instance(
            SCOPE, "Story", "s-a", _doc("Story", "s-a"))
        await kernel.write_instance(
            SCOPE, "Story", "s-b", _doc("Story", "s-b", dependencies=["s-a"]))
        await kernel.write_instance(
            SCOPE, "Story", "s-a", _doc("Story", "s-a", dependencies=["s-b"]))
        vivo = await kernel.graph_refs(
            SCOPE, "Story", "s-a", direction="out", depth=5)
        hist = await kernel.graph_refs(
            SCOPE, "Story", "s-a", direction="out", depth=5, as_of=_later())
        assert {(_key(e), e["closes_cycle"]) for e in hist.edges} == {
            (_key(e), e["closes_cycle"]) for e in vivo.edges
        }
        assert any(e["closes_cycle"] for e in hist.edges), (
            "o ciclo desapareceu da resposta histórica — a fixture, ou o "
            "anti-ciclo da re-derivação"
        )

    @pytest.mark.anyio
    async def test_a_aresta_DANGLING_aparece_nas_duas(self, store):
        """Com ``DNA_REF_VALIDATION=warn`` (o default) uma instância com
        referência quebrada persiste. A metade quebrada é o conteúdo mais
        valioso do grafo; uma travessia histórica que a filtrasse renderizaria o
        passado mais saudável do que ele foi."""
        kernel, _ = store
        await kernel.write_instance(
            SCOPE, "Story", "s-q", _doc("Story", "s-q", feature="f-nao-existe"))
        vivo = await kernel.graph_refs(
            SCOPE, "Story", "s-q", direction="out")
        hist = await kernel.graph_refs(
            SCOPE, "Story", "s-q", direction="out", as_of=_later())
        assert [e["resolved"] for e in hist.edges] == [False]
        assert {_key(e) for e in hist.edges} == {_key(e) for e in vivo.edges}


# ── 2. HISTÓRIA: o grafo de ontem é o de ONTEM ─────────────────────────────


class TestOGrafoComoEleEra:
    @pytest.mark.anyio
    async def test_a_aresta_que_SUMIU_ainda_esta_la_no_passado(self, store):
        """⭐ O teste da fatia inteira.

        ``s-x`` apontava para ``f-y`` e passou a apontar para ``f-z``. A linha
        de ``dna_edges`` que dizia ``f-y`` **não existe mais** — foi apagada
        pelo ``_replace_edges`` da segunda escrita. Nenhum filtro sobre aquela
        tabela pode devolvê-la; só a re-derivação sobre a versão 1 do envelope.
        """
        kernel, _ = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(SCOPE, "Feature", "f-z", _doc("Feature", "f-z"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"))
        antes = _mark()
        await asyncio.sleep(0.01)
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-z"),
        )

        agora = await kernel.graph_refs(SCOPE, "Story", "s-x", direction="out")
        assert [e["to_name"] for e in agora.edges] == ["f-z"]

        passado = await kernel.graph_refs(
            SCOPE, "Story", "s-x", direction="out", as_of=antes)
        assert [e["to_name"] for e in passado.edges] == ["f-y"], (
            "a travessia histórica devolveu o presente — que é exatamente o que "
            "filtrar dna_edges faria, e por isso a fatia não filtra"
        )

    @pytest.mark.anyio
    async def test_quem_apontava_para_mim_e_parou_aparece_no_IN(self, store):
        """A mesma perda, do lado da pergunta do produto.

        ``direction=in`` sobre ``f-y`` hoje devolve nada; em T devolvia ``s-x``.
        Uma tabela de arestas sem história responderia ``[]`` com a mesma
        confiança das duas vezes."""
        kernel, _ = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(SCOPE, "Feature", "f-z", _doc("Feature", "f-z"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"))
        antes = _mark()
        await asyncio.sleep(0.01)
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-z"),
        )

        agora = await kernel.graph_refs(SCOPE, "Feature", "f-y", direction="in")
        assert agora.edges == []
        passado = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction="in", as_of=antes)
        assert [(e["from_kind"], e["from_name"]) for e in passado.edges] == [
            ("Story", "s-x"),
        ]

    @pytest.mark.anyio
    async def test_from_version_e_a_versao_DAQUELE_instante(self, store):
        """⭐ A coluna que dá nome à fatia, servindo o que ela sempre quis dizer.

        ``from_version`` responde *de qual versão estas arestas foram
        derivadas*. Numa linha viva é sempre a versão de hoje (medido: 0 de 33
        stale). Numa linha ``as_of`` tem de ser a versão de ENTÃO — se viesse a
        de hoje, a resposta carimbaria o presente sobre o passado no único campo
        que serve para desconfiar disso."""
        kernel, _ = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"))
        antes = _mark()
        await asyncio.sleep(0.01)
        for _ in range(3):
            await kernel.write_instance(
                SCOPE, "Story", "s-x",
                _doc("Story", "s-x", feature="f-y", description="mexido"))

        vivo = await kernel.graph_refs(SCOPE, "Story", "s-x", direction="out")
        assert vivo.edges[0]["from_version"] == 4
        passado = await kernel.graph_refs(
            SCOPE, "Story", "s-x", direction="out", as_of=antes)
        assert passado.edges[0]["from_version"] == 1

    @pytest.mark.anyio
    async def test_o_as_of_volta_ecoado_na_resposta(self, store):
        """Quem só olha ``edges`` tem de conseguir distinguir uma resposta
        histórica de uma atual — a mesma razão pela qual ``get_instance`` ecoa o
        dele."""
        kernel, _ = store
        await _chain(kernel)
        instant = _later()
        hist = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction="in", as_of=instant)
        assert hist.as_of == instant
        vivo = await kernel.graph_refs(SCOPE, "Feature", "f-y", direction="in")
        assert vivo.as_of is None
        assert vivo.as_of_truncated == []


# ── 3. AS RECUSAS — metade da entrega ──────────────────────────────────────


class TestAsRecusas:
    @pytest.mark.anyio
    async def test_501_store_sem_historia_RECUSA_em_vez_de_devolver_hoje(
        self, store,
    ):
        """⚠️ Nem ``[]`` nem o grafo do presente. As duas se leem como fatos, e
        as duas seriam inventadas: um store sem história não tem como saber no
        que ele acreditava em T.

        A forma é REAL, não hipotética — é a do adapter de filesystem, que
        declara ``versions=True`` e não retém nenhuma (``list_versions`` →
        ``[]``). Modelada aqui apagando o método num store que guarda arestas,
        porque o filesystem para antes disto, no ``GraphUnsupported``: só assim
        a recusa que o EIXO levanta chega a ser exercitada.
        """
        kernel, src = store
        await _chain(kernel)
        src.load_one_as_of = None
        with pytest.raises(AsOfUnsupported) as exc:
            await kernel.graph_refs(
                SCOPE, "Feature", "f-y", direction="in", as_of=_mark())
        assert "load_one_as_of" in str(exc.value)
        # ⭐ E a travessia VIVA no mesmo store continua respondendo: a recusa é
        # do EIXO, não do store inteiro. Sem esta linha, "refuses everything"
        # passaria no teste.
        vivo = await kernel.graph_refs(SCOPE, "Feature", "f-y", direction="in")
        assert [e["from_name"] for e in vivo.edges] == ["s-x"]

    @pytest.mark.anyio
    async def test_501_o_IN_recusa_sem_load_kind_as_of_e_o_OUT_responde(
        self, store,
    ):
        """A capacidade é medida POR DIREÇÃO, e não por store.

        "O que esta instância apontava em T" precisa só da versão dela; "quem
        apontava PARA ela" precisa de ler os specs dos candidatos. Um store que
        tem a primeira e não a segunda responde uma e recusa a outra — e ``[]``
        na segunda diria "ninguém apontava", que é a afirmação que ele não pode
        fazer."""
        kernel, src = store
        await _chain(kernel)
        instante = _later()
        src.load_kind_as_of = None
        with pytest.raises(AsOfUnsupported):
            await kernel.graph_refs(
                SCOPE, "Feature", "f-y", direction="in", as_of=instante)
        saindo = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction="out", as_of=instante)
        assert [e["to_name"] for e in saindo.edges] == ["e-1"]

    @pytest.mark.anyio
    async def test_a_recusa_carrega_a_base_marcadora_certa(self):
        """``CapabilityRefusal`` e não ``KernelRefusal``: o pedido estava bem
        formado e o chamador tinha direito a ele — o que falta é capacidade do
        STORE, então o remédio é outro deployment e nunca outro pedido.

        É essa base que faz TODA face relatar isto por nome sem enumerar nada, e
        é ela que a guarda derivada de ``test_face_refusal_parity`` exige de
        qualquer coisa que o REST responda 501/410."""
        from dna.kernel.errors import CapabilityRefusal, KernelRefusal

        assert issubclass(AsOfUnsupported, CapabilityRefusal)
        assert issubclass(AsOfTruncated, CapabilityRefusal)
        assert not issubclass(AsOfTruncated, KernelRefusal)
        # ⚠️ E ``AsOfTruncated`` continua ``LookupError``, que é justamente o
        # motivo de a base marcadora ter de vir ANTES nos ``except`` das faces:
        # relatado como ``LookupError`` cru, ele vira "não existia" — o colapso
        # que a classe existe para impedir.
        assert issubclass(AsOfTruncated, LookupError)

    @pytest.mark.anyio
    async def test_410_a_ancora_com_historia_PODADA_recusa(self, store):
        """A poda é real e medida: 8 de 431 instâncias com história no banco do
        dna-cloud têm a v1 podada — todas Engram, porque
        ``VERSION_CHURN_RETENTION`` retém 3 e o autopilot reescreve a mesma
        memória milhares de vezes.

        Aqui a poda é feita à mão (um DELETE nas versões antigas) porque o teste
        é sobre a LEITURA, não sobre quem podou."""
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        for _ in range(3):
            await kernel.write_instance(
                SCOPE, "Feature", "f-y", _doc("Feature", "f-y", description="v"))
        podado_ate = _mark()
        await asyncio.sleep(0.01)
        await kernel.write_instance(
            SCOPE, "Feature", "f-y", _doc("Feature", "f-y", description="depois"))
        v = src.versions
        async with src._engine.begin() as conn:
            await conn.execute(v.delete().where(
                v.c.scope == SCOPE, v.c.kind == "Feature",
                v.c.name == "f-y", v.c.version < 5,
            ))
        with pytest.raises(AsOfTruncated) as exc:
            await kernel.graph_refs(
                SCOPE, "Feature", "f-y", direction="in", as_of=podado_ate)
        assert "pruned" in str(exc.value)

    @pytest.mark.anyio
    async def test_404_a_instancia_nao_existia_AINDA_e_uma_RESPOSTA(self, store):
        """``LookupError`` cru, e de propósito: em T aquilo genuinamente não
        estava lá. A diferença para o 410 é o fato inteiro — "não havia" contra
        "não dá para saber" — e é a única distinção que uma leitura histórica
        não pode errar."""
        kernel, _ = store
        antes_de_tudo = normalize_as_of(
            datetime.now(timezone.utc) - timedelta(days=365))
        await _chain(kernel)
        with pytest.raises(LookupError) as exc:
            await kernel.graph_refs(
                SCOPE, "Feature", "f-y", direction="in", as_of=antes_de_tudo)
        assert not isinstance(exc.value, AsOfTruncated), (
            "'não existia ainda' foi relatado como 'a história foi podada' — "
            "são fatos opostos sobre o mesmo silêncio"
        )

    @pytest.mark.anyio
    async def test_um_no_ALCANCADO_e_podado_vira_nome_e_nao_derruba(self, store):
        """O meio-termo, e ele é o desenho: a âncora que não dá para ler é uma
        RECUSA (410), um vizinho que não dá para ler é um NOME.

        Derrubar a resposta inteira por um vizinho cego trocaria um relatório
        útil por um erro; omiti-lo em silêncio deixaria o leitor concluir
        "ninguém apontava" de "não dá para saber o que estes diziam"."""
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"))
        for i in range(4):
            await kernel.write_instance(
                SCOPE, "Story", "s-z",
                _doc("Story", "s-z", feature="f-y", description=f"v{i}"))
        instante = _mark()
        await asyncio.sleep(0.01)
        # Uma escrita DEPOIS do instante, e a poda de tudo que veio antes: a
        # forma exata que ``VERSION_CHURN_RETENTION`` produz num Engram — resta
        # história, e nenhuma dela alcança T.
        await kernel.write_instance(
            SCOPE, "Story", "s-z", _doc("Story", "s-z", feature="f-y",
                                        description="depois"))
        v = src.versions
        async with src._engine.begin() as conn:
            await conn.execute(v.delete().where(
                v.c.scope == SCOPE, v.c.kind == "Story", v.c.name == "s-z",
                v.c.version < 5,
            ))
        hist = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction="in", as_of=instante)
        assert "Story/s-z" in hist.as_of_truncated
        # A travessia SOBREVIVEU e ainda diz o que sabe.
        assert [(e["from_kind"], e["from_name"]) for e in hist.edges] == [
            ("Story", "s-x"),
        ]


# ── 3b. O que cada uma das duas de fato responde ───────────────────────────


class TestOQueCadaUmaDasDuasResponde:
    """⚠️ ACHADO ao escrever esta fatia, e ele não estava na spec.

    ``as_of=agora`` **não é sempre** o grafo vivo, e a diferença não é bug de
    nenhuma das duas — é o que cada uma responde:

    * a travessia VIVA lê linhas que a ESCRITA produziu: ``resolved`` é *"a
      referência achou alvo NO MOMENTO EM QUE FOI ESCRITA"*;
    * a travessia ``as_of`` RE-DERIVA: ``resolved`` é *"a referência achava
      alvo NAQUELE INSTANTE"*.

    Elas coincidem enquanto a tabela de arestas está em dia, e divergem numa
    direção conhecida: um alvo criado DEPOIS do apontador deixa a linha viva
    dizendo ``dangling`` para sempre — é exatamente a defasagem que o backfill
    (``dna graph backfill``) existe para reparar, e o i-131 fechou só a outra
    metade (o alvo que morreu depois).

    Isto vira teste e não comentário porque é a única forma de a próxima pessoa
    descobrir a diferença ANTES de vê-la numa tela.
    """

    @pytest.mark.anyio
    async def test_o_alvo_criado_DEPOIS_do_apontador(self, store):
        kernel, _ = store
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-tarde"))
        await kernel.write_instance(
            SCOPE, "Feature", "f-tarde", _doc("Feature", "f-tarde"))
        instante = _later()

        vivo = await kernel.graph_refs(SCOPE, "Story", "s-x", direction="out")
        assert [e["resolved"] for e in vivo.edges] == [False], (
            "a aresta viva deixou de ser um fato da ESCRITA — se isto virou "
            "True, alguém ligou re-resolução no caminho vivo e esta suíte "
            "inteira precisa ser relida"
        )
        hist = await kernel.graph_refs(
            SCOPE, "Story", "s-x", direction="out", as_of=instante)
        assert [e["resolved"] for e in hist.edges] == [True], (
            "em T o alvo EXISTIA; a re-derivação tem de dizer isso, ainda que "
            "a linha gravada discorde"
        )


# ── 4. OS LIMITES, FIXADOS — não descobertos depois ────────────────────────


class TestOsLimitesHonestos:
    @pytest.mark.anyio
    async def test_quem_foi_APAGADO_depois_de_T_e_invisivel_no_IN(self, store):
        """⚠️ O limite irredutível desta fatia, PRESO por teste em vez de
        descoberto num incidente — e a metade que o i-131 NÃO alcança.

        ``delete_instance`` remove as linhas de ``dna_versions`` junto com a
        instância (delete é a poda mais completa que existe) **e leva as
        arestas de SAÍDA dela** — que são justamente as que diriam "eu apontava
        para você". Um AUTOR apagado depois de T não deixa testemunha nenhuma, e
        o store não tem como saber que ele existiu.

        O outro lado tem: as arestas de ENTRADA de uma instância apagada
        sobrevivem de propósito (``delete_instance`` explica por quê), com
        ``to_deleted_at`` carimbado — e é por isso que o teste seguinte prova o
        resgate no ``out`` e este pinta o limite no ``in``. **A assimetria é do
        armazenamento**, não uma escolha; ela está escrita nos dois lugares para
        que ninguém a leia como descuido."""
        kernel, _ = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"))
        antes_do_delete = _mark()
        await asyncio.sleep(0.01)
        await kernel.delete_instance(SCOPE, "Story", "s-x")

        hist = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction="in", as_of=antes_do_delete)
        assert hist.edges == [], (
            "se isto passou a devolver a aresta, o limite mudou — atualize o "
            "docstring do módulo de grafo, que promete o contrário"
        )
        assert hist.as_of_truncated == [], (
            "e não é 'truncado': o store não sabe sequer que havia algo a "
            "truncar. Chamar isto de cegueira conhecida seria inventar "
            "conhecimento"
        )

    @pytest.mark.anyio
    async def test_o_alvo_apagado_depois_de_T_e_RESGATADO_no_out(self, store):
        """⭐ Aqui o i-131 paga a fatia 4, e o mecanismo é o inverso do óbvio.

        A re-derivação sozinha erraria: o histórico do alvo foi embora com o
        delete, então "não achei" viraria ``resolved: false`` — a resposta
        OPOSTA, com a mesma confiança, sobre uma relação que em T estava
        perfeita. O que salva é um fato que uma ESCRITA produziu um dia antes
        desta fatia existir: o delete carimba ``to_deleted_at`` nas arestas de
        ENTRADA e as mantém. Carimbo posterior a T ⇒ o alvo estava vivo em T.

        E o que continua desconhecido continua dito: o CONTEÚDO do alvo naquele
        instante não é legível, então ele entra em ``as_of_truncated``.

        ⚠️ ``to_deleted_at`` na linha ``as_of`` continua ``None``, e isso não é
        contradição: um delete registrado DEPOIS de T não faz parte do que o
        store acreditava em T. Carimbá-lo ali misturaria dois instantes numa
        linha só — que é exatamente o que o i-131 criou o campo para impedir."""
        kernel, _ = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"))
        instante = _mark()
        await asyncio.sleep(0.01)
        await kernel.delete_instance(SCOPE, "Feature", "f-y")

        vivo = await kernel.graph_refs(SCOPE, "Story", "s-x", direction="out")
        assert vivo.edges[0]["to_deleted_at"] is not None
        assert vivo.edges[0]["resolved"] is False

        hist = await kernel.graph_refs(
            SCOPE, "Story", "s-x", direction="out", as_of=instante)
        assert hist.edges[0]["to_deleted_at"] is None
        assert hist.edges[0]["resolved"] is True, (
            "em T o alvo estava vivo; dizer 'resolved: false' seria contar ao "
            "passado uma notícia do futuro"
        )
        assert hist.edges[0]["to_kind"] == "Feature"
        assert hist.as_of_truncated == ["Feature/f-y"], (
            "o resgate provou que o alvo EXISTIA e não que ele é legível — "
            "omitir o nome aqui venderia como conhecida uma cegueira que não é"
        )
        # ⚠️ E o que NÃO se sabe fica ``None``, em vez de ser preenchido com o
        # que o registro diz hoje: um id do presente numa linha do passado é o
        # mesmo carimbo trocado, num campo em que ninguém iria conferir.
        assert hist.edges[0]["to_id"] is None
        assert hist.edges[0]["to_api_version"] is None


# ── 5. A INSTRUMENTAÇÃO não pode disparar o gatilho errado ─────────────────


class TestOEixoNaoContaminaOGatilho:
    """⚠️ Uma travessia ``as_of`` re-deriva e é N+1 POR CONSTRUÇÃO — mais lenta
    que a CTE por desenho, não por escala.

    Se as duas caírem no mesmo `p95`, o gatilho 2 dispara por causa de uma
    feature que acabamos de enviar, e alguém migra a topologia inteira lendo o
    número errado. Isto não é zelo: é o mesmo defeito que o campo ``producer``
    já preveniu uma vez — um número honesto respondendo a pergunta errada.
    """

    def test_a_linha_diz_de_qual_eixo_ela_e(self):
        from dna.kernel.query import graph as g

        linhas = [
            g.TRAVERSAL_MARK + '{"axis":"live","depth":3,"ms":10.0,"stop":"complete"}',
            g.TRAVERSAL_MARK + '{"axis":"as_of","depth":3,"ms":9000.0,"stop":"complete"}',
        ]
        stats = g.traversal_stats(linhas)
        assert stats["calls"] == 1, "a as_of foi somada às vivas"
        assert stats["as_of"]["calls"] == 1
        assert stats["as_of"]["counts_toward_trigger"] is False
        assert stats["triggers"]["scale_p95"]["fired"] is False, (
            "9 segundos de uma travessia HISTÓRICA acabaram de mandar migrar "
            "a topologia — o gatilho leu o número de outra pergunta"
        )
        assert stats["as_of"]["deep"]["p95_ms"] == 9000.0

    def test_uma_linha_SEM_axis_conta_como_viva(self):
        """As linhas emitidas antes do campo existir são vivas — elas eram. O
        default mora no LEITOR porque é ele que encontra as linhas velhas."""
        from dna.kernel.query import graph as g

        stats = g.traversal_stats([
            g.TRAVERSAL_MARK + '{"depth":3,"ms":600.0,"stop":"complete"}',
        ])
        assert stats["calls"] == 1
        assert stats["triggers"]["scale_p95"]["fired"] is True


# ── 6. O primitivo do adapter, direto ──────────────────────────────────────


class TestLoadKindAsOf:
    @pytest.mark.anyio
    async def test_devolve_a_versao_daquele_instante_e_nao_a_ultima(self, store):
        kernel, src = store
        await kernel.write_instance(
            SCOPE, "Feature", "f-y", _doc("Feature", "f-y", description="um"))
        instante = _mark()
        await asyncio.sleep(0.01)
        await kernel.write_instance(
            SCOPE, "Feature", "f-y", _doc("Feature", "f-y", description="dois"))
        payload = await src.load_kind_as_of(
            SCOPE, "Feature", as_of=instante, api_version=_SDLC_API)
        assert [i["name"] for i in payload["instances"]] == ["f-y"]
        assert payload["instances"][0]["version"] == 1
        assert payload["instances"][0]["raw"]["spec"]["description"] == "um"

    @pytest.mark.anyio
    async def test_uma_instancia_nascida_DEPOIS_nao_aparece(self, store):
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        instante = _mark()
        await asyncio.sleep(0.01)
        await kernel.write_instance(SCOPE, "Feature", "f-z", _doc("Feature", "f-z"))
        payload = await src.load_kind_as_of(
            SCOPE, "Feature", as_of=instante, api_version=_SDLC_API)
        assert sorted(i["name"] for i in payload["instances"]) == ["f-y"]
        assert payload["truncated"] == [], (
            "'ainda não existia' não é 'a história foi podada' — o segundo é "
            "uma cegueira e o primeiro é uma resposta"
        )

    @pytest.mark.anyio
    async def test_a_janela_ranqueia_por_versao_e_nao_le_o_historico_inteiro(
        self, store,
    ):
        """``row_number()`` numa janela, não um ``max(version)`` correlacionado:
        uma instância reescrita 195 vezes (a campeã de churn no banco do
        dna-cloud) teria os 195 envelopes lidos do store para guardar um.

        Medido pelo comportamento, que é o que sobrevive a uma reescrita da
        query: 40 versões, uma linha de volta, e a linha certa."""
        kernel, src = store
        for i in range(40):
            await kernel.write_instance(
                SCOPE, "Feature", "f-y",
                _doc("Feature", "f-y", description=f"v{i}"))
        payload = await src.load_kind_as_of(
            SCOPE, "Feature", as_of=_later(), api_version=_SDLC_API)
        assert len(payload["instances"]) == 1
        assert payload["instances"][0]["version"] == 40


# ── 7. O escopo herdado — os 9% que um pin de escopo quebraria ─────────────


class TestOEscopoHerdado:
    @pytest.mark.anyio
    async def test_uma_referencia_que_resolve_no_PAI_nao_vira_dangling(
        self, store,
    ):
        """Medido: 3 das 33 arestas do banco do dna-cloud (9%) resolveram pelo
        escopo pai. ``load_one_as_of`` fixa UM escopo, ao contrário de
        ``get_instance`` — então uma leitura histórica sem a cadeia diria
        ``resolved: false`` sobre uma relação que estava perfeita.

        A cadeia vem do kernel (``_graph_scope_chain``), derivada dos MESMOS
        dois lugares que a leitura viva consulta, para não haver uma segunda
        regra de herança ao lado da primeira."""
        kernel, _ = store
        pai = kernel._INHERIT_PARENT_SCOPE
        # ``ADR.supersedes → ADR``, e ADR É herdável (``Feature`` não é — a
        # primeira versão deste teste usou Feature e ficou verde nos dois lados
        # por não exercitar herança nenhuma).
        await kernel.write_instance(
            pai, "ADR", "adr-pai", _doc("ADR", "adr-pai"))
        await kernel.write_instance(
            SCOPE, "ADR", "adr-x", _doc("ADR", "adr-x", supersedes=["adr-pai"]))
        instante = _later()

        vivo = await kernel.graph_refs(SCOPE, "ADR", "adr-x", direction="out")
        hist = await kernel.graph_refs(
            SCOPE, "ADR", "adr-x", direction="out", as_of=instante)
        assert [e["resolved"] for e in vivo.edges] == [True]
        assert [e["resolved"] for e in hist.edges] == [True], (
            "a leitura histórica perdeu a cadeia de escopos e acusou de "
            "dangling uma referência que resolveu no pai"
        )
        assert {_key(e) for e in hist.edges} == {_key(e) for e in vivo.edges}
