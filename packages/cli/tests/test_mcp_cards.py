"""MCP Apps (SEP-1865) — the **Prefab cards** on the read tools.

Four reading tools carry a card: ``list_stories``, ``sdlc_digest``,
``list_my_kinds`` and ``review_kind``. All four point ONE shared renderer
resource (``ui://dna/prefab``), and all four return a result whose ``content``
is byte-identical to the pre-card baseline.

The two rules this file exists to pin, both from measurement:

1. **Merge, never replace.** FastMCP's ``app=True`` swaps ``content`` for the
   placeholder ``"[Rendered Prefab UI]"``. The spec makes ``content`` REQUIRED
   and ``structuredContent`` OPTIONAL, so that placeholder would blind every
   agent that consumes DNA over MCP without rendering. The result is built by
   hand instead: ``content`` byte-identical to the frozen pre-card fixtures,
   ``structured_content`` a strict SUPERSET of the same data.
2. **One shared resource URI.** The default synthesises
   ``ui://prefab/tool/<hash>/renderer.html`` per tool — a separate 6.6 MB
   instance per card in bundled mode. Every card points the same URI, and no
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
_CARD_TOOLS = ("list_stories", "sdlc_digest", "list_my_kinds", "review_kind")

#: Canonical payloads for the byte-stability tests. Byte-identity is a property
#: of the WIRE SERIALIZATION of a given payload (a live store's contents vary by
#: clock), so the payload is pinned in the fixture directory and the serialized
#: bytes are compared against the ``*.content.txt`` files captured BEFORE any
#: card existed. Do not edit the payloads together with the fixtures — that
#: would defeat the regression net.
#:
#: Two of them WERE re-frozen, once, and the procedure is written down because
#: "we regenerated it" is exactly what the sentence above forbids. The
#: ``list_my_kinds`` payload had drifted from its own impl — i-085 added
#: ``state``/``revoked_by``/``revoked_at`` to ``_authored_kind_summary`` and the
#: fixture never grew them, so the card was being proven against a shape the
#: tool can no longer return — and ``review_kind`` is new. Both were re-frozen
#: by running the payload through a BARE FastMCP tool (no ``app=``, no
#: ``with_card``), which is the pre-card path itself and not the path under
#: test; the procedure was validated by reproducing the two UNTOUCHED baselines
#: (``list_stories``, ``sdlc_digest``) byte for byte first. Re-freezing through
#: ``with_card`` would have made this test tautological.
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

    # `review_kind` wraps its projection in an envelope (`declaration`) because
    # the projection's own `state` field collides with a Prefab wire key, so the
    # seam returns the INNER half and the tool builds the envelope. Pinning the
    # seam rather than the tool keeps the envelope itself under test.
    async def _one_kind(*a, **k):
        return json.loads(json.dumps(_PAYLOADS["review_kind"]["declaration"]))

    monkeypatch.setattr(K, "get_authored_kind_impl", _one_kind)


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


#: The extra argument each card tool needs beyond ``scope``. ``review_kind``
#: addresses ONE Kind, so it takes a name; the value is irrelevant (the seam is
#: pinned) but its presence is not — the tool refuses without it.
_EXTRA_ARGS = {"review_kind": {"kind": "Contrato"}}


def _call(dna_dir, tool: str):
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return await client.call_tool(
                tool, {"scope": _SCOPE, **_EXTRA_ARGS.get(tool, {})},
            )

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
    6.6 MB instance each, in a mode where every host prefetches them."""
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

    # It is the BUNDLED instance, not the CDN stub. Grepping for a CDN string
    # cannot answer this — the bundle carries the stub's own template literals
    # as inert data — so the question is asked structurally instead: the served
    # instance is the bundled one with our stylesheet spliced in, and it is not
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
    # write: the bundled instance mentions the host token names itself, in the
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

