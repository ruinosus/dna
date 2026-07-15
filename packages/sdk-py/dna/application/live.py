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
    # ── Model B workspace base-scope isolation (ADR "Model B", f-ws-resolution) ─
    # When ``vendor_workspace`` is set the runtime is MULTI-WORKSPACE: the
    # scope-less DEFAULT a request resolves to becomes PER-WORKSPACE (see
    # ``default_scope``), so a new outside workspace never reads the vendor's
    # ``base_scope`` data as its own. Unset (the OSS / single-tenant default)
    # leaves the base path untouched — every read still defaults to ``base_scope``
    # exactly as before. This is the #114 ``vendor_tenant`` machinery ported to
    # workspace vocabulary (s/tid/workspace_id/): the kernel key stays the opaque
    # ``tenant`` column; Model B only changes that its value is a workspace id.
    vendor_workspace: str | None = None
    workspace_scope_prefix: str = "tenant-"

    def default_scope(self, workspace: str | None = None) -> str:
        """The scope a request DEFAULTS to when it names none — workspace-aware.

        Physical isolation beneath the auth resolver: once the ingress has
        resolved a request to a single ``workspace`` (verified identity +
        WorkspaceMembership), a scope-less read resolves PER WORKSPACE so a new
        outside workspace never merges the vendor's ``base_scope``
        (``dna-development``) data as its own:

        * no ``workspace`` (stdio / local / unauthenticated) → ``base_scope`` —
          the base path is untouched (the OSS / self-host workflow never changes).
        * multi-workspace OFF (``vendor_workspace`` unset) → ``base_scope`` for
          all — exactly today's behavior; per-workspace isolation is opt-in.
        * the reserved **vendor** workspace #1 (its id == the founder's Azure tid)
          → ``base_scope`` (``dna-development`` stays the vendor's; its existing
          data is NOT moved — the zero-migration hinge).
        * every OTHER workspace → its OWN scope ``<prefix><workspace_id>`` (e.g.
          ``tenant-<workspace_id>``), never the vendor's base.

        An explicitly-named ``scope`` still wins over this default; binding a
        resolved workspace to ONLY its own scope (denying a cross-workspace
        ``scope=`` argument) is enforced at the MCP/REST edge, not here.
        """
        if not workspace or not self.vendor_workspace:
            return self.base_scope
        if workspace == self.vendor_workspace:
            return self.base_scope
        return f"{self.workspace_scope_prefix}{workspace}"

    def scope_is_bound(self, requested: str | None, workspace: str | None) -> bool:
        """True when an explicitly ``requested`` scope is allowed for ``workspace``.

        The scope-binding half of the isolation invariant (the edge enforces it):
        when multi-workspace is ON and a request carries a resolved workspace, the
        ONLY scope it may name is its own ``default_scope`` — a caller-supplied
        ``scope`` pointing at another workspace's (or the vendor's) scope is a
        cross-workspace read and must be denied. Returns ``True`` (allowed) when:
        multi-workspace is off, there is no workspace, no explicit scope was named,
        or the named scope IS the workspace's own.
        """
        if requested is None or not workspace or not self.vendor_workspace:
            return True
        return requested == self.default_scope(workspace)

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
