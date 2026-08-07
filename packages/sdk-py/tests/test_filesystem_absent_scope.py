"""i-142 — an absent SCOPE is empty; an absent STORE refuses.

⚠️ THE DEFECT. ``assign_namespace`` READS the ``KindNamespace`` claim registry
in ``_lib`` before it mints, and the filesystem adapter answered an absent scope
DIRECTORY with ``FileNotFoundError``. So on a brand-new ``.dna`` — a scope with
a manifest and nothing else — the very FIRST Kind authored through any face
failed, and **four** places had grown a handler for it:

===============================================  ==============================
place                                            what it says
===============================================  ==============================
``dna_cli.new_cmd._no_registry``                 "create ``<base>/_lib/manifest.yaml``"
``dna_cli._mcp_kinds.NO_REGISTRY``               "ask an operator to provision"
``dna_cli._rest_api`` ×4 ``except``              503
``dna.application.sdlc.existing_or_none``        "absent scope ⇒ absent instance"
===============================================  ==============================

Every one of them is RIGHT for a store that LOST its ``_lib`` and WRONG for a
store that never had one — and none of them could tell, because a builtin
``FileNotFoundError`` carries no such distinction. A fifth handler would have
been a fifth guess. The distinction belongs where the evidence is: the ADAPTER
is the only layer that can see whether the store itself is there.

⚠️ THE OTHER THING IT WAS BREAKING, which nobody had noticed and which is worse
than the authoring refusal: see
:func:`test_the_first_instance_in_a_new_scope_still_gets_an_identity`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_STORY = {
    "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
    "metadata": {"name": "s-first"},
    "spec": {"title": "t", "description": "d", "status": "todo", "owner": "x"},
}


def _fresh_store(tmp_path: Path):
    """A ``.dna`` that exists and holds nothing — the shape of every new install."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.kernel import Kernel

    base = tmp_path / ".dna"
    base.mkdir(parents=True)
    src = FilesystemWritableSource(base_dir=str(base))
    return src, Kernel.auto(source=src)


@pytest.mark.asyncio
async def test_an_absent_scope_reads_as_empty(tmp_path):
    """The fact itself, on the door the whole chain goes through."""
    src, kernel = _fresh_store(tmp_path)
    assert await src.load_all("_lib") == []
    assert [r async for r in kernel.query("_lib", "KindNamespace")] == []


@pytest.mark.asyncio
async def test_an_absent_STORE_ROOT_refuses_rather_than_answering_empty(tmp_path):
    """⚠️ The other half, and the half that keeps the first one honest.

    "Absent scope ⇒ empty" must not become "absent anything ⇒ empty". A store
    root that is not there cannot answer at all, and ``[]`` would be a
    confident lie about data nobody looked at — the same shape of lie
    ``GraphUnsupported`` and ``KeyLookupUnsupported`` exist to refuse.

    Both bases are asserted because both have callers: ``CapabilityRefusal``
    for a face that relays deployment faults as a family, ``FileNotFoundError``
    for the four handlers written before this type existed.
    """
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.kernel.errors import (
        CapabilityRefusal, KernelRefusal, StoreUnavailable,
    )

    gone = FilesystemWritableSource(base_dir=str(tmp_path / "never-mounted"))
    with pytest.raises(StoreUnavailable) as caught:
        await gone.load_all("_lib")
    assert isinstance(caught.value, CapabilityRefusal)
    assert isinstance(caught.value, FileNotFoundError)
    # A deployment fault is not a verdict the caller may appeal.
    assert not isinstance(caught.value, KernelRefusal)


