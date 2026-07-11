"""Gallery aggregation — the *pure* core of ``dna sdlc gallery``.

``dna sdlc digest`` looks at **events** ("what happened while you were away").
The **gallery** looks at **artifacts** — it is the board-native index of every
``HtmlArtifact`` in a scope, grouped by the status of the work item that
produced it. It answers the delegator's *other* question: "you keep pasting
visual designs/reports into chat and I have to hunt for them — where are the
ones I still need to review?"

This module holds the deterministic, kernel-free aggregation so it can be
unit-tested in isolation: ``build_gallery`` takes already-loaded HtmlArtifact
summaries plus the work-item docs (whose ``produces[]`` / legacy back-refs are
the source of the link) and returns a structured gallery grouped into

    needs_review · decisions · shipped · in_progress · unlinked

The bucket a given artifact lands in is decided by its **producing work item**:

  * ``decisions``    — produced by an ADR (a decision record)
  * ``needs_review`` — produced by a Story in ``review`` (or any work item with
                       an open PR matched to it) — the delegator's queue
  * ``shipped``      — produced by a work item in a terminal status
  * ``in_progress``  — produced by a work item still being worked
  * ``unlinked``     — no work item claims it (an orphan pasted into the board)

The CLI command (``sdlc_cmd.py``) owns only the impure edges: opening a kernel
session to collect the docs, shelling out to ``gh`` for open PRs, rendering the
text panel, and generating the self-contained HTML file.

Py-only by design: the ``dna`` CLI is Python-only (there is no ``dna`` TS
binary), so this aggregator has no TS twin — the parity contract does not apply
to CLI-only surfaces.
"""
from __future__ import annotations

from typing import Any

from dna.extensions.sdlc.work_item_outputs import resolve_work_item_outputs

# ─── status vocabularies ──────────────────────────────────────────────
# Kept in sync with _digest._TERMINAL_TO — a work item in one of these
# states shipped/closed, so its artifacts are "done, for reference".
_TERMINAL_STATUS = {
    "done", "shipped", "resolved", "accepted", "merged", "closed",
    "answered", "cancelled", "wont-fix", "duplicate", "deprecated",
}
# A Story in these states is actively awaiting the delegator's eyes.
_REVIEW_STATUS = {"review"}

# The work-item Kinds whose produces[] we walk to build the reverse index.
# (ADR is included even though it is not in _WORK_ITEM_KINDS for `produces
# add` — an ADR still *produces* the HTML that visualises its decision.)
WORK_ITEM_KINDS = (
    "Story", "Feature", "Epic", "Issue", "Spike",
    "Bug", "Task", "Initiative", "ADR",
)

# Bucket order = render priority. First match wins when an artifact is
# produced by more than one work item (rare; explicit produces[] first).
BUCKET_ORDER = ("needs_review", "decisions", "shipped", "in_progress", "unlinked")

_BUCKET_LABEL = {
    "needs_review": "Precisa de avaliação",
    "decisions": "Decisões",
    "shipped": "Shipado",
    "in_progress": "Em andamento",
    "unlinked": "Sem work item",
}


def _title(spec: dict[str, Any], name: str) -> str:
    return str(spec.get("title") or spec.get("description") or name)[:100]


def _match_prs(name: str, spec: dict[str, Any], open_prs: list[dict] | None) -> list[dict]:
    """Match open PRs to a work item by branch/title/timeline pr_url.

    Mirrors ``_digest._match_prs`` (kept local so the gallery aggregator has no
    dependency on the digest module). Fail-soft: [] when ``open_prs`` is None."""
    if not open_prs:
        return []
    matched: list[dict] = []
    timeline_urls = {
        ev.get("pr_url")
        for ev in (spec.get("timeline") or [])
        if isinstance(ev, dict) and ev.get("pr_url")
    }
    for pr in open_prs:
        url = pr.get("url") or ""
        branch = (pr.get("headRefName") or "").lower()
        title = pr.get("title") or ""
        if (
            (url and url in timeline_urls)
            or (name and name.lower() in branch)
            or (name and name in title)
        ):
            matched.append({
                "number": pr.get("number"),
                "title": title[:70],
                "branch": pr.get("headRefName") or "",
                "url": url,
                "draft": bool(pr.get("isDraft")),
            })
    return matched


