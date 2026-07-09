"""Forward-only numbered migrations for the sqlite-vec search store.

This is the debt rsh-memory-similarity-evolution (f-embeddings-ddl-debt) calls
out: in the SDK DNA was extracted from, the embeddings sidecar table had NO
owning migration — its DDL was created out-of-band. Here the search store's
schema is OWNED by the shared migration contract (``adapters/_migrations.py``,
``run_migrations``): every table is created by a numbered, append-only,
idempotent migration recorded in the store's own ``schema_migrations`` control
table, so a re-boot against an up-to-date store applies nothing.

The vec0 virtual table needs the embedding width baked into its DDL, and that
width is a property of the active ``EmbeddingPort`` (384 for the fake floor and
all-MiniLM). ``build_migrations(dims)`` interpolates the width into migration 1;
the resulting Mapping is still fed through the SAME ``run_migrations`` runner —
the migration owns the DDL, it just parametrizes the vector width. A ``meta``
row pins ``embedding_dims`` + ``model_id`` so a later boot against a store built
for a different embedding space fails loud instead of silently mixing vectors.
"""
from __future__ import annotations


def build_migrations(dims: int) -> dict[int, str]:
    """Return the forward-only migration map for a store with ``dims``-wide
    embeddings. Keyed by positive int version, ascending; each value is one
    ``executescript`` payload (SQLite dialect)."""
    if dims < 1:
        raise ValueError(f"embedding dims must be positive, got {dims}")
    return {
        1: f"""
-- Owning DDL for the whole search store (closes f-embeddings-ddl-debt).
--
-- search_docs: the metadata + source text of every indexed record. rowid is
-- the join key into the two virtual tables. text_hash makes index() idempotent
-- (re-indexing unchanged text is a no-op). tenant '' is the canonical
-- "base / no tenant" sentinel (overlay rows carry the tenant name).
CREATE TABLE IF NOT EXISTS search_docs (
    rowid      INTEGER PRIMARY KEY AUTOINCREMENT,
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    tenant     TEXT NOT NULL DEFAULT '',
    text_hash  TEXT NOT NULL,
    title      TEXT,
    snippet    TEXT,
    text       TEXT NOT NULL,
    UNIQUE (scope, kind, name, tenant)
);

CREATE INDEX IF NOT EXISTS search_docs_lookup
    ON search_docs (scope, kind, tenant);

-- Dense plane: a sqlite-vec vec0 virtual table. doc_rowid mirrors the
-- search_docs rowid so a KNN hit joins straight back to its metadata.
CREATE VIRTUAL TABLE IF NOT EXISTS search_vec USING vec0(
    doc_rowid INTEGER PRIMARY KEY,
    embedding float[{dims}]
);

-- Lexical plane: FTS5 over the same text, rowid == search_docs rowid, so
-- bm25() ranks join back the same way.
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(text);

-- Store identity: which embedding space these vectors live in. A boot that
-- finds a different (dims, model_id) refuses rather than mix incomparable
-- vectors.
CREATE TABLE IF NOT EXISTS search_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
""",
    }
