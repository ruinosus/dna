"""``dna.emit.mcp_ui`` — the MCP Apps memory-card surface (SEP-1865).

One byte-golden render — the memory card's single delivery channel:

``memory_list_card_html()`` — the STATIC template registered at
``ui://dna/memory-list`` and pointed from the ``list_memories``/``recall``
tool declarations. Self-contained (the ``@modelcontextprotocol/ext-apps``
lib vendored + embedded inline — no CDN, no external URL), data-free
(the host pushes each tool result's ``structured_content`` into it via
``ontoolresult``), public and cacheable by URI.

Proven here, with the design's mutation discipline:
1. the render is byte-equal to the frozen golden;
2. the template contains NO memory data (data baked back in → dies) and NO
   external URL (a CDN planted → dies) — outside the delimited vendored-lib
   region it contains no ``http(s)://`` at all, and the vendored region is
   byte-equal to the committed vendor asset;
3. the template wires the MCP Apps data path: ``ontoolresult`` →
   ``structuredContent``, with the honest empty state;
4. the §3 grep-guard: ``TODO`` / ``deferred`` / ``follow-up`` / ``coming
   soon`` in ``mcp_ui.py`` or in the delivered template surface breaks the
   test (a TODO planted → dies);
5. the module's public surface is the template and ONLY the template — the
   retired shared-state canvas render stays retired (re-add it → dies).
"""
from __future__ import annotations

import inspect
import pathlib
import re

from dna.emit import mcp_ui as mcp_ui_module
from dna.emit.mcp_ui import (
    MCP_APP_MIME,
    UI_MEMORY_LIST_URI,
    _EXT_APPS_BEGIN,
    _EXT_APPS_END,
    memory_list_card_html,
)

_GOLDENS = pathlib.Path(__file__).parent / "goldens" / "mcp_ui"
_VENDOR = (
    pathlib.Path(__file__).parents[1] / "dna" / "emit" / "_vendor" / "ext-apps.iife.js"
)


def _golden(name: str) -> str:
    return (_GOLDENS / name).read_text(encoding="utf-8")


def _template_without_vendor(template: str) -> str:
    """The delivered template surface WE wrote — the vendored third-party lib
    region (delimited by the sentinels) stripped out."""
    begin = template.index(_EXT_APPS_BEGIN)
    end = template.index(_EXT_APPS_END) + len(_EXT_APPS_END)
    return template[:begin] + template[end:]


# ── the static MCP Apps template ───────────────────────────────────────────


def test_template_matches_golden():
    """The static template is byte-equal to the frozen golden."""
    assert memory_list_card_html() == _golden("memory_list_template.html")


def test_template_is_static_and_data_free():
    """The template is a ZERO-ARGUMENT pure render — no data can be baked in —
    and carries none of the fixture's memory content (data baked back → dies)."""
    assert not inspect.signature(memory_list_card_html).parameters
    template = memory_list_card_html()
    assert template == memory_list_card_html()  # pure — same bytes every call.
    for leaked in (
        "prefers-tea",
        "Barna prefers tea",
        "ships-on-green",
        "concierge",
    ):
        assert leaked not in template, f"memory data {leaked!r} baked into the template"


def test_template_is_self_contained_no_external_url():
    """CSP is deny-by-default: nothing in the template reaches the network.
    No script/style/img/font reference, no CDN (planted → dies); outside the
    delimited vendored region there is no ``http(s)://`` at all; the vendored
    region is byte-equal to the committed vendor asset (no swap for a CDN)."""
    template = memory_list_card_html()
    lowered = template.lower()
    for fetchable in ("<script src", "<link", "src=", "href=", "@import", "url(http"):
        assert fetchable not in lowered, f"external reference {fetchable!r} in template"

    ours = _template_without_vendor(template)
    assert "http://" not in ours and "https://" not in ours

    begin = template.index(_EXT_APPS_BEGIN)
    end = template.index(_EXT_APPS_END)
    vendored = template[begin + len(_EXT_APPS_BEGIN):end].strip("\n")
    assert vendored == _VENDOR.read_text(encoding="utf-8").strip("\n")


def test_template_wires_the_mcp_apps_data_path():
    """The inline JS consumes the host push: ``ontoolresult`` →
    ``structuredContent`` → render; the vendored lib's ``App`` is what
    connects; the honest empty state is rendered from the pushed data."""
    template = memory_list_card_html()
    ours = _template_without_vendor(template)
    assert "ontoolresult" in ours
    assert "structuredContent" in ours
    assert "DnaExtApps" in ours
    assert "No memories yet" in ours  # the honest empty state, host-pushed.
    # Data goes into the DOM via textContent only — never markup injection.
    assert "textContent" in ours
    assert ".innerHTML" not in ours


def test_template_constants():
    """The SEP-1865 resource id + profile mimeType the runtime face serves."""
    assert UI_MEMORY_LIST_URI == "ui://dna/memory-list"
    assert MCP_APP_MIME == "text/html;profile=mcp-app"


# ── §3 grep-guard: the delivered surface carries no future-work mention ─────


def test_grep_guard_rule_3():
    """`TODO` / `deferred` / `follow-up` / `coming soon` in ``mcp_ui.py`` or in
    the delivered template surface breaks the build (a planted TODO → dies).
    The delimited vendored third-party region is exempt (its internals name a
    promise-deferred pattern); everything DNA wrote is guarded."""
    banned = re.compile(r"todo|deferred|follow-up|coming soon", re.IGNORECASE)

    source = pathlib.Path(inspect.getsourcefile(mcp_ui_module)).read_text(
        encoding="utf-8"
    )
    hit = banned.search(source)
    assert hit is None, f"rule-3 banned token {hit.group(0)!r} in mcp_ui.py"

    ours = _template_without_vendor(memory_list_card_html())
    hit = banned.search(ours)
    assert hit is None, f"rule-3 banned token {hit.group(0)!r} in the template"


# ── the module's public surface is the MCP Apps template, and ONLY that ─────


def test_module_exposes_only_the_mcp_apps_template_surface():
    """``mcp_ui`` renders the ``ui://dna/memory-list`` template and nothing else.

    A second, data-populated render used to live here for a shared-state canvas
    that no console ever consumed, and it cost a full HTML render on EVERY
    memory read-tool call. It is gone; this guard keeps it gone (re-add it and
    this dies). ``__all__`` is the whole contract — no private render survives
    behind it either."""
    assert mcp_ui_module.__all__ == [
        "UI_MEMORY_LIST_URI",
        "MCP_APP_MIME",
        "memory_list_card_html",
    ]
    for retired in ("memory_canvas_card_html", "_item_html", "_esc"):
        assert not hasattr(mcp_ui_module, retired), (
            f"{retired!r} is back — the dead canvas renderer must stay deleted"
        )
