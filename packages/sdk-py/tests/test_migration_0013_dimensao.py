"""Revisão 0013 contra um banco que já tem a loja de busca dentro.

A pergunta que uma renomeação-com-adoção precisa responder não é *"as tabelas
novas existem?"* — é **"os documentos que já estavam lá continuam lá, achavéis,
e com o índice de pé?"**. Aqui o banco é construído na revisão ANTERIOR, ganha a
loja de busca na forma EXATA que a produção tem hoje (medida em 08/08/2026 no
Postgres de dev: ``vector(384)``, 170 linhas,
``dna_search_meta.embedding_model_id = sentence-transformers/all-MiniLM-L6-v2``),
é CONTADO, migrado, e conferido de novo.

O que estes casos provam, e cada um corresponde a uma alternativa descartada no
docstring da 0013:

* as linhas **não se movem** — a tabela velha VIRA a de 384, com a mesma
  contagem e o mesmo vetor byte a byte (nada foi reembeddado);
* o **índice sobrevive** à renomeação, e com o nome novo — um
  ``dna_search_docs_384`` carregando um ``dna_search_docs_embedding`` pendurado
  é um nome errado que sobreviveu à migração, e ninguém repara nisso até
  precisar dele;
* o ``model_id`` das linhas herdadas vem do **meta**, não de um palpite;
* ⚠️ e, sem meta, a revisão **recusa** em vez de rotular 170 vetores com um
  espaço inventado.

Gated no marcador ``requires_postgres``: a loja pgvector é pg-only.
"""
from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.requires_postgres

PREVIOUS_REVISION = "0012_turn_outcome"
THIS_REVISION = "0013_search_docs_by_dims"

#: O ``model_id`` real que o dev carrega — a fonte do backfill.
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"

#: O DDL da loja como ela existe HOJE, antes da 0013. Copiado do
#: ``pgvector_migrations.build_pg_migrations(384)`` que esta story retirou —
#: deliberadamente copiado e não importado: o passado de que partimos é um fato
#: histórico, e se o módulo que o descrevia foi apagado, quem o guarda é o teste
#: da migração que o supera.
LEGACY_DDL = """
CREATE TABLE {schema}.dna_search_docs (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    tenant     TEXT NOT NULL DEFAULT '',
    text_hash  TEXT NOT NULL,
    title      TEXT,
    snippet    TEXT,
    body       TEXT NOT NULL,
    embedding  vector({dims}),
    fts        tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(body, ''))) STORED,
    UNIQUE (scope, kind, name, tenant)
)
"""


def _dsn() -> str:
    for key in ("DATABASE_URL", "DNA_PG_TEST_URL", "DNA_PG_TEST_DSN"):
        value = os.environ.get(key)
        if value:
            return value
    pytest.skip("no Postgres DSN set")  # pragma: no cover — marker guards


class _Store:
    """Um schema descartável parado na revisão anterior, com a loja legada."""

    def __init__(self, engine, schema: str) -> None:
        self.engine = engine
        self.schema = schema

    async def exec(self, stmt: str, params: dict | None = None) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(sa.text(stmt), params or {})

    async def scalar(self, stmt: str, params: dict | None = None):
        async with self.engine.connect() as conn:
            return (await conn.execute(sa.text(stmt), params or {})).scalar()

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

    async def relation_exists(self, name: str) -> bool:
        got = await self.scalar(
            "SELECT to_regclass(CAST(:n AS text))", {"n": f"{self.schema}.{name}"}
        )
        return got is not None

    async def vector_width(self, table: str) -> int | None:
        return await self.scalar(
            "SELECT a.atttypmod FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relname = :t AND a.attname = 'embedding'",
            {"s": self.schema, "t": table},
        )

    async def index_names(self, table: str) -> set[str]:
        rows = await self.rows(
            "SELECT indexname FROM pg_indexes WHERE schemaname = :s "
            "AND tablename = :t",
            {"s": self.schema, "t": table},
        )
        return {r[0] for r in rows}

    async def unique_columns(self, table: str) -> list[str]:
        rows = await self.rows(
            "SELECT a.attname FROM pg_constraint con "
            "JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum "
            "WHERE n.nspname = :s AND c.relname = :t AND con.contype = 'u' "
            "ORDER BY k.ord",
            {"s": self.schema, "t": table},
        )
        return [r[0] for r in rows]


