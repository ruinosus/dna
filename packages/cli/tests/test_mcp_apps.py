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
   template carry no bearer / token / tenant header;
6. **the extension negotiation** — the server DECLARES the MCP Apps extension
   with the mimeType it actually serves, and it CHECKS the client's own
   declaration per call before advertising a UI-enabled tool. The check is
   tri-state and honest: a client that declared support keeps the pointer, a
   client that spoke and did NOT declare loses it, and a runtime that tells us
   nothing leaves the (inert) pointer alone rather than guessing. In every
   case the textual ``content`` is byte-identical — the UI declaration can
   never degrade the text answer.
"""
from __future__ import annotations

import asyncio
import json
import logging
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


def _declare_ui_extension(monkeypatch):
    """Make the in-memory client announce the MCP Apps extension.

    The MCP client SDK hard-codes its ``ClientCapabilities`` at ``initialize``
    with no seam for an extension, so the test injects the ``extensions`` extra
    the same way a UI-capable host sends it on the wire."""
    import mcp.types as mt

    original = mt.ClientCapabilities

    def with_ui(**kwargs):
        return original(
            **kwargs,
            extensions={M.UI_EXTENSION_ID: {"mimeTypes": [M.MCP_APP_MIME]}},
        )

    monkeypatch.setattr(mt, "ClientCapabilities", with_ui)


def test_memory_tool_declarations_point_the_template(dna_dir, monkeypatch):
    """``tools/list`` shows ``list_memories`` AND ``recall`` pointing the
    ``ui://dna/memory-list`` template in their own declaration — the pointer a
    host follows to prefetch the card. Pointer removed → this dies.

    The client here DECLARES the MCP Apps extension, which is what earns it the
    pointer (SEP-1865: check the client before advertising a UI-enabled tool)."""
    from fastmcp import Client

    _declare_ui_extension(monkeypatch)

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


def test_non_memory_tools_do_not_point_the_template(dna_dir, monkeypatch):
    """The pointer is deliberate, not a blanket: a non-memory tool (``remember``,
    a write) declares NO UI template even to a UI-capable client."""
    from fastmcp import Client

    _declare_ui_extension(monkeypatch)

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


# ── 5. the extension negotiation (SEP-1865, final) ─────────────────────────


def test_server_declares_the_ui_extension_with_the_mimetype_it_serves():
    """The server's own capabilities announce MCP Apps support in the
    ``extensions`` map, carrying the profile mimeType it actually serves.

    FastMCP announces the extension id with an EMPTY config; the final spec's
    shape is ``{"mimeTypes": ["text/html;profile=mcp-app"]}``, and a host that
    filters on the advertised mimeTypes would never prefetch our card without
    it. Drop the enrichment → this dies."""
    from mcp.server.lowlevel.server import NotificationOptions

    server = M.build_server(base_dir=str(_BASE))
    caps = server._mcp_server.get_capabilities(NotificationOptions(), {})
    extensions = (caps.model_extra or {}).get("extensions") or {}

    assert M.UI_EXTENSION_ID in extensions, "the MCP Apps extension is not declared"
    assert extensions[M.UI_EXTENSION_ID] == {"mimeTypes": [M.MCP_APP_MIME]}


def test_client_ui_extension_reads_the_per_request_meta_first():
    """The 2026-07-28 core removed ``initialize`` and sessions: protocol
    version, client info and capabilities travel in ``_meta`` on EVERY request.
    The resolver reads that first, so a session-less client is still heard —
    and it wins over a stale handshake."""
    meta = {"capabilities": {"extensions": {M.UI_EXTENSION_ID: {}}}}
    assert M.client_ui_extension(request_meta=meta, session_capabilities=None) is True

    # Same shape, extension absent → a definite NO, not a shrug.
    meta_without = {"capabilities": {"extensions": {"io.example/other": {}}}}
    assert M.client_ui_extension(
        request_meta=meta_without, session_capabilities=None) is False

    # The per-request map is authoritative over the handshake.
    assert M.client_ui_extension(
        request_meta=meta_without,
        session_capabilities={"extensions": {M.UI_EXTENSION_ID: {}}},
    ) is False


def test_client_ui_extension_falls_back_to_the_initialize_handshake():
    """On the protocol the installed runtime still speaks (2025-11-25) the
    capability map arrives once, at ``initialize``. With no per-request ``_meta``
    the resolver reads the handshake."""
    assert M.client_ui_extension(
        request_meta=None,
        session_capabilities={"extensions": {M.UI_EXTENSION_ID: {}}},
    ) is True
    assert M.client_ui_extension(
        request_meta=None, session_capabilities={"roots": {}}) is False


def test_client_ui_extension_says_unknown_rather_than_guessing():
    """The honest third answer. When neither channel carries a capability map
    the resolver returns ``None`` — it does NOT answer "yes", which would be a
    fake check that merely looks conformant, and it does not answer "no", which
    would silently blind a capable host."""
    assert M.client_ui_extension(request_meta=None, session_capabilities=None) is None
    assert M.client_ui_extension(
        request_meta={"progressToken": 1}, session_capabilities=None) is None


def test_a_client_that_declares_nothing_is_not_offered_the_ui_pointer(dna_dir):
    """The SEP-1865 SHOULD, applied per call: a client that completes the
    handshake WITHOUT the MCP Apps extension is a client that cannot render,
    so ``tools/list`` does not advertise a UI-enabled tool to it.

    (The stock MCP client SDK sends no ``extensions`` — this is the real,
    unpatched wire behaviour of every host that has not adopted the extension.)
    Remove the check → this dies."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            tools = {t.name: t for t in await client.list_tools()}

        for name in ("list_memories", "recall"):
            meta = tools[name].meta or {}
            assert not (meta.get("ui") or {}).get("resourceUri"), (
                f"{name} advertised its UI template to a client that cannot render it"
            )
            # The tool itself is still there — we withhold the CARD, never the tool.
            assert tools[name].description

    asyncio.run(scenario())


