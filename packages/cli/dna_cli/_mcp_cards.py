"""``dna_cli._mcp_cards`` — the MCP Apps card surface, built on Prefab.

One renderer, one resource, many cards. The read tools that read better as a
picture than as a wall of JSON declare :data:`UI_PREFAB_URI` and return a
:class:`~fastmcp.tools.tool.ToolResult` whose ``structured_content`` carries a
Prefab view alongside the data. A host that renders MCP Apps prefetches the
renderer once and pushes each result into it; every other host reads the same
textual ``content`` as ever.

**Merge, never replace.** FastMCP's ``app=True`` swaps ``content`` for the
placeholder ``"[Rendered Prefab UI]"`` (``fastmcp/tools/base.py``
``_prefab_to_tool_result``). The MCP Apps spec makes ``content`` REQUIRED and
``structuredContent`` OPTIONAL, so that placeholder would blind every agent
that consumes DNA over MCP without rendering. :func:`with_card` therefore
builds the result by hand: ``content`` goes through FastMCP's own converter
from the SAME dict the tool would have returned — byte-identical by
construction, not by careful copying — and the structured payload is a
SUPERSET of the data. The renderer reads only ``$prefab`` / ``view`` / ``defs``
/ ``state`` / ``_meta`` / ``css`` / ``mode`` / ``stylesheets`` / ``keyBindings``
and ignores every other top-level key (verified against the installed
renderer's own source, not its docs), which is what makes a card purely
additive.

**One shared resource.** FastMCP's default synthesises
``ui://prefab/tool/<hash>/renderer.html`` per tool — a separate 6.6 MB
document per card in bundled mode. Every DNA card points ONE URI instead, so
the host prefetches and caches a single renderer no matter how many tools
declare it.

**Bundled, not CDN.** ``prefab_ui.renderer.get_renderer_html()`` defaults to a
stub that loads the renderer from a public CDN. A card that phones out on
render would put a third-party origin in the request path of a tenant's board,
and the MCP Apps CSP is deny-by-default. Bundled mode is self-contained: the
library's own ``get_renderer_csp(mode="bundled")`` declares no origin at all,
which is why the resource is registered with no CSP to declare.

One caveat, measured rather than assumed: the bundled document still CONTAINS
a jsDelivr URL for Pyodide, reached only by the generative path the renderer
enters on ``ontoolinputpartial``. No tool here streams a partial input, so that
path is never entered and the string is inert — which is also why the resource
declares the base CSP and not ``get_generative_renderer_csp``'s. Grepping the
document for a CDN hostname therefore proves nothing either way; the test asks
the question structurally instead.

**One card acts, and it is the approval one.** Every other card here is a
mirror. :func:`kind_review_app` carries a single button that calls
:data:`APPROVE_TOOL` — the act that confers effect — and it ships now because
the thing that was missing when these cards were written exists: revocation
(i-085). A grant you cannot take back is the one that must not be one click
away; an undoable one may be.

**The trust boundary, stated where it is easy to mistake for a mechanism.**
The approval tool is declared ``visibility: ["app"]`` (MCP Apps, SEP-1865), and
the spec is explicit that a host MUST NOT put a tool in the model's tool list
when its visibility omits ``"model"``. It is equally explicit that **the server
cannot tell a UI-initiated ``tools/call`` from a model-initiated one** — the
call arrives on the same transport, with the same token, carrying nothing that
says which one pressed. So ``visibility`` is a declaration we make and the HOST
enforces. It is not our fence, and nothing here can make it one. What we can do
we do: the declaration is exact, a client that tells us it cannot render MCP
Apps is not offered the tool at all (``_mcp_server._ui_capability_middleware``),
and the act is reversible. The residual — an incomplete host that ignores
``visibility`` — is a third party's bug that our tests cannot catch, and saying
so here is worth more than a comment that implies a guarantee.

**The host's theme, with a fallback on every reference.** See
:func:`host_theme_css`.
"""
from __future__ import annotations

from functools import cache
from typing import Any

from dna.emit.mcp_ui import MCP_APP_MIME as MCP_APP_MIME

