"""Transaction time — "what did the system believe at T-1?" (s-memory-as-of).

The founder's criterion for this spike, verbatim: **write a memory, supersede
it, and recover the PREVIOUS belief state.** That is
:func:`test_the_founders_criterion` — everything else here defends the edges
where a lazier implementation would still pass it.

Why the criterion needs a real store: memory tests in this repo run over
``FilesystemWritableSource``, which declares ``versions=True`` and keeps NO
history (``list_versions`` → ``[]``). A belief state cannot be reconstructed from
a store that keeps one row per document, so these tests use ``SqlAlchemySource``
over sqlite — the same adapter production runs on postgres, same code path, no
postgres required.

Two axes, and conflating them is the mistake this whole feature exists to avoid:

- ``now=``    — WORLD time. Shifts the ``valid_to`` filter, still hands back
                TODAY's spec. Already existed.
- ``as_of=``  — TRANSACTION time. Resolves each hit from the version the store
                RECORDED at or before that instant. New.

``test_now_is_not_as_of`` is the one that would have caught us shipping the
first while claiming the second.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from dna.adapters.sqlalchemy_ import SqlAlchemySource
from dna.extensions.helix import HelixExtension
from dna.kernel import Kernel
from dna.memory import forget, recall, remember
from dna.memory.as_of import AsOfUnsupported, normalize_as_of

pytestmark = pytest.mark.asyncio

SCOPE = "s"


@pytest_asyncio.fixture
async def kernel(tmp_path):
    """A kernel over the REAL versioned store (sqlite dialect of the pg adapter)."""
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'as-of.db'}")
    await src.connect()  # runs the migrations — creates `versions`
    k = Kernel()
    k.load(HelixExtension())
    k.source(src)
    try:
        yield k
    finally:
        await src.close()


def _spec(summary: str, area: str = "infra", **extra) -> dict:
    """A schema-valid Engram spec. The required fields are the Kind's, not
    this feature's — kept in one place so a test reads as its own point."""
    return {
        "summary": summary,
        "area": area,
        "affect": "triumph",
        "surface_when": ["feature_touched"],
        "source_refs": ["s-memory-as-of"],
        **extra,
    }


async def _tick() -> datetime:
    """A timestamp strictly between two writes.

    ``created_at`` is written at microsecond resolution, but the sleep is not
    superstition: without it two writes inside the same event-loop turn can land
    on timestamps a test cannot cut BETWEEN, and the failure would look like a
    bug in as-of rather than in the test.
    """
    await asyncio.sleep(0.01)
    t = datetime.now(timezone.utc)
    await asyncio.sleep(0.01)
    return t


async def _summary_at(kernel, when, query="postgres") -> list[str]:
    res = await recall(kernel, SCOPE, query, k=10, as_of=when)
    return [h.get("summary") for h in res["hits"]]


# ── the criterion ──────────────────────────────────────────────────────────

async def test_the_founders_criterion(kernel):
    """Write a memory, supersede it, recover the PREVIOUS belief state.

    The spike passes if and only if this passes, and the assertion is about the
    OLD belief — not about the shape of the response, not about a flag.
    """
    await remember(
        kernel, SCOPE, name="mem-db",
        spec=_spec("we run postgres 14", "infra/db"),
    )

    t_before = await _tick()

    # Supersede: the memory is bi-temporally demoted and points at its successor.
    await forget(kernel, SCOPE, "mem-db", superseded_by="mem-db-v2")
    await remember(
        kernel, SCOPE, name="mem-db-v2",
        spec=_spec("we run postgres 16", "infra/db"),
    )

    # NOW — the present belief. The old memory is gone from recall.
    now_hits = [h.get("summary") for h in (
        await recall(kernel, SCOPE, "postgres", k=10)
    )["hits"]]
    assert "we run postgres 16" in now_hits
    assert "we run postgres 14" not in now_hits, (
        "a superseded memory must not surface in a live recall"
    )

    # T-1 — the belief state BEFORE the supersession. This is the criterion.
    then = await recall(kernel, SCOPE, "postgres", k=10, as_of=t_before)
    then_hits = [h.get("summary") for h in then["hits"]]
    assert "we run postgres 14" in then_hits, (
        "as_of must recover the belief the system held BEFORE the supersession "
        f"— got {then_hits}"
    )
    assert "we run postgres 16" not in then_hits, (
        "a memory written AFTER as_of did not exist then and must not appear"
    )
    assert then["as_of"] == normalize_as_of(t_before)
    assert then["as_of_truncated"] == []


