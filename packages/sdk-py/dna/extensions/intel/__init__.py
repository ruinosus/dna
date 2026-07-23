"""IntelExtension — DNA intelligence-layer data foundation.

Registers 2 record Kinds, from descriptors (F3 — record Kinds are data, not
classes):

  - IntelSource (``intel-source``) — a watched portfolio source (the
    "Direction" stage: what the DNA observes). One doc per source (a repo, a
    scope, or an external URL) carrying its research cadence, actionability
    threshold, Priority Intelligence Requirements (PIRs) and mute state.
    TENANTED — a source is the tenant's OWN watchlist (per-tenant user data),
    NOT a shared ``_lib`` default. It is deliberately NOT inheritable (never in
    ``DEFAULT_INHERITABLE_KINDS_V1``), so TENANTED is correct.
  - Insight (``intel-insight``, kind name ``IntelInsight``) — the
    dissemination unit: a ranked, actionable insight that the
    ranker/digest/dedup/feedback stages reference. TENANTED for the same
    reason (per-tenant generated data). Embeddable (``embed: [title, fact]``)
    so a later dedup story can do semantic recall.

This is the foundation ONLY — the research/ranker/digest/feedback stages land
in later stories; here we ship just the two data Kinds.
"""
from __future__ import annotations

from dna.kernel.source.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class IntelExtension:
    """Registers the IntelSource + IntelInsight Kinds (descriptor-backed)."""

    name = "intel"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # F3: both Kinds ship as kinds/*.kind.yaml package data (byte-identical
        # package data), registered through the SAME funnel as per-scope
        # KindDefinitions (plane lint + digest idempotency + builtin conflict
        # marker).
        for raw in load_descriptors("dna.extensions.intel"):
            kernel.kind_from_descriptor(raw)
