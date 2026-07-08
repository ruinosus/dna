"""``dna docs`` — browse the in-product Doc corpus.

Reads from the ``docs`` scope cross-scope (same as
``manifest_tools.docs.list_docs`` under the hood). The CLI verb
remains ``dna docs`` because that's the natural UX phrasing — the
underlying Kind is ``Doc``.
"""
from __future__ import annotations

import click

from dna_cli._ctx import fail, get_holder, print_json, print_table

DOCS_SCOPE = "docs"
DOC_KIND = "Doc"


@click.group(name="docs", help="Browse the in-product Doc corpus.")
def docs_() -> None:
    """Group root.

    Phase 16 — renamed from ``dna help`` to ``dna docs``. The trailing
    underscore on the function name avoids clashing with the ``docs``
    builtin module name in some toolchains.
    """


@docs_.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.option("--locale", default="pt-BR", show_default=True)
def list_docs(as_json: bool, locale: str) -> None:
    """List all docs (sidebar metadata)."""
    holder = get_holder()
    try:
        mi = holder.kernel.instance(DOCS_SCOPE)
    except Exception as e:
        raise fail(f"docs scope unreachable: {e}")
    _ = mi  # kept for future mi-based ops; current path uses kernel directly
    rows = []
    for d in holder.kernel.query_list_sync(DOCS_SCOPE, DOC_KIND):
        loc = d.spec.get("locale") or "pt-BR"
        if loc != locale:
            continue
        rows.append(
            {
                "name": d.name,
                "icon": d.spec.get("icon", ""),
                "title": d.metadata.get("description") or d.name,
                "order": d.spec.get("order", 999),
                "kind_of": d.spec.get("kind_of") or "",
                "category": d.spec.get("category") or "",
            }
        )
    rows.sort(key=lambda r: r["order"])
    if as_json:
        print_json(rows)
    else:
        print_table(rows, ["order", "icon", "name", "title", "kind_of", "category"])


@docs_.command("show")
@click.argument("doc_name")
@click.option("--locale", default="pt-BR")
def show(doc_name: str, locale: str) -> None:
    """Print the full markdown body of a doc."""
    holder = get_holder()
    _mi = holder.kernel.instance(DOCS_SCOPE)
    candidates = [
        d for d in holder.kernel.query_list_sync(DOCS_SCOPE, DOC_KIND)
        if d.name == doc_name
    ]
    if not candidates:
        raise fail(f"Doc '{doc_name}' not found.")
    chosen = next(
        (c for c in candidates if (c.spec.get("locale") or "pt-BR") == locale),
        candidates[0],
    )
    body = chosen.spec.get("body") or ""
    click.echo(body)