#: The MCP Apps host design-token vocabulary is NOT redeclared here: it is the
#: spec's own key union, imported from the SDK (which holds it against the
#: vendored ``@modelcontextprotocol/ext-apps`` lib), so the two faces cannot
#: disagree about what a host may send.
#:
#: And it is exact membership, never a prefix allowance. A prefix cannot tell a
#: real token from a name that merely resembles one, and the difference is
#: invisible: a fallback makes a wrong name look fine in every host, forever.
#: That is not hypothetical — ``--text-sm``/``--text-xs`` shipped on the memory
#: card under exactly such an allowance.
from dna.emit.mcp_ui import HOST_DESIGN_TOKENS  # noqa: E402


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
    """The tokens are the host's DOCUMENTED names, checked by exact membership
    in the spec's key union — not by prefix, and not against a list this file
    keeps for itself.

    A name no host sets is a name whose fallback applies forever: the card
    reads it, nothing provides it, nothing looks broken, and that part of the
    host's theme is silently ignored. Invent a plausible-looking token and this
    dies."""
    names = {name for name, _ in _var_calls(C.host_theme_css())}
    unknown = sorted(n for n in names if n not in HOST_DESIGN_TOKENS)
    assert not unknown, (
        f"not MCP Apps host design tokens: {unknown} — no host sets these, so "
        "their fallbacks apply forever and the card ignores the host's theme"
    )
    assert names == set(C.HOST_TOKENS), (
        "HOST_TOKENS and the stylesheet disagree about what the card reads"
    )
    assert not set(C.HOST_TOKENS) - set(HOST_DESIGN_TOKENS), (
        "HOST_TOKENS names something outside the spec's key union"
    )
    for required in (
        "--color-background-primary",
        "--color-text-primary",
        "--color-text-secondary",
        "--color-border-primary",
        "--font-sans",
        "--font-text-sm-size",
        "--font-text-xs-size",
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
    "review_kind": "kind_review_app",
}

#: The card builders that are handed the INNER projection rather than the whole
#: tool payload — see ``_pin_impls`` for why ``review_kind`` has an envelope.
_INNER = {"review_kind": "declaration"}


def _wire(tool: str) -> dict:
    payload = _PAYLOADS[tool]
    if tool in _INNER:
        payload = payload[_INNER[tool]]
    return getattr(C, _BUILDERS[tool])(payload).to_json()


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
    """The approval state is the fact this route exists to publish — an
    unapproved Kind is inert — and it is one field among thirteen in the text
    answer. The card promotes the counts to badges and keeps both actors
    visible."""
    wire = _wire("list_my_kinds")
    rows = wire["state"]["kinds"]
    assert [r["name"] for r in rows] == ["kd-contrato", "kd-apolice", "kd-recibo"]
    assert rows[0]["state"] == "unapproved", "an unapproved Kind must not read as approved"
    assert rows[1]["state"] == "approved"
    # BOTH actors survive: the reviewer's first question is who proposed it.
    assert rows[0]["proposed_by"] == "agent-7"
    assert rows[1]["approved_by"] == "barna"
    # The headline is the count that is still inert, and it wears the measured
    # warning colour only while something is actually waiting on a person.
    assert wire["state"]["pending"] == 1
    assert wire["state"]["pending_variant"] == "warning"
    assert C._pending_variant(0) == "success"


