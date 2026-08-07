"""documento vira instância — as tabelas passam a chamar a coisa pelo nome

Revision ID: 0007_instancia
Revises: 0006_document_edges
Create Date: 2026-08-06

i-111. ``select count(*) from dna_documents where kind = 'KindDefinition'``
devolvia 6: um Kind É um documento, guardado na MESMA tabela das instâncias
que ele define. A palavra fazia dois trabalhos a um nível de distância. O par
que fecha é Kind/Instância — inclusive no caso reflexivo ("o KindDefinition é
uma instância do Kind KindDefinition").

**Renomeia, não recria.** ``ALTER TABLE ... RENAME`` preserva as linhas, os
índices e o OID; nenhuma linha é lida, copiada ou reescrita, e por isso a
contagem antes é idêntica à contagem depois — o teste
``tests/test_migration_0007_rename.py`` mede exatamente isso em ambos os
dialetos.

**Índices e a PK vêm junto, de propósito.** No Postgres, renomear a tabela NÃO
renomeia os índices nem a constraint de PK: uma tabela ``dna_instances`` com
um ``dna_documents_pkey`` pendurado é um nome errado que sobrevive à
renomeação e reaparece em toda mensagem de erro de chave duplicada. Cada um é
renomeado com ``IF EXISTS``, porque o nome da PK depende de qual revisão a
criou (0001 nomeia ``dna_documents_pkey``; 0003 recria a PK e o Postgres pode
nomeá-la ``dna_documents_pkey1``) — a 0003 já documenta essa mesma armadilha.

**Idempotente por construção.** Todo passo é condicional ao nome ANTIGO ainda
existir, então rodar duas vezes é inócuo e um banco já renomeado à mão passa.

Sem downgrade: as migrações do DNA são forward-only (``docs/PORT-CONTRACT.md``
§ "Schema migrations"), e a recuperação é backup/re-seed.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_instancia"
down_revision = "0006_document_edges"
branch_labels = None
depends_on = None


#: (nome antigo, nome novo) — tabelas, no Postgres.
PG_TABLES = [
    ("dna_documents", "dna_instances"),
    ("dna_layer_documents", "dna_layer_instances"),
]

#: (nome antigo, nome novo) — índices, no Postgres. Os quatro ``dna_docs_*``
#: são os índices de expressão quentes da 0001 (parciais em
#: ``content ? 'spec'``), fora do modelo por serem inexprimíveis nele.
PG_INDEXES = [
    ("dna_documents_tenant_idx", "dna_instances_tenant_idx"),
    ("dna_docs_status_idx", "dna_insts_status_idx"),
    ("dna_docs_feature_idx", "dna_insts_feature_idx"),
    ("dna_docs_updated_at_idx", "dna_insts_updated_at_idx"),
    ("dna_docs_spec_gin_idx", "dna_insts_spec_gin_idx"),
]

#: (tabela JÁ renomeada, nome antigo da constraint, nome novo). A PK do
#: ``dna_instances`` tem DOIS nomes possíveis: 0001 a nomeia
#: ``dna_documents_pkey``, e a 0003 recria a PK — o Postgres pode nomear a
#: segunda ``dna_documents_pkey1``. Só uma das duas existe num banco dado.
PG_CONSTRAINTS = [
    ("dna_instances", "dna_documents_pkey", "dna_instances_pkey"),
    ("dna_instances", "dna_documents_pkey1", "dna_instances_pkey"),
    ("dna_layer_instances", "dna_layer_documents_pkey",
     "dna_layer_instances_pkey"),
]

SQLITE_TABLES = [
    ("documents", "instances"),
    ("layer_documents", "layer_instances"),
]

SQLITE_INDEXES = [
    ("documents_tenant_idx", "instances_tenant_idx"),
    ("docs_status_idx", "insts_status_idx"),
    ("docs_feature_idx", "insts_feature_idx"),
    ("docs_updated_at_idx", "insts_updated_at_idx"),
]


def _pg(schema: str) -> None:
    bind = op.get_bind()

    def exists(name: str) -> bool:
        got = bind.execute(
            sa.text("SELECT to_regclass(CAST(:n AS text))"), {"n": f"{schema}.{name}"}
        ).scalar()
        return got is not None

    for old, new in PG_TABLES:
        if exists(old):
            op.execute(f"ALTER TABLE {schema}.{old} RENAME TO {new}")
    for old, new in PG_INDEXES:
        if exists(old):
            op.execute(f"ALTER INDEX {schema}.{old} RENAME TO {new}")
    for table, old, new in PG_CONSTRAINTS:
        got = bind.execute(sa.text(
            "SELECT 1 FROM pg_constraint c JOIN pg_namespace n"
            " ON n.oid = c.connamespace"
            " WHERE n.nspname = :s AND c.conname = :c"
        ), {"s": schema, "c": old}).scalar()
        if got is not None:
            op.execute(
                f"ALTER TABLE {schema}.{table} RENAME CONSTRAINT {old} TO {new}"
            )


def _sqlite() -> None:
    bind = op.get_bind()

    def has(kind: str, name: str) -> bool:
        row = bind.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type = :t AND name = :n"),
            {"t": kind, "n": name},
        ).first()
        return row is not None

    for old, new in SQLITE_TABLES:
        if has("table", old) and not has("table", new):
            op.execute(f"ALTER TABLE {old} RENAME TO {new}")
    # SQLite carrega os índices junto com o RENAME da tabela, mas mantém os
    # NOMES antigos. `ALTER INDEX` não existe aqui: recria-se.
    for old, new in SQLITE_INDEXES:
        if has("index", old):
            sql = bind.execute(
                sa.text("SELECT sql FROM sqlite_master"
                        " WHERE type = 'index' AND name = :n"),
                {"n": old},
            ).scalar()
            op.execute(f"DROP INDEX {old}")
            if sql:
                op.execute(
                    sql.replace(f"INDEX {old}", f"INDEX {new}", 1)
                       .replace(" ON documents ", " ON instances ", 1)
                )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _pg(op.get_context().version_table_schema or "public")
    else:
        _sqlite()


def downgrade() -> None:
    raise NotImplementedError("DNA schema migrations are forward-only")
