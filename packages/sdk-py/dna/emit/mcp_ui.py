"""DNA → **MCP-UI / MCP Apps** card surface (standalone golden family).

The third UI-emit surface, alongside the AG-UI backend emitters and the
CopilotKit ``frontend.py`` console. Where the backend emitters materialize a
servable AG-UI *backend* and ``frontend.py`` materializes the *console* that
drives it, this module materializes a **UI resource at the tool** — an
``mcp-ui`` card (SEP-1865 "MCP Apps", ratified 2026-01-26) that any MCP host
(Claude, ChatGPT, VS Code, Goose) renders in a sandboxed iframe.

The mechanism (verified against ``mcp-ui-server`` 1.0.0):

    a tool returns a UI resource at ``ui://…`` (``rawHtml`` / ``externalUrl`` /
    ``remoteDom``) linked from the tool result's ``_meta.ui.resourceUri``; the
    host prefetches + renders it in a sandboxed iframe. Same resource renders
    across hosts (plain ``rawHtml`` is the most portable) — DNA's "your context
    follows you across every client" thesis made *visible in the UI*.

This module produces the **``create_ui_resource``-shaped options dict** (the
neutral artifact), NOT a live ``UIResource`` object — so the SDK base carries no
dependency on the optional ``mcp-ui-server`` package. The MCP runtime face
(``dna_cli._mcp_server``, which owns the ``[mcp]`` extra) turns the options into
a real resource via ``create_ui_resource(...)`` and attaches the ``_meta``
pointer. Keeping the payload here (pure, language-neutral) makes it byte-golden
and — like the ``rawHtml`` backend emitters — a candidate for a byte-equal
Py↔TS twin (``mcp_ui.ts``, a follow-up; see "Parity" below).

**Standalone surface, NOT a registered ``EmitterPort``.** Exactly like
``frontend.py``: a card carries no byte-equal ``build_prompt`` instruction and
is outside the ``build_prompt`` contract. It is a surface a consumer calls
alongside the backend emit / at the tool, governed by its own byte-stable
golden render — not by the emitter registry.

**The three UI-emit surfaces (Phase 4 "declare once, emit everywhere"):**

    AG-UI    the agent as a frontend stream — ALREADY COVERED. DNA emits
             AG-UI-native backends (agno / agent_framework / langgraph / vertex)
             and serves the copilot over ``/agui``; the portal consumes it via
             ``HttpAgent`` + ``CopilotRuntime``. Phase 4's AG-UI work is
             recognition + this label, not new construction.
    MCP-UI   THIS module — a UI resource at the tool (``rawHtml`` today,
             ``externalUrl``/portal-route next). The first real emit-target build.
    A2UI     UI as declarative JSON (``surfaceUpdate``/``dataModelUpdate``/
             ``beginRendering``) — DEFERRED to A2UI v1.0 (it is v0.9 with a v1.0
             candidate in flight; adopting the wire now risks churn). The
             preparation that de-risks it costs nothing and is already honoured
             here: every card is projected from **clean structured JSON** (the
             ``memories`` list), so a card becomes an A2UI surface by *mapping*,
             not rewriting. Build ``dna/emit/a2ui.py`` when A2UI ships v1.0.

**Parity.** The payload this module emits is language-neutral (a plain dict of
HTML + strings), so a ``mcp_ui.ts`` twin can render a byte-identical payload and
be diffed against this one (like the ``rawHtml`` backend emitters). That twin is
a tracked follow-up — this module lands the Python surface + its golden first,
per the research's "extract emitters once the card shape is real" discipline.
"""
from __future__ import annotations

import html
from typing import Any

__all__ = [
    "UI_MEMORY_LIST_URI",
    "MCP_APP_MIME",
    "memory_list_card_html",
    "memory_list_ui_resource",
    "available_emit_surfaces",
]

#: The ``ui://`` scheme resource id for the memory-list card. Stable — hosts key
#: their prefetch/render cache on it.
UI_MEMORY_LIST_URI = "ui://dna/memory-list"

#: The MCP Apps profile mimeType (SEP-1865). ``mcp-ui-server`` emits the base
#: ``text/html``; the runtime face stamps this profile so the resource is a
#: first-class MCP-App, not a bare HTML blob.
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


def memory_list_ui_resource(
    memories: list[dict[str, Any]],
    *,
    scope: str | None = None,
    uri: str = UI_MEMORY_LIST_URI,
) -> dict[str, Any]:
    """The ``create_ui_resource``-shaped options for the memory-list card.

    Returns the neutral options dict — ``{uri, content:{type:"rawHtml",
    htmlString}, encoding:"text"}`` — that ``mcp_ui_server.create_ui_resource``
    consumes. Kept as a plain dict (no ``mcp-ui-server`` import) so the SDK base
    stays dependency-free and the payload is byte-golden."""
    return {
        "uri": uri,
        "content": {
            "type": "rawHtml",
            "htmlString": memory_list_card_html(memories, scope=scope),
        },
        "encoding": "text",
    }


def available_emit_surfaces() -> dict[str, str]:
    """The UI-emit surfaces and their status (Phase 4 map).

    ``ag-ui`` is already covered by the backend emitters; ``mcp-ui`` is this
    module; ``a2ui`` is deferred to A2UI v1.0 (prepared for via clean JSON)."""
    return {
        "ag-ui": "covered",  # backend emitters + /agui — recognition, not new build.
        "mcp-ui": "available",  # this module (rawHtml card).
        "a2ui": "deferred",  # gated on external A2UI v1.0.
    }