def test_a_revoked_kind_reads_as_revoked_and_not_as_merely_unapproved():
    """i-085 shipped revocation as a THIRD state and accepted, explicitly, that
    every listing surface has to learn to render it. This is one of them.

    The two states the boolean collapsed behave in OPPOSITE ways: a Kind that
    was never approved is never registered, so its instances are accepted with
    NO validation; a REVOKED one refuses new instances and marks every existing
    one invalid. Showing both as "not approved" reports the tightest state in
    the system as the loosest.

    So the row carries the core's own word, the revoker is visible beside the
    proposer and the approver (revoking deliberately leaves ``approved_by``
    standing — the audit keeps who conferred effect in the first place), and the
    count gets its own badge in the danger hue rather than being folded into the
    amber "awaiting approval" one."""
    wire = _wire("list_my_kinds")
    state = wire["state"]
    revoked = next(r for r in state["kinds"] if r["name"] == "kd-recibo")

    assert revoked["state"] == "revoked", (
        "a revoked Kind reads as something else — and every other value here "
        "means the opposite thing about what its instances may do"
    )
    assert revoked["revoked_by"] == "ana" and revoked["revoked_at"]
    # The approval is NOT erased by the revocation: somebody conferred effect on
    # this Kind and it governed real instances for a while.
    assert revoked["approved_by"] == "barna"

    # Its own headline badge, in its own hue. Folded into the amber counter it
    # would be invisible: "1 awaiting approval" is a true sentence about a
    # roster where nothing is awaiting anything and one Kind is refusing writes.
    assert state["revoked"] == 1 and state["pending"] == 1
    assert "1 revoked" in state["revoked_label"]
    assert C._STATE_VARIANT["revoked"] == "destructive"
    assert C._STATE_VARIANT["unapproved"] != C._STATE_VARIANT["revoked"], (
        "the loosest and the tightest state paint the same colour"
    )
    blob = json.dumps(wire)
    assert '"revoked_by"' in blob and '"Revoked by"' in blob, (
        "the revoker never reaches the table"
    )


def test_the_state_cell_is_never_derived_from_the_boolean():
    """The fallback that would make a wrong value render identically to a right
    one, refused at the source.

    ``approved: false`` is true of BOTH an unapproved and a revoked Kind, so
    "no ``state``? derive it from ``approved``" silently prints ``unapproved``
    over a revoked row — and it would look completely fine. A row with no
    ``state`` therefore renders the em dash: the data did not say, and the card
    does not say for it."""
    assert C._state_of({"approved": False, "revoked_by": "ana"}) == ""
    assert C._state_of({"approved": True}) == ""
    assert C._state_of({"state": "revoked"}) == "revoked"
    assert C._state_of({"state": "whatever-comes-next"}) == "", (
        "an unknown state was accepted — a fourth state must fail visibly"
    )
    wire = C.kinds_app({"scope": "s", "kinds": [{"name": "x", "approved": False}]})
    row = wire.to_json()["state"]["kinds"][0]
    assert row["state"] == "—", row


def test_the_review_card_shows_what_would_be_approved():
    """The hole the portal closed in i-076, not reopened on this face.

    A reviewer conferring effect is deciding about the SCHEMA — registration is
    what gives a Kind validation and routing — and the roster deliberately does
    not carry it. So the single-Kind card does: the schema, both actors, and a
    sentence saying what the current state means for instances."""
    wire = _wire("review_kind")
    state = wire["state"]
    assert state["kind"] == "Contrato"
    assert state["state"] == "unapproved"
    assert state["state_variant"] == "warning"
    # The schema is really there, and it is the one from the instance.
    assert state["has_schema"] is True
    schema = json.loads(state["schema"])
    assert schema == _PAYLOADS["review_kind"]["declaration"]["schema"]
    assert '"Code"' in json.dumps(wire), "the schema is not rendered as a block"
    # Both actors, and the sentence that says what "unapproved" costs.
    assert "agent-7" in state["proposed"]
    assert "NO schema validation" in state["meaning"]
    assert state["traits"] == "searchable"


def test_the_review_card_does_not_invent_a_schema_it_does_not_have():
    """``None`` and ``{}`` are different facts and the projection keeps them
    apart, so the card must too. An empty code block reads as "this Kind
    declares nothing", which is a claim; "no schema is stored" is the fact."""
    declaration = dict(_PAYLOADS["review_kind"]["declaration"], schema=None)
    state = C.kind_review_app(declaration).to_json()["state"]
    assert state["has_schema"] is False
    assert state["schema"] == ""


