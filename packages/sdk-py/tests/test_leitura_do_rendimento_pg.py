"""A mesma amostra, contada em Python e agregada no Postgres — e elas TÊM de bater.

`Story/s-leitura-do-rendimento`. `sample_from_turns` (linhas na mão) e
`gather_sample` (``GROUP BY`` no banco) são dois produtores do MESMO
:class:`~dna.runtime.roi.Sample`, e a asserção central aqui é a PARIDADE entre
os dois — o mesmo desenho de `test_postgres_source_count`.

⭐ **Por que a paridade é o teste certo e não um extra.** As duas contagens
divergem exatamente nos casos que decidem esta story: um ``GROUP BY`` sobre
``tokens_partial`` cria grupos separados para ``true``/``false``/``NULL``, e
somar isso errado transformaria "uso ilegível" em "conta fechada". Da mesma
forma, um ``outcome`` fora do vocabulário tem de sair de LÁ contado como
desconhecido, exatamente como sai daqui — senão o banco contaria como desfecho
o que a leitura pura recusa, e a contenção subiria sozinha.

Requer um Postgres (``DATABASE_URL``).
"""
from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.asyncio(loop_scope="module"),
]

SCHEMA = "dna_test_rendimento"

# As linhas, com TODOS os casos que a leitura precisa distinguir num só lugar:
# desfecho declarado, desfecho ausente, desfecho INVENTADO, uso ilegível, uso
# desconhecido (pré-0012), e o turno que morreu sem chamar o modelo.
LINHAS = [
    dict(turn_id="t1", model="gpt-5-mini", input_tokens=1000, output_tokens=500,
         tokens_partial=False, outcome="resolved", workspace="w"),
    dict(turn_id="t2", model="gpt-5-mini", input_tokens=800, output_tokens=200,
         tokens_partial=False, outcome="resolved", workspace="w"),
    dict(turn_id="t3", model="gpt-5-mini", input_tokens=400, output_tokens=100,
         tokens_partial=False, outcome="escalated", workspace="w"),
    dict(turn_id="t4", model="gpt-5-mini", input_tokens=0, output_tokens=0,
         tokens_partial=True, outcome="", workspace="w"),
    dict(turn_id="t5", model="gpt-5-mini", input_tokens=200, output_tokens=50,
         tokens_partial=None, outcome="", workspace="w"),
    dict(turn_id="t6", model="", input_tokens=0, output_tokens=0,
         tokens_partial=False, outcome="", workspace="w"),
    # ⚠️ Um desfecho que NÃO existe no vocabulário. O banco não tem CHECK
    # (revisão 0012, de propósito), então ele CABE — e as duas contagens têm
    # de recusá-lo igual.
    dict(turn_id="t7", model="gpt-5-mini", input_tokens=10, output_tokens=5,
         tokens_partial=False, outcome="ok", workspace="w"),
    # De outro workspace: o filtro tem de deixá-lo de fora.
    dict(turn_id="t8", model="gpt-5-mini", input_tokens=9999, output_tokens=9999,
         tokens_partial=False, outcome="resolved", workspace="outro"),
]

