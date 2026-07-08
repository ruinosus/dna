"""SPIKE (i-216) — SqlAlchemySource: SQLAlchemy Core 2.x async prototype.

NOT production code. This package exists to answer, with evidence, whether
SQLAlchemy Core should unify the SQLite + Postgres SQL adapters
(e-dna-public-extraction). Requires the optional ``sqlalchemy-spike`` extra
(``pip install dna-sdk[sqlalchemy-spike]``); nothing in the default
install imports it.
"""
from .source import SqlAlchemySource

__all__ = ["SqlAlchemySource"]
