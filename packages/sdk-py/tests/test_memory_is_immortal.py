"""A memory is never hard-deleted — proved against a REAL store, both dialects.

i-130. The contradiction this closes was between two statements, both written
down and only one true. ``dna.memory.forget`` says a memory is *"NEVER
hard-deleted (auditable, point-in-time reconstructable, revivable)"* and the
Engram descriptor repeats it; ``test_ordinary_kinds_are_deletable`` said an
Engram is generically deletable, and it PASSED. Measured 06/08/2026, in both
dialects, through the same function the MCP delete tool calls: the row went, its
three ``dna_versions`` rows went with it, and ``forget`` afterwards raised
``KeyError: not found``. All three words fell together. The founder decided on
07/08/2026 that the promise survives and the behaviour falls.

WHY THIS FILE IS NOT ``test_generic_delete.py``. That file asks
``delete_refusal(port)`` — a pure function over a registry — against a fake
kernel whose ``delete_instance`` is a list append. It is the right test for the
CATALOGUE, and it is blind to the only question that matters here: *does the row
survive a delete driven through the real store?* The refusal that mattered had
to be measured the way the defect was, so every case below drives
``Kernel.delete_instance`` against a live ``SqlAlchemySource`` and then COUNTS
ROWS — instances and versions — instead of trusting a return value.

THE MUTANTS, and each is one line:

* **drop ``record.invalidate-only``** from
  ``dna/extensions/helix/kinds/engram.kind.yaml`` → the Engram falls back to the
  deletable default BY DERIVATION and every ``refuses`` test here goes red. This
  is the principal one: the fix IS the declaration, and if somebody ever adds an
  ``if kind == "Engram"`` on the delete path this mutant stops being red while
  the refusal keeps working — which is how a guard starts passing for the wrong
  reason.
* **move the gate from ``WritePipeline.delete`` up into
  ``delete_instance_impl``** → ``test_the_gate_is_below_the_generic_tool`` goes
  red. That is the shape of the original bug one level over: the two refusals
  that already existed were enforced at the generic TOOL, and every other door
  (REST's memory delete, the CLI, the internal callers) went straight to the
  kernel and never asked.
* **make the refusal a bare ``Exception``** → the family assertion goes red, and
  every face that relays ``KernelRefusal`` would deliver a documented refusal in
  the shape of a crash.
* **have ``forget`` delete instead of stamping** → the survival assertions after
  ``forget`` go red. The way out has to actually be a way out.
"""
from __future__ import annotations

import os
import tempfile
import uuid

import pytest
import pytest_asyncio

from dna.kernel import Kernel
from dna.kernel.errors import CapabilityRefusal, DeleteRefused, KernelRefusal

_ENGRAM_AV = "github.com/ruinosus/dna/v1"
_SCOPE = "probe"
_PG_URL = os.environ.get("DATABASE_URL")
_needs_pg = pytest.mark.skipif(
    not _PG_URL, reason="DATABASE_URL not set — the pg dialect row is skipped",
)


def _engram(name: str, summary: str) -> dict:
    """A VALID Engram — ``area``/``surface_when``/``source_refs``/``affect``/
    ``summary`` are all required, and a write that skips one is refused for the
    wrong reason."""
    return {
        "apiVersion": _ENGRAM_AV, "kind": "Engram",
        "metadata": {"name": name},
        "spec": {
            "area": "Feature/f-probe",
            "surface_when": ["feature_touched"],
            "source_refs": ["Story/s-probe"],
            "affect": "regret",
            "summary": summary,
        },
    }


async def _count(source, table, kind: str) -> int:
    """Rows of ``kind`` in ``table``, counted in the store itself."""
    from sqlalchemy import func, select

    async with source._engine.connect() as conn:  # noqa: SLF001 — the point is the STORE
        return int((await conn.execute(
            select(func.count()).select_from(table).where(table.c.kind == kind)
        )).scalar_one())


async def _kernel_on(source) -> Kernel:
    k = Kernel.auto()
    k.source(source)
    return k


