"""DNA → **MCP Apps** memory-card surface (SEP-1865, standalone golden family).

A standalone UI-emit surface, alongside the AG-UI backend emitters and the
CopilotKit ``frontend.py`` console — like ``frontend.py`` it is NOT a
registered ``EmitterPort``: it carries no byte-equal ``build_prompt``
instruction and is governed by its own byte-stable golden renders. Everything
here is a pure function of its inputs, so every render is byte-golden.

One render lives here — the memory card's single delivery channel:

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

The card wears the HOST's theme, never its own. Colour, type and shape read
the host's injected design tokens, whose values change when the user switches
theme; every reference carries a fallback because a host may provide any
subset of them. The DNA identity survives as the accent only — a card that
paints its own ground and ink inside someone else's chat reads as an
advertisement rather than as part of the product.
"""
from __future__ import annotations

from functools import cache
from importlib import resources

__all__ = [
    "UI_MEMORY_LIST_URI",
    "UI_KIND_DRAFT_URI",
    "MCP_APP_MIME",
    "HOST_DESIGN_TOKENS",
    "memory_list_card_html",
    "kind_draft_card_html",
]

#: The ``ui://`` scheme resource id for the memory-list card template. Stable —
#: hosts key their prefetch/render cache on it.
UI_MEMORY_LIST_URI = "ui://dna/memory-list"

#: O card INTERATIVO de Kind autorado (Kind Studio F3) — o primeiro MCP App
#: bidirecional próprio: renderiza o schema como linhas editáveis e reautora
#: via ``callServerTool`` (a aprovação continua humana, no portal).
UI_KIND_DRAFT_URI = "ui://dna/kind-draft"

#: The MCP Apps profile mimeType (SEP-1865) the ``ui://dna/memory-list``
#: resource is served with — what marks it a first-class MCP App template, not
#: a bare HTML blob.
MCP_APP_MIME = "text/html;profile=mcp-app"

#: EVERY design token an MCP Apps host may inject, and the ONLY names a card
#: may read — the ``styleVariables`` key union, transcribed from the
#: ``@modelcontextprotocol/ext-apps`` lib vendored in this package
#: (``_vendor/ext-apps.iife.js``), where it is declared as *"CSS variable keys
#: available to MCP apps for theming"*. Committed as data rather than parsed at
#: import time — a regex over 374 KB on every import to produce a constant is a
#: cost with no reader — and held to the vendored lib by
#: ``tests/test_emit_mcp_ui.py::test_the_host_token_vocabulary_matches_the_vendored_lib``,
#: so a vendor bump that changes the vocabulary fails the build instead of
#: silently blessing a name no host sets.
#:
#: This list exists because a name that merely LOOKS like a host token is
#: indistinguishable from one at a glance, and the failure is silent: the card
#: reads it, no host provides it, the fallback applies forever, and the card
#: quietly ignores that part of the host's theme. That is not hypothetical —
#: ``--text-sm``/``--text-xs`` shipped here and did exactly that; the real names
#: are ``--font-text-sm-size``/``--font-text-xs-size``.
#:
#: Declaration order is the lib's own (grouped by family), so a drift diff reads
#: as a change to a family rather than as an alphabetical reshuffle.
HOST_DESIGN_TOKENS: tuple[str, ...] = (
    "--color-background-primary",
    "--color-background-secondary",
    "--color-background-tertiary",
    "--color-background-inverse",
    "--color-background-ghost",
    "--color-background-info",
    "--color-background-danger",
    "--color-background-success",
    "--color-background-warning",
    "--color-background-disabled",
    "--color-text-primary",
    "--color-text-secondary",
    "--color-text-tertiary",
    "--color-text-inverse",
    "--color-text-ghost",
    "--color-text-info",
    "--color-text-danger",
    "--color-text-success",
    "--color-text-warning",
    "--color-text-disabled",
    "--color-border-primary",
    "--color-border-secondary",
    "--color-border-tertiary",
    "--color-border-inverse",
    "--color-border-ghost",
    "--color-border-info",
    "--color-border-danger",
    "--color-border-success",
    "--color-border-warning",
    "--color-border-disabled",
    "--color-ring-primary",
    "--color-ring-secondary",
    "--color-ring-inverse",
    "--color-ring-info",
    "--color-ring-danger",
    "--color-ring-success",
    "--color-ring-warning",
    "--font-sans",
    "--font-mono",
    "--font-weight-normal",
    "--font-weight-medium",
    "--font-weight-semibold",
    "--font-weight-bold",
    "--font-text-xs-size",
    "--font-text-sm-size",
    "--font-text-md-size",
    "--font-text-lg-size",
    "--font-heading-xs-size",
    "--font-heading-sm-size",
    "--font-heading-md-size",
    "--font-heading-lg-size",
    "--font-heading-xl-size",
    "--font-heading-2xl-size",
    "--font-heading-3xl-size",
    "--font-text-xs-line-height",
    "--font-text-sm-line-height",
    "--font-text-md-line-height",
    "--font-text-lg-line-height",
    "--font-heading-xs-line-height",
    "--font-heading-sm-line-height",
    "--font-heading-md-line-height",
    "--font-heading-lg-line-height",
    "--font-heading-xl-line-height",
    "--font-heading-2xl-line-height",
    "--font-heading-3xl-line-height",
    "--border-radius-xs",
    "--border-radius-sm",
    "--border-radius-md",
    "--border-radius-lg",
    "--border-radius-xl",
    "--border-radius-full",
    "--border-width-regular",
    "--shadow-hairline",
    "--shadow-sm",
    "--shadow-md",
    "--shadow-lg",
)


