"""Backfilling the derived reference graph for documents written before it.

A document that was saved before the producer existed has no edges, and there
are only three wrong answers to that plus one right one.

**Wrong: "on first read."** A read that writes deadlocks, costs
unpredictably, and makes two identical calls return different things.

**Wrong: "never — new writes only."** The graph would then describe only what
happened to be touched after the release, and no screen could tell "nothing
points at this" from "nobody has written since Tuesday".

**Wrong: a scanner that sweeps and guesses.** That is literally the slug regex
i-039 refused, arriving through a side door.

**Right: an explicit backfill derived from the SAME declaration the producer
reads.** For each declared ``(Kind, field)`` pair, ask the store for the
documents whose ``spec`` HAS that field — on Postgres a JSONB containment
query the existing ``dna_docs_spec_gin_idx`` serves directly. That is sixteen
queries against the shipped registry today, not a walk over every document,
and it is the same fact, resolved the same way, written through the same
DELETE+INSERT the producer uses. Idempotent, and runnable COLD: nothing in it
needs the write path to be warm.

⚠️ **It must not be able to close a door.** Where this runs at boot it follows
the ``infra/tiers/`` discipline of an artifact applied before serving — but
NOT its ``set -eu``. The Tiers were a revenue gate; this is a read-side
sidecar, and taking an MCP container down because a graph could not be filled
trades an incomplete screen for a closed door. A failure logs, marks the scope,
and lets the container come up.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("dna.kernel")


@dataclass
class BackfillReport:
    """What a backfill did, in numbers a human can check against the database."""

    pairs: int = 0            # declared (Kind, field) pairs consulted
    documents: int = 0        # documents whose edges were recomputed
    edges: int = 0            # edge rows written
    dangling: int = 0         # of those, edges resolving to nothing
    skipped: int = 0          # documents left alone (resolution incomplete)
    #: Scopes where at least one document could not be resolved completely.
    #: The screen reads this as "still being filled" rather than as "empty".
    pending: set[str] = field(default_factory=set)
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "pairs": self.pairs, "documents": self.documents,
            "edges": self.edges, "dangling": self.dangling,
            "skipped": self.skipped, "pending": sorted(self.pending),
            "dry_run": self.dry_run,
        }


def declared_pairs(kernel: Any) -> list[tuple[str, str]]:
    """Every ``(Kind, field)`` the registry declares an ``x-dna-ref`` on.

    DERIVED from the registry, never enumerated by hand: a hand-kept list is
    how a guard goes green while going blind, and the whole point of this
    degree is that the graph is made of declarations rather than of opinions.
    """
    from dna.kernel.query.references import declared_references

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for kind, port in sorted(_registry_items(kernel)):
        for ref in declared_references(port):
            key = (kind, ref.field)
            if key in seen:
                continue
            seen.add(key)
            pairs.append(key)
    return pairs


def _registry_items(kernel: Any) -> list[tuple[str, Any]]:
    """``(kind_name, port)`` for every registered Kind.

    A backfill that cannot reach the registry must SAY so. Returning an empty
    list there would report "0 pairs, 0 documents" — a successful-looking run
    that filled nothing, which is precisely the failure this whole degree is
    about.
    """
    ports = getattr(kernel, "kind_ports", None)
    if not callable(ports):
        raise RuntimeError(
            "cannot enumerate registered Kinds on this kernel (no "
            "kind_ports()), so the declared (Kind, field) pairs cannot be "
            "derived — refusing to report an empty backfill that would look "
            "like a successful one."
        )
    out: list[tuple[str, Any]] = []
    for port in ports():
        kind = getattr(port, "kind", None)
        if isinstance(kind, str):
            out.append((kind, port))
    return out


async def backfill_edges(
    kernel: Any, *, scope: str | None = None, dry_run: bool = False,
) -> BackfillReport:
    """Recompute and store edges for existing documents.

    ``scope=None`` covers every scope the store holds. ``dry_run`` resolves
    everything and writes nothing — the same reads, so the numbers it reports
    are the numbers a real run would produce.
    """
    from dna.kernel.query.references import resolve_declared_edges

    source = kernel._source
    if source is None:
        raise RuntimeError("no source registered")
    reader = getattr(source, "list_documents_with_spec_field", None)
    writer = getattr(source, "replace_edges", None)
    if not callable(reader) or not callable(writer):
        from dna.kernel.query.graph import GraphUnsupported

        raise GraphUnsupported(
            "the active source records no derived reference graph, so there "
            "is nothing to backfill into it."
        )

    report = BackfillReport(dry_run=dry_run)
    pairs = declared_pairs(kernel)
    report.pairs = len(pairs)

    # One document can carry several declared fields; resolve it ONCE.
    # Keyed on the full identity, apiVersion included — two workspaces may each
    # declare a `Deal`, and collapsing them here would give one the other's
    # edges.
    docs: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for kind, ref_field in pairs:
        for row in await reader(kind, ref_field, scope=scope):
            key = (
                row["scope"], row["tenant"], row["kind"],
                row["api_version"], row["name"],
            )
            docs.setdefault(key, row)

    for key, row in sorted(docs.items()):
        doc_scope, tenant, kind, api_version, name = key
        port = kernel.kind_port_for(
            kind, api_version=api_version or None, scope=doc_scope,
        )
        edges, _problems, complete = await resolve_declared_edges(
            port, row["raw"],
            scope=doc_scope, tenant=tenant or None,
            getter=kernel.get_document,
            port_for=kernel.kind_port_for,
            local_getter=getattr(kernel, "get_document_local", None),
        )
        if not complete:
            # Same refusal as the write path: a partial edge set stored as
            # whole is a graph that lies while looking finished. The scope is
            # marked so the screen can say "still being filled".
            report.skipped += 1
            report.pending.add(doc_scope)
            logger.warning(
                "graph backfill: %s/%s/%s left unresolved (a document read "
                "failed mid-resolution) — its edges were NOT replaced",
                doc_scope, kind, name,
            )
            continue
        report.documents += 1
        report.edges += len(edges)
        report.dangling += sum(1 for e in edges if e.to_kind is None)
        if not dry_run:
            await writer(
                doc_scope, kind, name, edges,
                api_version=api_version, tenant=tenant or None,
                from_version=int(row.get("version") or 0),
            )
    return report
