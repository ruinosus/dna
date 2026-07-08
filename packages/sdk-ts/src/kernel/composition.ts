/**
 * @deprecated shim — import from `./composition-resolver.js` instead.
 *
 * The CompositionProfile (V1) types moved into the unified composition
 * motor (s-unify-composition-subsystems); this module remains only so
 * external callers keep importing. It will be removed in a future major.
 * Py twin: `dna/kernel/composition.py`.
 */
export type {
  CompositionProfile,
  CompositionSlot,
  HealthCheckHint,
  QuadrantHint,
  TimelineHint,
} from "./composition-resolver.js";
export { profileForOrchestrator } from "./composition-resolver.js";
