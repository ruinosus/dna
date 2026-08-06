"""Item 8 — "create is never an update", now true under concurrency.

#242 closed the whole class of NON-concurrent overwrites by reading before
writing, and said in its own docstring what it could not close: two creates can
both find a name free in the same instant, because "the kernel has no unique-name
constraint to lean on, and inventing a lock here would be a distributed-systems
claim this function cannot honour".

The constraint was already there, one layer down — a composite primary key on the
SQL side, ``O_CREAT|O_EXCL`` / ``mkdir`` on the filesystem — it simply had no way
up. ``if_absent`` is that way up.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.application import sdlc as S
from dna.kernel import Kernel
from dna.kernel.errors import InstanceNameTaken

_SCOPE = "probe"


@pytest.fixture
def kernel(tmp_path):
    from dna.adapters.filesystem.writable import FilesystemWritableSource

    k = Kernel.auto()
    src = FilesystemWritableSource(base_dir=str(tmp_path), kernel=k)
    k.source(src)
    (tmp_path / _SCOPE).mkdir(parents=True, exist_ok=True)
    return k


def _raw(kind: str, name: str, marker: str) -> dict:
    return {
        "apiVersion": S.SDLC_API_VERSION, "kind": kind,
        "metadata": {"name": name},
        "spec": {"title": marker, "description": marker, "status": "open",
                 "type": "bug", "severity": "medium"},
    }


# ── the primitive ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_if_absent_creates_when_the_name_is_free(kernel):
    await kernel.write_instance(
        _SCOPE, "Issue", "i-001-x", _raw("Issue", "i-001-x", "first"),
        if_absent=True, invalidate_mode="doc")
    doc = await kernel.get_instance(_SCOPE, "Issue", "i-001-x")
    assert doc["spec"]["title"] == "first"


@pytest.mark.asyncio
async def test_if_absent_refuses_a_taken_name_and_leaves_it_alone(kernel):
    await kernel.write_instance(
        _SCOPE, "Issue", "i-001-x", _raw("Issue", "i-001-x", "the real one"),
        if_absent=True, invalidate_mode="doc")
    with pytest.raises(InstanceNameTaken, match="already exists"):
        await kernel.write_instance(
            _SCOPE, "Issue", "i-001-x", _raw("Issue", "i-001-x", "a guess"),
            if_absent=True, invalidate_mode="doc")
    doc = await kernel.get_instance(_SCOPE, "Issue", "i-001-x")
    assert doc["spec"]["title"] == "the real one", "the refusal must not write"


@pytest.mark.asyncio
async def test_a_plain_write_is_still_an_upsert(kernel):
    """``if_absent`` is opt-in: nothing that worked before changes."""
    await kernel.write_instance(
        _SCOPE, "Issue", "i-001-x", _raw("Issue", "i-001-x", "one"),
        invalidate_mode="doc")
    await kernel.write_instance(
        _SCOPE, "Issue", "i-001-x", _raw("Issue", "i-001-x", "two"),
        invalidate_mode="doc")
    doc = await kernel.get_instance(_SCOPE, "Issue", "i-001-x")
    assert doc["spec"]["title"] == "two"


@pytest.mark.asyncio
async def test_an_adapter_without_the_kwarg_refuses_rather_than_degrades(
    kernel, monkeypatch,
):
    """A caller that asked for "create or fail" and silently got an upsert would
    believe it holds a guarantee it does not — worse than not offering one.

    Simulated by stripping the DECLARATION from a real adapter, because that is
    exactly the situation: an adapter that has not adopted the kwarg."""
    import dataclasses

    from dna.kernel import capabilities as C

    real = C.write_kwarg_support
    monkeypatch.setattr(
        C, "write_kwarg_support",
        lambda src: dataclasses.replace(real(src), if_absent=False),
    )
    with pytest.raises(NotImplementedError, match="if_absent"):
        await kernel.write_instance(
            _SCOPE, "Issue", "i-x", _raw("Issue", "i-x", "x"), if_absent=True)


# ── what it buys create_issue ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_create_issue_calls_produce_two_issues(kernel):
    """The race #242 documented and could not close.

    Both calls enumerate an empty board, both compute ``i-001``, and before this
    one of them silently replaced the other. Now the loser's write is REFUSED by
    the storage layer and it takes the next number — two calls, two Issues."""
    results = await asyncio.gather(*[
        S.create_issue(kernel, _SCOPE, f"slug{i}", description=f"issue {i}")
        for i in range(6)
    ])
    names = [r["name"] for r in results]
    assert len(set(names)) == len(names), f"a name was reused: {names}"
    for name in names:
        assert await kernel.get_instance(_SCOPE, "Issue", name) is not None


@pytest.mark.asyncio
async def test_create_issue_still_numbers_sequentially(kernel):
    a = await S.create_issue(kernel, _SCOPE, "first", description="a")
    b = await S.create_issue(kernel, _SCOPE, "second", description="b")
    assert a["name"] == "i-001-first"
    assert b["name"] == "i-002-second"


@pytest.mark.asyncio
async def test_create_issue_steps_past_a_name_the_enumeration_missed(kernel):
    """A pre-existing ``i-001`` the enumeration cannot see (a lagging replica,
    a hand-placed file) must not be overwritten."""
    await kernel.write_instance(
        _SCOPE, "Issue", "i-001-mine", _raw("Issue", "i-001-mine", "mine"),
        invalidate_mode="doc")
    out = await S.create_issue(kernel, _SCOPE, "mine", description="a guess")
    assert out["name"] != "i-001-mine"
    kept = await kernel.get_instance(_SCOPE, "Issue", "i-001-mine")
    assert kept["spec"]["title"] == "mine"
