"""Composition V2 — pure resolution types + merge utilities
(Phase 17, Story s-comp-f2-resolver).

This module defines the data shapes returned by ``kernel.resolve_document``
plus pure merge utilities — no engine dependency. The engine itself (and
every other composition concern: CompositionProfile wiring, the shared
ref-validation core, the ``mi.composition`` namespace) lives in the
unified motor ``kernel/composition_resolver.py``
(s-unify-composition-subsystems).

Architectural model (summary):

  Resolution chain pra (scope=S, tenant=T, kind=K, name=N):
    walk Genome.parent_scope transitively, building ordered layers:
        L0 = (S,   T)     # local + tenant overlay
        L1 = (S,   None)  # local base
        L2 = (P,   T)     # parent + tenant overlay (if rule allows)
        L3 = (P,   None)  # parent base
        L4 = (GP,  T)     # grandparent...
        ...

    At each layer, try `source.load_one` (cache-aware via
    `kernel._granular_doc_cached`). Collect contributions.

    Apply merge strategy from `LayerPolicy.composition_rules[K]`:
      - `override_full`  → first non-None layer wins entirely
      - `field_level`    → deep-merge specs, later layers contribute
                            individual fields (and provenance tracks
                            which layer set each field)

  Returns ``ResolvedDocument`` carrying:
    - the merged ``doc`` dict (None if no layer found)
    - ``provenance`` = full resolution path (which layers tried, hit/miss)
    - ``is_inherited`` (derived — true iff effective_layer.scope != S)
    - ``contributions_by_field`` (only populated when merge=field_level)

Bootstrap Kinds (``Genome``, ``LayerPolicy``, ``KindDefinition``) are
NEVER inherited. They're read local-only; provenance still emitted for
uniform API.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────────────────────────────────────
# Module-level constants — sensible defaults (V1 → V2 transition)
# ──────────────────────────────────────────────────────────────────────


# Kinds excluded from inheritance regardless of LayerPolicy. Structural
# (Genome = scope identity; LayerPolicy = the policy Kind itself;
# KindDefinition = registered before docs parse, can't be overlaid).
BOOTSTRAP_KINDS: frozenset[str] = frozenset({
    "Genome",
    "LayerPolicy",
    "KindDefinition",
})


# Scope inheritance default = DENYLIST (s-platform-inherit-by-default, 2026-06-06).
# When a scope has NO LayerPolicy with composition_rules, EVERY Kind defaults to
# scope_inheritance=enabled (override_full merge, field_level tenant overlay)
# EXCEPT the per-scope ledger + structural Kinds below. Mirrors the kernel's
# ``Kernel._NON_INHERITABLE_KINDS``.
#
# "Epic" and "Milestone" are BOTH listed on purpose: v1.3 renamed the Milestone
# Kind to Epic and the rename missed this set, so Epic silently inherited while
# its Story/Issue/Feature/Roadmap siblings did not. "Milestone" stays as a
# tombstone — `kind: Milestone` no longer parses, but un-migrated docs may still
# sit in an `_lib` on disk, and a stale ledger doc must not START leaking into
# child scopes just because its Kind was retired.
DEFAULT_NON_INHERITABLE_KINDS_V1: frozenset[str] = frozenset({
    "Story", "Issue", "Feature", "Epic", "Milestone", "Roadmap",
    "Narrative", "VibeSession", "Engram", "Plan",
    "Genome", "KindDefinition", "LayerPolicy",
})

# Display set ONLY (NOT the inheritance source of truth anymore): the
# composition-summary endpoint iterates this to surface per-Kind local/inherited
# counts in the Studio sidebar. Membership semantics live in the denylist above.
DEFAULT_INHERITABLE_KINDS_V1: frozenset[str] = frozenset({
    "Agent",
    "LottieAsset",
    "HtmlTemplate",
    "Skill",
    "ImagePrompt",
    "Theme",
    "PromptTemplate",
    # s-automation-trio-extinction: JobType/HookType/ScheduleType foram
    # extintos e unificados no Kind Automation (o inheritable herdável).
    "Automation",
})


# Hard limit on parent_scope chain depth — guards against runaway loops
# (cycle detection runs first, but this is a belt-and-suspenders cap).
MAX_RESOLUTION_DEPTH: int = 16


# ──────────────────────────────────────────────────────────────────────
# Provenance + result types
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolutionLayer:
    """One step in the resolution chain — a single ``(scope, tenant)`` pair
    consulted by the resolver.

    - ``found`` records whether the source had ANY doc at this layer.
    - ``contributed`` flips true when this layer ACTUALLY influenced
      the final merged doc (e.g. for override_full only the winning
      layer contributes; for field_level multiple layers contribute).
    """
    scope: str
    tenant: str | None
    found: bool
    contributed: bool = False
    # Version sha or content hash if the source exposes it (best-effort).
    version_sha: str | None = None


@dataclass
class ResolutionPath:
    """Ordered list of layers consulted, highest-priority-first.

    Layer order is:
      [local+tenant, local+base, parent+tenant, parent+base,
       grandparent+tenant, grandparent+base, ...]

    The HIGHEST priority layer is first — i.e. local-tenant beats
    everything else.
    """
    steps: list[ResolutionLayer] = field(default_factory=list)

    @property
    def effective_layer(self) -> ResolutionLayer | None:
        """The single layer that became the doc's primary origin.
        For override_full this is the layer whose doc was returned
        wholesale. For field_level this is the highest-priority layer
        that contributed metadata/envelope (semantic primary owner).
        """
        for s in self.steps:
            if s.found:
                return s
        return None

    def serialize(self) -> dict[str, Any]:
        """JSON-friendly serialization for HTTP responses."""
        eff = self.effective_layer
        return {
            "steps": [
                {
                    "scope": s.scope,
                    "tenant": s.tenant,
                    "found": s.found,
                    "contributed": s.contributed,
                    "version_sha": s.version_sha,
                }
                for s in self.steps
            ],
            "effective_layer": (
                {"scope": eff.scope, "tenant": eff.tenant} if eff else None
            ),
        }


@dataclass
class ResolvedDocument:
    """Result of ``kernel.resolve_document`` — the doc plus full
    provenance.

    Studio renders banner/badge directly from ``provenance`` and
    ``is_inherited`` — no client-side detection logic needed.
    """
    doc: dict[str, Any] | None
    """The merged document (or None if not found in any layer)."""

    provenance: ResolutionPath
    """Full ordered resolution path. Includes layers consulted but
    not contributing."""

    is_inherited: bool
    """True when ``effective_layer.scope != requested_scope``. Convenience
    derived from provenance; Studio uses this for badge/banner toggle."""

    contributions_by_field: dict[str, str] = field(default_factory=dict)
    """LEAF field-path → scope name. Populated when merge_strategy=field_level.
    Paths are nested (``spec.config.model``, not just ``spec.config``), so
    the Detail page can show ``spec.persona ← _lib`` /
    ``spec.config.model ← acme-prod`` annotations at any depth."""

    def serialize(self) -> dict[str, Any]:
        return {
            "doc": self.doc,
            "provenance": self.provenance.serialize(),
            "is_inherited": self.is_inherited,
            "contributions_by_field": self.contributions_by_field,
        }


# ──────────────────────────────────────────────────────────────────────
# Merge strategies — pure functions for testability
# ──────────────────────────────────────────────────────────────────────


def merge_override_full(
    contributions: list[tuple[ResolutionLayer, dict[str, Any]]],
) -> tuple[dict[str, Any] | None, ResolutionLayer | None]:
    """First non-None contribution wins entirely.

    Used for assetic Kinds (LottieAsset, ImagePrompt) where partial
    override makes no sense (binary payload is atomic).

    Input: list of (layer, raw_doc_or_None), highest-priority-first.
    Output: (winning_raw_doc, winning_layer) or (None, None) if all miss.
    """
    for layer, raw in contributions:
        if raw is not None:
            return raw, layer
    return None, None


def _merge_spec_subtree(
    dst: dict[str, Any],
    src: dict[str, Any],
    origin: str,
    prefix: str,
    fields_by_origin: dict[str, str],
) -> None:
    """Recursive worker for :func:`merge_field_level`.

    Merge semantics (MUST stay consistent with
    ``dna.kernel.compose.layer_resolver.deep_merge`` — the overlay engine):

      - dict onto dict   → merge recursively, key by key;
      - list onto ANY    → the higher-priority list REPLACES wholesale
                            (no concat / no element-wise merge);
      - scalar onto ANY  → replace;
      - dict onto scalar/list → the dict replaces, then fills its keys.

    Provenance is recorded at LEAF paths (``spec.config.model``), not
    top-level keys — nested contributions from different layers each keep
    their true origin. When a subtree is REPLACED by a non-dict value,
    the stale descendant records are purged so provenance never points
    at fields that no longer exist. An empty-dict contribution is itself
    a leaf and is recorded at the container path.

    Values are deep-copied into the merged doc so the result never
    aliases the (cached) raw layer documents.
    """
    for k, v in src.items():
        path = f"{prefix}.{k}"
        if isinstance(v, dict):
            existing = dst.get(k)
            if not isinstance(existing, dict):
                # A subtree replaces a scalar/list (or nothing) — drop the
                # stale leaf record from the shadowed layer at this path.
                fields_by_origin.pop(path, None)
                dst[k] = {}
                if not v:
                    fields_by_origin[path] = origin
            _merge_spec_subtree(dst[k], v, origin, path, fields_by_origin)
        else:
            if isinstance(dst.get(k), dict):
                # Scalar/list replaces a whole subtree — purge provenance
                # of every leaf that just ceased to exist.
                stale_prefix = path + "."
                for p in [p for p in fields_by_origin if p.startswith(stale_prefix)]:
                    del fields_by_origin[p]
            dst[k] = copy.deepcopy(v)
            fields_by_origin[path] = origin


def merge_field_level(
    contributions: list[tuple[ResolutionLayer, dict[str, Any]]],
) -> tuple[dict[str, Any] | None, ResolutionLayer | None, dict[str, str]]:
    """Deep-merge ``spec`` dicts, RECURSIVELY. Higher-priority layers shadow
    lower ones per NESTED field, not per top-level key — a local
    ``spec.config.temperature`` no longer erases an inherited
    ``spec.config.model``. Returns
    ``(merged_doc, primary_origin_layer, fields_by_origin)``.

    Algorithm:
      - First pass: find the PRIMARY layer (highest-priority hit). Its
        metadata + envelope (apiVersion, kind) carry over wholesale.
      - Second pass: iterate contributions LOWEST → HIGHEST priority,
        deep-merging specs into a fresh dict (dicts nest; lists and
        scalars are replaced wholesale — the same semantics as
        ``layer_resolver.deep_merge``, so the two merge engines agree).
      - ``fields_by_origin`` maps each FINAL leaf field path
        (``spec.config.model``) to the scope that set it, so the UI can
        render ``spec.config.model ← _lib`` annotations at any depth.

    Edge cases:
      - All-None contributions → (None, None, {}).
      - Single hit → equivalent to override_full (single-layer merge).
      - Spec missing or non-dict → that layer contributes no spec fields
        (envelope/metadata still count if it is the primary).
      - A layer contributing an empty dict at some path is recorded as a
        leaf contribution at that path.
    """
    # First pass — find primary (highest priority hit).
    primary: ResolutionLayer | None = None
    primary_raw: dict[str, Any] | None = None
    for layer, raw in contributions:
        if raw is not None:
            primary = layer
            primary_raw = raw
            break

    if primary is None or primary_raw is None:
        return None, None, {}

    # Second pass — merge specs LOWEST to HIGHEST so highest wins per-field.
    merged_spec: dict[str, Any] = {}
    fields_by_origin: dict[str, str] = {}
    for layer, raw in reversed(contributions):
        if raw is None:
            continue
        spec = raw.get("spec") or {}
        if not isinstance(spec, dict):
            continue
        _merge_spec_subtree(merged_spec, spec, layer.scope, "spec", fields_by_origin)

    final: dict[str, Any] = {
        "apiVersion": primary_raw.get("apiVersion"),
        "kind": primary_raw.get("kind"),
        "metadata": primary_raw.get("metadata") or {},
        "spec": merged_spec,
    }
    return final, primary, fields_by_origin
