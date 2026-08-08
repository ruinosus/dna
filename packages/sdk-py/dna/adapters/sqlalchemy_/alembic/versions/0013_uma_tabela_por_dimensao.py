"""uma tabela por dimensão — o índice deixa de fixar o embedder

Revision ID: 0013_search_docs_by_dims
Revises: 0012_turn_outcome
Create Date: 2026-08-08

``s-indice-por-dimensao`` / ``i-104``. ``dna_search_docs`` já era dinâmica em
tudo, menos numa coisa::

    scope · kind · name · tenant   ← já eram COLUNA
    embedding vector(384)          ← a ÚNICA fixa, porque vector(N) é o TIPO

E a coisa fixa era a que decidia o produto: com a largura tipada na coluna,
**um tenant não podia escolher o próprio embedder** sem migrar a tabela inteira.

⛔ TABELA DINÂMICA FOI RECUSADA — e a primeira razão é regra dura
================================================================

    ``CLAUDE.md``: *"Data-access code never runs DDL."*

Não é preferência: é o que faz o schema ser **propriedade de migration,
revisável em PR**. Criar tabela em runtime faria o schema depender do que os
usuários fizeram, e ninguém mais responderia *"qual é o schema?"* olhando o
repo. A segunda razão é volume — uma tabela por coleção × tenant vira CENTENAS,
cada uma com índice ANN próprio, caro em memória.

⭐ A saída: o espaço de dimensões é pequeno e quase fechado
===========================================================

384 (MiniLM) · 768 (base) · 1024 (large) · 1536 (openai-3-small/ada) ·
3072 (openai-3-large). **Cinco tabelas, aqui.** Coleção nova e tenant novo já
eram INSERT (``scope`` e ``tenant`` são coluna desde sempre); ``model_id`` novo
numa dimensão que já tem tabela é só escrever; e uma dimensão INÉDITA é uma
migration nova, em PR revisado — que é o certo.

⚠️ Esta revisão NÃO importa ``dimensions.SUPPORTED_DIMS``
=========================================================

As cinco larguras estão escritas à mão aqui. Uma revisão é um **fato histórico
congelado** e não pode se re-renderizar a partir do modelo de hoje — a mesma
regra que a 0001/0004/0012 seguem ao usar DDL cru em vez de ``op.add_column``.
Quem garante que as duas listas concordam é
``tests/test_search_dimension_routing.py``, comparando duas listas
INDEPENDENTES: acrescentar uma largura ao runtime sem escrever a migration fica
VERMELHO. Se elas se importassem uma da outra, a guarda mediria a si mesma.

⚠️ 3072 NÃO GANHA ÍNDICE ANN, e isso é limite do pgvector, não escolha
=====================================================================

Medido em 08/08/2026 contra ``pgvector 0.8.2``::

    create index ... using ivfflat (e vector_cosine_ops) → ERROR: column cannot
        have more than 2000 dimensions for ivfflat index
    create index ... using hnsw    (e vector_cosine_ops) → ERROR: column cannot
        have more than 2000 dimensions for hnsw index

Ou seja: **1536 é a última largura indexável**; 3072 (``text-embedding-3-large``)
faz varredura exata. A decisão do founder falava em "cada uma com índice HNSW
próprio (caro em memória)" — para a maior das cinco, o índice sequer é
possível. A tabela existe e responde certo; ela só não tem acelerador, e ficar
sem índice calado seria pior do que dizer isto aqui. (O caminho conhecido é
``halfvec`` — indexável até 4000 — mas é OUTRO tipo de coluna e OUTRO espaço
numérico, portanto outra migration e outra decisão.)

⭐ OS 170 DOCUMENTOS QUE JÁ EXISTEM: eles NÃO se movem, NÃO se reindexam
=======================================================================

Medido no Postgres de dev em 08/08/2026::

    select count(*) from public.dna_search_docs          →  170
    format_type(embedding)                               →  vector(384)
    dna_search_meta.embedding_model_id                   →  sentence-transformers/all-MiniLM-L6-v2

A tabela velha **VIRA** a tabela de 384 (``ALTER TABLE … RENAME TO``), e as três
alternativas foram descartadas com motivo:

``INSERT … SELECT`` para a tabela nova
    reescreve 170 linhas e, pior, **reconstrói o índice IVFFlat do zero**. Entre
    o ``CREATE TABLE`` e o ``CREATE INDEX`` a busca em produção fica sem
    acelerador — perder o índice no meio é exatamente o que o pedido proíbe.

reindexar (re-``embed`` dos 170)
    ⚠️ Só isto seria necessário se os vetores fossem inválidos. Não são: são
    MiniLM de 384 e continuam comparáveis entre si. Reembeddar seria pagar 170
    inferências para chegar ao mesmo lugar, e — no caminho remoto — pagar em
    dinheiro por isso.

deixar a tabela velha viva ao lado das novas
    dois nomes para a mesma coisa, e o roteamento teria de conhecer os dois. É
    a exceção que nunca morre.

``ALTER TABLE … RENAME`` é operação de catálogo: **O(1), sem reescrever
linha, e os índices seguem a tabela** (mantendo os nomes antigos, que esta
revisão também renomeia para que uma base migrada e uma base nova fiquem
indistinguíveis). O ``ADD COLUMN model_id … DEFAULT ''`` é o único toque nas
linhas, e no PG11+ ele nem reescreve a tabela.

E o backfill do ``model_id`` **não é chute**: ele vem de
``dna_search_meta.embedding_model_id``, que o store já gravava justamente para
recusar a mistura. ⚠️ Se houver linhas e o meta NÃO disser qual espaço é,
esta revisão **falha alto**: rotular 170 vetores com um ``model_id`` inventado
os faria participar de buscas de um espaço que não é o deles, e um número
errado a favor de quem o calcula é a pior espécie.

⚠️ ``model_id`` é FILTRO, não etiqueta
======================================

O contrato de ``EmbeddingPort`` é explícito: *"vetores de providers com
``model_id`` diferente NÃO são comparáveis"*. Duas coleções a 1536 com
embedders diferentes moram na MESMA tabela (mesmo tipo de coluna) e não podem
aparecer na mesma busca. Por isso ``model_id`` entra na chave única e em todo
predicado de leitura — e por isso o antigo ``dna_search_meta``, que recusava a
loja INTEIRA quando o espaço divergia, deixa de ser lido: ele impedia a
convivência que o produto quer vender.

**Postgres only**, como a 0004 e a 0012: o store pgvector não existe num
self-host SQLite (lá o ``SqliteVecRecordSearchProvider`` mantém a sua própria
loja, um arquivo por scope, com a sua própria escada de migrations).

Sem downgrade: as migrações do DNA são forward-only.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_search_docs_by_dims"
down_revision = "0012_turn_outcome"
branch_labels = None
depends_on = None


#: As cinco larguras, escritas à mão (ver o docstring: uma revisão não importa
#: a constante de runtime). ⚠️ O bool é "dá para indexar com ANN?" — 2000 é o
#: teto do ivfflat/hnsw no pgvector, medido, não suposto.
_DIMS: tuple[tuple[int, bool], ...] = (
    (384, True),
    (768, True),
    (1024, True),
    (1536, True),
    (3072, False),   # acima do teto de 2000 do ivfflat/hnsw — varredura exata
)

_LEGACY = "dna_search_docs"


def _qualify(schema: str | None, table: str) -> str:
    return f"{schema}.{table}" if schema else table


def _has_table(bind, schema: str | None, table: str) -> bool:
    return sa.inspect(bind).has_table(table, schema=schema)


def _vector_width(bind, schema: str | None, table: str) -> int | None:
    """A largura tipada na coluna ``embedding``, lida do catálogo.

    ``format_type`` devolve ``vector(384)``; ``atttypmod`` guarda a largura
    diretamente e é o que se lê aqui — sem parsear texto. ``None`` quando a
    coluna não existe ou não é ``vector`` (uma base a meio caminho).
    """
    row = bind.execute(
        sa.text(
            "SELECT a.atttypmod, t.typname "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_type t ON t.oid = a.atttypid "
            "WHERE n.nspname = :schema AND c.relname = :table "
            "AND a.attname = 'embedding' AND NOT a.attisdropped"
        ),
        {"schema": schema or "public", "table": table},
    ).first()
    if row is None or row[1] != "vector":
        return None
    return int(row[0])


def _create_table(schema: str | None, dims: int, indexable: bool) -> None:
    table = f"dna_search_docs_{dims}"
    qualified = _qualify(schema, table)
    # Mesma forma da tabela que o store já usava, MAIS ``model_id``:
    #   id         — chave surrogada (o plano de busca fundido referencia por id)
    #   text_hash  — o que faz ``index()`` idempotente (texto igual não reembeda)
    #   tenant ''  — o sentinela canônico de "base / sem tenant"
    #   model_id   — o ESPAÇO. '' só existe em linha herdada de antes de 0013
    #   fts        — coluna gerada, sempre em sincronia com ``body``
    op.execute(f"""
