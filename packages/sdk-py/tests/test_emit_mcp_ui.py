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
   retired shared-state canvas render stays retired (re-add it → dies);
6. the card is themed by the HOST: every design-token reference carries a
   fallback (strip one → dies), the token names are the host's vocabulary,
   the surface colours we used to impose are gone, and the zero-token render
   — the one that proves portability — still has a ground and an ink that
   differ, with no text rendering onto its own colour.
"""
from __future__ import annotations

import inspect
import pathlib
import re

from dna.emit import mcp_ui as mcp_ui_module
from dna.emit.mcp_ui import (
    HOST_DESIGN_TOKENS,
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
        "HOST_DESIGN_TOKENS",
        "memory_list_card_html",
    ]
    for retired in ("memory_canvas_card_html", "_item_html", "_esc"):
        assert not hasattr(mcp_ui_module, retired), (
            f"{retired!r} is back — the dead canvas renderer must stay deleted"
        )


# ── the card wears the HOST's theme, not ours ──────────────────────────────
#
# MCP App hosts inject a design-token system as CSS custom properties into the
# app iframe and change the VALUES when the user switches theme. Every one of
# them is optional — "hosts may provide any subset" — so a card that only looks
# right when every token exists is not portable. These tests hold the card to
# the zero-token case, which is the one that proves it.

#: A PREFIX allowance is what let a non-existent token look legitimate. The
#: guard used to admit anything starting ``--color-``/``--font-``/``--text-``/
#: ``--border-radius-``/``--shadow-``, so ``--text-sm`` — a Tailwind name, not
#: an MCP Apps one — passed as a host token and the card silently ignored the
#: host's type scale for as long as it shipped. The check is now EXACT
#: membership in the vendored spec lib's own key union
#: (:data:`~dna.emit.mcp_ui.HOST_DESIGN_TOKENS`), because "looks like a host
#: token" and "is one" are the same thing to a prefix and opposite things to a
#: host.

#: The brand values the card used to paint its own surface with. They are the
#: host's business now: ink ground, raised panel, hairline, ink-on-dark text,
#: muted text — and the amber that was legible on our dark ground only.
_RETIRED_SURFACE_COLOURS = ("#12161c", "#1a2029", "#252c37", "#e6eaef", "#8b95a3", "#e0a838")

#: The one brand colour that stays, because a host has no opinion about an
#: accent — the genome teal, on the wordmark and the tag chips.
_ACCENT = "#2f8570"


def _card_css() -> str:
    """The stylesheet DNA wrote, lifted out of the delivered template."""
    template = _template_without_vendor(memory_list_card_html())
    start = template.index("<style>") + len("<style>")
    return template[start:template.index("</style>", start)]


def _var_calls(css: str) -> list[tuple[str, str | None]]:
    """Every ``var()`` in ``css`` as ``(custom-property, fallback-or-None)``,
    scanned with paren balancing so a nested ``var()`` inside a fallback is
    read as part of that fallback rather than truncating it."""
    calls: list[tuple[str, str | None]] = []
    i = 0
    while (i := css.find("var(", i)) != -1:
        depth, j = 0, i + len("var(") - 1
        while j < len(css):
            if css[j] == "(":
                depth += 1
            elif css[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        inner = css[i + len("var("):j]
        name, sep, fallback = inner.partition(",")
        calls.append((name.strip(), fallback.strip() if sep else None))
        i += len("var(")
    return calls


def _resolve_without_host_tokens(css: str) -> str:
    """The card as a host that provides NO design tokens renders it: every
    ``var()`` collapses to its fallback (innermost first, so nested fallbacks
    resolve too). A reference with no fallback collapses to nothing — which is
    exactly what the browser does, and what makes the card disappear."""
    while "var(" in css:
        before = css
        for name, fallback in _var_calls(css):
            call = f"var({name}" + (f", {fallback})" if fallback is not None else ")")
            if call in css:
                css = css.replace(call, fallback if fallback is not None else "", 1)
        if css == before:  # pragma: no cover — a shape the scanner cannot reduce
            raise AssertionError(f"could not resolve the var() calls in: {css[:200]}")
    return css


def _declarations(css: str, selector: str) -> dict[str, str]:
    """The property→value map of one rule."""
    start = css.index(selector + "{") + len(selector) + 1
    body = css[start:css.index("}", start)]
    out: dict[str, str] = {}
    depth = 0
    prop = ""
    buf: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ":" and depth == 0 and not prop:
            prop, buf = "".join(buf).strip(), []
            continue
        if ch == ";" and depth == 0:
            if prop:
                out[prop] = "".join(buf).strip()
            prop, buf = "", []
            continue
        buf.append(ch)
    if prop:
        out[prop] = "".join(buf).strip()
    return out


def test_every_host_token_reference_carries_a_fallback():
    """The rule that decides portability: all host variables are optional and a
    host may provide any subset, so every reference needs its own fallback.
    Strip one fallback and this dies — which is the whole point, because that
    is the bug you cannot see in the host you happen to be testing in."""
    calls = _var_calls(_card_css())
    assert calls, "the card references no host design token at all"
    missing = [name for name, fallback in calls if not fallback]
    assert not missing, f"host tokens referenced with no fallback: {missing}"


def test_the_host_token_vocabulary_matches_the_vendored_lib():
    """``HOST_DESIGN_TOKENS`` is the vendored spec lib's own key union, not a
    list somebody typed. The lib is committed in this package, so the two can
    be compared and the constant can never drift from what a host is actually
    told it may send.

    Extracted from the ONE union the lib describes as *"CSS variable keys
    available to MCP apps for theming"* — not by grepping the whole 374 KB for
    things that look like custom properties, which would sweep up any CSS the
    bundle happens to contain. Bump the vendor and change the vocabulary, and
    this fails instead of silently blessing a stale name."""
    lib = _VENDOR.read_text(encoding="utf-8")
    marker = '.describe("CSS variable keys available to MCP apps for theming.")'
    assert lib.count(marker) == 1, (
        "the vendored lib no longer declares exactly one theming-key union — "
        "re-derive the extraction before trusting it"
    )
    end = lib.index(marker)
    union = lib[lib.rindex("u.union(", 0, end):end]
    declared = re.findall(r'u\.literal\("(--[a-z0-9-]+)"\)', union)

    assert declared, "no token literals found — the extraction broke, not the vocabulary"
    assert len(set(declared)) == len(declared), "the lib declares a token twice"
    assert list(HOST_DESIGN_TOKENS) == declared, (
        "HOST_DESIGN_TOKENS drifted from the vendored lib's key union"
    )


def test_the_card_targets_the_host_token_vocabulary():
    """The tokens are the host's DOCUMENTED names, checked by exact membership
    in the spec's key union — not by prefix.

    A prefix allowance cannot tell a real token from one that merely resembles
    it, and the difference is invisible: a name no host sets is a name whose
    fallback silently applies forever, so the card looks fine in every host and
    honours none of them. ``--text-sm``/``--text-xs`` shipped here for exactly
    that reason. Reintroduce a plausible-looking name and this dies."""
    names = {name for name, _ in _var_calls(_card_css())}
    unknown = sorted(n for n in names if n not in HOST_DESIGN_TOKENS)
    assert not unknown, (
        f"not MCP Apps host design tokens: {unknown} — no host sets these, so "
        "their fallbacks apply forever and the card ignores the host's theme"
    )
    # The load-bearing ones: ground, ink, hairline and type all come from the host.
    for required in (
        "--color-background-primary",
        "--color-text-primary",
        "--color-text-secondary",
        "--color-border-primary",
        "--font-sans",
        "--font-text-sm-size",
        "--font-text-xs-size",
    ):
        assert required in names, f"the card does not read {required}"


def test_the_card_no_longer_paints_its_own_surface():
    """A card that paints its own ground and ink inside someone else's chat
    reads as an advertisement, not as part of the product. The surface colours
    are gone; the accent — which a host has no opinion about — stays."""
    template = memory_list_card_html().lower()
    for retired in _RETIRED_SURFACE_COLOURS:
        assert retired not in template, f"the card still hardcodes {retired}"
    assert _ACCENT in template, "the brand accent was thrown out with the surface"


def test_zero_token_render_stays_legible():
    """The acceptance criterion, computed rather than eyeballed: with NOT ONE
    host variable set, the card still has a ground and an ink that differ.

    Every fallback resolves, nothing collapses to empty, and each rule's text
    colour differs from the surface it sits on — so no text can render onto
    its own colour. The ground/ink pair falls back to the UA's own system
    colours, which are contrasting by definition and follow the user's light
    or dark preference through ``color-scheme``."""
    css = _resolve_without_host_tokens(_card_css())

    assert ":" in css and "var(" not in css
    body = _declarations(css, "body")
    assert body["background"] == "Canvas"
    assert body["color"] == "CanvasText"
    assert body["background"] != body["color"], "ground and ink resolve to the same value"
    assert "light dark" in _declarations(css, ":root")["color-scheme"], (
        "without color-scheme the system-colour fallback is locked to light"
    )

    # No text renders onto its own surface: for every rule that sets a colour,
    # that colour differs from the nearest ground behind it.
    grounds = {
        "body": body["background"],
        ".dna-card": _declarations(css, ".dna-card")["background"],
    }
    for selector in (
        ".dna-mark", ".dna-scope", ".dna-summary", ".dna-meta", ".dna-tag",
        ".dna-empty", ".dna-foot",
    ):
        rule = _declarations(css, selector)
        colour = rule.get("color")
        assert colour, f"{selector} sets no colour"
        assert colour.strip(), f"{selector} resolves its colour to nothing — invisible"
        ground = rule.get("background", grounds[".dna-card"])
        assert colour != ground, f"{selector} renders its text onto its own colour"
