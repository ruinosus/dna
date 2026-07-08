/**
 * DEPRECATED shim — DefaultLayerResolver moved into the kernel.
 *
 * Layer resolution is a core kernel responsibility
 * (s-invert-layer-resolver-dep, 2026-07-07): the kernel must work with
 * zero extensions loaded, so the resolver now lives at
 * `src/kernel/layer-resolver.ts`. This module reexports the old public
 * names for external importers and emits a DeprecationWarning on import.
 *
 * @deprecated Import from `dna-sdk/kernel/layer-resolver` instead.
 */

export {
  DefaultLayerResolver,
  deepMerge,
  mergeTimelineArrays,
  type LayerSource,
} from "../../kernel/layer-resolver.js";

// Node/Bun idiomatic import-time deprecation (parity with the Python
// shim's warnings.warn(DeprecationWarning)).
if (typeof process !== "undefined" && typeof process.emitWarning === "function") {
  process.emitWarning(
    "extensions/helix/layers is deprecated — import DefaultLayerResolver/" +
      "deepMerge from kernel/layer-resolver instead (s-invert-layer-resolver-dep).",
    "DeprecationWarning",
  );
}