#: ⭐ `i-158`: as raias, num WORKSPACE PRÓPRIO — e é de propósito.
#:
#: Misturá-las em ``w`` faria as asserções acima (``turns == 7``,
#: ``outcomes == {...}``) quebrarem por um motivo que nada tem a ver com o que
#: elas afirmam. Um lote separado mantém cada teste falhando só pelo que ele
#: mede, e a paridade abaixo cobre os dois lotes.
#:
#: Quatro casos, e o quarto é o que decide: uma raia INVENTADA cabe na coluna
#: (não há CHECK, revisão 0014, de propósito) e tem de sair contada como NÃO
#: DECLARADA nos dois caminhos — senão o banco criaria uma raia que a leitura
#: pura recusa.
LINHAS_DE_RAIA = [
    dict(turn_id="r1", model="gpt-5-mini", input_tokens=300, output_tokens=100,
         tokens_partial=False, outcome="resolved", workspace="raias", lane="real"),
    dict(turn_id="r2", model="gpt-5-mini", input_tokens=100, output_tokens=50,
         tokens_partial=False, outcome="", workspace="raias", lane="real"),
    dict(turn_id="r3", model="gpt-5-mini", input_tokens=7000, output_tokens=7000,
         tokens_partial=False, outcome="resolved", workspace="raias", lane="test"),
    dict(turn_id="r4", model="gpt-5-mini", input_tokens=1, output_tokens=1,
         tokens_partial=False, outcome="", workspace="raias", lane="prod"),
    # E o vazio explícito: o estado dos 86 turnos medidos em 08/08/2026, que é
    # o que o `DEFAULT ''` da 0014 produz. Escrito por extenso porque um
    # `executemany` exige as mesmas chaves em todo o lote.
    dict(turn_id="r5", model="gpt-5-mini", input_tokens=2, output_tokens=2,
         tokens_partial=False, outcome="", workspace="raias", lane=""),
]

# ⚠️ `arguments`/`edited_args` estão aqui porque a `i-151` os LÊ, e o caminho do
# banco é o único que pode divergir do puro: ele traz o par numa SEGUNDA
# consulta (um `GROUP BY` não compara dois JSON por caminho). A paridade é a
# asserção que impede as duas contagens de andarem para lados diferentes.
APROVACOES = [
    dict(approval_id="a1", tool="t", decision="approve", workspace="w",
         arguments='{"a": 1}', edited_args=""),
    dict(approval_id="a2", tool="t", decision="approve", workspace="w",
         arguments='{"a": 1}', edited_args=""),
    # O `edit` com REESCRITA — o único que produz magnitude.
    dict(approval_id="a3", tool="t", decision="edit", workspace="w",
         arguments='{"a": "proposto", "b": "igual", "rationale": "porque sim"}',
         edited_args='{"name": "t", "args": {"a": "REESCRITO", "b": "igual"}}'),
    dict(approval_id="a4", tool="t", decision="", workspace="w",
         arguments='{"a": 1}', edited_args=""),
    dict(approval_id="a5", tool="t", decision="approve", workspace="outro",
         arguments='{"a": 1}', edited_args=""),
    # O `edit` que só RECORTA — fora da magnitude, contado ao lado.
    dict(approval_id="a6", tool="t", decision="edit", workspace="w",
         arguments='{"a": 1, "b": 2}',
         edited_args='{"name": "t", "args": {"a": 1}}'),
    # ⚠️ O `edit` ILEGÍVEL: cabe na coluna (é TEXT, sem CHECK) e as duas
    # contagens têm de recusá-lo IGUAL — senão o banco contaria como comparação
    # o que a leitura pura conta como buraco.
    dict(approval_id="a7", tool="t", decision="edit", workspace="w",
         arguments="{isto não é json", edited_args="{}"),
    # E um `edit` de OUTRO workspace: o filtro tem de deixá-lo fora da
    # COMPARAÇÃO também, não só da contagem de decisões.
    dict(approval_id="a8", tool="t", decision="edit", workspace="outro",
         arguments='{"a": "x"}', edited_args='{"name": "t", "args": {"a": "y"}}'),
]


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def conexao():
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    from dna.adapters.sqlalchemy_.schema import build_metadata

    dsn = os.environ["DATABASE_URL"]
    url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)

    tables = build_metadata(is_pg=True, schema=SCHEMA)
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await conn.execute(sa.text(f"CREATE SCHEMA {SCHEMA}"))
        # Só as duas tabelas desta leitura — o resto do modelo não é o assunto.
        await conn.run_sync(
            tables.metadata.create_all,
            tables=[tables.turn, tables.turn_step, tables.approval],
        )
        await conn.execute(sa.insert(tables.turn), LINHAS)
        await conn.execute(sa.insert(tables.turn), LINHAS_DE_RAIA)
        await conn.execute(sa.insert(tables.approval), APROVACOES)

    async with engine.connect() as conn:
        yield conn, tables

    async with engine.begin() as conn:
        await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
    await engine.dispose()


