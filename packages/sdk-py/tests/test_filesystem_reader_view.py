"""i-140 — every read door on an FS source sees what ``load_all`` sees.

⚠️ THE DEFECT, and why the guard is shaped exactly like this.

``FilesystemSource`` declared ``query_pushdown=True`` — "delegate the query to
me" — and ``kernel_attachable=False`` — "I cannot be handed the kernel's
readers". Its query is correct only WITH them, so the two declarations could not
both be true, and the one somebody believed answered with an EMPTY LIST.

A reader is what turns a bundle DIRECTORY (``skills/greeter/SKILL.md``) into an
instance. ``load_all`` takes ``readers`` as a parameter, so the kernel hands
over its own and bundles appear; every other read door has to find readers on
``self``, and on the read-only base there was nothing to find. Measured on one
seeded scope holding a bundle-stored ``Skill`` and a yaml-stored ``Story``::

    adapter                  Kind    load_all  query  list_doc_refs  load_one
    FilesystemWritable       Skill      1        1         1           HIT
    Filesystem (read-only)   Skill      1        0         0          MISS
    Filesystem (read-only)   Story      1        1         1           HIT
    Composite                Skill      1        0         0          MISS
    Composite                Story      1        1         1           HIT

What changes between a passing row and a failing one is the **storage form**,
not the Kind, not the plane and not the scope — which is why this file
parametrizes on storage form and compares the two doors, rather than asserting
some count it hard-codes. A guard written as "``query('Skill')`` returns 1"
would pass on a fixture that seeded nothing.

⚠️ It also covers the SECOND half, which the issue did not name: the reader view
was split across TWO private helpers, so the fix that taught ``query`` to see
bundles left ``list_doc_refs`` / ``load_one`` / ``find_instances_by_spec_key``
reading the stale snapshot. Every door is asserted here for that reason — each
of them fails by returning LESS, never by failing, so none of them would have
been noticed.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

_SCOPE = "rv-scope"

#: The two storage forms in one scope, as ``(kind, name, api_version, spec)``.
#: ``Skill`` is written by the agentskills WRITER into a bundle DIRECTORY;
#: ``Story`` lands as a plain YAML file. The pair is the whole experiment.
_BUNDLE = ("Skill", "greeter", "agentskills.io/v1", {"instruction": "say hi"})
_YAML = ("Story", "s-1", "github.com/ruinosus/dna/sdlc/v1", {"title": "a story"})


async def _seed(base: Path) -> None:
    """Write one bundle-stored and one yaml-stored instance into ``base``."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.kernel import Kernel

    src = FilesystemWritableSource(base_dir=str(base))
    Kernel.auto(source=src)
    await src.save_instance(_SCOPE, "Genome", _SCOPE, {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {},
    })
    for kind, name, api, spec in (_BUNDLE, _YAML):
        await src.save_instance(_SCOPE, kind, name, {
            "apiVersion": api, "kind": kind,
            "metadata": {"name": name}, "spec": spec,
        })


def _assert_the_two_forms_really_landed_differently(base: Path) -> None:
    """The BLINDNESS FLOOR, and it runs before every assertion below.

    This whole file is a comparison between two storage forms, so a fixture
    that quietly wrote both as YAML would make every row agree and the suite
    would go green over the exact defect. Asserted against the DISK, not
    against the adapter that is under test.
    """
    scope_dir = base / _SCOPE
    bundles = [p for p in scope_dir.rglob("SKILL.md") if p.is_file()]
    yamls = [p for p in scope_dir.rglob("*.yaml") if p.is_file() and "s-1" in p.name]
    assert bundles, (
        f"no bundle landed under {scope_dir} — the writer did not run, so "
        f"'bundle vs yaml' is not being compared at all"
    )
    assert yamls, f"no YAML instance landed under {scope_dir}"


async def _fs_readonly(tmp: Path) -> tuple[Any, Any]:
    from dna.adapters.filesystem import FilesystemSource
    from dna.kernel import Kernel

    base = tmp / ".dna"
    await _seed(base)
    _assert_the_two_forms_really_landed_differently(base)
    src = FilesystemSource(str(base))
    return src, Kernel.auto(source=src)


async def _fs_writable(tmp: Path) -> tuple[Any, Any]:
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.kernel import Kernel

    base = tmp / ".dna"
    await _seed(base)
    _assert_the_two_forms_really_landed_differently(base)
    src = FilesystemWritableSource(base_dir=str(base))
    return src, Kernel.auto(source=src)


async def _fs_composite(tmp: Path) -> tuple[Any, Any]:
    from dna.adapters.filesystem.composite import CompositeFilesystemSource
    from dna.kernel import Kernel

    base = tmp / "childrepo" / ".dna"
    await _seed(base)
    _assert_the_two_forms_really_landed_differently(base)
    src = CompositeFilesystemSource(str(tmp))
    return src, Kernel.auto(source=src)


