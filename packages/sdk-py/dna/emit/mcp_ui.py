"""DNA → **MCP Apps** memory-card surface (SEP-1865, standalone golden family).

A standalone UI-emit surface, alongside the AG-UI backend emitters and the
CopilotKit ``frontend.py`` console — like ``frontend.py`` it is NOT a
registered ``EmitterPort``: it carries no byte-equal ``build_prompt``
instruction and is governed by its own byte-stable golden renders. Everything
here is a pure function of its inputs, so every render is byte-golden.

``memory_list_card_html(memories)`` renders the DNA-branded memory card as a
self-contained HTML document (inline CSS, no external asset), consumed by the
AG-UI shared-state canvas: the emitted LangGraph copilot projects a memory
read-tool result into the ``memory_card_html`` state key and the DNA console's
Memória canvas renders it as an ``<iframe srcDoc>``. Data flows inside the
authenticated AG-UI session state, never a public URI.
"""
from __future__ import annotations

import html
from typing import Any

__all__ = [
    "UI_MEMORY_LIST_URI",
    "MCP_APP_MIME",
    "memory_list_card_html",
]

#: The ``ui://`` scheme resource id for the memory-list card. Stable — hosts
#: key their prefetch/render cache on it.
UI_MEMORY_LIST_URI = "ui://dna/memory-list"

#: The MCP Apps profile mimeType (SEP-1865) that marks a ``ui://`` resource as
#: a first-class MCP App, not a bare HTML blob.
MCP_APP_MIME = "text/html;profile=mcp-app"

# DNA brand tokens — dark ink ground, teal + amber accents. Kept inline (no
# external asset) because MCP hosts render the card in a sandboxed iframe that
# cannot reach the network.
_INK = "#12161c"
_INK_RAISED = "#1a2029"
_TEAL = "#2f8570"
_AMBER = "#e0a838"
_TEXT = "#e6eaef"
_MUTED = "#8b95a3"
_LINE = "#252c37"


def _esc(value: Any) -> str:
    """HTML-escape any scalar (``None`` → empty string)."""
    return html.escape("" if value is None else str(value), quote=True)


def _item_html(memory: dict[str, Any]) -> str:
    """One memory → one ``<li>`` card row. The main line is the summary (falling
    back to the slug ``name``); a meta row carries the timestamp + area + affect;
    tags render as chips. Everything is escaped — memory content is user data."""
    title = memory.get("summary") or memory.get("name") or "(untitled memory)"
    created = memory.get("created_at")
    area = memory.get("area")
    affect = memory.get("affect")
    tags = memory.get("tags") or []

    meta_bits: list[str] = []
    if created:
        meta_bits.append(f'<time class="dna-when">{_esc(created)}</time>')
    if area:
        meta_bits.append(f'<span class="dna-area">{_esc(area)}</span>')
    if affect:
        meta_bits.append(f'<span class="dna-affect">{_esc(affect)}</span>')
    meta_row = (
        f'<div class="dna-meta">{"".join(meta_bits)}</div>' if meta_bits else ""
    )

    chips = "".join(
        f'<span class="dna-tag">{_esc(t)}</span>' for t in tags if str(t).strip()
    )
    tag_row = f'<div class="dna-tags">{chips}</div>' if chips else ""

    return (
        '<li class="dna-item">'
        f'<div class="dna-summary">{_esc(title)}</div>'
        f"{meta_row}"
        f"{tag_row}"
        "</li>"
    )


def memory_list_card_html(
    memories: list[dict[str, Any]], *, scope: str | None = None
) -> str:
    """Render the memory-list card as a **self-contained** HTML document.

    Fully inline (CSS in a ``<style>`` block, no external assets) so it renders
    in a host's sandboxed iframe with no network. Each memory shows its summary,
    timestamp, area/affect, and tag chips; an empty list renders an honest empty
    state. Deterministic — the output is a pure function of ``memories`` (+
    ``scope``), so it is byte-golden. DNA-branded (dark ink ground, teal + amber
    accents)."""
    scope_badge = (
        f'<span class="dna-scope">{_esc(scope)}</span>' if scope else ""
    )
    count = len(memories)
    if memories:
        body = (
            '<ul class="dna-list">'
            + "".join(_item_html(m) for m in memories)
            + "</ul>"
        )
    else:
        body = (
            '<p class="dna-empty">No memories yet — anything you ask DNA to '
            "remember will appear here, and follow you across every client.</p>"
        )
    foot = (
        f'<footer class="dna-foot">{count} '
        f'{"memory" if count == 1 else "memories"} · '
        "your context, portable across every AI client</footer>"
    )
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>DNA · Memory</title><style>"
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
        "Helvetica,Arial,sans-serif;"
        f"background:{_INK};color:{_TEXT};padding:16px}}"
        f".dna-card{{max-width:640px;margin:0 auto;background:{_INK_RAISED};"
        f"border:1px solid {_LINE};border-radius:14px;overflow:hidden}}"
        ".dna-head{display:flex;align-items:center;gap:10px;padding:14px 18px;"
        f"border-bottom:1px solid {_LINE}}}"
        f".dna-mark{{font-weight:700;letter-spacing:.14em;color:{_TEAL}}}"
        ".dna-htitle{font-weight:600}"
        f".dna-scope{{margin-left:auto;font-size:12px;color:{_MUTED};"
        f"border:1px solid {_LINE};padding:2px 8px;border-radius:999px}}"
        ".dna-list{list-style:none}"
        f".dna-item{{padding:14px 18px;border-bottom:1px solid {_LINE}}}"
        ".dna-item:last-child{border-bottom:0}"
        ".dna-summary{font-weight:600;color:" + _TEXT + "}"
        ".dna-meta{display:flex;flex-wrap:wrap;gap:10px;margin-top:5px;"
        f"font-size:12px;color:{_MUTED}}}"
        f".dna-when{{color:{_AMBER}}}"
        ".dna-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}"
        f".dna-tag{{font-size:11px;color:{_TEAL};background:rgba(47,133,112,.12);"
        f"border:1px solid rgba(47,133,112,.35);padding:2px 8px;"
        "border-radius:999px}"
        f".dna-empty{{padding:22px 18px;color:{_MUTED}}}"
        f".dna-foot{{padding:12px 18px;font-size:11px;color:{_MUTED};"
        f"border-top:1px solid {_LINE}}}"
        "</style></head><body>"
        '<div class="dna-card">'
        '<div class="dna-head"><span class="dna-mark">DNA</span>'
        '<span class="dna-htitle">Memory</span>'
        f"{scope_badge}</div>"
        f"{body}{foot}"
        "</div></body></html>"
    )