@pytest_asyncio.fixture
async def sqlite_source():
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    fd, path = tempfile.mkstemp(prefix="dna-i130-", suffix=".db")
    os.close(fd)
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{path}")
    await src.connect()
    yield src
    await src.close()
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest_asyncio.fixture
async def pg_source():
    """One source per test in its own throwaway schema — the isolation the rest
    of the suite uses, for the same reason (the revisions run on ``connect()``
    and a shared schema collides on ``alembic_version``)."""
    import asyncpg

    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    schema = f"dna_i130_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(_PG_URL)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    src = SqlAlchemySource(
        _PG_URL.replace("postgresql://", "postgresql+asyncpg://", 1), schema=schema)
    await src.connect()
    try:
        yield src
    finally:
        await src.close()
        c = await asyncpg.connect(_PG_URL)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()


# ── the row, and its history, survive the delete ────────────────────────────


async def _delete_refuses_and_nothing_is_lost(source):
    """The measurement of 06/08/2026, re-run and inverted.

    Three writes first, because the defect that mattered was not the row: it was
    ``dna_versions`` 3 → 0 in the same transaction. A guard that only counted
    instances would pass on a fix that still destroyed the history an ``as_of``
    read reconstructs from."""
    kernel = await _kernel_on(source)
    for i in range(3):
        await kernel.write_instance(
            _SCOPE, "Engram", "m-1", _engram("m-1", f"revisão {i}"))

    before_instances = await _count(source, source.instances, "Engram")
    before_versions = await _count(source, source.versions, "Engram")
    assert before_instances == 1
    assert before_versions >= 1, (
        "the floor: with no version rows the history assertion below would pass "
        "vacuously and this guard would have stopped guarding"
    )

    with pytest.raises(DeleteRefused) as ei:
        await kernel.delete_instance(
            _SCOPE, "Engram", "m-1", api_version=_ENGRAM_AV)
    assert "INVALIDATE-ONLY" in str(ei.value)
    assert "forget" in str(ei.value), "the refusal must name the way out"

    assert await _count(source, source.instances, "Engram") == before_instances
    assert await _count(source, source.versions, "Engram") == before_versions, (
        "the delete took the version history with it — which is exactly what "
        "made 'auditable, point-in-time reconstructable, revivable' false"
    )
    assert await kernel.get_instance(_SCOPE, "Engram", "m-1") is not None

    # …and the way out actually works, on the same instance, after the refusal.
    from dna.memory import forget

    out = await forget(kernel, _SCOPE, "m-1")
    assert out["valid_to"], "forget must stamp the world-time end"
    assert out["already_forgotten"] is False
    survivor = await kernel.get_instance(_SCOPE, "Engram", "m-1")
    assert survivor is not None, "forget DEMOTES; it never removes"
    assert survivor["spec"]["valid_to"] == out["valid_to"]
    assert await _count(source, source.instances, "Engram") == before_instances

    # A forgotten memory is still not deletable — the demotion is not a consent.
    with pytest.raises(DeleteRefused):
        await kernel.delete_instance(
            _SCOPE, "Engram", "m-1", api_version=_ENGRAM_AV)
    assert await kernel.get_instance(_SCOPE, "Engram", "m-1") is not None


@pytest.mark.asyncio
async def test_sqlite_refuses_the_hard_delete_and_keeps_the_history(sqlite_source):
    await _delete_refuses_and_nothing_is_lost(sqlite_source)


@_needs_pg
@pytest.mark.asyncio
async def test_postgres_refuses_the_hard_delete_and_keeps_the_history(pg_source):
    """The dialect the measurement was taken on, and the one that carries the
    ``valid_at`` column slice 3 of the topology just built. A delete removes the
    instance from the reach of that column entirely, which is what makes the
    world-time axis an investment in something a delete can erase."""
    await _delete_refuses_and_nothing_is_lost(pg_source)


# ── an ordinary Kind is untouched: this is a Kind rule, not a delete freeze ──