__all__ = [
    "UI_PREFAB_URI",
    "MCP_APP_MIME",
    "APPROVE_TOOL",
    "HOST_TOKENS",
    "host_theme_css",
    "prefab_renderer_html",
    "with_card",
    "stories_app",
    "digest_app",
    "kinds_app",
    "kind_review_app",
]

#: The ONE ``ui://`` resource every Prefab card in this face points at. Stable —
#: hosts key their prefetch/render cache on it, and sharing it is the difference
#: between one cached renderer and one per tool.
UI_PREFAB_URI = "ui://dna/prefab"

#: The tool the review card's button calls — the ONLY action wired anywhere on
#: this surface. Named here rather than spelled inline so the test that proves
#: the target is registered ``visibility: ["app"]`` has one string to follow,
#: and so a button pointed at a model-visible tool cannot be introduced by a
#: typo that merely fails to render.
APPROVE_TOOL = "approve_kind"

#: The host design tokens this surface reads, in the host's own vocabulary
#: (the MCP Apps host-context ``styles.variables`` names). Named here so the
#: test that proves each one carries a fallback has something to enumerate,
#: and so a token invented by us cannot slip in unnoticed.
HOST_TOKENS = (
    "--color-background-primary",
    "--color-background-secondary",
    "--color-background-tertiary",
    "--color-text-primary",
    "--color-text-secondary",
    "--color-text-danger",
    "--color-text-warning",
    "--color-text-success",
    "--color-text-info",
    "--color-border-primary",
    "--color-border-secondary",
    "--font-sans",
    "--font-mono",
    "--font-text-xs-size",
    "--font-text-sm-size",
    "--font-weight-bold",
    "--border-radius-lg",
)


# ── the host's theme, and the fallback that makes it optional ──────────────
#
# An MCP Apps host injects its design tokens into the app iframe as CSS custom
# properties and changes their VALUES when the user switches theme. The Prefab
# renderer paints from its own (shadcn-shaped) base variables — `--background`,
# `--foreground`, `--card`, `--border`, `--destructive`… — and does NOT read the
# host vocabulary. This stylesheet is the bridge: each base variable is
# redeclared as a read of the host token that means the same thing.
#
# EVERY reference carries its own fallback, because the guidance is explicit
# that all the variables are optional and a host may provide any subset. A card
# that only looks right when every token exists is not portable, it is lucky in
# the host it happened to be built against.
#
# The NEUTRAL fallbacks are the UA's own system colours (`Canvas` / `CanvasText`
# — a contrasting pair by definition) plus `color-mix()` toward the ink for the
# derived muted/hairline values, exactly as `dna.emit.mcp_ui`'s memory card does
# them. `color-scheme:light dark` is declared so those system colours follow the
# user's preference, and the renderer's own `colorScheme` assignment when a host
# declares a theme without variables.
#
# The SEMANTIC hues cannot use that recipe. A badge paints its label in the hue
# AND its ground in a 10% tint of the same hue (20% in dark mode), so one mixing
# ratio has to clear 4.5:1 against two different tinted grounds; measured, no
# single ratio does it for red/green/blue. `light-dark()` resolves against the
# same `color-scheme` the system colours do, so each mode gets its own measured
# value. Every pair below clears AA on the plain ground AND on the tint, in both
# modes — the SDLC amber `#e0a838` does not (2.14:1 on white), which is why the
# warning fallback is a darker gold on light and a lighter one on dark.
#
# `:root:root` rather than `:root`: the renderer declares its base variables in
# `:root` / `.dark`, and the theme bridge has to win over both. Doubling the
# pseudo-class raises specificity above `.dark` without `!important`, and the
# rule is unlayered, so it also outranks anything the renderer puts in a
# cascade layer.
#
# NOT declared here, deliberately: `--font-sans`, `--font-mono`,
# `--font-weight-*`. Those host token names collide EXACTLY with the renderer's
# Tailwind theme names, so the host's inline declaration on the document element
# already outranks the renderer's layered one — redeclaring them as
# `var(--font-sans, …)` would be a self-reference, which is a cycle, which makes
# the whole declaration invalid. `--default-font-family` is the seam that reads
# them without the cycle.