# ── the edges a lazier implementation would still pass ─────────────────────

async def test_now_is_not_as_of(kernel):
    """World time and transaction time are different axes.

    A memory RECORDED today about a fact valid last year: a world-time read at
    last year finds it (it was true then), a transaction-time read at last year
    must not (nobody believed it yet). Passing ``now=`` off as ``as_of=`` would
    fail exactly here, and nowhere else.
    """
    long_ago = datetime.now(timezone.utc) - timedelta(days=365)
    before_anything = await _tick()
    await remember(
        kernel, SCOPE, name="mem-late",
        spec=_spec("the outage was caused by a full disk", "infra/db",
                   valid_from=long_ago.isoformat()),
    )

    world = await recall(kernel, SCOPE, "outage", k=10, now=long_ago)
    assert any(h.get("summary", "").startswith("the outage") for h in world["hits"]), (
        "world time: the fact WAS valid a year ago, so now= must surface it"
    )

    belief = await recall(kernel, SCOPE, "outage", k=10, as_of=before_anything)
    assert belief["hits"] == [], (
        "transaction time: nothing was believed before the memory was recorded"
    )


async def test_as_of_returns_the_spec_as_recorded_not_todays(kernel):
    """A corrected memory answers with its OLD text, not the corrected one.

    Filtering by timestamp while still loading the CURRENT document would pass
    the supersession criterion (the doc drops out on ``valid_to``) and fail
    here — the doc is live at both instants and only its CONTENT moved.
    """
    await remember(
        kernel, SCOPE, name="mem-owner",
        spec=_spec("the owner is Ana", "team"),
    )
    t_before = await _tick()
    await remember(
        kernel, SCOPE, name="mem-owner",
        spec=_spec("the owner is Bruno", "team"),
    )

    assert "the owner is Bruno" in await _summary_at(
        kernel, datetime.now(timezone.utc), "owner"
    )
    assert await _summary_at(kernel, t_before, "owner") == ["the owner is Ana"]


async def test_as_of_does_not_write(kernel):
    """A read of the past must not touch the present.

    ``recall`` reconsolidates every hit it surfaces (cue append + confidence
    bump). Under ``as_of`` that is a contradiction, and it is also destructive:
    Engram keeps 3 versions, so a reconsolidating historical read would prune the
    very history it is reading.
    """
    await remember(
        kernel, SCOPE, name="mem-quiet",
        spec=_spec("kafka is the bus", "infra"),
    )
    src = kernel._source
    before = await src.list_versions(SCOPE, "Engram", "mem-quiet")

    res = await recall(kernel, SCOPE, "kafka", k=10, as_of=datetime.now(timezone.utc))
    assert [h["name"] for h in res["hits"]] == ["mem-quiet"]

    after = await src.list_versions(SCOPE, "Engram", "mem-quiet")
    assert [v["version"] for v in after] == [v["version"] for v in before], (
        "as_of recall must not reconsolidate — a historical read that writes is "
        "a contradiction, and it prunes the history it reads"
    )


async def test_truncated_history_is_reported_not_guessed(kernel):
    """"No record" is a blind spot, never "no memory".

    Engram is capped at ``VERSION_CHURN_RETENTION`` = 3. Past that, version 1 is
    pruned and the store genuinely cannot know what it held at an early instant.
    The honest answer is to name the memory in ``as_of_truncated`` — NOT to drop
    it silently (reads as "you had no such memory") and NOT to fall back to the
    current spec (reads as "this is what you believed", which is a fabrication).
    """
    await remember(
        kernel, SCOPE, name="mem-churn",
        spec=_spec("revision 0", "infra"),
    )
    t_early = await _tick()
    for i in range(1, 6):  # 5 more writes — v1 is pruned long before the last
        await remember(
            kernel, SCOPE, name="mem-churn",
            spec=_spec(f"revision {i}", "infra"),
        )

    src = kernel._source
    kept = [v["version"] for v in await src.list_versions(SCOPE, "Engram", "mem-churn")]
    assert 1 not in kept, f"precondition: v1 must have been pruned, kept={kept}"

    res = await recall(kernel, SCOPE, "revision", k=10, as_of=t_early)
    assert res["as_of_truncated"] == ["mem-churn"]
    assert [h["name"] for h in res["hits"]] == [], (
        "a memory we cannot answer for must not be answered for with today's spec"
    )