def test_the_review_card_offers_the_act_only_where_it_would_change_something():
    """The button is shown on an unapproved Kind and on a REVOKED one — the
    second because approving again is the documented one-act undo, and hiding it
    would leave the reviewer hunting for a route this face does not have. It is
    NOT shown on an approved Kind: there is nothing to confer, and a live button
    that only re-stamps the approver invites a click that means nothing."""
    base = _PAYLOADS["review_kind"]["declaration"]

    unapproved = C.kind_review_app(base).to_json()["state"]
    assert unapproved["can_approve"] is True
    assert "put this Kind into effect" in unapproved["approve_label"]

    revoked = C.kind_review_app(
        dict(base, state="revoked", approved_by="barna", revoked_by="ana")
    ).to_json()["state"]
    assert revoked["can_approve"] is True
    assert "restore" in revoked["approve_label"], (
        "a revoked Kind's button must say what pressing it does — approving "
        "again is an undo, not a first approval"
    )
    assert revoked["was_revoked"] is True and revoked["was_approved"] is True

    approved = C.kind_review_app(
        dict(base, state="approved", approved=True, approved_by="barna")
    ).to_json()["state"]
    assert approved["can_approve"] is False


def test_no_card_forces_a_colour_mode():
    """Setting ``mode`` on a card would silently kill the host theme on EVERY
    card, which is why it is pinned here rather than left to a comment.

    Read from the renderer's own source: the host-context handler is
    ``s.current ? ZN(s.current) : osr(f)``. ``s.current`` is the ``mode`` the
    wire carried, and ``osr`` is the ONLY function that injects the host's
    ``styles.variables`` (and sets ``colorScheme``). So a card that declares a
    mode takes the branch that merely toggles a dark class and NEVER receives
    the host's design tokens — the theme bridge would resolve every one of its
    fallbacks and the card would ignore the host completely.

    A plausible future "just force dark on this card" is therefore a
    theme-wide regression that nothing else would catch: it breaks no layout,
    raises nothing, and looks deliberate. Add ``mode=`` to any ``PrefabApp``
    and this dies."""
    for tool in _CARD_TOOLS:
        wire = _wire(tool)
        assert "mode" not in wire, (
            f"{tool} declares a colour mode — the renderer would then skip the "
            "host-context handler that injects styles.variables, and the card "
            "would never see the host's tokens at all"
        )
        # The same trap through the other door: a `theme` with a mode on it is
        # serialized to the same top-level `mode` key.
        assert "theme" not in wire


def _tool_calls(node: object) -> list[dict]:
    """Every ``toolCall`` action anywhere in a serialized card, at any depth."""
    found: list[dict] = []
    if isinstance(node, dict):
        if node.get("action") == "toolCall":
            found.append(node)
        for value in node.values():
            found += _tool_calls(value)
    elif isinstance(node, list):
        for value in node:
            found += _tool_calls(value)
    return found


def test_exactly_one_card_acts_and_it_is_the_approval_one():
    """Every card here was display-only, and the reason was named: a button
    that acts without a way to take the grant back is the wrong thing to ship
    first. Revocation shipped (i-085), so ONE button ships with it — and the
    rule is now "one", not "none", which is a weaker rule and therefore needs
    to be pinned in both directions.

    Both directions: no OTHER card may grow an action (a roster button is
    pressed against a schema the reviewer has not seen), and the review card's
    action must be the approval call and nothing else."""
    for tool in _CARD_TOOLS:
        blob = json.dumps(_wire(tool))
        if tool == "review_kind":
            continue
        for forbidden in (
            "CallTool", "SendMessage", "OpenLink", "onClick", "onRowClick",
            '"action"', '"actions"', '"onSubmit"', "toolCall",
        ):
            assert forbidden not in blob, f"{tool} wires {forbidden} — a mirror, not a door"

    calls = _tool_calls(_wire("review_kind"))
    assert len(calls) == 1, f"the review card wires {len(calls)} tool calls, not one"
    assert calls[0]["tool"] == C.APPROVE_TOOL, calls[0]
    # The button names the Kind and NOTHING else. A workspace or an approver a
    # card could name would be a workspace or an approver a caller can name.
    assert set(calls[0].get("arguments") or {}) == {"kind"}, calls[0]


