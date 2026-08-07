"""a aresta passa a saber que o alvo morreu — e para de dizer que resolveu

Revision ID: 0011_edge_target_deleted
Revises: 0010_valid_time_column
Create Date: 2026-08-06

i-131. A travessia servia ``resolved`` como ``to_kind IS NOT NULL``. Isso não
é a pergunta que ``resolved`` responde: ``to_kind`` é um fato do INSTANTE DA
ESCRITA — *"a referência achou um alvo, e ele era deste Kind"* — e estava sendo
lido como um fato do instante da LEITURA — *"isto ainda aponta para algo"*.
Apagada a instância alvo, a aresta continuava na tabela **e continuava dizendo
``resolved: true``**. Não era uma informação imprecisa: era a informação
OPOSTA, entregue com a mesma confiança de sempre.

⚠️ **O conserto não é apagar a aresta junto**, e o ``delete_instance`` já
explica por quê desde a 0006: as arestas de ENTRADA pertencem a OUTRAS
instâncias, que continuam dizendo o que disseram. A decisão do founder de
06/08/2026 sobre o ``AuditLog`` transformou isso em regra com vocabulário
próprio (``on_target_delete: allow``): uma linha de auditoria sobre uma
instância apagada **tem** que continuar apontando. O defeito nunca foi a aresta
sobreviver; foi ela MENTIR sobre o próprio estado enquanto sobrevivia.

Duas saídas estavam registradas na issue. Medidas antes de escolher, contra o
Postgres real (2000 instâncias, 10.000 arestas, ``ANALYZE`` feito):

============================================  ==========  ==========
                                              p50         incidência
============================================  ==========  ==========
**(b) marcar no delete** — esta revisão
delete sozinho (baseline da transação)         3,32 ms
delete + ``UPDATE`` das arestas de entrada     4,80 ms    **1× por delete**
o ``UPDATE`` no servidor (EXPLAIN ANALYZE)     0,032 ms   Index Scan
                                                          ``dna_edges_in_idx``,
                                                          13 buffers
**(a) recalcular na leitura** — recusada
travessia estreita, sem join                   2,70 ms
travessia estreita, com ``LEFT JOIN``          3,37 ms    **1× por travessia**
travessia larga (5000 arestas), sem join      11,54 ms
travessia larga (5000 arestas), com join      13,98 ms    **1× por travessia**
============================================  ==========  ==========

⚠️ **A premissa de custo da issue estava errada, e no sentido que importa.**
Ela dizia que (b) *"precisa achar as arestas, o que o portão do
``on_target_delete`` já faz, então o custo incremental pode ser zero"*. Não é:
``plan_target_delete`` curto-circuita em ``enforcers_for`` e **não toca em loja
nenhuma** quando nenhuma relação declara política — que é todo delete deste
registro hoje. Então (b) custa um ``UPDATE`` indexado inteiro, não zero. Ainda
assim ganha, porque o custo é pago UMA vez por delete e (a) seria pago em TODA
travessia, para sempre.

**Mas o que decidiu não foi o milissegundo — foi a segunda regra de resolução.**

Um ``LEFT JOIN`` em ``dna_instances`` casa por ``(scope, tenant, kind, name)``.
Não é assim que uma referência resolve: ``Kernel.get_instance`` cai para os
scopes PAI dos Kinds herdáveis, e é por isso que ``dna_edges.to_scope`` é
NULL — *"resolvida, mas pela cadeia de herança"* — em vez de ser sempre igual a
``scope``. Recalcular na leitura pelo join ingênuo é escrever uma SEGUNDA regra
de resolução ao lado da do kernel, que é textualmente o que
``dna.kernel.query.references`` diz que esta casa já pagou para não fazer.

**Medido na base de desenvolvimento do founder em 06/08/2026** — e a medição
pegou a segunda regra em flagrante:

| | |
|---|---:|
| arestas em ``dna_edges`` | **32** |
| resolvidas (``to_kind`` não nulo) | **30** |
| penduradas de nascença | **2** (``App/i116-app-quebrado`` → dois fantasmas) |
| com ``to_scope`` NULL (resolveram por herança) | **3** |
| que o join ingênuo declararia quebradas | **1** — e ela está CERTA |

A uma é ``App/estudio-pro-teste.copilots → Copilot/copiloto-criador``: a aresta
mora no scope de um tenant, o alvo existe em ``dna-cloud``, e ela resolveu por
herança. O join ingênuo a chama de quebrada. Ou seja, a saída (a) trocaria a
mentira atual por **a mentira oposta em 1 de 30 arestas resolvidas** — e a
versão correta de (a), que replicaria a cadeia de scopes em SQL, custaria mais
que o número medido acima, que é o piso da versão errada.

**A terceira razão, e ela sobrevive ao delete-e-recria.** O que esta coluna
grava não é *"existe hoje algo com este nome"*: é *"a instância que esta aresta
resolveu foi apagada"*. Apagar ``Feature/f-y`` e criar outra com o mesmo nome
produz, pelo ``ownerReference`` do Kubernetes que a 0008 cita, um objeto
DIFERENTE — e o ``to_id`` desta aresta nomeia o antigo. Um recálculo por NOME
diria ``resolved: true`` para um objeto que a aresta nunca viu. A marca
continua verdadeira.

**Sem backfill, de propósito.** Uma linha anterior a esta revisão diz NULL
porque *ninguém estava olhando*, e NULL é exatamente essa leitura: "nenhum
delete foi observado". Preencher exigiria (1) inventar um instante que ninguém
registrou e (2) descobrir quais alvos sumiram — pelo join ingênuo que este
mesmo docstring acabou de recusar. A base de dev tem **zero** arestas mentindo
hoje (a única candidata é o falso negativo acima), então o backfill compraria
nada e importaria o defeito para dentro da migração. Uma aresta antiga se
conserta sozinha do mesmo jeito que a 0009 descreve: a próxima escrita da
instância de ORIGEM re-deriva o conjunto pelo produtor vivo, que teve o alvo na
mão.

**Sem índice**, pela mesma razão que a 0009 não indexou ``to_api_version``: a
coluna não é predicado de busca. Ela é lida junto com a linha que
``dna_edges_in_idx``/``dna_edges_out_idx`` já trouxe, e escrita por um
``UPDATE`` que o ``_in`` já serve. Um índice aqui pagaria manutenção em toda
escrita de aresta para não ser usado por consulta nenhuma.

⚠️ **O limite honesto: a marca é do mesmo ``scope``/``tenant``.** O ``UPDATE``
casa ``(scope, tenant, to_kind, to_name)`` porque é o que o índice serve. Uma
aresta que resolveu por HERANÇA mora no scope filho e o delete acontece no
scope pai — ela não é alcançada, e continua dizendo o que dizia. Isso é
estritamente melhor que hoje e não inventa mentira nova: são as mesmas 3 linhas
em 32 da tabela acima, e são as mesmas que a 0008 e a 0009 também não
alcançaram, pela mesma razão e com a mesma cura (a próxima escrita da origem).
Alargar o ``UPDATE`` para todos os scopes exigiria um segundo índice pago em
toda escrita, para servir o caso de 9%.

Sem downgrade: as migrações do DNA são forward-only.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_edge_target_deleted"
down_revision = "0010_valid_time_column"
branch_labels = None
depends_on = None


def _edges_table(is_pg: bool) -> str:
    """O Postgres prefixa ``dna_``, o SQLite não — igual à 0009."""
    return "dna_edges" if is_pg else "edges"


def _has_column(bind, schema: str | None, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    try:
        cols = insp.get_columns(table, schema=schema)
    except Exception:  # noqa: BLE001 — tabela ausente numa base parcial
        return False
    return any(c["name"] == column for c in cols)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    schema = op.get_context().version_table_schema if is_pg else None
    edge_t = _edges_table(is_pg)

    # Condicional, como a 0009: rodar duas vezes tem de ser inócuo, e uma base
    # que já ganhou a coluna à mão tem de passar.
    if not _has_column(bind, schema, edge_t, "to_deleted_at"):
        # [dialect] o mesmo par que ``updated_at`` desta tabela usa: timestamp
        # de verdade no PG, TEXT ISO-8601 no SQLite (que não tem o tipo).
        col = (
            sa.Column("to_deleted_at", sa.DateTime(timezone=True), nullable=True)
            if is_pg else
            sa.Column("to_deleted_at", sa.Text, nullable=True)
        )
        op.add_column(edge_t, col, schema=schema)

    # SEM backfill e SEM índice — as duas ausências são decisões, e o porquê
    # de cada uma está no docstring do módulo.


def downgrade() -> None:
    raise NotImplementedError("DNA schema migrations are forward-only")
