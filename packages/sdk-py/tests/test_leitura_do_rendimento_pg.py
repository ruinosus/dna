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

APROVACOES = [
    dict(approval_id="a1", tool="t", decision="approve", workspace="w"),
    dict(approval_id="a2", tool="t", decision="approve", workspace="w"),
    dict(approval_id="a3", tool="t", decision="edit", workspace="w"),
    dict(approval_id="a4", tool="t", decision="", workspace="w"),
    dict(approval_id="a5", tool="t", decision="approve", workspace="outro"),
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
