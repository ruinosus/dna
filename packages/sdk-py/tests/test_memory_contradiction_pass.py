"""Contradiction detection, kernel-bound — the consolidate dry-run carries it.

The pure verdict lives in ``test_memory_contradiction.py``. This file proves the
three things only a real kernel over a real versioned store can prove:

1. ``consolidate(dry_run=True)`` REPORTS contradictions and changes nothing —
   including under ``apply=True``, which still only expires stale memories;
2. the survivor proposal rests on TRANSACTION time read from
   ``dna_versions.created_at`` (degrau 0's second clock, asked in the other
   direction by :func:`dna.memory.verbs.first_recorded_at`) — and specifically on
   the FIRST recorded version, so recall's reconsolidation rewrites cannot
   promote a stale belief by making it look freshly written;
3. ``remember`` REFUSES a malformed claim before writing anything.

Store choice mirrors ``test_memory_as_of.py``: ``SqlAlchemySource`` over sqlite
is the same adapter production runs on postgres. ``FilesystemWritableSource``
keeps no history at all, which is exactly why the fallback is tested against it.
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.adapters.sqlalchemy_ import SqlAlchemySource
from dna.extensions.helix import HelixExtension
from dna.kernel import Kernel
from dna.memory import consolidate, first_recorded_at, recall, remember

pytestmark = pytest.mark.asyncio

SCOPE = "s"
_REASON = "a concrete reason long enough for the affect validator to accept it"


@pytest_asyncio.fixture
async def kernel(tmp_path):
    """A kernel over the REAL versioned store (sqlite dialect of the pg adapter)."""
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'contradiction.db'}")
    await src.connect()
    k = Kernel()
    k.load(HelixExtension())
    k.source(src)
    try:
        yield k
    finally:
        await src.close()


@pytest_asyncio.fixture
async def historyless_kernel(tmp_path):
    """A store that keeps NO version history — the transaction clock is absent."""
    base = tmp_path / "fs"
    base.mkdir()
    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(base_dir=str(base)))
    return k


def _spec(summary: str, obj: str, **extra) -> dict:
    """A schema-valid Engram claiming ONE approval state for the Kind Livro."""
    return {
        "summary": summary,
        "area": "KindDefinition/livro",
        "affect": "wistful",
        "affect_reason": _REASON,
        "surface_when": ["feature_touched"],
        "source_refs": ["s-grafo-2-contradicao"],
        "claims": [{"predicate": "approval", "object": obj}],
        **extra,
    }


async def _write_the_livro_pair(k) -> None:
    """The founder's living proof (2026-08-05), in the order it happened."""
    await remember(
        k, SCOPE, name="rem-livro-pendente",
        spec=_spec("O Kind Livro ainda precisa de aprovação.", "pending"),
    )
    await asyncio.sleep(0.01)  # two distinct transaction stamps, not one
    await remember(
        k, SCOPE, name="rem-livro-aprovado",
        spec=_spec("O Kind Livro foi aprovado pelo founder no portal.", "approved"),
    )


# ── 1. the pass reports, and changes nothing ────────────────────────────────


async def test_the_dry_run_reports_the_livro_contradiction(kernel):
    """The acceptance criterion, through the verb the story names as its home."""
    await _write_the_livro_pair(kernel)

    report = await consolidate(kernel, SCOPE, dry_run=True)

    (conflict,) = report["contradictions"]
    assert conflict["subject"] == "KindDefinition/livro"
    assert conflict["predicate"] == "approval"
    assert conflict["names"] == ["rem-livro-aprovado", "rem-livro-pendente"]
    assert conflict["decided_by"] == "rule"
    assert conflict["proposal"]["strategy"] == "await_confirmation"


async def test_the_pass_never_resolves_a_contradiction_even_with_apply(kernel):
    """``apply`` expires STALE memories. It has never had, and must not gain, a
    path that acts on a disagreement: the story's whole point is that the
    resolution is a human's."""
    await _write_the_livro_pair(kernel)

    await consolidate(kernel, SCOPE, apply=True)

    for name in ("rem-livro-pendente", "rem-livro-aprovado"):
        doc = await kernel.get_instance(SCOPE, "Engram", name)
        assert not (doc["spec"].get("valid_to")), f"{name} was demoted by the pass"
        assert not doc["spec"].get("superseded_by_memory")
    # and both are still recallable — nothing was hidden.
    hits = {h["name"] for h in (await recall(kernel, SCOPE, "Livro", k=10))["hits"]}
    assert {"rem-livro-pendente", "rem-livro-aprovado"} <= hits