_BG = "var(--color-background-primary,Canvas)"
_BG_RAISED = "var(--color-background-secondary,Canvas)"
_BG_SUBTLE = "var(--color-background-tertiary,color-mix(in srgb,CanvasText 6%,Canvas))"
_FG = "var(--color-text-primary,CanvasText)"
_FG_MUTED = "var(--color-text-secondary,color-mix(in srgb,CanvasText 68%,Canvas))"
_BORDER = "var(--color-border-primary,color-mix(in srgb,CanvasText 22%,Canvas))"
_RING = "var(--color-border-secondary,color-mix(in srgb,CanvasText 40%,Canvas))"

#: Semantic hues: (host token, light fallback, dark fallback). Measured against
#: the plain ground and the badge tint in both modes — see the module note.
_DANGER = "var(--color-text-danger,light-dark(#9d2622,#f0a6a3))"
_WARNING = "var(--color-text-warning,light-dark(#785707,#d1b060))"
_SUCCESS = "var(--color-text-success,light-dark(#166135,#8fc5a6))"
_INFO = "var(--color-text-info,light-dark(#1f4887,#a1beea))"

_FONT = (
    "var(--font-sans,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',"
    "Roboto,Helvetica,Arial,sans-serif)"
)
_FONT_MONO = "var(--font-mono,ui-monospace,SFMono-Regular,Menlo,monospace)"

# The one brand colour a card keeps. A host themes its own surfaces and has no
# opinion about an accent, so this is where the DNA identity lives. Mixed toward
# the host's own ink so it darkens on a light ground and lightens on a dark one:
# measured 6.38:1 on white and 5.50:1 on a #1a1a1a ground, against 4.46:1 for
# the raw teal on white (below AA).
_ACCENT = f"color-mix(in srgb,#2f8570 80%,{_FG})"

_THEME_CSS = (
    ":root:root{"
    "color-scheme:light dark;"
    f"--background:{_BG};"
    f"--foreground:{_FG};"
    f"--card:{_BG_RAISED};"
    f"--card-foreground:{_FG};"
    f"--popover:{_BG_RAISED};"
    f"--popover-foreground:{_FG};"
    f"--muted:{_BG_SUBTLE};"
    f"--muted-foreground:{_FG_MUTED};"
    f"--accent:{_BG_SUBTLE};"
    f"--accent-foreground:{_FG};"
    f"--secondary:{_BG_SUBTLE};"
    f"--secondary-foreground:{_FG};"
    f"--primary:{_FG};"
    f"--primary-foreground:{_BG};"
    f"--border:{_BORDER};"
    f"--input:{_BORDER};"
    f"--ring:{_RING};"
    f"--destructive:{_DANGER};"
    f"--warning:{_WARNING};"
    f"--success:{_SUCCESS};"
    f"--info:{_INFO};"
    "--radius:var(--border-radius-lg,.625rem);"
    "--text-xs:var(--font-text-xs-size,.75rem);"
    "--text-sm:var(--font-text-sm-size,.875rem);"
    f"--default-font-family:{_FONT};"
    f"--default-mono-font-family:{_FONT_MONO}"
    "}"
    ".pf-app-root{padding:0}"
    f".dna-mark{{color:{_ACCENT};letter-spacing:.14em;"
    "font-weight:var(--font-weight-bold,700)}"
)


def host_theme_css() -> str:
    """The stylesheet that makes a Prefab card wear the HOST's theme.

    Redeclares the renderer's own base variables as reads of the host's design
    tokens, every one with a fallback — a host may provide any subset, and a
    card that needs all of them is not portable. Served inside the shared
    renderer resource (see :func:`prefab_renderer_html`) rather than shipped in
    every tool result: the resource is fetched once and cached by URI, so the
    theme costs nothing per call and there is no unthemed first paint."""
    return _THEME_CSS


# ── the shared renderer resource ───────────────────────────────────────────


