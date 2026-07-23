"""The kernel's unified composition motor (s-unify-composition-subsystems).

One module, four composition concerns that used to be spread over four
files with diverging semantics:

  1. **CompositionProfile (V1)** — declarative wiring registered by
     extensions ("here is how an orchestrator Kind connects to soul /
     skills / guardrails") + the UI hints (timeline, health-check,
     quadrant) the viz layer reads generically. Moved here from the old
     ``kernel/composition.py`` (now a deprecated re-export shim).

  2. **``validate_refs``** — THE cross-kind ref validation core. It is
     the single implementation behind ``mi.composition.validate()``
     (MI plane) and ``nav_kernel.validate_composition_async`` (source
     plane). Target resolution goes through
     ``KindRegistry.resolve_dep_filter_target`` — the same canonical
     resolver (alias contract + legacy ``kind=`` shim, s-alias) used by
     nav classification and kinds-api docs. The old three-reader
     asymmetry (each reader hand-rolling its own alias loop with
     different ``kind=`` / record semantics) is gone.

  3. **CompositionEngine** — the ``mi.composition`` namespace
     (validate / iter_doc_deps / consumers_of / dependency_tree). Moved
     here from the old ``kernel/composition_engine.py`` (deleted);
     ``validate()`` delegates to ``validate_refs``.

  4. **CompositionResolver** — the Composition-V2 chain-resolution
     engine (``resolve_document`` / ``personalize_document`` — cross-
     scope inheritance + tenant overlay + Catalog tier + merge).

Pure resolution TYPES + merge functions (ResolutionLayer,
ResolvedDocument, merge_override_full, merge_field_level, the
inheritance constants) stay in ``kernel/resolver.py`` — data shapes
with no engine dependency, imported by both this module and callers
that only need the types.

Record-plane rule (two-planes F2.5) — ONE rule for every reader:
a ref whose TARGET Kind is ``plane="record"`` resolves when present in
the doc index and is DEFERRED otherwise (records resolve lazily via the
kernel record plane — never false-``missing``). The MI plane excludes
records from materialization, so record refs always defer there; the
source plane sees records in its index, so present ones resolve. Same
rule, different inputs.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Container, Iterable, Literal, Mapping

from dna.kernel.kinds.registry import KindRegistry
from dna.kernel.protocols import CompositionResult

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import CompositionResolverHost
    from dna.kernel.document import Document
    from dna.kernel.instance import ManifestInstance
    from dna.kernel.protocols import KindPort

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 1. CompositionProfile (V1) — declarative kind-wiring + UI hints
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TimelineHint:
    label: str
    item_label: str


@dataclass(frozen=True)
class HealthCheckHint:
    rule: Literal["at-least-one", "has-error-severity"]
    severity: Literal["warn", "error"]
    issue_key: str
    message: str


@dataclass(frozen=True)
class QuadrantHint:
    axis: Literal["x", "y"]
    label: str
    max_scale: float


@dataclass(frozen=True)
class CompositionSlot:
    name: str
    target_alias: str
    cardinality: Literal["one", "many"]
    order: int
    filterable: bool = False
    timeline: TimelineHint | None = None
    health_check: HealthCheckHint | None = None
    quadrant: QuadrantHint | None = None


@dataclass(frozen=True)
class CompositionProfile:
    orchestrator_alias: str
    label: str
    slots: tuple[CompositionSlot, ...] = ()


def profile_for_orchestrator(
    profiles: list[CompositionProfile],
    orchestrator_alias: str,
) -> CompositionProfile | None:
    """Find the profile whose orchestrator matches a given alias."""
    return next(
        (p for p in profiles if p.orchestrator_alias == orchestrator_alias),
        None,
    )


# ──────────────────────────────────────────────────────────────────────
# 2. validate_refs — the shared cross-kind ref validation core
# ──────────────────────────────────────────────────────────────────────


def validate_refs(
    docs: Iterable["Document"],
    doc_index: Container[tuple[str, str]],
    kinds: Mapping[tuple[str, str], "KindPort"],
    registry: KindRegistry,
) -> CompositionResult:
    """Validate declared dep_filter refs of ``docs`` against ``doc_index``.

    The ONE implementation behind ``mi.composition.validate()`` and
    ``nav_kernel.validate_composition_async`` — both feed their own doc
    set/index but share resolution + classification semantics:

    - Target resolution via ``registry.resolve_dep_filter_target`` (the
      canonical s-alias resolver: alias contract + deprecated ``kind=``
      shim). Unresolvable target → ``warnings``.
    - Ref present in ``doc_index`` → ``resolved``.
    - Absent + target Kind is ``plane="record"`` → ``deferred`` (records
      resolve lazily via the kernel record plane; never false-missing).
    - Absent otherwise → ``missing``.
    """
    resolved: list[str] = []
    missing: list[str] = []
    warnings_: list[str] = []
    deferred: list[str] = []

    for doc in docs:
        kp = kinds.get((doc.api_version, doc.kind))
        if not kp:
            continue
        # dep_filters is a REQUIRED KindPort member (H1-gated) — call it
        # directly; no duck-typing needed for the core contract.
        filters = kp.dep_filters()
        if not filters:
            continue

        spec = doc.spec
        for spec_field, target_value in filters.items():
            target_kp = registry.resolve_dep_filter_target(target_value)
            if target_kp is None:
                warnings_.append(
                    f"{doc.kind}/{doc.name}: unknown alias '{target_value}' in dep_filters"
                )
                continue
            target_kind = target_kp.kind

            declared = spec.get(spec_field)
            if declared is None:
                continue
            refs = (
                [declared] if isinstance(declared, str)
                else (declared if isinstance(declared, list) else [])
            )

            target_is_record = (
                getattr(target_kp, "plane", "composition") == "record"
            )
            for ref_name in refs:
                label = f"{doc.kind}/{doc.name}.{spec_field}={ref_name} → {target_kind}/{ref_name}"
                if (target_kind, ref_name) in doc_index:
                    resolved.append(label)
                elif target_is_record:
                    deferred.append(label + " (record — resolved lazily)")
                else:
                    missing.append(label + " NOT FOUND")

    return CompositionResult(
        resolved=resolved, missing=missing, warnings=warnings_,
        deferred=deferred,
    )


# ──────────────────────────────────────────────────────────────────────
# 3. CompositionEngine — the ``mi.composition`` namespace
# ──────────────────────────────────────────────────────────────────────


class CompositionEngine:
    """Namespace for composition validation — accessed via ``mi.composition``."""

    def __init__(self, host: "ManifestInstance") -> None:
        self._host = host
        # Registry VIEW over the MI's kinds map (no copy) — gives this
        # namespace the same canonical dep_filter resolver the kernel uses.
        self._registry = KindRegistry(host._kinds)

    def validate(self) -> CompositionResult:
        """Validate cross-kind references over the MI plane.

        Equivalent to ``mi.composition_result``. Delegates to
        ``validate_refs`` — records are excluded from the MI
        materialization, so record-target refs land in ``deferred``
        (they resolve lazily via the kernel record plane at read time).
        """
        host = self._host
        doc_index = {(d.kind, d.name) for d in host.documents}
        return validate_refs(host.documents, doc_index, host._kinds, self._registry)

    def iter_doc_deps(self, doc: "Document") -> list[dict[str, Any]]:
        """Iterate a document's declared dep_filters dynamically.

        Equivalent to ``mi.iter_doc_deps(doc)``.

        Returns a list of ``{"label", "target_kind", "names"}`` dicts.
        """
        source_kp = self._host._kinds.get((doc.api_version, doc.kind))
        if source_kp is None:
            return []
        # dep_filters is a REQUIRED KindPort member (H1-gated) — direct call.
        filters = source_kp.dep_filters()
        if not filters:
            return []

        spec = doc.spec
        result: list[dict[str, Any]] = []
        for label, target_value in filters.items():
            target_kp = self._registry.resolve_dep_filter_target(target_value)
            if target_kp is None:
                continue
            target_kind = getattr(target_kp, "kind", None)
            if not target_kind:
                continue

            value = spec.get(label) if hasattr(spec, "get") else None
            if value is None or value == "" or value == []:
                continue
            if isinstance(value, str):
                names = [value]
            elif isinstance(value, list):
                names = [v for v in value if isinstance(v, str)]
            else:
                continue
            if not names:
                continue
            result.append({"label": label, "target_kind": target_kind, "names": names})
        return result

    def consumers_of(
        self, kind: str, name: str,
    ) -> list[dict[str, str]]:
        """Walk the manifest and return every doc that references this one.

        Equivalent to ``mi.consumers_of(kind, name)``.
        """
        from dna.kernel.preview import find_consumers
        return find_consumers(self._host, {"kind": kind, "name": name})

    def dependency_tree(self) -> dict[str, Any]:
        """Build a dependency tree for the manifest.

        Equivalent to ``mi.dependency_tree()``.
        """
        from dna.kernel.document import Document as Doc

        doc_index: dict[tuple[str, str], Doc] = {}
        for d in self._host.documents:
            doc_index[(d.kind, d.name)] = d

        tree: dict[str, Any] = {}

        for doc in self._host.documents:
            kp = self._host._kinds.get((doc.api_version, doc.kind))
            if not kp:
                continue
            filters = kp.dep_filters()
            if not filters:
                continue

            depends_on: dict[str, Any] = {}
            spec = doc.spec

            for spec_field, target_value in filters.items():
                target_kp = self._registry.resolve_dep_filter_target(target_value)
                if target_kp is None:
                    continue
                target_kind = target_kp.kind

                declared = spec.get(spec_field)
                if not declared:
                    continue

                refs = [declared] if isinstance(declared, str) else (declared if isinstance(declared, list) else [])

                deps: dict[str, Any] = {}
                for ref_name in refs:
                    dep_entry: dict[str, Any] = {"kind": target_kind}
                    ref_doc = doc_index.get((target_kind, ref_name))
                    if ref_doc:
                        dep_entry["found"] = True
                        desc = ref_doc.metadata.get("description", "")
                        if desc:
                            dep_entry["description"] = desc
                        extra = target_kp.summary(ref_doc)
                        if extra:
                            dep_entry.update(extra)
                    else:
                        dep_entry["found"] = False

                    deps[ref_name] = dep_entry

                if deps:
                    depends_on[spec_field] = deps

            if depends_on:
                tree[doc.name] = {
                    "kind": doc.kind,
                    "description": doc.metadata.get("description", ""),
                    "depends_on": depends_on,
                }

        return tree


# ──────────────────────────────────────────────────────────────────────
# 4. CompositionResolver — the Composition-V2 chain-resolution engine
# ──────────────────────────────────────────────────────────────────────


class CompositionResolver:
    """Composition-V2: resolve a doc through the scope/tenant chain.

    Extracted from the Kernel god-object (kernel-decompose-continue);
    the kernel keeps the public three (``resolve_document`` /
    ``composition_summary`` / ``personalize_document``) plus the two
    internal helpers as thin delegators. Holds a back-ref to the kernel
    for the accessors it needs (granular cache, source, query, write,
    storage, ``_layer_observers`` — the reverse-dep graph stays kernel
    state, shared with ``_invalidate_internal``).
    """

    def __init__(self, kernel: "CompositionResolverHost") -> None:
        self._k = kernel

    async def compute_resolution_chain(
        self, scope: str, tenant: str | None,
    ) -> list:
        """Walk ``Genome.spec.parent_scope`` transitively → ordered chain of
        ``(scope, tenant)`` pairs, HIGHEST priority first. Cycle-guarded; depth
        capped at MAX_RESOLUTION_DEPTH; missing Genome terminates the walk."""
        from dna.kernel.resolver import MAX_RESOLUTION_DEPTH
        k = self._k
        chain: list[tuple[str, str | None]] = []
        visited: set[str] = set()
        current: str | None = scope
        depth = 0
        while current and current not in visited and depth < MAX_RESOLUTION_DEPTH:
            visited.add(current)
            if tenant:
                chain.append((current, tenant))
            chain.append((current, None))
            # fail-soft: a scope absent on the source contributes no parent
            # (chain ends here instead of raising) — critical under the
            # inherit-by-default denylist where every read computes a chain.
            # Debug (hot path — one probe per chain step on broken sources).
            try:
                pkg_raw = await k._granular_doc_cached(
                    (current, "Genome", current, "")
                )
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "compute_resolution_chain: Genome read failed for scope "
                    "%r (chain ends here): %s", current, e,
                )
                pkg_raw = None
            parent: str | None = None
            if isinstance(pkg_raw, dict):
                spec = pkg_raw.get("spec") or {}
                if isinstance(spec, dict):
                    parent_val = spec.get("parent_scope")
                    if isinstance(parent_val, str) and parent_val:
                        parent = parent_val
            # V1 back-compat: when Genome omits parent_scope, escalate to the
            # legacy _INHERIT_PARENT_SCOPE (default _lib) so existing scopes
            # inherit without migration. Overridden once parent_scope is declared.
            if (
                parent is None
                and current != k._INHERIT_PARENT_SCOPE
                and k._INHERIT_PARENT_SCOPE not in visited
            ):
                parent = k._INHERIT_PARENT_SCOPE
            current = parent
            depth += 1
        return chain

    async def get_composition_rule(
        self, scope: str, kind: str,
    ) -> tuple[str, str, str]:
        """Resolve ``(scope_inheritance, merge_strategy, tenant_overlay)`` for
        ``(scope, kind)`` — from the scope's LayerPolicy composition_rules, else
        the inherit-by-default denylist (everything inherits from _lib
        except the per-scope ledger + structural Kinds)."""
        from dna.kernel.resolver import DEFAULT_NON_INHERITABLE_KINDS_V1
        k = self._k
        if k._source is not None:
            try:
                async for raw in k._source.query(  # type: ignore[attr-defined]
                    scope, "LayerPolicy", tenant=None,
                ):
                    spec = raw.get("spec") if isinstance(raw, dict) else None
                    if not isinstance(spec, dict):
                        continue
                    rules = spec.get("composition_rules")
                    if not isinstance(rules, dict):
                        continue
                    rule = rules.get(kind)
                    if isinstance(rule, dict):
                        return (
                            str(rule.get("scope_inheritance") or "disabled").lower(),
                            str(rule.get("merge_strategy") or "override_full").lower(),
                            str(rule.get("tenant_overlay") or "none").lower(),
                        )
            except Exception as e:  # noqa: BLE001
                # fail-soft: an unreadable LayerPolicy falls back to the
                # inherit-by-default rule — merge semantics silently change,
                # so the fallback is logged (debug: fires per resolve on a
                # broken source).
                logger.debug(
                    "get_composition_rule: LayerPolicy query failed for "
                    "scope=%r kind=%r (falling back to defaults): %s",
                    scope, kind, e,
                )
        if kind not in DEFAULT_NON_INHERITABLE_KINDS_V1:
            return ("enabled", "override_full", "field_level")
        # Non-inheritable Kinds STILL honor tenant overlay (TENANTED Canvas,
        # VoiceEpisode, Story must read tenant=X correctly).
        return ("disabled", "override_full", "field_level")

    async def resolve_document(
        self, scope: str, kind: str, name: str, *, tenant: str | None = None,
    ):
        """Resolve a doc through the composition chain (Phase 17). Returns a
        ResolvedDocument with merged doc + full provenance. Bootstrap Kinds
        bypass inheritance (local-only)."""
        from dna.kernel.resolver import (
            BOOTSTRAP_KINDS,
            ResolutionLayer,
            ResolutionPath,
            ResolvedDocument,
            merge_field_level,
            merge_override_full,
        )
        k = self._k

        # ── Bootstrap Kinds — local-only ─────────────────────────────
        if kind in BOOTSTRAP_KINDS:
            raw = await k._granular_doc_cached((scope, kind, name, tenant or ""))
            layer = ResolutionLayer(
                scope=scope, tenant=tenant, found=raw is not None,
                contributed=raw is not None,
            )
            return ResolvedDocument(
                doc=raw,
                provenance=ResolutionPath(steps=[layer]),
                is_inherited=False,
            )

        # ── Resolve composition rule ─────────────────────────────────
        scope_inh, merge_strat, tenant_ov = await self.get_composition_rule(scope, kind)

        # ── Build resolution chain ───────────────────────────────────
        # Catalog scopes that contributed THIS (kind,name) — used to surface
        # multi-package conflicts after the merge (Phase 3b ch4, i-112).
        catalog_layer_scopes: set[str] = set()
        if scope_inh == "disabled":
            # Local-only: bootstrap/structural Kinds never inherit AND never
            # pick up the Catalog tier (matches today's behavior exactly).
            chain: list[tuple[str, str | None]] = []
            if tenant and tenant_ov != "none":
                chain.append((scope, tenant))
            chain.append((scope, None))
        else:
            chain = await self.compute_resolution_chain(
                scope, tenant if tenant_ov != "none" else None,
            )
            # ── Splice the Catalog tier: Local > Catalog > Base ──────────
            # Insert the tenant's Catalog scopes IMMEDIATELY AFTER the local
            # scope's entries (the leading (scope, …) pairs) and BEFORE the
            # first parent — so the positional merge yields Local > Catalog >
            # Base while preserving merge_field_level (first contributor =
            # primary). Fail-soft: a Catalog glitch must never crash a resolve.
            try:
                catalog_scopes = await k._catalog_scopes(tenant, exclude={scope})
            except Exception as e:  # noqa: BLE001
                # fail-soft: a Catalog glitch must never crash a resolve —
                # _catalog_scopes itself warns on compute failure; this catches
                # anything past it (debug: resolve hot path).
                logger.debug(
                    "resolve_document: catalog splice skipped for scope=%r "
                    "tenant=%r: %s", scope, tenant, e,
                )
                catalog_scopes = []
            if catalog_scopes:
                local_len = 0
                for cs, _ct in chain:
                    if cs == scope:
                        local_len += 1
                    else:
                        break
                local_part = chain[:local_len]
                rest = chain[local_len:]
                catalog_entries = [
                    (cat_scope, cat_tenant) for cat_scope, cat_tenant in catalog_scopes
                ]
                catalog_layer_scopes = {cs for cs, _ in catalog_entries}
                chain = local_part + catalog_entries + rest

        # ── Query each layer (cache-aware) + populate reverse-dep graph ──
        observers = getattr(k, "_layer_observers", None)
        if observers is None:
            observers = OrderedDict()
            k._layer_observers = observers

        contributions: list[tuple[ResolutionLayer, dict | None]] = []
        # Catalog scopes that actually held this (kind,name) — for the
        # multi-package conflict surface below.
        catalog_hits: list[str] = []
        for layer_scope, layer_tenant in chain:
            try:
                raw = await k._granular_doc_cached(
                    (layer_scope, kind, name, layer_tenant or "")
                )
            except FileNotFoundError as e:
                # A parent/catalog scope in the chain may not exist on this
                # source (e.g. a `_lib` library scope absent in a bare
                # checkout). Treat it as "no contribution at this layer" —
                # the same fail-soft the instance builder applies — instead of
                # crashing the whole resolve. (Matches TS resolveDocument.)
                logger.debug(
                    "resolve_document: layer scope %r missing for %s/%s: %s",
                    layer_scope, kind, name, e,
                )
                raw = None
            # Register dependency when consulting a NON-requested scope
            # (parent/grandparent/CATALOG). LRU-bounded — touch on access,
            # evict oldest. Catalog layers register identically to parents so
            # cross-scope invalidation drops this resolution when a catalog
            # package's doc is rewritten.
            if layer_scope != scope:
                parent_key = (layer_scope, kind, name, layer_tenant)
                observers.setdefault(parent_key, set()).add((scope, tenant))
                observers.move_to_end(parent_key)
                while len(observers) > k._LAYER_OBSERVERS_MAX:
                    observers.popitem(last=False)
            if raw is not None and layer_scope in catalog_layer_scopes:
                catalog_hits.append(layer_scope)
            contributions.append((
                ResolutionLayer(
                    scope=layer_scope, tenant=layer_tenant, found=raw is not None,
                ),
                raw,
            ))

        # Surface (don't fail) when ≥2 Catalog packages provide the same
        # (kind,name): the sorted-first catalog scope wins positionally; the
        # rest are shadowed. Determinism is guaranteed by _catalog_scopes' sort.
        if len(catalog_hits) >= 2:
            logger.info(
                "catalog tier conflict: %s/%s provided by %d catalog packages "
                "%s for scope=%r tenant=%r — %r wins (sorted-first); others "
                "shadowed.",
                kind, name, len(catalog_hits), catalog_hits, scope, tenant,
                catalog_hits[0],
            )

        # ── Apply merge strategy ─────────────────────────────────────
        contributions_by_field: dict[str, str] = {}
        if merge_strat == "field_level":
            merged_doc, primary, contributions_by_field = merge_field_level(contributions)
        else:
            merged_doc, primary = merge_override_full(contributions)

        # ── Build provenance with contributed flag ───────────────────
        steps_with_contributed = []
        for layer, raw in contributions:
            contributed = (
                (merge_strat == "field_level" and raw is not None)
                or (primary is not None and layer == primary)
            )
            steps_with_contributed.append(ResolutionLayer(
                scope=layer.scope, tenant=layer.tenant, found=layer.found,
                contributed=contributed, version_sha=layer.version_sha,
            ))

        provenance = ResolutionPath(steps=steps_with_contributed)
        is_inherited = bool(primary is not None and primary.scope != scope)

        return ResolvedDocument(
            doc=merged_doc,
            provenance=provenance,
            is_inherited=is_inherited,
            contributions_by_field=contributions_by_field,
        )

    # NOTE: composition_summary lives on the Kernel (kernel/__init__.py) — the
    # single wired implementation (routes/docs.py → holder.kernel.composition_summary).
    # The former duplicate here was dead code; removed (i-116).

    async def personalize_document(
        self, target_scope: str, kind: str, name: str, *,
        tenant: str | None = None, overwrite: bool = False,
    ):
        """Clone an inherited doc into ``target_scope`` as a local override
        (Phase 17). Raises if the doc isn't inherited / target exists (without
        overwrite). Clones spec + bundle entries atomically."""
        from dna.kernel.resolver import BOOTSTRAP_KINDS
        k = self._k

        if kind in BOOTSTRAP_KINDS:
            raise ValueError(f"Kind {kind!r} is bootstrap and cannot be personalized.")

        resolved = await self.resolve_document(target_scope, kind, name, tenant=tenant)
        if resolved.doc is None:
            raise ValueError(
                f"{kind}/{name} not found in any scope via composition "
                f"chain from {target_scope}."
            )
        if not resolved.is_inherited:
            raise ValueError(
                f"{kind}/{name} is already local to {target_scope} — "
                f"no need to personalize."
            )

        # Check target_scope local existence (skip cache for fresh source state).
        if not overwrite and k._source is not None:
            from dna.kernel.capabilities import source_capabilities
            if source_capabilities(k._source).granular_one:
                existing = await k._source.load_one(target_scope, kind, name, tenant=tenant)
                if existing is not None:
                    raise ValueError(
                        f"{kind}/{name} already exists locally in "
                        f"{target_scope}. Pass overwrite=True to replace."
                    )

        eff = resolved.provenance.effective_layer
        if eff is None:
            raise ValueError("Cannot personalize: provenance has no effective layer.")
        source_scope = eff.scope

        cloned_raw = {
            "apiVersion": resolved.doc.get("apiVersion"),
            "kind": kind,
            "metadata": {**(resolved.doc.get("metadata") or {}), "name": name},
            "spec": dict(resolved.doc.get("spec") or {}),
        }
        await k.write_document(target_scope, kind, name, cloned_raw, tenant=tenant)

        # Clone bundle entries (binary payload) when the Kind is bundle-based.
        sd = k.storage_for_kind(kind)
        if sd is not None and k._source is not None:
            try:
                from dna.kernel.protocols import StoragePattern
            except ImportError:
                StoragePattern = None  # type: ignore[assignment]
            if StoragePattern is not None and sd.pattern == StoragePattern.BUNDLE:
                loader = getattr(k._source, "_load_bundle_entries", None)
                if loader is not None:
                    entries = await loader(source_scope, kind, name, tenant or "")
                    if not entries:
                        entries = await loader(source_scope, kind, name, "")
                    for entry_path, payload in (entries or {}).items():
                        # Skip the marker — write_document already wrote it.
                        if entry_path == sd.marker:
                            continue
                        if isinstance(payload, (bytes, bytearray)):
                            data = bytes(payload)
                        elif isinstance(payload, str):
                            data = payload.encode("utf-8")
                        else:
                            continue
                        try:
                            await k.write_bundle_entry_async(
                                target_scope, kind, name, entry_path, data, tenant=tenant,
                            )
                        except Exception as e:  # noqa: BLE001
                            # fail-soft: the doc write above already succeeded
                            # (and raised on failure) — entry cloning is
                            # best-effort enhancement, but a dropped payload
                            # is a visible gap, so it logs loud.
                            logger.warning(
                                "personalize_document: bundle entry clone "
                                "failed for %s/%s entry=%r: %s",
                                kind, name, entry_path, e,
                            )

        # Return fresh resolution (now local).
        return await self.resolve_document(target_scope, kind, name, tenant=tenant)


__all__ = [
    "CompositionEngine",
    "CompositionProfile",
    "CompositionResolver",
    "CompositionSlot",
    "HealthCheckHint",
    "QuadrantHint",
    "TimelineHint",
    "profile_for_orchestrator",
    "validate_refs",
]
