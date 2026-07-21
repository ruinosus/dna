"""MCP Apps (SEP-1865) — the **memory card** at the runtime face.

The memory read tools (``list_memories``, ``recall``) carry a read-only
interactive card: the static template ``ui://dna/memory-list`` is registered
as a resource and pointed from each tool's DECLARATION, so a host that
renders MCP Apps prefetches the template and pushes each result's
``structured_content`` into it. A host WITHOUT the extension reads the same
textual ``content`` as ever — byte-identical (the degradation contract).

Proven end-to-end through the REAL FastMCP protocol (in-memory ``Client``):

1. **degradation is byte-identical** — the textual ``content`` of
   ``list_memories``/``recall`` matches the frozen pre-feature baseline in
   ``fixtures/mcp_apps/`` byte for byte (captured on clean main before the
   card landed; a client without MCP Apps sees zero change);
2. **the declaration carries the pointer** — ``tools/list`` shows both tools
   pointing the ``ui://dna/memory-list`` template (pointer removed → dies);
3. **the template is served** — ``resources/read`` of ``ui://dna/memory-list``
   answers the static template with the SEP-1865 profile mimeType
   (registration removed → dies);
4. **no pre-spec residue** — the tool RESULT carries no UI metadata (the card
   rides the declaration, not the result);
5. **no secret in the surface** — the returned payload and the served
   template carry no bearer / token / tenant header.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "mcp_apps"
_SCOPE = "concierge"

# Canonical payloads pinned for the byte-stability tests. Byte-identity is a
# property of the WIRE SERIALIZATION of a given payload (the store's own
# contents vary by clock), so the payload is pinned and the serialized bytes
# are compared against the fixtures captured on clean main BEFORE the card
# landed. Do not edit these together with the fixtures — that would defeat
# the regression net.
_LIST_DATA = {
    "scope": "concierge",
    "memories": [
        {
            "name": "prefers-tea",
            "summary": "Barna prefers tea over coffee in the afternoon",
            "area": "preferences",
            "tags": ["drink", "routine"],
            "affect": "triumph",
            "created_at": "2026-07-10T14:20:00Z",
        },
        {
            "name": "no-summary-item",
            "summary": None,
            "area": None,
            "tags": [],
            "affect": None,
            "created_at": None,
        },
    ],
}
_RECALL_DATA = {
    "query": "tea",
    "scope": "concierge",
    "degraded": False,
    "semantic": False,
    "hits": [
        {
            "kind": "Engram",
            "name": "prefers-tea",
            "score": 0.8125,
            "retention": 0.9142,
        },
    ],
}


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope (so a memory can be written)."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _call_with_pinned_data(dna_dir, monkeypatch, tool: str, args: dict):
    """Call ``tool`` through the real protocol with the impl pinned to the
    canonical payload — the serialization path (tool fn + result shaping +
    FastMCP framing) is the code under test."""
    from fastmcp import Client

    async def fake_list(*a, **k):
        return json.loads(json.dumps(_LIST_DATA))

    async def fake_recall(*a, **k):
        return json.loads(json.dumps(_RECALL_DATA))

    monkeypatch.setattr(M, "list_memories_impl", fake_list)
    monkeypatch.setattr(M, "recall_impl", fake_recall)

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(scenario())


# ── 1. degradation: textual content byte-identical to the baseline ─────────


def test_list_memories_content_byte_identical_to_baseline(dna_dir, monkeypatch):
    """A client without MCP Apps reads the exact pre-feature bytes: the textual
    ``content`` of ``list_memories`` equals the frozen baseline fixture."""
    result = _call_with_pinned_data(dna_dir, monkeypatch, "list_memories", {"scope": _SCOPE})
    text_blocks = [b for b in result.content if getattr(b, "text", None)]
    assert len(text_blocks) == 1, "expected exactly one textual (data) content block"
    baseline = (_FIXTURES / "list_memories.content.txt").read_bytes()
    assert text_blocks[0].text.encode("utf-8") == baseline


def test_recall_content_byte_identical_to_baseline(dna_dir, monkeypatch):
    """Same contract for ``recall`` — its textual ``content`` is byte-identical
    to the frozen baseline."""
    result = _call_with_pinned_data(
        dna_dir, monkeypatch, "recall", {"query": "tea", "scope": _SCOPE}
    )
    text_blocks = [b for b in result.content if getattr(b, "text", None)]
    assert len(text_blocks) == 1, "expected exactly one textual (data) content block"
    baseline = (_FIXTURES / "recall.content.txt").read_bytes()
    assert text_blocks[0].text.encode("utf-8") == baseline


def test_degradation_client_without_extension_reads_same_bytes(dna_dir, monkeypatch):
    """US3, the whole contract in one scenario: a plain MCP client — one that
    never negotiates the MCP Apps extension and never reads ``ui://`` resources
    — calls BOTH memory read tools and gets textual ``content`` byte-identical
    to the pre-feature baseline, self-sufficient to parse (the JSON in
    ``content`` IS the data; no UI channel needed)."""
    for tool, args, fixture in (
        ("list_memories", {"scope": _SCOPE}, "list_memories.content.txt"),
        ("recall", {"query": "tea", "scope": _SCOPE}, "recall.content.txt"),
    ):
        result = _call_with_pinned_data(dna_dir, monkeypatch, tool, args)
        text_blocks = [b for b in result.content if getattr(b, "text", None)]
        assert len(text_blocks) == 1
        assert text_blocks[0].text.encode("utf-8") == (_FIXTURES / fixture).read_bytes()
        # content alone carries the data — a UI-less client needs nothing else.
        assert json.loads(text_blocks[0].text) == result.structured_content


# ── 2. the result: data mirrored, no pre-spec UI residue ───────────────────


def test_list_memories_result_mirrors_data_and_carries_no_ui_meta(dna_dir):
    """Through the real protocol with the REAL impl: the data is the primary
    ``content`` (a JSON text block every client reads), mirrored in
    ``structured_content``; the result carries NO UI metadata — the card rides
    the tool DECLARATION, not the result."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        # Seed one memory so the list has a real row (write on THIS loop).
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.remember_impl(
            live, "Barna ships only on a green CI", _SCOPE,
            area="process", tags=["ci", "discipline"],
        )

        async with Client(server) as client:
            result = await client.call_tool("list_memories", {"scope": _SCOPE})

        # 1. the DATA is the primary content — a JSON text block every client reads.
        text_blocks = [b for b in result.content if getattr(b, "text", None)]
        assert len(text_blocks) == 1, "expected one JSON (data) content block"
        payload = json.loads(text_blocks[0].text)
        assert payload["scope"] == _SCOPE
        assert any(
            "green CI" in (m.get("summary") or "") for m in payload["memories"]
        ), "the seeded memory is missing from the content data"

        # 2. structured_content mirrors it.
        data = result.structured_content
        assert data["scope"] == _SCOPE
        assert any("green CI" in (m.get("summary") or "") for m in data["memories"])

        # 3. no pre-spec UI residue in the result.
        meta = result.meta or {}
        assert "ui/resourceUri" not in meta
        assert "resourceUri" not in (meta.get("ui") or {})

        # 4. no secret leaked into the returned payload.
        lowered = text_blocks[0].text.lower()
        for forbidden in ("bearer", "authorization", "x-dna-tenant"):
            assert forbidden not in lowered, f"{forbidden!r} leaked into the result"

    asyncio.run(scenario())


