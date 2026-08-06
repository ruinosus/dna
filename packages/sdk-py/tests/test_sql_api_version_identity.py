"""A Kind's identity is ``(apiVersion, kind)`` — the SQL adapter must agree.

The registry keys Kinds on ``(api_version, kind)``, and tenant-authored Kinds
depend on it: two workspaces may each declare a ``Deal`` under their own
namespace, which is what namespacing the apiVersion is FOR. The SQL adapter's
tables, however, keyed rows on ``(scope, kind, name)`` alone — so two Kinds
sharing a name in one scope were indistinguishable to it on SAVE as well as on
DELETE, and ``delete_instance``'s ``api_version`` kwarg had nowhere to go.

This is the scenario that motivates the column, end to end: two Kinds with the
same name, in one scope, saved / read back / updated / deleted independently
with no cross-talk. It runs on BOTH dialects (Postgres when ``DATABASE_URL``
is set, the same gate the conformance matrix uses).
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any, AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio

# Two Kinds, one NAME, two namespaces — the tenancy case #244 made real.
NS_A = "acme.example/v1"
NS_B = "globex.example/v1"
SCOPE = "api-version-identity"


def _deal(api_version: str, name: str, title: str) -> dict[str, Any]:
    return {
        "apiVersion": api_version,
        "kind": "Deal",
        "metadata": {"name": name},
        "spec": {"title": title},
    }


async def _build_sqlite() -> tuple[Any, Callable[[], Awaitable[None]]]:
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    fd, tmp = tempfile.mkstemp(prefix="dna-apiver-", suffix=".db")
    os.close(fd)
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp}")
    await src.connect()

    async def cleanup() -> None:
        await src.close()
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

    return src, cleanup


async def _build_postgres() -> tuple[Any, Callable[[], Awaitable[None]]]:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping Postgres dialect")

    import asyncpg

    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    schema = f"dna_apiver_{os.getpid()}_{id(asyncio):x}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    src = SqlAlchemySource(
        dsn.replace("postgresql://", "postgresql+asyncpg://", 1), schema=schema,
    )
    await src.connect()

    async def cleanup() -> None:
        await src.close()
        c = await asyncpg.connect(dsn)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()

    return src, cleanup


@pytest_asyncio.fixture(params=[
    pytest.param(_build_sqlite, id="sqlite"),
    # Marked so the CI Postgres job (`-m requires_postgres`) actually collects
    # this leg, and the ordinary job skips it with a reason instead of a bare
    # in-factory `pytest.skip` nobody sees.
    pytest.param(_build_postgres, id="postgres",
                 marks=pytest.mark.requires_postgres),
])
async def source(request) -> AsyncIterator[Any]:
    src, cleanup = await request.param()
    try:
        yield src
    finally:
        await cleanup()


def _by_api_version(docs: list[dict]) -> dict[str, dict]:
    return {d["apiVersion"]: d for d in docs if d.get("kind") == "Deal"}


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_kinds_one_name_save_independently(source) -> None:
    """A save under NS_B must not overwrite the NS_A instance of the same name."""
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme deal"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_B, "d-1", "globex deal"))

    docs = _by_api_version(await source.load_all(SCOPE))
    assert set(docs) == {NS_A, NS_B}, (
        f"expected both Deals to survive, got {sorted(docs)} — the second save "
        "overwrote the first, so the two Kinds share one row"
    )
    assert docs[NS_A]["spec"]["title"] == "acme deal"
    assert docs[NS_B]["spec"]["title"] == "globex deal"


@pytest.mark.asyncio
async def test_load_one_resolves_the_exact_kind(source) -> None:
    """``load_one(api_version=...)`` must return THAT Kind's instance."""
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme deal"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_B, "d-1", "globex deal"))

    a = await source.load_one(SCOPE, "Deal", "d-1", api_version=NS_A)
    b = await source.load_one(SCOPE, "Deal", "d-1", api_version=NS_B)
    assert a is not None and a["spec"]["title"] == "acme deal"
    assert b is not None and b["spec"]["title"] == "globex deal"

    missing = await source.load_one(
        SCOPE, "Deal", "d-1", api_version="nobody.example/v1",
    )
    assert missing is None, (
        "load_one pinned to an unregistered apiVersion returned an instance — "
        "the pin is not being applied"
    )


