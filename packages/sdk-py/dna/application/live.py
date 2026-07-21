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
from typing import Any, Iterable

#: The conscious opt-out sentinel for a workspace-less credential's scope grant
#: (see :meth:`LiveDna.scope_is_granted`). An operator that genuinely wants a
#: service token to read every scope writes this explicitly, so the exposure is
#: configured and auditable instead of silent — which is the whole point of the
#: i-034 fix.
SCOPE_GRANT_ALL = "*"


def parse_scope_grants(raw: str | None) -> frozenset[str] | None:
    """Parse a comma-separated scope-grant list (a CLI flag / env var) into a set.

    ``None`` / blank → ``None`` ("nothing granted"), which the binder reads as
    fail-closed to the server's own :attr:`LiveDna.base_scope`. Whitespace around
    entries is trimmed and empties dropped, so ``"a, b,"`` is ``{"a", "b"}``."""
    if not raw:
        return None
    names = frozenset(part.strip() for part in raw.split(",") if part.strip())
    return names or None


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
    # ── workspace definitions base (i-058) ──────────────────────────────────────
    # When set (``DNA_WORKSPACE_DEFINITIONS_BASE`` at the faces), a workspace's
    # scope is born — and an existing one is adopted on sign-in — with a Genome
    # declaring ``parent_scope = workspace_definitions_base``, so every
    # definition surface (list_agents / compose_prompt / get_* / query) inherits
    # the host's curated base scope from the first request: the overlay thesis
    # ("declare only the difference") finally has a REST to inherit. ``None``
    # (the OSS / self-host default) writes nothing — behavior unchanged.
    workspace_definitions_base: str | None = None

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
        * the workspace CONFIGURED as the **vendor**'s (``vendor_workspace``) →
          ``base_scope`` (``dna-development`` stays the vendor's; its existing data
          is NOT moved). The reservation is by configuration; this code never
          inspects the id's shape, which is why generated ids (D5) changed nothing
          here.
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

    def scope_is_bound(
        self,
        requested: str | None,
        workspace: str | None,
        *,
        authenticated: bool = False,
        granted_scopes: Iterable[str] | None = None,
    ) -> bool:
        """True when an explicitly ``requested`` scope is allowed for this caller.

        The scope-binding half of the isolation invariant (the edge enforces it).
        There are three regimes, and the distinction that matters is **not**
        "is there a workspace" but "is this caller AUTHENTICATED":

        1. ``authenticated=False`` — stdio / local / ``--auth none``. No credential,
           no tenancy, nothing to bind to: any scope is allowed, exactly as before.
           This is the OSS / self-host path and it is never capped.
        2. ``authenticated=True`` **with a resolved** ``workspace`` — when
           multi-workspace is ON the only scope the request may name is its own
           ``default_scope``; a ``scope`` pointing at another workspace's (or the
           vendor's) is a cross-workspace read and is denied. With multi-workspace
           OFF this is the documented single-tenant shared-scope+overlay model and
           stays permissive.
        3. ``authenticated=True`` and **no workspace resolved** — a service /
           shared-token credential, or an authenticated request on a source that
           configured no workspaces. This used to return ``True`` (i-034: the REST
           path's fail-open), which made *absence of evidence* into a right: a
           caller that resolved no workspace could name ANY scope precisely because
           it had no workspace to be bound to. It is now **fail-closed** — only a
           scope EXPLICITLY granted to the credential is reachable.
           ``granted_scopes`` is that grant: ``None`` means "nothing was granted",
           which falls back to the single scope the server was booted on
           (:attr:`base_scope`); the sentinel :data:`SCOPE_GRANT_ALL` (``"*"``) is
           the operator's conscious, auditable opt-out back to unrestricted
           multi-scope reads.

        ``requested is None`` (the caller named no scope) is always allowed — it
        resolves to :meth:`default_scope`, which is itself workspace-bound.
        """
        if requested is None:
            return True
        if not authenticated:
            # Regime 1 — unauthenticated/local. No tenancy exists to bind against.
            return True
        if workspace:
            # Regime 2 — a resolved workspace may only reach its own scope.
            if not self.vendor_workspace:
                return True
            return requested == self.default_scope(workspace)
        # Regime 3 — authenticated but workspace-less: explicit grant, or nothing.
        return self.scope_is_granted(requested, granted_scopes)

    def scope_is_granted(
        self, requested: str, granted_scopes: Iterable[str] | None
    ) -> bool:
        """True when ``requested`` is explicitly granted to a workspace-less
        authenticated credential.

        The grant is a closed set of scope names, or the sentinel
        :data:`SCOPE_GRANT_ALL`. ``None`` / empty means nothing was granted, and the
        credential falls back to the ONE scope the server was booted on — never to
        "everything", which is the fail-open this method exists to prevent."""
        grants = frozenset(granted_scopes) if granted_scopes else frozenset()
        if not grants:
            return requested == self.base_scope
        if SCOPE_GRANT_ALL in grants:
            return True
        return requested in grants

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
