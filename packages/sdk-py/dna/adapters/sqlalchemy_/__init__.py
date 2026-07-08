"""SqlAlchemySource — one SQL adapter, two dialects, same tables.

Production adapter (promoted from the i-216 spike by
``s-sqlalchemy-source-production``): SQLAlchemy Core 2.x async over
aiosqlite OR asyncpg, bound to the EXACT tables + migrations the raw
``SqliteSource`` / ``PostgresSource`` own — switching adapters is pure
instantiation, zero data migration. Requires the optional ``sql`` extra
(``pip install dna-sdk[sql]``); nothing in the default install imports
sqlalchemy. See docs/PORT-CONTRACT.md § "Using the SQLAlchemy adapter".
"""
from .source import SqlAlchemySource

__all__ = ["SqlAlchemySource"]
