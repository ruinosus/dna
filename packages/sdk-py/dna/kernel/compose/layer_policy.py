"""LayerPolicyEnforcer — the kernel's layer-write policy check, extracted from
the Kernel god-object (kernel-decompose-continue).

Behavior-preserving: the LOCKED / RESTRICTED / OPEN enforcement (Phase 16) moves
verbatim; the kernel keeps ``_check_layer_policy`` / ``_check_layer_policy_async``
/ ``_enforce_layer_policy_with_mi`` as thin delegators (only ``write_document``
calls the async one internally; no external caller). Holds a back-ref to the
kernel for the accessors it needs (base-MI cache, non-overlayable set, alias,
Kind-port lookup).

Also home to the per-FIELD allowlist gate — ``KindPort.OVERLAYABLE_FIELDS``.
That one is deliberately WRITE-PATH ONLY (see
``non_overlayable_changes`` and ``DefaultLayerResolver.__init__``): it
constrains what a layer may AUTHOR through the runtime, not how documents
already stored are composed.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import LayerPolicyHost

_logger = logging.getLogger(__name__)

_MISSING = object()

# ``timeline`` is append-only across overlays REGARDLESS of policy (ADR
# 2026-05-10): the merge port concatenates a layer's events even onto a LOCKED
# document. Refusing the write that records them would make the field
# allowlist the one rule in the system able to break that contract, so it is
# exempt — a Kind author never has to remember to list it.
_ALLOWLIST_EXEMPT_KEYS = frozenset({"timeline"})


def non_overlayable_changes(
    overlay_spec: dict[str, Any] | None,
    base_spec: dict[str, Any] | None,
    allowlist: "frozenset[str] | None",
) -> list[str]:
    """THE per-field allowlist rule.

    Returns the sorted top-level spec keys that ``overlay_spec`` would CHANGE
    and that ``allowlist`` does not permit a layer to change. Empty list = the
    overlay is admissible.

    Two things make this the rule rather than plain key membership:

    * ``allowlist is None`` means the Kind declares NO per-field restriction,
      so nothing is ever reported. That is the default for every Kind
      (``KindBase.OVERLAYABLE_FIELDS``); an explicitly declared EMPTY set, by
      contrast, forbids every change and is honoured as such.
    * a non-allowlisted key written back at its BASE value is not an
      override, so it is not a violation. Consumers submit whole effective
      specs — read-only fields included, at their inherited values — and that
      has to stay a no-op rather than a 403.
    """
    if allowlist is None:
        return []
    base = base_spec or {}
    return sorted(
        key
        for key, value in (overlay_spec or {}).items()
        if key not in allowlist
        and key not in _ALLOWLIST_EXEMPT_KEYS
        and base.get(key, _MISSING) != value
    )


class LayerPolicyEnforcer:
    """Enforces per-layer write policy: the structurally non-overlayable Kind
    set, the operator's LayerPolicy docs, and the Kind author's per-field
    ``OVERLAYABLE_FIELDS`` allowlist. One instance per Kernel; holds a
    back-ref. See ``_enforce`` for how the three gates compose."""

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
        """Sync entry point (non-async callers). Policy modes (key resolved by
        the SHARED ``match_policy_key`` — exact Kind name → declared alias →
        legacy suffixes — same as the read/merge port, i-049): LOCKED (any
        write raises), RESTRICTED (adding a new
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
        in ONE place, plus the Kind's per-field allowlist.

        Three gates, coarse → fine, so a refusal always names the broadest
        reason it was refused for:

        1. the structurally non-overlayable Kind set (derived from
           ``KindPort.is_overlayable``) — independent of any document;
        2. the per-layer LayerPolicy verdict (LOCKED / RESTRICTED / OPEN)
           resolved from the scope's LayerPolicy docs — what the OPERATOR
           declared;
        3. the Kind's ``OVERLAYABLE_FIELDS`` allowlist — what the Kind
           AUTHOR declared about individual spec fields.

        (2) and (3) compose by CONJUNCTION: a write must satisfy both, and
        neither can widen the other. LayerPolicy OPEN does not unlock a
        field the Kind never allowed; an allowlist does not unlock a Kind
        the operator LOCKED."""
        layer_id, _ = layer

        # Hardcoded allowlist runs FIRST — independent of LayerPolicy docs.
        if kind in self._k._NON_OVERLAYABLE_KINDS:
            raise LayerPolicyViolationError(
                f"{kind} is structurally non-overlayable; "
                f"cannot write to layer '{layer_id}'"
            )

        alias = self._k._alias_for(kind)

        # Pick the LayerPolicy doc whose spec.layer_id matches the layer being
        # written (last match wins, matching mi.all iteration order). The key
        # inside each doc's ``policies`` map is resolved by the SAME resolver
        # the read/merge port uses (``match_policy_key``, i-049): before this,
        # the write port accepted the key ONLY by alias, so ``Agent: locked``
        # (keyed by Kind name) locked the merge but was silently ignored
        # here — the declared protection held on one port and not the other.
        from dna.kernel.compose.layer_resolver import match_policy_key
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
                value = match_policy_key(kind, lp_policies, declared_alias=alias)
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
            added = new_keys - set(_base_spec(existing))
            if added:
                raise LayerPolicyViolationError(
                    f"{alias} in layer '{layer_id}' is RESTRICTED — "
                    f"cannot add new top-level spec keys {sorted(added)}; "
                    f"may only override existing"
                )
        # OPEN: the operator allows the Kind in this layer. Gate 3 — the Kind
        # AUTHOR's per-field allowlist — still applies, and applies under
        # RESTRICTED too: the two constraints intersect, they never widen
        # each other. Runs LAST so a LOCKED/RESTRICTED refusal keeps its own
        # (broader, more actionable) message.
        self._check_overlayable_fields(
            mi_base, kind, name, raw, layer_id, alias, LayerPolicyViolationError,
        )

    def _check_overlayable_fields(
        self, mi_base, kind: str, name: str, raw: dict, layer_id: str,
        alias: str, LayerPolicyViolationError,
    ) -> None:
        """Gate 3: refuse a layer write that CHANGES a top-level spec key the
        Kind's ``OVERLAYABLE_FIELDS`` allowlist does not cover.

        WRITE PATH ONLY — unlike gate 2, this is not mirrored on the merge
        port, and that asymmetry is deliberate. A LayerPolicy doc is written
        by the scope OPERATOR, who opts into it per scope, so re-applying it
        on merge only affects deployments that asked for it. The field
        allowlist is declared globally by the Kind AUTHOR, so enforcing it on
        merge would retroactively rewrite overlays already stored in every
        deployment — silently changing composed prompts nobody edited. It
        would also break a working feature: a tenant-published Genome
        legitimately carries ``owner_tenant``, which Genome's own allowlist
        excludes (``test_load_manifest_tenant_phase9``). The gate belongs on
        what a layer may AUTHOR; merge stays faithful to what is stored.

        A Kind that declares nothing (``OVERLAYABLE_FIELDS is None``, the
        default) is unrestricted and short-circuits before any MI read."""
        port = self._k.kind_port_for(kind)
        allowlist = getattr(port, "OVERLAYABLE_FIELDS", None) if port else None
        if allowlist is None:
            return
        try:
            base = _base_spec(mi_base._one(kind, name))
        except Exception as e:  # noqa: BLE001 — no base → every key is a change
            _logger.debug(
                "overlayable-fields check: base doc unavailable for %s/%s: %r",
                kind, name, e,
            )
            base = {}
        offending = non_overlayable_changes(raw.get("spec") or {}, base, allowlist)
        if offending:
            raise LayerPolicyViolationError(
                f"{alias} field(s) {offending} are not overlayable; layer "
                f"'{layer_id}' may only change {sorted(allowlist)}"
            )


def _base_spec(doc) -> dict:
    """The base document's raw top-level spec mapping, or ``{}``.

    Prefers ``doc.raw['spec']`` (the authored dict) over ``doc.spec`` (which
    may be a typed model on some Kinds) — the same preference the RESTRICTED
    key-diff has always used, now shared with the field-allowlist check."""
    if doc is None:
        return {}
    raw = getattr(doc, "raw", None) or {}
    spec_raw = raw.get("spec") if isinstance(raw, dict) else None
    if isinstance(spec_raw, dict):
        return spec_raw
    spec = getattr(doc, "spec", None)
    return spec if isinstance(spec, dict) else {}
