"""Record-search provider adapters (opt-in extras).

Nothing here is imported by the default SDK — importing ``dna`` or booting a
kernel must never pull ``sqlite-vec`` (guard:
``tests/test_search_import_isolation.py``). Install the extra and import the
adapter explicitly to register a real ``RecordSearchProvider``:

    pip install "dna-sdk[search-sqlite]"
    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider
    provider = SqliteVecRecordSearchProvider(kernel, db_dir=".dna-search")
    kernel.record_search_provider(provider)

The default embeddable adapter is ``sqlite_vec`` (sqlite-vec + FTS5 + RRF), the
offline/CI floor of the search plane (rsh-memory-similarity-evolution →
rec-embeddable-provider). It runs anywhere SQLite runs, with the deterministic
``FakeEmbeddingProvider`` as the zero-dependency embedding floor.
"""

from dna.adapters.search.rrf import reciprocal_rank_fusion

__all__ = ["reciprocal_rank_fusion"]