async def test_a_workspace_without_claims_reports_no_contradictions(kernel):
    """Total backward compatibility: the keys appear, empty, and the pass costs
    what it always cost (no claim ⇒ no version-list read)."""
    await remember(kernel, SCOPE, name="rem-plain", spec={
        "summary": "nothing structured here",
        "area": "general", "affect": "triumph",
        "surface_when": ["feature_touched"], "source_refs": ["general"],
    })
    report = await consolidate(kernel, SCOPE, dry_run=True)
    assert report["contradictions"] == []
    assert report["undecided"] == []


async def test_without_dry_run_the_report_shape_is_unchanged(kernel):
    await _write_the_livro_pair(kernel)
    report = await consolidate(kernel, SCOPE)
    assert set(report) == {"evaluated", "stale", "archived", "applied"}


async def test_a_superseded_memory_is_not_a_contradiction(kernel):
    """The bi-temporal case, end to end: once the stale belief is properly
    demoted, the pass has nothing to report — it only ever compares memories the
    system believes AT THE SAME TIME."""
    await _write_the_livro_pair(kernel)
    from dna.memory import forget

    await forget(kernel, SCOPE, "rem-livro-pendente",
                 superseded_by="rem-livro-aprovado")

    report = await consolidate(kernel, SCOPE, dry_run=True)
    assert report["contradictions"] == []


# ── 2. the clock the proposal rests on ──────────────────────────────────────


async def test_the_proposal_uses_the_stores_transaction_clock(kernel):
    await _write_the_livro_pair(kernel)

    conflict = (await consolidate(kernel, SCOPE, dry_run=True))["contradictions"][0]
    assert conflict["proposal"]["basis"] == "recorded_at"
    assert conflict["proposal"]["suggested_keep"] == "rem-livro-aprovado"
    assert conflict["proposal"]["suggested_supersede"] == ["rem-livro-pendente"]


async def test_recall_reconsolidation_cannot_promote_the_stale_belief(kernel):
    """The reason :func:`first_recorded_at` reads the FIRST version and not the
    newest. ``recall`` rewrites every memory it surfaces (cue append + confidence
    bump), so "when was this last written" moves every time somebody looks —
    reading the newest stamp would let a much-recalled stale belief outrank the
    correction that replaced it.

    ONE recall on purpose: two versions is under ``VERSION_CHURN_RETENTION``'s
    cap of 3, so version 1 survives and the stamp is the FACT. Three recalls
    prune it, and the run then proves the fallback instead of this — which is
    exactly how this test first passed for the wrong reason (the mutation that
    reads the newest version survived it). The ``basis`` assertion is what stops
    that from happening again silently.
    """
    await _write_the_livro_pair(kernel)
    await recall(kernel, SCOPE, "precisa de aprovação", k=1)
    await asyncio.sleep(0.01)

    versions = await kernel._source.list_versions(SCOPE, "Engram", "rem-livro-pendente")
    assert len(versions) > 1, "the reconsolidation rewrite did not happen"
    assert max(v["version"] for v in versions) > 1
    newest = max(versions, key=lambda v: v["version"])["created_at"]
    aprovado = await kernel._source.list_versions(SCOPE, "Engram", "rem-livro-aprovado")
    assert str(newest) > str(aprovado[0]["created_at"]), (
        "the stale memory's NEWEST stamp must be the later one, or this test "
        "cannot tell the two readings apart"
    )

    report = await consolidate(kernel, SCOPE, dry_run=True)
    assert "recorded_at_approximate" not in report
    conflict = report["contradictions"][0]
    assert conflict["proposal"]["basis"] == "recorded_at"
    assert conflict["proposal"]["suggested_keep"] == "rem-livro-aprovado"


async def test_first_recorded_at_is_the_first_version(kernel):
    await _write_the_livro_pair(kernel)
    await recall(kernel, SCOPE, "Livro", k=10)  # ⇒ a version 2 on both memories

    stamps, approximate = await first_recorded_at(
        kernel, SCOPE, "Engram", ["rem-livro-pendente", "rem-livro-aprovado"],
    )
    assert approximate == []
    assert stamps["rem-livro-pendente"] < stamps["rem-livro-aprovado"]

    for name in ("rem-livro-pendente", "rem-livro-aprovado"):
        versions = await kernel._source.list_versions(SCOPE, "Engram", name)
        assert len(versions) > 1, "no rewrite ⇒ min and max cannot be told apart"
        assert stamps[name] == str(min(versions, key=lambda v: v["version"])["created_at"])


