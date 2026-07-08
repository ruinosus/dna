/**
 * DefaultLayerResolver — overlay resolution with per-kind policies.
 *
 * 1:1 parity with Python dna.kernel.layer_resolver.
 *
 * Kernel-owned since s-invert-layer-resolver-dep (2026-07-07): layer
 * resolution is a core kernel responsibility, so the default resolver
 * lives in the kernel package — the kernel must work with ZERO
 * extensions loaded. Previously at src/extensions/helix/layers.ts
 * (which remains as a deprecated reexport shim).
 *
 * Iterates layer dimensions, loads overlays from the source,
 * and merges with per-kind policies (open/restricted/locked).
 * The resolver is fully generic: it depends only on
 * kernel/protocols.LayerPolicy — no extension models or constants.
 */

import { LayerPolicy } from "./protocols.js";

// ---------------------------------------------------------------------------
// Deep merge
// ---------------------------------------------------------------------------

/**
 * Deep merge two plain objects. Overlay wins.
 * Lists are replaced (not concatenated), dicts are merged recursively.
 */
export function deepMerge(
  base: Record<string, unknown>,
  overlay: Record<string, unknown>,
): Record<string, unknown> {
  const result = structuredClone(base);
  for (const [key, value] of Object.entries(overlay)) {
    if (
      key in result &&
      typeof result[key] === "object" &&
      result[key] !== null &&
      !Array.isArray(result[key]) &&
      typeof value === "object" &&
      value !== null &&
      !Array.isArray(value)
    ) {
      result[key] = deepMerge(
        result[key] as Record<string, unknown>,
        value as Record<string, unknown>,
      );
    } else {
      result[key] = structuredClone(value);
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// Timeline merger (cross-overlay append-only)
// ---------------------------------------------------------------------------

/**
 * Concat + dedup + sort base.spec.timeline and overlay.spec.timeline
 * (per ADR 2026-05-10). Returns the merged list when EITHER side has a
 * timeline array; ``null`` when neither does.
 *
 * Dedup key: `at + actor + type + (from + to | summary)`.
 * Sort: descending by ``at`` (newest first).
 */
export function mergeTimelineArrays(
  baseSpec: Record<string, unknown>,
  overlaySpec: Record<string, unknown>,
): Record<string, unknown>[] | null {
  const baseTl = Array.isArray(baseSpec.timeline)
    ? (baseSpec.timeline as Record<string, unknown>[])
    : [];
  const overlayTl = Array.isArray(overlaySpec.timeline)
    ? (overlaySpec.timeline as Record<string, unknown>[])
    : [];
  if (baseTl.length === 0 && overlayTl.length === 0) return null;

  const seen = new Set<string>();
  const merged: Record<string, unknown>[] = [];
  for (const ev of [...baseTl, ...overlayTl]) {
    if (typeof ev !== "object" || ev === null || Array.isArray(ev)) continue;
    const key = JSON.stringify([
      ev.at ?? null,
      ev.actor ?? null,
      ev.type ?? null,
      ev.from ?? null,
      ev.to ?? null,
      ev.summary ?? null,
    ]);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(structuredClone(ev));
  }
  // Stable sort: newest first.
  merged.sort((a, b) => {
    const ax = String(a.at ?? "");
    const bx = String(b.at ?? "");
    if (ax < bx) return 1;
    if (ax > bx) return -1;
    return 0;
  });
  return merged;
}

// ---------------------------------------------------------------------------
// Overlay metadata stamper (Phase 2 overlay UX)
// ---------------------------------------------------------------------------

/**
 * In-place: write ``has_overlay`` + ``overlay_fields`` into ``doc.metadata``.
 * Studio's editor banners + per-field markers read these.
 *
 * ``overlayFields=null`` is the sentinel for "the entire doc came from
 * the overlay" (overlay-only add, no base to diff against). Frontend
 * treats this distinctly from an empty list.
 *
 * Idempotent across multiple layer dimensions: subsequent calls UNION
 * the field list so the user sees every field touched across all
 * applied layers.
 */
function stampOverlayMetadata(
  doc: Record<string, unknown>,
  overlayFields: string[] | null,
): void {
  const md = (doc.metadata as Record<string, unknown>) ?? {};
  doc.metadata = md;
  md.has_overlay = true;
  if (overlayFields === null) {
    md.overlay_fields = null;
    return;
  }
  const existing = md.overlay_fields;
  if (existing === undefined || existing === null) {
    md.overlay_fields = [...overlayFields];
    return;
  }
  if (Array.isArray(existing)) {
    const merged = [...(existing as string[])];
    for (const f of overlayFields) {
      if (!merged.includes(f)) merged.push(f);
    }
    md.overlay_fields = merged;
  }
}

// ---------------------------------------------------------------------------
// LayerSource interface (minimal duck-type for the resolver)
// ---------------------------------------------------------------------------

export interface LayerSource {
  loadLayer(
    scope: string,
    layerId: string,
    layerValue: string,
  ): Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// DefaultLayerResolver
// ---------------------------------------------------------------------------

/**
 * Merges layer overlay documents into base documents, applying policies by kind alias.
 *
 * Policies map: `{ kind_alias_or_kind_name: LayerPolicy }`
 * - open: deep merge spec (or add new documents)
 * - restricted: only override existing keys in spec
 * - locked: block changes (warn only)
 */
export class DefaultLayerResolver {
  resolve(
    baseDocuments: Record<string, unknown>[],
    layers: Record<string, string>,
    source: LayerSource,
    scope: string,
    policies: Record<string, string>,
  ): Record<string, unknown>[] {
    let result = baseDocuments.map((d) => structuredClone(d));

    for (const [layerId, value] of Object.entries(layers)) {
      const overlayDocs = source.loadLayer(scope, layerId, value);
      if (overlayDocs.length === 0) continue;
      result = this._mergeAll(result, overlayDocs, policies, layerId, value);
    }

    return result;
  }

  // -------------------------------------------------------------------------

  private _mergeAll(
    baseDocs: Record<string, unknown>[],
    overlayDocs: Record<string, unknown>[],
    policies: Record<string, string>,
    layerId: string,
    value: string,
  ): Record<string, unknown>[] {
    const result = baseDocs.map((d) => structuredClone(d));

    // Build index: "kind\0name" -> position in result
    const baseIndex = new Map<string, number>();
    for (let i = 0; i < result.length; i++) {
      const kind = (result[i].kind as string) ?? "";
      const name =
        ((result[i].metadata as Record<string, unknown>)?.name as string) ?? "";
      if (kind && name) baseIndex.set(`${kind}\0${name}`, i);
    }

    for (const overlay of overlayDocs) {
      const oKind = (overlay.kind as string) ?? "";
      const oName =
        ((overlay.metadata as Record<string, unknown>)?.name as string) ?? "";
      const policy = this._policyForKind(oKind, policies);
      const key = `${oKind}\0${oName}`;

      if (baseIndex.has(key)) {
        const idx = baseIndex.get(key)!;
        result[idx] = this._applyMerge(
          result[idx],
          overlay,
          policy,
          layerId,
          value,
        );
      } else {
        // New document — only allowed under OPEN policy
        if (
          policy === LayerPolicy.LOCKED ||
          policy === LayerPolicy.RESTRICTED
        ) {
          console.warn(
            `Layer '${layerId}=${value}' tried to add '${oKind}/${oName}' but policy is ${policy}. Ignored.`,
          );
        } else {
          // Overlay-only add — stamp metadata so the frontend knows
          // "the whole doc is your overlay" (Phase 2 UX).
          const newDoc = structuredClone(overlay);
          stampOverlayMetadata(newDoc, null);
          result.push(newDoc);
        }
      }
    }
    return result;
  }

  private _policyForKind(
    kind: string,
    policies: Record<string, string>,
  ): string {
    if (kind in policies) return policies[kind];
    const kindLower = kind.toLowerCase();
    for (const [alias, policy] of Object.entries(policies)) {
      if (alias.endsWith(`-${kindLower}`) || alias === kindLower) return policy;
    }
    return LayerPolicy.OPEN;
  }

  private _applyMerge(
    base: Record<string, unknown>,
    overlay: Record<string, unknown>,
    policy: string,
    layerId: string,
    value: string,
  ): Record<string, unknown> {
    const specOverlay = (overlay.spec as Record<string, unknown>) ?? {};
    const specBase = (base.spec as Record<string, unknown>) ?? {};

    // Timeline is append-only across overlays — concat+sort regardless
    // of policy (even LOCKED). ADR 2026-05-10.
    const mergedTimeline = mergeTimelineArrays(specBase, specOverlay);

    if (Object.keys(specOverlay).length === 0 && mergedTimeline === null) {
      return base;
    }

    if (policy === LayerPolicy.LOCKED) {
      if (mergedTimeline === null) {
        const name =
          ((base.metadata as Record<string, unknown>)?.name as string) ?? "";
        console.warn(
          `Layer '${layerId}=${value}' tried to modify locked document '${name}'. Ignored.`,
        );
        return base;
      }
      // Timeline-only overlay on a LOCKED doc still appends events.
      const result = structuredClone(base);
      const sp = (result.spec as Record<string, unknown>) ?? {};
      sp.timeline = mergedTimeline;
      result.spec = sp;
      return result;
    }

    if (policy === LayerPolicy.RESTRICTED) {
      // Strip `timeline` from the restricted-merge call so the
      // "unknown key" warning doesn't fire for timeline-only changes.
      const specOverlayNoTl: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(specOverlay)) {
        if (k !== "timeline") specOverlayNoTl[k] = v;
      }
      const result = this._applyRestrictedMerge(
        base,
        specOverlayNoTl,
        layerId,
        value,
      );
      if (mergedTimeline !== null) {
        const sp = (result.spec as Record<string, unknown>) ?? {};
        sp.timeline = mergedTimeline;
        result.spec = sp;
      }
      return result;
    }

    // OPEN — deep merge spec
    const result = structuredClone(base);
    result.spec = deepMerge(specBase, specOverlay);
    if (mergedTimeline !== null) {
      (result.spec as Record<string, unknown>).timeline = mergedTimeline;
    }
    if (Object.keys(specOverlay).length > 0) {
      // Phase 2 overlay UX: top-level spec keys the overlay provided
      // are "overridden" under OPEN policy. Exclude `timeline` since
      // it's append-only, not an override.
      const overridden = Object.keys(specOverlay).filter(
        (k) => k !== "timeline",
      );
      if (overridden.length > 0) {
        stampOverlayMetadata(result, overridden);
      }
    }
    return result;
  }

  private _applyRestrictedMerge(
    base: Record<string, unknown>,
    specOverlay: Record<string, unknown>,
    layerId: string,
    value: string,
  ): Record<string, unknown> {
    const result = structuredClone(base);
    const specBase = (result.spec as Record<string, unknown>) ?? {};
    const applied: string[] = [];

    for (const [key, val] of Object.entries(specOverlay)) {
      if (!(key in specBase)) {
        console.warn(
          `Layer '${layerId}=${value}' tried to add key '${key}' to restricted document. Ignored.`,
        );
        continue;
      }
      if (
        typeof specBase[key] === "object" &&
        specBase[key] !== null &&
        !Array.isArray(specBase[key]) &&
        typeof val === "object" &&
        val !== null &&
        !Array.isArray(val)
      ) {
        specBase[key] = deepMerge(
          specBase[key] as Record<string, unknown>,
          val as Record<string, unknown>,
        );
      } else {
        specBase[key] = structuredClone(val);
      }
      applied.push(key);
    }

    result.spec = specBase;
    // Restricted policy drops unknown keys — stamp only the ones
    // that actually merged.
    if (applied.length > 0) {
      stampOverlayMetadata(result, applied);
    }
    return result;
  }
}
