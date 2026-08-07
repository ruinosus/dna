"""o turno ganha desfecho — e o zero de tokens para de ter dois significados

Revision ID: 0012_turn_outcome
Revises: 0011_edge_target_deleted
Create Date: 2026-08-07

``spec-rendimento-do-copiloto``. Com 85 turnos gravados, o CUSTO é exato
(tokens × modelo) e o RENDIMENTO é zero: nada nestas tabelas diz se o turno
*conseguiu* alguma coisa. ``status`` responde *"estourou exceção?"* e vinha
sendo lido como se respondesse *"resolveu?"* — duas perguntas que divergem
justamente onde a medição importa, porque um turno pode terminar limpo sem ter
resolvido nada.

Duas colunas, e a segunda existe porque a medição desmentiu a spec.

``outcome TEXT NOT NULL DEFAULT ''``
    ``resolved`` / ``escalated`` / ``abandoned``.

    ⭐ **Vazio significa DESCONHECIDO, jamais ``resolved``.** Os 85 turnos
    existentes ficam vazios e **nenhum é presumido resolvido** — o backfill
    óbvio (``status = 'ok'`` → ``resolved``) é exatamente o zero fabricado que
    este produto proíbe, e no sentido pior: ele inventaria uma taxa de
    resolução de 89% que mede a ausência de crashes e se apresenta como medida
    de valor entregue. Um número inventado a favor de quem o calcula é a pior
    espécie, porque ninguém tem incentivo para conferi-lo.

    Sem CHECK constraint, pela mesma razão que ``dna_run.status`` não tem: o
    vocabulário é do runtime (``dna.runtime.telemetry.OUTCOMES``), e uma
    segunda cópia dele no banco vira migração toda vez que um desfecho novo
    aparecer. A porta de escrita valida — ``_desfecho()`` é a ÚNICA por onde um
    desfecho entra num ``Turn``, e ela recusa o que não está na lista.

``tokens_partial BOOLEAN`` (nulo = desconhecido)
    ⚠️ **Esta coluna é o que sobrou de uma hipótese medida e derrubada.**

    A spec afirmava: *"8 dos 9 turnos com erro não gravaram tokens — o turno
    falhou, queimou tokens de verdade, e a conta não os viu"*, e concluía que
    era defeito de escrita, consertável gravando no caminho de exceção.

    **Medido contra os 85 turnos antes de consertar qualquer coisa, e não é
    isso.** ``model`` e ``input_tokens`` são escritos pelo mesmo lugar, e no
    banco inteiro andam juntos — ``model = ''`` ⟺ ``input_tokens = 0``, em 9 de
    9 linhas. Modelo vazio prova que **nenhum span de LLM existiu**, não que o
    token se perdeu:

    ==========================================  =====  ======================
    turnos com ``status='error'``                  9
    ------------------------------------------  -----  ----------------------
    morreram antes de qualquer chamada ao          7    7–32 ms, ``model=''``
    modelo (401 nas tools, ``CancelledError``)          zero é a MEDIÇÃO CERTA
    chamaram o modelo e a chamada estourou         1    404, ``gpt-5-mini``,
    (o único caso real)                                 ``model`` sim, tokens 0
    somaram 5.662 tokens e MORRERAM depois         1    ``DiskFull`` — provam
                                                        que a soma já
                                                        sobrevivia à exceção
    ==========================================  =====  ======================

    Ou seja: o caminho de erro **já gravava** o que tinha sido consumido. O
    defeito real é outro e é de LEITURA — ``input_tokens = 0`` significa duas
    coisas incompatíveis: *"nenhuma chamada ao modelo, conta fechada em zero"*
    e *"houve chamada e o uso dela é ilegível"*. O ``openinference`` monta os
    contadores com ``_token_counts(run.outputs)``, e numa run que errou
    ``run.outputs`` é ``None`` — sai o nome do modelo (que ele lê do ``extra``,
    carimbado na largada) e nenhum contador. O provedor cobrou o prompt.

    Recontar por conta própria seria estimar, e estimativa aqui é o zero
    fabricado com outra roupa. Então o registro passa a dizer QUAL dos dois
    zeros ele é: ``false`` = conta fechada, ``true`` = ``input_tokens`` é um
    PISO. Um ROI que soma tokens sem olhar esta coluna continua subestimando o
    custo — a diferença é que agora ele tem como saber que está.

    **Nula para as linhas existentes, de propósito**, e é a mesma decisão da
    0011 sobre ``to_deleted_at``. Nem ``false`` nem ``true`` seriam verdade
    sobre elas: ``false`` afirmaria que a conta daqueles 85 turnos está fechada
    — e do turno do 404 ela não está —, e ``true`` difamaria os 75 que
    reportaram uso direitinho. NULL é a leitura honesta: *ninguém estava
    olhando quando aquilo foi gravado*.

**Postgres only**, como a 0004 que criou a tabela: ``dna_turn`` é tabela de
plano de controle e não existe num self-host SQLite. ``build_metadata`` espelha
isto com ``if is_pg``, e ``test_postgres_model_matches_migrated_database``
(marcado ``requires_postgres``, roda no job ``postgres`` do CI) falha se as
duas descrições divergirem.

DDL cru em vez de ``op.add_column`` segue a 0001/0004: uma revisão é um fato
histórico congelado e não pode se re-renderizar a partir do modelo.
``IF NOT EXISTS`` porque rodar duas vezes tem de ser inócuo — e porque uma base
que ganhou a coluna à mão tem de passar, que é a mesma condicional da 0011.

Sem índice, pela razão que a 0011 e a 0009 já escreveram: nenhuma das duas é
predicado de busca. ``outcome`` é lido em agregação sobre a fatia que
``dna_turn_thread_started_idx`` já traz (workspace + janela de tempo), e um
índice aqui pagaria manutenção em toda escrita de turno — o caminho quente —
para não servir consulta nenhuma. Quando existir uma tela que filtre POR
desfecho, ela virá com o número na mão e o índice se justifica então.

Sem downgrade: as migrações do DNA são forward-only.
"""
from __future__ import annotations

from alembic import op

revision = "0012_turn_outcome"
down_revision = "0011_edge_target_deleted"
branch_labels = None
depends_on = None


# ``{schema}`` is interpolated from the migration context (see env.py); the
# identifier is validated at SqlAlchemySource construction (trusted config).
PG_DDL_OUTCOME = """
ALTER TABLE {schema}.dna_turn
    ADD COLUMN IF NOT EXISTS outcome TEXT NOT NULL DEFAULT ''
"""

PG_DDL_TOKENS_PARTIAL = """
ALTER TABLE {schema}.dna_turn
    ADD COLUMN IF NOT EXISTS tokens_partial BOOLEAN
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # [dialect] control-plane table is pg-only (see the docstring).
    schema = op.get_context().version_table_schema or "public"
    op.execute(PG_DDL_OUTCOME.format(schema=schema))
    op.execute(PG_DDL_TOKENS_PARTIAL.format(schema=schema))

    # SEM backfill, e é a decisão mais importante desta revisão. Nenhum turno
    # anterior é presumido resolvido, e nenhum tem a conta declarada fechada.
    # O porquê de cada uma está no docstring do módulo.


def downgrade() -> None:
    # Forward-only, as the baseline is (docs/PORT-CONTRACT.md § "Schema
    # migrations"): recovery is backup/re-seed, not downgrade.
    raise NotImplementedError("DNA schema migrations are forward-only")
