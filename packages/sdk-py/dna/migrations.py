"""Public schema-migration PORT — the forward-only numbered runner.

This is a NEUTRAL mechanism. It knows nothing about any consumer, any table, or
any product: it orders a ``Mapping[int, payload]`` by version, skips versions the
caller's control table already records, applies the rest in ascending order, and
tolerates a store newer than the binary (forward-only). The caller owns EVERYTHING
specific — its migrations, its control table (its own name, so N consumers coexist
in one database with zero collision), its DSN, and WHEN it runs (its own boot).

That neutrality is the point: dna-cloud's copilot consumes this for its
``copilot_thread`` schema today; a future DNA Live / DNA Marketplace consumes the
SAME runner for its own tables tomorrow — and this module never changes, never
enumerates them, never depends on them. None is obligatory. The SDK ships the
mechanism; each consumer brings its policy (open-core boundary).

Usage (the shape every consumer follows — cf. the SDK's own search stores):

    from dna.migrations import run_migrations

    async def ensure_control_table(): ...   # CREATE the consumer's OWN control table
    async def fetch_applied() -> list[int]: ...
    async def apply_version(version, payload): ...   # apply + record, consumer's atomicity

    applied = await run_migrations(
        {1: [...ddl statements...]},          # version → payload (payload shape is yours)
        ensure_control_table=ensure_control_table,
        fetch_applied=fetch_applied,
        apply_version=apply_version,
        dialect="Postgres(mything)",
    )

The runner itself lives in :mod:`dna.adapters._migrations` (where the SDK's search
stores use it); this module is its stable public name for out-of-tree consumers.
"""

from __future__ import annotations

from dna.adapters._migrations import PayloadT, run_migrations

__all__ = ["run_migrations", "PayloadT"]