def test_the_card_button_targets_a_tool_the_model_cannot_see(dna_dir, monkeypatch):
    """The card half of the visibility guard, and the one that closes the loop.

    ``_mcp_kinds`` declares the tool app-only; ``_mcp_cards`` points a button at
    a NAME. Nothing else makes those the same tool, and a button aimed at a
    model-visible tool is the exact outcome this feature must not ship — it
    would not fail to render, it would work perfectly, for the model too.

    So the target name is resolved against the LIVE server: it must be a
    registered tool, and it must be declared app-only. Point the button at
    ``author_kind``, or drop ``visibility`` from the approval tool, and this
    dies."""
    from fastmcp import Client

    # As a UI-CAPABLE host: a client that cannot render is not offered the tool
    # at all (see the sibling test), and the question here is what the host that
    # WILL show the button receives.
    _declare_ui_extension(monkeypatch)

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return {t.name: t for t in await client.list_tools()}

    tools = asyncio.run(scenario())
    target = tools.get(C.APPROVE_TOOL)
    assert target is not None, (
        f"the review card's button calls {C.APPROVE_TOOL!r}, which this server "
        f"does not register — it would fail at click time, on a user's machine"
    )
    assert M.app_only(target), (
        f"{C.APPROVE_TOOL} is offered to the MODEL — the button is no longer "
        "the only thing that can press it"
    )


# ── 5. the card's columns are the KIND's, not the card's ───────────────────
#
# The false green this section is shaped against: asserting that the Story card
# renders a "Status" header passes whether that header came from the Story Kind
# or from a literal in the builder — which is exactly what it WAS. So every
# test below changes the DECLARATION and requires the card to change with it.
# A hardcoded column list cannot pass any of them.


def _columns(wire: dict) -> list[dict]:
    """The ONE DataTable's columns, found by walking the view tree — read off
    the wire the host would actually receive, never from the builder's locals."""
    found: list[list[dict]] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "DataTable":
                found.append(node.get("columns") or [])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(wire["view"])
    assert len(found) == 1, f"expected exactly one DataTable, got {len(found)}"
    return found[0]


def _headers(wire: dict) -> list[str]:
    return [c["header"] for c in _columns(wire)]


def _stories_payload(presentation):
    """The pinned Story payload plus a presentation. The rows are untouched —
    what varies is only how the Kind says they read."""
    return dict(
        json.loads(json.dumps(_PAYLOADS["list_stories"])),
        presentation=presentation,
    )


def test_the_story_cards_columns_come_from_the_kind():
    """PROVENANCE. Same rows, two different declarations, two different
    cards — headers, order and heading all follow the Kind."""
    first = C.stories_app(_stories_payload({
        "label": "Stories",
        "icon": "B",
        "fields": [
            {"field": "name", "label": "Story", "role": "identifier"},
            {"field": "status", "label": "Status", "role": "status"},
        ],
        "hidden": [],
    })).to_json()
    assert _headers(first) == ["Story", "Status"]
    assert first["state"]["label"] == "Stories"

    second = C.stories_app(_stories_payload({
        "label": "Histórias",
        "icon": "H",
        "fields": [
            {"field": "priority", "label": "Prioridade", "role": "rank"},
            {"field": "title", "label": "Título", "role": "title"},
            {"field": "name", "label": "Ficha", "role": "identifier"},
        ],
        "hidden": [],
    })).to_json()
    assert _headers(second) == ["Prioridade", "Título", "Ficha"], (
        "the columns did not follow the Kind — they are still hardcoded"
    )
    assert [c["key"] for c in _columns(second)] == ["priority", "title", "name"]
    assert second["state"]["label"] == "Histórias"
    assert "Histórias" in json.dumps(second, ensure_ascii=False), (
        "the heading is not the Kind's"
    )


