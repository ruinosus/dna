"""Revisão 0012 contra um banco que já tem turnos gravados.

⭐ **O que estes testes defendem é uma AUSÊNCIA**, e ausência é o que ninguém
lembra de testar: que a migração não presumiu nada sobre os turnos que já
existiam.

O backfill tentador — ``UPDATE dna_turn SET outcome = 'resolved' WHERE status =
'ok'`` — é uma linha de SQL, roda em milissegundos, e produziria uma taxa de
resolução de 89% sobre os 85 turnos medidos em 07/08/2026. Esse número mediria
a ausência de crashes e se apresentaria como medida de valor entregue, num
painel onde ninguém mais poderia distinguir o declarado do presumido. É o zero
fabricado que o produto proíbe, na direção que favorece quem o calcula.

Uma migração que NÃO faz isso é indistinguível, no código, de uma que ninguém
pensou no assunto. Estes testes são a diferença.

Postgres apenas: ``dna_turn`` é tabela de plano de controle e a 0004 não a cria
em SQLite.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

PREVIOUS_REVISION = "0011_edge_target_deleted"
REVISION = "0012_turn_outcome"

#: A forma que o banco de desenvolvimento tinha em 07/08/2026, reduzida aos
#: casos que decidem: o turno normal, o que morreu sem chamar o modelo, o que
#: morreu DEPOIS de queimar tokens, e o que chamou o modelo e levou 404.
TURNOS = (
    # (turn_id, agent, model, in_tok, out_tok, status, error)
    ("t-ok-1", "supervisor-copilot", "gpt-5.4", 5100, 320, "ok", None),
    ("t-ok-2", "assistente", "gpt-5.4", 8800, 210, "ok", None),
    ("t-err-sem-modelo", "supervisor-copilot", "", 0, 0, "error", "401 Unauthorized"),
    ("t-err-caro", "supervisor-copilot", "gpt-5.4", 5662, 1732, "error", "DiskFull(...)"),
    ("t-err-404", "supervisor-copilot", "gpt-5-mini", 0, 0, "error", "NotFoundError 404"),
)

INSERT = """
INSERT INTO {t} (turn_id, agent, model, input_tokens, output_tokens, status, error)
VALUES (:turn_id, :agent, :model, :i, :o, :status, :error)
"""


class _Db:
    def __init__(self, engine, schema: str) -> None:
        self.engine = engine
        self.schema = schema

    @property
    def turn(self) -> str:
        return f"{self.schema}.dna_turn"

    async def alembic(self, revision: str) -> None:
        from alembic import command

        from dna.adapters.sqlalchemy_.migrate import build_config

        schema = self.schema

        def _run(sync_conn):
            command.upgrade(build_config(schema, connection=sync_conn), revision)

        async with self.engine.begin() as conn:
            await conn.run_sync(_run)

    async def rows(self, stmt: str) -> list:
        async with self.engine.connect() as conn:
            return (await conn.execute(sa.text(stmt))).all()

    async def exec(self, stmt: str, params: dict) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(sa.text(stmt), params)

    async def colunas(self) -> dict[str, tuple[str, str | None]]:
        linhas = await self.rows(
            "SELECT column_name, is_nullable, column_default "
            "FROM information_schema.columns "
            f"WHERE table_schema = '{self.schema}' AND table_name = 'dna_turn'"
        )
        return {r[0]: (r[1], r[2]) for r in linhas}


@pytest_asyncio.fixture
async def db():
    """Um banco no 0011, com turnos dentro — o estado que a 0012 vai encontrar."""
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DNA_PG_TEST_URL")
    if not dsn:  # pragma: no cover — o marker já pula, isto é cinto duplo
        pytest.skip("DATABASE_URL not set")

    schema = f"dna_0012_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(dsn.replace("postgresql://", "postgresql+asyncpg://", 1))
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"CREATE SCHEMA {schema}"))

    d = _Db(engine, schema)
    await d.alembic(PREVIOUS_REVISION)
    for turn_id, agent, model, i, o, status, error in TURNOS:
        await d.exec(INSERT.format(t=d.turn), {
            "turn_id": turn_id, "agent": agent, "model": model,
            "i": i, "o": o, "status": status, "error": error,
        })
    try:
        yield d
    finally:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_a_0012_nao_presume_desfecho_para_NENHUM_turno_existente(db):
    """⭐ O AC, e a razão desta suíte existir.

    Cinco turnos, dois deles `status='ok'`. Depois da migração, TODOS estão
    vazios — inclusive os dois que terminaram sem exceção, que são exatamente
    os que um backfill teria marcado como resolvidos.
    """
    await db.alembic(REVISION)

    linhas = await db.rows(f"SELECT turn_id, status, outcome FROM {db.turn}")
    assert len(linhas) == len(TURNOS), "a migração perdeu turnos"
    assert {r[2] for r in linhas} == {""}, dict((r[0], r[2]) for r in linhas)

    resolvidos = await db.rows(
        f"SELECT count(*) FROM {db.turn} WHERE outcome = 'resolved'"
    )
    assert resolvidos[0][0] == 0


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_os_tokens_dos_turnos_existentes_ficam_INTACTOS(db):
    """A migração é aditiva. Nenhum número gravado muda — inclusive o turno que
    queimou 5.662 tokens antes de morrer, que é a prova de que a acumulação já
    sobrevivia à exceção."""
    await db.alembic(REVISION)
    linhas = await db.rows(
        f"SELECT turn_id, model, input_tokens, output_tokens, status FROM {db.turn}"
    )
    assert {(r[0], r[1], r[2], r[3], r[4]) for r in linhas} == {
        (t[0], t[2], t[3], t[4], t[5]) for t in TURNOS
    }


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_tokens_partial_fica_NULO_e_nao_falso_nas_linhas_antigas(db):
    """⚠️ NULL é a leitura honesta: *ninguém estava olhando quando aquilo foi
    gravado*.

    `false` afirmaria que a conta daqueles turnos está fechada — e a do
    `t-err-404` não está, ele chamou o modelo e o uso é ilegível. `true`
    difamaria os que reportaram uso direitinho. A migração não sabe qual é
    qual, e o jeito de dizer isso é não dizer nada.
    """
    await db.alembic(REVISION)
    linhas = await db.rows(f"SELECT turn_id, tokens_partial FROM {db.turn}")
    assert {r[1] for r in linhas} == {None}, dict((r[0], r[1]) for r in linhas)


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_as_colunas_nascem_com_a_forma_declarada(db):
    """`outcome` NOT NULL com default vazio; `tokens_partial` NULO permitido."""
    await db.alembic(REVISION)
    cols = await db.colunas()

    nullable, default = cols["outcome"]
    assert nullable == "NO"
    assert default is not None and "''" in default

    nullable, _ = cols["tokens_partial"]
    assert nullable == "YES"


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_um_turno_novo_nasce_DESCONHECIDO_e_nao_resolvido(db):
    """O default do banco é a última porta do caminho de escrita: quem inserir
    um turno sem citar `outcome` também não ganha um `resolved` de graça."""
    await db.alembic(REVISION)
    await db.exec(INSERT.format(t=db.turn), {
        "turn_id": "t-novo", "agent": "a", "model": "gpt-5.4",
        "i": 10, "o": 2, "status": "ok", "error": None,
    })
    linhas = await db.rows(
        f"SELECT outcome, tokens_partial FROM {db.turn} WHERE turn_id = 't-novo'"
    )
    assert linhas[0] == ("", None)


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_rodar_a_0012_duas_vezes_e_inocuo(db):
    """`IF NOT EXISTS`, como a 0011: uma base que já ganhou a coluna à mão tem
    de passar, e um re-run não pode estourar nem mexer em dado."""
    await db.exec(
        f"ALTER TABLE {db.turn} ADD COLUMN outcome TEXT NOT NULL DEFAULT ''", {}
    )
    await db.alembic(REVISION)
    linhas = await db.rows(f"SELECT outcome, tokens_partial FROM {db.turn}")
    assert {r[0] for r in linhas} == {""}
    assert {r[1] for r in linhas} == {None}
