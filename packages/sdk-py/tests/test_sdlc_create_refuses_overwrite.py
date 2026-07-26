"""``create_story`` / ``create_issue`` / ``create_feature`` never destroy a
document that is already there.

The hole: each of the three built a fresh spec and called
``kernel.write_document`` with no existence check. ``write_document`` is an
upsert keyed on the name, so an agent guessing (or re-trying, or working from a
stale board) obliterated the existing document's status, timeline,
acceptance_criteria and definition_of_done — silently, and reported success.
"Create" is the ONE verb that must never be an update.

``create_issue`` had a second, quieter version of the same bug: it derived its
name from ``max(existing i-NNN) + 1``. Any enumeration that misses a document —
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
    assert "s-one" in msg and "Story" in msg      # names the document…
    assert "in-progress" in msg                   # …and its current state

    spec = (await kernel.get_document(_SCOPE, "Story", "s-one"))["spec"]
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
    spec = (await kernel.get_document(_SCOPE, "Feature", "f-one"))["spec"]
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
    caller into hand-rolling ``kernel.write_document`` with no timeline at all."""
    await S.create_story(
        kernel, _SCOPE, "s-one", feature="f-x", description="the old one",
        acceptance_criteria=["Given X"], definition_of_done=["done"])
    await S.create_story(
        kernel, _SCOPE, "s-one", feature="f-x", description="the new one",
        acceptance_criteria=["Given X"], definition_of_done=["done"],
        overwrite=True)
    spec = (await kernel.get_document(_SCOPE, "Story", "s-one"))["spec"]
    assert spec["description"] == "the new one"


# ── create_issue: the auto-incremented name never lands on a live document ──


class _HidingKernel:
    """The real kernel with ONE Issue hidden from ``query`` — the shape of every
    enumeration that can under-report (a concurrent writer, a read replica that
    has not caught up). ``get_document`` still sees it, which is exactly why the
    probe is the fix and the enumeration is not."""

    def __init__(self, inner: Any, hidden: str) -> None:
        self._inner = inner
        self._hidden = hidden

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    async def query(self, *a: Any, **kw: Any):
        async for row in self._inner.query(*a, **kw):
            meta = row.get("metadata") if isinstance(row, dict) else None
            if isinstance(meta, dict) and meta.get("name") == self._hidden:
                continue
            yield row


@pytest.mark.asyncio
async def test_create_issue_probes_past_a_name_the_enumeration_missed(kernel):
    await S.create_issue(kernel, _SCOPE, "first", description="the real i-001")
    hiding = _HidingKernel(kernel, "i-001-first")

    out = await S.create_issue(hiding, _SCOPE, "second", description="the new one")

    assert out["name"] == "i-002-second", (
        "the enumeration saw no Issues, so max+1 = 1 — the probe must step past "
        "the i-001 that is actually there"
    )
    kept = (await kernel.get_document(_SCOPE, "Issue", "i-001-first"))["spec"]
    assert kept["description"] == "the real i-001"


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