CREATE TABLE IF NOT EXISTS {qualified} (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    tenant     TEXT NOT NULL DEFAULT '',
    model_id   TEXT NOT NULL DEFAULT '',
    text_hash  TEXT NOT NULL,
    title      TEXT,
    snippet    TEXT,
    body       TEXT NOT NULL,
    embedding  vector({dims}),
    fts        tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(body, ''))) STORED,
    CONSTRAINT {table}_ident_key UNIQUE (scope, kind, name, tenant, model_id)
)
""")
    # Lookup + filtro de tenant. ``model_id`` vem logo depois de ``scope``
    # porque agora ele está em TODO predicado de leitura — a busca nunca lê
    # duas espaços de uma vez.
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {table}_lookup "
        f"ON {qualified} (scope, model_id, kind, tenant)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {table}_fts ON {qualified} USING gin (fts)"
    )
    if indexable:
        # Plano denso: IVFFlat sobre distância de cosseno. IVFFlat (e não HNSW)
        # mantém o custo de construção trivial para as lojas pequenas com que
        # este adapter começa; ``lists=100`` é o default documentado do pgvector
        # para corpus pequeno. O índice é ACELERADOR — a corretude do ranking
        # não depende dele, e trocá-lo por HNSW não toca a consulta.
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {table}_embedding "
            f"ON {qualified} USING ivfflat (embedding vector_cosine_ops) "
            "WITH (lists = 100)"
        )


def _adopt_legacy(bind, schema: str | None) -> None:
    """A ``dna_search_docs`` que já existe VIRA a tabela da sua dimensão.

    Renomeia tabela, índices e a constraint única, acrescenta ``model_id`` e o
    preenche a partir de ``dna_search_meta`` — sem mover linha e sem perder o
    índice. Ver o docstring do módulo para as alternativas descartadas.
    """
    width = _vector_width(bind, schema, _LEGACY)
    if width is None:
        # Tabela presente sem coluna ``embedding`` do tipo ``vector`` — não é
        # uma loja de busca que esta revisão reconheça. Parar é a única leitura
        # honesta: renomeá-la seria adotar algo que não sabemos o que é.
        raise RuntimeError(
            f"{_qualify(schema, _LEGACY)} exists but has no vector 'embedding' "
            "column — refusing to adopt a table this revision cannot identify. "
            "Inspect it by hand and either drop it or rename it out of the way."
        )
    known = [d for d, _ in _DIMS]
    if width not in known:
        # ⭐ Dimensão inédita falha ALTO e aponta a migration que falta. Jamais
        # cria tabela por conta própria, jamais arredonda para a vizinha.
        raise RuntimeError(
            f"{_qualify(schema, _LEGACY)} holds vector({width}) embeddings and "
            f"this revision only knows {known}. A new width needs a NEW "
            f"migration creating dna_search_docs_{width} (+ indexes) and "
            f"{width} in dna.adapters.search.dimensions.SUPPORTED_DIMS. "
            "Refusing to guess."
        )

    target = f"dna_search_docs_{width}"
    legacy_q = _qualify(schema, _LEGACY)
    target_q = _qualify(schema, target)

    # O ``model_id`` das linhas existentes vem do meta que o store já mantinha
    # para recusar mistura — é o dado, não uma inferência.
    model_id = None
    if _has_table(bind, schema, "dna_search_meta"):
        model_id = bind.execute(
            sa.text(
                f"SELECT value FROM {_qualify(schema, 'dna_search_meta')} "
                "WHERE key = 'embedding_model_id'"
            )
        ).scalar()
    rows = bind.execute(sa.text(f"SELECT count(*) FROM {legacy_q}")).scalar() or 0
    if rows and not model_id:
        raise RuntimeError(
            f"{legacy_q} has {rows} indexed rows but "
            f"{_qualify(schema, 'dna_search_meta')} does not say which embedding "
            "space they belong to. Labelling them with an invented model_id "
            "would enter them into searches of a space that is not theirs. "
            "Set dna_search_meta.embedding_model_id to the model that produced "
            "them, or truncate the table and re-index."
        )

    op.execute(f"ALTER TABLE {legacy_q} RENAME TO {target}")
    # Os índices SEGUEM a tabela, mas com o nome antigo. Renomeá-los é o que faz
    # uma base migrada e uma base nova ficarem indistinguíveis — e o que impede
    # o ``CREATE INDEX IF NOT EXISTS`` abaixo de criar uma SEGUNDA cópia de cada
    # um, pagando escrita para sempre por um índice duplicado que ninguém pediu.
    for old, new in (
        (f"{_LEGACY}_pkey", f"{target}_pkey"),
        (f"{_LEGACY}_scope_kind_name_tenant_key", f"{target}_ident_key"),
        (f"{_LEGACY}_lookup", f"{target}_lookup"),
        (f"{_LEGACY}_fts", f"{target}_fts"),
        (f"{_LEGACY}_embedding", f"{target}_embedding"),
    ):
        op.execute(sa.text(f"""
            DO $$
            BEGIN
                IF to_regclass('{_qualify(schema, old)}') IS NOT NULL
                   AND to_regclass('{_qualify(schema, new)}') IS NULL THEN
                    ALTER INDEX {_qualify(schema, old)} RENAME TO {new};
                END IF;
            END $$;
        """))

    op.execute(
        f"ALTER TABLE {target_q} ADD COLUMN IF NOT EXISTS model_id TEXT "
        "NOT NULL DEFAULT ''"
    )
    if model_id:
        op.execute(
            sa.text(
                f"UPDATE {target_q} SET model_id = :m WHERE model_id = ''"
            ).bindparams(m=model_id)
        )

    # A chave única passa a incluir o espaço: o MESMO documento embeddado por
    # dois modelos são duas linhas, e a antiga chave as recusaria.
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = '{target_q}'::regclass
                  AND conname = '{target}_ident_key'
                  AND array_length(conkey, 1) = 4
            ) THEN
                ALTER TABLE {target_q} DROP CONSTRAINT {target}_ident_key;
                ALTER TABLE {target_q} ADD CONSTRAINT {target}_ident_key
                    UNIQUE (scope, kind, name, tenant, model_id);
            END IF;
        END $$;
    """))
    # O índice de lookup ganha ``model_id``; o antigo (sem ele) não serve mais
    # os predicados e só pagaria manutenção.
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = '{target}_lookup'
                  AND n.nspname = '{schema or "public"}'
                  AND i.indnatts = 3
            ) THEN
                DROP INDEX {_qualify(schema, f'{target}_lookup')};
            END IF;
        END $$;
    """))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # [dialect] a loja pgvector é pg-only (ver o docstring).

    schema = op.get_context().version_table_schema

    # A extensão PRIMEIRO: sem ela o tipo ``vector`` não existe.
    #
    # ⚠️ ``IF NOT EXISTS`` não torna isto seguro sob concorrência, e isso foi
    # MEDIDO (a 0010 escreveu a medição, e a escada de migrations do store
    # pgvector repetia o mesmo bloco): o Postgres verifica e cria em dois
    # passos, sem lock entre eles. Sob xdist, seis processos rodaram isto ao
    # mesmo tempo e cinco morreram em ``pg_extension_name_index``. Os
    # containers do dna-cloud rodam a migração no CMD de boot — duas réplicas
    # subindo juntas são exatamente este caso.
    op.execute(sa.text("""
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION WHEN duplicate_object OR unique_violation THEN
            NULL;  -- outro processo ganhou a corrida; o resultado é o mesmo
        END $$;
    """))

    # A adoção vem ANTES do CREATE: a tabela velha vira a de 384 e o
    # ``CREATE TABLE IF NOT EXISTS`` daquela largura passa a ser inócuo. Na
    # ordem inversa, o rename colidiria com a tabela recém-criada e os 170
    # documentos ficariam órfãos numa tabela sem nome de dimensão.
    if _has_table(bind, schema, _LEGACY):
        _adopt_legacy(bind, schema)

    for dims, indexable in _DIMS:
        _create_table(schema, dims, indexable)


def downgrade() -> None:
    # Forward-only, como a baseline (docs/PORT-CONTRACT.md § "Schema
    # migrations"): a recuperação é backup/re-seed, não downgrade.
    raise NotImplementedError("DNA schema migrations are forward-only")
