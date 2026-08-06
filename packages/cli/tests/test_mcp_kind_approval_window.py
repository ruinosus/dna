"""The MCP face honours a Kind approved on ANOTHER replica, within the window.

The core seam is measured in ``packages/sdk-py/tests/
test_kind_approval_rebuild_trigger.py``; this file answers the only question that
file cannot: is the seam actually WIRED into the served face?

It matters because the MCP instance tools do not call the core use-cases
directly — ``_mcp_instances._guard_for`` resolves the Kind itself, before the
use-case runs, so that it can meter the call against the target Kind's family
(i-081). A fix applied only inside ``dna.application.instances`` would be
bypassed by that earlier resolution and the served product would still answer
"Kind not registered" for a Kind the workspace had just approved.

The setup is a real two-replica one: a ``boot_live`` handle authors and approves
the Kind, and the SERVER — a different process-shaped handle over the same store
— is warmed BEFORE that happens and never told. Nothing invalidates the server,
nothing rebuilds it. The only thing that can make the write land is the instance
tool's own refresh.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
import time

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_TENANT = "ws-acme"
_SCHEMA = {
    "type": "object",
    "properties": {"titulo": {"type": "string"}},
    "required": ["titulo"],
}
#: Short enough to keep the test fast, long enough that the "still refused"
#: assertion below is not racing the clock. The default is 30 s; what is under
#: test is that the window EXISTS and that expiry reaches the face, not its size.
_TTL = "0.05"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    # The namespace registry lives in the system scope, and the authoring door
    # reads it before it will mint a namespace for the workspace. The example
    # scope ships without one.
    lib = dst / "_lib"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n  name: _lib\n"
        "spec: {}\n"
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_KIND_REFRESH_TTL", _TTL)
    return dst


def _call(server, tool, args):
    from fastmcp import Client

    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(go())


def _refused(server, tool, args) -> str:
    with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
        _call(server, tool, args)
    return str(ei.value)


def _approve_on_a_sibling_replica(dna_dir, *, revoke: bool = False) -> None:
    """Author + approve (or revoke) through a SEPARATE live handle.

    A different ``boot_live`` is a different kernel over the same store, which
    is exactly what a second pod is. Nothing here touches the server's handle."""
    from dna.application.kind_authoring import (
        approve_kind_impl,
        author_kind_impl,
        revoke_kind_impl,
    )
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        if revoke:
            await revoke_kind_impl(
                live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
                now="2026-07-28T12:00:00Z",
            )
            return
        await author_kind_impl(
            live, kind="Deal", schema=_SCHEMA, tenant=_TENANT,
            now="2026-07-28T10:00:00Z", actor="author@acme.example",
        )
        await approve_kind_impl(
            live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
            now="2026-07-28T11:00:00Z",
        )

    asyncio.run(go())


def test_the_document_tools_pick_up_a_kind_approved_elsewhere(dna_dir):
    """Approve on replica A → the SERVER writes the Kind within the window."""
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    # Warm the server: its live handle is built and its registry window stamped
    # for this scope, with the Kind absent. Without this the server's FIRST
    # build would happen after the approval and would register the Kind for
    # reasons that have nothing to do with the fix.
    _call(server, "list_kinds", {"scope": _SCOPE})
    msg = _refused(server, "write_instance", {
        "kind": "Deal", "name": "deal-early", "scope": _SCOPE,
        "spec": {"titulo": "cedo demais"}})
    assert "not registered" in msg, msg

    _approve_on_a_sibling_replica(dna_dir)
    time.sleep(float(_TTL) * 2)

    out = _call(server, "write_instance", {
        "kind": "Deal", "name": "deal-1", "scope": _SCOPE,
        "spec": {"titulo": "chegou"}})
    assert "deal-1" in str(out)

    # …and the catalog agrees, on the same replica, without a restart.
    catalog = _call(server, "list_kinds", {"scope": _SCOPE})
    assert "Deal" in str(catalog)


def test_the_document_tools_close_on_a_revocation_made_elsewhere(dna_dir):
    """The half that must not lag: revoke on replica A → the SERVER refuses.

    A revocation that only tightens "eventually" leaves the served face
    accepting instances of a Kind the workspace has already withdrawn."""
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    _call(server, "list_kinds", {"scope": _SCOPE})
    _approve_on_a_sibling_replica(dna_dir)
    time.sleep(float(_TTL) * 2)
    _call(server, "write_instance", {
        "kind": "Deal", "name": "deal-before", "scope": _SCOPE,
        "spec": {"titulo": "antes"}})

    _approve_on_a_sibling_replica(dna_dir, revoke=True)
    time.sleep(float(_TTL) * 2)

    msg = _refused(server, "write_instance", {
        "kind": "Deal", "name": "deal-after", "scope": _SCOPE,
        "spec": {"titulo": "depois"}})
    assert "revoked" in msg.lower(), msg
