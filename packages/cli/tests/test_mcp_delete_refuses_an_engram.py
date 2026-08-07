"""The generic MCP delete REFUSES an Engram, and says where to go instead (i-130).

Through the real door — a booted ``fastmcp`` server and the ``delete_instance``
tool as an agent calls it — because the version of this that lives one layer down
(``tests/test_generic_delete.py`` in the SDK) asks a pure function about a
registry, and this house has already shipped a validator that was correct,
unit-tested and called by nobody.

What each case would catch, in one line:

* the refusal ARRIVES (not a crash, not a silent success) and NAMES ``forget``;
* the memory is still readable through the same face afterwards — the tool that
  refused did not half-delete;
* ``forget`` through the face works on that same memory, so the way out the
  refusal names is a way out and not a slogan;
* an ordinary Kind still deletes through the same tool, so what shipped is a
  Kind rule and not a delete freeze.

Mutant for all four: drop ``record.invalidate-only`` from
``dna/extensions/helix/kinds/engram.kind.yaml``. The first three go red.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_ENGRAM_AV = "github.com/ruinosus/dna/v1"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
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


def _seed_memory(dna_dir, summary: str) -> str:
    """One memory through the SAME impl the ``remember`` tool uses."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.remember_impl(live, summary, scope=_SCOPE)

    return asyncio.run(go())["name"]


def test_delete_instance_refuses_an_engram_and_names_forget(dna_dir):
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    name = _seed_memory(dna_dir, "a memória que ninguém apaga")
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))

    msg = _refused(server, "delete_instance", {
        "kind": "Engram", "name": name,
        "api_version": _ENGRAM_AV, "scope": _SCOPE})
    assert "INVALIDATE-ONLY" in msg, msg
    assert "forget" in msg, (
        "a refusal that does not name the way out is a wall — and a wall is "
        "what sends somebody to psql, which is worse than the delete"
    )

    # …and it is still there, read back through the same face.
    got = _call(server, "get_instance",
                {"kind": "Engram", "name": name, "scope": _SCOPE})
    assert got.structured_content["instance"]["metadata"]["name"] == name


def test_the_way_out_the_refusal_names_actually_works(dna_dir):
    """``forget`` through the face: the memory is demoted (``valid_to`` stamped)
    and the instance is STILL readable — which is the whole difference between
    the path that was refused and the path that was named."""
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    name = _seed_memory(dna_dir, "a memória que se aposenta direito")
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))

    out = _call(server, "forget", {"name": name, "scope": _SCOPE}).structured_content
    assert out.get("forgotten") is True, out
    got = _call(server, "get_instance",
                {"kind": "Engram", "name": name, "scope": _SCOPE})
    spec = got.structured_content["instance"]["spec"]
    assert spec.get("valid_to"), "forget stamps the world-time end"


def test_the_catalog_says_so_before_anybody_tries(dna_dir):
    """``list_kinds`` reports ``deletable``/``delete_refusal`` per Kind, and an
    agent that reads it never writes the failing call. Mutant: report the
    refusal only when the delete is attempted — every caller learns by being
    denied."""
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    out = _call(server, "list_kinds", {"scope": _SCOPE}).structured_content
    by_kind = {e["kind"]: e for e in out["kinds"]}
    assert by_kind["Engram"]["deletable"] is False
    assert "forget" in by_kind["Engram"]["delete_refusal"]


def test_an_ordinary_kind_still_deletes_through_the_same_tool(dna_dir):
    """Mutant: gate on ``plane == 'record'`` (or anything else the Engram
    happens to be) instead of on the declared trait. This goes red, and what
    shipped would be a delete freeze wearing a Kind rule's name."""
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    _call(server, "write_instance", {
        "kind": "ModelProfile", "name": "mp-x", "scope": _SCOPE,
        "spec": {"model_id": "x", "provider": "y"}})
    out = _call(server, "delete_instance", {
        "kind": "ModelProfile", "name": "mp-x",
        "api_version": "github.com/ruinosus/dna/modelreg/v1", "scope": _SCOPE})
    assert out.structured_content["deleted"] is True
