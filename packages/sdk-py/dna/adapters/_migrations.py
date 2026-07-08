"""Shared forward-only schema-migration runner (s-dna-migration-contract).

THE single implementation of the migration *algorithm* both SQL adapters
(``adapters/sqlite`` and ``adapters/postgres``) previously hand-rolled in
parallel. The contract it encodes (documented in
``docs/PORT-CONTRACT.md`` § "Schema migrations"):

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
    its own connection/control-table dialect. Existing control tables
    (SQLite ``schema_migrations``, Postgres ``{schema}.dna_schema_migrations``)
    keep their exact name and shape — full compat with existing DBs.

Why callables instead of a driver abstraction: the two callers have
deliberately different atomicity semantics (SQLite ``executescript`` per
version + separate record/commit; Postgres one transaction per version
wrapping statements + record) and different payload shapes (one SQL
script string vs a list of statements with a ``{schema}`` placeholder).
``apply_version`` owns "apply + record, with MY atomicity" so the helper
can unify ordering/skip/reporting without flattening those semantics.
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