# ── the host's design tokens, every one of them optional ───────────────────
#
# An MCP Apps host injects a design-token system into the app iframe as CSS
# custom properties, and changes their VALUES when the user switches theme —
# so the card is themed by reading them, not by declaring a theme of its own.
# There is no media query and no data attribute to watch here; the values
# simply change underneath us.
#
# EVERY reference carries its own fallback, because a host may provide any
# subset of the vocabulary: a card that only looks right when all the tokens
# exist is not portable, it is merely lucky in the host it was built against.
# The fallbacks are the UA's own system colours (`Canvas` / `CanvasText`),
# which are a contrasting pair by definition and follow the user's light/dark
# preference through the `color-scheme` declared on `:root` below.
#
# And every NAME is checked against `HOST_DESIGN_TOKENS` above, because a
# fallback makes a wrong name INVISIBLE: the card reads a property no host
# sets, the fallback applies in every host forever, and nothing looks broken.
# The type scale shipped that way — `--text-sm`/`--text-xs` are Tailwind's
# names, not MCP Apps', so the card pinned 14px/12px while advertising that it
# followed the host. The real names are `--font-text-sm-size`/`-xs-size`.

#: Ground, raised ground, ink, muted ink, hairline — the host's business.
_BG = "var(--color-background-primary, Canvas)"
_BG_RAISED = "var(--color-background-secondary, Canvas)"
_FG = "var(--color-text-primary, CanvasText)"
_FG_MUTED = "var(--color-text-secondary, color-mix(in srgb, CanvasText 68%, Canvas))"
_BORDER = "var(--color-border-primary, color-mix(in srgb, CanvasText 22%, Canvas))"

#: Type, weight and shape — same rule, same fallbacks.
_FONT = (
    "var(--font-sans, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', "
    "Roboto, Helvetica, Arial, sans-serif)"
)
_TEXT_SM = "var(--font-text-sm-size, 14px)"
_TEXT_XS = "var(--font-text-xs-size, 12px)"
_WEIGHT_SEMIBOLD = "var(--font-weight-semibold, 600)"
_WEIGHT_BOLD = "var(--font-weight-bold, 700)"
_RADIUS = "var(--border-radius-lg, 14px)"
_RADIUS_FULL = "var(--border-radius-full, 999px)"

# The ONE brand colour the card keeps: the genome teal, on the wordmark and the
# tag chips. A host themes its own surfaces and has no opinion about an accent,
# so this is where the DNA identity lives now. It is mixed toward the host's
# own ink so it darkens on a light ground and lightens on a dark one — at 80%
# it stays unmistakably teal and clears 4.5:1 either way (measured: 6.4:1 on a
# white ground, 5.7:1 on a near-black one). The chip's fill and edge are the
# same teal at low alpha, which composites correctly over any ground.
_ACCENT = f"color-mix(in srgb, #2f8570 80%, {_FG})"
_ACCENT_FILL = "rgba(47,133,112,.12)"
_ACCENT_EDGE = "rgba(47,133,112,.35)"

# Sentinels delimiting the vendored third-party lib inside the template — the
# §3 grep-guard and the no-external-URL test treat the region between them as
# the committed vendor asset (byte-equal), and everything outside as the
# surface DNA wrote.
_EXT_APPS_BEGIN = "/*! begin vendored @modelcontextprotocol/ext-apps */"
_EXT_APPS_END = "/*! end vendored @modelcontextprotocol/ext-apps */"


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