def build_reverse_index(work_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map ``HtmlArtifact/<name>`` → the work item that produced it.

    Walks every work item's resolved outputs (``produces[]`` ∪ legacy
    back-refs) and records the producer for each HtmlArtifact. Explicit
    ``produces[]`` wins over legacy; the first producer wins on collision
    (deterministic by input order). Each value carries the producer's
    ``kind``/``name``/``status``/``title`` + the resolver ``source``.
    """
    index: dict[str, dict[str, Any]] = {}
    for wi in work_items:
        kind = wi.get("kind")
        name = wi.get("name")
        spec = wi.get("spec") if isinstance(wi.get("spec"), dict) else {}
        if not isinstance(kind, str) or not isinstance(name, str):
            continue
        outputs = resolve_work_item_outputs(name, spec)
        for o in outputs:
            if o.get("kind") != "HtmlArtifact":
                continue
            art_name = o.get("name")
            if not isinstance(art_name, str) or art_name in index:
                continue
            index[art_name] = {
                "kind": kind,
                "name": name,
                "status": spec.get("status"),
                "title": _title(spec, name),
                "source": o.get("source"),
                "spec": spec,
            }
    return index


def _classify(producer: dict[str, Any] | None, prs: list[dict]) -> str:
    """Which bucket does an artifact land in, given its producer + PRs."""
    if producer is None:
        return "unlinked"
    kind = producer.get("kind")
    status = producer.get("status")
    if kind == "ADR":
        return "decisions"
    if status in _REVIEW_STATUS or prs:
        return "needs_review"
    if status in _TERMINAL_STATUS:
        return "shipped"
    return "in_progress"


def build_gallery(
    *,
    artifacts: list[dict[str, Any]],
    work_items: list[dict[str, Any]],
    scope: str,
    open_prs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate a scope's HtmlArtifacts into a status-grouped gallery.

    ``artifacts``: list of ``{name, title, description, source, published_url,
    html_bytes}`` (already loaded — the summary shape, kernel-free here).
    ``work_items``: list of ``{kind, name, spec}`` whose produces[]/back-refs
    link them to the artifacts.

    Returns::

        {
          "scope": str,
          "counts": {"total", <bucket>: int, ...},
          "buckets": {<bucket>: [ {artifact + work_item + prs} ]},
        }
    """
    index = build_reverse_index(work_items)
    buckets: dict[str, list[dict[str, Any]]] = {b: [] for b in BUCKET_ORDER}

    for art in artifacts:
        art_name = art.get("name")
        producer = index.get(art_name) if isinstance(art_name, str) else None
        prs: list[dict] = []
        if producer is not None:
            prs = _match_prs(producer["name"], producer.get("spec") or {}, open_prs)
        bucket = _classify(producer, prs)
        entry = {
            "name": art_name,
            "title": art.get("title"),
            "description": art.get("description"),
            "source": art.get("source"),
            "published_url": art.get("published_url"),
            "html_bytes": art.get("html_bytes") or 0,
            "work_item": (
                None if producer is None
                else {
                    "kind": producer["kind"],
                    "name": producer["name"],
                    "status": producer.get("status"),
                    "title": producer.get("title"),
                }
            ),
            "prs": prs,
            "bucket": bucket,
        }
        buckets[bucket].append(entry)

    counts = {b: len(buckets[b]) for b in BUCKET_ORDER}
    counts["total"] = sum(counts.values())
    return {"scope": scope, "counts": counts, "buckets": buckets}


def bucket_label(bucket: str) -> str:
    return _BUCKET_LABEL.get(bucket, bucket)


# ─── self-contained HTML panel ────────────────────────────────────────
# A single navigable file the delegator opens — cards per artifact, a status
# chip, the producing work item, and the published link. Self-contained (no
# CDN, no external assets), theme-aware. Same retrospective tese as the digest:
# "delego e reviso" — so the review queue leads.

_BUCKET_ACCENT = {
    "needs_review": "#EA580C",   # DNA orange — the review queue leads
    "decisions": "#7C3AED",      # violet — decisions
    "shipped": "#16A34A",        # green — done
    "in_progress": "#2563EB",    # blue — in flight
    "unlinked": "#6B7280",       # grey — orphan
}
_BUCKET_ICON = {
    "needs_review": "👀", "decisions": "🧭", "shipped": "✅",
    "in_progress": "📈", "unlinked": "📎",
}


def _esc(v: Any) -> str:
    import html as _html
    return _html.escape("" if v is None else str(v), quote=True)


def _render_card(entry: dict[str, Any], accent: str) -> str:
    title = _esc(entry.get("title") or entry.get("name"))
    name = _esc(entry.get("name"))
    desc = entry.get("description")
    wi = entry.get("work_item")
    url = entry.get("published_url")
    kb = round((entry.get("html_bytes") or 0) / 1024, 1)

    wi_html = ""
    if wi:
        wi_html = (
            f'<div class="wi"><span class="wi-kind">{_esc(wi.get("kind"))}</span>'
            f'<span class="wi-name">{_esc(wi.get("name"))}</span>'
            f'<span class="wi-status">{_esc(wi.get("status") or "—")}</span></div>'
        )
    else:
        wi_html = '<div class="wi wi-orphan">sem work item — órfão no board</div>'

    prs_html = ""
    for pr in entry.get("prs") or []:
        num = _esc(pr.get("number"))
        purl = pr.get("url")
        draft = " · draft" if pr.get("draft") else ""
        if purl:
            prs_html += f'<a class="pr" href="{_esc(purl)}" target="_blank" rel="noopener">PR #{num}{_esc(draft)}</a>'
        else:
            prs_html += f'<span class="pr">PR #{num}{_esc(draft)}</span>'

    link_html = (
        f'<a class="open" href="{_esc(url)}" target="_blank" rel="noopener">Abrir artifact ↗</a>'
        if url else '<span class="open open-none">sem URL publicada</span>'
    )
    desc_html = f'<p class="desc">{_esc(desc)}</p>' if desc else ""

    return (
        f'<article class="card" style="--accent:{accent}">'
        f'<div class="card-head"><h3>{title}</h3><code class="id">{name}</code></div>'
        f'{desc_html}{wi_html}'
        f'<div class="card-foot">{link_html}{prs_html}'
        f'<span class="bytes">{kb} KB</span></div>'
        f'</article>'
    )


