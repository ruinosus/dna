"""``dna.application.live`` — the live DNA handle the use-cases operate over.

Per ``adr-faces-reorg`` (move #1): the transport-agnostic application layer
lives in the CORE, not buried in a face. ``LiveDna`` is the kernel-only handle
every use-case in :mod:`dna.application.runtime` takes — a thin wrapper over the
configured kernel + default scope. It has ZERO transport dependencies (no HTTP /
Click / FastMCP); a face BOOTS one (the CLI's ``boot_live`` composition root) and
hands it to the shared use-cases.
"""
from __future__ import annotations

import logging
import os
import time

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: The clock the Kind-refresh window is measured on. MONOTONIC, not wall clock:
#: an NTP step backwards would freeze the window for the size of the step and a
#: step forwards would expire it on every request. Aliased at module level so a
#: test can drive the window deterministically instead of sleeping through it.
_monotonic = time.monotonic

#: How long (seconds) a replica may keep serving a scope's Kind registry without
#: re-reading the store — and therefore the WORST-CASE lag between one replica
#: approving/revoking a Kind and every OTHER replica honouring it (i-090).
#:
#: This number is the SLA. It is not a performance knob that happens to have a
#: correctness side effect: registration is what confers schema validation,
#: storage routing and the revocation refusal, and registration only happens
#: inside a Manifest Instance build. Nothing else in the process schedules that
#: build for a scope, so without this window the moment an approval starts to
#: hold is indeterminate and differs per replica.
#:
#: 30 s mirrors the kernel's granular list TTL
#: (``dna.kernel.boot.cache._GRANULAR_LIST_TTL``) so an operator has one number
#: to reason about rather than two.
KIND_REFRESH_TTL_DEFAULT = 30.0

#: The operator's knob for :data:`KIND_REFRESH_TTL_DEFAULT`. Lower it for a
#: deployment that wants approvals to land faster (at one extra bootstrap read
#: per scope per window per replica); ``0`` disables the seam entirely, which
#: returns the deployment to "the approving replica only" — Layer 1 — and is a
#: choice an operator may legitimately make for a single-replica self-host.
KIND_REFRESH_TTL_ENV = "DNA_KIND_REFRESH_TTL"


def default_kind_refresh_ttl() -> float:
    """The configured Kind-refresh window, in seconds.

    Unparseable or negative input falls back to the default rather than
    disabling the seam: ``0`` switches it off and that has to stay a DELIBERATE
    act, not something a typo in an env var can do silently."""
    raw = os.environ.get(KIND_REFRESH_TTL_ENV)
    if raw is None or not raw.strip():
        return KIND_REFRESH_TTL_DEFAULT
    try:
        ttl = float(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not a number — falling back to the %.0fs default",
            KIND_REFRESH_TTL_ENV, raw, KIND_REFRESH_TTL_DEFAULT,
        )
        return KIND_REFRESH_TTL_DEFAULT
    if ttl < 0:
        logger.warning(
            "%s=%r is negative — falling back to the %.0fs default",
            KIND_REFRESH_TTL_ENV, raw, KIND_REFRESH_TTL_DEFAULT,
        )
        return KIND_REFRESH_TTL_DEFAULT
    return ttl

#: The access levels a ``WorkspaceScopeGrant`` row can carry, weakest first, and
#: the ONLY vocabulary the binder understands. The Kind's ``access`` enum
#: currently has a single member (``read``) on purpose — widening it is meant to
#: be a deliberate schema change with a reviewer — but the RANKING lives here so
#: the binder can already answer "does this grant cover this call?" instead of
#: not asking. Anything outside this table is unknown, and unknown is a denial.
SCOPE_ACCESS_RANK: Mapping[str, int] = {"read": 0, "write": 1}

#: The level a grant is read at when it records none (the Kind's own default,
#: and the only safe reading of a grant shape that carries no access at all).
SCOPE_ACCESS_DEFAULT = "read"