# The card's stylesheet, inlined into the template. Colour, type and shape all
# read the host's tokens; only the accent is ours. Borders are declared as a
# separate `border-color` after the shorthand so that a host token AND its
# fallback both failing leaves a visible hairline (`currentColor`) rather than
# no border at all.
_CARD_CSS = (
    ":root{color-scheme:light dark}"
    "*{box-sizing:border-box;margin:0;padding:0}"
    f"body{{font-family:{_FONT};font-size:{_TEXT_SM};line-height:1.5;"
    f"background:{_BG};color:{_FG};padding:16px}}"
    f".dna-card{{max-width:640px;margin:0 auto;background:{_BG_RAISED};"
    f"border:1px solid;border-color:{_BORDER};border-radius:{_RADIUS};"
    "overflow:hidden}"
    ".dna-head{display:flex;align-items:center;gap:10px;padding:14px 18px;"
    f"border-bottom:1px solid;border-bottom-color:{_BORDER}}}"
    f".dna-mark{{font-weight:{_WEIGHT_BOLD};letter-spacing:.14em;color:{_ACCENT}}}"
    f".dna-htitle{{font-weight:{_WEIGHT_SEMIBOLD}}}"
    f".dna-scope{{margin-left:auto;font-size:{_TEXT_XS};color:{_FG_MUTED};"
    f"border:1px solid;border-color:{_BORDER};padding:2px 8px;"
    f"border-radius:{_RADIUS_FULL}}}"
    ".dna-list{list-style:none}"
    f".dna-item{{padding:14px 18px;border-bottom:1px solid;"
    f"border-bottom-color:{_BORDER}}}"
    ".dna-item:last-child{border-bottom:0}"
    f".dna-summary{{font-weight:{_WEIGHT_SEMIBOLD};color:{_FG}}}"
    ".dna-meta{display:flex;flex-wrap:wrap;gap:10px;margin-top:5px;"
    f"font-size:{_TEXT_XS};color:{_FG_MUTED}}}"
    ".dna-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}"
    f".dna-tag{{font-size:{_TEXT_XS};color:{_ACCENT};background:{_ACCENT_FILL};"
    f"border:1px solid;border-color:{_ACCENT_EDGE};padding:2px 8px;"
    f"border-radius:{_RADIUS_FULL}}}"
    f".dna-empty{{padding:22px 18px;color:{_FG_MUTED}}}"
    f".dna-foot{{padding:12px 18px;font-size:{_TEXT_XS};color:{_FG_MUTED};"
    f"border-top:1px solid;border-top-color:{_BORDER}}}"
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

_KIND_CARD_JS = """
(function () {
  var App = (globalThis.DnaExtApps || {}).App;
  if (!App) return;
  var body = document.getElementById("dna-body");
  var note = document.getElementById("dna-note");
  var TYPES = ["string", "integer", "number", "boolean", "array", "date"];
  var state = null; // {kind, fields:[{name,type,required,description}]}
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function typeOf(frag) {
    frag = frag || {};
    if (frag.type === "string" && frag.format === "date") return "date";
    return TYPES.indexOf(frag.type) >= 0 ? frag.type : "string";
  }
  function fromResult(data) {
    data = data || {};
    var schema = data.schema || {};
    var props = schema.properties || {};
    var req = schema.required || [];
    var fields = Object.keys(props).map(function (n) {
      return {
        name: n,
        type: typeOf(props[n]),
        required: req.indexOf(n) >= 0,
        description: (props[n] || {}).description || "",
      };
    });
    return { kind: data.kind || "", fields: fields };
  }
  function toSchema(st) {
    var properties = {};
    var required = [];
    st.fields.forEach(function (f) {
      var frag = { description: f.description };
      if (f.type === "date") { frag.type = "string"; frag.format = "date"; }
      else if (f.type === "array") { frag.type = "array"; frag.items = { type: "string" }; }
      else frag.type = f.type;
      properties[f.name] = frag;
      if (f.required) required.push(f.name);
    });
    var schema = { type: "object", properties: properties };
    if (required.length) schema.required = required.sort();
    return schema;
  }
  function render() {
    if (!state || !state.kind) {
      body.innerHTML = '<p class="dna-empty">Waiting for the authored Kind…</p>';
      return;
    }
    var rows = state.fields.map(function (f, i) {
      var opts = TYPES.map(function (t) {
        return '<option value="' + t + '"' + (t === f.type ? " selected" : "") + ">" + t + "</option>";
      }).join("");
      return (
        '<div class="dna-krow" data-i="' + i + '">' +
        '<code>' + esc(f.name) + "</code>" +
        '<select data-k="type" aria-label="type of ' + esc(f.name) + '">' + opts + "</select>" +
        '<label><input type="checkbox" data-k="required"' + (f.required ? " checked" : "") + ">req</label>" +
        '<input type="text" data-k="description" value="' + esc(f.description) + '" aria-label="description of ' + esc(f.name) + '">' +
        "</div>"
      );
    }).join("");
    body.innerHTML =
      '<p class="dna-ktitle">Kind <b>' + esc(state.kind) + "</b> — awaiting human approval in the portal</p>" +
      '<div class="dna-krows">' + rows + "</div>" +
      '<button id="dna-reauthor" class="dna-kbtn">Re-author with these edits</button>';
    body.querySelectorAll(".dna-krow").forEach(function (row) {
      var i = Number(row.getAttribute("data-i"));
      row.querySelectorAll("[data-k]").forEach(function (el) {
        el.addEventListener("change", function () {
          var k = el.getAttribute("data-k");
          if (k === "required") state.fields[i].required = el.checked;
          else state.fields[i][k] = el.value;
        });
      });
    });
    var btn = document.getElementById("dna-reauthor");
    btn.addEventListener("click", function () {
      btn.disabled = true;
      note.textContent = "Re-authoring…";
      app
        .callServerTool({ name: "author_kind", arguments: { kind: state.kind, schema: toSchema(state) } })
        .then(function () {
          note.textContent = "Re-authored — still awaiting human approval in the portal.";
        })
        .catch(function (e) {
          note.textContent = "Refused: " + String((e && e.message) || e).slice(0, 200);
        })
        .then(function () { btn.disabled = false; });
    });
  }
  function dataOf(result) {
    if (result && typeof result.structuredContent === "object") return result.structuredContent;
    if (result && typeof result.structured_content === "object") return result.structured_content;
    return result || {};
  }
  var app = new App({ name: "dna-kind-draft", version: "1" });
  app.ontoolresult = function (result) {
    state = fromResult(dataOf(result));
    note.textContent = "";
    render();
  };
  app.connect();
  render();
})();
"""


@cache
def kind_draft_card_html() -> str:
    """O template MCP Apps do Kind autorado (Kind Studio F3) — estático,
    público, sem dado embutido, MESMOS sentinelas da lib vendorada.

    INTERATIVO, e o primeiro: o host empurra o resultado de ``author_kind``
    (que ecoa o ``schema``), o card renderiza linhas editáveis
    (nome/tipo/obrigatório/descrição) e reautora via ``callServerTool`` —
    a instância continua INERTE; a aprovação é humana, no portal, e o card
    o diz em toda renderização. Um host sem a extensão ignora a declaração
    e segue lendo o ``content`` textual, byte-idêntico."""
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>DNA · Kind</title><style>"
        + _CARD_CSS
        + ".dna-krow{display:grid;grid-template-columns:minmax(6rem,.8fr) auto auto 1.4fr;"
        "gap:.45rem;align-items:center;padding:.3rem 0}"
        ".dna-krow code{font-size:.8rem;overflow:hidden;text-overflow:ellipsis}"
        ".dna-krow select,.dna-krow input[type=text]{font:inherit;font-size:.78rem;"
        "min-width:0;padding:.15rem .35rem}"
        ".dna-krow label{font-size:.72rem;white-space:nowrap}"
        ".dna-ktitle{margin:.1rem 0 .4rem}"
        ".dna-kbtn{margin-top:.55rem;font:inherit;font-size:.8rem;font-weight:600;"
        "padding:.3rem .7rem;cursor:pointer}"
        "</style></head><body>"
        '<div class="dna-card">'
        '<div class="dna-head"><span class="dna-mark">DNA</span>'
        '<span class="dna-htitle">Kind</span></div>'
        '<div id="dna-body"></div>'
        '<p id="dna-note" class="dna-empty" role="status"></p>'
        '<footer class="dna-foot">authored INERT · a human approves it in '
        "the portal</footer>"
        "</div>"
        "<script>\n"
        + _EXT_APPS_BEGIN
        + "\n"
        + _ext_apps_js()
        + "\n"
        + _EXT_APPS_END
        + "\n</script>"
        "<script>\n" + _KIND_CARD_JS + "</script>"
        "</body></html>"
    )
