"""``SqlAlchemySource.pg_search_binding`` — the sanctioned source→search wire.

i-069: the hosted MCP ran permanently lexical-degraded because no boot path
ever registered the pgvector provider. The binding is how a boot path derives
the provider's (dsn, schema) FROM the source it already opened — instead of
re-parsing environment URLs (and drifting from them).
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from dna.adapters.sqlalchemy_ import SqlAlchemySource  # noqa: E402


def test_sqlite_source_has_no_binding(tmp_path):
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path}/x.db")
    assert src.pg_search_binding() is None


def test_pg_source_binding_is_driverless_with_password_and_schema():
    pytest.importorskip("asyncpg")
    src = SqlAlchemySource("postgresql+asyncpg://u:sec@h:5432/db")
    dsn, schema = src.pg_search_binding()
    # Driverless (native asyncpg), password PRESERVED (the provider must be
    # able to actually connect — render_as_string hides it by default).
    assert dsn == "postgresql://u:sec@h:5432/db"
    assert schema == "public"


def test_pg_source_binding_carries_the_namespaced_schema():
    pytest.importorskip("asyncpg")
    src = SqlAlchemySource("postgresql+asyncpg://u@h/db", schema="dna_x")
    dsn, schema = src.pg_search_binding()
    assert schema == "dna_x"
