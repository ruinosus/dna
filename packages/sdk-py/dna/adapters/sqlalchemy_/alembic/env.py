"""Alembic environment for the DNA SqlAlchemySource schema.

Two entry paths share this file:

1. **In-process, at ``SqlAlchemySource.connect()``** — the library applies
   its own schema to the consumer's database, as it always has. The source
   passes its live ``Connection`` in through ``config.attributes`` and
   Alembic runs on it (no second engine, no separate event loop).
2. **``alembic revision --autogenerate`` / ``alembic check``** at the
   sdk-py root, for a developer evolving the schema. That path builds its
   own engine from ``-x url=...``.

``target_metadata`` is the ONE table model (``..schema.build_metadata``)
that ``SqlAlchemySource`` itself binds to, so autogenerate compares the
code's idea of the schema against the database's. That comparison is the
whole point of i-038.
"""
from __future__ import annotations

from alembic import context

# Absolute, not relative: Alembic loads env.py by file path, so this module
# has no parent package to resolve a relative import against.
from dna.adapters.sqlalchemy_.schema import (
    build_metadata, compare_type, include_object, make_include_name,
)


def _is_pg(dialect_name: str) -> bool:
    return dialect_name == "postgresql"


def _configure_common(**kw):
    schema = context.config.attributes.get("dna_schema")
    dialect = kw.pop("_dialect")
    tables = build_metadata(is_pg=_is_pg(dialect), schema=schema)
    context.configure(
        target_metadata=tables.metadata,
        include_object=include_object,
        include_name=make_include_name(schema),
        compare_type=compare_type,
        # Server defaults are deliberately NOT compared: the same default
        # round-trips with different text per backend ('' vs ''::text,
        # 1 vs '1'), which produces noise, not signal. The drift this guard
        # exists to catch (a column present in code, absent in the database)
        # is caught by table/column/type/nullability comparison.
        compare_server_default=False,
        # [dialect] pg keeps the version table inside the DNA schema so a
        # database hosting several DNA schemas tracks each independently.
        version_table_schema=schema,
        include_schemas=bool(schema),
        **kw,
    )


def run_migrations_offline() -> None:
    url = context.config.get_main_option("sqlalchemy.url")
    dialect = "postgresql" if url and url.startswith("postgres") else "sqlite"
    _configure_common(url=url, literal_binds=True, _dialect=dialect)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Path 1: a live Connection handed in by SqlAlchemySource.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _configure_common(connection=connection,
                          _dialect=connection.dialect.name)
        with context.begin_transaction():
            context.run_migrations()
        return

    # Path 2: the alembic CLI, building its own engine.
    from sqlalchemy import engine_from_config, pool

    cfg = context.config.get_section(context.config.config_ini_section, {})
    x_url = context.get_x_argument(as_dictionary=True).get("url")
    if x_url:
        cfg["sqlalchemy.url"] = x_url
    engine = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        _configure_common(connection=conn, _dialect=conn.dialect.name)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
