"""s-pg-schema-identifier-guard — the SQL source validates its Postgres schema
identifier once at construction (trusted-config-only allowlist), closing the
latent SQL injection vector from f-string-interpolating an unvalidated schema
into the migration DDL / control-table statements. Inherited from the retired
raw Postgres adapter (s-retire-raw-sql-adapters) — SqlAlchemySource enforces
the same allowlist. Tests only __init__ — no server contacted (lazy engine).
"""
from __future__ import annotations

import pytest

from dna.adapters.sqlalchemy_ import SqlAlchemySource

_PG_URL = "postgresql+asyncpg://u:p@nowhere.invalid/db"


def test_valid_schema_identifiers_accepted():
    for schema in ("public", "dna", "tenant_acme", "_private", "s1"):
        src = SqlAlchemySource(_PG_URL, schema=schema)
        assert src._schema == schema


def test_default_schema_is_none_used_as_public():
    # No explicit schema → None; every use site falls back to 'public'.
    assert SqlAlchemySource(_PG_URL)._schema is None


def test_sqlite_dialect_ignores_schema_but_still_validates():
    # The identifier is validated regardless of dialect (fail fast on a
    # config typo), then discarded on sqlite (no namespaced schemas).
    assert SqlAlchemySource("sqlite+aiosqlite:///:memory:", schema="ok")._schema is None
    with pytest.raises(ValueError):
        SqlAlchemySource("sqlite+aiosqlite:///:memory:", schema="a b")


@pytest.mark.parametrize("bad", [
    "public; DROP TABLE dna_documents",
    "a b",                  # space
    "a-b",                  # hyphen
    'a"b',                  # quote
    "Public",               # uppercase (unquoted PG folds, allowlist is strict)
    "1schema",              # leading digit
    "",                     # empty
    "schema--",             # comment-ish
    "dna.documents",        # dotted
])
def test_invalid_schema_identifiers_rejected(bad):
    with pytest.raises(ValueError):
        SqlAlchemySource(_PG_URL, schema=bad)
