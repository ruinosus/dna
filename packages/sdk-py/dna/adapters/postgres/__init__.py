"""Postgres-specific infrastructure that outlived the raw PostgresSource.

The raw ``PostgresSource`` was retired by s-retire-raw-sql-adapters — the
SQL path in Python is :class:`dna.adapters.sqlalchemy_.SqlAlchemySource`
(same tables, both dialects, zero data migration). What remains here is the
LISTEN/NOTIFY *subscriber* side of the kernel event bus, which is
conceptually independent of which adapter produced the writes.
"""
from dna.adapters.postgres.eventbus import PostgresEventBus

__all__ = ["PostgresEventBus"]