@cache
def prefab_renderer_html() -> str:
    """The ONE renderer document served at :data:`UI_PREFAB_URI`.

    Prefab's bundled single-file renderer with :func:`host_theme_css` appended
    into its ``<head>`` — the last stylesheet in the document, so the bridge
    wins the cascade without touching the vendored bundle's bytes.

    Bundled, never CDN: self-contained means the served resource declares no
    external origin at all, which is the only shape that survives the MCP Apps
    deny-by-default CSP without asking the host to trust a third-party host."""
    from prefab_ui.renderer import get_renderer_html

    html = get_renderer_html(mode="bundled")
    head_close = html.rindex("</head>", 0, html.index("<body"))
    return html[:head_close] + f"<style>{_THEME_CSS}</style>" + html[head_close:]


# ── the merge: content untouched, structured a superset ────────────────────


def with_card(data: dict[str, Any], app: Any) -> Any:
    """Return ``data`` as a tool result that ALSO carries the Prefab card.

    ``content`` is produced by FastMCP's own converter from the very dict the
    tool would otherwise have returned, so a client that renders nothing reads
    byte-identical bytes — the identity holds by construction rather than by a
    hand-written serializer that could drift from FastMCP's.

    ``structured_content`` is ``data`` plus the Prefab wire keys. A key
    collision would silently replace the tool's own field with a rendering
    detail, so it RAISES instead: the wire keys are Prefab's to change, and a
    future one shadowing a DNA field must break loudly here, not quietly on a
    consumer's screen."""
    from fastmcp.tools.tool import ToolResult

    merged = dict(data)
    for key, value in app.to_json().items():
        if key in merged:
            raise ValueError(
                f"the Prefab wire key {key!r} would shadow the tool's own data — "
                "the card must be purely additive"
            )
        merged[key] = value
    return ToolResult(content=data, structured_content=merged)


# ── the cards ──────────────────────────────────────────────────────────────


def _text(value: Any) -> str:
    """A cell the card can print. ``None`` renders as an em dash rather than
    as the string ``"None"`` — the data says "not set", and a card that prints
    a Python repr has invented a value."""
    return "—" if value is None or value == "" else str(value)


def stories_app(data: dict[str, Any]) -> Any:
    """The ``list_stories`` card: the board as a sortable, searchable roster.

    A Story list is a table — name, title, status, feature, priority across N
    rows — and a table is the one shape JSON text reads worst. Status is left
    as plain text rather than a coloured badge: the vocabulary is open (any
    workflow may define its own), so a colour map would either be incomplete
    or invented."""
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import (
        Card,
        CardContent,
        CardDescription,
        CardHeader,
        CardTitle,
        DataTable,
        DataTableColumn,
        Row,
        Text,
    )
    from prefab_ui.components.control_flow import Else, If

    stories = data.get("stories")
    rows = [
        {
            "name": _text(s.get("name")),
            "title": _text(s.get("title")),
            "status": _text(s.get("status")),
            "feature": _text(s.get("feature")),
            "priority": _text(s.get("priority")),
        }
        for s in (stories if isinstance(stories, list) else [])
        if isinstance(s, dict)
    ]
    state = {
        "scope": _text(data.get("scope")),
        "count": len(rows),
        "stories": rows,
    }
    with Card() as view:
        with CardHeader():
            with Row(gap=3, align="center"):
                Text("DNA", css_class="dna-mark")
                CardTitle("Stories")
            CardDescription("{{ count }} in {{ scope }}")
        with CardContent():
            with If("count > 0"):
                DataTable(
                    columns=[
                        DataTableColumn(key="name", header="Story", sortable=True),
                        DataTableColumn(key="title", header="Title"),
                        DataTableColumn(key="status", header="Status", sortable=True),
                        DataTableColumn(key="feature", header="Feature", sortable=True),
                        DataTableColumn(key="priority", header="Priority", sortable=True),
                    ],
                    rows="{{ stories }}",
                    search=True,
                    paginated=True,
                    page_size=10,
                )
            with Else():
                Text(
                    "No Stories in this scope yet — anything the board records "
                    "will appear here.",
                    css_class="text-muted-foreground",
                )
    return PrefabApp(view=view, state=state)


