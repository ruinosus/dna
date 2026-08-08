"""Forward-only schema-migration runner for the EMBEDDABLE search store.

Scope narrowed twice.

**i-038** took ``SqlAlchemySource``'s schema to Alembic
(``adapters/sqlalchemy_/migrate.py``), which brings revision checksums and
``autogenerate`` drift detection the numbered ladder could not.

⭐ **``s-indice-por-dimensao`` took the pgvector store too**, and it matters that
this docstring used to argue the opposite. It said:

    their DDL is parametrized at RUNTIME by the active ``EmbeddingPort``'s
    vector width […] An Alembic revision is a static file authored ahead of
    time; it cannot know the width the consumer will boot with.

The premise was wrong, and one observation is what showed it: the space of
widths is **small and nearly closed** (384 · 768 · 1024 · 1536 · 3072). A static
revision does not have to *know* the width — it can create a table for each and
let the store ROUTE by ``kernel.embedding_dims``. What read as an open parameter
was a five-element enumeration, and the whole case for a runtime ladder rested
on it. Revision ``0013_uma_tabela_por_dimensao`` now owns the pgvector store,
``pgvector_migrations.py`` is gone, and that provider runs zero DDL — which is
what ``CLAUDE.md`` asked for all along ("Data-access code never runs DDL").

What remains here is **sqlite-vec** (``adapters/search/sqlite_vec.py``, control
table ``schema_migrations`` inside its own store file), plus the public
``dna.migrations`` re-export. The same move does not obviously transfer to it:
its store is a FILE PER SCOPE created wherever the consumer points ``db_dir``,
so there is no shared database for a revision ladder to be applied to. That is
a different problem, not this one left half-done.

The contract it encodes (documented in ``docs/PORT-CONTRACT.md``
§ "Schema migrations"):

  - **Forward-only, numbered.** Migrations are a ``Mapping[int, payload]``
    keyed by positive integer version. They are applied in ascending
    numeric order. There is no downgrade path — recovery is
    backup/re-seed.
  - **Append-only.** A version already recorded in the adapter's control
    table is NEVER re-applied (and must never be edited in code — add a
    new version instead).
  - **Idempotent boot.** Running against an up-to-date store applies
    nothing and returns ``[]`` — this is what every service boot does.
  - **Control table owned by the adapter.** The helper never touches
    storage itself; the adapter supplies three async callables bound to
    its own connection/control-table dialect. sqlite-vec's
    ``schema_migrations``, in its own store file, keeps its exact name and
    shape. Note that neither the Source's control tables (Alembic's
    ``alembic_version`` since i-038) nor the pgvector store's retired
    ``dna_search_migrations`` (Alembic since ``s-indice-por-dimensao``) are
    among them any more.

Why callables instead of a driver abstraction: the callers have deliberately
different atomicity semantics and payload shapes — sqlite-vec applies one SQL
script per version with ``executescript`` and records/commits separately, while
the (now retired) pgvector caller wrapped a list of statements plus the record
in one transaction. ``apply_version`` owns "apply + record, with MY atomicity"
so the helper can unify ordering/skip/reporting without flattening that. The
seam is kept even with one caller left inside the SDK, because
``dna.migrations`` re-exports this runner as public API: a consumer's own store
is the second caller.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Iterable, Mapping, TypeVar

logger = logging.getLogger(__name__)

PayloadT = TypeVar("PayloadT")


async def run_migrations(
    migrations: Mapping[int, PayloadT],
    *,
    ensure_control_table: Callable[[], Awaitable[None]],
    fetch_applied: Callable[[], Awaitable[Iterable[int]]],
    apply_version: Callable[[int, PayloadT], Awaitable[None]],
    dialect: str = "SQL",
) -> list[int]:
    """Apply every pending migration in ascending version order.

    Args:
        migrations: version → payload. Keys MUST be positive ints; the
            payload shape is the adapter's business (SQLite: one script
            ``str``; Postgres: ``list[str]`` of statements).
        ensure_control_table: create the adapter's control table if it
            doesn't exist yet (bootstrap — runs FIRST, exactly once).
        fetch_applied: return the version numbers already recorded in
            the control table.
        apply_version: apply ONE version's payload AND record it in the
            control table, honoring the adapter's own atomicity
            (transaction) semantics. Called once per pending version,
            in ascending order. An exception aborts the run — versions
            already applied stay recorded; the failed one is retried on
            the next boot.
        dialect: human label for log lines (``"SQLite"``, ``"Postgres"``).

    Returns:
        The version numbers applied by THIS run, in application order.
        ``[]`` means the store was already up to date (the idempotent
        re-boot case).
    """
    bad = [v for v in migrations if not isinstance(v, int) or v < 1]
    if bad:
        raise ValueError(
            f"migration versions must be positive ints, got {sorted(bad, key=repr)!r}"
        )

    await ensure_control_table()
    applied = {int(v) for v in await fetch_applied()}

    unknown = applied - set(migrations)
    if unknown:
        # Forward-only tolerance: an OLDER binary booting against a NEWER
        # store must not crash (nor try to "fix" anything). Surface it,
        # because writes from old code against a newer schema may misbehave.
        logger.warning(
            "%s control table records migration version(s) %s unknown to this "
            "code (store is newer than the binary) — leaving them untouched.",
            dialect, sorted(unknown),
        )

    applied_now: list[int] = []
    for version in sorted(migrations):
        if version in applied:
            continue
        logger.info("Applying %s migration v%d", dialect, version)
        await apply_version(version, migrations[version])
        applied_now.append(version)
    return applied_now
