"""a aresta sabe a apiVersion do alvo — a invariante emprestada é devolvida

Revision ID: 0009_edge_to_api_version
Revises: 0008_instance_id
Create Date: 2026-08-06

i-110.3, fatia 1 de ``spec-topologia-do-grafo``.

``dna_edges`` sabia de que apiVersion uma aresta SAI — ``from_api_version``
está na chave primária desde a 0006, porque é a identidade da origem. Não sabia
para qual ela ENTRA. E a razão pela qual isso funcionava **não estava escrita
nesta tabela**: morava em ``dna.kernel.kinds.registry``, na guarda da i-195 que
recusa registrar dois Kinds homônimos sob apiVersions diferentes. A integridade
do grafo dependia, calada, de uma invariante de outro módulo — que tem uma
lista de exceções (``KIND_NAME_COLLISION_ALLOWLIST``, hoje ``{"Reference"}``).

⚠️ **Medido ao escrever esta revisão:** a permissão está ABERTA e ninguém passa
por ela — um kernel booteado hoje serve 84 portas e 84 nomes DISTINTOS, com uma
única ``Reference`` (a extensão ``research`` reusa a do ``sdlc`` em vez de
registrar a sua). Isso não torna a coluna desnecessária: torna a dependência
oculta ainda mais frágil, porque a única coisa que a mantinha verdadeira era um
acidente de registro que teste nenhum guardava. A catraca que passa a guardar
está em ``tests/test_edge_knows_target_api_version.py``.

A 0008 já tinha escrito a consequência, sem nomear a causa como um defeito, ao
explicar por que o backfill de ``to_id`` deixa NULL:

    *"ambíguo — a aresta grava ``to_kind``/``to_name`` mas não a
    ``api_version`` do alvo, então dois Kinds homônimos em namespaces
    diferentes tornam o alvo indeterminado"*

Esta revisão é a resposta a essa frase.

**O backfill sai do ``to_id``, não da chave natural — e isso não é conveniência.**
A 0008 casou pela chave natural (``scope``/``kind``/``name``/``tenant``) e teve
de contar as linhas para recusar o ambíguo, porque a chave natural É ambígua
quando há homônimos: é o problema. O ``to_id`` que ela deixou gravado não é —
um id identifica UMA linha. Então o join desta revisão é
``dna_instances.id = dna_edges.to_id``, e ele é ambíguo por construção zero.
A consequência honesta: **esta revisão preenche exatamente as arestas que a
0008 conseguiu identificar, nem uma a mais.** Onde a 0008 não soube, esta
também não sabe, e NULL continua sendo a informação — não uma lacuna a
preencher com palpite.

**Medido na base de desenvolvimento do founder em 06/08/2026:**

| | |
|---|---:|
| arestas em ``dna_edges`` | **26** |
| com ``to_id`` (0008) | **23** |
| que esta revisão preenche | **23** (100% das que têm ``to_id``) |
| que ficam NULL | **3** |

As três, nomeadas, porque "3 ficaram" sem os nomes é um número que ninguém pode
conferir:

* duas são **penduradas** (``to_kind IS NULL``) — ``App/i116-app-quebrado``
  apontando para ``i116-copiloto-fantasma`` e ``i116-outro-fantasma``, dados de
  teste quebrados de propósito. Uma aresta pendurada não tem alvo, logo não tem
  apiVersion de alvo. NULL aqui não é falha do backfill: é a leitura certa.
* uma resolveu por **herança de scope** — ``App/estudio-pro-teste`` num scope de
  tenant apontando para um ``Copilot`` herdado de ``dna-cloud``. É EXATAMENTE a
  mesma linha que a 0008 não alcançou, pela mesma razão, e continua se
  consertando sozinha do mesmo jeito: a próxima escrita da instância de origem
  re-deriva a aresta pelo produtor VIVO, que teve o alvo na mão.

Sem downgrade: as migrações do DNA são forward-only.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_edge_to_api_version"
down_revision = "0008_instance_id"
branch_labels = None
depends_on = None


def _names(is_pg: bool) -> tuple[str, str]:
    """(instances, edges) — o Postgres prefixa ``dna_``, o SQLite não."""
    return ("dna_instances", "dna_edges") if is_pg else ("instances", "edges")


def _qualify(schema: str | None, table: str) -> str:
    return f"{schema}.{table}" if schema else table


def _has_column(bind, schema: str | None, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    try:
        cols = insp.get_columns(table, schema=schema)
    except Exception:  # noqa: BLE001 — tabela ausente numa base parcial
        return False
    return any(c["name"] == column for c in cols)


def _backfill_edge_api_versions(bind, instances: str, edges: str) -> None:
    """``to_api_version`` para toda aresta cujo ``to_id`` nomeia uma instância.

    Um ``UPDATE ... SET x = (subselect)`` puro escreveria NULL sobre as linhas
    sem correspondência, o que aqui seria inócuo (a coluna acabou de nascer
    NULL) e amanhã não seria — rodar esta migração de novo numa base já corrida
    apagaria o que o produtor vivo carimbou desde então. O ``WHERE EXISTS``
    torna a revisão idempotente E incapaz de regredir: ela só escreve onde tem
    resposta.

    Sem ``COUNT(*) = 1`` como na 0008: o join é por ``id``, e um id nomeia uma
    linha. A contagem lá existia porque a chave natural podia casar duas — que
    é o defeito que esta coluna fecha.
    """
    match = (
        f"FROM {instances} i"
        f" WHERE i.id = e.to_id"
        f"   AND COALESCE(i.tenant, '') = COALESCE(e.tenant, '')"
        f"   AND i.api_version IS NOT NULL AND i.api_version <> ''"
    )
    bind.execute(sa.text(
        f"UPDATE {edges} AS e SET to_api_version = ("
        f"  SELECT i.api_version {match}"
        f") WHERE e.to_id IS NOT NULL AND EXISTS (SELECT 1 {match})"
    ))


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    schema = op.get_context().version_table_schema if is_pg else None
    inst_t, edge_t = _names(is_pg)

    # Condicional, como a 0008: rodar duas vezes tem de ser inócuo, e uma base
    # que já ganhou a coluna à mão tem de passar.
    if not _has_column(bind, schema, edge_t, "to_api_version"):
        op.add_column(edge_t, sa.Column("to_api_version", sa.Text, nullable=True),
                      schema=schema)

    # A 0008 é a fornecedora do ``to_id`` de que este backfill depende. Numa
    # base parcial em que ela não rodou (ou rodou antes de a coluna existir), a
    # ausência é dita, não suposta: sem ``to_id`` não há de onde derivar, e
    # deixar tudo NULL é a resposta correta — não um erro.
    if _has_column(bind, schema, edge_t, "to_id") and _has_column(
        bind, schema, inst_t, "id",
    ):
        _backfill_edge_api_versions(
            bind, _qualify(schema, inst_t), _qualify(schema, edge_t),
        )

    # SEM índice. ``to_api_version`` não é predicado de busca: ela é um
    # DESEMPATE aplicado depois que ``(scope, tenant, to_kind, to_name)`` — que
    # o ``dna_edges_in_idx`` já serve — reduziu o conjunto a um punhado de
    # linhas. Um índice aqui pagaria manutenção em toda escrita de aresta para
    # não ser usado por consulta nenhuma. Se um dia a coluna virar predicado
    # (uma travessia que FILTRA por apiVersion), o índice é a correção, e ele
    # deve entrar com a consulta que o justifica, não antes.


def downgrade() -> None:
    raise NotImplementedError("DNA schema migrations are forward-only")