#: RAG → the renderer's badge variant. The digest's own three-value vocabulary
#: (``_digest.build_digest``), mapped ONCE here so the view carries no colour
#: logic: red is a stop, amber is an open question, green is clear.
_RAG_VARIANT = {"red": "destructive", "amber": "warning", "green": "success"}

#: The attention buckets, in the order a delegator should read them, with the
#: field each one puts the reason in. Declared rather than inferred: the buckets
#: are heterogeneous (``reason`` / ``question`` / ``owner``) and a card that
#: guessed would silently drop the one column that says WHY.
_ATTENTION = (
    ("blocked", "Blocked", "reason"),
    ("review_awaiting", "Awaiting review", "owner"),
    ("owner_decisions", "Owner decision", "owner"),
    ("open_questions", "Open question", "question"),
)


def digest_app(data: dict[str, Any]) -> Any:
    """The ``sdlc_digest`` card: the retrospective as a dashboard.

    The digest is the one read on this face that is genuinely dashboard-shaped
    — a RAG verdict, a row of counts, and a list of things needing a person —
    and all three are buried in a deeply nested JSON object that a reader has
    to reassemble in their head.

    The card SUMMARISES; it does not replace. The full buckets (every completed
    item, every decision, every artifact) stay in ``content``, which the same
    result carries unchanged, so nothing is lost by rendering less."""
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import (
        Badge,
        Card,
        CardContent,
        CardDescription,
        CardHeader,
        CardTitle,
        DataTable,
        DataTableColumn,
        Grid,
        Metric,
        Row,
        Text,
    )
    from prefab_ui.components.control_flow import If

    counts = data.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    attention = data.get("attention")
    attention = attention if isinstance(attention, dict) else {}

    rows: list[dict[str, str]] = []
    for bucket, label, why in _ATTENTION:
        for item in attention.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "bucket": label,
                    "item": " ".join(
                        p for p in (item.get("kind"), item.get("name")) if p
                    )
                    or "—",
                    "title": _text(item.get("title")),
                    "why": _text(item.get(why)),
                }
            )

    unreadable = ((data.get("sources") or {}) if isinstance(data.get("sources"), dict)
                  else {}).get("unreadable") or []
    rag = _text(data.get("rag_status"))
    state = {
        "scope": _text(data.get("scope")),
        "since_label": _text(data.get("since_label")),
        "verdict": _text(data.get("verdict")),
        "rag": rag,
        "rag_variant": _RAG_VARIANT.get(rag, "secondary"),
        "completed": int(counts.get("completed") or 0),
        "decided": int(counts.get("decided") or 0),
        "found": int(counts.get("found") or 0),
        "attention_count": len(rows),
        "attention_rows": rows,
        "partial": bool(data.get("partial")),
        # The coverage sentence, composed here so the view holds no grammar.
        "partial_note": (
            f"{len(unreadable)} Kind(s) could not be read, so this digest is "
            "partial — the board it reports on is not the whole board."
        ),
    }

    with Card() as view:
        with CardHeader():
            with Row(gap=3, align="center"):
                Text("DNA", css_class="dna-mark")
                CardTitle("Board digest")
                Badge("{{ rag }}", variant="{{ rag_variant }}")
            CardDescription("{{ scope }} · since {{ since_label }}")
        with CardContent():
            Text("{{ verdict }}")
            with If("partial"):
                Text("{{ partial_note }}", css_class="text-warning")
            with Grid(columns=4, gap=4):
                Metric(label="Completed", value="{{ completed }}")
                Metric(label="Decided", value="{{ decided }}")
                Metric(label="Found", value="{{ found }}")
                Metric(label="Needs attention", value="{{ attention_count }}")
            with If("attention_count > 0"):
                DataTable(
                    columns=[
                        DataTableColumn(key="bucket", header="Needs", sortable=True),
                        DataTableColumn(key="item", header="Item"),
                        DataTableColumn(key="title", header="Title"),
                        DataTableColumn(key="why", header="Why"),
                    ],
                    rows="{{ attention_rows }}",
                )
    return PrefabApp(view=view, state=state)