def scope_access_covers(granted: str | None, requested: str) -> bool:
    """True when a grant recorded at ``granted`` covers a ``requested`` call.

    Fail-CLOSED on BOTH sides: a level this build does not know — whether it is
    the one a row recorded or the one a call site asked for — is a denial, never
    a fallback to the permissive answer. A grant that means nothing here must
    grant nothing here."""
    if granted is None:
        return False
    try:
        return SCOPE_ACCESS_RANK[granted] >= SCOPE_ACCESS_RANK[requested]
    except KeyError:
        return False


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
    # ── the Kind-refresh window (i-090) ─────────────────────────────────────────
    # See :func:`default_kind_refresh_ttl`. Read from the environment at
    # construction so a face gets the operator's number with no wiring, and it is
    # a FIELD rather than a module lookup so a test — or a face with its own
    # configuration — can set it per handle.
    kind_refresh_ttl: float = field(default_factory=default_kind_refresh_ttl)
    # ── adopt-on-access probe cache (the i-058 hardening) ────────────────────────
    # Scopes this PROCESS has already probed/adopted via
    # ``dna.application.runtime.adopt_workspace_scope_on_access`` — the memo that
    # makes the per-request adoption probe cost one set lookup instead of one
    # kernel read per request (the ``is_personal_doc`` pattern). Entries are added
    # ONLY after the probe reached a stable state (a parent is declared, or the
    # scope is exempt); a FAILED probe is never cached, so a transient hiccup
    # retries on the next request. ``init=False``: faces never pass these — the
    # cache is an implementation detail of the live handle, not configuration.
    adoption_probed: set = field(default_factory=set, init=False, repr=False, compare=False)
    adoption_lock: Any = field(default=None, init=False, repr=False, compare=False)
    # ── Kind-refresh bookkeeping (i-090) ────────────────────────────────────────
    # ``{scope: monotonic timestamp of the last registry refresh}`` plus the lock
    # that single-flights concurrent refreshes. ``init=False``: faces never pass
    # these — they are an implementation detail of the live handle, exactly like
    # the adoption cache above.
    _kinds_refreshed: dict = field(
        default_factory=dict, init=False, repr=False, compare=False)
    _kinds_lock: Any = field(default=None, init=False, repr=False, compare=False)

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
        workspace_grants: Mapping[str, str] | Iterable[str] | None = None,
        access: str = SCOPE_ACCESS_DEFAULT,
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

        ``access`` is the read/write axis of regime 2, and it constrains ONLY the
        cross-scope grant (i-082). A workspace writes its own scope as it always
        did; reaching ANOTHER scope now asks the grant what it actually permits,
        because the ``WorkspaceScopeGrant`` Kind pins ``access`` to ``read`` and
        an operator reading that schema is owed the guarantee it states. A caller
        that names no ``access`` is asking to READ — the narrow answer, so a face
        that forgets the axis cannot accidentally widen anybody's reach.
        """
        if requested is None:
            return True
        if not authenticated:
            # Regime 1 — unauthenticated/local. No tenancy exists to bind against.
            return True
        if workspace:
            # Regime 2 — a resolved workspace reaches its OWN scope, plus any
            # scope explicitly GRANTED to it by a ``WorkspaceScopeGrant`` row
            # (``workspace_grants``).
            #
            # ``granted_scopes`` — the CREDENTIAL's grant, an operator env var —
            # is deliberately NOT consulted here, and the two arrive under two
            # names so they cannot be confused at a call site. They answer
            # different questions ("what may this token reach" vs "what may this
            # workspace reach") and ORing them would make a permissive service
            # token a back door into any workspace's data: the composition bug
            # a two-mechanism design invites.
            #
            # The grant is DATA, and it is checked by membership, never derived:
            # no prefix rule, no "same account" inference, no wildcard. A leak is
            # therefore always a row somebody wrote — which can be listed,
            # diffed and revoked — rather than a rule nobody can see. With no
            # grants (``granted_scopes`` empty or None) this is byte-for-byte
            # today's behavior, so nothing changes for a deployment that adds no
            # rows.
            if not self.vendor_workspace:
                return True
            if requested == self.default_scope(workspace):
                return True
            return self.workspace_scope_is_granted(
                requested, workspace_grants, access=access,
            )
        # Regime 3 — authenticated but workspace-less: explicit grant, or nothing.
        return self.scope_is_granted(requested, granted_scopes)

    def workspace_scope_is_granted(
        self,
        requested: str,
        granted_scopes: Mapping[str, str] | Iterable[str] | None,
        *,
        access: str = SCOPE_ACCESS_DEFAULT,
    ) -> bool:
        """True when a ``WorkspaceScopeGrant`` names ``requested`` for this
        workspace **at or above** ``access``.

        Deliberately NOT :meth:`scope_is_granted`: that one honours
        :data:`SCOPE_GRANT_ALL` (``"*"``), which is an operator's conscious,
        process-level opt-out for a service credential with no workspace. A
        wildcard reaching this path would let ONE data row grant a workspace
        every scope in the deployment — the exact unbounded blast radius the
        "grants are rows" design exists to avoid. ``"*"`` here is not a
        wildcard; it is a scope literally named ``*``, and there isn't one.

        ``granted_scopes`` is a ``{scope: access}`` mapping — the shape
        ``workspace_granted_scopes`` reads off the rows. A bare iterable of scope
        names is still accepted and read as :data:`SCOPE_ACCESS_DEFAULT`: it
        records no level, and the only safe reading of "no level recorded" is the
        narrowest one, so a caller still on the older shape stays fail-closed for
        writes instead of silently gaining them."""
        if not granted_scopes:
            return False
        if isinstance(granted_scopes, Mapping):
            level = granted_scopes.get(requested)
        else:
            level = (
                SCOPE_ACCESS_DEFAULT
                if requested in frozenset(granted_scopes)
                else None
            )
        return scope_access_covers(level, access)

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

    # ── the Kind-registry rebuild trigger (i-090) ───────────────────────────

    async def refresh_kinds(
        self, scope: str | None = None, *, tenant: str | None = None,
    ) -> bool:
        """Re-register ``scope``'s Kinds from the store, NOW, and reset its
        window. Returns whether the refresh actually ran.

        The narrowest act that makes an approval or a revocation real. What
        confers effect on a Kind is REGISTRATION — the registry's approval gate
        withholds it until ``approved_by`` names somebody, and marks the port
        revoked when ``revoked_by`` does — and registration happens only inside a
        Manifest Instance build (``instance_builder``'s Phase 1). The approval
        write already invalidates the scope's base MI, so the next build is
        fresh; what was missing (i-090) is anything that SCHEDULES a next build.
        This is that thing.

        ``lazy=True`` is the point, not an optimisation: it loads the bootstrap
        slice only (Genome + KindDefinition + LayerPolicy) and runs the same
        Phase 1 registration the eager path runs, so it buys the whole effect for
        a fraction of the cost — measured at roughly a quarter of an eager build
        on a filesystem store. It also deliberately bypasses the base-MI cache
        (which has no TTL and would hand back the very stale registry this call
        exists to replace).

        **Fail-soft.** A store hiccup here must not turn a request that would
        have worked into an error: the caller proceeds against the registry the
        replica already has, the window is NOT stamped, and the next call
        retries. This is a freshness mechanism layered onto a path that already
        functioned; making it a new failure mode would be a bad trade.
        """
        sc = scope or self.default_scope(tenant)
        try:
            await self.kernel.instance_async(sc, None, lazy=True)
        except Exception as exc:  # noqa: BLE001 — fail-soft, retry next call.
            logger.warning(
                "Kind-registry refresh failed for scope %r — the call proceeds "
                "against the registry this replica already holds and the next "
                "one retries: %s", sc, exc,
            )
            return False
        self._kinds_refreshed[sc] = _monotonic()
        return True

    async def ensure_kinds(
        self, scope: str | None = None, *, tenant: str | None = None,
    ) -> bool:
        """Make sure ``scope``'s Kind registry is no older than
        :attr:`kind_refresh_ttl`. Returns whether a refresh ran.

        The seam the INSTANCE routes go through, and the reason an approval now
        has a publishable bound instead of an indeterminate one. Instance routes
        (``write_instance`` / ``get_instance`` / ``list_instances`` /
        ``list_kinds`` / the generic delete) resolve their Kind straight off the
        registry; they never built a Manifest Instance, so on any replica that
        did not itself serve the approval the Kind stayed unregistered until
        somebody happened to call a ``definitions``-family route for that scope.
        "Happened to" is not a guarantee, and for a REVOCATION it is a door that
        is slow to close.

        With this in place the guarantee is a number: **an approval or a
        revocation is honoured by every replica within
        :attr:`kind_refresh_ttl` seconds** (immediately on the replica that
        served the act — see :meth:`refresh_kinds`). The cost of the guarantee is
        one bootstrap-slice read per scope per window per replica, so a hot scope
        under 30 s costs two reads a minute regardless of request rate.

        ``kind_refresh_ttl <= 0`` disables it — a deliberate operator choice
        (:data:`KIND_REFRESH_TTL_ENV`), which returns the deployment to
        "the approving replica honours it, the others on their next definitions
        call".

        Single-flighted: a burst over a cold scope yields ONE rebuild, not one
        per concurrent request. The refresh is idempotent, so the lock is about
        cost, not correctness.
        """
        ttl = float(self.kind_refresh_ttl or 0.0)
        if ttl <= 0:
            return False
        sc = scope or self.default_scope(tenant)
        last = self._kinds_refreshed.get(sc)
        if last is not None and (_monotonic() - last) < ttl:
            return False   # steady state: one dict lookup, zero store reads.

        import asyncio

        if self._kinds_lock is None:
            self._kinds_lock = asyncio.Lock()
        async with self._kinds_lock:
            last = self._kinds_refreshed.get(sc)
            if last is not None and (_monotonic() - last) < ttl:
                return False   # lost the race to the first flight.
            return await self.refresh_kinds(sc)

    async def mi(self, scope: str | None = None, tenant: str | None = None) -> Any:
        """Build a (optionally tenant-resolved) ManifestInstance for ``scope``.

        Eager (``lazy=False``) so ``mi.instances`` is fully materialized for
        agent/tool enumeration. ``tenant`` promotes into the layer context, so
        ``build_prompt`` composes the per-tenant overlay — the axis emit drops.
        """
        layers = {"tenant": tenant} if tenant else None
        return await self.kernel.instance_async(
            scope or self.default_scope(tenant), layers, lazy=False
        )
