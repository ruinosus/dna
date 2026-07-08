"""LayerPolicyEnforcer — the kernel's layer-write policy check, extracted from
the Kernel god-object (kernel-decompose-continue).

Behavior-preserving: the LOCKED / RESTRICTED / OPEN enforcement (Phase 16) moves
verbatim; the kernel keeps ``_check_layer_policy`` / ``_check_layer_policy_async``
/ ``_enforce_layer_policy_with_mi`` as thin delegators (only ``write_document``
calls the async one internally; no external caller). Holds a back-ref to the
kernel for the accessors it needs (base-MI cache, non-overlayable set, alias).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import LayerPolicyHost

_logger = logging.getLogger(__name__)


class LayerPolicyEnforcer:
    """Enforces per-layer write policy (LayerPolicy docs + the structurally
    non-overlayable allowlist). One instance per Kernel; holds a back-ref."""

    def __init__(self, kernel: "LayerPolicyHost") -> None:
        self._k = kernel

    async def check_async(
        self, scope: str, kind: str, name: str, raw: dict, layer: tuple[str, str],
    ) -> None:
        """Async-native policy check — loads the base MI via the async path so
        callers inside an event loop don't trip the sync-in-loop guard. Same
        semantics as ``check``."""
        from dna.kernel.protocols import LayerPolicy, LayerPolicyViolationError
        try:
            mi_base = await self._k._base_instance_cached_async(scope)
        except Exception as e:  # noqa: BLE001 — no base MI → nothing to enforce
            _logger.debug(
                "layer policy check: base MI unavailable for scope %r: %r", scope, e,
            )
            return
        return self._enforce(
            mi_base, scope, kind, name, raw, layer,
            LayerPolicy=LayerPolicy,
            LayerPolicyViolationError=LayerPolicyViolationError,
        )

    def check(
        self, scope: str, kind: str, name: str, raw: dict, layer: tuple[str, str],
    ) -> None:
        """Sync entry point (non-async callers). Policy modes (resolved via alias
        ``<owner>-<kind>``): LOCKED (any write raises), RESTRICTED (adding a new
        doc, or a new top-level spec key on an existing doc, raises; overriding
        existing keys is allowed), OPEN (default — never raises). No Module/
        LayerPolicy doc → OPEN."""
        from dna.kernel.protocols import LayerPolicy, LayerPolicyViolationError
        try:
            mi_base = self._k._base_instance_cached(scope)
        except Exception as e:  # noqa: BLE001 — no base MI → OPEN (mock sources/tests)
            _logger.debug(
                "layer policy check: base MI unavailable for scope %r: %r", scope, e,
            )
            return
        return self._enforce(
            mi_base, scope, kind, name, raw, layer,
            LayerPolicy=LayerPolicy,
            LayerPolicyViolationError=LayerPolicyViolationError,
        )

    def _enforce(
        self, mi_base, scope: str, kind: str, name: str, raw: dict,
        layer: tuple[str, str], *, LayerPolicy, LayerPolicyViolationError,
    ) -> None:
        """Shared policy-enforcement body — the LOCKED/RESTRICTED/OPEN semantics
        in ONE place. The hardcoded non-overlayable allowlist runs first
        (independent of LayerPolicy docs); then the per-layer policy resolved
        from LayerPolicy docs in the scope."""
        layer_id, _ = layer

        # Hardcoded allowlist runs FIRST — independent of LayerPolicy docs.
        if kind in self._k._NON_OVERLAYABLE_KINDS:
            raise LayerPolicyViolationError(
                f"{kind} is structurally non-overlayable; "
                f"cannot write to layer '{layer_id}'"
            )

        alias = self._k._alias_for(kind)

        # Pick the LayerPolicy doc whose spec.layer_id matches the layer being
        # written (last match wins, matching mi.all iteration order).
        policy_str = "open"
        try:
            layer_policy_docs = mi_base._all("LayerPolicy")
        except Exception as e:  # noqa: BLE001
            # fail-soft: unreadable LayerPolicy docs → OPEN (same posture as
            # the missing-base-MI guard above) — logged, never silent.
            _logger.debug(
                "layer policy check: LayerPolicy docs unavailable for scope "
                "%r (policy=OPEN): %r", scope, e,
            )
            layer_policy_docs = []
        for lp_doc in layer_policy_docs:
            try:
                lp_spec = lp_doc.spec or {}
                if lp_spec.get("layer_id") != layer_id:
                    continue
                lp_policies = lp_spec.get("policies") or {}
                if not isinstance(lp_policies, dict):
                    continue
                value = lp_policies.get(alias)
                if value:
                    policy_str = str(value).lower()
            except Exception as e:  # noqa: BLE001
                # fail-soft: one malformed LayerPolicy doc is skipped — but a
                # skipped doc means the policy the operator DECLARED is not
                # being enforced, so it logs loud.
                _logger.warning(
                    "layer policy check: malformed LayerPolicy doc %r in "
                    "scope %r ignored: %s", lp_doc.name, scope, e,
                )
                continue

        try:
            policy = LayerPolicy(policy_str)
        except ValueError:
            policy = LayerPolicy.OPEN
        if policy == LayerPolicy.LOCKED:
            raise LayerPolicyViolationError(
                f"{alias} is LOCKED in layer '{layer_id}' per LayerPolicy docs"
            )
        if policy == LayerPolicy.RESTRICTED:
            existing = mi_base._one(kind, name)
            if existing is None:
                raise LayerPolicyViolationError(
                    f"{alias} in layer '{layer_id}' is RESTRICTED — "
                    f"cannot add new document '{name}' not present in base"
                )
            new_keys = set((raw.get("spec") or {}).keys())
            existing_raw = getattr(existing, "raw", None) or {}
            existing_spec_raw = existing_raw.get("spec") if isinstance(existing_raw, dict) else None
            if isinstance(existing_spec_raw, dict):
                existing_keys = set(existing_spec_raw.keys())
            else:
                existing_spec = (
                    existing.spec
                    if hasattr(existing, "spec") and existing.spec is not None
                    else {}
                )
                existing_keys = (
                    set(existing_spec.keys()) if hasattr(existing_spec, "keys") else set()
                )
            added = new_keys - existing_keys
            if added:
                raise LayerPolicyViolationError(
                    f"{alias} in layer '{layer_id}' is RESTRICTED — "
                    f"cannot add new top-level spec keys {sorted(added)}; "
                    f"may only override existing"
                )
        # OPEN: allow