async def test_hits_carry_the_transaction_stamp(kernel):
    """The answer says WHICH recorded version it came from.

    Without this a caller cannot tell a precise historical hit from a stale one
    resolved to some other instant, and 'trust me' is not a provenance claim.
    """
    await remember(
        kernel, SCOPE, name="mem-stamp",
        spec=_spec("redis caches sessions", "infra"),
    )
    res = await recall(kernel, SCOPE, "redis", k=10, as_of=datetime.now(timezone.utc))
    hit = res["hits"][0]
    assert hit["as_of_version"] == 1
    assert hit["recorded_at"] <= res["as_of"]


async def test_store_without_history_refuses(tmp_path):
    """A store that cannot answer REFUSES — it does not approximate.

    ``FilesystemWritableSource`` declares ``versions=True`` and keeps none. If
    as-of degraded to a normal read there, a self-hosted deployment would get
    confident, plausible, wrong history — the failure mode that is worse than no
    feature at all.
    """
    from dna.adapters.filesystem.writable import FilesystemWritableSource

    src = FilesystemWritableSource(str(tmp_path))
    k = Kernel()
    k.load(HelixExtension())
    k.source(src)
    await remember(
        kernel := k, SCOPE, name="mem-fs",
        spec=_spec("anything", "infra"),
    )
    with pytest.raises(AsOfUnsupported):
        await recall(kernel, SCOPE, "anything", k=5, as_of=datetime.now(timezone.utc))

    # and it says so BEFORE the read, so a face can 501 instead of trying
    assert k._source.capabilities().as_of_reads is False


async def test_without_as_of_nothing_changes(kernel):
    """Retrocompat, asserted rather than assumed.

    Same recall, twice: once through the untouched call, once with the argument
    explicitly ``None``. Identical hits, no ``as_of`` keys in the envelope, and
    reconsolidation still ON (the version count still moves) — the behaviour
    every existing caller depends on.
    """
    await remember(
        kernel, SCOPE, name="mem-plain",
        spec=_spec("nginx terminates tls", "infra"),
    )
    a = await recall(kernel, SCOPE, "nginx", k=5)
    b = await recall(kernel, SCOPE, "nginx", k=5, as_of=None)
    assert [h["name"] for h in a["hits"]] == [h["name"] for h in b["hits"]] == ["mem-plain"]
    assert "as_of" not in a and "as_of_truncated" not in a
    assert "as_of" not in b

    versions = await kernel._source.list_versions(SCOPE, "Engram", "mem-plain")
    assert max(v["version"] for v in versions) > 1, (
        "reconsolidation must still fire on a normal recall"
    )


# ── normalization ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("given,expected", [
    ("2026-08-01T12:00:00Z", "2026-08-01T12:00:00+00:00"),
    ("2026-08-01T12:00:00+00:00", "2026-08-01T12:00:00+00:00"),
    ("2026-08-01T14:00:00+02:00", "2026-08-01T12:00:00+00:00"),
    ("2026-08-01T12:00:00", "2026-08-01T12:00:00+00:00"),  # naive ⇒ UTC, never local
])
async def test_normalize_as_of(given, expected):
    """``created_at`` is compared as TEXT, so both sides must be the same shape.

    A naive timestamp is read as UTC on purpose: reading it as local time would
    silently shift every answer by the developer's offset, and the shift would
    be invisible to anyone in UTC.
    """
    assert normalize_as_of(given) == expected


async def test_normalize_as_of_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_as_of("last tuesday")


async def test_iso_strings_sort_chronologically():
    """The lexicographic comparison the SQL relies on IS the chronological one.

    Guarding the assumption rather than trusting it: fixed-width ISO fields with
    one fixed offset sort correctly, including across the microsecond boundary
    (``'.'`` > ``'+'``), which is the case a hand-check gets wrong.
    """
    stamps = [
        "2026-08-01T12:00:00+00:00",
        "2026-08-01T12:00:00.500000+00:00",
        "2026-08-01T12:00:01+00:00",
        "2026-08-01T12:01:00+00:00",
    ]
    assert sorted(stamps) == stamps
