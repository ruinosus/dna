"""The embedding-dimension → table map, and the ONE place that knows it.

``s-indice-por-dimensao``. ``dna_search_docs`` was dynamic in everything but one
thing::

    scope · kind · name · tenant   ← already COLUMNS
    embedding vector(384)          ← the only fixed one, because vector(N) is
                                     the column's TYPE

The founder's decision (08/08/2026, on the measurement in ``i-104``): **one
table per DIMENSION, created by migration.** Not a dynamic table, not one column.

⛔ Why a dynamic table was refused — the first reason is a hard house rule
--------------------------------------------------------------------------

  ``CLAUDE.md``: *"Data-access code never runs DDL."*

That is not a preference. It is what makes the schema **property of a migration,
reviewable in a PR**. A table created at runtime makes the schema depend on what
users did, and then nobody can answer *"what is the schema?"* by reading the
repo.

The second reason is volume: one table per collection × tenant is HUNDREDS of
tables, each carrying its own ANN index — expensive in memory.

⭐ The way out: the dimension space is small and nearly closed
-------------------------------------------------------------

======  ====================================
  384   MiniLM (``all-MiniLM-L6-v2``, ours)
  768   base
 1024   large
 1536   ``text-embedding-3-small`` / ada
 3072   ``text-embedding-3-large``
======  ====================================

Five tables, by migration (``0013_uma_tabela_por_dimensao``). Everything else
that used to want DDL becomes an INSERT:

===================================================  =========================
a new collection (``scope``)                          INSERT — always was
a new tenant                                          INSERT — always was
a new ``model_id`` on a dimension we already have     nothing; just write
an UNSEEN dimension                                   a migration, in a
                                                      reviewed PR — the right
                                                      answer
===================================================  =========================

Routing needs no new configuration
----------------------------------

``EmbeddingPort`` already publishes ``dims`` (``kernel/protocols.py``). The
store reads ``kernel.embedding_dims`` and knows which table to use. No heuristic,
no config key, and **never** the model's name.

⚠️ ``model_id`` is a FILTER, not a label
----------------------------------------

The port's contract is explicit: *"vectors from providers with different
``model_id`` are NOT comparable."* Two collections at 1536 embedded by different
models live in the SAME table (same column type) and **must never appear in the
same search**. So ``model_id`` is a column that every read and every write
filters on — the thing that makes co-existence safe. A table shared by two
spaces without that filter would rank one space's vectors against the other's
and call the result relevance.
"""
from __future__ import annotations

#: The dimensions that have a table. Kept in lockstep with
#: ``0013_uma_tabela_por_dimensao`` by
#: ``tests/test_search_dimension_routing.py`` — adding a number here without
#: writing the migration turns that guard RED, which is exactly the signal a
#: silent ``CREATE TABLE`` used to swallow.
#:
#: ⚠️ The migration does NOT import this tuple, and must not: a revision is a
#: frozen historical fact and cannot re-render itself from today's code (the
#: rule 0012's docstring states). The guard compares two independent lists —
#: that comparison is the whole point.
SUPPORTED_DIMS: tuple[int, ...] = (384, 768, 1024, 1536, 3072)

#: Table name prefix. ``dna_search_docs`` (unsuffixed) is the RETIRED name —
#: migration 0013 renames it to its dimension, carrying rows and indexes with it.
TABLE_PREFIX = "dna_search_docs_"


class UnsupportedEmbeddingDims(ValueError):
    """An embedding width with no table — raised LOUD, never worked around.

    Carries the missing width so a caller can report it, and a message that
    names the fix (write the next migration). The store must never create the
    table itself, and must never fall back to a neighbouring width: a 768-wide
    vector stored in a 384 column is not a degraded answer, it is a type error
    at best and a silent mixing of incomparable spaces at worst.
    """

    def __init__(self, dims: int) -> None:
        self.dims = dims
        super().__init__(
            f"no search table for embedding width {dims}. The dimensions with a "
            f"table are {', '.join(str(d) for d in SUPPORTED_DIMS)} — created by "
            "alembic revision 0013_uma_tabela_por_dimensao. A new width needs a "
            "NEW migration adding "
            f"{TABLE_PREFIX}{dims} (+ its indexes) and {dims} in "
            "dna.adapters.search.dimensions.SUPPORTED_DIMS. The store will not "
            "create it: data-access code never runs DDL."
        )


def search_table(dims: int) -> str:
    """The search table for an embedding width. Pure — no I/O, no DDL, no guess.

    Raises :class:`UnsupportedEmbeddingDims` for a width with no migration. That
    raise is the whole safety property: the alternative designs (create it,
    round to the nearest, share one table) each mix incomparable vectors.
    """
    if dims not in SUPPORTED_DIMS:
        raise UnsupportedEmbeddingDims(dims)
    return f"{TABLE_PREFIX}{dims}"