async def _store(dims: int = 384, rows: int = 170, meta: bool = True):
    """Banco na 0012 + a loja legada de ``dims``, com ``rows`` documentos."""
    raw = _dsn()
    url = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    schema = f"dna_0013_{uuid.uuid4().hex[:10]}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
    store = _Store(engine, schema)
    await store.alembic(PREVIOUS_REVISION)

    # A extensão + a loja como o provider a criava antes desta story.
    await store.exec("CREATE EXTENSION IF NOT EXISTS vector")
    await store.exec(LEGACY_DDL.format(schema=schema, dims=dims))
    await store.exec(
        f"CREATE INDEX dna_search_docs_lookup ON {schema}.dna_search_docs "
        "(scope, kind, tenant)"
    )
    await store.exec(
        f"CREATE INDEX dna_search_docs_fts ON {schema}.dna_search_docs "
        "USING gin (fts)"
    )
    if dims <= 2000:
        await store.exec(
            f"CREATE INDEX dna_search_docs_embedding ON {schema}.dna_search_docs "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
    await store.exec(
        f"CREATE TABLE {schema}.dna_search_meta "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    if meta:
        await store.exec(
            f"INSERT INTO {schema}.dna_search_meta (key, value) VALUES "
            f"('embedding_dims', '{dims}'), ('embedding_model_id', '{MODEL_ID}')"
        )

    for i in range(rows):
        vector = "[" + ",".join(
            "1.0" if j == i % dims else "0.0" for j in range(dims)
        ) + "]"
        await store.exec(
            f"INSERT INTO {schema}.dna_search_docs "
            "(scope, kind, name, tenant, text_hash, title, snippet, body, "
            "embedding) VALUES (:s, 'Story', :n, '', :h, :t, :sn, :b, "
            f"'{vector}'::vector)",
            {"s": "dna", "n": f"s-{i:04d}", "h": f"hash-{i}",
             "t": f"Story {i}", "sn": f"snippet {i}", "b": f"body about topic {i}"},
        )

    async def cleanup() -> None:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()

    return store, cleanup


# ---------------------------------------------------------------------------
# ⭐ os 170 documentos
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_as_linhas_sobrevivem_e_nao_se_movem():
    """A contagem ANTES é a contagem DEPOIS, e o VETOR é o mesmo byte a byte.

    A contagem sozinha sobreviveria a um ``INSERT … SELECT`` e sobreviveria a um
    reembedding — as duas alternativas descartadas. O vetor idêntico é o que
    prova que nada foi recalculado.
    """
    store, cleanup = await _store()
    try:
        before = await store.scalar(
            f"SELECT count(*) FROM {store.schema}.dna_search_docs"
        )
        sample = await store.scalar(
            f"SELECT embedding::text FROM {store.schema}.dna_search_docs "
            "WHERE name = 's-0042'"
        )
        assert before == 170

        await store.alembic(THIS_REVISION)

        assert await store.scalar(
            f"SELECT count(*) FROM {store.schema}.dna_search_docs_384"
        ) == 170
        assert await store.scalar(
            f"SELECT embedding::text FROM {store.schema}.dna_search_docs_384 "
            "WHERE name = 's-0042'"
        ) == sample, "o vetor mudou — alguém reembeddou o que já estava certo"
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_o_nome_velho_deixa_de_existir():
    """Sem alias, sem view: o mutante que só ACRESCENTA as tabelas novas e deixa
    a velha viva morre aqui. Dois nomes para a mesma coisa é a exceção que nunca
    morre — e o roteamento teria de conhecer os dois."""
    store, cleanup = await _store()
    try:
        await store.alembic(THIS_REVISION)
        assert not await store.relation_exists("dna_search_docs")
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_o_indice_atravessa_a_migracao_e_com_o_nome_certo():
    """⚠️ O caminho não pode perder o índice em produção no meio.

    ``ALTER TABLE … RENAME`` é operação de catálogo e os índices seguem — mas
    com o NOME antigo, e um índice com nome de tabela que não existe mais é a
    ponta solta que um ``CREATE INDEX IF NOT EXISTS`` posterior duplica em
    silêncio, pagando escrita para sempre.
    """
    store, cleanup = await _store()
    try:
        await store.alembic(THIS_REVISION)
        names = await store.index_names("dna_search_docs_384")
        assert "dna_search_docs_384_embedding" in names, names
        assert "dna_search_docs_384_fts" in names, names
        assert "dna_search_docs_384_lookup" in names, names
        assert not [n for n in names if n.startswith("dna_search_docs_") and not
                    n.startswith("dna_search_docs_384")], (
            f"índice com o nome antigo pendurado na tabela nova: {names}"
        )
        # E exatamente UM de cada — nenhum duplicado pelo CREATE IF NOT EXISTS.
        assert len([n for n in names if n.endswith("_embedding")]) == 1, names
        assert len([n for n in names if n.endswith("_fts")]) == 1, names
        assert len([n for n in names if n.endswith("_lookup")]) == 1, names
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_o_model_id_herdado_vem_do_meta_e_nao_de_um_palpite():
    store, cleanup = await _store()
    try:
        await store.alembic(THIS_REVISION)
        distinct = await store.rows(
            f"SELECT DISTINCT model_id FROM {store.schema}.dna_search_docs_384"
        )
        assert [r[0] for r in distinct] == [MODEL_ID], distinct
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_sem_meta_a_revisao_recusa_em_vez_de_inventar_o_espaco():
    """⚠️ Rotular 170 vetores com um ``model_id`` inventado os faria participar
    de buscas de um espaço que não é o deles — e ninguém teria como conferir.
    A recusa é a leitura honesta."""
    store, cleanup = await _store(meta=False)
    try:
        with pytest.raises(Exception, match="which embedding space"):
            await store.alembic(THIS_REVISION)
        # ⚠️ E a recusa não pode deixar o banco pela metade: uma migração
        # parcialmente aplicada é pior que uma recusada (a 0003 já escreveu
        # isto). A tabela velha continua velha, e a revisão continua a 0012.
        assert await store.relation_exists("dna_search_docs")
        assert not await store.relation_exists("dna_search_docs_384")
        assert await store.scalar(
            f"SELECT version_num FROM {store.schema}.alembic_version"
        ) == PREVIOUS_REVISION
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_uma_largura_inedita_na_loja_legada_falha_alto():
    """⭐ Dimensão INÉDITA falha ALTO e aponta a migration que falta — jamais
    cria a tabela sozinha, jamais arredonda para a vizinha."""
    store, cleanup = await _store(dims=777, rows=3)
    try:
        with pytest.raises(Exception, match="777"):
            await store.alembic(THIS_REVISION)
    finally:
        await cleanup()


# ---------------------------------------------------------------------------
# a forma nova
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_as_cinco_tabelas_existem_e_so_as_indexaveis_tem_indice_ann():
    """3072 não ganha índice, e é limite do pgvector (2000), não escolha —
    medido. Uma tabela silenciosamente sem acelerador vira 'a busca ficou
    lenta' seis meses depois."""
    store, cleanup = await _store()
    try:
        await store.alembic(THIS_REVISION)
        for dims in (384, 768, 1024, 1536, 3072):
            table = f"dna_search_docs_{dims}"
            assert await store.relation_exists(table), table
            assert await store.vector_width(table) == dims
            names = await store.index_names(table)
            has_ann = f"{table}_embedding" in names
            assert has_ann is (dims <= 2000), (
                f"{table}: índice ANN={has_ann} para dims={dims} — acima de "
                f"2000 o pgvector recusa ivfflat e hnsw. {names}"
            )
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_a_chave_unica_passa_a_incluir_o_espaco():
    """O MESMO documento embeddado por dois modelos são DUAS linhas; a chave
    antiga (sem ``model_id``) as recusaria — e recusar é pior que duplicar,
    porque o segundo embedder simplesmente não conseguiria indexar."""
    store, cleanup = await _store()
    try:
        await store.alembic(THIS_REVISION)
        for dims in (384, 1536):
            cols = await store.unique_columns(f"dna_search_docs_{dims}")
            assert cols == ["scope", "kind", "name", "tenant", "model_id"], (
                f"dna_search_docs_{dims}: {cols}"
            )
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_rodar_a_migracao_duas_vezes_e_inocuo():
    """Uma escada forward-only tem de aguentar um re-boot — os containers do
    dna-cloud aplicam a migração no CMD, toda vez que sobem."""
    store, cleanup = await _store()
    try:
        await store.alembic(THIS_REVISION)
        await store.alembic(THIS_REVISION)  # no-op: já está no head
        assert await store.scalar(
            f"SELECT count(*) FROM {store.schema}.dna_search_docs_384"
        ) == 170
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_um_banco_sem_loja_de_busca_migra_sem_reclamar():
    """A adoção é CONDICIONAL: um consumidor que nunca ligou a busca não tem
    ``dna_search_docs``, e a revisão simplesmente cria as cinco."""
    raw = _dsn()
    url = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    schema = f"dna_0013_fresh_{uuid.uuid4().hex[:10]}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
    store = _Store(engine, schema)
    try:
        await store.alembic(THIS_REVISION)
        for dims in (384, 3072):
            assert await store.relation_exists(f"dna_search_docs_{dims}")
        assert await store.scalar(
            f"SELECT count(*) FROM {schema}.dna_search_docs_384"
        ) == 0
    finally:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()
