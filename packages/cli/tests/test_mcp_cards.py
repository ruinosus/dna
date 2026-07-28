"""MCP Apps (SEP-1865) — the **Prefab cards** on the read tools.

Three reading tools carry a card: ``list_stories``, ``sdlc_digest`` and
``list_my_kinds``. All three point ONE shared renderer resource
(``ui://dna/prefab``), and all three return a result whose ``content`` is
byte-identical to the pre-card baseline.

The two rules this file exists to pin, both from measurement:

1. **Merge, never replace.** FastMCP's ``app=True`` swaps ``content`` for the
   placeholder ``"[Rendered Prefab UI]"``. The spec makes ``content`` REQUIRED
   and ``structuredContent`` OPTIONAL, so that placeholder would blind every
   agent that consumes DNA over MCP without rendering. The result is built by
   hand instead: ``content`` byte-identical to the frozen pre-card fixtures,
   ``structured_content`` a strict SUPERSET of the same data.
2. **One shared resource URI.** The default synthesises
   ``ui://prefab/tool/<hash>/renderer.html`` per tool — a separate 6.6 MB
   document per card in bundled mode. Every card points the same URI, and no
   per-tool renderer is ever listed or served.

And the requirement that is not a polish pass: the card wears the HOST's
theme. Every design-token reference carries its own fallback (a host may
provide any subset), the names are the host's own vocabulary, and the
zero-token render — the one that proves portability — still has a ground and
an ink that differ.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")
pytest.importorskip("prefab_ui", reason="the card renderer needs the optional 'apps' extra")

from dna_cli import _mcp_cards as C  # noqa: E402
from dna_cli import _mcp_kinds as K  # noqa: E402
from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "mcp_cards"
_SCOPE = "concierge"

#: The tools that carry a card, with the impl seam each one is pinned through.
_CARD_TOOLS = ("list_stories", "sdlc_digest", "list_my_kinds")

#: Canonical payloads for the byte-stability tests. Byte-identity is a property
#: of the WIRE SERIALIZATION of a given payload (a live store's contents vary by
#: clock), so the payload is pinned in the fixture directory and the serialized
#: bytes are compared against the ``*.content.txt`` files captured BEFORE any
#: card existed. Do not edit the payloads together with the fixtures — that
#: would defeat the regression net.
_PAYLOADS = json.loads((_FIXTURES / "payloads.json").read_text(encoding="utf-8"))


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _pin_impls(monkeypatch):
    """Pin the three tools to their canonical payloads, at the seam each tool
    actually calls — the serialization path (tool fn + result shaping + FastMCP
    framing) is what is under test, never the store."""
    def _fixed(key):
        async def impl(*a, **k):
            return json.loads(json.dumps(_PAYLOADS[key]))
        return impl

    monkeypatch.setattr(M, "list_stories_impl", _fixed("list_stories"))
    monkeypatch.setattr(M, "sdlc_digest_impl", _fixed("sdlc_digest"))
    monkeypatch.setattr(K, "list_authored_kinds_impl", _fixed("list_my_kinds"))


def _declare_ui_extension(monkeypatch):
    """Make the in-memory client announce the MCP Apps extension, the way a
    UI-capable host does on the wire (the client SDK hard-codes its
    ``ClientCapabilities`` with no seam for one)."""
    import mcp.types as mt

    original = mt.ClientCapabilities

    def with_ui(**kwargs):
        return original(
            **kwargs,
            extensions={M.UI_EXTENSION_ID: {"mimeTypes": [M.MCP_APP_MIME]}},
        )

    monkeypatch.setattr(mt, "ClientCapabilities", with_ui)


def _call(dna_dir, tool: str):
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return await client.call_tool(tool, {"scope": _SCOPE})

    return asyncio.run(scenario())


# ── 1. merge, never replace ────────────────────────────────────────────────


def test_content_is_byte_identical_to_the_pre_card_baseline(dna_dir, monkeypatch):
    """The non-negotiable. A client that renders nothing reads the exact bytes
    it read before any card existed — one textual block, byte-equal to the
    fixture frozen from the un-carded tool.

    Adopt ``app=True`` (or hand-roll the serialization with anything but
    FastMCP's own converter) and this dies."""
    _pin_impls(monkeypatch)
    for tool in _CARD_TOOLS:
        result = _call(dna_dir, tool)
        blocks = [b for b in result.content if getattr(b, "text", None)]
        assert len(blocks) == 1, (
            f"{tool}: expected exactly one textual (data) content block — a UI "
            "declaration replaced or padded the text answer"
        )
        baseline = (_FIXTURES / f"{tool}.content.txt").read_bytes()
        assert blocks[0].text.encode("utf-8") == baseline, (
            f"{tool}: the card changed the bytes a UI-blind client reads"
        )


def test_the_card_rides_along_as_a_strict_superset(dna_dir, monkeypatch):
    """``structured_content`` carries the tool's own data UNCHANGED plus the
    Prefab wire keys. Not a replacement, not a reshaping: every key the tool
    returned is present with the identical value, and the card is what is
    added on top."""
    _pin_impls(monkeypatch)
    for tool in _CARD_TOOLS:
        result = _call(dna_dir, tool)
        data = json.loads([b for b in result.content if getattr(b, "text", None)][0].text)
        structured = result.structured_content or {}
        for key, value in data.items():
            assert key in structured, f"{tool}: the card dropped {key!r} from the data"
            assert structured[key] == value, f"{tool}: the card rewrote {key!r}"
        for wire_key in ("$prefab", "view", "state"):
            assert wire_key in structured, f"{tool}: no {wire_key!r} — no card at all"
        assert structured["$prefab"]["version"], f"{tool}: the card declares no protocol version"


def test_a_card_that_would_shadow_a_tool_field_raises(monkeypatch):
    """The merge is only safe while the two key sets are disjoint, and which
    keys Prefab uses is Prefab's to change. A collision must break loudly here
    rather than quietly replace a tool's field with a rendering detail on a
    consumer's screen."""
    class _Colliding:
        @staticmethod
        def to_json():
            return {"$prefab": {"version": "0.3"}, "scope": "hijacked"}

    with pytest.raises(ValueError, match="shadow"):
        C.with_card({"scope": "concierge"}, _Colliding())


# ── 2. one shared renderer resource ────────────────────────────────────────


def test_every_card_tool_points_the_one_shared_renderer(dna_dir, monkeypatch):
    """All three declarations point the SAME ``ui://`` resource. The default
    would mint ``ui://prefab/tool/<hash>/renderer.html`` per tool — a separate
    6.6 MB document each, in a mode where every host prefetches them."""
    from fastmcp import Client

    _declare_ui_extension(monkeypatch)

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return {t.name: t for t in await client.list_tools()}

    tools = asyncio.run(scenario())
    pointed = set()
    for tool in _CARD_TOOLS:
        uri = ((tools[tool].meta or {}).get("ui") or {}).get("resourceUri")
        assert uri, f"{tool} declares no card template"
        pointed.add(uri)
    assert pointed == {C.UI_PREFAB_URI}, f"the cards do not share one renderer: {pointed}"


def test_a_ui_blind_client_is_not_offered_the_card_pointer(dna_dir):
    """The SEP-1865 capability check reaches the new tools too, not only the
    memory pair it was written for: a client that completes the handshake
    without the MCP Apps extension is not advertised a UI-enabled tool. The
    TOOL is still listed — we withhold the card, never the capability."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:  # declares no extension
            return {t.name: t for t in await client.list_tools()}

    tools = asyncio.run(scenario())
    for tool in _CARD_TOOLS:
        assert not ((tools[tool].meta or {}).get("ui") or {}).get("resourceUri"), (
            f"{tool} advertised its card to a client that cannot render it"
        )
        assert tools[tool].description


def test_no_per_tool_renderer_is_ever_listed_or_served(dna_dir):
    """The listing carries exactly ONE Prefab renderer, and nothing under the
    per-tool hash scheme. Drop the ``resource_uri`` override and this dies with
    three hashed resources instead of one shared one."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return [str(r.uri) for r in await client.list_resources()]

    uris = asyncio.run(scenario())
    assert uris.count(C.UI_PREFAB_URI) == 1, f"the shared renderer is not listed once: {uris}"
    hashed = [u for u in uris if u.startswith("ui://prefab/tool/")]
    assert not hashed, f"per-tool renderer resources were synthesised: {hashed}"


def test_the_shared_renderer_is_served_bundled_and_self_contained(dna_dir):
    """``resources/read`` answers the renderer with the SEP-1865 profile
    mimeType, in BUNDLED mode — no CDN stub, no external origin. A card that
    phoned out on render would put a third-party host in the request path of a
    tenant's board, and the MCP Apps CSP is deny-by-default."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return await client.read_resource(C.UI_PREFAB_URI)

    from prefab_ui.renderer import get_renderer_csp, get_renderer_html

    contents = asyncio.run(scenario())
    assert len(contents) == 1
    block = contents[0]
    assert block.mimeType == M.MCP_APP_MIME
    html = block.text

    # It is the BUNDLED document, not the CDN stub. Grepping for a CDN string
    # cannot answer this — the bundle carries the stub's own template literals
    # as inert data — so the question is asked structurally instead: the served
    # document is the bundled one with our stylesheet spliced in, and it is not
    # the stub.
    bundled = get_renderer_html(mode="bundled")
    stub = get_renderer_html(mode="cdn")
    assert html != stub and len(html) > len(stub) * 100
    assert html.replace(f"<style>{C.host_theme_css()}</style>", "", 1) == bundled, (
        "the served resource is not the bundled renderer plus the theme bridge"
    )
    # Self-containment is the library's own declared contract for this mode:
    # bundled needs no external origin at all, which is what lets the resource
    # be served under the MCP Apps deny-by-default CSP with nothing declared.
    assert not any(get_renderer_csp(mode="bundled").values())
    assert get_renderer_csp(mode="cdn")["resource_domains"], "the CDN mode would need one"

    # The theme bridge travels INSIDE the resource — fetched once, cached by
    # URI — rather than in every tool result. Asked for by a string only WE
    # write: the bundled document mentions the host token names itself, in the
    # schema it validates the host context against, so a token name proves
    # nothing here.
    assert ".dna-mark{" in html, "the host-theme bridge is not in the resource"
    assert html.index(".dna-mark{") < html.index("</head>"), "the bridge is not in the head"


# ── 3. the card wears the HOST's theme ─────────────────────────────────────
#
# The scanners below are the ones ``dna.emit.mcp_ui``'s memory card is proven
# with, reproduced rather than imported: a test under ``packages/cli/tests``
# cannot reach into ``packages/sdk-py``'s suite, and the alternative — a second,
# looser way of asking the same question — is exactly what the memory card's
# conversion was told not to introduce.

#: The MCP Apps host design-token vocabulary. Every name the bridge reads must
#: be one a host actually sets; a private ``--dna-*`` property is one no host
#: will ever provide.
_HOST_TOKEN_FAMILIES = (
    "--color-", "--font-", "--border-radius-", "--border-width-", "--shadow-",
)


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
    """The bridge as a host that provides NO design tokens resolves it: every
    ``var()`` collapses to its fallback (innermost first, so nested fallbacks
    resolve too). A reference with no fallback collapses to nothing — which is
    exactly what the browser does, and what makes the card disappear."""
    while "var(" in css:
        before = css
        for name, fallback in _var_calls(css):
            call = f"var({name}" + (f",{fallback})" if fallback is not None else ")")
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
    depth, prop, buf = 0, "", []
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


def _light_dark(value: str, mode: str) -> str:
    """Resolve ``light-dark(a,b)`` the way the UA does for a given
    ``color-scheme`` — the fallback shape the semantic hues need, because one
    mixing ratio cannot clear AA against both a light and a dark tint."""
    while "light-dark(" in value:
        i = value.index("light-dark(")
        depth, j = 0, i + len("light-dark")
        while j < len(value):
            if value[j] == "(":
                depth += 1
            elif value[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        light, _, dark = value[i + len("light-dark("):j].partition(",")
        value = value[:i] + (light if mode == "light" else dark).strip() + value[j + 1:]
    return value


def test_every_host_token_reference_carries_a_fallback():
    """The rule that decides portability: all host variables are optional and a
    host may provide any subset, so every reference needs its own fallback.
    Strip one and this dies — which is the whole point, because that is the bug
    you cannot see in the host you happen to be testing in."""
    calls = _var_calls(C.host_theme_css())
    assert calls, "the bridge references no host design token at all"
    missing = [name for name, fallback in calls if not fallback]
    assert not missing, f"host tokens referenced with no fallback: {missing}"


def test_the_bridge_targets_the_host_token_vocabulary():
    """The tokens are the host's documented names, not names we invented."""
    names = {name for name, _ in _var_calls(C.host_theme_css())}
    unknown = [n for n in names if not n.startswith(_HOST_TOKEN_FAMILIES)]
    assert not unknown, f"not host design tokens: {unknown}"
    assert names == set(C.HOST_TOKENS), (
        "HOST_TOKENS and the stylesheet disagree about what the card reads"
    )
    for required in (
        "--color-background-primary",
        "--color-text-primary",
        "--color-text-secondary",
        "--color-border-primary",
        "--font-sans",
    ):
        assert required in names, f"the bridge does not read {required}"


def test_the_bridge_never_reads_a_token_it_also_declares():
    """A custom property whose own value reads itself is a CYCLE, and a cycle
    makes the declaration invalid — the property resolves to nothing and takes
    every rule that uses it with it. Several host token names collide exactly
    with the renderer's own theme names (``--font-sans``, ``--font-weight-*``),
    which is precisely where this bug is easy to write and impossible to see."""
    css = C.host_theme_css()
    declared = {p for p in _declarations(css, ":root:root")}
    read = {name for name, _ in _var_calls(css)}
    assert not (declared & read), f"self-referential custom properties: {declared & read}"


def test_the_bridge_outranks_the_renderers_own_palette():
    """The renderer declares its base palette in ``:root`` and swaps it in
    ``.dark``; the bridge has to win over BOTH without ``!important``. A
    doubled pseudo-class raises specificity above a class selector, and the
    rule is unlayered, so it also outranks anything the renderer puts in a
    cascade layer. Weaken the selector to ``:root`` and the card silently keeps
    the renderer's own colours in dark mode."""
    css = C.host_theme_css()
    assert ":root:root{" in css
    assert "@layer" not in css, "a layered rule loses to every unlayered one"
    assert "!important" not in css, "specificity, not force"


def test_zero_token_render_stays_legible():
    """The acceptance criterion, computed rather than eyeballed: with NOT ONE
    host variable set, the card still has a ground and an ink that differ, in
    BOTH the light and the dark resolution of the fallbacks.

    Every fallback resolves — nothing collapses to empty — and the ground/ink
    pair falls back to the UA's own system colours, which are contrasting by
    definition and follow the user's preference through ``color-scheme``."""
    css = _resolve_without_host_tokens(C.host_theme_css())
    assert "var(" not in css
    root = _declarations(css, ":root:root")
    assert "light dark" in root["color-scheme"], (
        "without color-scheme the system-colour fallback is locked to light"
    )
    for prop, value in root.items():
        assert value.strip(), f"{prop} resolves to nothing — the card loses it entirely"

    assert root["--background"] == "Canvas"
    assert root["--foreground"] == "CanvasText"
    assert root["--background"] != root["--foreground"], (
        "ground and ink resolve to the same value"
    )
    # Nothing paints its text onto its own ground.
    for ink, ground in (
        ("--foreground", "--background"),
        ("--card-foreground", "--card"),
        ("--muted-foreground", "--muted"),
        ("--primary-foreground", "--primary"),
    ):
        assert root[ink] != root[ground], f"{ink} resolves onto {ground}"

    # The semantic hues resolve to a DIFFERENT value per mode — a single value
    # cannot clear AA against both a light and a dark tint, and the measured
    # pairs are what the fallback exists to carry.
    for hue in ("--destructive", "--warning", "--success", "--info"):
        light = _light_dark(root[hue], "light")
        dark = _light_dark(root[hue], "dark")
        assert light.startswith("#") and dark.startswith("#"), (
            f"{hue} has no measured per-mode fallback: {root[hue]}"
        )
        assert light != dark, f"{hue} uses one value for both modes"
    # The retired SDLC amber measured 2.14:1 on white — illegible on any light
    # host. It must not come back as a fallback.
    assert "#e0a838" not in css, "the illegible SDLC amber is back"


# ── 4. what each card actually renders ─────────────────────────────────────


#: tool → the builder that shapes its card. Resolved lazily (by NAME, not by
#: attribute) so a missing builder fails the test that needs it and no other.
_BUILDERS = {
    "list_stories": "stories_app",
    "sdlc_digest": "digest_app",
    "list_my_kinds": "kinds_app",
}


def _wire(tool: str) -> dict:
    return getattr(C, _BUILDERS[tool])(_PAYLOADS[tool]).to_json()


def test_the_stories_card_binds_the_rows_and_carries_an_empty_state():
    """The Story roster is a table bound to state, with an honest empty state
    for a scope that has none."""
    wire = _wire("list_stories")
    assert wire["state"]["count"] == 3
    assert [s["name"] for s in wire["state"]["stories"]] == [
        "s-cards", "s-negotiation", "s-bare",
    ]
    # A missing field renders as an em dash, never as the string "None".
    bare = wire["state"]["stories"][2]
    assert bare["title"] == "—" and bare["feature"] == "—"
    blob = json.dumps(wire)
    assert '"DataTable"' in blob
    assert "None" not in json.dumps(wire["state"])
    assert "No Stories in this scope yet" in blob, "no empty state"


def test_the_digest_card_maps_rag_to_a_measured_badge_variant():
    """The digest's own three-value RAG vocabulary maps to the renderer's
    semantic variants — the only place a colour carries meaning on these
    cards, and the reason the semantic fallbacks were measured."""
    wire = _wire("sdlc_digest")
    assert wire["state"]["rag"] == "red"
    assert wire["state"]["rag_variant"] == "destructive"
    assert C._RAG_VARIANT == {
        "red": "destructive", "amber": "warning", "green": "success",
    }
    # Every attention bucket reaches the table, with the field that says WHY.
    rows = wire["state"]["attention_rows"]
    assert [r["bucket"] for r in rows] == ["Blocked", "Open question"]
    assert rows[0]["why"] == "waiting on the renderer decision"
    assert rows[1]["why"] == "prefab or hand-written?"
    # A partial read is stated on the card, not only in the text answer.
    assert wire["state"]["partial"] is True
    assert "partial" in wire["state"]["partial_note"]


def test_the_kinds_card_shows_the_one_fact_the_roster_exists_for():
    """``approved`` is the fact this route exists to publish — an unapproved
    Kind is inert — and it is one boolean among ten fields in the text answer.
    The card promotes it to a badge and keeps both actors visible."""
    wire = _wire("list_my_kinds")
    rows = wire["state"]["kinds"]
    assert [r["name"] for r in rows] == ["kd-contrato", "kd-apolice"]
    assert rows[0]["status"] == "proposed", "an unapproved Kind must not read as approved"
    assert rows[1]["status"] == "approved"
    # BOTH actors survive: the reviewer's first question is who proposed it.
    assert rows[0]["proposed_by"] == "agent-7"
    assert rows[1]["approved_by"] == "barna"
    # The headline is the count that is still inert, and it wears the measured
    # warning colour only while something is actually waiting on a person.
    assert wire["state"]["pending"] == 1
    assert wire["state"]["pending_variant"] == "warning"
    assert C._pending_variant(0) == "success"


def test_no_card_wires_an_action():
    """Display only, deliberately. What a card can DO is gated behind
    revocation work that does not exist yet, and a button that acts without a
    way to take the grant back is the wrong thing to ship first. Add one and
    this dies."""
    for tool in _CARD_TOOLS:
        blob = json.dumps(_wire(tool))
        for forbidden in (
            "CallTool", "SendMessage", "OpenLink", "onClick", "onRowClick",
            '"action"', '"actions"', '"onSubmit"',
        ):
            assert forbidden not in blob, f"{tool} wires {forbidden} — cards are read-only here"