# ── 3. the declaration carries the template pointer (SEP-1865) ─────────────


def test_memory_tool_declarations_point_the_template(dna_dir):
    """``tools/list`` shows ``list_memories`` AND ``recall`` pointing the
    ``ui://dna/memory-list`` template in their own declaration — the pointer a
    host follows to prefetch the card. Pointer removed → this dies."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            tools = {t.name: t for t in await client.list_tools()}

        for name in ("list_memories", "recall"):
            meta = tools[name].meta or {}
            ui = meta.get("ui") or {}
            assert ui.get("resourceUri") == "ui://dna/memory-list", (
                f"{name} does not declare the memory-card template pointer"
            )

    asyncio.run(scenario())


def test_non_memory_tools_do_not_point_the_template(dna_dir):
    """The pointer is deliberate, not a blanket: a non-memory tool (``remember``,
    a write) declares NO UI template."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            tools = {t.name: t for t in await client.list_tools()}
        meta = tools["remember"].meta or {}
        assert not (meta.get("ui") or {}).get("resourceUri")

    asyncio.run(scenario())


# ── 4. the template resource is served with the SEP-1865 profile ───────────


def test_memory_list_template_resource_is_served(dna_dir):
    """``resources/read`` of ``ui://dna/memory-list`` answers the static
    template with mimeType ``text/html;profile=mcp-app``. Registration
    removed → this dies."""
    from dna.emit.mcp_ui import memory_list_card_html
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            contents = await client.read_resource("ui://dna/memory-list")

        assert len(contents) == 1
        block = contents[0]
        assert block.mimeType == "text/html;profile=mcp-app"
        # The served template IS the SDK's static template — data-free, public.
        assert block.text == memory_list_card_html()
        lowered = block.text.lower()
        for forbidden in ("bearer ", "authorization:", "x-dna-tenant"):
            assert forbidden not in lowered, f"{forbidden!r} leaked into the template"

    asyncio.run(scenario())