def _pending_variant(pending: int) -> str:
    """The headline badge's colour. Amber only while something is genuinely
    waiting on a person; a roster with nothing inert is a clean one, and a
    permanent warning colour is a warning nobody reads."""
    return "warning" if pending else "success"


#: The three approval states → the renderer's semantic badge variants. The
#: vocabulary is the core's own (``dna.kernel.kinds.approval``), which is why
#: this map is exhaustive and closed rather than a default-carrying lookup:
#: a fourth state must fail visibly here, not paint itself grey and read as
#: "nothing special".
#:
#: The colours are NOT a gradient from bad to good — they are three different
#: kinds of fact, and the pair that must never look alike is amber/red. An
#: UNAPPROVED Kind is the LOOSEST state in the system (never registered, so its
#: documents are accepted with no validation at all); a REVOKED one is the
#: TIGHTEST (new documents refused, existing ones read back invalid). Rendering
#: both as "not approved" — which the boolean did — reads the loosest and the
#: tightest as the same word.
_STATE_VARIANT = {
    "unapproved": "warning",
    "approved": "success",
    "revoked": "destructive",
}

#: What each state MEANS for documents, in one sentence — the thing a reviewer
#: is actually deciding about. Kept beside the variant map so a new state cannot
#: acquire a colour without acquiring an explanation.
_STATE_MEANING = {
    "unapproved": (
        "Not approved: this Kind is not registered, so documents of it are "
        "accepted with NO schema validation and no storage routing."
    ),
    "approved": (
        "Approved: documents of this Kind are validated against the schema "
        "below and routed as it declares."
    ),
    "revoked": (
        "REVOKED: new documents of this Kind are refused and existing ones "
        "read back invalid. Nothing was deleted, and approving again restores "
        "every one of them."
    ),
}


def _state_of(row: Any) -> str:
    """The row's approval state, taken from the projection and NEVER derived.

    No fallback, deliberately. ``_authored_kind_summary`` always emits
    ``state``, so its absence means the payload did not come from the audit
    projection — and the obvious "fall back to the ``approved`` boolean" would
    make a REVOKED row (``approved: false``) render identically to one that was
    never approved, which is precisely the two-facts-one-word bug this column
    exists to end. An unknown state renders as the em dash: the data did not
    say, and the card must not say for it."""
    state = row.get("state") if isinstance(row, dict) else None
    return state if state in _STATE_VARIANT else ""


