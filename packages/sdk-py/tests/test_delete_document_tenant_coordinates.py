"""i-088 — an existence check must read at the coordinates the operation acts on.

A document of a tenant-authored Kind wrote fine, appeared in ``list_documents``
and read back through ``get_document`` — and ``delete_document`` answered
``UnknownDocumentError: … not found in scope … — nothing to delete``. All four
calls named the SAME scope, the same Kind, the same name and the same tenant.

The delete's existence check read WITHOUT a tenant::

    :604  read    get_document(sc, port.kind, name, tenant=tenant)   ✓
    :758  delete  get_document(sc, port.kind, name)                  ✗

while the delete immediately below it targeted ``tenant=_write_tenant(...)`` and
the write that created the row used the same. ``tenant`` participates in the
lookup key of every store — the SQL adapters put it in the WHERE clause (and, on
Postgres, in the primary key), the filesystem adapter puts the overlay in its own
layer directory — so the check queried a coordinate the row was never at and
concluded the document did not exist. Two documents were unreachable in a live
deployment: present to every read, undeletable by any caller.

The check is not "does something by this name exist somewhere". It is "will the
operation I am about to run find a row". Asked at different coordinates it is a
check of a different question, and its answer means nothing.

The quartet is tested TOGETHER on purpose. A test that only exercised delete
would let write, list, get and delete drift apart again one call at a time; what
must hold is that all four resolve the SAME document for the SAME coordinates.

Stores: the filesystem adapter and BOTH dialects of the SQL adapter. The bug is
only visible where the tenant participates in the lookup, so a filesystem-only
test would have been a test of the wrong layer.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.adapters.sqlalchemy_ import SqlAlchemySource
from dna.application import documents as D
from dna.application.live import LiveDna
from dna.kernel import Kernel
from dna.kernel.kinds import registry as registry_mod
from dna.kernel.protocols import TenantNotAllowed

_SCOPE = "probe-scope"
_WORKSPACE = "ws-000000000000000000000001"

# A tenant-authored Kind, in the namespace its author was assigned — the exact
# shape of the report. The alias must carry the namespace owner (the registry
# refuses a bare alias), so it is derived here rather than spelled twice.
_NAMESPACE = "ws-deadbeefcafe.dna.local"
_TENANT_AV = f"{_NAMESPACE}/v1"
_TENANT_KIND = "ProbeCheck"
_ALIAS = "ws-deadbeefcafe-dna-local-probe-check"

# A BUILTIN tenanted Kind, so the defect is not read as something peculiar to
# store-loaded Kinds: it is the coordinate mismatch, and it reaches every Kind
# whose documents live in a tenant layer.
_BUILTIN_KIND = "Agent"

# The board is GLOBAL — ``_write_tenant`` returns None for it. It is the control
# for the second inconsistency of the same family (see the GLOBAL section).
_GLOBAL_KIND = "Story"
_GLOBAL_AV = "github.com/ruinosus/dna/sdlc/v1"


@pytest.fixture(autouse=True)
def _clear_process_wide_warn_caches():
    """The Kind registry's warn caches are process-wide; a store-loaded Kind
    registered here must not silence a warning another module asserts on."""
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()
    yield
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()


def _genome() -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {"description": "probe scope"},
    }


def _kinddef() -> dict:
    """APPROVED — an unapproved store-loaded Kind never registers at all, and
    every assertion below would then hold for the wrong reason."""
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1", "kind": "KindDefinition",
        "metadata": {"name": _ALIAS},
        "spec": {
            "target_api_version": _TENANT_AV,
            "target_kind": _TENANT_KIND,
            "alias": _ALIAS,
            "origin": _NAMESPACE,
            "storage": {"type": "yaml", "container": "probe-checks"},
            "schema": {
                "type": "object",
                "required": ["title"],
                "properties": {"title": {"type": "string"}},
            },
            "approved_by": "approver@example.com",
        },
    }


async def _pg_source():
    """A throwaway schema on the configured Postgres — the ONLY dialect whose
    ``documents`` primary key carries ``tenant`` (i-092), so base and overlay
    rows genuinely coexist there."""
    import asyncpg

    dsn = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DNA_PG_TEST_URL")
        or os.environ.get("DNA_PG_TEST_DSN")
    )
    if not dsn:
        pytest.skip("no Postgres DSN set (DATABASE_URL / DNA_PG_TEST_URL / DNA_PG_TEST_DSN)")
    schema = f"dna_i088_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()
    src = SqlAlchemySource(
        dsn.replace("postgresql://", "postgresql+asyncpg://", 1), schema=schema)
    await src.connect()

    async def cleanup() -> None:
        await src.close()
        c = await asyncpg.connect(dsn)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()

    return src, cleanup


@pytest_asyncio.fixture(params=["filesystem", "sqlite", "postgres"])
async def kernel(request, tmp_path: Path):
    """One kernel per store, each with the tenant-authored Kind registered.

    The Kind is seeded through ``kernel.write_document`` rather than as a file so
    the SAME seeding works on all three — the fixture is about coordinates, not
    about how a KindDefinition arrives."""
    cleanup = None
    if request.param == "filesystem":
        base = tmp_path / ".dna"
        (base / _SCOPE).mkdir(parents=True)
        (base / "_lib").mkdir(parents=True)
        source = FilesystemWritableSource(str(base))
    elif request.param == "sqlite":
        source = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'probe.db'}")
        await source.connect()
    else:
        source, cleanup = await _pg_source()

    k = Kernel.auto(source)
    await k.write_document(_SCOPE, "Genome", _SCOPE, _genome())
    await k.write_document(_SCOPE, "KindDefinition", _ALIAS, _kinddef())
    await k.instance_async(_SCOPE)
    assert k.kind_port_for(_TENANT_KIND, scope=_SCOPE) is not None, (
        "the tenant-authored Kind did not register — every assertion below "
        "would then be measuring an unregistered Kind"
    )
    try:
        yield k
    finally:
        if cleanup is not None:
            await cleanup()


@pytest.fixture()
def live(kernel):
    return LiveDna(base_scope=_SCOPE, kernel=kernel, provider=None)


def _spec_for(kind: str) -> dict:
    return {"title": "probe"} if kind == _TENANT_KIND else {"instruction": "probe"}


# ── the reproduction ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_finds_the_document_the_tenant_write_created(live):
    """RED before the fix, with the reported error verbatim:

        UnknownDocumentError: ProbeCheck 'c1' not found in scope 'probe-scope'
        — nothing to delete

    The write below is the ordinary one; nothing about these coordinates is
    exotic. That is what made the defect so hard to believe from the outside —
    the document was right there in every listing.
    """
    await D.write_document_impl(
        live, kind=_TENANT_KIND, name="c1", spec=_spec_for(_TENANT_KIND),
        scope=_SCOPE, tenant=_WORKSPACE, api_version=_TENANT_AV,
    )
    out = await D.delete_document_impl(
        live, kind=_TENANT_KIND, name="c1", api_version=_TENANT_AV,
        scope=_SCOPE, tenant=_WORKSPACE,
    )
    assert out["deleted"] is True
    assert out["tenant"] == _WORKSPACE


@pytest.mark.parametrize(
    ("kind", "api_version"),
    [(_TENANT_KIND, _TENANT_AV), (_BUILTIN_KIND, None)],
    ids=["tenant-authored-kind", "builtin-tenanted-kind"],
)
@pytest.mark.asyncio
async def test_the_quartet_agrees_on_one_document(live, kernel, kind, api_version):
    """Write, list, get and delete must resolve the SAME document for the SAME
    coordinates — and the delete must actually remove it.

    Covering delete alone would leave the four free to drift apart again; the
    defect WAS a drift, between two calls that were each individually defensible.
    """
    written = await D.write_document_impl(
        live, kind=kind, name="c1", spec=_spec_for(kind),
        scope=_SCOPE, tenant=_WORKSPACE, api_version=api_version,
    )
    av = written["api_version"]
    assert written["tenant"] == _WORKSPACE

    listed = await D.list_documents_impl(
        live, kind=kind, scope=_SCOPE, tenant=_WORKSPACE, api_version=api_version)
    assert [d["name"] for d in listed["documents"]] == ["c1"]

    got = await D.get_document_impl(
        live, kind=kind, name="c1", scope=_SCOPE, tenant=_WORKSPACE,
        api_version=api_version)
    assert got["name"] == "c1"

    deleted = await D.delete_document_impl(
        live, kind=kind, name="c1", api_version=av,
        scope=_SCOPE, tenant=_WORKSPACE)
    assert deleted["deleted"] is True

    # …and the delete really landed: the list the write appeared in is empty,
    # and a second delete is honestly refused rather than quietly succeeding.
    after = await D.list_documents_impl(
        live, kind=kind, scope=_SCOPE, tenant=_WORKSPACE, api_version=api_version)
    assert after["documents"] == []
    with pytest.raises(D.UnknownDocumentError):
        await D.delete_document_impl(
            live, kind=kind, name="c1", api_version=av,
            scope=_SCOPE, tenant=_WORKSPACE)


@pytest.mark.asyncio
async def test_the_existence_check_reads_at_the_delete_coordinates(live, kernel):
    """The property under the fix, asserted directly rather than inferred from a
    green delete: whatever tenant the delete ACTS on is the tenant the check
    READ at. A future refactor that reintroduces the mismatch fails here with a
    message that names the defect, instead of somewhere downstream."""
    await D.write_document_impl(
        live, kind=_TENANT_KIND, name="c1", spec=_spec_for(_TENANT_KIND),
        scope=_SCOPE, tenant=_WORKSPACE, api_version=_TENANT_AV)

    seen: dict[str, object] = {}
    real_get, real_delete = kernel.get_document, kernel.delete_document

    async def spy_get(scope, kind, name, **kw):
        seen["checked_at"] = kw.get("tenant")
        return await real_get(scope, kind, name, **kw)

    async def spy_delete(scope, kind, name, **kw):
        seen["acted_on"] = kw.get("tenant")
        return await real_delete(scope, kind, name, **kw)

    kernel.get_document, kernel.delete_document = spy_get, spy_delete
    try:
        await D.delete_document_impl(
            live, kind=_TENANT_KIND, name="c1", api_version=_TENANT_AV,
            scope=_SCOPE, tenant=_WORKSPACE)
    finally:
        kernel.get_document, kernel.delete_document = real_get, real_delete

    assert seen["checked_at"] == seen["acted_on"] == _WORKSPACE, (
        f"the existence check read at tenant={seen.get('checked_at')!r} while the "
        f"delete acted on tenant={seen.get('acted_on')!r} — a check at other "
        f"coordinates answers a different question than the one being asked"
    )


@pytest.mark.asyncio
async def test_a_base_document_is_still_deletable_without_a_tenant(live):
    """The fix must not buy the tenant layer at the base layer's expense: a
    document written with no tenant stays deletable with no tenant."""
    await D.write_document_impl(
        live, kind=_TENANT_KIND, name="base-1", spec=_spec_for(_TENANT_KIND),
        scope=_SCOPE, api_version=_TENANT_AV)
    out = await D.delete_document_impl(
        live, kind=_TENANT_KIND, name="base-1", api_version=_TENANT_AV, scope=_SCOPE)
    assert out["deleted"] is True and out["tenant"] is None


@pytest.mark.asyncio
async def test_a_tenants_delete_does_not_reach_another_tenants_document(live):
    """Reading at the operation's coordinates is also what keeps the layers
    apart: one workspace's delete must not find — or destroy — another's row."""
    other = "ws-000000000000000000000002"
    await D.write_document_impl(
        live, kind=_TENANT_KIND, name="c1", spec=_spec_for(_TENANT_KIND),
        scope=_SCOPE, tenant=other, api_version=_TENANT_AV)
    with pytest.raises(D.UnknownDocumentError):
        await D.delete_document_impl(
            live, kind=_TENANT_KIND, name="c1", api_version=_TENANT_AV,
            scope=_SCOPE, tenant=_WORKSPACE)
    still_there = await D.get_document_impl(
        live, kind=_TENANT_KIND, name="c1", scope=_SCOPE, tenant=other,
        api_version=_TENANT_AV)
    assert still_there["name"] == "c1"


# ── the GLOBAL-Kind twin, and the measurement behind the verdict ────────────
#
# ``write_document_impl`` had the same family of asymmetry, latent: it checked
# with ``tenant=tenant`` and wrote with ``tenant=_write_tenant(port, tenant)``,
# which is None for a GLOBAL Kind. The two tests below are the measurement that
# decided it — see the comment at the check in ``documents.py``.


@pytest.mark.asyncio
async def test_a_global_kind_can_never_have_a_tenant_row(kernel):
    """Half of why the GLOBAL asymmetry was never observed breaking: the write
    pipeline REFUSES a tenanted write for a GLOBAL Kind, so there is no overlay
    row for the check to find and mistake for the base row it would then
    overwrite."""
    with pytest.raises(TenantNotAllowed):
        await kernel.write_document(
            _SCOPE, _GLOBAL_KIND, "s-1",
            {"apiVersion": _GLOBAL_AV, "kind": _GLOBAL_KIND,
             "metadata": {"name": "s-1"},
             "spec": {"title": "t", "description": "d", "status": "todo"}},
            tenant=_WORKSPACE,
        )


@pytest.mark.asyncio
async def test_a_global_kind_resolves_the_same_document_at_both_coordinates(
    live, kernel,
):
    """The other half: for a GLOBAL Kind the two readings are the same document.
    ``get_document(tenant=X)`` probes the overlay and FALLS BACK to the base
    layer, so a check at ``tenant`` and a check at ``None`` return byte-identical
    results — measured here rather than assumed, on every store."""
    await D.write_document_impl(
        live, kind=_GLOBAL_KIND, name="s-1",
        spec={"title": "one", "description": "d", "status": "todo"},
        scope=_SCOPE, tenant=_WORKSPACE)

    at_tenant = await kernel.get_document(_SCOPE, _GLOBAL_KIND, "s-1", tenant=_WORKSPACE)
    at_base = await kernel.get_document(_SCOPE, _GLOBAL_KIND, "s-1")
    assert at_tenant is not None and at_tenant == at_base


@pytest.mark.asyncio
async def test_a_global_kind_checks_and_writes_at_the_same_coordinates(live, kernel):
    """With the measurement in hand the asymmetry was removed rather than
    documented: the check now reads at ``_write_tenant``, exactly where the write
    lands. Provably a no-op today (the two tests above), and the only reading
    that survives a Kind whose declared scope CHANGES from tenanted to global —
    where stale overlay rows do exist, and the old check would have merged one
    into the shared base."""
    seen: dict[str, object] = {}
    real_get, real_write = kernel.get_document, kernel.write_document

    async def spy_get(scope, kind, name, **kw):
        seen["checked_at"] = kw.get("tenant")
        return await real_get(scope, kind, name, **kw)

    async def spy_write(scope, kind, name, raw, *a, **kw):
        seen["wrote_at"] = kw.get("tenant")
        return await real_write(scope, kind, name, raw, *a, **kw)

    kernel.get_document, kernel.write_document = spy_get, spy_write
    try:
        await D.write_document_impl(
            live, kind=_GLOBAL_KIND, name="s-1",
            spec={"title": "one", "description": "d", "status": "todo"},
            scope=_SCOPE, tenant=_WORKSPACE)
    finally:
        kernel.get_document, kernel.write_document = real_get, real_write

    assert seen["checked_at"] == seen["wrote_at"] is None


@pytest.mark.asyncio
async def test_a_global_kind_still_merges_and_deletes(live):
    """The GLOBAL path's BEHAVIOUR is unchanged by the above: an update still
    finds the stored document and merges over it (rather than replacing it), and
    the delete still goes through."""
    await D.write_document_impl(
        live, kind=_GLOBAL_KIND, name="s-1",
        spec={"title": "one", "description": "d", "status": "todo"},
        scope=_SCOPE, tenant=_WORKSPACE)
    second = await D.write_document_impl(
        live, kind=_GLOBAL_KIND, name="s-1", spec={"status": "in-progress"},
        scope=_SCOPE, tenant=_WORKSPACE)
    assert second["created"] is False and second["merged"] is True

    got = await D.get_document_impl(
        live, kind=_GLOBAL_KIND, name="s-1", scope=_SCOPE, tenant=_WORKSPACE)
    assert got["document"]["spec"]["title"] == "one", (
        "the update dropped a field the caller did not send — the check no "
        "longer resolves the stored document")
    assert got["document"]["spec"]["status"] == "in-progress"

    out = await D.delete_document_impl(
        live, kind=_GLOBAL_KIND, name="s-1", api_version=_GLOBAL_AV,
        scope=_SCOPE, tenant=_WORKSPACE)
    assert out["deleted"] is True and out["tenant"] is None
