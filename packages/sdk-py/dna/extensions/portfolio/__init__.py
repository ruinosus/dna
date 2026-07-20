"""PortfolioExtension — DNA Cloud portfolio-console data foundation.

Registers 5 record Kinds, from descriptors (F3 — record Kinds are data, not
classes). The accepted model (adr-portfolio-project-model): an Organization
(the tenant boundary) owns Projects; a Project is a multi-repo CONTAINER that
owns its board scope + intel sources + memory; RBAC is the standard ladder.

  - Organization (``portfolio-org``) — the tenant's org profile, the
    enterprise-familiar top-level container the console aggregates. One per
    tenant. Distinct from the platform-level ``Tenant`` provisioning identity
    Kind (GLOBAL); this is the editable profile inside the tenant's portfolio.
  - Project (``portfolio-project``) — the KEY Kind: the multi-repo
    development-space container that OWNS a board scope (``<slug>-development``),
    IntelSources and memory, and is the permission boundary. Repos are attached
    BY REFERENCE via ``repo_refs`` (the N—N edge lives on the Project side).
  - Repo (``portfolio-repo``) — a code repository the portfolio references.
    Attached to N Projects via ``Project.repo_refs``; carries NO project
    back-ref (single source of truth for the N—N edge → no duplication).
  - Membership (``portfolio-membership``) — the RBAC join: a user's role at an
    org- or project-scope (standard ladder owner > admin > member > guest,
    highest-role-wins, org-owner superuser). Distinct from the tenant Kind
    ``TenantMembership`` (which links a user to a provisioning Tenant).
  - Role (``portfolio-role``) — the role ladder AS DATA (the DNA thesis):
    each rung a doc with ``rank`` + ``capabilities``, so the ladder is
    extensible (custom roles) rather than a hardcoded enum. The four standard
    rungs ship as per-tenant seed docs (examples/dna-cloud/.dna/.../roles/).

All 5 are TENANTED — per-tenant portfolio data, NOT shared ``_lib`` defaults,
and deliberately NOT inheritable (never in ``DEFAULT_INHERITABLE_KINDS_V1``),
so TENANTED is the correct tenancy.

This is the data foundation ONLY — the console UI, the resolve_role helper
(highest-role-wins + org-owner superuser) and the enterprise SSO/SCIM layer
land in later stories; here we ship just the five data Kinds.
"""
from __future__ import annotations

from dna.kernel.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class PortfolioExtension:
    """Registers the 5 portfolio Kinds (descriptor-backed)."""

    name = "portfolio"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # F3: all 5 Kinds ship as kinds/*.kind.yaml package data (byte-identical
        # package data), registered through the SAME funnel as per-scope
        # KindDefinitions (plane lint + digest idempotency + builtin conflict
        # marker).
        for raw in load_descriptors("dna.extensions.portfolio"):
            kernel.kind_from_descriptor(raw)