_SHAPES = [
    pytest.param(_fs_readonly, id="filesystem-readonly"),
    pytest.param(_fs_writable, id="filesystem-writable"),
    pytest.param(_fs_composite, id="composite-filesystem"),
]


@pytest.fixture(params=_SHAPES)
def shape(request):
    """One of the three filesystem-backed source shapes, seeded and wired.

    All three are here because all three declared ``query_pushdown=True``, and
    only ONE of them was attachable. The read-only base and the composite router
    were blind; a guard that exercised only the writable subclass — the shape
    every existing FS test happens to use — would have been green throughout.
    """
    return request.param


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,name", [
    pytest.param(_BUNDLE[0], _BUNDLE[1], id="bundle-stored"),
    pytest.param(_YAML[0], _YAML[1], id="yaml-stored"),
])
async def test_every_read_door_agrees_with_load_all(shape, kind, name, tmp_path):
    """⚠️ THE guard for i-140, at the granularity of the defect.

    The question each assertion answers is the same one: *for THIS storage
    form, does this door return what ``load_all`` returns?* Nothing here
    hard-codes a count — the oracle is the other door, so the test measures the
    DIVERGENCE that was the bug and cannot be satisfied by a fixture that seeds
    less than it claims (``_assert_the_two_forms_really_landed_differently``
    is the floor under that).
    """
    src, kernel = await shape(tmp_path)
    readers = list(getattr(kernel, "_readers", []) or [])
    seen = [d for d in await src.load_all(_SCOPE, readers=readers)
            if d.get("kind") == kind]
    assert seen, (
        f"load_all itself does not see the {kind} — the fixture is broken, not "
        f"the adapter; every comparison below would pass vacuously"
    )
    expected = len(seen)

    got = len([r async for r in src.query(_SCOPE, kind)])
    assert got == expected, (
        f"source.query({kind!r}) returned {got}, load_all returned {expected}. "
        f"An empty list is indistinguishable from 'there is none'."
    )

    got = len([r async for r in kernel.query(_SCOPE, kind)])
    assert got == expected, f"kernel.query({kind!r}) returned {got}, not {expected}"

    refs = [r for r in await src.list_doc_refs(_SCOPE) if r[0] == kind]
    assert len(refs) == expected, f"list_doc_refs missed the {kind}: {refs}"

    assert await src.load_one(_SCOPE, kind, name) is not None, (
        f"load_one({kind!r}, {name!r}) returned None while load_all returns it"
    )

    # Gated on the DECLARATION, not on ``hasattr``. The composite router
    # declares ``key_lookup=False`` and says why in its own capabilities: it
    # does not subclass ``FilesystemSource`` and implements no such method, so
    # a ``by: <key>`` relation comes back UNSUPPORTED there — which is the
    # honest answer and emphatically not the ``None`` that reads as "no
    # instance carries that key". Asserting the door on an adapter that refuses
    # it would be this file demanding a capability nobody claimed.
    from dna.kernel.capabilities import source_capabilities

    if source_capabilities(src).key_lookup:
        key, value = next(iter(
            (_BUNDLE if kind == _BUNDLE[0] else _YAML)[3].items()
        ))
        hits = await src.find_instances_by_spec_key(_SCOPE, kind, key, str(value))
        assert len(hits) == expected, (
            f"find_instances_by_spec_key found {len(hits)} {kind}(s), not "
            f"{expected} — a `by: <key>` relation would read as unfollowed"
        )


@pytest.mark.asyncio
async def test_count_agrees_with_query_per_storage_form(shape, tmp_path):
    """``count`` rides ``query``, so it inherits the blindness silently.

    Its own assertion because a caller who asks "how many" and is told zero has
    no second door to check against — a query at least returns rows somebody
    might notice are missing.
    """
    src, kernel = await shape(tmp_path)
    for kind, _name, _api, _spec in (_BUNDLE, _YAML):
        rows = len([r async for r in src.query(_SCOPE, kind)])
        counted = (await src.count(_SCOPE, kind)).get("total")
        assert counted == rows == 1, (
            f"count({kind!r})={counted} vs query={rows} — expected 1 of each"
        )


@pytest.mark.asyncio
async def test_declaring_query_pushdown_requires_being_attachable(shape, tmp_path):
    """⚠️ The CONTRADICTION itself, asserted as an implication.

    ``query_pushdown=True`` means the kernel stops serving the query from its
    own fallback (which is handed the kernel's live readers explicitly) and
    delegates to the adapter. An adapter that cannot BE handed those readers
    therefore answers a narrower question than the one it took over. That is not
    a slow path or a missing feature — it is a different answer with no signal.

    Written as an implication rather than as two hard-coded booleans so it keeps
    meaning something for an adapter added later: take the query over, or accept
    the fallback; do not take it over blind.
    """
    from dna.kernel.capabilities import source_capabilities

    src, _kernel = await shape(tmp_path)
    caps = source_capabilities(src)
    if caps.query_pushdown:
        assert caps.kernel_attachable, (
            f"{type(src).__name__} declares query_pushdown=True but "
            f"kernel_attachable=False. The kernel will delegate queries to an "
            f"adapter it cannot give its readers to, and bundle-stored "
            f"instances will come back as an empty list."
        )


