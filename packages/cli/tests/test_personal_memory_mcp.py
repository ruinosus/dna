"""Personal memory over the MCP impl surface (data layer, no server/auth).

Covers ``s-personal-memory-surfaces`` (MCP face) at the transport-agnostic
``*_impl`` layer, mirroring ``test_mcp_memory``'s tenant-isolation proof: a
``memory_scope="personal"`` remember/recall keys on ``personal:<oid>`` and is
isolated from the workspace AND from a different identity. The oid-from-token
resolution seam itself is unit-tested in ``test_personal_memory_cmd``.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_OID_A = "aaaa1111-0000-0000-0000-000000000001"
_OID_B = "bbbb2222-0000-0000-0000-000000000002"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def test_personal_impl_isolated_from_workspace_and_other_identity(dna_dir):
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        # A remembers privately; a workspace memory is written too.
        await M.remember_impl(
            live, "A PRIVATE roadmap pivot alpha", memory_scope="personal", oid=_OID_A)
        await M.remember_impl(
            live, "WORKSPACE roadmap pivot shared", scope=_SCOPE, tenant="acme")
        a = await M.recall_impl(
            live, "roadmap pivot", memory_scope="personal", oid=_OID_A, k=10)
        b = await M.recall_impl(
            live, "roadmap pivot", memory_scope="personal", oid=_OID_B, k=10)
        ws = await M.recall_impl(live, "roadmap pivot", scope=_SCOPE, tenant="acme", k=10)
        return a, b, ws

    a, b, ws = asyncio.run(scenario())
    a_names = {h["name"] for h in a["hits"]}
    b_names = {h["name"] for h in b["hits"]}
    ws_names = {h["name"] for h in ws["hits"]}
    # A sees A's private memory ...
    assert a_names, a_names
    # ... B (different identity) sees NONE of A's ...
    assert not (a_names & b_names)
    # ... and the workspace recall sees NONE of A's private memory.
    assert not (a_names & ws_names)


def test_personal_impl_fails_closed_without_oid(dna_dir):
    from dna_cli import _mcp_server as M
    from dna.memory.personal import PersonalIdentityRequired

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.recall_impl(live, "anything", memory_scope="personal", oid=None, k=5)

    with pytest.raises(PersonalIdentityRequired):
        asyncio.run(scenario())