def kinds_app(data: dict[str, Any]) -> Any:
    """The ``list_my_kinds`` card: the authoring audit roster.

    ``approved`` is the one fact this route exists to publish — an unapproved
    Kind exists and has NO effect, because registration is what confers schema
    validation and storage routing — and in the text answer it is one boolean
    among ten fields, per row. The card promotes the count still inert to the
    headline and gives the boolean its own column, while keeping both actors
    and both timestamps visible: a reviewer deciding whether to confer effect
    needs to see who proposed it, and when.

    THREE states, not a boolean (i-085). ``approved: false`` collapses the two
    states that behave in OPPOSITE ways — never approved accepts documents
    unvalidated, revoked refuses them and marks the existing ones invalid — so
    the roster renders ``state`` from the projection and counts the revoked rows
    into their own headline badge. A listing surface that shows a revoked Kind
    as merely unapproved under-reports the tightest state in the system as the
    loosest one.

    No approve affordance HERE: this is the roster, and a button on a row is a
    button pressed against a schema the reviewer has not seen. The act lives on
    :func:`kind_review_app`, which shows the schema it would confer effect on —
    the same hole the portal closed in i-076, not reopened on this face."""
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import (
        Badge,
        Card,
        CardContent,
        CardDescription,
        CardHeader,
        CardTitle,
        DataTable,
        DataTableColumn,
        Row,
        Text,
    )
    from prefab_ui.components.control_flow import Else, If

    raw = data.get("kinds")
    rows = [
        {
            "name": _text(k.get("name")),
            "kind": _text(k.get("kind")),
            "api_version": _text(k.get("api_version")),
            "namespace": _text(k.get("namespace")),
            "state": _text(_state_of(k)),
            "proposed_by": _text(k.get("proposed_by")),
            "proposed_at": _text(k.get("proposed_at")),
            "approved_by": _text(k.get("approved_by")),
            "approved_at": _text(k.get("approved_at")),
            "revoked_by": _text(k.get("revoked_by")),
            "revoked_at": _text(k.get("revoked_at")),
        }
        for k in (raw if isinstance(raw, list) else [])
        if isinstance(k, dict)
    ]
    pending = sum(1 for r in rows if r["state"] == "unapproved")
    revoked = sum(1 for r in rows if r["state"] == "revoked")
    state = {
        "scope": _text(data.get("scope")),
        "count": len(rows),
        "pending": pending,
        "pending_label": (
            f"{pending} awaiting approval" if pending else "none awaiting approval"
        ),
        "pending_variant": _pending_variant(pending),
        # The revoked count gets its OWN badge rather than sharing the amber
        # one. Two facts in one counter would be the boolean's mistake again,
        # one level up: "3 not approved" is true of a roster where one Kind is
        # refusing every write and two are accepting anything.
        "revoked": revoked,
        "revoked_label": f"{revoked} revoked",
        "kinds": rows,
    }
    with Card() as view:
        with CardHeader():
            with Row(gap=3, align="center"):
                Text("DNA", css_class="dna-mark")
                CardTitle("Kinds you have authored")
                Badge("{{ pending_label }}", variant="{{ pending_variant }}")
                with If("revoked > 0"):
                    Badge("{{ revoked_label }}", variant="destructive")
            CardDescription(
                "{{ count }} in {{ scope }} · a Kind awaiting approval exists "
                "and has no effect yet; a revoked one refuses new documents"
            )
        with CardContent():
            with If("count > 0"):
                DataTable(
                    columns=[
                        DataTableColumn(key="name", header="Document", sortable=True),
                        DataTableColumn(key="kind", header="Kind", sortable=True),
                        DataTableColumn(key="api_version", header="apiVersion"),
                        DataTableColumn(key="namespace", header="Namespace", sortable=True),
                        DataTableColumn(key="state", header="State", sortable=True),
                        DataTableColumn(key="proposed_by", header="Proposed by"),
                        DataTableColumn(key="proposed_at", header="Proposed at", sortable=True),
                        DataTableColumn(key="approved_by", header="Approved by"),
                        DataTableColumn(key="approved_at", header="Approved at", sortable=True),
                        DataTableColumn(key="revoked_by", header="Revoked by"),
                        DataTableColumn(key="revoked_at", header="Revoked at", sortable=True),
                    ],
                    rows="{{ kinds }}",
                    search=True,
                    paginated=True,
                    page_size=10,
                )
            with Else():
                Text(
                    "Your workspace has authored no Kinds yet — author one and "
                    "it will appear here, inert, until a human approves it.",
                    css_class="text-muted-foreground",
                )
    return PrefabApp(view=view, state=state)


