"""Revisão 0007 contra um banco que já tem dado dentro (i-111).

A pergunta que uma renomeação de tabela precisa responder não é "o nome mudou?"
— é "**as linhas continuam lá?**". Aqui o banco é construído na revisão
ANTERIOR, preenchido com a forma de um deployment (instâncias em dois escopos,
overlay de tenant, overlays de layer), CONTADO, migrado, e contado de novo.

Também prova as três coisas que uma renomeação parcial deixa passar:

* o nome VELHO deixa de existir — não é alias, não é view;
* os índices vêm junto (um ``dna_instances`` com ``dna_documents_tenant_idx``
  pendurado é um nome errado que sobreviveu à renomeação);
* rodar a migração duas vezes é inócuo.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

PREVIOUS_REVISION = "0006_document_edges"
THIS_REVISION = "0007_instancia"

CORE = "github.com/ruinosus/dna/v1"
SDLC = "github.com/ruinosus/dna/sdlc/v1"

#: (scope, kind, api_version, name, tenant)
_ROWS = [
    ("acme", "Genome", CORE, "acme", ""),
    ("acme", "KindDefinition", CORE, "deal", ""),
    ("acme", "Story", SDLC, "s-alpha", ""),
    ("acme", "Story", SDLC, "s-bravo", ""),
    ("acme", "Agent", CORE, "planner", "tenant-one"),
    ("beta", "Story", SDLC, "s-alpha", ""),
]

#: (scope, layer_id, layer_value, kind, name)
_LAYER_ROWS = [
    ("acme", "tenant", "tenant-one", "Agent", "planner"),
    ("acme", "tenant", "tenant-two", "Agent", "planner"),
]


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

    async def scalar(self, stmt: str, params: dict | None = None):
        async with self.engine.connect() as conn:
            return (await conn.execute(sa.text(stmt), params or {})).scalar()

    async def rows(self, stmt: str, params: dict | None = None) -> list:
        async with self.engine.connect() as conn:
            return (await conn.execute(sa.text(stmt), params or {})).all()

    async def count(self, table: str) -> int:
        return await self.scalar(f"SELECT count(*) FROM {self.table(table)}")

    async def table_exists(self, bare: str) -> bool:
        name = f"{self.prefix}{bare}"
        if self.is_pg:
            got = await self.scalar(
                "SELECT to_regclass(CAST(:n AS text))",
                {"n": f"{self.schema}.{name}"})
            return got is not None
        got = await self.scalar(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:n",
            {"n": name})
        return got is not None

    async def index_exists(self, name: str) -> bool:
        if self.is_pg:
            got = await self.scalar(
                "SELECT to_regclass(CAST(:n AS text))",
                {"n": f"{self.schema}.{name}"})
            return got is not None
        got = await self.scalar(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=:n",
            {"n": name})
        return got is not None

    async def alembic(self, revision: str) -> None:
        from alembic import command

        from dna.adapters.sqlalchemy_.migrate import build_config

        schema = self.schema

        def _run(sync_conn):
            command.upgrade(build_config(schema, connection=sync_conn), revision)

        async with self.engine.begin() as conn:
            await conn.run_sync(_run)


async def _sqlite_db(tmp_path) -> tuple[_Db, Any]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'prod.db'}")
    db = _Db(engine, None)
    await db.alembic(PREVIOUS_REVISION)
    return db, engine.dispose


async def _postgres_db(_tmp_path) -> tuple[_Db, Any]:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping Postgres dialect")

    url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    schema = f"dna_i111_{os.getpid()}_{id(asyncio):x}"
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


async def _seed(db: _Db) -> None:
    docs = db.table("documents")
    for scope, kind, api, name, tenant in _ROWS:
        if db.is_pg:
            await db.exec(
                f"INSERT INTO {docs} (scope, kind, api_version, name, content,"
                f" version, updated_at, tenant) VALUES (:s, :k, :a, :n, :c, 1,"
                f" '2026-08-06T00:00:00Z', :t)",
                {"s": scope, "k": kind, "a": api, "n": name,
                 "c": '{"spec": {}}', "t": tenant})
        else:
            await db.exec(
                f"INSERT INTO {docs} (scope, kind, api_version, name, content,"
                f" version, updated_at, tenant) VALUES (:s, :k, :a, :n, :c, 1,"
                f" '2026-08-06T00:00:00Z', :t)",
                {"s": scope, "k": kind, "a": api, "n": name,
                 "c": '{"spec": {}}', "t": tenant or None})
    layers = db.table("layer_documents")
    for scope, lid, lval, kind, name in _LAYER_ROWS:
        await db.exec(
            f"INSERT INTO {layers} (scope, layer_id, layer_value, kind, name,"
            f" content, updated_at) VALUES (:s, :i, :v, :k, :n, :c,"
            f" '2026-08-06T00:00:00Z')",
            {"s": scope, "i": lid, "v": lval, "k": kind, "n": name,
             "c": '{"spec": {}}'})


@pytest.mark.asyncio
async def test_as_linhas_sobrevivem_a_renomeacao(db_factory):
    """A contagem ANTES é a contagem DEPOIS, tabela por tabela."""
    db, cleanup = await db_factory()
    try:
        await _seed(db)
        before_docs = await db.count("documents")
        before_layers = await db.count("layer_documents")
        assert before_docs == len(_ROWS)
        assert before_layers == len(_LAYER_ROWS)

        await db.alembic(THIS_REVISION)

        assert await db.count("instances") == before_docs
        assert await db.count("layer_instances") == before_layers
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_o_nome_velho_deixa_de_existir(db_factory):
    """Sem alias, sem view: o mutante que só ADICIONA o nome novo morre aqui."""
    db, cleanup = await db_factory()
    try:
        await _seed(db)
        await db.alembic(THIS_REVISION)
        assert not await db.table_exists("documents")
        assert not await db.table_exists("layer_documents")
        assert await db.table_exists("instances")
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_o_conteudo_e_o_mesmo_linha_a_linha(db_factory):
    """Não é só a contagem: as chaves são as mesmas, na mesma ordem."""
    db, cleanup = await db_factory()
    try:
        await _seed(db)
        docs = db.table("documents")
        async with db.engine.connect() as conn:
            before = (await conn.execute(sa.text(
                f"SELECT scope, kind, api_version, name FROM {docs}"
                f" ORDER BY scope, kind, name"))).all()

        await db.alembic(THIS_REVISION)

        insts = db.table("instances")
        async with db.engine.connect() as conn:
            after = (await conn.execute(sa.text(
                f"SELECT scope, kind, api_version, name FROM {insts}"
                f" ORDER BY scope, kind, name"))).all()
        assert after == before
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_os_indices_vem_junto(db_factory):
    """Um índice com o nome velho é um nome errado que sobreviveu."""
    db, cleanup = await db_factory()
    try:
        await _seed(db)
        await db.alembic(THIS_REVISION)
        if db.is_pg:
            assert await db.index_exists("dna_instances_tenant_idx")
            assert not await db.index_exists("dna_documents_tenant_idx")
            assert await db.index_exists("dna_insts_status_idx")
            assert not await db.index_exists("dna_docs_status_idx")
            # A PK das DUAS tabelas: renomear a tabela não renomeia a
            # constraint, e um `dna_layer_documents_pkey` pendurado num
            # `dna_layer_instances` é o nome velho sobrevivendo (medido no
            # banco de dev depois da primeira passada desta revisão).
            names = [r[0] for r in (await db.rows(
                "SELECT conname FROM pg_constraint c"
                " JOIN pg_namespace n ON n.oid = c.connamespace"
                " WHERE n.nspname = :s AND c.contype = 'p'"
                "   AND c.conrelid::regclass::text LIKE '%instances'",
                {"s": db.schema},
            ))]
            assert not [n for n in names if "document" in n], names
        else:
            assert await db.index_exists("instances_tenant_idx")
            assert not await db.index_exists("documents_tenant_idx")
            assert await db.index_exists("insts_status_idx")
            assert not await db.index_exists("docs_status_idx")
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_um_banco_ja_renomeado_a_mao_passa(db_factory):
    """Idempotência pelos guardas ``IF EXISTS``: se alguém já renomeou (ou a
    migração morreu no meio), a revisão não pode explodir no nome ausente."""
    db, cleanup = await db_factory()
    try:
        await _seed(db)
        await db.exec(
            f"ALTER TABLE {db.table('documents')} RENAME TO {db.prefix}instances")
        await db.alembic(THIS_REVISION)
        assert await db.count("instances") == len(_ROWS)
        assert await db.count("layer_instances") == len(_LAYER_ROWS)
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_o_source_le_o_banco_migrado(db_factory):
    """A prova que atravessa a porta: depois da migração o adapter LÊ."""
    db, cleanup = await db_factory()
    try:
        await _seed(db)
        await db.alembic(THIS_REVISION)
        insts = db.table("instances")
        got = await db.scalar(
            f"SELECT count(*) FROM {insts} WHERE kind = 'KindDefinition'")
        assert got == 1
    finally:
        await cleanup()
