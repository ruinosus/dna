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
from typing import TYPE_CHECKING

from dna.kernel.protocols import SYSTEM_SCOPE

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import RegistryAccessorHost

logger = logging.getLogger(__name__)


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
            # the degradation logs loud.
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