#: A ``KindDefinition`` whose instances are stored as a BUNDLE — the exact
#: population i-140 identified as reachable: a ``KIND.yaml`` written by hand
#: into ``.dna/<scope>/kinds/``, declaring ``storage.type: bundle``, served by
#: no extension's own reader but by the kernel's ``GenericBundleReader``.
_DECLARATIVE_BUNDLE_KIND = {
    "apiVersion": "github.com/ruinosus/dna/core/v1", "kind": "KindDefinition",
    "metadata": {"name": "recipe"},
    "spec": {
        "target_api_version": "example.com/v1", "target_kind": "Recipe",
        "alias": "example-recipe", "origin": "example.com",
        "schema": {"type": "object", "properties": {"title": {"type": "string"}}},
        "storage": {"type": "bundle", "container": "recipes",
                    "marker": "RECIPE.md", "body_as": "text",
                    "body_field": "description"},
        "approved_by": "approver@example.com",
    },
}


@pytest.mark.asyncio
async def test_a_lazily_registered_bundle_reader_is_visible_to_every_door(tmp_path):
    """⚠️ The second half of i-140, and the half a well-behaved fixture HIDES.

    The reader view used to be TWO private helpers — one preferring the
    kernel's LIVE list, one reading a snapshot taken at ``attach_kernel`` time
    — and ``query`` picked the live one while ``list_doc_refs`` / ``load_one``
    / ``find_instances_by_*`` picked the stale one. Collapsing them to one is
    the fix; this is the test that can tell.

    It needs the ordering that makes the snapshot stale, because with
    ``Kernel.auto`` the two lists happen to agree and a mutation that restores
    the snapshot passes unnoticed. MEASURED, wiring the source BEFORE the boot
    read the way a factory does::

        snapshot at attach       5 readers
        kernel live after boot  10 readers
        the gap                  GenericBundleReader   ← the only type missing

    And that one type is not an obscure corner: it is what serves a Kind
    DECLARED as a descriptor with ``storage.type: bundle`` — the ``KIND.yaml``
    written by hand into ``.dna/<scope>/kinds/`` that i-140 named as the
    reachable population. Every extension-owned reader (Agent, Skill, Soul) is
    already in the snapshot, which is precisely why the defect could sit behind
    a green suite.

    Asserted ACROSS THE DOORS with a real instance, never by comparing the two
    lists: a helper that returns the right readers to nobody is a defect this
    house has already paid for.
    """
    import yaml

    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.agentsmd import AgentsMdExtension
    from dna.extensions.helix import HelixExtension
    from dna.extensions.kinddef import KindDefinitionExtension
    from dna.kernel import Kernel

    base = tmp_path / ".dna"
    scope_dir = base / _SCOPE
    (scope_dir / "kinds" / "recipe").mkdir(parents=True)
    (scope_dir / "Genome.yaml").write_text(yaml.safe_dump({
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {},
    }))
    (scope_dir / "kinds" / "recipe" / "KIND.yaml").write_text(
        yaml.safe_dump(_DECLARATIVE_BUNDLE_KIND))
    (scope_dir / "recipes" / "pasta").mkdir(parents=True)
    (scope_dir / "recipes" / "pasta" / "RECIPE.md").write_text(
        "---\nname: pasta\ntitle: Simple Pasta\n---\n\nBoil water.\n")

    kernel = Kernel()
    for ext in (HelixExtension(), AgentsMdExtension(), KindDefinitionExtension()):
        kernel.load(ext)
    src = FilesystemWritableSource(str(base))
    kernel.source(src)                      # ← attach, and the snapshot, happen HERE
    kernel.cache(FilesystemCache(str(base)))
    await kernel.instance_async(_SCOPE)     # ← GenericBundleReader registers HERE

    readers = list(getattr(kernel, "_readers", []) or [])
    seen = [d for d in await src.load_all(_SCOPE, readers=readers)
            if d.get("kind") == "Recipe"]
    assert seen, (
        "load_all does not see the declarative bundle instance — the fixture "
        "never registered GenericBundleReader, so nothing below is being tested"
    )

    assert await src.load_one(_SCOPE, "Recipe", "pasta") is not None, (
        "load_one read the stale attach-time snapshot: the reader that turns "
        "recipes/pasta/RECIPE.md into an instance registered after it was taken"
    )
    assert ("Recipe", "pasta") in await src.list_doc_refs(_SCOPE)
    assert len([r async for r in src.query(_SCOPE, "Recipe")]) == len(seen)
    assert len([r async for r in kernel.query(_SCOPE, "Recipe")]) == len(seen)