@pytest.mark.asyncio
async def test_an_ordinary_kind_still_deletes(sqlite_source):
    """Mutant: refuse on ``plane == "record"``, or on any other property the
    Engram happens to share. Story is a record-plane-adjacent, versioned,
    ordinary Kind and it must still go — a gate that froze every delete would
    pass every assertion above and be a different, larger bug."""
    kernel = await _kernel_on(sqlite_source)
    await kernel.write_instance(_SCOPE, "Story", "s-x", {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
        "metadata": {"name": "s-x"},
        "spec": {"title": "T", "description": "uma story comum", "status": "todo"},
    })
    assert await _count(sqlite_source, sqlite_source.instances, "Story") == 1
    await kernel.delete_instance(
        _SCOPE, "Story", "s-x",
        api_version="github.com/ruinosus/dna/sdlc/v1")
    assert await _count(sqlite_source, sqlite_source.instances, "Story") == 0


# ── the gate is BELOW the generic tool, which is the whole point ─────────────


@pytest.mark.asyncio
async def test_the_gate_is_below_the_generic_tool(sqlite_source):
    """The defect this fix exists to not repeat, stated as a test.

    ``delete_refusal`` already refused two categories and was consulted by
    exactly one caller — the generic MCP delete. Every other door (the REST
    memory delete, the CLI, the internal callers) reaches
    ``Kernel.delete_instance`` directly. This case bypasses the application
    layer entirely, exactly as those doors do, and still gets the refusal.

    Mutant: move the check into ``delete_instance_impl`` and this goes red while
    ``test_generic_delete.py`` stays green — a fix that guards the door somebody
    was looking at."""
    kernel = await _kernel_on(sqlite_source)
    await kernel.write_instance(_SCOPE, "Engram", "m-2", _engram("m-2", "direto"))
    with pytest.raises(DeleteRefused):
        await kernel.delete_instance(
            _SCOPE, "Engram", "m-2", api_version=_ENGRAM_AV)
    assert await kernel.get_instance(_SCOPE, "Engram", "m-2") is not None


@pytest.mark.asyncio
async def test_the_refusal_is_catchable_as_the_FAMILY_not_by_name(sqlite_source):
    """Mutant: declare ``DeleteRefused`` as a bare ``Exception`` (or move it to
    ``CapabilityRefusal``).

    ``KernelRefusal`` is the base every face relays with ONE ``except``; without
    it a documented refusal reaches the client as an unexplained failure, which
    is the defect that created the base. ``CapabilityRefusal`` would be worse
    than useless here: it says *the store cannot*, sending the caller to look for
    a different deployment — while the store could have removed the row, which
    is precisely the problem, and the remedy (``forget``) is a different
    REQUEST that works on any store."""
    kernel = await _kernel_on(sqlite_source)
    await kernel.write_instance(_SCOPE, "Engram", "m-3", _engram("m-3", "família"))
    with pytest.raises(KernelRefusal):
        await kernel.delete_instance(
            _SCOPE, "Engram", "m-3", api_version=_ENGRAM_AV)
    assert issubclass(DeleteRefused, KernelRefusal)
    assert issubclass(DeleteRefused, PermissionError), (
        "additive, never a re-parenting: the MCP delete tool catches it by name "
        "and every face maps a PermissionError to an honest denial"
    )
    assert not issubclass(DeleteRefused, CapabilityRefusal)


@pytest.mark.asyncio
async def test_nothing_is_deleted_before_the_refusal(sqlite_source):
    """Mutant: run the gate AFTER ``plan_target_delete`` / after the first
    ``_persist_delete``. A refusal raised halfway through a cascade leaves the
    store in a state nobody asked for, and the caller reads an exception that
    says the delete did not happen."""
    kernel = await _kernel_on(sqlite_source)
    await kernel.write_instance(_SCOPE, "Engram", "m-4", _engram("m-4", "átomo"))
    await kernel.write_instance(_SCOPE, "Engram", "m-5", _engram("m-5", "átomo"))
    before = await _count(sqlite_source, sqlite_source.instances, "Engram")
    with pytest.raises(DeleteRefused):
        await kernel.delete_instance(
            _SCOPE, "Engram", "m-4", api_version=_ENGRAM_AV)
    assert await _count(sqlite_source, sqlite_source.instances, "Engram") == before