async def test_a_agregacao_no_banco_bate_com_a_contagem_em_python(conexao):
    """⭐ A paridade. Divergir aqui é divergir nos casos que decidem a story."""
    from dna.runtime.roi import gather_sample, sample_from_turns

    conn, tables = conexao
    do_banco = await gather_sample(conn, tables, workspace="w")
    do_python = sample_from_turns(
        [l for l in LINHAS if l["workspace"] == "w"],
        [a for a in APROVACOES if a["workspace"] == "w"],
    )

    assert do_banco == do_python


async def test_a_agregacao_por_RAIA_no_banco_bate_com_a_de_python(conexao):
    """⭐ `i-158`: a paridade vale com a raia no `GROUP BY`, e vale FILTRADA.

    O caminho do banco ganhou uma quarta dimensão de agrupamento e um filtro
    aplicado DEPOIS da agregação. Se ele divergisse do puro, a exclusão de
    turnos de teste seria diferente conforme quem perguntou — e ninguém
    descobriria, porque os dois números são plausíveis.
    """
    from dna.runtime.roi import gather_sample, sample_from_turns

    conn, tables = conexao
    for filtro in (None, "real", "test", ""):
        do_banco = await gather_sample(
            conn, tables, workspace="raias", lane=filtro
        )
        do_python = sample_from_turns(LINHAS_DE_RAIA, lane=filtro)
        assert do_banco == do_python, f"divergiram com lane={filtro!r}"


async def test_uma_raia_INVENTADA_no_banco_conta_como_NAO_DECLARADA(conexao):
    """`lane = 'prod'` cabe na coluna (não há CHECK) e não pode virar raia."""
    from dna.runtime.roi import gather_sample

    conn, tables = conexao
    amostra = await gather_sample(conn, tables, workspace="raias")
    assert amostra.lanes == {"real": 2, "test": 1, "": 2}
    assert amostra.undeclared_lane == 2


async def test_o_banco_filtrado_pela_raia_real_AINDA_sabe_o_que_excluiu(conexao):
    """⭐ A regra 3 da issue, atravessando o Postgres.

    A restrição é feita em Python sobre um agregado já vindo por raia — nunca
    por um `WHERE`. Um `WHERE lane = 'real'` traria o número certo e apagaria
    a existência dos outros três turnos, e o painel não teria de onde dizer o
    que ficou de fora.
    """
    from dna.runtime.roi import gather_sample, read_yield

    conn, tables = conexao
    amostra = await gather_sample(conn, tables, workspace="raias", lane="real")
    assert amostra.turns == 2
    assert amostra.lanes_seen == 5
    assert amostra.excluded_turns == 3
    assert amostra.excluded_by_lane == {"test": 1, "": 2}
    # E os tokens do turno de teste (14.000) NÃO entram na conta.
    assert read_yield(amostra, copilot={}).tokens.value == 550


async def test_o_desfecho_INVENTADO_nao_e_contado_pelo_banco(conexao):
    """``outcome = 'ok'`` cabe na coluna (não há CHECK) e não pode virar
    desfecho — nem no caminho do banco."""
    from dna.runtime.roi import gather_sample

    conn, tables = conexao
    amostra = await gather_sample(conn, tables, workspace="w")
    assert amostra.outcomes == {"resolved": 2, "escalated": 1}
    assert amostra.turns == 7
    assert amostra.undeclared_outcomes == 4


async def test_o_GROUP_BY_por_tokens_partial_separa_os_DOIS_zeros(conexao):
    """`false`, `true` e `NULL` viram grupos distintos, e a soma tem de manter
    a distinção — senão "uso ilegível" some dentro de "conta fechada"."""
    from dna.runtime.roi import gather_sample

    conn, tables = conexao
    amostra = await gather_sample(conn, tables, workspace="w")
    assert amostra.unreadable_turns == 1
    assert amostra.unknown_usage_turns == 1
    assert amostra.usage_is_floor


