"""A personal Engram is reachable by every memory verb, and ``forget`` says which
of the three things happened.

``recall`` and ``remember`` have carried ``personal=`` since personal memory
shipped, so a private memory could be written and read — and then never listed,
never forgotten and never consolidated, because ``list_memories`` / ``forget`` /
``consolidate`` had no parameter to name the partition. The partition was
write-and-read-only by accident.

``forget`` was the worst of the three. Asked for a personal memory it looked in
the WORKSPACE layer, found nothing, and answered ``forgotten: false`` — the same
word it uses for "already forgotten". So the caller could not tell "there is
nothing left to do" from "you are looking in the wrong place", which is exactly
the distinction that would have revealed the missing parameter.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_PERSONAL_ID", "oid-barna")
    return dst


def _call(server, tool, args):
    from fastmcp import Client

    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(go())


def _server(dna_dir):
    from dna_cli import _mcp_server as M

    return M.build_server(scope=_SCOPE, base_dir=str(dna_dir))


def test_the_three_verbs_now_take_personal(dna_dir):
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    async def go(server):
        async with Client(server) as client:
            return {t.name: t.inputSchema for t in await client.list_tools()}

    schemas = asyncio.run(go(_server(dna_dir)))
    for tool in ("list_memories", "forget", "consolidate", "recall", "remember"):
        assert "personal" in schemas[tool]["properties"], tool


def test_a_personal_memory_is_listable(dna_dir):
    pytest.importorskip("fastmcp")
    server = _server(dna_dir)
    _call(server, "remember", {"summary": "my own private lesson",
                               "personal": True})

    personal = _call(server, "list_memories", {"personal": True})
    summaries = {m["summary"] for m in personal.structured_content["memories"]}
    assert "my own private lesson" in summaries
    assert any(
        m["personal"] for m in personal.structured_content["memories"]
        if m["summary"] == "my own private lesson"
    )

    # …and it is NOT in the workspace's shared list (the partition still holds).
    shared = _call(server, "list_memories", {"scope": _SCOPE})
    assert "my own private lesson" not in {
        m["summary"] for m in shared.structured_content["memories"]}


def test_a_personal_memory_is_forgettable(dna_dir):
    pytest.importorskip("fastmcp")
    server = _server(dna_dir)
    written = _call(server, "remember", {"summary": "forget me please",
                                         "personal": True})
    name = written.structured_content["name"]

    out = _call(server, "forget", {"name": name, "personal": True})
    assert out.structured_content["forgotten"] is True
    assert out.structured_content["outcome"] == "forgotten"

    listed = _call(server, "list_memories", {"personal": True})
    assert "forget me please" not in {
        m["summary"] for m in listed.structured_content["memories"]}


def test_forget_distinguishes_already_forgotten_from_not_found(dna_dir):
    pytest.importorskip("fastmcp")
    server = _server(dna_dir)
    name = _call(server, "remember", {
        "summary": "twice forgotten", "personal": True},
    ).structured_content["name"]

    first = _call(server, "forget", {"name": name, "personal": True})
    second = _call(server, "forget", {"name": name, "personal": True})
    missing = _call(server, "forget", {"name": "no-such-memory-at-all",
                                       "personal": True})

    assert first.structured_content["outcome"] == "forgotten"
    assert second.structured_content["outcome"] == "already_forgotten"
    assert missing.structured_content["outcome"] == "not_found"
    # the old boolean still answers "did this call change anything" for both.
    assert second.structured_content["forgotten"] is False
    assert missing.structured_content["forgotten"] is False


def test_looking_in_the_wrong_partition_reports_not_found(dna_dir):
    """The concrete confusion the split removes: a personal memory asked for
    WITHOUT ``personal=true`` is ``not_found``, not "already forgotten"."""
    pytest.importorskip("fastmcp")
    server = _server(dna_dir)
    name = _call(server, "remember", {
        "summary": "only mine", "personal": True},
    ).structured_content["name"]

    wrong = _call(server, "forget", {"name": name, "scope": _SCOPE})
    assert wrong.structured_content["outcome"] == "not_found"

    right = _call(server, "forget", {"name": name, "personal": True})
    assert right.structured_content["outcome"] == "forgotten"


def test_consolidate_can_target_the_personal_partition(dna_dir):
    pytest.importorskip("fastmcp")
    server = _server(dna_dir)
    _call(server, "remember", {"summary": "a personal memory to score",
                               "personal": True})
    out = _call(server, "consolidate", {"personal": True})
    assert out.structured_content  # a real pass, not a refusal