def test_withholding_the_pointer_never_degrades_the_text_answer(dna_dir, monkeypatch):
    """The non-negotiable: ``content`` is REQUIRED and ``structuredContent`` is
    OPTIONAL, so the capability check may only ever touch the DECLARATION. The
    same call to a UI-blind client returns bytes identical to the frozen
    pre-feature baseline, with the data mirrored in ``structured_content``."""
    for tool, args, fixture in (
        ("list_memories", {"scope": _SCOPE}, "list_memories.content.txt"),
        ("recall", {"query": "tea", "scope": _SCOPE}, "recall.content.txt"),
    ):
        result = _call_with_pinned_data(dna_dir, monkeypatch, tool, args)
        text_blocks = [b for b in result.content if getattr(b, "text", None)]
        assert len(text_blocks) == 1, (
            "the UI declaration replaced the content with a placeholder — "
            "the house rule is merge, never replace"
        )
        assert text_blocks[0].text.encode("utf-8") == (_FIXTURES / fixture).read_bytes()
        assert json.loads(text_blocks[0].text) == result.structured_content


def test_the_template_is_served_to_any_client(dna_dir):
    """The capability check gates the DECLARATION only. The ``ui://`` resource
    stays readable by anyone who asks — it is public, data-free and cacheable,
    and gating it would break a host that prefetches before it declares."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:  # declares no extension
            contents = await client.read_resource("ui://dna/memory-list")
        assert contents and contents[0].mimeType == M.MCP_APP_MIME

    asyncio.run(scenario())


def test_an_unknown_client_keeps_the_inert_pointer(dna_dir):
    """The stated gap, pinned as behaviour. When the runtime surfaces no
    capability map at all the middleware leaves the pointer alone: it is inert
    metadata a non-supporting host ignores, and stripping on a shrug would
    break every host whose declaration this runtime cannot yet surface.

    Flip the middleware to strip on ``None`` and this dies."""
    middleware = M._ui_capability_middleware()

    class _Tool:
        meta = {"ui": {"resourceUri": "ui://dna/memory-list"}}

    class _Context:
        fastmcp_context = None  # no session, no request — nothing to read.

    async def call_next(_context):
        return [_Tool()]

    tools = asyncio.run(middleware.on_list_tools(_Context(), call_next))
    assert tools[0].meta == {"ui": {"resourceUri": "ui://dna/memory-list"}}


def _list_tools_under(declared, caplog, monkeypatch):
    """Drive the middleware once with a client whose declaration is ``declared``,
    returning the log lines it emitted."""
    middleware = M._ui_capability_middleware()

    class _Fake:
        """Enough of a FastMCP tool for the middleware: a ``meta`` to read and
        the ``model_copy`` the strip path uses (it copies, never mutates)."""

        def __init__(self, name, meta):
            self.name, self.meta = name, meta

        def model_copy(self, *, update):
            return _Fake(self.name, update.get("meta"))

    def _Tool():
        return _Fake(
            "approve_kind",
            {"ui": {"resourceUri": "ui://dna/prefab", "visibility": ["app"]}},
        )

    def _Plain():
        return _Fake("recall", {"ui": {"resourceUri": "ui://dna/memory-list"}})

    class _Context:
        fastmcp_context = object()

    async def call_next(_context):
        return [_Tool(), _Plain()]

    with caplog.at_level(logging.INFO, logger=M.logger.name):
        monkeypatch.setattr(
            M, "client_ui_extension_from_context", lambda _ctx: declared
        )
        asyncio.run(middleware.on_list_tools(_Context(), call_next))
        asyncio.run(middleware.on_list_tools(_Context(), call_next))
    return [r.getMessage() for r in caplog.records], middleware


@pytest.mark.parametrize("declared", [True, False, None])
def test_the_negotiation_reading_is_logged_not_discarded(
    declared, caplog, monkeypatch
):
    """The tri-state decides the filter and must also be READABLE.

    Without this line the answer to "did the host declare MCP Apps?" is
    computed and thrown away, and from outside the server all three readings
    look identical — no card rendered. Delete the ``_report`` call and this
    dies."""
    lines, _ = _list_tools_under(declared, caplog, monkeypatch)
    said = [ln for ln in lines if "MCP Apps" in ln]
    assert len(said) == 1, (
        f"expected exactly one line for declared={declared!r}, got {said}"
    )


def test_each_reading_is_told_apart_from_the_other_two(caplog, monkeypatch):
    """A line that says the same thing for True, False and None would satisfy
    "something was logged" while answering nothing — the whole point is that a
    reader can tell WHICH of the three happened, and the tool count that
    implies. Collapse the three branches into one message and this dies."""
    said = {}
    for declared in (True, False, None):
        caplog.clear()
        lines, _ = _list_tools_under(declared, caplog, monkeypatch)
        said[declared] = next(ln for ln in lines if "MCP Apps" in ln)

    assert len(set(said.values())) == 3, f"readings not distinguishable: {said}"
    assert "DECLARED" in said[True]
    assert "WITHOUT" in said[False]
    assert "NOTHING readable" in said[None]
    # The count is the field a reader compares against the client's own list:
    # 2 tools offered when we advertise, 1 when we withhold the app-only one.
    assert " 2 tools" in said[True] and "1 app-only" in said[True]
    assert " 1 tools" in said[False]
    assert " 2 tools" in said[None]


def test_a_chatty_client_does_not_flood_the_log(caplog, monkeypatch):
    """``tools/list`` is called on every reconnect. The reading is a fact about
    the client, not an event — report it once per distinct value. Drop the
    dedup and this dies (the helper lists twice)."""
    lines, middleware = _list_tools_under(None, caplog, monkeypatch)
    assert len([ln for ln in lines if "MCP Apps" in ln]) == 1
    assert middleware._reported == {None}


def test_withholding_for_one_client_does_not_poison_the_next(dna_dir, monkeypatch):
    """The tool objects live in the server's registry and are shared by every
    connected client. Withholding the card from a UI-blind client must copy,
    never mutate — otherwise the FIRST such client permanently strips the
    pointer for everyone after it. Strip in place and this dies."""
    from fastmcp import Client

    server = M.build_server(base_dir=str(dna_dir))

    async def list_tools():
        async with Client(server) as client:
            return {t.name: t for t in await client.list_tools()}

    blind = asyncio.run(list_tools())
    assert not ((blind["list_memories"].meta or {}).get("ui") or {}).get("resourceUri")

    _declare_ui_extension(monkeypatch)
    capable = asyncio.run(list_tools())
    ui = (capable["list_memories"].meta or {}).get("ui") or {}
    assert ui.get("resourceUri") == "ui://dna/memory-list", (
        "the UI-blind listing stripped the shared registry, not its own copy"
    )