@pytest.mark.asyncio
async def test_update_does_not_cross_talk(source) -> None:
    """Updating one Kind's instance leaves the other's content AND version alone."""
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme v1"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_B, "d-1", "globex v1"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme v2"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme v3"))

    a = await source.load_one(SCOPE, "Deal", "d-1", api_version=NS_A)
    b = await source.load_one(SCOPE, "Deal", "d-1", api_version=NS_B)
    assert a["spec"]["title"] == "acme v3"
    assert b["spec"]["title"] == "globex v1", (
        "the NS_B instance changed when only NS_A was written"
    )

    # Version histories are per-Kind: three writes for A, one for B.
    va = await source.list_versions(SCOPE, "Deal", "d-1", api_version=NS_A)
    vb = await source.list_versions(SCOPE, "Deal", "d-1", api_version=NS_B)
    assert len(va) == 3, f"NS_A version history is {len(va)}, expected 3"
    assert len(vb) == 1, (
        f"NS_B version history is {len(vb)}, expected 1 — the two Kinds share "
        "one version counter"
    )


@pytest.mark.asyncio
async def test_delete_by_api_version_leaves_the_other_kind(source) -> None:
    """The delete the port already carries must hit exactly one Kind."""
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme deal"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_B, "d-1", "globex deal"))

    await source.delete_instance(SCOPE, "Deal", "d-1", api_version=NS_A)

    docs = _by_api_version(await source.load_all(SCOPE))
    assert set(docs) == {NS_B}, (
        f"after deleting the NS_A Deal the surviving set is {sorted(docs)} — "
        "the delete either missed or took both"
    )
    assert await source.load_one(SCOPE, "Deal", "d-1", api_version=NS_A) is None
    assert await source.load_one(SCOPE, "Deal", "d-1", api_version=NS_B) is not None

    # And the second delete still works on the survivor.
    await source.delete_instance(SCOPE, "Deal", "d-1", api_version=NS_B)
    assert _by_api_version(await source.load_all(SCOPE)) == {}


@pytest.mark.asyncio
async def test_delete_of_an_absent_api_version_is_not_found(source) -> None:
    """A pinned delete that matches nothing must raise, not silently succeed."""
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme deal"))
    with pytest.raises(ValueError, match="not_found"):
        await source.delete_instance(
            SCOPE, "Deal", "d-1", api_version="nobody.example/v1",
        )
    assert await source.load_one(SCOPE, "Deal", "d-1", api_version=NS_A) is not None


@pytest.mark.asyncio
async def test_bare_delete_refuses_when_the_name_is_ambiguous(source) -> None:
    """Without a pin, a name that resolves to two Kinds is refused, not guessed.

    Before the column the table could hold only one row for the name, so a bare
    delete was unambiguous by construction. Now that both rows can exist, a bare
    delete would have to pick one (a delete that misses) or take both (a delete
    that over-reaches). Neither is defensible; the caller is told to say which.
    """
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme deal"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_B, "d-1", "globex deal"))

    with pytest.raises(ValueError, match="ambiguous"):
        await source.delete_instance(SCOPE, "Deal", "d-1")

    # Nothing was deleted by the refusal.
    assert set(_by_api_version(await source.load_all(SCOPE))) == {NS_A, NS_B}


@pytest.mark.asyncio
async def test_bare_delete_still_works_for_a_single_kind(source) -> None:
    """All 76 shipped Kinds are unique by name in their scope — unchanged."""
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme deal"))
    await source.delete_instance(SCOPE, "Deal", "d-1")
    assert _by_api_version(await source.load_all(SCOPE)) == {}


@pytest.mark.asyncio
async def test_bundle_entries_do_not_cross_talk(source) -> None:
    """Bundle entries belong to an instance, hence to that instance's Kind."""
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme deal"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_B, "d-1", "globex deal"))

    await source.write_bundle_entry(
        SCOPE, "Deal", "d-1", "notes.md", "acme notes", api_version=NS_A,
    )
    await source.write_bundle_entry(
        SCOPE, "Deal", "d-1", "notes.md", "globex notes", api_version=NS_B,
    )

    a = await source.fetch_bundle_entry(
        SCOPE, "Deal", "d-1", "notes.md", api_version=NS_A,
    )
    b = await source.fetch_bundle_entry(
        SCOPE, "Deal", "d-1", "notes.md", api_version=NS_B,
    )
    assert a == b"acme notes"
    assert b == b"globex notes", (
        "the two Kinds' bundle entries share one row — the second write "
        "overwrote the first"
    )

    # Deleting one Kind takes its entries and only its entries.
    await source.delete_instance(SCOPE, "Deal", "d-1", api_version=NS_A)
    assert await source.fetch_bundle_entry(
        SCOPE, "Deal", "d-1", "notes.md", api_version=NS_B,
    ) == b"globex notes"
    with pytest.raises(FileNotFoundError):
        await source.fetch_bundle_entry(
            SCOPE, "Deal", "d-1", "notes.md", api_version=NS_A,
        )


