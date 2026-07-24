"""Bundle-entry fork, end-to-end on Postgres (s-strain-bundle-fork B2/B3).

Proves against the pg dialect of SqlAlchemySource — the adapter the published
env uses — that the four bundle-entry use-cases (list/read/write/revert)
compose base+tenant-override file forks correctly, AND that a LOCKED-Kind
fork write is vetoed. Mirrors test_definition_overlay_pg.py's fixture pattern
(fresh throwaway schema, asyncpg + SqlAlchemySource, LiveDna) and
test_bundle_entry_impls.py's Skill-bundle seed (SKILL.md + scripts/hello.py).
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from dna.adapters.sqlalchemy_ import SqlAlchemySource
from dna.application.live import LiveDna
from dna.application.runtime import (
    list_bundle_entries_impl, read_bundle_entry_impl,
    revert_bundle_entry_impl, write_bundle_entry_impl,
)
from dna.kernel import Kernel
from dna.kernel.protocols import LayerPolicyViolationError

pytestmark = pytest.mark.requires_postgres

_SCOPE = "test-bundle"
_WID = "ws-bundle0000000000000001"

GENOME_RAW = {
    "apiVersion": "github.com/ruinosus/dna/v1",
    "kind": "Genome",
    "metadata": {"name": _SCOPE, "description": "Test bundle scope"},
    "spec": {
        "default_agent": None,
        "layers": {"tenant": "open"},
    },
}

SKILL_MD_BASE = "---\nname: greeter\n---\nBase.\n"
HELLO_PY_BASE = "print('base')\n"


def _layer_policy_raw(*, skill_policy: str) -> dict:
    """Policy keys by Kind ALIAS (i-049): SkillKind.alias = "agentskills-skill",
    MCPFederationKind.alias = "federation-mcp"."""
    return {
        "apiVersion": "github.com/ruinosus/dna/policy/v1",
        "kind": "LayerPolicy",
        "metadata": {"name": "tenant-default"},
        "spec": {
            "layer_id": "tenant",
            "policies": {"agentskills-skill": skill_policy, "federation-mcp": "locked"},
        },
    }


async def _pg_env():
    """Fresh throwaway schema + connected pg-dialect SqlAlchemySource."""
    import asyncpg

    dsn = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DNA_PG_TEST_URL")
        or os.environ.get("DNA_PG_TEST_DSN")
    )
    schema = f"dna_bundleoverlay_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()
    sa_url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    src = SqlAlchemySource(sa_url, schema=schema)
    await src.connect()

    async def cleanup() -> None:
        await src.close()
        c = await asyncpg.connect(dsn)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()

    return src, cleanup


def _make_kernel(source: SqlAlchemySource) -> Kernel:
    """Build a Kernel wired to the pg source with all extensions loaded."""
    k = Kernel.auto()
    k.source(source)

    # No cache dependency needed for this scenario; Kernel.instance() still
    # requires one to be configured.
    class _NoOpCache:
        async def has(self, scope, key):
            return True

        async def load_all(self, scope, readers=None):
            return []

        async def store(self, scope, key, items):
            pass

    k.cache(_NoOpCache())
    return k


async def _seed(source: SqlAlchemySource, *, skill_policy: str) -> None:
    """Seed scope ``test-bundle``: a Genome, a LayerPolicy (Skill @
    ``skill_policy``, MCPFederation locked), and a base Skill bundle
    (greeter/SKILL.md + greeter/scripts/hello.py) as tenant-less (base)
    bundle-entry rows."""
    for kind, name, raw in [
        ("Genome", _SCOPE, GENOME_RAW),
        ("LayerPolicy", "tenant-default", _layer_policy_raw(skill_policy=skill_policy)),
    ]:
        await source.save_document(_SCOPE, kind, name, raw)
        await source.publish(_SCOPE, kind, name)
    await source.write_bundle_entry(_SCOPE, "Skill", "greeter", "SKILL.md", SKILL_MD_BASE)
    await source.write_bundle_entry(_SCOPE, "Skill", "greeter", "scripts/hello.py", HELLO_PY_BASE)


@pytest_asyncio.fixture
async def live_pg():
    """A LiveDna over a fresh pg schema, seeded with scope ``test-bundle``:
    a Genome, a base Skill bundle "greeter" (SKILL.md + scripts/hello.py),
    and a LayerPolicy leaving Skill OPEN (MCPFederation stays LOCKED, unused
    here — mirrors test_definition_overlay_pg.py's policy shape)."""
    source, cleanup = await _pg_env()
    await _seed(source, skill_policy="open")
    kernel = _make_kernel(source)
    yield LiveDna(
        base_scope=_SCOPE, kernel=kernel, provider=None,
        vendor_workspace=None, workspace_definitions_base=_SCOPE,
    )
    await cleanup()


@pytest_asyncio.fixture
async def live_pg_locked():
    """Same seed, but the LayerPolicy LOCKS the Skill Kind (agentskills-skill)
    — used to prove a fork write on a genuinely locked bundle Kind is vetoed."""
    source, cleanup = await _pg_env()
    await _seed(source, skill_policy="locked")
    kernel = _make_kernel(source)
    yield LiveDna(
        base_scope=_SCOPE, kernel=kernel, provider=None,
        vendor_workspace=None, workspace_definitions_base=_SCOPE,
    )
    await cleanup()


@pytest.mark.asyncio
async def test_write_read_list_revert_compose(live_pg) -> None:
    # base, before any fork: not overridden, base content.
    before = await read_bundle_entry_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter",
        entry="scripts/hello.py")
    assert before["overridden"] is False
    assert before["content"] == HELLO_PY_BASE

    # fork it for the tenant.
    await write_bundle_entry_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter",
        entry="scripts/hello.py", content="print('mine')\n")

    after = await read_bundle_entry_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter",
        entry="scripts/hello.py")
    assert after["overridden"] is True
    assert after["content"] == "print('mine')\n"

    # the BASE layer (no tenant) is untouched — fetch directly through the
    # kernel to assert base-vs-tenant isolation at the primitive level.
    base_raw = await live_pg.kernel.fetch_bundle_entry_async(
        _SCOPE, "Skill", "greeter", "scripts/hello.py", tenant=None)
    assert base_raw == HELLO_PY_BASE.encode("utf-8")

    # list flags the forked entry, and only that one, as overridden.
    listing = await list_bundle_entries_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter")
    by_entry = {e["entry"]: e["overridden"] for e in listing["entries"]}
    assert by_entry["scripts/hello.py"] is True
    assert by_entry["SKILL.md"] is False

    # revert → base composes through again.
    await revert_bundle_entry_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter",
        entry="scripts/hello.py")
    reverted = await read_bundle_entry_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter",
        entry="scripts/hello.py")
    assert reverted["overridden"] is False
    assert reverted["content"] == HELLO_PY_BASE


@pytest.mark.asyncio
async def test_write_forbidden_on_locked_skill_layer_policy(live_pg_locked) -> None:
    """A fork of a bundle-file entry on a LOCKED Kind must be vetoed the SAME
    way a spec-override write is (plane A parity, test_definition_overlay_pg.py's
    ``test_locked_kind_write_is_vetoed``) — LayerPolicy governance applies
    uniformly regardless of storage pattern. Targets Skill/agentskills-skill
    (a genuine bundle Kind) rather than MCPFederation: MCPFederation's storage
    pattern isn't "bundle", so ``write_bundle_entry_impl`` would reject it with
    ValueError before ever reaching the policy gate — the LOCKED assertion
    must target a Kind the bundle-entry use-cases actually accept."""
    with pytest.raises(LayerPolicyViolationError, match="LOCKED"):
        await write_bundle_entry_impl(
            live_pg_locked, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter",
            entry="scripts/hello.py", content="print('mine')\n")