def test_a_payload_with_no_presentation_still_renders_every_column():
    """A server that predates the declaration — or a Kind that declares none —
    must still produce a usable card. The fallback derives the columns from the
    rows themselves; it never blanks the table and never invents a field."""
    wire = C.stories_app(_PAYLOADS["list_stories"]).to_json()
    assert [c["key"] for c in _columns(wire)] == [
        "name", "title", "status", "feature", "priority",
    ]
    assert _headers(wire) == ["Name", "Title", "Status", "Feature", "Priority"]
    assert wire["state"]["count"] == 3


def test_a_new_kind_gets_a_usable_card_with_no_new_card_code():
    """THE measure. A Kind nothing in this repo has ever heard of — a tenant's
    own, in its own language — renders through the SAME generic builder, with
    its own labels, its own order and its own heading. No branch here knows the
    word ``Contrato``."""
    wire = C.documents_app(
        {
            "scope": "acme",
            "count": 1,
            "instances": [
                {"name": "c-001", "parte": "Acme Ltda", "situacao": "vigente"},
            ],
            "presentation": {
                "label": "Contratos",
                "icon": "C",
                "fields": [
                    {"field": "name", "label": "Contrato", "role": "identifier"},
                    {"field": "parte", "label": "Parte", "role": "owner"},
                    {"field": "situacao", "label": "Situação", "role": "status"},
                ],
                "hidden": [],
            },
        },
        items_key="instances",
    ).to_json()
    assert _headers(wire) == ["Contrato", "Parte", "Situação"]
    assert wire["state"]["label"] == "Contratos"
    assert wire["state"]["instances"][0]["situacao"] == "vigente"
    assert "No Contratos" in json.dumps(wire), (
        "the empty state names some other Kind — it is not derived"
    )


def test_the_card_prints_no_python_repr_for_a_missing_value():
    """The em dash rule survives the generalisation: a field the instance does
    not carry is absent, and a card that printed ``None`` would have invented a
    value."""
    wire = C.documents_app(
        {
            "count": 1,
            "instances": [{"name": "c-001", "parte": None}],
            "presentation": {
                "label": "Contratos", "icon": None,
                "fields": [{"field": "name", "label": "Contrato", "role": None},
                           {"field": "parte", "label": "Parte", "role": None}],
                "hidden": [],
            },
        },
        items_key="instances",
    ).to_json()
    assert wire["state"]["instances"][0]["parte"] == "—"
    assert "None" not in json.dumps(wire["state"])


def test_the_review_card_shows_how_the_kinds_documents_will_read():
    """``schema`` says what an instance may CONTAIN; the presentation says how
    it will READ, on every surface the workspace has. Both are conferred by the
    same approval, so a reviewer sees both — and the rows here are the Kind's
    declaration, not a shape this card knows."""
    declaration = dict(
        _PAYLOADS["review_kind"]["declaration"],
        presentation={
            "label": "Contratos",
            "icon": "C",
            "fields": [
                {"field": "name", "label": "Contrato", "role": "identifier"},
                {"field": "titulo", "label": "Título", "role": "title"},
                {"field": "valor", "label": "Valor", "role": "metric"},
            ],
            "hidden": ["assinado_em"],
        },
    )
    state = C.kind_review_app(declaration).to_json()["state"]
    assert state["has_presentation"] is True
    assert [r["label"] for r in state["presentation_rows"]] == [
        "Contrato", "Título", "Valor",
    ]
    assert [r["role"] for r in state["presentation_rows"]] == [
        "identifier", "title", "metric",
    ]
    assert state["presentation_label"] == "Contratos"
    assert state["presentation_hidden"] == "assinado_em"


def test_the_review_card_does_not_invent_a_presentation_it_does_not_have():
    """Same rule as the schema beside it: ``None`` is a fact, and an empty
    field table would read as "this Kind declares nothing about how it reads",
    which is a claim the card is not entitled to make silently."""
    state = C.kind_review_app(_PAYLOADS["review_kind"]["declaration"]).to_json()["state"]
    assert state["has_presentation"] is False
    assert state["presentation_rows"] == []
