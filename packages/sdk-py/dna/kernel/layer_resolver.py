"""DefaultLayerResolver — overlay resolution with per-kind policies.

Kernel-owned since s-invert-layer-resolver-dep (2026-07-07): layer
resolution is a core kernel responsibility, so the default resolver
lives in the kernel package — the kernel must work with ZERO extensions
loaded. Previously at ``dna.extensions.helix.layers`` (which
remains as a deprecated reexport shim).

Iterates layer dimensions, loads overlays from the source,
and merges with per-kind policies (open/restricted/locked).
The resolver is fully generic: it depends only on the stdlib and
``kernel.protocols.LayerPolicy`` — no extension models or constants.
"""
from __future__ import annotations

import copy
import logging
import warnings
from typing import Any

from dna.kernel.protocols import LayerPolicy

logger = logging.getLogger(__name__)


def match_policy_key(
    kind: str,
    policies: dict[str, Any],
    declared_alias: str | None = None,
) -> Any | None:
    """THE policy-key resolver — shared by BOTH policy ports (i-049).

    Given a Kind name and a ``policies`` mapping (keys are Kind names or
    aliases; values are whatever the caller stores — ``LayerPolicy`` enums on
    the read/merge port, raw strings on the write port), return the entry
    that governs ``kind``, or ``None`` when nothing matches (the CALLER
    decides the fallback posture — the read port warns loudly, i-044).

    Lookup order (the i-044 contract):
      1. exact Kind name (``Agent``) — legacy ``Module.spec.layers`` form;
      2. ``declared_alias`` — the Kind's DECLARED alias from the kind
         registry, the canonical non-inferred path;
      3. legacy string heuristics (lowercase / hyphen-suffix /
         CamelCase→kebab) — kept only for callers without a registry map.

    Extracted from ``DefaultLayerResolver._policy_for_kind`` so the write
    port (``LayerPolicyEnforcer._enforce``) resolves the key IDENTICALLY:
    before i-049 the write port accepted ONLY the alias, so an
    ``Agent: locked`` (keyed by name) locked the merge but was silently
    ignored on write — the same declared protection held on one port and
    not the other. One resolver, one answer."""
    if kind in policies:
        return policies[kind]
    # Declared alias from the registry — exact, no inference.
    if declared_alias is not None and declared_alias in policies:
        return policies[declared_alias]
    kind_lower = kind.lower()
    # Heuristic: hyphen-suffix alias match (legacy from when
    # policies dict could be keyed by tail-of-alias).
    for alias, policy in policies.items():
        if alias.endswith(f"-{kind_lower}") or alias == kind_lower:
            return policy
    # Phase 16 alias match: convert kind to its alias-tail by
    # CamelCase → kebab-case (Agent → agent), then
    # match aliases ending in that tail.
    import re
    kebab = re.sub(r"(?<!^)(?=[A-Z])", "-", kind).lower()
    for alias, policy in policies.items():
        if alias.endswith(f"-{kebab}") or alias == kebab:
            return policy
    return None


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dicts. Overlay wins. Lists are replaced, dicts merged recursively."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _merge_timeline_arrays(
    base_spec: dict[str, Any],
    overlay_spec: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Concat + dedup + sort base.spec.timeline and overlay.spec.timeline
    (per ADR 2026-05-10). Returns the merged list when EITHER side has
    a timeline array; None when neither does (caller skips merging).

    Dedup key: ``at + actor + type + (from + to | summary)``.

    Sort: descending by ``at`` (newest first, matches Studio
    TimelineView convention).
    """
    base_tl = base_spec.get("timeline") or []
    overlay_tl = overlay_spec.get("timeline") or []
    if not isinstance(base_tl, list):
        base_tl = []
    if not isinstance(overlay_tl, list):
        overlay_tl = []
    if not base_tl and not overlay_tl:
        return None

    seen: set[tuple[Any, ...]] = set()
    merged: list[dict[str, Any]] = []
    for ev in [*base_tl, *overlay_tl]:
        if not isinstance(ev, dict):
            continue
        key = (
            ev.get("at"),
            ev.get("actor"),
            ev.get("type"),
            ev.get("from"),
            ev.get("to"),
            ev.get("summary"),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(copy.deepcopy(ev))
    # Stable sort: newest first, fall back to original list order on tie.
    merged.sort(key=lambda e: e.get("at", ""), reverse=True)
    return merged


def _stamp_overlay_metadata(
    doc: dict[str, Any],
    *,
    overlay_fields: list[str] | None,
) -> None:
    """In-place: write ``has_overlay`` + ``overlay_fields`` into doc.metadata.

    Studio's editor banners + per-field markers read these. Phase 2
    overlay UX. Idempotent — re-merging a doc with new overlay keys
    UNIONS the field list so the user sees every field touched
    across all layer dimensions, not just the last one applied.

    ``overlay_fields=None`` means "the entire doc came from the
    overlay" (overlay-only add, no base to diff against). Frontend
    treats this distinctly from an empty list.
    """
    md = doc.setdefault("metadata", {})
    md["has_overlay"] = True
    if overlay_fields is None:
        # Sentinel: overlay-only add. Don't union, don't list fields —
        # the whole doc IS the overlay.
        md["overlay_fields"] = None
        return
    existing = md.get("overlay_fields")
    if existing is None:
        # Either not set, or a previous layer marked it as overlay-only.
        # An overlay-only doc shouldn't be re-stamped with field list,
        # but if it does happen we prefer the conservative None.
        md["overlay_fields"] = list(overlay_fields)
        return
    if isinstance(existing, list):
        merged = list(existing)
        for f in overlay_fields:
            if f not in merged:
                merged.append(f)
        md["overlay_fields"] = merged


class DefaultLayerResolver:
    """Merges layer overlay documents into base documents, applying policies by kind alias.

    Policies map: { kind_alias_or_kind_name: LayerPolicy }
    - open: deep merge spec (or add new documents)
    - restricted: only override existing keys in spec
    - locked: block changes (warn only)
    """

    def __init__(self, kind_aliases: dict[str, str] | None = None) -> None:
        # Declared Kind-name → alias map (from the kind registry). When
        # present, policy lookup is DECLARED, not inferred from name shape
        # (i-044) — the string heuristics below survive only as legacy
        # fallback for callers that can't supply the map.
        self._kind_aliases: dict[str, str] = dict(kind_aliases or {})
        # Kinds already warned about (unmatched-policy fallback) — one
        # warning per kind per resolver instance, not one per document.
        self._warned_fallback_kinds: set[str] = set()

    def resolve(
        self,
        base_documents: list[dict[str, Any]],
        layers: dict[str, str],
        source: Any,
        scope: str,
        policies: dict[str, LayerPolicy],
    ) -> list[dict[str, Any]]:
        result = [copy.deepcopy(doc) for doc in base_documents]

        for layer_id, value in layers.items():
            overlay_docs = source.load_layer(scope, layer_id, value)
            if not overlay_docs:
                continue
            result = self._merge_all(result, overlay_docs, policies, layer_id, value)

        return result

    def _merge_all(
        self,
        base_docs: list[dict[str, Any]],
        overlay_docs: list[dict[str, Any]],
        policies: dict[str, LayerPolicy],
        layer_id: str,
        value: str,
    ) -> list[dict[str, Any]]:
        result = [copy.deepcopy(doc) for doc in base_docs]

        base_index: dict[tuple[str, str], int] = {}
        for i, doc in enumerate(result):
            kind = doc.get("kind", "")
            name = doc.get("metadata", {}).get("name", "")
            if kind and name:
                base_index[(kind, name)] = i

        for overlay_doc in overlay_docs:
            overlay_kind = overlay_doc.get("kind", "")
            overlay_name = overlay_doc.get("metadata", {}).get("name", "")
            policy = self._policy_for_kind(overlay_kind, policies)

            match_key = (overlay_kind, overlay_name)

            if match_key in base_index:
                idx = base_index[match_key]
                result[idx] = self._apply_merge(result[idx], overlay_doc, policy, layer_id, value)
            else:
                if policy == LayerPolicy.LOCKED:
                    warnings.warn(
                        f"Layer '{layer_id}={value}' tried to add '{overlay_kind}/{overlay_name}' "
                        f"but policy is locked. Ignored.",
                        stacklevel=3,
                    )
                elif policy == LayerPolicy.RESTRICTED:
                    warnings.warn(
                        f"Layer '{layer_id}={value}' tried to add '{overlay_kind}/{overlay_name}' "
                        f"but policy is restricted. Ignored.",
                        stacklevel=3,
                    )
                else:
                    # Overlay-only add — no base to diff against. Stamp
                    # ``has_overlay=true, overlay_fields=null`` so the
                    # frontend knows "the whole doc is your overlay".
                    new_doc = copy.deepcopy(overlay_doc)
                    _stamp_overlay_metadata(new_doc, overlay_fields=None)
                    result.append(new_doc)

        return result

    def _policy_for_kind(self, kind: str, policies: dict[str, LayerPolicy]) -> LayerPolicy:
        """Resolve policy for a kind. Falls back to OPEN — NOISILY — when a
        non-empty policy set matches nothing (i-044).

        Key resolution delegates to :func:`match_policy_key` — the ONE
        resolver both policy ports share (i-049): the write port
        (``LayerPolicyEnforcer``) resolves through the same function, so a
        policy key that locks the merge locks the write too.

        The fallback contract: OPEN is a fine default when NO policies are
        declared (that scope opted out of a policy regime). But when the
        operator DID declare policies and this kind matched none of them,
        degrading to OPEN silently is how a typo'd alias turns ``locked``
        into ``open`` — so that path warns, once per kind per resolver.
        """
        declared_alias = self._kind_aliases.get(kind)
        matched = match_policy_key(kind, policies, declared_alias)
        if matched is not None:
            return matched
        if policies and kind not in self._warned_fallback_kinds:
            self._warned_fallback_kinds.add(kind)
            warnings.warn(
                f"No LayerPolicy entry matched Kind '{kind}'"
                + (f" (declared alias '{declared_alias}')" if declared_alias else "")
                + f"; assuming OPEN. Declared policy keys: "
                f"{sorted(policies)}. If this Kind was meant to be "
                f"restricted/locked, check the policy key for a typo — a "
                f"mismatched alias silently degrades the policy to OPEN.",
                stacklevel=4,
            )
        return LayerPolicy.OPEN

    def _apply_merge(
        self,
        base: dict[str, Any],
        overlay: dict[str, Any],
        policy: LayerPolicy,
        layer_id: str,
        value: str,
    ) -> dict[str, Any]:
        spec_overlay = overlay.get("spec", {})
        spec_base = base.get("spec", {})

        # Timeline is append-only across overlays — concat+sort regardless
        # of policy (even LOCKED), since events recorded against an
        # overlay describe what happened on that overlay and shouldn't
        # be silently dropped. ADR 2026-05-10.
        merged_timeline = _merge_timeline_arrays(spec_base, spec_overlay)

        if not spec_overlay and merged_timeline is None:
            return base

        if policy == LayerPolicy.LOCKED:
            if merged_timeline is None:
                name = base.get("metadata", {}).get("name", "")
                warnings.warn(
                    f"Layer '{layer_id}={value}' tried to modify locked document '{name}'. Ignored.",
                    stacklevel=4,
                )
                return base
            # Timeline-only overlay on a LOCKED doc still appends events.
            result = copy.deepcopy(base)
            result.setdefault("spec", {})["timeline"] = merged_timeline
            return result

        if policy == LayerPolicy.RESTRICTED:
            # Strip `timeline` from the restricted-merge call so the
            # "unknown key" warning doesn't fire when only timeline
            # changed; we re-attach the merged list afterwards.
            spec_overlay_no_tl = {
                k: v for k, v in spec_overlay.items() if k != "timeline"
            }
            result = self._apply_restricted_merge(
                base, spec_overlay_no_tl, layer_id, value
            )
            if merged_timeline is not None:
                result.setdefault("spec", {})["timeline"] = merged_timeline
            return result

        # OPEN — deep merge spec
        result = copy.deepcopy(base)
        result["spec"] = deep_merge(spec_base, spec_overlay)
        if merged_timeline is not None:
            result["spec"]["timeline"] = merged_timeline
        if spec_overlay:
            # Phase 2 overlay UX: every top-level spec key the overlay
            # provided is "overridden" under OPEN policy (deep merge
            # always wins). Exclude `timeline` since it's append-only,
            # not an override — having timeline events on the overlay
            # shouldn't make the editor think every story field was
            # forked.
            overridden = [k for k in spec_overlay.keys() if k != "timeline"]
            if overridden:
                _stamp_overlay_metadata(result, overlay_fields=overridden)
        return result

    def _apply_restricted_merge(
        self,
        base: dict[str, Any],
        spec_overlay: dict[str, Any],
        layer_id: str,
        value: str,
    ) -> dict[str, Any]:
        """Restricted: only override existing keys in spec."""
        result = copy.deepcopy(base)
        spec_base = result.get("spec", {})

        # Track which overlay keys actually got applied — restricted
        # policy drops unknown keys, so the overlay_fields metadata
        # reflects what merged, not what the overlay tried to push.
        applied: list[str] = []
        for key, val in spec_overlay.items():
            if key not in spec_base:
                warnings.warn(
                    f"Layer '{layer_id}={value}' tried to add key '{key}' to restricted document. Ignored.",
                    stacklevel=5,
                )
                continue
            if isinstance(spec_base[key], dict) and isinstance(val, dict):
                spec_base[key] = deep_merge(spec_base[key], val)
            else:
                spec_base[key] = copy.deepcopy(val)
            applied.append(key)

        result["spec"] = spec_base
        if applied:
            _stamp_overlay_metadata(result, overlay_fields=applied)
        return result
