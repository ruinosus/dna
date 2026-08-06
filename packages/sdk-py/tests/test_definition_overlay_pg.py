"""Definition override, end-to-end on Postgres (s-strain-customization-ui).

Proves against the pg dialect of SqlAlchemySource — the adapter the published
env uses — that apply/read/revert compose base+override correctly AND that a
LOCKED Kind write is vetoed by the write pipeline. Extends the fixture pattern of
test_layers_integration.py.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from dna.adapters.sqlalchemy_ import SqlAlchemySource
from dna.application.live import LiveDna
from dna.application.runtime import (
    apply_definition_impl,
    read_definition_impl,
    revert_definition_impl,
)
from dna.kernel import Kernel
from dna.kernel.protocols import LayerPolicyViolationError

pytestmark = pytest.mark.requires_postgres

_SCOPE = "test-strain"
_WID = "ws-pg000000000000000000001"

GENOME_RAW = {
    "apiVersion": "github.com/ruinosus/dna/v1",
    "kind": "Genome",
    "metadata": {"name": _SCOPE, "description": "Test strain"},
    "spec": {
        "default_agent": "brad",
        "layers": {"tenant": "open"},
    },
}

AGENT_BRAD_RAW = {
    "apiVersion": "github.com/ruinosus/dna/v1",
    "kind": "Agent",
    "metadata": {"name": "brad", "description": "Base architect"},
    "spec": {
        "instruction": "Base architect.",
    },
}

# Phase 16 — overlay rules live in LayerPolicy docs, not Genome.spec.layers.
# Policy keys by Kind ALIAS (i-049): AgentKind.alias = "helix-agent",
# MCPFederationKind.alias = "federation-mcp".
LAYER_POLICY_RAW = {
    "apiVersion": "github.com/ruinosus/dna/policy/v1",
    "kind": "LayerPolicy",
    "metadata": {"name": "tenant-default"},
    "spec": {
        "layer_id": "tenant",
        "policies": {"helix-agent": "open", "federation-mcp": "locked"},
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
    schema = f"dna_defoverlay_{uuid.uuid4().hex[:12]}"
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


@pytest_asyncio.fixture
async def live_pg():
    """A LiveDna over a fresh pg schema, seeded with scope ``test-strain``:
    a Genome, an Agent "brad", and a LayerPolicy locking MCPFederation while
    leaving Agent open."""
    source, cleanup = await _pg_env()
    for kind, name, raw in [
        ("Genome", _SCOPE, GENOME_RAW),
        ("LayerPolicy", "tenant-default", LAYER_POLICY_RAW),
        ("Agent", "brad", AGENT_BRAD_RAW),
    ]:
        await source.save_instance(_SCOPE, kind, name, raw)
        await source.publish(_SCOPE, kind, name)

    kernel = _make_kernel(source)
    yield LiveDna(
        base_scope=_SCOPE, kernel=kernel, provider=None,
        vendor_workspace=None, workspace_definitions_base=_SCOPE,
    )
    await cleanup()


@pytest.mark.asyncio
async def test_apply_read_revert_compose(live_pg) -> None:
    before = await read_definition_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Agent", name="brad")
    assert before["overridden"] is False
    assert before["effective"]["instruction"] == "Base architect."

    await apply_definition_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Agent", name="brad",
        spec={"instruction": "Focus on compliance."})
    after = await read_definition_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Agent", name="brad")
    assert after["overridden"] is True
    assert "compliance" in after["effective"]["instruction"].lower()

    # base for a DIFFERENT (no) tenant is unchanged
    base = await read_definition_impl(
        live_pg, scope=_SCOPE, tenant=None, kind="Agent", name="brad")
    assert base["effective"]["instruction"] == "Base architect."

    await revert_definition_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Agent", name="brad")
    reverted = await read_definition_impl(
        live_pg, scope=_SCOPE, tenant=_WID, kind="Agent", name="brad")
    assert reverted["overridden"] is False
    assert reverted["effective"]["instruction"] == "Base architect."


@pytest.mark.asyncio
async def test_locked_kind_write_is_vetoed(live_pg) -> None:
    with pytest.raises(LayerPolicyViolationError):
        await apply_definition_impl(
            live_pg, scope=_SCOPE, tenant=_WID, kind="MCPFederation", name="anything",
            spec={"servers": []})
