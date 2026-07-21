"""``dna sdlc reference`` + the citation graph (cite / uncite).

Extracted verbatim from ``sdlc_cmd.py`` (the sdlc_cmd decomposition —
same seam-per-module idiom as the kernel decomposition). Story
s-cli-reference-cite-uncite (f-reference-citation-kind).
"""
from __future__ import annotations

import sys
from typing import Any

import click

from dna_cli._ctx import open_session
from dna_cli.sdlc._common import _build_raw, _now_iso, _scope_option
from dna_cli.sdlc._root import sdlc

# ─── Reference Kind — citation graph ──────────────────────────────────
# Story s-cli-reference-cite-uncite (f-reference-citation-kind).

@sdlc.group("reference")
def reference_group() -> None:
    """Reference Kind — create / list / show external sources."""


@reference_group.command("create")
@click.argument("name")
@click.option("--kind-of", required=True,
              type=click.Choice(["web", "paper", "book", "file", "internal-doc", "other"]))
@click.option("--title", required=True)
@click.option("--url", default=None)
@click.option("--summary", required=True, help="1-2 sentence summary of what this source says.")
@click.option("--quote", "quotes", multiple=True, help="Verbatim key quote (max ~500 chars). Repeat for multiple.")
@click.option("--relevance", default=None, help="Why this matters for THIS project.")
@click.option("--content-path", default=None, help="Path to rich-content sidecar markdown.")
@click.option("--tag", "tags", multiple=True)
@_scope_option
def cmd_reference_create(
    name: str, kind_of: str, title: str, url: str | None,
    summary: str, quotes: tuple, relevance: str | None,
    content_path: str | None, tags: tuple, scope: str,
) -> None:
    """Create a Reference doc capturing an external source."""
    now = _now_iso()
    spec: dict[str, Any] = {
        "title": title,
        "kind_of": kind_of,
        "summary": summary,
        "key_quotes": list(quotes),
        "cited_by": [],
        "owner": "claude-code",
        "created_at": now,
        "updated_at": now,
    }
    if url:
        spec["url"] = url
        spec["fetched_at"] = now
    if relevance:
        spec["relevance"] = relevance
    if content_path:
        spec["content_path"] = content_path
    if tags:
        spec["tags"] = list(tags)
    raw = _build_raw("Reference", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Reference", name, raw))
    click.secho(f"CREATED Reference/{name} (kind_of={kind_of})", fg="green")


@reference_group.command("list")
@click.option("--kind-of", default=None,
              type=click.Choice(["web", "paper", "book", "file", "internal-doc", "other"]))
@_scope_option
def cmd_reference_list(kind_of: str | None, scope: str) -> None:
    """List Reference docs (optionally filtered by kind_of)."""
    with open_session(scope) as s:
        refs = s.query_list("Reference")
    if kind_of:
        refs = [r for r in refs if (r.spec or {}).get("kind_of") == kind_of]
    if not refs:
        click.secho("(no references)", fg="bright_black")
        return
    click.echo(f"{'name':<40} {'kind_of':<14} cited_by  title")
    click.echo("─" * 100)
    for r in sorted(refs, key=lambda x: x.name):
        sp = r.spec or {}
        n_cited = len(sp.get("cited_by") or [])
        title = (sp.get("title") or "")[:50]
        click.echo(f"{r.name:<40} {sp.get('kind_of','-'):<14} {n_cited:<8}  {title}")


@reference_group.command("show")
@click.argument("name")
@_scope_option
def cmd_reference_show(name: str, scope: str) -> None:
    """Show a Reference doc + its citation graph."""
    with open_session(scope) as s:
        doc = s.get_doc("Reference", name)
    if not doc:
        click.secho(f"Reference/{name} not found", fg="red")
        sys.exit(2)
    sp = doc.spec or {}
    click.secho(f"Reference/{name}", bold=True)
    click.echo(f"  title:     {sp.get('title')}")
    click.echo(f"  kind_of:   {sp.get('kind_of')}")
    if sp.get("url"):
        click.echo(f"  url:       {sp.get('url')}")
    click.echo(f"  summary:   {sp.get('summary')}")
    if sp.get("relevance"):
        click.echo(f"  relevance: {sp.get('relevance')}")
    quotes = sp.get("key_quotes") or []
    if quotes:
        click.echo(f"  quotes:    {len(quotes)} entries")
        for q in quotes[:3]:
            click.echo(f"             \"{q[:120]}{'...' if len(q) > 120 else ''}\"")
    cited_by = sp.get("cited_by") or []
    click.echo(f"  cited_by:  {len(cited_by)} docs")
    for c in cited_by[:10]:
        click.echo(f"             - {c}")


# Bare-name citations default to the Reference Kind (backwards-compat with
# the original Reference-only `cite`). A `<Kind>/<name>` cited target is
# resolved as-is — any citable Kind (Research, ADR, Reference, ...).
_CITE_DEFAULT_KIND = "Reference"


def _split_cited(target: str) -> tuple[str, str]:
    """Parse a cited target — ``<Kind>/<name>`` or a bare ``<name>`` that
    defaults to Reference. Semantics: `cite` records a SOURCE that grounds
    the caller (vs `produces` = an output the caller authored)."""
    if "/" in target:
        kind, name = target.split("/", 1)
        return kind, name
    return _CITE_DEFAULT_KIND, target


@sdlc.command("cite")
@click.argument("cited")
@click.option("--from", "from_ref", required=True,
              help="Kind/name of the doc that cites this source (e.g. ADR/0007-emit).")
@_scope_option
def cmd_cite(cited: str, from_ref: str, scope: str) -> None:
    """Bidirectional citation between any two Kinds.

    CITED is the source that grounds the caller — ``<Kind>/<name>`` (e.g.
    ``Research/dna-portability`` or ``ADR/0007``) or a bare ``<name>`` that
    defaults to a Reference. Adds ``cited`` to caller.spec.references AND
    adds the caller ref to the cited doc's spec.cited_by (the back-ref).

    `cite` = a source that FUNDAMENTA the work; `produces` = an output the
    work AUTHORED. Any Kind with a flexible spec gains ``cited_by`` on the
    cited side and ``references`` on the caller side.
    """
    if "/" not in from_ref:
        click.secho("--from must be Kind/name (e.g. ADR/0007-emit)", fg="red")
        sys.exit(2)
    cited_kind, cited_name = _split_cited(cited)
    cited_ref = f"{cited_kind}/{cited_name}"
    caller_kind, caller_name = from_ref.split("/", 1)
    with open_session(scope) as s:
        cited_doc = s.get_doc(cited_kind, cited_name)
        if not cited_doc:
            click.secho(f"{cited_ref} not found", fg="red")
            sys.exit(2)
        caller_doc = s.get_doc(caller_kind, caller_name)
        if not caller_doc:
            click.secho(f"{caller_kind}/{caller_name} not found", fg="red")
            sys.exit(2)
        # Back-ref: cited.spec.cited_by += caller_ref (any Kind — SDLC specs
        # carry additionalProperties, so the field persists even when the
        # Kind doesn't declare it explicitly).
        rspec = dict(cited_doc.spec) if isinstance(cited_doc.spec, dict) else {}
        cited_by = list(rspec.get("cited_by") or [])
        if from_ref not in cited_by:
            cited_by.append(from_ref)
            rspec["cited_by"] = cited_by
            rspec["updated_at"] = _now_iso()
            rraw = _build_raw(cited_kind, cited_name, rspec)
            s.run(s.kernel.write_document(scope, cited_kind, cited_name, rraw))
        # Forward: caller.spec.references += cited_ref. Bare Reference names
        # stay bare (compat); cross-Kind citations store the qualified ref.
        forward = cited_name if cited_kind == _CITE_DEFAULT_KIND else cited_ref
        cspec = dict(caller_doc.spec) if isinstance(caller_doc.spec, dict) else {}
        refs = list(cspec.get("references") or [])
        if forward not in refs:
            refs.append(forward)
            cspec["references"] = refs
            cspec["updated_at"] = _now_iso()
            craw = _build_raw(caller_kind, caller_name, cspec)
            s.run(s.kernel.write_document(scope, caller_kind, caller_name, craw))
    click.secho(f"CITED {cited_ref} ← {from_ref}", fg="green")


@sdlc.command("uncite")
@click.argument("cited")
@click.option("--from", "from_ref", required=True)
@_scope_option
def cmd_uncite(cited: str, from_ref: str, scope: str) -> None:
    """Symmetric removal of a citation link (any Kind)."""
    if "/" not in from_ref:
        click.secho("--from must be Kind/name", fg="red")
        sys.exit(2)
    cited_kind, cited_name = _split_cited(cited)
    cited_ref = f"{cited_kind}/{cited_name}"
    forward = cited_name if cited_kind == _CITE_DEFAULT_KIND else cited_ref
    caller_kind, caller_name = from_ref.split("/", 1)
    with open_session(scope) as s:
        cited_doc = s.get_doc(cited_kind, cited_name)
        caller_doc = s.get_doc(caller_kind, caller_name)
        if cited_doc:
            rspec = dict(cited_doc.spec) if isinstance(cited_doc.spec, dict) else {}
            cited_by = [c for c in (rspec.get("cited_by") or []) if c != from_ref]
            rspec["cited_by"] = cited_by
            rspec["updated_at"] = _now_iso()
            rraw = _build_raw(cited_kind, cited_name, rspec)
            s.run(s.kernel.write_document(scope, cited_kind, cited_name, rraw))
        if caller_doc:
            cspec = dict(caller_doc.spec) if isinstance(caller_doc.spec, dict) else {}
            # Tolerate either the bare or qualified form in the caller's list.
            refs = [
                r for r in (cspec.get("references") or [])
                if r not in (forward, cited_ref, cited_name)
            ]
            cspec["references"] = refs
            cspec["updated_at"] = _now_iso()
            craw = _build_raw(caller_kind, caller_name, cspec)
            s.run(s.kernel.write_document(scope, caller_kind, caller_name, craw))
    click.secho(f"UNCITED {cited_ref} ← {from_ref}", fg="yellow")
