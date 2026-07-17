"""``dna.emit.mcp_ui`` — the MCP-UI / MCP Apps card surface (Phase 4).

The third UI-emit surface (alongside the AG-UI backend emitters and the
``frontend.py`` console): a self-contained ``rawHtml`` card projected from a
tool's clean structured JSON, shaped for ``create_ui_resource``. Like the
backend emitters' ``rawHtml`` artifacts it is **byte-golden** — the card is a
pure function of its input, so it is a candidate for a byte-equal ``mcp_ui.ts``
twin (a tracked follow-up).

Proven here:
1. the ``create_ui_resource``-shaped payload has the right ``ui://`` uri +
   ``rawHtml`` content + ``text`` encoding;
2. the card HTML matches a frozen golden (byte-equal), for a populated list and
   for the empty state;
3. memory content is HTML-escaped (user data never breaks the markup / injects);
4. the surface map labels AG-UI covered, MCP-UI available, A2UI deferred.
"""
from __future__ import annotations

import pathlib

from dna.emit.mcp_ui import (
    MCP_APP_MIME,
    UI_MEMORY_LIST_URI,
    available_emit_surfaces,
    memory_list_card_html,
    memory_list_ui_resource,
)

# The deterministic fixture the goldens were rendered from — newest-first, as
# ``list_memories_impl`` returns. The last item omits summary/area/affect/tags to
# exercise the fallback (summary → slug name) and the meta/tag-row suppression.
_MEMORIES = [
    {
        "name": "prefers-tea",
        "summary": "Barna prefers tea over coffee in the afternoon",
        "area": "preferences",
        "tags": ["drink", "routine"],
        "affect": "triumph",
        "created_at": "2026-07-10T14:20:00Z",
    },
    {
        "name": "ships-on-green",
        "summary": "Ship only on a green CI; the pipeline is the gate",
        "area": "process",
        "tags": ["ci", "discipline"],
        "affect": "resolve",
        "created_at": "2026-07-08T09:00:00Z",
    },
    {
        "name": "no-summary-item",
        "summary": None,
        "area": None,
        "tags": [],
        "affect": None,
        "created_at": None,
    },
]


def _golden(name: str) -> str:
    return (
        pathlib.Path(__file__).parent / "goldens" / "mcp_ui" / name
    ).read_text(encoding="utf-8")


def test_ui_resource_payload_shape():
    """The payload is exactly the ``create_ui_resource`` options dict: a ``ui://``
    uri, a ``rawHtml`` content payload, ``text`` encoding."""
    payload = memory_list_ui_resource(_MEMORIES, scope="concierge")
    assert payload["uri"] == UI_MEMORY_LIST_URI == "ui://dna/memory-list"
    assert payload["encoding"] == "text"
    assert payload["content"]["type"] == "rawHtml"
    # The card HTML is carried inline (self-contained — no external asset).
    assert payload["content"]["htmlString"].startswith("<!doctype html>")


def test_card_html_matches_golden():
    """The populated card is byte-equal to the frozen golden."""
    assert memory_list_card_html(_MEMORIES, scope="concierge") == _golden(
        "memory_list_card.html"
    )


def test_empty_card_matches_golden():
    """An empty memory list renders the honest empty-state golden."""
    assert memory_list_card_html([], scope=None) == _golden("memory_list_empty.html")


def test_card_is_self_contained_and_branded():
    """No external asset (hosts sandbox the iframe) and DNA-branded ink/teal/amber."""
    html = memory_list_card_html(_MEMORIES, scope="concierge")
    assert "http://" not in html and "https://" not in html  # no external fetch.
    assert "src=" not in html  # no external image/script.
    assert "#12161c" in html and "#2f8570" in html and "#e0a838" in html  # brand.


def test_memory_content_is_escaped():
    """User memory content is HTML-escaped — it cannot break markup or inject."""
    hostile = [
        {"summary": "<script>alert(1)</script>", "tags": ["<b>x</b>"], "created_at": "t"}
    ]
    html = memory_list_card_html(hostile, scope="s&s")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "s&amp;s" in html  # the scope badge is escaped too.


def test_surface_map():
    """AG-UI is already covered; MCP-UI is this surface; A2UI is deferred."""
    surfaces = available_emit_surfaces()
    assert surfaces == {
        "ag-ui": "covered",
        "mcp-ui": "available",
        "a2ui": "deferred",
    }


def test_mcp_app_profile_mime_constant():
    """The SEP-1865 profile mimeType is exposed for the runtime face to stamp."""
    assert MCP_APP_MIME == "text/html;profile=mcp-app"
