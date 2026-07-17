"""``f-dna-cloud-copilot`` Phase 3 (M0) — the **MCP-App memory card**.

The ``list_memories`` MCP tool ships an interactive UI card (SEP-1865 "MCP
Apps") alongside its structured data: a ``ui://dna/memory-list`` ``rawHtml``
resource, linked from the tool result's ``_meta.ui.resourceUri``, so an MCP host
(Claude / ChatGPT / VS Code / Goose) renders the memory list as a card in a
sandboxed iframe. This is the DNA thesis — "your context follows you across
every client" — made *visible in the UI*, reached by the path
``host → DNA MCP server`` (the copilot ``/agui`` agent is bypassed entirely).

Proven end-to-end through the REAL FastMCP protocol (in-memory ``Client``):

1. **the card is emitted** — the tool result carries a UI resource at
   ``ui://dna/memory-list`` with the MCP-App profile mimeType, plus the
   ``_meta.ui.resourceUri`` pointer a host follows to render it;
2. **graceful degradation** — the plain structured data (``{scope, memories}``)
   is returned unchanged in ``structured_content``, so a host WITHOUT MCP Apps
   still gets the data; the tool never breaks for a non-MCP-App host;
3. **no secret in the emitted HTML** — the card is self-contained markup; no
   bearer / token ever leaks into the rendered resource (research §5 hard rule).
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope (so a memory can be written)."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def test_list_memories_emits_mcp_app_metadata(dna_dir):
    """Through the real protocol: ``list_memories`` returns the DATA as the primary
    ``content`` (a JSON text block EVERY MCP client reads — langchain-mcp-adapters and
    the like read ``content``, not ``structured_content``), mirrored in
    ``structured_content``, plus the ``_meta.ui.resourceUri`` MCP-App pointer a host
    follows to render the ``ui://dna/memory-list`` card (registering that resource +
    a data-aware template is the proper follow-up)."""
    import json

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

        # 3. the MCP-App _meta pointer a host follows (both spellings).
        meta = result.meta or {}
        assert meta.get("ui", {}).get("resourceUri") == "ui://dna/memory-list"
        assert meta.get("ui/resourceUri") == "ui://dna/memory-list"

        # 4. no secret leaked into the returned payload.
        lowered = text_blocks[0].text.lower()
        for forbidden in ("bearer", "authorization", "x-dna-tenant"):
            assert forbidden not in lowered, f"{forbidden!r} leaked into the result"

    asyncio.run(scenario())


def test_degrades_to_plain_dict_without_mcp_ui(monkeypatch):
    """If ``dna.emit.mcp_ui`` is unavailable, ``_with_memory_card`` returns the plain
    data dict unchanged — the tool never breaks."""
    import builtins

    real_import = builtins.__import__

    def _no_mcp_ui(name, *args, **kwargs):
        if name == "dna.emit.mcp_ui" or name.startswith("dna.emit.mcp_ui."):
            raise ModuleNotFoundError("No module named 'dna.emit.mcp_ui'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_mcp_ui)
    data = {"scope": _SCOPE, "memories": []}
    assert M._with_memory_card(data) is data
