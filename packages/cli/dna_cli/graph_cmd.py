"""``dna graph`` — the DERIVED reference graph: backfill it, ask it.

The producer writes an edge every time a document is saved, inside the save's
own transaction. Everything written BEFORE the producer existed therefore has
no edges, and this is the command that fixes that — explicitly, from the same
``x-dna-ref`` declaration the producer reads, never from a scan that guesses at
slug prefixes (the mechanism i-039 refused, and the reason ``dna_edges`` was
dropped the first time).

``backfill`` is idempotent (the same DELETE+INSERT per document the producer
uses) and runnable COLD: nothing in it needs the write path to be warm.

⚠️ Naming: ``dna_cli.graph`` is the Microsoft Graph OBO adapter, an unrelated
package that happens to share the English word. This module is ``graph_cmd``
like every other command module, and the two never meet.
"""
from __future__ import annotations

import click

from dna_cli._ctx import fail, open_session, print_json


@click.group("graph", help="The derived reference graph (x-dna-ref edges).")
def graph() -> None:
    """Group root."""


@graph.command("backfill")
@click.option("--scope", default=None,
              help="Only this scope (default: every scope in the store).")
@click.option("--dry-run", is_flag=True,
              help="Resolve everything, write nothing — same reads, real numbers.")
@click.option("--json", "as_json", is_flag=True)
def backfill(scope: str | None, dry_run: bool, as_json: bool) -> None:
    """Compute edges for documents that predate the producer.

    For each declared ``(Kind, field)`` pair, ask the store for the documents
    whose ``spec`` HAS that field — on Postgres a JSONB key-existence query the
    ``dna_docs_spec_gin_idx`` index serves directly. That is a handful of
    queries, not a walk over every document.

    A document whose references cannot be resolved COMPLETELY (a read failed
    part-way) is left alone and its scope is reported as pending: a partial
    edge set stored as if it were whole is a graph that lies while looking
    finished, and the screen can label an absent graph but not a lying one.
    """
    from dna.kernel.query.backfill import backfill_edges
    from dna.kernel.query.graph import GraphUnsupported

    with open_session(scope) as s:
        try:
            report = s.run(
                backfill_edges(s.kernel, scope=scope, dry_run=dry_run)
            )
        except GraphUnsupported as exc:
            fail(str(exc))
            return
    if as_json:
        print_json(report.as_dict())
        return
    verb = "would write" if dry_run else "wrote"
    click.echo(
        f"{report.pairs} declared (Kind, field) pair(s) · "
        f"{report.documents} document(s) · {verb} {report.edges} edge(s), "
        f"{report.dangling} dangling"
    )
    if report.skipped:
        # Loud on purpose: this is the number that says the graph is INCOMPLETE,
        # and an incomplete graph reported as a finished one is the whole defect
        # this degree exists to avoid.
        click.echo(
            f"⚠ {report.skipped} document(s) left unresolved in "
            f"{', '.join(sorted(report.pending))} — their edges were NOT "
            f"replaced. Re-run once the store is healthy."
        )


@graph.command("refs")
@click.argument("kind_name")
@click.argument("name")
@click.option("--scope", default=None)
@click.option("--tenant", default=None)
@click.option("--direction", type=click.Choice(["in", "out", "both"]),
              default="in", show_default=True,
              help="'in' = what points AT this document (the product question).")
@click.option("--depth", default=1, show_default=True,
              help="Walk further; clamped by DNA_GRAPH_MAX_DEPTH.")
@click.option("--json", "as_json", is_flag=True)
def refs(
    kind_name: str, name: str, scope: str | None, tenant: str | None,
    direction: str, depth: int, as_json: bool,
) -> None:
    """"What points at this document?" — the same walk the REST face serves."""
    from dna.kernel.query.graph import GraphUnsupported

    with open_session(scope) as s:
        try:
            result = s.run(s.kernel.graph_refs(
                s.scope, kind_name, name,
                tenant=tenant, direction=direction, depth=depth,
            ))
        except GraphUnsupported as exc:
            fail(str(exc))
            return
    if as_json:
        print_json({
            "direction": result.direction, "depth": result.depth,
            "stop": result.stop, "graph_producer": result.graph_producer,
            "edges": result.edges,
        })
        return
    if not result.edges:
        # Never a bare "none": the reader must be able to tell "nothing points
        # at it" from "the producer is off and nothing was ever recorded".
        click.echo(
            f"no edges recorded (producer: {result.graph_producer}, "
            f"stop: {result.stop})"
        )
        return
    for e in result.edges:
        mark = "" if e["resolved"] else "  ⚠ dangling"
        click.echo(
            f"[{e['depth']}] {e['from_kind']}/{e['from_name']}"
            f" --{e['source_field']}[{e['ordinal']}]--> "
            f"{e['to_kind'] or '?'}/{e['to_name']}{mark}"
        )
    click.echo(f"({len(result.edges)} edge(s); stop: {result.stop})")