async def test_a_leitura_inteira_roda_sobre_o_banco_e_recusa_o_que_falta(conexao):
    """A porta ATRAVESSADA: do Postgres à leitura, sem valor declarado."""
    from dna.runtime.roi import (
        NO_VALUE_PER_OUTCOME,
        NotCalculable,
        gather_sample,
        read_yield,
    )

    conn, tables = conexao
    r = read_yield(await gather_sample(conn, tables, workspace="w"), copilot={})
    assert isinstance(r.value, NotCalculable)
    assert r.value.reason == NO_VALUE_PER_OUTCOME
    assert not r.nothing_to_look_at


async def test_um_workspace_SEM_turnos_e_NAO_HA_O_QUE_OLHAR(conexao):
    """⭐ E vindo do banco também: vazio é achado, não resultado zero."""
    from dna.runtime.roi import NO_TURNS, NotCalculable, gather_sample, read_yield

    conn, tables = conexao
    amostra = await gather_sample(conn, tables, workspace="ninguem")
    assert amostra.turns == 0
    r = read_yield(amostra, copilot={})
    assert r.nothing_to_look_at
    assert isinstance(r.containment, NotCalculable)
    assert r.containment.reason == NO_TURNS


async def test_a_comparacao_de_edited_args_bate_nos_DOIS_caminhos(conexao):
    """⭐ `i-151`: a leitura do `edited_args` é o único ponto em que o caminho
    do banco NÃO é um `GROUP BY` — os pares viajam numa segunda consulta.

    É por isso que ele pode divergir do puro, e por isso a paridade tem de
    cobri-lo explicitamente: o `edit` ilegível e o de outro workspace são
    exatamente os casos em que uma das duas contagens erraria sozinha.
    """
    from dna.runtime.roi import gather_sample

    conn, tables = conexao
    amostra = await gather_sample(conn, tables, workspace="w")
    assert amostra.edits == 3
    assert amostra.edits_compared == 2      # o ilegível fica de fora
    assert amostra.edits_unreadable == 1
    d = amostra.edit_delta
    # a3: 1 reescrito + 1 intacto (`rationale` descontado) · a6: 1 intacto + 1
    # recortado. O `edit` de `outro` não entra em nenhuma das contagens.
    assert (d.changed, d.added, d.kept, d.removed) == (1, 0, 2, 1)
    assert d.ignored == 1 and d.unwrapped


async def test_o_grau_de_correcao_ATRAVESSA_a_porta_do_banco(conexao):
    """A porta inteira: do Postgres à linha da tela, com a ressalva colada."""
    from dna.runtime.roi import INCIDENTAL, Number, gather_sample, read_yield, render

    conn, tables = conexao
    r = read_yield(await gather_sample(conn, tables, workspace="w"), copilot={})
    assert isinstance(r.correction, Number)
    assert r.correction.basis == INCIDENTAL
    assert r.correction.value == pytest.approx(100.0 / 3)   # 1 de 3 folhas
    assert r.correction.is_small_sample
    linha = next(l for l in render(r) if l.startswith("Grau de correção:"))
    assert "AMOSTRA PEQUENA" in linha


async def test_o_dialeto_SEM_as_tabelas_LEVANTA_em_vez_de_devolver_vazio(conexao):
    """⚠️ Num SQLite ``tables.turn`` é ``None``. Devolver uma amostra vazia
    diria "nenhum turno"; o que houve foi "esta pergunta não se faz aqui"."""
    from dna.adapters.sqlalchemy_.schema import build_metadata
    from dna.runtime.roi import gather_sample

    conn, _ = conexao
    sqlite_tables = build_metadata(is_pg=False)
    assert sqlite_tables.turn is None
    with pytest.raises(RuntimeError, match="Postgres-only"):
        await gather_sample(conn, sqlite_tables)
