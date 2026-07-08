"""s-pg-schema-identifier-guard — PostgresSource validates its schema identifier
once at construction (trusted-config-only allowlist), closing the latent SQL
injection vector from f-string-interpolating an unvalidated schema into ~40
statements. Tests only __init__ — no real Postgres needed (dummy pool).
"""
from __future__ import annotations

import pytest

from dna.adapters.postgres.source import PostgresSource


class _DummyPool:  # asyncpg.Pool stand-in — __init__ only stores it
    pass


def test_valid_schema_identifiers_accepted():
    for schema in ("public", "dna", "tenant_acme", "_private", "s1"):
        src = PostgresSource(_DummyPool(), schema=schema)
        assert src._schema == schema


def test_default_schema_is_public():
    assert PostgresSource(_DummyPool())._schema == "public"


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
        PostgresSource(_DummyPool(), schema=bad)
