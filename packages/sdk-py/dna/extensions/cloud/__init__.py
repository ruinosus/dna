"""CloudExtension — DNA Cloud pricing + billing→enforcement registry.

Registers 2 Kinds, from descriptors (F3 — record Kinds are data, not
classes):

  - Tier (``cloud-pricing-plan``) — one DNA Cloud plan's hard caps
    (``calls_per_day``, ``rate_per_sec``, ``max_tenants``) + the feature
    families it unlocks + price, as a first-class GLOBAL Kind so limits are
    project data, not implicit knowledge. NOT named ``Plan`` — that alias
    belongs to the SDLC implementation-plan Kind; a pricing plan is a Tier.
    Free / Pro / Enterprise are tiers.
  - AccountPlan (``cloud-plan-binding``) — the BILLING ACCOUNT→Tier assignment:
    which Tier a given account is currently on. **The subscription belongs to
    the account, not to a workspace** — ONE AccountPlan covers EVERY workspace
    whose ``Workspace.account_id`` matches, so a second workspace is never a
    second charge and billing writes one doc instead of fanning out per
    workspace. The billing→enforcement bridge: dna-cloud's Stripe webhook writes
    it on subscribe/cancel; the MCP server resolves ``workspace → account_id →
    plan`` (``kernel.account_for_workspace`` then ``kernel.account_plan``) when a
    token carries no explicit plan claim. The OSS SDK only READS — zero Stripe
    code. Replaces the retired per-workspace ``WorkspacePlan``, now a write-block
    tombstone in ``Kernel._REMOVED_KINDS``.

CONTRACT — never hardcode caps. The single source of truth for a plan's
limits is its Tier doc (``_lib`` scope, ``tiers/<tier_id>.yaml``), resolved
via ``kernel.tier(id_or_alias)``. The quota enforcer reads calls/day, rate
and tenant caps from there — a cap literal in code is a bug.

Both Kinds are GLOBAL (base-only shared data, no per-tenant override) and NOT
inheritable — ``kernel.tier`` / ``kernel.account_plan`` query ``_lib``
directly regardless of the caller's scope. AccountPlan HAS to be global: an
account sits above every workspace it owns, so it cannot live inside one.
"""
from __future__ import annotations

from dna.kernel.source.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class CloudExtension:
    """Registers the Tier Kind (descriptor-backed)."""

    name = "cloud"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # F3: Tier ships as kinds/pricing-plan.kind.yaml package data (byte-identical
        # package data), registered through the SAME funnel as per-scope
        # KindDefinitions (plane lint + digest idempotency + builtin conflict
        # marker).
        for raw in load_descriptors("dna.extensions.cloud"):
            kernel.kind_from_descriptor(raw)
