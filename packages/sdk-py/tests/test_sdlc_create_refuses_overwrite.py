"""``create_story`` / ``create_issue`` / ``create_feature`` never destroy a
instance that is already there.

The hole: each of the three built a fresh spec and called
``kernel.write_instance`` with no existence check. ``write_instance`` is an
upsert keyed on the name, so an agent guessing (or re-trying, or working from a
stale board) obliterated the existing instance's status, timeline,
acceptance_criteria and definition_of_done — silently, and reported success.
"Create" is the ONE verb that must never be an update.

``create_issue`` had a second, quieter version of the same bug: it derived its
name from ``max(existing i-NNN) + 1``. Any enumeration that misses an instance —
a racing writer, an eventually-consistent read — computes a number that is
already taken, and the write then lands ON TOP of that Issue. It now probes the
name it intends to use.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application import sdlc as S
from dna.kernel import Kernel

_SCOPE = "board"


def _write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def kernel(tmp_path: Path) -> Kernel:
    base = tmp_path / ".dna"
    _write_yaml(base / _SCOPE / "Genome.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {},
    })
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return k


# ── the refusal ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_story_refuses_an_existing_name(kernel):
    await S.create_story(
        kernel, _SCOPE, "s-one", feature="f-x", description="the real one",
        acceptance_criteria=["Given A, when B, then C"],
        definition_of_done=["code+tests"],
    )
    await S.set_status(kernel, _SCOPE, "Story", "s-one", "in-progress")

    with pytest.raises(S.DocumentExists) as ei:
        await S.create_story(
            kernel, _SCOPE, "s-one", feature="f-y", description="a guess")

    msg = str(ei.value)
    assert "s-one" in msg and "Story" in msg      # names the instance…
    assert "in-progress" in msg                   # …and its current state

    spec = (await kernel.get_instance(_SCOPE, "Story", "s-one"))["spec"]
    assert spec["description"] == "the real one"
    assert spec["status"] == "in-progress"
    assert spec["acceptance_criteria"] == ["Given A, when B, then C"]
    assert len(spec["timeline"]) == 2             # create + the status flip


@pytest.mark.asyncio
async def test_create_feature_refuses_an_existing_name(kernel):
    await S.create_feature(
        kernel, _SCOPE, "f-one", title="T", description="the real one")
    with pytest.raises(S.DocumentExists, match="f-one"):
        await S.create_feature(
            kernel, _SCOPE, "f-one", title="T2", description="a guess")
    spec = (await kernel.get_instance(_SCOPE, "Feature", "f-one"))["spec"]
    assert spec["description"] == "the real one"


@pytest.mark.asyncio
async def test_the_refusal_points_at_the_update_verbs(kernel):
    """A refusal that does not say what to do instead just makes the agent retry
    with a different guess."""
    await S.create_story(
        kernel, _SCOPE, "s-one", feature="f-x", description="d",
        acceptance_criteria=["Given X"], definition_of_done=["done"])
    with pytest.raises(S.DocumentExists) as ei:
        await S.create_story(
            kernel, _SCOPE, "s-one", feature="f-x", description="d",
            acceptance_criteria=["Given X"], definition_of_done=["done"])
    msg = str(ei.value)
    assert "set_status" in msg and "comment" in msg


@pytest.mark.asyncio
async def test_overwrite_is_reachable_but_only_by_name(kernel):
    """The destructive semantics stay available to a caller that means it (a
    backfill / migration), because refusing outright would only push such a
    caller into hand-rolling ``kernel.write_instance`` with no timeline at all."""
    await S.create_story(
        kernel, _SCOPE, "s-one", feature="f-x", description="the old one",
        acceptance_criteria=["Given X"], definition_of_done=["done"])
    await S.create_story(
        kernel, _SCOPE, "s-one", feature="f-x", description="the new one",
        acceptance_criteria=["Given X"], definition_of_done=["done"],
        overwrite=True)
    spec = (await kernel.get_instance(_SCOPE, "Story", "s-one"))["spec"]
    assert spec["description"] == "the new one"


# ── create_issue: the auto-incremented name never lands on a live instance ──


class _HidingKernel:
    """The real kernel with ONE Issue hidden from ``query`` — the shape of every
    enumeration that can under-report (a concurrent writer, a read replica that
    has not caught up). ``get_instance`` still sees it.

    ⚠️ It hides BOTH row shapes on purpose. ``create_issue`` pushes a
    ``projection=["name"]`` down, and a projected row comes back FLAT
    (``{"name": ...}``) with no ``metadata`` envelope — so the original version
    of this stub, which only inspected ``row["metadata"]["name"]``, hid nothing
    at all. Every test built on it was green because the enumeration saw
    everything, i.e. it proved the opposite of what it claimed. A stub that
    cannot suppress the row cannot test what happens when the row is missing."""

    def __init__(self, inner: Any, hidden: str) -> None:
        self._inner = inner
        self._hidden = hidden

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    async def query(self, *a: Any, **kw: Any):
        async for row in self._inner.query(*a, **kw):
            if isinstance(row, dict):
                meta = row.get("metadata")
                name = meta.get("name") if isinstance(meta, dict) else row.get("name")
                if name == self._hidden:
                    continue
            yield row


@pytest.mark.asyncio
async def test_the_hiding_kernel_actually_hides(kernel):
    """The stub above is load-bearing; a stub that silently no-ops turns every
    test that uses it into a false green (which is exactly what happened)."""
    await S.create_issue(kernel, _SCOPE, "first", description="d")
    hiding = _HidingKernel(kernel, "i-001-first")
    seen = [r async for r in hiding.query(_SCOPE, "Issue", projection=["name"])]
    assert seen == [], f"the projected row was not suppressed: {seen}"


@pytest.mark.asyncio
async def test_a_missed_enumeration_never_destroys_the_document_it_missed(kernel):
    """What the atomic claim DOES guarantee when the enumeration is blind.

    With ``i-001-first`` invisible, ``max+1`` is 1 and the allocator aims at
    number 1 — but the name it writes is ``i-001-second``, which is free, so
    ``if_absent`` lets it through. Nothing is overwritten: the instance the
    enumeration missed keeps every byte.

    What it does NOT guarantee is the ID: two Issues now share ``i-001``. That
    is the open gap, and it is structural — the write path can claim a NAME
    atomically and the id is a NUMBER, so nothing short of making the number
    the whole name (``i-NNN``) or a number-keyed allocator can close it. This
    test asserts the real behavior rather than a comfortable one; it is the
    canary for that decision.
    """
    await S.create_issue(kernel, _SCOPE, "first", description="the real i-001")
    hiding = _HidingKernel(kernel, "i-001-first")

    out = await S.create_issue(hiding, _SCOPE, "second", description="the new one")

    kept = (await kernel.get_instance(_SCOPE, "Issue", "i-001-first"))["spec"]
    assert kept["description"] == "the real i-001", "the missed doc was destroyed"
    assert out["name"] == "i-001-second"


# ── the id is the NUMBER; the write path can only claim the NAME ────────────


def test_duplicate_issue_numbers_names_every_id_claimed_twice():
    """The detection, on the shape measured on the dna-cloud board 05/08/2026."""
    dupes = S.duplicate_issue_numbers([
        "i-094-board-unificado-um-so",
        "i-094-voz-so-na-surface",
        "i-095-terraform-fases-2-4-decisao",
        "i-096-tf-entra-nunca-importado",
        "s-not-an-issue",
        "",
    ])
    assert dupes == {94: ["i-094-board-unificado-um-so", "i-094-voz-so-na-surface"]}


def test_duplicate_issue_numbers_is_quiet_on_a_healthy_board():
    assert S.duplicate_issue_numbers(["i-001-a", "i-002-b", "i-003-c"]) == {}


def test_no_filter_over_the_enumeration_can_reject_the_number_it_produced():
    """Why ``create_issue`` does NOT try to skip 'taken' numbers.

    An earlier attempt at this fix added ``if candidate in taken_numbers:
    continue`` to the allocator loop. It read well and was dead code: the
    candidate is ``max(taken) + 1``, computed from that very list, so the test
    written to prove it still passed with the line deleted. The guard that
    works has to look at something the allocator did not read — the merged
    tree, in CI."""
    names = ["i-001-a", "i-002-b", "i-002-b-again", "i-003-c"]
    assert S.next_issue_number(names) not in set(S.duplicate_issue_numbers(names))
    assert S.next_issue_number(names) == 4
    # …and the collision that is already there is invisible to the allocator,
    # which is exactly why detection is a separate, later step.
    assert S.duplicate_issue_numbers(names) == {2: ["i-002-b", "i-002-b-again"]}


class _NoAtomicLateArrival:
    """An adapter with no ``if_absent``, plus an instance that shows up only
    AFTER the enumeration — the concurrent write that landed in between."""

    def __init__(self, inner: Any, late: str) -> None:
        self._inner = inner
        self._late = late
        self.reads = 0

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    async def query(self, *a: Any, **kw: Any):
        self.reads += 1
        first = self.reads == 1
        async for row in self._inner.query(*a, **kw):
            if first and isinstance(row, dict):
                meta = row.get("metadata")
                name = meta.get("name") if isinstance(meta, dict) else row.get("name")
                if name == self._late:
                    continue
            yield row

    async def write_instance(self, *a: Any, **kw: Any):
        if kw.pop("if_absent", False):
            raise NotImplementedError("this adapter cannot claim atomically")
        return await self._inner.write_instance(*a, **kw)


@pytest.mark.asyncio
async def test_the_fallback_probe_asks_about_the_NUMBER_not_the_name(kernel):
    """On the probe-then-write adapter, the probe has to be worth running.

    #242's probe asked ``get_instance("i-002-<our slug>")`` — a name nobody
    else would ever pick, so it answered "free" for every real collision. The
    probe now asks whether ANY slug holds ``i-002``, and because it re-reads,
    it can see the write that landed after the enumeration."""
    await S.create_issue(kernel, _SCOPE, "a", description="a")            # i-001
    await S.create_issue(kernel, _SCOPE, "landed-late", description="b")  # i-002

    k = _NoAtomicLateArrival(kernel, late="i-002-landed-late")
    out = await S.create_issue(k, _SCOPE, "mine", description="c")

    assert out["name"] == "i-003-mine", (
        "the enumeration saw only i-001 and aimed at 002; the number probe "
        "re-read, found i-002-landed-late, and stepped past it"
    )
    kept = (await kernel.get_instance(_SCOPE, "Issue", "i-002-landed-late"))["spec"]
    assert kept["description"] == "b"


@pytest.mark.asyncio
async def test_create_issue_still_numbers_from_the_highest_existing(kernel):
    await S.create_issue(kernel, _SCOPE, "a", description="a")
    await S.create_issue(kernel, _SCOPE, "b", description="b")
    out = await S.create_issue(kernel, _SCOPE, "c", description="c")
    assert out["name"] == "i-003-c"


class _SpyKernel:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.query_kwargs: list[dict[str, Any]] = []

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    async def query(self, *a: Any, **kw: Any):
        self.query_kwargs.append(kw)
        async for row in self._inner.query(*a, **kw):
            yield row


@pytest.mark.asyncio
async def test_create_issue_enumerates_names_only(kernel):
    """The numbering needs the NAMES, not 51 full Issue specs. Pushing the
    projection down keeps the per-call payload proportional to what is used —
    the enumeration is still O(N) rows, which is documented, not hidden."""
    spy = _SpyKernel(kernel)
    await S.create_issue(spy, _SCOPE, "a", description="a")
    assert spy.query_kwargs, "create_issue must enumerate through kernel.query"
    assert spy.query_kwargs[0].get("projection") == ["name"]


# ── the names this kernel cannot see ───────────────────────────────────────


def test_next_number_is_prefix_agnostic():
    """``kz-NNN`` is the SAME allocator as ``i-NNN``, and it had none of the
    hardening — so the primitive is one function now, not two that drift."""
    assert S.next_number("kz", ["kz-001-a", "kz-007-b", "i-999-nao-conta"]) == 8
    assert S.next_number("i", ["kz-042-a"]) == 1
    assert S.duplicate_numbers("kz", ["kz-002-a", "kz-002-b", "kz-003-c"]) == {
        2: ["kz-002-a", "kz-002-b"],
    }
    # The published Issue names stay published: the wrappers are the same call.
    assert S.next_issue_number(["i-004-x"]) == S.next_number("i", ["i-004-x"])


@pytest.mark.asyncio
async def test_also_taken_moves_the_number_past_a_source_this_kernel_cannot_see(
    kernel,
):
    """The one input that can break ``max+1``\'s tautology.

    Filtering the candidate against the enumeration is dead code — it is
    ``max+1`` of that same list. ``also_taken`` is different in kind: names from
    a place this kernel never reads. On the board that produced the bug it is
    the other git worktree, whose ``i-101`` is a real file on this machine and
    absent from every row this kernel can return.

    Note what it is NOT: the caller is trusting a read, not holding a lock. Two
    processes reading each other\'s trees in the same instant still both see
    nothing, and a clone on another machine is invisible either way — which is
    why ``duplicate_issue_numbers`` on the merged tree stays the backstop.
    """
    await S.create_issue(kernel, _SCOPE, "aqui", description="a")  # i-001

    out = await S.create_issue(
        kernel, _SCOPE, "nova", description="b",
        also_taken=["i-002-noutra-worktree", "i-003-noutra-worktree"],
    )

    assert out["name"] == "i-004-nova"
    # …and without the hint, the same board hands out numbers the other tree
    # already used. This is the collision; the assertion above is earned by the
    # hint and by nothing else.
    again = await S.create_issue(kernel, _SCOPE, "outra", description="c")
    assert again["name"] == "i-005-outra"


@pytest.mark.asyncio
async def test_also_taken_defaults_to_nothing_and_changes_no_caller(kernel):
    """A face that knows nothing about other trees keeps the old behavior —
    the MCP tool runs against a shared database where worktrees do not exist."""
    await S.create_issue(kernel, _SCOPE, "a", description="a")
    out = await S.create_issue(kernel, _SCOPE, "b", description="b")
    assert out["name"] == "i-002-b"
