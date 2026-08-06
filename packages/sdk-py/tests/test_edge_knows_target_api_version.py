"""i-110.3 — ``dna_edges.to_api_version``, e a catraca que a mantém suficiente.

**Fatia 1 de ``spec-topologia-do-grafo``.** A aresta sabia de que apiVersion
ela SAI (``from_api_version``, na chave primária desde a 0006) e não sabia para
qual ela ENTRA. Isso funcionava por uma razão que não estava escrita na tabela:
``dna.kernel.kinds.registry`` recusa registrar dois Kinds com o MESMO nome sob
apiVersions diferentes (i-195). A integridade do grafo dependia, calada, de uma
invariante de OUTRO módulo — que tem uma lista de exceções
(``KIND_NAME_COLLISION_ALLOWLIST``) com uma entrada.

Este arquivo prova as duas metades da fatia:

1. **a coluna** — o produtor a preenche com a apiVersion do documento que
   CASOU, a revisão 0009 a preenche retroativamente pelo ``to_id``, a travessia
   a lê, e o salto multi-hop passa a casar por ela;
2. **a catraca** — a guarda que fica VERMELHA no dia em que dois Kinds
   passarem a dividir um nome, dizendo por quê. Porque a tolerância a NULL
   (``_same_api_family``) é o que impede a fatia de apagar arestas antigas, e o
   preço dessa tolerância é que toda linha ainda NULL volta a ser ambígua
   naquele dia.

⚠️ **A catraca é DERIVADA, não enumerada.** Ela não pergunta "a lista está do
tamanho que eu escrevi?" — ela pergunta ao registry VIVO *quais nomes de Kind
são servidos por mais de uma apiVersion* e exige que esse conjunto esteja
vazio. Um Kind homônimo que entrasse pelo funil declarativo per-scope (que
permite colisão por desenho) deixa a lista intacta e esta guarda vermelha; a
versão enumerada não veria isso.

⚠️ **Achado desta fatia, medido em 06/08/2026:** a única entrada do allowlist
está SEM USO — o registry booteado serve 84 portas e 84 nomes distintos, e
apenas uma ``Reference``. Ver
``test_a_permissao_do_allowlist_esta_hoje_SEM_USO``.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from dna.kernel import Kernel
from dna.kernel.kinds.registry import KIND_NAME_COLLISION_ALLOWLIST
from tests import _graph_store

CORE = "github.com/ruinosus/dna/v1"
SDLC = "github.com/ruinosus/dna/sdlc/v1"
OTHER = "example.test/v1"


# ===========================================================================
# 1. A CATRACA — o allowlist não pode crescer, e o motivo é ESTE
# ===========================================================================


@pytest.fixture(scope="module")
def booted() -> Kernel:
    return Kernel.auto()


def _names_shared_by_two_api_versions(kernel: Kernel) -> dict[str, set[str]]:
    """Todo nome de Kind que o registry VIVO serve sob mais de uma apiVersion.

    Derivado de ``kind_ports()`` — o mesmo lugar de onde qualquer leitura por
    nome nu sai. Uma lista escrita à mão aqui responderia "a lista mudou?", que
    não é a pergunta; a pergunta é "o REGISTRY tem homônimos?", e as duas só
    coincidem enquanto ninguém entra por outro funil.
    """
    by_name: dict[str, set[str]] = defaultdict(set)
    for port in kernel.kind_ports():
        name = getattr(port, "kind", None)
        api = getattr(port, "api_version", None)
        if isinstance(name, str) and isinstance(api, str):
            by_name[name].add(api)
    return {n: v for n, v in by_name.items() if len(v) > 1}


def test_o_catalogo_nao_esta_vazio_por_acidente(booted: Kernel):
    """Guarda da guarda: as duas asserções abaixo são sobre um conjunto
    DERIVADO de ``kind_ports()``, e um registry vazio as satisfaz todas."""
    assert len(booted.kind_ports()) >= 76


def test_nenhum_nome_de_kind_e_servido_por_duas_apiversions(booted: Kernel):
    """⭐ A CATRACA da fatia 1 de ``spec-topologia-do-grafo`` (i-110.3).

    **A asserção é ``== {}``, não ``<= allowlist``, e isso foi MEDIDO, não
    escolhido.** Um kernel booteado hoje serve 84 portas e 84 nomes distintos:
    ZERO homônimos. O allowlist PERMITE ``Reference``, mas a segunda
    ``Reference`` não existe mais — a extensão ``research`` diz por escrito que
    reusa a do ``sdlc`` em vez de registrar a sua (ver
    ``test_a_permissao_do_allowlist_esta_hoje_SEM_USO``). Escrever
    ``<= allowlist`` aqui seria afrouxar a guarda para caber uma exceção que
    ninguém exerce.

    **O que ela vê mudar:** QUALQUER nome de Kind passando a ser servido por
    duas apiVersions — pelo allowlist, ou pelo funil declarativo per-scope, que
    permite colisão por desenho e não toca no allowlist. A igualdade literal
    sobre a lista (o teste seguinte, e o que já existe em
    ``test_kind_name_collision.py``) só vê o primeiro caminho.

    **Por que isso é problema DESTA tabela.** ``dna_edges.to_api_version`` trata
    NULL e ``''`` como "não sei" e deixa o salto passar — é o que impede a fatia
    de apagar toda aresta anterior à revisão 0009. O preço dessa tolerância é
    que cada linha ainda NULL é desambiguada por uma única coisa: ``to_kind``
    nomear apenas um Kind. No dia em que dois Kinds dividirem um nome, toda
    linha NULL volta a ser ambígua de uma vez, calada — e ninguém vai lembrar
    que a razão estava aqui. Está.

    **Se você chegou por causa desta falha:** a saída não é relaxar esta
    asserção. É (a) renomear o Kind novo, ou (b) preencher ``to_api_version``
    em TODA linha resolvida — e então reescrever este teste com esse fato na
    mão, não com a esperança dele.
    """
    colliding = _names_shared_by_two_api_versions(booted)
    assert colliding == {}, (
        "nome(s) de Kind servidos por DUAS apiVersions: "
        f"{ {k: sorted(v) for k, v in colliding.items()} } — cada aresta com "
        "to_api_version NULL apontando para esses nomes acabou de virar "
        "ambígua. Ver o docstring deste teste (i-110.3)."
    )


def test_o_allowlist_nao_cresceu():
    """A outra metade da catraca: a LISTA, e não o registry.

    Separada da anterior de propósito — esta vê a permissão aparecer mesmo que
    o Kind homônimo ainda não tenha sido escrito; aquela vê o Kind aparecer
    mesmo que a permissão não mude. Juntas não há porta.
    """
    assert KIND_NAME_COLLISION_ALLOWLIST == frozenset({"Reference"}), (
        "o allowlist mudou. Se CRESCEU, leia "
        "test_nenhum_nome_de_kind_e_servido_por_duas_apiversions: arestas com "
        "to_api_version NULL apontando para o nome novo ficam ambíguas. Se "
        "ENCOLHEU, ótimo — atualize este literal."
    )


def test_a_permissao_do_allowlist_esta_hoje_SEM_USO(booted: Kernel):
    """⚠️ Achado desta fatia, medido em 06/08/2026 — registrado como teste
    porque um achado que vira só comentário não sobrevive.

    O allowlist existe para permitir DUAS ``Reference``
    (``research/v1`` + ``sdlc/v1``, i-195). Hoje o kernel booteado registra
    **uma**: ``dna/extensions/research/__init__.py`` afirma explicitamente que
    *"we reuse the existing Kind, we do NOT register a second Reference here"*.
    A permissão está aberta e ninguém passa por ela.

    Isso é uma boa notícia para esta fatia — nenhuma aresta é ambígua hoje — e
    uma ponta para a i-195: esvaziar o allowlist é a sua história de
    seguimento, não esta. **Enquanto ele não for esvaziado, é a única porta por
    onde a ambiguidade pode voltar sem que nenhuma outra guarda perceba.**

    Este teste fica VERMELHO no dia em que uma segunda ``Reference`` voltar a
    ser registrada — que é exatamente o dia em que o teste acima também fica, e
    é a redundância que se quer: dois testes falhando dizem "isto foi previsto",
    um teste falhando diz "isto surpreendeu alguém".
    """
    refs = [p for p in booted.kind_ports() if getattr(p, "kind", None) == "Reference"]
    assert len(refs) == 1, (
        "voltou a haver mais de uma Reference registrada: "
        f"{sorted(p.api_version for p in refs)}"
    )
    assert refs[0].api_version == SDLC


# ===========================================================================
# 2. O PRODUTOR — a apiVersion gravada é a do documento que CASOU
# ===========================================================================


def _doc(api_version: str, kind: str, name: str, spec: dict | None = None) -> dict:
    return {
        "apiVersion": api_version, "kind": kind,
        "metadata": {"id": f"id-{name}", "name": name},
        "spec": spec or {},
    }


class _PortWithRelation:
    """Porta mínima que declara UMA relação resolvível, pelo caminho de
    verdade: ``relations_of`` lê ``port.relations`` e normaliza."""

    def __init__(self, kind: str, api_version: str, field: str,
                 to: tuple[str, ...]) -> None:
        self.kind = kind
        self.api_version = api_version
        self.relations = {field: {"to": list(to), "cardinality": "one"}}


@pytest.mark.asyncio
async def test_o_produtor_grava_a_apiversion_do_ALVO_nao_a_de_quem_escreve():
    """⭐ MUTANTE PLANTADO: trocar ``_api_version_of(matched_doc)`` por
    ``port.api_version`` (a de quem escreve) — que está em escopo, é plausível,
    e produziria um valor sempre presente e sempre errado quando as duas
    diferem. Este teste as faz diferirem de propósito.
    """
    from dna.kernel.query.references import resolve_relations

    target = _doc(OTHER, "Widget", "w-1")

    async def getter(scope, kind, name, tenant=None):
        return target if (kind, name) == ("Widget", "w-1") else None

    port = _PortWithRelation("Holder", CORE, "widget", ("Widget",))
    edges, problems, _discords, complete = await resolve_relations(
        port, {"spec": {"widget": "w-1"}},
        scope="s", name="h-1", tenant=None, getter=getter,
    )
    assert complete and not problems
    assert len(edges) == 1
    assert edges[0].to_api_version == OTHER
    assert edges[0].to_api_version != port.api_version, (
        "a aresta gravou a apiVersion de QUEM ESCREVE, não a do alvo"
    )


@pytest.mark.asyncio
async def test_aresta_pendurada_nao_inventa_apiversion():
    """Sem alvo não há apiVersion de alvo. ``None``, nunca ``''``, nunca a de
    quem escreve — MUTANTE: um ``or port.api_version`` como "default sensato"
    morre aqui."""
    from dna.kernel.query.references import resolve_relations

    async def getter(scope, kind, name, tenant=None):
        return None

    port = _PortWithRelation("Holder", CORE, "widget", ("Widget",))
    edges, problems, _d, complete = await resolve_relations(
        port, {"spec": {"widget": "fantasma"}},
        scope="s", name="h-1", tenant=None, getter=getter,
    )
    assert complete and len(problems) == 1
    assert edges[0].to_kind is None
    assert edges[0].to_api_version is None


@pytest.mark.asyncio
async def test_documento_sem_apiversion_le_como_ausente_nao_como_vazio():
    """O alvo existe mas não declara apiVersion: ``None``, e não ``''``.

    Um ``''`` gravado seria um SEGUNDO jeito de dizer "não sei" numa coluna que
    já tem NULL, e a travessia teria dois sentinelas para lembrar. MUTANTE:
    ``return value if isinstance(value, str) else None`` (sem o ``.strip()``)
    morre aqui.
    """
    from dna.kernel.query.references import resolve_relations

    target = {"kind": "Widget", "metadata": {"name": "w-1"}, "spec": {}}

    async def getter(scope, kind, name, tenant=None):
        return target

    port = _PortWithRelation("Holder", CORE, "widget", ("Widget",))
    edges, _p, _d, _c = await resolve_relations(
        port, {"spec": {"widget": "w-1"}},
        scope="s", name="h-1", tenant=None, getter=getter,
    )
    assert edges[0].to_kind == "Widget"
    assert edges[0].to_api_version is None


# ===========================================================================
# 3. ATRAVÉS DA PORTA — do write até a linha, e do banco até a face
# ===========================================================================


@pytest.fixture(autouse=True)
def _write_modes(monkeypatch):
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def kernel_store(request):
    """Kernel de verdade sobre store de verdade, nos dois dialetos."""
    src, cleanup = await _graph_store.build_store(request.param, "toapiv")
    kernel = Kernel.auto()
    kernel.source(src)
    try:
        yield kernel, src
    finally:
        await cleanup()


@pytest.mark.anyio
async def test_uma_escrita_de_verdade_deixa_a_apiversion_do_alvo_na_linha(
    kernel_store,
):
    """⭐ A PORTA. ``kernel.write_instance`` de uma ``Story`` apontando para uma
    ``Feature`` tem de deixar ``to_api_version`` gravado na linha.

    Esta casa já pagou por "guarda existe, porta não chama" e por "capacidade
    existe, porta não": o campo no dataclass, a coluna no schema e a cláusula no
    adapter podem estar todos certos e o CAMINHO DE ESCRITA não os ligar. As
    unidades acima usam porta falsa; esta usa o kernel inteiro, os Kinds
    registrados de verdade e uma relação declarada de verdade
    (``Story.feature → Feature``).

    **MUTANTE:** qualquer elo cortado entre ``resolve_relations`` e o INSERT
    (o kwarg ``edges=``, o ``getattr`` do ``_replace_edges``, o campo do
    dataclass) deixa a coluna NULL e este teste vermelho.
    """
    kernel, src = kernel_store
    scope = "porta-i1103"
    await kernel.write_instance(
        scope, "Feature", "f-y",
        {"apiVersion": SDLC, "kind": "Feature", "metadata": {"name": "f-y"},
         "spec": {"description": "d", "status": "todo"}},
    )
    await kernel.write_instance(
        scope, "Story", "s-x",
        {"apiVersion": SDLC, "kind": "Story", "metadata": {"name": "s-x"},
         "spec": {"description": "d", "status": "todo", "feature": "f-y"}},
    )
    async with src._engine.connect() as conn:
        rows = (await conn.execute(
            sa.select(src.edges).where(src.edges.c.from_kind == "Story")
        )).all()
    assert len(rows) == 1, rows
    row = dict(rows[0]._mapping)
    assert row["to_kind"] == "Feature"
    assert row["to_api_version"] == SDLC, (
        "o produtor não gravou a apiVersion do alvo — a coluna existe e o "
        "caminho de escrita não a alcança"
    )


@dataclass
class _E:
    """O bastante de um ``ResolvedEdge`` para o adapter gravar."""

    field: str
    ordinal: int
    value: str
    to_kind: str | None
    to_scope: str | None
    declared: tuple[str, ...]
    to_id: str | None = None
    to_api_version: str | None = None


async def _sqlite_source(tmp_path, tag: str):
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / f'{tag}.db'}")
    await src.connect()
    return src, src.close


async def _postgres_source(_tmp_path, tag: str):
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set")
    if "+asyncpg" not in dsn:
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    schema = f"dna_i1103_{tag}_{os.getpid()}"
    setup = create_async_engine(dsn)
    async with setup.begin() as conn:
        await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
    await setup.dispose()
    src = SqlAlchemySource(dsn, schema=schema)
    await src.connect()

    async def cleanup() -> None:
        await src.close()
        teardown = create_async_engine(dsn)
        async with teardown.begin() as conn:
            await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await teardown.dispose()

    return src, cleanup


@pytest.fixture(params=[
    pytest.param(_sqlite_source, id="sqlite"),
    pytest.param(_postgres_source, id="postgres",
                 marks=pytest.mark.requires_postgres),
])
def source_factory(request, tmp_path):
    async def build(tag: str):
        return await request.param(tmp_path, tag)

    return build


@pytest.mark.asyncio
async def test_a_coluna_atravessa_o_adapter_de_ponta_a_ponta(source_factory):
    """Grava uma aresta com ``to_api_version`` e lê de volta pela travessia.

    ⚠️ Este é o teste que a regra "guard existe, porta não chama" exige: o
    campo no dataclass e a coluna no schema podem ambos estar certos e o
    adapter, no meio, não gravar nem selecionar nada. **MUTANTE:** apagar
    ``"to_api_version": getattr(edge, ...)`` do ``_replace_edges`` — ou
    ``e.c.to_api_version`` da lista ``cols`` — morre aqui, nos dois dialetos.
    """
    src, cleanup = await source_factory("door")
    try:
        await src.replace_edges(
            "s", "Holder", "h-1",
            [_E("widget", 0, "w-1", "Widget", "s", ("Widget",),
                to_id="id-w-1", to_api_version=OTHER)],
            api_version=CORE,
        )
        rows = await src.traverse_edges("s", "Holder", "h-1", direction="out")
        assert len(rows) == 1
        assert rows[0]["to_api_version"] == OTHER
        assert rows[0]["from_api_version"] == CORE
        assert rows[0]["to_id"] == "id-w-1"
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_o_salto_multihop_fica_dentro_da_familia(source_factory):
    """⭐ O CORAÇÃO DA FATIA, e o mutante mais valioso.

    Duas famílias homônimas: ``Widget`` sob ``example.test/v1`` e ``Widget`` sob
    ``github.com/ruinosus/dna/v1``, ambas com uma instância chamada ``w``.
    ``Holder/h`` aponta para a de ``example.test/v1``. Cada ``Widget/w`` aponta
    para um ``Leaf`` diferente.

    Uma travessia ``depth=2`` a partir de ``Holder/h`` tem de alcançar
    ``leaf-other`` e NÃO ``leaf-core``.

    **MUTANTE:** remover ``_same_api_family(...)`` do ``join`` do passo
    recursivo — o salto volta a casar por ``(kind, name)``, a travessia atravessa
    para a outra família e este teste fica vermelho com ``leaf-core`` na lista.
    É exatamente o defeito que a guarda da i-195 vinha escondendo de graça.
    """
    src, cleanup = await source_factory("family")
    try:
        await src.replace_edges(
            "s", "Holder", "h",
            [_E("widget", 0, "w", "Widget", "s", ("Widget",),
                to_api_version=OTHER)],
            api_version=CORE,
        )
        # As duas famílias homônimas, cada uma com a SUA folha.
        await src.replace_edges(
            "s", "Widget", "w",
            [_E("leaf", 0, "leaf-other", "Leaf", "s", ("Leaf",),
                to_api_version=CORE)],
            api_version=OTHER,
        )
        await src.replace_edges(
            "s", "Widget", "w",
            [_E("leaf", 0, "leaf-core", "Leaf", "s", ("Leaf",),
                to_api_version=CORE)],
            api_version=CORE,
        )

        rows = await src.traverse_edges(
            "s", "Holder", "h", direction="out", depth=2,
        )
        reached = sorted(r["to_name"] for r in rows)
        assert reached == ["leaf-other", "w"], (
            f"a travessia saiu da família: {reached}"
        )
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_uma_apiversion_desconhecida_nao_corta_o_salto(source_factory):
    """A tolerância, e ela é o que torna a fatia segura para dado antigo.

    Uma linha anterior à revisão 0009 (ou pendurada) tem ``to_api_version``
    NULL; uma linha escrita por um chamador que não passou ``api_version=`` tem
    ``from_api_version`` ``''``. Nos dois casos o salto TEM de continuar
    acontecendo — a fatia não pode apagar aresta.

    **MUTANTE:** trocar ``_same_api_family(a, b)`` por ``a == b`` — os dois
    saltos abaixo somem e este teste fica vermelho. É a diferença entre apertar
    o join e perder metade do grafo.
    """
    src, cleanup = await source_factory("tolerant")
    try:
        # 1. o lado TO não sabe (linha pré-0009)
        await src.replace_edges(
            "s", "Holder", "h",
            [_E("widget", 0, "w", "Widget", "s", ("Widget",),
                to_api_version=None)],
            api_version=CORE,
        )
        # 2. o lado FROM não sabe (escrita sem api_version= → '')
        await src.replace_edges(
            "s", "Widget", "w",
            [_E("leaf", 0, "leaf-1", "Leaf", "s", ("Leaf",),
                to_api_version=CORE)],
        )
        rows = await src.traverse_edges(
            "s", "Holder", "h", direction="out", depth=2,
        )
        assert sorted(r["to_name"] for r in rows) == ["leaf-1", "w"]
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_a_travessia_reversa_tambem_casa_por_apiversion(source_factory):
    """A direção ``in`` é o join ESPELHADO — e um espelho é onde uma condição
    nova é esquecida.

    ⚠️ **Este teste começou passando pelo motivo errado**, e o mutante o
    pegou. A primeira versão montava duas famílias de ``Widget`` e checava
    quais ``Holder`` chegavam — mas os dois Holders chegavam com o join solto
    OU com o apertado, porque ambos apontavam para um ``Widget/w`` que existia
    nas duas famílias. A asserção era sobre um conjunto que a mudança não
    alterava, exatamente a família de defeito que esta casa já catalogou como
    "guarda cega e verde". A montagem abaixo é a corrigida: existe UM
    ``Widget/w`` produzindo arestas (família ``example.test/v1``), e dois
    ``Holder`` apontando para ``Widget/w`` — um declarando a família certa, o
    outro declarando a outra. Só o primeiro pode ser alcançado.

    **MUTANTE:** aplicar ``_same_api_family`` só no ramo ``outward``, ou não
    espelhar ``ea_anchor_apiv``/``walk_node_apiv`` — ``h-core`` aparece na
    resposta e este teste morre.
    """
    src, cleanup = await source_factory("reverse")
    try:
        #   Holder/h-other --widget[→ Widget @OTHER]--> Widget/w @OTHER --> Leaf/l
        #   Holder/h-core  --widget[→ Widget @CORE ]--> (um Widget/w que não
        #                                                aponta para Leaf/l)
        await src.replace_edges(
            "s", "Widget", "w",
            [_E("leaf", 0, "l", "Leaf", "s", ("Leaf",), to_api_version=CORE)],
            api_version=OTHER,
        )
        await src.replace_edges(
            "s", "Holder", "h-other",
            [_E("widget", 0, "w", "Widget", "s", ("Widget",),
                to_api_version=OTHER)],
            api_version=CORE,
        )
        await src.replace_edges(
            "s", "Holder", "h-core",
            [_E("widget", 0, "w", "Widget", "s", ("Widget",),
                to_api_version=CORE)],
            api_version=CORE,
        )

        rows = await src.traverse_edges(
            "s", "Leaf", "l", direction="in", depth=2,
        )
        holders = sorted(
            r["from_name"] for r in rows if r["from_kind"] == "Holder"
        )
        assert holders == ["h-other"], (
            f"a travessia reversa saiu da família: {holders}"
        )
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_duas_familias_homonimas_nao_se_engolem_na_deduplicacao(
    source_factory,
):
    """A chave de deduplicação da travessia inclui ``from_api_version``.

    A tabela permite as duas linhas (``from_api_version`` está na PK); o
    dicionário que colapsa caminhos em arestas, não. **MUTANTE:** remover
    ``r.from_api_version`` da tupla ``key`` — uma das duas famílias desaparece
    da resposta em silêncio e este teste fica vermelho.
    """
    src, cleanup = await source_factory("dedup")
    try:
        await src.replace_edges(
            "s", "Widget", "w",
            [_E("leaf", 0, "l", "Leaf", "s", ("Leaf",), to_api_version=CORE)],
            api_version=OTHER,
        )
        await src.replace_edges(
            "s", "Widget", "w",
            [_E("leaf", 0, "l", "Leaf", "s", ("Leaf",), to_api_version=CORE)],
            api_version=CORE,
        )
        rows = await src.traverse_edges("s", "Leaf", "l", direction="in")
        assert sorted(r["from_api_version"] for r in rows) == sorted([CORE, OTHER])
    finally:
        await cleanup()


# ===========================================================================
# 4. A REVISÃO 0009 — o backfill contra um banco de verdade, nos dois dialetos
# ===========================================================================


PREVIOUS_REVISION = "0008_instance_id"
THIS_REVISION = "0009_edge_to_api_version"


class _Db:
    def __init__(self, engine, schema: str | None) -> None:
        self.engine = engine
        self.schema = schema
        self.is_pg = engine.dialect.name == "postgresql"
        self.prefix = "dna_" if self.is_pg else ""

    def table(self, name: str) -> str:
        base = f"{self.prefix}{name}"
        return f"{self.schema}.{base}" if self.schema else base

    async def exec(self, stmt: str, params: dict | None = None) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(sa.text(stmt), params or {})

    async def rows(self, stmt: str, params: dict | None = None) -> list:
        async with self.engine.connect() as conn:
            return (await conn.execute(sa.text(stmt), params or {})).all()

    async def alembic(self, revision: str) -> None:
        from alembic import command

        from dna.adapters.sqlalchemy_.migrate import build_config

        schema = self.schema

        def _run(sync_conn):
            command.upgrade(build_config(schema, connection=sync_conn), revision)

        async with self.engine.begin() as conn:
            await conn.run_sync(_run)


async def _sqlite_db(tmp_path) -> tuple[_Db, Any]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'm9.db'}")
    db = _Db(engine, None)
    await db.alembic(PREVIOUS_REVISION)
    return db, engine.dispose


async def _postgres_db(_tmp_path) -> tuple[_Db, Any]:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping Postgres dialect")
    url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    schema = f"dna_i1103m_{os.getpid()}_{id(asyncio):x}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
    db = _Db(engine, schema)
    await db.alembic(PREVIOUS_REVISION)

    async def cleanup() -> None:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()

    return db, cleanup


@pytest.fixture(params=[
    pytest.param(_sqlite_db, id="sqlite"),
    pytest.param(_postgres_db, id="postgres",
                 marks=pytest.mark.requires_postgres),
])
def db_factory(request, tmp_path):
    async def build() -> tuple[_Db, Any]:
        return await request.param(tmp_path)

    return build


#: (scope, kind, api_version, name, id) — as instâncias-alvo.
_INSTANCES = [
    ("acme", "Feature", SDLC, "f-alpha", "idfa"),
    ("acme", "Copilot", CORE, "c-um", "idcu"),
    # ⭐ O PAR HOMÔNIMO — o caso que esta coluna existe para resolver, e o
    # único que separa o join por ``id`` do join pela chave natural. A PK de
    # ``dna_instances`` inclui ``api_version``, então estas DUAS linhas
    # coexistem legalmente e ``(scope, kind, name)`` não as distingue.
    ("acme", "Reference", SDLC, "r-1", "idr-sdlc"),
    ("acme", "Reference", OTHER, "r-1", "idr-other"),
    # O alvo HERDADO: vive noutro scope, e a aresta que aponta para ele tem
    # ``to_scope`` NULL — a 0008 não o alcançou e esta também não deve.
    ("shared", "Copilot", CORE, "herdado", "idherd"),
]

#: (from_kind, from_api_version, from_name, field, to_kind, to_name, to_id)
#: — a forma medida da base de desenvolvimento: resolvidas com ``to_id``,
#: uma pendurada, e uma resolvida cujo ``to_id`` a 0008 não alcançou.
_EDGES = [
    ("Story", SDLC, "s-1", "feature", "Feature", "f-alpha", "idfa"),
    ("Story", SDLC, "s-2", "feature", "Feature", "f-alpha", "idfa"),
    ("App", CORE, "a-1", "copilots", "Copilot", "c-um", "idcu"),
    # ⭐ aponta para UMA das duas ``Reference/r-1`` — a do sdlc. Só o ``to_id``
    # sabe qual; a chave natural casa as duas.
    ("Cite", SDLC, "c-1", "ref", "Reference", "r-1", "idr-sdlc"),
    # pendurada: sem to_kind, sem to_id
    ("App", CORE, "a-2", "copilots", None, "fantasma", None),
    # resolvida por herança de scope: to_kind sim, to_id não (o caso real)
    ("App", CORE, "a-3", "copilots", "Copilot", "herdado", None),
]


async def _seed(db: _Db) -> None:
    insts = db.table("instances")
    for scope, kind, api, name, iid in _INSTANCES:
        await db.exec(
            f"INSERT INTO {insts} (scope, kind, api_version, name, id, content,"
            f" version, updated_at, tenant) VALUES (:s, :k, :a, :n, :i, :c, 1,"
            f" '2026-08-06T00:00:00Z', :t)",
            {"s": scope, "k": kind, "a": api, "n": name, "i": iid,
             "c": json.dumps({"apiVersion": api, "kind": kind,
                              "metadata": {"id": iid, "name": name},
                              "spec": {}}),
             "t": "" if db.is_pg else None},
        )
    edges = db.table("edges")
    for fk, fa, fn, field, tk, tn, tid in _EDGES:
        await db.exec(
            f"INSERT INTO {edges} (scope, tenant, from_api_version, from_kind,"
            f" from_name, source_field, ordinal, to_scope, to_kind, to_name,"
            f" to_id, declared_to, from_version, updated_at)"
            f" VALUES (:s, '', :fa, :fk, :fn, :f, 0, 'acme', :tk, :tn, :ti,"
            f" '', 1, :u)",
            {"s": "acme", "fa": fa, "fk": fk, "fn": fn, "f": field,
             "tk": tk, "tn": tn, "ti": tid,
             # [dialect] ``dna_edges.updated_at`` é TIMESTAMPTZ no pg e TEXT no
             # sqlite (schema.py) — o asyncpg recusa a string.
             "u": (datetime(2026, 8, 6, tzinfo=timezone.utc) if db.is_pg
                   else "2026-08-06T00:00:00Z")},
        )


async def _to_api_versions(db: _Db) -> dict[str, str | None]:
    rows = await db.rows(
        f"SELECT from_name, to_api_version FROM {db.table('edges')}"
    )
    return {r[0]: r[1] for r in rows}


@pytest.mark.asyncio
async def test_0009_preenche_exatamente_as_arestas_que_a_0008_identificou(
    db_factory,
):
    """Os DOIS números da fatia, provados contra um banco real, nos dois
    dialetos.

    Seis arestas: quatro com ``to_id`` (uma delas apontando para UMA de duas
    ``Reference/r-1`` homônimas), uma pendurada, e uma resolvida cujo alvo mora
    num scope pai — o caso medido na base do founder. Depois da 0009:
    **quatro preenchidas, duas NULL**.

    **MUTANTE 1 (o principal):** copiar o join da 0008 — casar por
    ``scope``/``to_kind``/``to_name`` em vez de por ``to_id``. A chave natural
    casa as DUAS ``Reference/r-1``, e ``c-1`` recebe a apiVersion errada (ou,
    com o ``COUNT(*) = 1`` da 0008, nenhuma). Vermelho nos dois casos, e é a
    razão inteira pela qual esta revisão não reusou aquele SQL.

    **MUTANTE 2:** preencher a pendurada ou a herdada com ``from_api_version``
    — vermelho, porque o teste exige NULL nos dois. "Não sei" e "chutei" têm de
    ser distinguíveis na coluna.
    """
    db, cleanup = await db_factory()
    try:
        await _seed(db)
        await db.alembic(THIS_REVISION)

        got = await _to_api_versions(db)
        assert got == {
            "s-1": SDLC,     # → Feature (sdlc/v1), via to_id
            "s-2": SDLC,
            "a-1": CORE,     # → Copilot (dna/v1), via to_id
            "c-1": SDLC,     # ⭐ a Reference CERTA das duas homônimas
            "a-2": None,     # pendurada
            "a-3": None,     # herdada de outro scope, sem to_id: não SEI
        }
        preenchidas = sum(1 for v in got.values() if v is not None)
        assert (preenchidas, len(got) - preenchidas) == (4, 2)
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_0009_e_idempotente_e_nao_apaga_o_que_o_produtor_carimbou(
    db_factory,
):
    """Rodar de novo é inócuo — e a segunda rodada não pode REGREDIR.

    O caso perigoso: uma aresta que o produtor vivo carimbou com
    ``to_api_version`` e cujo ``to_id`` depois virou pendurado (o alvo foi
    apagado). Um ``UPDATE ... SET x = (subselect)`` sem o ``WHERE EXISTS``
    escreve NULL por cima — apagando um fato correto.

    **MUTANTE:** remover ``AND EXISTS (SELECT 1 ...)`` do backfill — vermelho
    aqui, e verde em tudo o mais, que é o que faz este teste valer.
    """
    db, cleanup = await db_factory()
    try:
        await _seed(db)
        await db.alembic(THIS_REVISION)
        first = await _to_api_versions(db)

        # o produtor vivo carimba a pendurada... e o alvo some
        await db.exec(
            f"UPDATE {db.table('edges')} SET to_api_version = :v,"
            f" to_id = 'idsumiu' WHERE from_name = 'a-2'",
            {"v": OTHER},
        )

        await _rerun_backfill(db)

        again = await _to_api_versions(db)
        assert again["a-2"] == OTHER, (
            "a segunda passada apagou um valor que o produtor tinha gravado"
        )
        assert {k: v for k, v in again.items() if k != "a-2"} == {
            k: v for k, v in first.items() if k != "a-2"
        }
    finally:
        await cleanup()


def _revision_module():
    """A revisão 0009, carregada pelo caminho — o nome do arquivo começa com um
    dígito, então ``import`` não a alcança e o alembic a carrega assim também.

    ⚠️ Pelo ARQUIVO e não por uma cópia do SQL: um teste que reescrevesse o
    ``UPDATE`` estaria provando o seu próprio SQL, não o da migração, e as duas
    versões divergiriam no primeiro conserto.
    """
    import importlib.util
    from pathlib import Path

    import dna.adapters.sqlalchemy_ as pkg

    # ``…/alembic`` é um NAMESPACE package (sem ``__init__.py``), então
    # ``__file__`` é ``None`` — o caminho sai do pacote pai, que tem arquivo.
    path = (Path(pkg.__file__).parent / "alembic" / "versions"
            / "0009_aresta_sabe_a_versao_do_alvo.py")
    spec = importlib.util.spec_from_file_location("_rev0009", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _rerun_backfill(db: _Db) -> None:
    """Roda o backfill da revisão uma segunda vez, direto, sem alembic.

    O alembic recusaria (a revisão já está aplicada), e o que este teste
    pergunta é sobre o SQL, não sobre o versionamento.
    """
    rev = _revision_module()
    inst, edges = db.table("instances"), db.table("edges")

    def _run(sync_conn):
        rev._backfill_edge_api_versions(sync_conn, inst, edges)

    async with db.engine.begin() as conn:
        await conn.run_sync(_run)
