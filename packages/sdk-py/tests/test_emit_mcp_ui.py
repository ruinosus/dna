"""``dna.emit.mcp_ui`` — the MCP Apps memory-card surface.

A standalone UI-emit surface (alongside the AG-UI backend emitters and the
``frontend.py`` console): the DNA-branded memory card, byte-golden — every
render is a pure function of its input.

Proven here:
1. the card HTML matches a frozen golden (byte-equal), for a populated list and
   for the empty state;
2. memory content is HTML-escaped (user data never breaks the markup / injects);
3. the card is self-contained (no external asset — hosts sandbox the iframe)
   and DNA-branded;
4. the SEP-1865 constants (``ui://`` id + profile mimeType) hold.
"""
from __future__ import annotations

import pathlib

from dna.emit.mcp_ui import (
    MCP_APP_MIME,
    UI_MEMORY_LIST_URI,
    memory_list_card_html,
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


def test_mcp_app_constants():
    """The SEP-1865 resource id + profile mimeType the runtime face serves."""
    assert UI_MEMORY_LIST_URI == "ui://dna/memory-list"
    assert MCP_APP_MIME == "text/html;profile=mcp-app"
