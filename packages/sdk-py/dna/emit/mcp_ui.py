"""DNA → **MCP Apps** memory-card surface (SEP-1865, standalone golden family).

A standalone UI-emit surface, alongside the AG-UI backend emitters and the
CopilotKit ``frontend.py`` console — like ``frontend.py`` it is NOT a
registered ``EmitterPort``: it carries no byte-equal ``build_prompt``
instruction and is governed by its own byte-stable golden renders. Everything
here is a pure function of its inputs, so every render is byte-golden.

Two renders live here, one per delivery channel of the memory card:

``memory_list_card_html()`` — the **static MCP Apps template** the runtime
face (``dna_cli._mcp_server``) registers at ``ui://dna/memory-list`` and
points from the ``list_memories``/``recall`` tool declarations. Self-contained
HTML + inline JS: the ``@modelcontextprotocol/ext-apps`` lib is vendored in
this package (``_vendor/ext-apps.iife.js``, license alongside) and embedded in
an inline ``<script>`` — no CDN, no external URL; the spec's CSP is
deny-by-default. The JS consumes the host push (``app.ontoolresult``) and
renders each tool result's ``structured_content``. The template is public and
cacheable by URI: zero tenant data, zero secret/token in the HTML — data
reaches the card only via the authenticated session's push, and only ever
lands in the DOM through ``textContent`` (escaped by construction).

``memory_canvas_card_html(memories)`` — the **data-populated card** for the
AG-UI shared-state canvas: the emitted LangGraph copilot projects a memory
read-tool result into the ``memory_card_html`` state key and the DNA console's
Memória canvas renders it as an ``<iframe srcDoc>``. Data flows inside the
authenticated AG-UI session state, never a public URI. Every value is
HTML-escaped — memory content is user data.
"""
from __future__ import annotations

import html
from functools import cache
from importlib import resources
from typing import Any

__all__ = [
    "UI_MEMORY_LIST_URI",
    "MCP_APP_MIME",
    "memory_list_card_html",
    "memory_canvas_card_html",
]

#: The ``ui://`` scheme resource id for the memory-list card template. Stable —
#: hosts key their prefetch/render cache on it.
UI_MEMORY_LIST_URI = "ui://dna/memory-list"

#: The MCP Apps profile mimeType (SEP-1865) the ``ui://dna/memory-list``
#: resource is served with — what marks it a first-class MCP App template, not
#: a bare HTML blob.
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

# Sentinels delimiting the vendored third-party lib inside the template — the
# §3 grep-guard and the no-external-URL test treat the region between them as
# the committed vendor asset (byte-equal), and everything outside as the
# surface DNA wrote.
_EXT_APPS_BEGIN = "/*! begin vendored @modelcontextprotocol/ext-apps */"
_EXT_APPS_END = "/*! end vendored @modelcontextprotocol/ext-apps */"


def _esc(value: Any) -> str:
    """HTML-escape any scalar (``None`` → empty string)."""
    return html.escape("" if value is None else str(value), quote=True)


# ── the static MCP Apps template (ui://dna/memory-list) ─────────────────────


@cache
def _ext_apps_js() -> str:
    """The vendored ``@modelcontextprotocol/ext-apps`` IIFE (exposes
    ``globalThis.DnaExtApps.App``), read from the packaged asset."""
    return (
        (resources.files("dna.emit") / "_vendor" / "ext-apps.iife.js")
        .read_text(encoding="utf-8")
        .strip("\n")
    )


# The shared brand stylesheet of the card (template + canvas render the same
# visual system; the template adds the states only the live card has).
_CARD_CSS = (
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
)