def render_gallery_html(gallery: dict[str, Any], *, generated_at: str = "") -> str:
    """Render the gallery as ONE self-contained HTML file (no CDN, theme-aware).

    Pure: takes the ``build_gallery`` dict + an optional timestamp, returns the
    full HTML string. The CLI writes it to ``--html <out>``.
    """
    scope = _esc(gallery.get("scope"))
    counts = gallery.get("counts") or {}
    buckets = gallery.get("buckets") or {}
    total = counts.get("total", 0)

    sections = ""
    for b in BUCKET_ORDER:
        entries = buckets.get(b) or []
        if not entries:
            continue
        accent = _BUCKET_ACCENT[b]
        icon = _BUCKET_ICON[b]
        cards = "".join(_render_card(e, accent) for e in entries)
        sections += (
            f'<section class="bucket" style="--accent:{accent}">'
            f'<h2><span class="dot"></span>{icon} {_esc(bucket_label(b))} '
            f'<span class="count">{len(entries)}</span></h2>'
            f'<div class="grid">{cards}</div></section>'
        )
    if not sections:
        sections = '<p class="empty">Nenhum HtmlArtifact neste scope ainda.</p>'

    gen = f'<span class="gen">gerado {_esc(generated_at)}</span>' if generated_at else ""

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DNA · Gallery — {scope}</title>
<style>
:root {{
  --bg:#faf9f7; --panel:#ffffff; --ink:#1a1a1a; --muted:#6b7280;
  --line:#e5e3df; --chip:#f3f1ed;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0f0f11; --panel:#18181b; --ink:#f4f4f5; --muted:#a1a1aa;
           --line:#27272a; --chip:#232327; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:40px 24px 80px; }}
header {{ border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:32px; }}
h1 {{ font-size:26px; margin:0 0 6px; letter-spacing:-.02em; }}
.sub {{ color:var(--muted); font-size:14px; }}
.sub b {{ color:var(--ink); }}
.gen {{ color:var(--muted); font-size:12px; }}
.bucket {{ margin-bottom:40px; }}
.bucket h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.06em;
  display:flex; align-items:center; gap:8px; margin:0 0 16px; }}
.bucket .dot {{ width:10px; height:10px; border-radius:50%; background:var(--accent); }}
.count {{ background:var(--chip); color:var(--muted); border-radius:999px;
  padding:1px 9px; font-size:12px; font-weight:600; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:16px; }}
.card {{ background:var(--panel); border:1px solid var(--line);
  border-left:3px solid var(--accent); border-radius:12px; padding:16px 18px;
  display:flex; flex-direction:column; gap:10px; }}
.card-head {{ display:flex; flex-direction:column; gap:4px; }}
.card h3 {{ margin:0; font-size:16px; line-height:1.3; }}
.id {{ font-size:11px; color:var(--muted); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
.desc {{ margin:0; color:var(--muted); font-size:13px; }}
.wi {{ display:flex; align-items:center; gap:8px; font-size:12px; flex-wrap:wrap; }}
.wi-kind {{ background:var(--accent); color:#fff; border-radius:5px; padding:1px 7px; font-weight:600; }}
.wi-name {{ font-family:ui-monospace,monospace; color:var(--ink); }}
.wi-status {{ color:var(--muted); }}
.wi-orphan {{ color:var(--muted); font-style:italic; }}
.card-foot {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  margin-top:auto; padding-top:6px; border-top:1px solid var(--line); }}
.open {{ font-size:13px; font-weight:600; color:var(--accent); text-decoration:none; }}
.open:hover {{ text-decoration:underline; }}
.open-none {{ color:var(--muted); font-weight:400; font-style:italic; }}
.pr {{ font-size:12px; background:var(--chip); border-radius:6px; padding:2px 8px;
  color:var(--ink); text-decoration:none; }}
.bytes {{ margin-left:auto; font-size:11px; color:var(--muted); }}
.empty {{ color:var(--muted); }}
footer {{ margin-top:48px; padding-top:20px; border-top:1px solid var(--line);
  color:var(--muted); font-size:12px; }}
</style></head>
<body><div class="wrap">
<header>
  <h1>🖼️ Gallery — {scope}</h1>
  <div class="sub"><b>{total}</b> HtmlArtifact(s) do board, agrupados pelo status do work item que os produziu. {gen}</div>
</header>
{sections}
<footer>
  <b>Gallery</b> = os artefatos visuais pra revisar (HtmlArtifacts). Para <b>o que aconteceu</b> (eventos), use <code>dna sdlc digest</code>.
  Painel board-native — regenere com <code>dna sdlc gallery --html</code> pra refletir o board atual.
</footer>
</div></body></html>
"""
