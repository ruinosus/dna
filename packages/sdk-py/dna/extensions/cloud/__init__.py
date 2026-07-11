"""CloudExtension — DNA Cloud pricing-tier registry.

Registers 1 Kind, from a descriptor (F3 — record Kinds are data, not
classes):

  - Tier (``cloud-tier``) — one DNA Cloud plan's hard caps
    (``calls_per_day``, ``rate_per_sec``, ``max_tenants``) + the feature
    families it unlocks + price, as a first-class GLOBAL Kind so limits are
    project data, not implicit knowledge. NOT named ``Plan`` — that alias
    belongs to the SDLC implementation-plan Kind; a pricing plan is a Tier.
    Free / Pro / Enterprise are tiers.

CONTRACT — never hardcode caps. The single source of truth for a plan's
limits is its Tier doc (``_lib`` scope, ``tiers/<tier_id>.yaml``), resolved
via ``kernel.tier(id_or_alias)``. The quota enforcer reads calls/day, rate
and tenant caps from there — a cap literal in code is a bug.

The Kind is GLOBAL (base-only shared data, no per-tenant override) and NOT
inheritable — ``kernel.tier`` queries ``_lib`` directly regardless of the
caller's scope.
"""
from __future__ import annotations

from dna.kernel.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class CloudExtension:
    """Registers the Tier Kind (descriptor-backed)."""

    name = "cloud"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # F3: Tier ships as kinds/tier.kind.yaml package data (byte-identical
        # Py↔TS mirror), registered through the SAME funnel as per-scope
        # KindDefinitions (plane lint + digest idempotency + builtin conflict
        # marker).
        for raw in load_descriptors("dna.extensions.cloud"):
            kernel.kind_from_descriptor(raw)
