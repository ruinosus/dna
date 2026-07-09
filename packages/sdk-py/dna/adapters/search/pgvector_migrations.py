"""Forward-only numbered migrations for the pgvector search store.

The Postgres/scale sibling of ``migrations.py`` (the sqlite-vec store). Same
debt story (f-embeddings-ddl-debt): the search store's schema is OWNED by the
shared migration contract (``adapters/_migrations.py``, ``run_migrations``) —
every table is created by a numbered, append-only, idempotent migration recorded
in the store's own ``{schema}.dna_search_migrations`` control table, so a re-boot
against an up-to-date store applies nothing.

The ``vector(dims)`` column needs the embedding width baked into its DDL, and
that width is a property of the active ``EmbeddingPort`` (384 for the fake floor
and all-MiniLM). ``build_pg_migrations(dims)`` interpolates the width into
migration 1; the resulting Mapping is fed through the SAME ``run_migrations``
runner. A ``dna_search_meta`` row pins ``embedding_dims`` + ``model_id`` so a
later boot against a store built for a different embedding space fails loud
instead of silently mixing vectors.

Payload shape (Postgres dialect): each version maps to a ``list[str]`` of
statements — asyncpg can't multi-statement a single ``execute``, and the runner
applies each list inside one transaction per version. The ``{schema}``
placeholder is interpolated by the provider's ``apply_version`` (the schema
identifier is validated once at provider construction — trusted config, never
request input).
"""
from __future__ import annotations


def build_pg_migrations(dims: int) -> dict[int, list[str]]:
    """Return the forward-only migration map for a pgvector search store with
    ``dims``-wide embeddings. Keyed by positive int version, ascending; each
    value is a ``list[str]`` of statements (Postgres dialect) with a ``{schema}``
    placeholder the runner interpolates.

    Migration 1 owns the whole store schema. ``CREATE EXTENSION vector`` is the
    first statement: pgvector must be present (the CI job runs the
    ``pgvector/pgvector:pg16`` image; a plain ``postgres:16`` would fail here
    loudly — the honest signal that the extension is missing).
    """
    if dims < 1:
        raise ValueError(f"embedding dims must be positive, got {dims}")

    # dna_search_docs: metadata + source text + the dense embedding of every
    # indexed record, all in one table (unlike sqlite-vec's sidecar virtual
    # tables — pgvector is a native column type). id is the surrogate key;
    # text_hash makes index() idempotent; tenant '' is the canonical
    # "base / no tenant" sentinel (overlay rows carry the tenant name). fts is
    # a generated tsvector column so the lexical plane is always in sync with
    # body. The {{schema}} braces are doubled to survive this f-string; the
    # runner substitutes the real schema.
    create_docs = f"""
CREATE TABLE IF NOT EXISTS {{schema}}.dna_search_docs (
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

    return {
        1: [
            # pgvector must be installed in the target database. IF NOT EXISTS
            # makes the boot idempotent; a missing extension fails loud here.
            "CREATE EXTENSION IF NOT EXISTS vector",
            create_docs,
            # Metadata lookup + tenant filter.
            "CREATE INDEX IF NOT EXISTS dna_search_docs_lookup "
            "ON {schema}.dna_search_docs (scope, kind, tenant)",
            # Lexical plane: GIN over the generated tsvector.
            "CREATE INDEX IF NOT EXISTS dna_search_docs_fts "
            "ON {schema}.dna_search_docs USING gin (fts)",
            # Dense plane: IVFFlat over cosine distance. IVFFlat (not HNSW) keeps
            # build cost trivial for the small stores this adapter starts with;
            # lists=100 is pgvector's documented small-corpus default. The index
            # is an ANN accelerator — correctness (the conformance ranking) does
            # not depend on it; it can be swapped for HNSW without touching the
            # query. Created IF NOT EXISTS so re-boot is a no-op.
            "CREATE INDEX IF NOT EXISTS dna_search_docs_embedding "
            "ON {schema}.dna_search_docs USING ivfflat (embedding vector_cosine_ops) "
            "WITH (lists = 100)",
            # Store identity: which embedding space these vectors live in. A boot
            # that finds a different (dims, model_id) refuses rather than mix
            # incomparable vectors.
            "CREATE TABLE IF NOT EXISTS {schema}.dna_search_meta ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        ],
    }