@pytest.mark.asyncio
async def test_drafts_are_per_kind(source) -> None:
    """``load_drafts`` must not collapse two Kinds' drafts into one row."""
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme deal"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_B, "d-1", "globex deal"))
    drafts = [d for d in await source.load_drafts(SCOPE) if d["kind"] == "Deal"]
    assert len(drafts) == 2, (
        f"load_drafts returned {len(drafts)} Deal draft(s), expected 2 — the "
        "two Kinds are being grouped as one instance"
    )


@pytest.mark.asyncio
async def test_publish_promotes_only_its_own_kind(source) -> None:
    """Publishing one Kind's draft must not republish the other's content."""
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_A, "d-1", "acme deal"))
    await source.save_instance(SCOPE, "Deal", "d-1", _deal(NS_B, "d-1", "globex deal"))
    await source.publish(SCOPE, "Deal", "d-1", api_version=NS_A)

    a = await source.load_one(SCOPE, "Deal", "d-1", api_version=NS_A)
    b = await source.load_one(SCOPE, "Deal", "d-1", api_version=NS_B)
    assert a["spec"]["title"] == "acme deal"
    assert b["spec"]["title"] == "globex deal"


@pytest.mark.asyncio
async def test_every_registered_kind_still_resolves_by_bare_name(source) -> None:
    """All shipped Kinds keep resolving identically — proven, not asserted.

    Every Kind the kernel registers gets an instance written through the adapter
    and read back by BARE name through each keyed read path. Widening the key is
    only safe if it changes nothing for a store where each name belongs to one
    Kind, which is every one of these: the registry has no two Kinds sharing a
    name, so an unpinned read has exactly one row to find, exactly as before.
    """
    from dna.kernel import Kernel

    kernel = Kernel.auto()
    kinds = sorted({(p.kind, p.api_version) for p in kernel.kind_ports()})
    assert len(kinds) >= 76, f"only {len(kinds)} Kinds registered"
    # No two registered Kinds share a name — the precondition that makes an
    # unpinned read unambiguous for shipped content.
    names = [k for k, _ in kinds]
    assert len(names) == len(set(names)), (
        "two registered Kinds share a name; the claim below no longer holds"
    )

    for kind, api_version in kinds:
        raw = {
            "apiVersion": api_version, "kind": kind,
            "metadata": {"name": f"n-{kind}"}, "spec": {"title": kind},
        }
        await source.save_instance(SCOPE, kind, f"n-{kind}", raw)

    for kind, api_version in kinds:
        name = f"n-{kind}"
        bare = await source.load_one(SCOPE, kind, name)
        assert bare is not None, f"{kind} vanished from load_one"
        assert bare["apiVersion"] == api_version
        assert bare == await source.load_one(
            SCOPE, kind, name, api_version=api_version), (
            f"{kind}: the pinned read and the bare read disagree"
        )
        assert (kind, name) in await source.list_doc_refs(SCOPE)
        assert len(await source.list_versions(SCOPE, kind, name)) == 1
        assert (await source.get_version(
            SCOPE, kind, name, "1"))["content"]["kind"] == kind

    loaded = {d["kind"] for d in await source.load_all(SCOPE)}
    assert loaded == {k for k, _ in kinds}

    for kind, _ in kinds:  # and every one deletes by bare name, as before
        await source.delete_instance(SCOPE, kind, f"n-{kind}")
    assert await source.load_all(SCOPE) == []


@pytest.mark.asyncio
async def test_existing_kinds_resolve_identically_without_a_pin(source) -> None:
    """One Kind per name — every read path answers exactly as it always did."""
    doc = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
        "metadata": {"name": "s-alpha"}, "spec": {"title": "alpha", "priority": 1},
    }
    await source.save_instance(SCOPE, "Story", "s-alpha", doc)

    assert (await source.load_one(SCOPE, "Story", "s-alpha"))["spec"]["title"] == "alpha"
    assert ("Story", "s-alpha") in await source.list_doc_refs(SCOPE)
    assert len(await source.list_versions(SCOPE, "Story", "s-alpha")) == 1
    v = await source.get_version(SCOPE, "Story", "s-alpha", "1")
    assert v["content"]["spec"]["title"] == "alpha"
