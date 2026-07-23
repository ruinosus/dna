"""The shared forward-only migration runner (``adapters/_migrations.py``).

Scope SHRANK with i-038. This file used to cover three layers: the runner
algorithm, plus old-DB→new-code compatibility for ``SqlAlchemySource`` on
both dialects. ``SqlAlchemySource`` no longer uses this runner — its schema
is Alembic's now (``adapters/sqlalchemy_/migrate.py``), so those two layers
moved/retired:

  - the legacy-DB compat fixtures replayed ``SQLITE_MIGRATIONS`` /
    ``PG_MIGRATIONS``, which no longer exist. The equivalent guarantee for
    the Alembic era -- a pre-Alembic database boots clean -- is
    ``tests/test_alembic_legacy_baseline.py``.
  - schema-vs-code agreement, which the old ladder had NO test for at all,
    is ``tests/test_schema_autogenerate_guard.py``.

What remains here is the runner itself, which is NOT dead code: the
sqlite-vec and pgvector search providers still drive their DDL through it
(``adapters/search/sqlite_vec.py``, ``adapters/search/pgvector.py``). Those
stores bake the embedding width into their DDL at runtime
(``build_migrations(dims)``), which a static Alembic revision file cannot
express -- so they keep the numbered runner deliberately. See i-038.
"""
from __future__ import annotations

import pytest

from dna.adapters._migrations import run_migrations

pytestmark = pytest.mark.asyncio


async def test_public_seam_reexports_the_real_runner():
    """`dna.migrations` is the stable public name for out-of-tree consumers
    (dna-cloud's copilot, a future DNA Live / Marketplace). It MUST be the same
    object as the internal runner — a copy would drift (mutation: the re-export
    points elsewhere → dies)."""
    import dna.migrations as public

    assert public.run_migrations is run_migrations
    assert set(public.__all__) == {"run_migrations", "PayloadT"}


# ---------------------------------------------------------------------------
# 1. Helper unit tests (no real DB — recording fakes)
# ---------------------------------------------------------------------------


class _Recorder:
    """Callable trio over an in-memory 'control table' (a set of ints)."""

    def __init__(self, already_applied: set[int] | None = None) -> None:
        self.control: set[int] | None = (
            set(already_applied) if already_applied is not None else None
        )
        self.events: list[tuple[str, object]] = []

    async def ensure_control_table(self) -> None:
        self.events.append(("ensure", None))
        if self.control is None:
            self.control = set()

    async def fetch_applied(self) -> list[int]:
        self.events.append(("fetch", None))
        assert self.control is not None, "ensure_control_table must run first"
        return sorted(self.control)

    async def apply_version(self, version: int, payload: object) -> None:
        self.events.append(("apply", (version, payload)))
        assert self.control is not None
        self.control.add(version)

    def kwargs(self) -> dict:
        return dict(
            ensure_control_table=self.ensure_control_table,
            fetch_applied=self.fetch_applied,
            apply_version=self.apply_version,
        )


async def test_helper_applies_in_ascending_order_and_returns_applied():
    rec = _Recorder()
    migrations = {3: "c", 1: "a", 2: "b"}  # deliberately unsorted keys
    out = await run_migrations(migrations, **rec.kwargs())
    assert out == [1, 2, 3]
    applies = [ev for ev in rec.events if ev[0] == "apply"]
    assert applies == [("apply", (1, "a")), ("apply", (2, "b")), ("apply", (3, "c"))]
    # bootstrap-first contract: ensure precedes fetch precedes any apply
    assert [e[0] for e in rec.events[:2]] == ["ensure", "fetch"]


async def test_helper_skips_applied_versions_and_is_idempotent():
    rec = _Recorder(already_applied={1, 2})
    out = await run_migrations({1: "a", 2: "b", 3: "c"}, **rec.kwargs())
    assert out == [3]
    # second run: nothing pending → [] and zero apply calls
    rec.events.clear()
    out2 = await run_migrations({1: "a", 2: "b", 3: "c"}, **rec.kwargs())
    assert out2 == []
    assert not [ev for ev in rec.events if ev[0] == "apply"]


async def test_helper_tolerates_store_newer_than_binary(caplog):
    """Forward-only tolerance: control table knows v4 but the binary only
    ships 1-3 → no crash, nothing re-applied, loud warning."""
    rec = _Recorder(already_applied={1, 2, 3, 4})
    with caplog.at_level("WARNING", logger="dna.adapters._migrations"):
        out = await run_migrations({1: "a", 2: "b", 3: "c"}, **rec.kwargs())
    assert out == []
    assert any("unknown to this code" in r.message for r in caplog.records)


async def test_helper_rejects_non_positive_or_non_int_versions():
    rec = _Recorder()
    with pytest.raises(ValueError, match="positive ints"):
        await run_migrations({0: "zero"}, **rec.kwargs())
    with pytest.raises(ValueError, match="positive ints"):
        await run_migrations({"1": "str-key"}, **rec.kwargs())  # type: ignore[dict-item]


async def test_helper_failure_keeps_prior_versions_and_stops():
    """A failing migration aborts the run; already-applied versions stay
    recorded so the next boot retries only from the failure point."""
    rec = _Recorder()

    async def apply_version(version: int, payload: object) -> None:
        if version == 2:
            raise RuntimeError("boom")
        await rec.apply_version(version, payload)

    kwargs = rec.kwargs() | {"apply_version": apply_version}
    with pytest.raises(RuntimeError, match="boom"):
        await run_migrations({1: "a", 2: "b", 3: "c"}, **kwargs)
    assert rec.control == {1}
    # next boot: v1 skipped, v2 retried (now passing), v3 applied
    out = await run_migrations({1: "a", 2: "b", 3: "c"}, **rec.kwargs())
    assert out == [2, 3]


