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
pytest.importorskip("mcp_ui_server", reason="MCP Apps need the optional 'mcp-ui-server' (part of the 'mcp' extra)")

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


def test_list_memories_emits_mcp_app_card(dna_dir):
    """Through the real protocol: ``list_memories`` returns the data AND a
    ``ui://dna/memory-list`` UI resource + the ``_meta.ui.resourceUri`` pointer."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        # Seed one memory so the card has a real row (write on THIS loop).
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.remember_impl(
            live, "Barna ships only on a green CI", _SCOPE,
            area="process", tags=["ci", "discipline"],
        )

        async with Client(server) as client:
            result = await client.call_tool("list_memories", {"scope": _SCOPE})

        # 2. graceful degradation — the plain data is intact.
        data = result.structured_content
        assert data["scope"] == _SCOPE
        assert any(
            "green CI" in (m.get("summary") or "") for m in data["memories"]
        ), "the seeded memory is missing from the structured data"

        # 1. the card is emitted — a UI resource block at the ui:// uri.
        resources = [b for b in result.content if getattr(b, "resource", None)]
        assert len(resources) == 1, "expected exactly one UI resource content block"
        res = resources[0].resource
        assert str(res.uri) == "ui://dna/memory-list"
        assert res.mimeType == "text/html;profile=mcp-app"
        assert res.text.startswith("<!doctype html>")  # self-contained rawHtml.
        assert "green CI" in res.text  # the memory rendered into the card.

        # 1. the _meta pointer a host follows (both spellings).
        meta = result.meta or {}
        assert meta.get("ui", {}).get("resourceUri") == "ui://dna/memory-list"
        assert meta.get("ui/resourceUri") == "ui://dna/memory-list"

        # 3. no secret in the emitted HTML.
        lowered = res.text.lower()
        for forbidden in ("bearer", "authorization", "x-dna-tenant", "token"):
            assert forbidden not in lowered, f"{forbidden!r} leaked into the card HTML"

    asyncio.run(scenario())


def test_degrades_to_plain_dict_without_mcp_ui(monkeypatch):
    """If ``mcp-ui-server`` is absent, ``_with_memory_card`` returns the plain
    data dict unchanged — the tool never breaks on an install without the extra."""
    import builtins

    real_import = builtins.__import__

    def _no_mcp_ui(name, *args, **kwargs):
        if name == "mcp_ui_server" or name.startswith("mcp_ui_server."):
            raise ModuleNotFoundError("No module named 'mcp_ui_server'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_mcp_ui)
    data = {"scope": _SCOPE, "memories": []}
    assert M._with_memory_card(data) is data
