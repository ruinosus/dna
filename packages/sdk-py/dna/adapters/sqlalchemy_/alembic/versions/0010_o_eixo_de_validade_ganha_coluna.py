"""o eixo de validade sai da convenção e vira coluna — com a restrição junto

Revision ID: 0010_valid_time_column
Revises: 0009_edge_to_api_version
Create Date: 2026-08-06

Fatia 3 de ``spec-topologia-do-grafo``. O §4.2(c) da spec media a
bi-temporalidade do DNA e achou **meio eixo**:

===================  ==========================================  ==========
eixo                 onde estava                                 tipo
===================  ==========================================  ==========
**transação**        ``dna_versions.created_at`` — uma COLUNA     ``TEXT``
**validade**         ``spec.valid_from`` / ``spec.valid_to``,     strings
                     **só no Kind Engram**, JSON dentro de
                     ``content``, **sem coluna e sem índice**
===================  ==========================================  ==========

Esta revisão promove o segundo. Ela não inventa dado nenhum: ``remember`` semeia
``spec.valid_from`` e ``forget`` grava ``spec.valid_to`` desde que os verbos de
memória existem, e ``dna.memory.decay.currently_valid`` filtra por eles em
Python a cada recall. O que faltava era o lugar onde a loja pudesse **indexar,
recusar e ser perguntada** — e sobretudo o lugar onde a invariante pudesse ser
DITA: *uma instância tem no máximo um estado verdadeiro em cada instante do
mundo*.

⚠️ **Os dois eixos ficam separados de propósito.** Misturá-los é o erro clássico
do bitemporal: uma nota escrita hoje sobre o ano passado é **válida** no ano
passado e **acreditada** hoje. ``as_of`` continua lendo ``dna_versions``; nada
aqui o toca.

**Medido na base de desenvolvimento do founder em 06/08/2026**, antes de
desenhar — porque a resposta muda o desenho:

| | |
|---|---:|
| instâncias em ``dna_instances`` | **414** |
| com ``spec.valid_from`` | **14** (todas ``Engram`` — 100% dos Engrams) |
| com ``spec.valid_to`` preenchido | **2** |
| **sem noção nenhuma de validade** | **400** (96,6%) |
| ids distintos / linhas | **414 / 414** — nenhuma colisão a resolver |

Então a coluna **não nasce vazia**: nasce com 14 janelas de limite inferior e 2
fechadas. E nasce sem nenhum backfill capaz de falhar, porque não há um único id
repetido para a restrição rejeitar.

Três decisões que a medição e a documentação decidiram, não o gosto:

**1. UMA coluna de range, não duas colunas escalares.**
A fatia se chama "valid-time como duas colunas" pela FORMA do fato (um começo e
um fim), e a leitura óbvia seria ``valid_from timestamptz`` + ``valid_to
timestamptz``. Essa leitura não sobrevive a um upgrade de major: o **PG18**
(25/09/2025) implementa chave temporal como ``PRIMARY KEY (id, valid_at WITHOUT
OVERLAPS)``, e a documentação é literal — *"The WITHOUT OVERLAPS column must
have a range or multirange type"*. **Duas escalares não são aceitas.** Com um
``tstzrange``, adotar o motor no PG18 é trocar esta ``EXCLUDE`` pela chave, sem
tocar em dado; com duas escalares seria reescrever a tabela. O projeto roda
PG16 hoje (compose ``pgvector/pgvector:pg16``; Azure Flexible Server 16.14,
medido 06/08/2026), então a restrição desta revisão é a forma certa PARA HOJE
**e** a única que o PG18 consegue promover.

**2. NOT NULL com janela ilimitada, não nullable.**
NULL diria "não declara janela", que é informação real — mas uma ``EXCLUDE``
**pula qualquer linha com operando NULL**, então a coluna nullable deixaria a
restrição sem efeito sobre as 400 linhas que não dizem nada. Uma guarda verde
sobre a tabela inteira é exatamente o defeito que esta casa já pagou. A janela
ilimitada também não é invenção: é o que
``dna.memory.decay.currently_valid`` sempre significou por um ``valid_to``
ausente (*"True quando ``valid_to`` não está setado OU está no futuro"*), dito
no esquema em vez de re-derivado em Python. Quem precisa distinguir "não disse"
de "disse sempre" usa ``ValidWindow.bounded``.

**3. ``EXCLUDE`` sobre ``id``, não sobre a chave natural.**
Um período de validade pertence à IDENTIDADE, e um rename não pode partir a
história (i-114). Linhas com ``id`` NULL ficam de fora — corretamente: uma
linha sem identidade não colide com a identidade de ninguém.

⚠️ **``btree_gist`` é obrigatório** e a revisão o cria. GiST fala range
nativamente e mais nada; o ``=`` sobre um ``id`` TEXT precisa da extensão.
Confirmado na allowlist do Azure Flexible Server — **1.7 em PG16, sem
``shared_preload_libraries``** (docs da Microsoft, lidas em 06/08/2026). ⚠️ Mas
estar na allowlist do PRODUTO não basta: o `azure.extensions` do servidor é uma
allowlist POR SERVIDOR e hoje diz só ``VECTOR``. Sem acrescentar ``BTREE_GIST``
lá (``infra/bicep/resources.bicep`` no dna-cloud) e reimplantar, este
``CREATE EXTENSION`` falha em produção. Está dito na story, não suposto aqui.

⚠️ **SQLite não ganha nada disto, e não ganha calado.** Não há range type, não
há GiST, não há ``EXCLUDE``. A meia-solução — duas colunas TEXT — carregaria os
extremos e **não** a invariante, que é a metade que vale. Então o dialeto sqlite
não recebe a coluna, declara ``SourceCapabilities.valid_time=False``, e
``load_one_valid_at`` levanta ``ValidTimeUnsupported`` (501) em vez de filtrar
nada e chamar o resultado de resposta. A matriz de conformidade registra isso
como ``xfail(strict=True)``.

Sem downgrade: as migrações do DNA são forward-only.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_valid_time_column"
down_revision = "0009_edge_to_api_version"
branch_labels = None
depends_on = None

#: A janela ilimitada, meio-aberta. Meio-aberta ``[from, to)`` porque é o que
#: ``dna.memory.contradiction`` já afirma sobre janelas de claim — e porque só
#: sob ela duas janelas que se ENCOSTAM (uma termina em T, a seguinte começa em
#: T) não se sobrepõem, que é o que torna uma cadeia de supersession expressável.
_UNBOUNDED = (
    "tstzrange('-infinity'::timestamptz, 'infinity'::timestamptz, '[)')"
)

_EXCL_NAME = "dna_instances_valid_at_excl"


def _has_column(bind, schema: str | None, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    try:
        cols = insp.get_columns(table, schema=schema)
    except Exception:  # noqa: BLE001 — tabela ausente numa base parcial
        return False
    return any(c["name"] == column for c in cols)


def _qualify(schema: str | None, table: str) -> str:
    return f"{schema}.{table}" if schema else table


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Não é um "ainda não": é a resposta. Ver o docstring — a meia-solução
        # em sqlite carregaria os extremos sem a invariante, e um adapter que
        # tem os extremos mas não a restrição é um que responde com confiança
        # onde não sabe. O sqlite recusa por capability, que é honesto e
        # sondável ANTES da leitura.
        return

    schema = op.get_context().version_table_schema
    inst = _qualify(schema, "dna_instances")

    # A extensão PRIMEIRO: a EXCLUDE abaixo não existe sem ela.
    #
    # ⚠️ ``IF NOT EXISTS`` NÃO BASTA, e isto foi medido, não suposto: com a
    # suíte rodando sob ``pytest-xdist`` (``addopts = -n auto``) seis processos
    # aplicaram esta revisão ao mesmo tempo contra o mesmo banco, e cinco
    # morreram em ``duplicate key value violates unique constraint
    # "pg_extension_name_index"``. ``CREATE EXTENSION IF NOT EXISTS`` verifica e
    # cria em dois passos, sem lock entre eles — o ``IF NOT EXISTS`` do
    # Postgres protege contra a extensão JÁ existir, não contra alguém a criar
    # no meio. Isso não é artefato de teste: os containers do dna-cloud rodam
    # a migração no CMD de boot, e duas réplicas subindo juntas são exatamente
    # este caso. O bloco captura as duas formas que a corrida assume.
    op.execute(sa.text("""
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS btree_gist;
        EXCEPTION WHEN duplicate_object OR unique_violation THEN
            NULL;  -- outro processo ganhou a corrida; o resultado é o mesmo
        END $$;
    """))

    # Condicional, como a 0008 e a 0009: rodar duas vezes tem de ser inócuo, e
    # uma base que já ganhou a coluna à mão tem de passar.
    if not _has_column(bind, schema, "dna_instances", "valid_at"):
        op.execute(
            f"ALTER TABLE {inst} ADD COLUMN valid_at tstzrange "
            f"NOT NULL DEFAULT {_UNBOUNDED}"
        )

    # ── backfill: a convenção em JSON vira a coluna ────────────────────────
    #
    # A projeção é a MESMA que ``dna.kernel.valid_time.valid_window_of`` faz no
    # caminho de escrita, e tinha de ser: se as duas divergissem, a coluna
    # diria uma coisa nas linhas antigas e outra nas novas, e ninguém
    # descobriria porque as duas são plausíveis. As regras, idênticas dos dois
    # lados:
    #
    #   * ausente / vazio / inparseável  → extremo ilimitado (fail-open, a
    #     mesma escolha de ``currently_valid``: um ``valid_to`` corrompido
    #     escrito meses atrás não pode tornar a instância ilegível);
    #   * janela invertida (fim <= começo) → o fim cai, o começo fica. Derrubar
    #     os dois apagaria a metade que estava bem formada.
    #
    # ⚠️ ``content`` é TEXT (não JSONB) nesta tabela — o ``::jsonb`` é o mesmo
    # cast que os índices de expressão de ``dna_insts_*_idx`` já usam.
    # ``jsonb_typeof`` guarda o cast contra um ``content`` que não seja objeto,
    # e o regex guarda o ``::timestamptz`` contra um texto que não seja
    # instante — sem ele, UMA string ruim aborta a migração inteira.
    lower_sql = (
        "case when c.spec_valid_from ~ "
        r"'^\d{4}-\d{2}-\d{2}[T ]' "
        "then c.spec_valid_from::timestamptz else null end"
    )
    upper_sql = (
        "case when c.spec_valid_to ~ "
        r"'^\d{4}-\d{2}-\d{2}[T ]' "
        "then c.spec_valid_to::timestamptz else null end"
    )
    op.execute(sa.text(f"""
        WITH c AS (
            SELECT scope, kind, api_version, name, tenant,
                   nullif(content::jsonb->'spec'->>'valid_from', '') AS spec_valid_from,
                   nullif(content::jsonb->'spec'->>'valid_to',   '') AS spec_valid_to
              FROM {inst}
             WHERE jsonb_typeof(content::jsonb) = 'object'
               AND jsonb_typeof(content::jsonb->'spec') = 'object'
               AND (content::jsonb->'spec' ? 'valid_from'
                 OR content::jsonb->'spec' ? 'valid_to')
        ), w AS (
            SELECT c.scope, c.kind, c.api_version, c.name, c.tenant,
                   ({lower_sql}) AS lo,
                   ({upper_sql}) AS hi
              FROM c
        )
        UPDATE {inst} AS i
           SET valid_at = tstzrange(
                   coalesce(w.lo, '-infinity'::timestamptz),
                   CASE WHEN w.hi IS NOT NULL AND w.lo IS NOT NULL
                             AND w.hi <= w.lo THEN 'infinity'::timestamptz
                        ELSE coalesce(w.hi, 'infinity'::timestamptz)
                   END,
                   '[)')
          FROM w
         WHERE i.scope = w.scope AND i.kind = w.kind
           AND i.api_version = w.api_version AND i.name = w.name
           AND i.tenant = w.tenant
           AND (w.lo IS NOT NULL OR w.hi IS NOT NULL)
    """))

    # ── a invariante ───────────────────────────────────────────────────────
    #
    # Depois do backfill, e não antes: criar a restrição primeiro e só então
    # escrever os períodos deixaria a revisão passar por um estado em que as
    # linhas ainda não são o que a restrição vai julgar. Aqui ela é verificada
    # contra o dado FINAL, que é o único momento em que a verificação vale.
    #
    # ``id`` NULL sai da restrição por semântica de EXCLUDE (operando NULL →
    # linha ignorada). Medido: 0 linhas com id NULL na base do founder, o que
    # torna a restrição efetiva sobre 100% das linhas hoje.
    #
    # ⚠️ ``conrelid`` e não só ``conname``, e isto foi um DEFEITO REAL desta
    # revisão, pego pelos testes antes de sair: ``pg_constraint.conname`` NÃO é
    # qualificado por schema. A primeira versão perguntava só o nome, então num
    # banco onde outro schema DNA já tivesse a restrição (o caso normal aqui —
    # o Postgres do dna-cloud é compartilhado, e a suíte cria um schema por
    # teste) a revisão via "já existe" e PULAVA a criação. O resultado é o pior
    # tipo de verde: migração aplicada, ``alembic_version`` em 0010, e a
    # invariante ausente na tabela — que os dois testes de sobreposição pegaram
    # em vermelho. ``'{inst}'::regclass`` amarra a pergunta a ESTA tabela.
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conname = '{_EXCL_NAME}'
                   AND conrelid = '{inst}'::regclass
            ) THEN
                ALTER TABLE {inst} ADD CONSTRAINT {_EXCL_NAME}
                    EXCLUDE USING gist (id WITH =, valid_at WITH &&);
            END IF;
        END $$;
    """))


def downgrade() -> None:
    raise NotImplementedError("DNA schema migrations are forward-only")