def kind_review_app(data: dict[str, Any]) -> Any:
    """The ``review_kind`` card: ONE authored Kind, with the act attached.

    This is the surface the whole feature exists for. A workspace has more than
    one person: the author's agent proposes a Kind, and the person who has to
    confer effect on it wants to answer "what is there to approve?" where she
    already is. So the card shows what she is deciding about — the SCHEMA, both
    actors, and what the current state means for documents — and carries the
    button that decides it.

    **The schema is not optional decoration.** A roster inlining every JSON
    Schema is unreadable, which is why the listing omits it; but approving what
    you cannot see is not approving, and it is exactly the hole the portal
    closed (i-076). A button without the schema beside it would reopen it here.

    **The button is app-only.** It calls :data:`APPROVE_TOOL`, which is declared
    ``visibility: ["app"]`` so a conforming host never offers it to the model —
    see the module docstring for what that does and does not guarantee. It is
    shown only while the Kind is NOT currently in effect: on an approved Kind
    there is nothing to confer, and a live button that re-stamps the approver
    invites a click that means nothing.

    On a REVOKED Kind the button is shown and says so. Approving again is the
    documented one-act undo — it clears the revocation and every existing
    document is valid again — and hiding it would leave the reviewer looking
    for a route that does not exist on this face."""
    import json

    from prefab_ui.actions import CallTool, ShowToast
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import (
        Badge,
        Button,
        Card,
        CardContent,
        CardDescription,
        CardFooter,
        CardHeader,
        CardTitle,
        Code,
        Row,
        Text,
    )
    from prefab_ui.components.control_flow import Else, If

    current = _state_of(data)
    schema = data.get("schema")
    traits = data.get("traits")
    traits = [str(t) for t in traits] if isinstance(traits, list) else []
    state = {
        "kind": _text(data.get("kind")),
        "name": _text(data.get("name")),
        "api_version": _text(data.get("api_version")),
        "namespace": _text(data.get("namespace")),
        "state": _text(current),
        "state_variant": _STATE_VARIANT.get(current, "secondary"),
        "meaning": _STATE_MEANING.get(
            current,
            "This Kind's approval state could not be read, so what it does to "
            "documents is unknown — do not act on this card.",
        ),
        # Pretty-printed HERE so the view holds no formatting logic and a host
        # that renders nothing still reads the same schema in `content`.
        # `ensure_ascii=False` because a tenant's own field names are routinely
        # not ASCII and `á` is not a schema anyone can review.
        "schema": (
            json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True)
            if isinstance(schema, dict) else ""
        ),
        # "There is no schema" and "the schema is {}" are different facts; the
        # projection already distinguishes them (None vs a dict) and the card
        # must not flatten them into an empty code block.
        "has_schema": isinstance(schema, dict),
        "traits": ", ".join(traits) if traits else "—",
        "proposed": f"{_text(data.get('proposed_by'))} · {_text(data.get('proposed_at'))}",
        "approved": f"{_text(data.get('approved_by'))} · {_text(data.get('approved_at'))}",
        "revoked": f"{_text(data.get('revoked_by'))} · {_text(data.get('revoked_at'))}",
        "was_approved": bool(data.get("approved_by")),
        "was_revoked": current == "revoked",
        # The act is offered exactly when it would change something.
        "can_approve": current in ("unapproved", "revoked"),
        "approve_label": (
            "Approve again — restore this Kind" if current == "revoked"
            else "Approve — put this Kind into effect"
        ),
    }

    with Card() as view:
        with CardHeader():
            with Row(gap=3, align="center"):
                Text("DNA", css_class="dna-mark")
                CardTitle("{{ kind }}")
                Badge("{{ state }}", variant="{{ state_variant }}")
            CardDescription("{{ api_version }} · namespace {{ namespace }} · {{ name }}")
        with CardContent():
            Text("{{ meaning }}")
            Text("Proposed by {{ proposed }}", css_class="text-muted-foreground")
            with If("was_approved"):
                Text("Approved by {{ approved }}", css_class="text-muted-foreground")
            with If("was_revoked"):
                Text("Revoked by {{ revoked }}", css_class="text-muted-foreground")
            Text("Traits: {{ traits }}", css_class="text-muted-foreground")
            with If("has_schema"):
                Code("{{ schema }}", language="json")
            with Else():
                Text(
                    "This declaration stores no schema — approving it would "
                    "confer effect on a shape nobody can read.",
                    css_class="text-destructive",
                )
        with If("can_approve"):
            with CardFooter():
                Button(
                    "{{ approve_label }}",
                    on_click=CallTool(
                        APPROVE_TOOL,
                        # ONLY the Kind. The workspace is resolved server-side
                        # from the verified identity of the connection, exactly
                        # as every other tool on this face resolves it — a
                        # tenant a card can name is not a tenant — and the
                        # approver is likewise never an argument.
                        arguments={"kind": "{{ kind }}"},
                        on_success=ShowToast(
                            "Approved — {{ kind }} is now in effect",
                            variant="success",
                        ),
                        on_error=ShowToast(
                            "{{ kind }} was NOT approved",
                            variant="error",
                        ),
                    ),
                )
    return PrefabApp(view=view, state=state)
