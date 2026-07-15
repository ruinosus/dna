"""``dna.application.live`` — the live DNA handle the use-cases operate over.

Per ``adr-faces-reorg`` (move #1): the transport-agnostic application layer
lives in the CORE, not buried in a face. ``LiveDna`` is the kernel-only handle
every use-case in :mod:`dna.application.runtime` takes — a thin wrapper over the
configured kernel + default scope. It has ZERO transport dependencies (no HTTP /
Click / FastMCP); a face BOOTS one (the CLI's ``boot_live`` composition root) and
hands it to the shared use-cases.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LiveDna:
    """A live handle over the configured DNA source — the kernel plus the
    default scope. Built ONCE per face (lazily, on the first call) and shared by
    every use-case. Transport-agnostic: it depends only on the kernel."""

    base_scope: str
    kernel: Any
    provider: Any  # sqlite-vec search provider, or None (lexical fallback)
    # ── multi-tenant base-scope isolation (audit finding H2) ────────────────
    # When ``vendor_tenant`` is set the runtime is MULTI-TENANT: the scope-less
    # DEFAULT a request resolves to becomes PER-TENANT (see ``default_scope``),
    # so a new outside tenant never reads the vendor's ``base_scope`` data as its
    # own. Unset (the OSS / single-tenant default) leaves the base path untouched
    # — every read still defaults to ``base_scope`` exactly as before.
    vendor_tenant: str | None = None
    tenant_scope_prefix: str = "tenant-"

    def default_scope(self, tenant: str | None = None) -> str:
        """The scope a request DEFAULTS to when it names none — tenant-aware.

        The fix for audit finding **H2**: today ``base_scope`` (the vendor's own
        ``dna-development``, holding DNA's internal Orgs/Projects/Stories) is the
        default for EVERY tenant, so a new outside tenant's scope-less reads merge
        the vendor's data as theirs. This resolves the default PER TENANT instead:

        * no ``tenant`` (stdio / local / unauthenticated) → ``base_scope`` — the
          base path is untouched (the OSS / self-host workflow never changes).
        * multi-tenant OFF (``vendor_tenant`` unset) → ``base_scope`` for all —
          exactly today's behavior; per-tenant isolation is opt-in with the flip.
        * the reserved **vendor** tenant → ``base_scope`` (``dna-development`` stays
          the vendor's; its existing data is NOT moved — non-breaking).
        * every OTHER tenant → its OWN scope ``<prefix><tenant>`` (e.g.
          ``tenant-<tid>``), never the vendor's base.

        An explicitly-named ``scope`` still wins over this default; binding an
        authenticated tenant to ONLY its own scope (denying a cross-scope
        ``scope=`` argument) is enforced at the MCP/REST edge, not here.
        """
        if not tenant or not self.vendor_tenant:
            return self.base_scope
        if tenant == self.vendor_tenant:
            return self.base_scope
        return f"{self.tenant_scope_prefix}{tenant}"

    def scope_is_bound(self, requested: str | None, tenant: str | None) -> bool:
        """True when an explicitly ``requested`` scope is allowed for ``tenant``.

        The scope-binding half of H2 (the edge enforces it): when multi-tenant is
        ON and a request carries a tenant, the ONLY scope it may name is its own
        ``default_scope`` — a caller-supplied ``scope`` pointing at another
        tenant's (or the vendor's) scope is a cross-scope read and must be denied.
        Returns ``True`` (allowed) when: multi-tenant is off, there is no tenant,
        no explicit scope was named, or the named scope IS the tenant's own.
        """
        if requested is None or not tenant or not self.vendor_tenant:
            return True
        return requested == self.default_scope(tenant)

    async def mi(self, scope: str | None = None, tenant: str | None = None) -> Any:
        """Build a (optionally tenant-resolved) ManifestInstance for ``scope``.

        Eager (``lazy=False``) so ``mi.documents`` is fully materialized for
        agent/tool enumeration. ``tenant`` promotes into the layer context, so
        ``build_prompt`` composes the per-tenant overlay — the axis emit drops.
        """
        layers = {"tenant": tenant} if tenant else None
        return await self.kernel.instance_async(
            scope or self.default_scope(tenant), layers, lazy=False
        )
