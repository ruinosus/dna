"""o turno declara a raia — teste e uso real param de somar na mesma conta

Revision ID: 0014_turn_lane
Revises: 0013_search_docs_by_dims
Create Date: 2026-08-08

``i-158``. *"Uma coisa é conversa de teste, outra é conversa real."*

MEDIDO em 08/08/2026 no Postgres de desenvolvimento: **86 turnos, 76 de um
copiloto só, TODOS gerados por agente durante desenvolvimento e nenhum de uso
real.** ``dna_turn`` não tinha nenhuma coluna capaz de dizer isso, e a
consequência não é estética: o painel da conta (``dna.runtime.roi``) somava os
86 tokens como se fossem consumo de cliente. Uma suíte de avaliação — que é
justamente o que se quer construir a seguir (``i-159``) — pioraria isso a cada
rodada, sujando exatamente o dado que ela existe para melhorar.

``lane TEXT NOT NULL DEFAULT ''``
    ``real`` (uso de verdade) · ``test`` (avaliação, smoke, demonstração).

    ⭐ **Vazio significa NÃO DECLARADA, jamais ``real``.** Os 86 turnos
    existentes ficam vazios e **nenhum é presumido real** — pelos dois lados:
    um backfill para ``real`` afirmaria que aquilo foi uso de cliente, e a
    medição diz o contrário; um backfill para ``test`` difamaria qualquer turno
    que porventura fosse legítimo. É a decisão da 0012 sobre ``outcome``,
    repetida porque a razão é a mesma — um número inventado a favor de quem o
    calcula é a pior espécie, e aqui ele inventaria uso.

    Sem CHECK constraint, pela mesma razão da 0012: o vocabulário é do runtime
    (``dna.runtime.telemetry.LANES``) e uma segunda cópia dele no banco vira
    migração toda vez que uma raia nova aparecer. A porta de escrita valida —
    ``_raia()`` é a ÚNICA por onde uma raia entra num ``Turn``, e ela recusa o
    que não está na lista.

**Por que aqui, e não numa tabela do host.** A opção barata era marcar a raia
no índice de conversas do dna-cloud (``copilot_thread``), sem release de SDK
nenhum. Ela foi recusada por dois motivos medidos, não por gosto:

1. **Quem precisa excluir o turno de teste da conta lê ``dna_turn``**, não o
   índice de conversas. Uma raia invisível para esse leitor faria cada
   consumidor do SDK reinventar a exclusão por conta própria — que é como um
   invariante vira convenção e depois vira bug.

   ⚠️ **Nota de 11/08/2026, e ela NÃO revoga a decisão acima.** O leitor que
   motivou esta coluna chamava-se ``dna.runtime.roi`` e saiu deste repositório
   nessa data — cruzar custo, preço e aceitação é fato do contrato de quem
   opera, não do SDK. **A coluna FICA**, e é exatamente o que o argumento (1)
   sempre disse: a razão nunca foi *"o leitor é do SDK"*, foi *"o leitor lê
   ``dna_turn``"*. Um leitor que se mudou continua lendo ``dna_turn``, e a
   alternativa recusada (marcar a raia no índice de conversas do host)
   continua recusada pelo mesmo motivo — agora com mais força, porque o host
   e o leitor deixaram de ser o mesmo processo em todo deployment.
   **Quem já aplicou esta revisão não precisa fazer nada.**
2. ``dna_turn.thread_id`` **pode ser vazio** (turno de A2A, de worker). Uma raia
   presa à conversa não cobre esses turnos, e eles são exatamente os que uma
   suíte de avaliação automatizada produz.

**Sem índice**, pela razão que a 0012, a 0011 e a 0009 já escreveram: ``lane`` é
lido em AGREGAÇÃO sobre a fatia que ``dna_turn_thread_started_idx`` já traz
(workspace + janela), e um índice aqui pagaria manutenção em toda escrita de
turno — o caminho quente — para não servir consulta nenhuma. Quando existir uma
tela que filtre POR raia sobre volume que doa, ela vem com o número na mão.

**Postgres only**, como a 0004 que criou a tabela e a 0012 que a estendeu:
``dna_turn`` é tabela de plano de controle e não existe num self-host SQLite.
``build_metadata`` espelha isto com ``if is_pg``, e
``test_postgres_model_matches_migrated_database`` (marcado
``requires_postgres``) falha se as duas descrições divergirem.

DDL cru em vez de ``op.add_column`` segue a 0001/0004/0012: uma revisão é um
fato histórico congelado e não pode se re-renderizar a partir do modelo.
``IF NOT EXISTS`` porque rodar duas vezes tem de ser inócuo — e porque uma base
que ganhou a coluna à mão tem de passar.

Sem downgrade: as migrações do DNA são forward-only.
"""
from __future__ import annotations

from alembic import op

revision = "0014_turn_lane"
down_revision = "0013_search_docs_by_dims"
branch_labels = None
depends_on = None


# ``{schema}`` is interpolated from the migration context (see env.py); the
# identifier is validated at SqlAlchemySource construction (trusted config).
PG_DDL_LANE = """
ALTER TABLE {schema}.dna_turn
    ADD COLUMN IF NOT EXISTS lane TEXT NOT NULL DEFAULT ''
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # [dialect] control-plane table is pg-only (see the docstring).
    schema = op.get_context().version_table_schema or "public"
    op.execute(PG_DDL_LANE.format(schema=schema))

    # SEM backfill, e é a decisão mais importante desta revisão. Nenhum turno
    # anterior é presumido real e nenhum é presumido de teste. O porquê está no
    # docstring do módulo.


def downgrade() -> None:
    # Forward-only, as the baseline is (docs/PORT-CONTRACT.md § "Schema
    # migrations"): recovery is backup/re-seed, not downgrade.
    raise NotImplementedError("DNA schema migrations are forward-only")
