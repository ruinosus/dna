"""RegistryAccessor — the three GLOBAL ``_lib``-direct registry reads extracted
from the Kernel god-object (``s-kernel-decomp-f5-satellites``).

``model_profile`` / ``voice_policy`` / ``embedding_profile`` all resolve a
GLOBAL Kind that lives exclusively in the ``_lib`` scope and is NOT in
``_INHERITABLE_KINDS`` — so per-scope inheritance never surfaces it. Each read
is therefore ``_lib``-direct (a caller-scope query would silently no-op for
scopes with zero such docs) and fail-soft (a registry glitch degrades to
``None``, logged loud, rather than crashing the caller).

Behavior-preserving extraction: the three bodies move here verbatim; the kernel
keeps ``model_profile`` / ``voice_policy`` / ``embedding_profile`` as thin
delegators (read by voice callers + the write-path prompt-budget veto guard, so
the facade signatures are unchanged). A STATELESS back-ref collaborator: it
reads ``query`` (which auto-stamps ``k.tenant``) through the host, so
``with_tenant`` rebinds it to the shallow copy — matching the pre-extraction
method-bound-to-``self`` behavior exactly.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from dna.kernel.protocols import SYSTEM_SCOPE

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import RegistryAccessorHost

logger = logging.getLogger(__name__)

#: i-051 — the hosted shape's fail-CLOSED switch for the Tier registry. The
#: env NAME is the contract shared with ``dna_cli._mcp_quota.require_tiers``
#: (the CLI cannot be imported from the SDK): when the host sets it, a Tier
#: registry failure must PROPAGATE to the caller (which then refuses the
#: call) instead of degrading to ``None`` — because downstream, ``None``
#: becomes empty caps becomes NO quota enforcement, i.e. a database hiccup
#: silently converting into unlimited unbilled calls. Scoped to ``tier()``
#: only: it is a QUOTA contract, not a general fail-hard switch.
_REQUIRE_TIERS_ENV = "DNA_QUOTA_REQUIRE_TIERS"


def _quota_requires_tiers() -> bool:
    """Whether this process opted into fail-CLOSED quota (see above)."""
    return str(os.environ.get(_REQUIRE_TIERS_ENV) or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


class RegistryAccessor:
    """The GLOBAL ``_lib`` registry reads. One per kernel; back-ref to it."""

    # The ModelProfile / VoicePolicy Kinds and the CognitivePolicy-embedded
    # embedding profile are GLOBAL — they live exclusively in the _lib scope.
    # These lookups MUST query _lib directly, never the caller's scope, to avoid
    # a silent no-op when the caller has a scope that contains zero such docs.
    _MODEL_REGISTRY_SCOPE = SYSTEM_SCOPE
    _VOICE_POLICY_SCOPE = SYSTEM_SCOPE
    _EMBEDDING_PROFILE_SCOPE = SYSTEM_SCOPE
    # Tier (DNA Cloud pricing plans) is GLOBAL — _lib-resident like
    # ModelProfile, not inheritable. Same _lib-direct rationale.
    _TIER_REGISTRY_SCOPE = SYSTEM_SCOPE
    # AccountPlan (BILLING ACCOUNT→Tier assignment) is GLOBAL — _lib-resident like
    # Tier. dna-cloud's Stripe webhook writes it; the SDK only reads it. It HAS to
    # be _lib-resident: an account sits ABOVE every workspace it owns, so it
    # cannot live inside any one of them. Same _lib-direct rationale.
    _ACCOUNT_PLAN_REGISTRY_SCOPE = SYSTEM_SCOPE
    # WorkspaceMembership (identity→workspace grant, ADR "Model B") is GLOBAL —
    # _lib-resident like AccountPlan (the tenancy boundary lives above any single
    # workspace). The auth→workspace resolver reads ALL grants here and filters
    # by the verified identity in pure core. Same _lib-direct rationale.
    _WORKSPACE_MEMBERSHIP_REGISTRY_SCOPE = SYSTEM_SCOPE
    # Workspace (the tenancy ROOT itself) is GLOBAL for the same reason its
    # memberships are: the tenancy boundary cannot live inside a tenant. Same
    # _lib-direct rationale.
    _WORKSPACE_REGISTRY_SCOPE = SYSTEM_SCOPE

    def __init__(self, kernel: "RegistryAccessorHost") -> None:
        self._k = kernel

    async def model_profile(self, model_id_or_alias: str) -> dict | None:
        """Resolve a ModelProfile from the _lib registry by model_id,
        then by aliases[].

        Returns the RAW DICT row (kernel.query yields raw dicts, not
        Documents — callers read profile["spec"][...]) or None when no
        match is found.

        The lookup is _lib-direct — ModelProfile is NOT in
        _INHERITABLE_KINDS so per-scope inheritance does not surface it.
        Accepts no scope arg: the registry is global.
        """
        try:
            rows = [
                r async for r in self._k.query(self._MODEL_REGISTRY_SCOPE, "ModelProfile")
            ]
        except Exception as e:  # noqa: BLE001
            # fail-soft: registry read — but a silent None here disables the
            # prompt-budget guard downstream (the write-path cap enforcement
            # reads this profile), so the degradation logs loud.
            logger.warning(
                "model_profile: registry query failed for %r (budget "
                "enforcement degrades to no-profile): %s",
                model_id_or_alias, e,
            )
            return None
        # First pass: exact model_id match.
        for r in rows:
            if (r.get("spec") or {}).get("model_id") == model_id_or_alias:
                return r
        # Second pass: alias match.
        for r in rows:
            if model_id_or_alias in ((r.get("spec") or {}).get("aliases") or []):
                return r
        return None

    async def tier(self, tier_id_or_alias: str) -> dict | None:
        """Resolve a Tier (DNA Cloud pricing plan) from the _lib registry by
        tier_id, then by aliases[].

        Returns the RAW DICT row (kernel.query yields raw dicts, not
        Documents — callers read tier["spec"][...]) or None when no match is
        found.

        The lookup is _lib-direct — Tier is NOT in _INHERITABLE_KINDS so
        per-scope inheritance does not surface it. Accepts no scope arg: the
        registry is global. The quota enforcer reads the caps from here —
        never hardcode calls_per_day / rate_per_sec / max_tenants in code.
        """
        try:
            rows = [
                r async for r in self._k.query(self._TIER_REGISTRY_SCOPE, "Tier")
            ]
        except Exception as e:  # noqa: BLE001
            # fail-soft: registry read — but a silent None here disables the
            # quota enforcer downstream (it reads the caps from this Tier), so
            # the degradation logs loud. Under DNA_QUOTA_REQUIRE_TIERS (the
            # hosted shape, i-051) it does not degrade at all: the failure
            # PROPAGATES so the metered call fails instead of the billing.
            if _quota_requires_tiers():
                raise
            logger.warning(
                "tier: registry query failed for %r (quota enforcement "
                "degrades to no-tier): %s",
                tier_id_or_alias, e,
            )
            return None
        # First pass: exact tier_id match.
        for r in rows:
            if (r.get("spec") or {}).get("tier_id") == tier_id_or_alias:
                return r
        # Second pass: alias match.
        for r in rows:
            if tier_id_or_alias in ((r.get("spec") or {}).get("aliases") or []):
                return r
        return None

    async def account_plan(self, account_id: str) -> dict | None:
        """Resolve an AccountPlan (an ACCOUNT→Tier assignment) from the _lib
        registry by ``spec.account_id``.

        Returns the RAW DICT row (kernel.query yields raw dicts, not
        Documents — callers read plan["spec"]["tier_id"]) or None when no
        assignment exists for ``account_id``.

        This is the billing→enforcement bridge read. **The subscription belongs
        to the BILLING ACCOUNT, not to a workspace** — ONE AccountPlan covers
        every workspace whose ``Workspace.account_id`` matches, so creating a
        second workspace is never a second charge and never needs a second write.
        dna-cloud's Stripe webhook writes the doc; the MCP quota guard reads it
        here (after :meth:`account_for_workspace`) when a token carries no
        explicit plan claim.

        The ``account_id`` is OPAQUE to this lookup — matched, never parsed.

        **Fail-closed on a blank key.** A blank/None ``account_id`` returns
        ``None`` WITHOUT querying: it must never be able to match a doc whose
        ``spec.account_id`` is itself blank or absent, which would hand a
        workspace with no account whatever tier that malformed doc names. No
        account ⇒ no plan ⇒ the Free floor, always.

        _lib-direct — AccountPlan is NOT in _INHERITABLE_KINDS so inheritance
        does not surface it. No alias pass: the match is on ``account_id``.
        """
        if not (account_id or "").strip():
            return None  # fail-closed — see the docstring.
        try:
            rows = [
                r async for r in self._k.query(
                    self._ACCOUNT_PLAN_REGISTRY_SCOPE, "AccountPlan"
                )
            ]
        except Exception as e:  # noqa: BLE001
            # fail-soft: registry read — a silent None means the guard falls
            # back to the Free floor for this account, so the degradation logs
            # loud rather than silently downgrading a paying account.
            logger.warning(
                "account_plan: registry query failed for %r (enforcement "
                "degrades to no-assignment / Free floor): %s",
                account_id, e,
            )
            return None
        for r in rows:
            if (r.get("spec") or {}).get("account_id") == account_id:
                return r
        return None

    async def account_for_workspace(self, workspace_id: str) -> str | None:
        """The BILLING ACCOUNT id a workspace belongs to — ``Workspace.account_id``.

        The FIRST half of the enforcement resolution ``workspace → account_id →
        AccountPlan``. Returns ``None`` when the workspace is unknown, carries no
        ``account_id``, or the registry read fails.

        **Every ``None`` here is a Free-floor outcome, never a permissive one.**
        There is deliberately no fallback that treats the workspace_id itself as
        an account: that would resurrect the per-workspace plan model this
        replaced, as a silent default nobody would notice — every workspace whose
        account failed to record would quietly become its own billing account
        instead of failing closed. A workspace created before ``account_id``
        existed is fixed by DATA (re-run ``scripts/seed_workspace_one.py``, which
        backfills it), not by a permanent code special case.

        Both the workspace_id and the account_id are OPAQUE — matched, never
        parsed. _lib-direct + fail-soft (a registry glitch degrades to ``None``,
        logged loud).
        """
        if not (workspace_id or "").strip():
            return None
        try:
            rows = [
                r async for r in self._k.query(
                    self._WORKSPACE_REGISTRY_SCOPE, "Workspace"
                )
            ]
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "account_for_workspace: registry query failed for %r (enforcement "
                "degrades to no-account / Free floor): %s",
                workspace_id, e,
            )
            return None
        for r in rows:
            spec = r.get("spec") or {}
            if spec.get("workspace_id") == workspace_id:
                account_id = (spec.get("account_id") or "").strip()
                return account_id or None
        return None

    async def workspace_memberships(self) -> list[dict]:
        """List EVERY ``WorkspaceMembership`` grant from the _lib registry (ADR
        "Model B").

        Returns the RAW DICT rows (callers read ``m["spec"][...]``) — the full
        set, unfiltered: the auth→workspace resolver
        (:func:`dna.tenancy.resolution.workspace_for_identity`) filters by the
        VERIFIED identity in pure core. An EMPTY list is meaningful: it means the
        source never opted into workspaces (OSS / pre-Model-B), and the auth
        bridge then falls back to the legacy tid tenancy — so this must
        distinguish "no grants configured" ([]) from a read failure.

        _lib-direct — WorkspaceMembership is GLOBAL and NOT in _INHERITABLE_KINDS
        so per-scope inheritance does not surface it. Fail-soft: a registry glitch
        degrades to ``[]`` (logged loud). NOTE the deny-on-no-membership
        invariant lives in the resolver, not here — a fail-soft ``[]`` on a
        transient error deliberately degrades to the legacy path, never to
        "all workspaces"."""
        try:
            return [
                r async for r in self._k.query(
                    self._WORKSPACE_MEMBERSHIP_REGISTRY_SCOPE, "WorkspaceMembership"
                )
            ]
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "workspace_memberships: registry query failed (auth resolution "
                "degrades to the legacy tid path): %s", e,
            )
            return []

    async def workspaces(self) -> list[dict]:
        """List every ``Workspace`` doc from the _lib registry (ADR "Model B").

        Returns the RAW DICT rows (callers read ``w["spec"][...]``) — the full,
        UNFILTERED set. This is the tenancy-root inventory, not an authorization
        surface: ``GET /v1/workspaces`` filters it down to the caller's ACTIVE
        memberships in pure core (``list_workspaces_impl``), and the workspace
        creation path uses it only to keep slugs unique. Never hand this list to a
        caller unfiltered.

        _lib-direct — Workspace is GLOBAL and NOT in _INHERITABLE_KINDS, so a
        per-scope query would silently no-op. Fail-soft: a registry glitch (or a
        source that has no ``_lib`` yet) degrades to ``[]``, logged loud. ``[]``
        is meaningful and safe here: it means "no workspaces to show / no slug
        taken", never "everything"."""
        try:
            return [
                r async for r in self._k.query(
                    self._WORKSPACE_REGISTRY_SCOPE, "Workspace"
                )
            ]
        except Exception as e:  # noqa: BLE001
            logger.warning("workspaces: registry query failed: %s", e)
            return []

    async def voice_policy(self, name: str = "default") -> dict | None:
        """Resolve a VoicePolicy from the _lib registry by metadata name.

        Returns the RAW DICT row (callers read policy["spec"][...]) or None
        when no match is found. _lib-direct — VoicePolicy is NOT in
        _INHERITABLE_KINDS so per-scope inheritance does not surface it.
        """
        try:
            rows = [
                r async for r in self._k.query(self._VOICE_POLICY_SCOPE, "VoicePolicy")
            ]
        except Exception as e:  # noqa: BLE001
            # fail-soft: registry read — a silent None means voice callers
            # proceed without policy, so the degradation logs loud.
            logger.warning(
                "voice_policy: registry query failed for %r: %s", name, e,
            )
            return None
        for r in rows:
            meta = r.get("metadata") or {}
            if (meta.get("name") or r.get("name")) == name:
                return r
        # Fall back to the first policy if the named one is absent but some
        # policy exists — a single unnamed default is the common case.
        return rows[0] if rows else None

    async def embedding_profile(self, name: str = "default") -> dict | None:
        """Resolve the embedding profile from the _lib CognitivePolicy by name.

        Returns a RAW-DICT-shaped row whose ``spec`` is the doc's ``embedding``
        section (callers read profile["spec"][...]) or None when the _lib doc
        is absent or carries no ``embedding`` section. _lib-direct — a single
        global default is the common case.
        """
        try:
            rows = [
                r async for r in self._k.query(self._EMBEDDING_PROFILE_SCOPE, "CognitivePolicy")
            ]
        except Exception as e:  # noqa: BLE001
            # fail-soft: registry read — a silent None forks embedding-space
            # defaults for callers, so the degradation logs loud.
            logger.warning(
                "embedding_profile: registry query failed for %r: %s", name, e,
            )
            return None
        chosen = None
        for r in rows:
            meta = r.get("metadata") or {}
            if (meta.get("name") or r.get("name")) == name:
                chosen = r
                break
        if chosen is None:
            chosen = rows[0] if rows else None
        if chosen is None:
            return None
        emb = (chosen.get("spec") or {}).get("embedding")
        if not isinstance(emb, dict) or not emb:
            return None
        return {**chosen, "spec": emb}