# The card app — everything DNA wrote in the template's inline JS. Data only
# ever enters the DOM via ``textContent`` (escaped by construction); missing
# fields render honestly empty, never invented. Read-only: no action wired.
_CARD_JS = """\
(function () {
  "use strict";
  var App = globalThis.DnaExtApps.App;
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null && text !== "") n.textContent = String(text);
    return n;
  }
  function itemsOf(data) {
    if (data && Array.isArray(data.memories)) return data.memories;
    if (data && Array.isArray(data.hits)) return data.hits;
    return [];
  }
  function dataOf(result) {
    if (result && typeof result.structuredContent === "object" && result.structuredContent) {
      return result.structuredContent;
    }
    var blocks = result && Array.isArray(result.content) ? result.content : [];
    for (var i = 0; i < blocks.length; i++) {
      var b = blocks[i];
      if (b && b.type === "text" && typeof b.text === "string") {
        try { return JSON.parse(b.text); } catch (e) { /* not JSON — keep looking */ }
      }
    }
    return null;
  }
  function render(data) {
    var body = document.getElementById("dna-body");
    var foot = document.getElementById("dna-foot");
    var badge = document.getElementById("dna-scope");
    body.textContent = "";
    var scope = data && typeof data.scope === "string" ? data.scope : "";
    badge.textContent = scope;
    badge.hidden = !scope;
    if (data === null) {
      body.appendChild(el("p", "dna-empty",
        "The card could not read this result — the tool's textual reply is the source of truth."));
      foot.textContent = "your context, portable across every AI client";
      return;
    }
    var items = itemsOf(data);
    if (!items.length) {
      body.appendChild(el("p", "dna-empty",
        "No memories yet — anything you ask DNA to remember will appear here, and follow you across every client."));
    } else {
      var list = el("ul", "dna-list");
      for (var i = 0; i < items.length; i++) {
        var m = items[i] && typeof items[i] === "object" ? items[i] : {};
        var li = el("li", "dna-item");
        li.appendChild(el("div", "dna-summary", m.summary || m.name || "(untitled memory)"));
        var meta = el("div", "dna-meta");
        if (m.created_at) meta.appendChild(el("time", "dna-when", m.created_at));
        if (m.area) meta.appendChild(el("span", "dna-area", m.area));
        if (m.affect) meta.appendChild(el("span", "dna-affect", m.affect));
        if (meta.childNodes.length) li.appendChild(meta);
        var tags = [];
        if (Array.isArray(m.tags)) {
          for (var j = 0; j < m.tags.length; j++) {
            if (m.tags[j] !== null && m.tags[j] !== undefined && String(m.tags[j]).trim()) {
              tags.push(m.tags[j]);
            }
          }
        }
        if (tags.length) {
          var row = el("div", "dna-tags");
          for (var t = 0; t < tags.length; t++) row.appendChild(el("span", "dna-tag", tags[t]));
          li.appendChild(row);
        }
        list.appendChild(li);
      }
      body.appendChild(list);
    }
    var n = items.length;
    foot.textContent = n + " " + (n === 1 ? "memory" : "memories") +
      " \\u00b7 your context, portable across every AI client";
  }
  var app = new App({ name: "dna-memory-card", version: "1" });
  app.ontoolresult = function (result) { render(dataOf(result)); };
  app.connect();
})();
"""


@cache
def memory_list_card_html() -> str:
    """The **static MCP Apps template** for the memory card — zero arguments,
    same bytes every call (byte-golden).

    Self-contained HTML: brand CSS inline, the vendored
    ``@modelcontextprotocol/ext-apps`` lib embedded between sentinel comments,
    and the card app JS that consumes ``app.ontoolresult`` → renders the
    pushed ``structured_content`` (``memories`` from ``list_memories``,
    ``hits`` from ``recall``). No data is baked in — before the host pushes,
    the card says so honestly; an empty push renders the honest empty state.
    Read-only: the card exposes no action."""
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>DNA · Memory</title><style>"
        + _CARD_CSS
        + "</style></head><body>"
        '<div class="dna-card">'
        '<div class="dna-head"><span class="dna-mark">DNA</span>'
        '<span class="dna-htitle">Memory</span>'
        '<span class="dna-scope" id="dna-scope" hidden></span></div>'
        '<div id="dna-body"><p class="dna-empty">Waiting for the memory data '
        "from the tool result…</p></div>"
        '<footer class="dna-foot" id="dna-foot">your context, portable across '
        "every AI client</footer>"
        "</div>"
        "<script>\n"
        + _EXT_APPS_BEGIN
        + "\n"
        + _ext_apps_js()
        + "\n"
        + _EXT_APPS_END
        + "\n</script>"
        "<script>\n" + _CARD_JS + "</script>"
        "</body></html>"
    )


# ── the canvas card (AG-UI shared state → console Memória canvas) ───────────


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


def memory_canvas_card_html(
    memories: list[dict[str, Any]], *, scope: str | None = None
) -> str:
    """Render the memory card **populated with data** as a self-contained HTML
    document — the AG-UI shared-state canvas render.

    The emitted LangGraph copilot projects a memory read-tool result into the
    ``memory_card_html`` state key with this function, and the DNA console's
    Memória canvas renders it as an ``<iframe srcDoc>`` — data flows inside the
    authenticated AG-UI session state, never a public URI. Fully inline (CSS in
    a ``<style>`` block, no external assets). Each memory shows its summary,
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
        + _CARD_CSS
        + "</style></head><body>"
        '<div class="dna-card">'
        '<div class="dna-head"><span class="dna-mark">DNA</span>'
        '<span class="dna-htitle">Memory</span>'
        f"{scope_badge}</div>"
        f"{body}{foot}"
        "</div></body></html>"
    )
