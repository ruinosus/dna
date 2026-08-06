"""Walking the DERIVED reference graph — ``dna_edges``, one document at a time.

The companion of :mod:`dna.kernel.query.references`: that module says what a
Kind DECLARES (``x-dna-ref``), this one answers what the documents actually
say to each other. The rows come from the write path — the same lookups
``WritePipeline._resolve_references`` performs to validate a reference also
record which Kind it resolved to — so nothing here derives, guesses or parses a
slug. It reads a fact somebody's write produced.

**Why the kernel and not the adapter alone.** The SQL is the adapter's (a
recursive CTE, identical on Postgres and SQLite). The POLICY is not: the depth
ceiling, the refusal to answer at all on a store that keeps no edges, and the
vocabulary the face renders — those belong where the registry lives.

**The refusal that matters most.** A store without an edge table does not
return an empty list. ``[]`` reads as "nothing points at this document", which
is a claim only a store that actually records edges may make; the filesystem
adapter has neither a transaction to write edges in nor a table to write them
to, so the answer is :class:`GraphUnsupported` and the face says so. Serving a
confident empty answer from a store that cannot know is the fail-open silence
this codebase treats as a defect, not a convenience.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

#: Default walk depth. ONE, on purpose: ``Spec.supersedes → Spec`` and
#: ``Story.dependencies → Story`` are self-referential by design, so an
#: unbounded default would be an incident waiting for the first cyclic board.
DEFAULT_DEPTH = 1

#: Ceiling the caller cannot raise. Overridable by the operator through
#: ``DNA_GRAPH_MAX_DEPTH`` — configuration, never request input.
DEFAULT_MAX_DEPTH = 5


class GraphUnsupported(RuntimeError):
    """The active source keeps no derived edge graph, so there is no answer.

    Deliberately an exception and not an empty result: see the module
    docstring. The faces translate it into an explicit ``unsupported``
    capability, never into a list.
    """


def max_depth() -> int:
    """The traversal ceiling, read per call so an operator can change it live."""
    raw = os.environ.get("DNA_GRAPH_MAX_DEPTH", "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_DEPTH
    return value if 1 <= value <= 50 else DEFAULT_MAX_DEPTH


def producer_mode() -> str:
    """How the edge PRODUCER is configured — ``warn`` / ``enforce`` / ``off``.

    Reported alongside every traversal because ``DNA_REF_VALIDATION=off`` skips
    the reference lookups entirely, so no edges are produced. That is a
    defensible operational choice; a screen rendering the resulting emptiness
    as "no relations" is not. Same shape as the degree-0 ``as_of_reads`` /
    ``as_of_truncated`` capability flags.
    """
    mode = os.environ.get("DNA_REF_VALIDATION", "warn").strip().lower()
    return mode if mode in ("enforce", "warn", "off") else "warn"


@dataclass(frozen=True)
class GraphResult:
    """One traversal, with the reason it stopped where it did.

    ``stop`` is not decoration. A caller that cannot tell "this is everything"
    from "this is where I gave up" will render the second as the first.
    """

    edges: list[dict[str, Any]] = field(default_factory=list)
    direction: str = "in"
    depth: int = DEFAULT_DEPTH
    #: ``complete`` | ``depth_reached`` | ``truncated``
    stop: str = "complete"
    #: The producer's configured mode — see :func:`producer_mode`.
    graph_producer: str = "warn"

    @property
    def dangling(self) -> list[dict[str, Any]]:
        """Edges that resolve to nothing — the list of what is broken."""
        return [e for e in self.edges if not e.get("resolved")]


def _clamp_depth(depth: int | None) -> int:
    if depth is None:
        return DEFAULT_DEPTH
    try:
        value = int(depth)
    except (TypeError, ValueError):
        return DEFAULT_DEPTH
    return max(1, min(value, max_depth()))


async def traverse(
    source: Any, scope: str, kind: str, name: str, *,
    tenant: str | None = None,
    direction: str = "in",
    depth: int | None = None,
) -> GraphResult:
    """Walk ``source``'s edge graph from one document.

    ``direction``: ``in`` (what points at this — the product question),
    ``out`` (what this points at), ``both``.

    Raises :class:`GraphUnsupported` when the source declares no edge graph.
    """
    from dna.kernel.capabilities import source_capabilities

    if direction not in ("in", "out", "both"):
        raise ValueError(
            f"direction must be 'in', 'out' or 'both' (got {direction!r})"
        )
    caps = source_capabilities(source)
    if not caps.edge_graph:
        raise GraphUnsupported(
            f"the active source ({caps.source}) does not record the derived "
            f"reference graph, so it cannot answer what points at "
            f"{kind}/{name}. This is not the same as 'nothing points at it' — "
            f"run against an adapter that declares edge_graph (the SQL "
            f"adapter, on either dialect) to get a real answer."
        )
    effective = _clamp_depth(depth)
    rows = await source.traverse_edges(
        scope, kind, name,
        tenant=tenant, direction=direction, depth=effective,
    )
    deepest = max((int(r.get("depth", 1)) for r in rows), default=0)
    stop = "depth_reached" if deepest >= effective else "complete"
    if len(rows) >= getattr(source, "MAX_TRAVERSAL_ROWS", 10**9):
        # The walk hit the adapter's row ceiling: what came back is a PREFIX of
        # the answer, and saying "complete" here would be the graph's version
        # of a truncated list rendered as a full one.
        stop = "truncated"
    return GraphResult(
        edges=rows, direction=direction, depth=effective, stop=stop,
        graph_producer=producer_mode(),
    )