@pytest.mark.asyncio
async def test_the_composite_router_answers_the_same_way(tmp_path):
    """The multi-base router is the fourth filesystem-backed shape, and a
    divergence between it and the flat adapter is the same defect one level up.

    Its READ door answers ``[]`` for a scope it holds nothing for, like every
    other store. Its WRITE door still refuses, and that asymmetry is deliberate
    rather than an oversight: a write to an unrouted scope has genuinely
    nowhere to go, and inventing a child would put somebody's instance in a
    repository they never named.
    """
    from dna.adapters.filesystem.composite import CompositeFilesystemSource

    child = tmp_path / "childrepo" / ".dna" / "known"
    child.mkdir(parents=True)
    (child / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata:\n  name: known\nspec: {}\n"
    )
    comp = CompositeFilesystemSource(str(tmp_path))
    assert await comp.load_all("never-written-to") == []
    with pytest.raises(FileNotFoundError):
        await comp.save_instance("never-written-to", "Story", "s-x", dict(_STORY))


@pytest.mark.asyncio
async def test_the_first_kind_authored_in_a_brand_new_store_succeeds(tmp_path):
    """⚠️ ACROSS THE DOOR, with the real chain — not the adapter in isolation.

    ``assign_namespace`` → ``_stored_for`` → ``kernel.query(SYSTEM_SCOPE, …)``
    → the adapter, which is where it used to die. A unit test on ``load_all``
    would have gone green while every authoring face stayed broken; this house
    has paid for a guard that was right and that no door called.

    The second call asserts idempotence, and it is doing more work than it
    looks: it proves the READ path now finds the claim the WRITE path just
    stored. A read that still refused would mint a second namespace, and a
    workspace owning two assigned namespaces is an instance-IDENTITY problem —
    ``apiVersion`` participates in the key.
    """
    from dna.application.namespace_assignment import assign_namespace

    _src, kernel = _fresh_store(tmp_path)
    first = await assign_namespace(kernel, "ws-fresh", now="2026-08-07T00:00:00+00:00")
    assert first.endswith(".dna.local")
    again = await assign_namespace(kernel, "ws-fresh", now="2026-08-07T01:00:00+00:00")
    assert again == first, "a second call minted a SECOND namespace — the read still refuses"


@pytest.mark.asyncio
async def test_the_first_instance_in_a_new_scope_still_gets_an_identity(tmp_path):
    """⚠️ The defect this issue was HIDING, and it is the expensive one.

    ``WritePipeline._ensure_instance_id`` reads the store to decide whether to
    ADOPT a stored id or MINT a new one, and its contract says — for a good
    reason, spelled out in its own docstring — that *a read that RAISES mints
    nothing*: inventing an identity because the store was briefly unreachable
    turns a transient failure into a permanent wrong answer.

    An absent scope directory RAISED. So the rule fired on a case that is not a
    failure at all, and **the first instance written into any new filesystem
    scope was stored with no ``metadata.id``**. Measured on the same store,
    before and after the fix::

        FIRST instance in a NEW scope   id = None    →  id = sdpf37uwgaja
        SECOND instance (scope exists)  id = nomw7…  →  id = btdyt3mcxf4l

    Nothing was red. i-114 gave every instance an identity and
    ``dna_edges.to_id`` points at it; a first-in-scope instance had none to
    point at, and the only symptom was a test asserting the envelope came back
    unchanged.

    Both instances are asserted, and DIFFERENT: identical ids would mean the
    second adopted the first's, which is the other way this can go wrong.
    """
    from dna.kernel.identity import instance_id_of

    _src, kernel = _fresh_store(tmp_path)
    await kernel.write_instance("brand-new", "Story", "s-first", dict(_STORY))
    second = dict(_STORY, metadata={"name": "s-second"})
    await kernel.write_instance("brand-new", "Story", "s-second", second)

    first_id = instance_id_of(await kernel.get_instance("brand-new", "Story", "s-first"))
    second_id = instance_id_of(await kernel.get_instance("brand-new", "Story", "s-second"))
    assert first_id, (
        "the FIRST instance in a new scope has no instance id — the store read "
        "refused instead of answering empty, and _ensure_instance_id correctly "
        "declined to mint on a raise"
    )
    assert second_id
    assert first_id != second_id, "the second instance adopted the first's identity"