async def test_a_pruned_first_version_is_a_bound_and_can_only_LOSE(kernel):
    """``VERSION_CHURN_RETENTION`` caps Engram at 3, and reconsolidation reaches
    that in three glances — so in production most memories have lost version 1.
    The oldest RETAINED stamp then reads newer than the truth, which is sound in
    exactly one direction. Here the churned memory would WIN on it, so the whole
    proposal falls back to the authored clock and names the bound."""
    await _write_the_livro_pair(kernel)
    for _ in range(3):
        await recall(kernel, SCOPE, "precisa de aprovação", k=1)
        await asyncio.sleep(0.01)

    versions = await kernel._source.list_versions(SCOPE, "Engram", "rem-livro-pendente")
    assert min(v["version"] for v in versions) > 1, "version 1 was not pruned"

    report = await consolidate(kernel, SCOPE, dry_run=True)
    assert report["recorded_at_approximate"] == ["rem-livro-pendente"]
    assert report["contradictions"][0]["proposal"]["basis"] == "spec"


async def test_an_approximate_stamp_that_LOSES_still_decides(kernel):
    """The other direction, and the reason the bound is kept rather than
    dropped: a churned memory whose bound is still older than the winner's exact
    stamp is provably older, so the election stands on the transaction clock."""
    from dna.memory.contradiction import contradiction_report

    members = [
        ("rem-old", _spec("belief a", "pending")),
        ("rem-new", _spec("belief b", "approved")),
    ]
    conflict = contradiction_report(
        members,
        recorded_at={"rem-old": "2026-01-01T00:00:00+00:00",
                     "rem-new": "2026-08-01T00:00:00+00:00"},
        recorded_at_approximate=["rem-old"],
    )["contradictions"][0]
    assert conflict["proposal"]["basis"] == "recorded_at"
    assert conflict["proposal"]["suggested_keep"] == "rem-new"


async def test_a_historyless_store_falls_back_and_says_so(historyless_kernel):
    """The filesystem adapter keeps no versions. Detection still works — the
    verdict never depended on the clock — and the proposal reports that it fell
    back to the authored one instead of pretending it had a transaction stamp."""
    k = historyless_kernel
    await _write_the_livro_pair(k)

    stamps, approximate = await first_recorded_at(
        k, SCOPE, "Engram", ["rem-livro-pendente", "rem-livro-aprovado"],
    )
    assert (stamps, approximate) == ({}, [])

    conflict = (await consolidate(k, SCOPE, dry_run=True))["contradictions"][0]
    assert conflict["names"] == ["rem-livro-aprovado", "rem-livro-pendente"]
    assert conflict["proposal"]["basis"] == "spec"


# ── 3. the claim is refused at the verb, before anything is written ─────────


@pytest.mark.parametrize("bad, needle", [
    ("not a list", "claims must be a list"),
    ([{"object": "pending"}], "claims[0].predicate is required"),
    ([{"predicate": "approval", "polarity": "maybe"}], "claims[0].polarity"),
    ([{"predicate": "approval", "objekt": "typo"}], "unknown field(s)"),
])
async def test_remember_refuses_a_malformed_claim_and_writes_nothing(
    kernel, bad, needle,
):
    spec = _spec("uma memória com claim inválido", "pending")
    spec["claims"] = bad

    with pytest.raises(ValueError) as exc:
        await remember(kernel, SCOPE, name="rem-bad", spec=spec)
    assert needle in str(exc.value)
    assert await kernel.get_instance(SCOPE, "Engram", "rem-bad") is None


async def test_the_schema_refuses_the_same_claim_on_the_raw_write_door(kernel):
    """Two doors, one contract. ``write_instance`` bypasses the verb entirely,
    so the Engram schema has to say the same thing the validator says — a guard
    that only the convenience path calls is a guard the raw path walks past."""
    from dna.kernel.protocols import SpecValidationError

    spec = _spec("claim inválido pela porta crua", "pending")
    spec["claims"] = [{"predicate": "approval", "polarity": "maybe"}]
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Engram", "metadata": {"name": "rem-raw"}, "spec": spec,
    }
    with pytest.raises(SpecValidationError):
        await kernel.write_instance(SCOPE, "Engram", "rem-raw", raw)
    assert await kernel.get_instance(SCOPE, "Engram", "rem-raw") is None


async def test_an_unknown_claim_field_is_refused_by_the_schema_too(kernel):
    from dna.kernel.protocols import SpecValidationError

    spec = _spec("claim com campo inventado", "pending")
    spec["claims"] = [{"predicate": "approval", "objekt": "pending"}]
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Engram", "metadata": {"name": "rem-raw-2"}, "spec": spec,
    }
    with pytest.raises(SpecValidationError):
        await kernel.write_instance(SCOPE, "Engram", "rem-raw-2", raw)


async def test_a_valid_claim_round_trips_through_the_verb(kernel):
    await remember(
        kernel, SCOPE, name="rem-ok",
        spec=_spec("uma memória com claim válido", "pending"),
    )
    doc = await kernel.get_instance(SCOPE, "Engram", "rem-ok")
    assert doc["spec"]["claims"] == [
        {"predicate": "approval", "object": "pending", "polarity": "asserts"}
    ]
