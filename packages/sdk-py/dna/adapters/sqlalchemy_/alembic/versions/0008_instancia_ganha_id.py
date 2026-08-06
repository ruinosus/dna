"""a instância ganha id — identidade separada do endereço

Revision ID: 0008_instance_id
Revises: 0007_instancia
Create Date: 2026-08-06

i-114. Até aqui a instância tinha UM identificador: o ``name``, que era também
o endereço. Toda renomeação era, por construção, uma exclusão — o histórico
desta casa tem três provas (Tier→PricingPlan, LessonLearned→Engram,
``dna-cloud-dev``→``dna-cloud``), e em todas *mudar o endereço apagou a
identidade*.

O desenho vem do Kubernetes e está escrito por extenso em
``dna/kernel/identity.py``: **não se escolhe entre nome e id — separa-se por
quem escreve.** O que um humano autora (o ``.dna/`` que se revisa em PR) guarda
o NOME; o que a máquina deriva (``dna_edges``) guarda ID e NOME. Esta revisão
abre as duas colunas e preenche as duas.

**Três decisões que esta migração toma, e a razão de cada uma:**

1. **``id`` NÃO entra na primary key.** A chave continua a 5-tupla natural,
   porque é por ela que todo leitor endereça. A coluna é o punho durável, não
   um endereço novo.

2. **O id das instâncias que já existem é DERIVADO da chave natural**, não
   sorteado — ao contrário do id de toda instância criada daqui em diante (ver
   ``mint_instance_id``). A razão é específica da migração e não vale para
   escritas: as MESMAS instâncias existem em DOIS lugares que precisam
   concordar — as linhas do Postgres e os YAML do ``.dna/`` em git — e são
   migrados por códigos diferentes, em momentos diferentes. Sorteio daria ao
   mesmo objeto um id no banco e outro no disco, e ``to_id`` nasceria certo num
   store e errado no outro. Derivar da chave natural torna o backfill
   CONVERGENTE: roda no banco, roda nos arquivos, roda de novo depois de um
   re-seed — mesmos ids. A objeção óbvia ("derivar do nome faz o rename mudar o
   id, que é o bug") não se aplica: a derivação acontece UMA vez, agora, para o
   que existe agora; o valor fica gravado e nunca é recalculado.

3. **O ``content`` é reescrito junto com a coluna.** Se só a coluna ganhasse o
   id, o caminho de leitura — que devolve ``content`` — continuaria sem ele, o
   pipeline de escrita não teria de onde herdar, cunharia um id NOVO na
   primeira gravação e sobrescreveria a coluna. A migração pareceria ter
   funcionado e teria durado até a próxima escrita. Coluna e conteúdo dizem a
   mesma coisa ou a identidade não existe.

**O backfill de ``dna_edges.to_id`` recusa quando é ambíguo.** Uma aresta grava
``to_kind``/``to_name`` mas não a ``api_version`` do alvo, então dois Kinds
homônimos em namespaces diferentes tornam o alvo indeterminado. Nesse caso
``to_id`` fica NULL — a mesma regra que o resolvedor de prefixo aplica: prefixo
ambíguo é RECUSA, nunca escolha em silêncio. NULL aqui é "não sei", e é
recuperável pelo backfill do grafo; um id errado não seria.

Sem downgrade: as migrações do DNA são forward-only.
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from dna.kernel.identity import derived_instance_id, is_instance_id

revision = "0008_instance_id"
down_revision = "0007_instancia"
branch_labels = None
depends_on = None

#: Quantas linhas por ida ao banco no backfill. As instâncias cabem em memória
#: numa base de desenvolvimento; numa de produção não necessariamente, e um
#: ``SELECT *`` sem teto é o jeito de descobrir isso da pior maneira.
_BATCH = 500


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


def _backfill_instance_ids(bind, instances: str) -> int:
    """Dá id a toda instância que ainda não tem — na coluna E no ``content``.

    Idempotente: uma linha cujo ``content`` já declara um ``metadata.id``
    bem-formado adota ESSE valor na coluna em vez de derivar outro. É o que faz
    a migração sobreviver a uma base semeada por um ``.dna/`` que já passou pelo
    backfill dos arquivos — os dois lados convergem para o mesmo id em vez de
    brigarem.
    """
    stamped = 0
    while True:
        rows = bind.execute(sa.text(
            f"SELECT scope, kind, api_version, name, tenant, content"
            f"  FROM {instances} WHERE id IS NULL LIMIT :n"
        ), {"n": _BATCH}).mappings().all()
        if not rows:
            return stamped
        for row in rows:
            try:
                raw = json.loads(row["content"])
            except (TypeError, ValueError):
                raw = None
            meta = raw.get("metadata") if isinstance(raw, dict) else None
            existing = meta.get("id") if isinstance(meta, dict) else None
            if is_instance_id(existing):
                new_id = existing
                content = row["content"]
            else:
                new_id = derived_instance_id(
                    tenant=row["tenant"], scope=row["scope"],
                    api_version=row["api_version"] or "",
                    kind=row["kind"], name=row["name"],
                )
                if isinstance(raw, dict):
                    if not isinstance(meta, dict):
                        meta = {}
                        raw["metadata"] = meta
                    # ``id`` primeiro: é identidade, e é onde um leitor a
                    # procura. Só reordena aqui, na única vez em que a chave
                    # nasce — nenhuma escrita posterior reordena nada.
                    raw["metadata"] = {"id": new_id, **meta}
                    content = json.dumps(raw)
                else:
                    # ``content`` ilegível (nunca visto, mas não é lugar de
                    # supor): a coluna ganha o id, o conteúdo fica como está.
                    content = row["content"]
            bind.execute(sa.text(
                f"UPDATE {instances} SET id = :id, content = :content"
                f" WHERE scope = :scope AND kind = :kind"
                f"   AND api_version = :api_version AND name = :name"
                f"   AND COALESCE(tenant, '') = COALESCE(:tenant, '')"
            ), {
                "id": new_id, "content": content,
                "scope": row["scope"], "kind": row["kind"],
                "api_version": row["api_version"], "name": row["name"],
                "tenant": row["tenant"],
            })
            stamped += 1


def _backfill_edge_ids(bind, instances: str, edges: str) -> None:
    """``to_id`` para toda aresta cujo alvo resolve para EXATAMENTE uma
    instância. Ambíguo (dois Kinds homônimos) ou ausente (aresta pendurada)
    fica NULL — ver o docstring do módulo."""
    match = (
        f"FROM {instances} i"
        f" WHERE i.scope = COALESCE(e.to_scope, e.scope)"
        f"   AND i.kind = e.to_kind"
        f"   AND i.name = e.to_name"
        f"   AND COALESCE(i.tenant, '') = COALESCE(e.tenant, '')"
    )
    bind.execute(sa.text(
        f"UPDATE {edges} AS e SET to_id = ("
        f"  SELECT MIN(i.id) {match}"
        f") WHERE e.to_kind IS NOT NULL"
        f"  AND (SELECT COUNT(*) {match}) = 1"
    ))


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    schema = op.get_context().version_table_schema if is_pg else None
    inst_t, edge_t = _names(is_pg)
    instances = _qualify(schema, inst_t)
    edges = _qualify(schema, edge_t)

    # Condicional em cada passo: rodar duas vezes tem de ser inócuo, e uma base
    # que já ganhou a coluna à mão tem de passar.
    if not _has_column(bind, schema, inst_t, "id"):
        op.add_column(inst_t, sa.Column("id", sa.Text, nullable=True),
                      schema=schema)
    if not _has_column(bind, schema, edge_t, "to_id"):
        op.add_column(edge_t, sa.Column("to_id", sa.Text, nullable=True),
                      schema=schema)

    _backfill_instance_ids(bind, instances)
    _backfill_edge_ids(bind, instances, edges)

    idx = f"{'dna_' if is_pg else ''}instances_id_idx"
    # Perguntado ao catálogo direto, e NÃO por ``inspect().get_indexes()``: a
    # tabela carrega índices de EXPRESSÃO (os quatro ``dna_insts_*`` parciais da
    # 0001), e o reflector do SQLAlchemy emite um ``SAWarning`` ao topar com
    # eles — que numa suíte com ``-W error`` vira falha de teste vinda de uma
    # migração que só queria saber se um índice existe.
    if is_pg:
        found = bind.execute(sa.text(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n"
            " ON n.oid = c.relnamespace"
            " WHERE c.relkind = 'i' AND n.nspname = :s AND c.relname = :i"
        ), {"s": schema or "public", "i": idx}).first()
    else:
        found = bind.execute(sa.text(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = :i"
        ), {"i": idx}).first()
    if found is None:
        # Depois do backfill, não antes: preencher uma coluna indexada paga a
        # manutenção do índice a cada UPDATE.
        op.create_index(idx, inst_t, ["tenant", "id"], schema=schema)


def downgrade() -> None:
    raise NotImplementedError("DNA schema migrations are forward-only")
