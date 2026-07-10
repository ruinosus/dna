/**
 * Public testing kit for TS SDK port adapters (twin of Python `dna.testing`).
 *
 * Ship-with-the-SDK conformance suites: an adapter author hands us a factory
 * for their adapter and gets back the battery of cases every conforming
 * implementation must pass. Currently the RecordSearchProvider search-plane
 * kit and the memory-scoring kit (the pure twin of Python's memory kit — the
 * kernel-bound memory VERBS are Py-only by the SDK's declared boundary).
 */
export {
  FIXTURE_SCOPE,
  fixtureRecords,
  recordSearchConformanceSuite,
  SearchCaseNotApplicable,
  type ConformanceProvider,
  type ProviderFactory,
  type RecordSearchCase,
} from "./recordSearchConformance.js";
export {
  KIT_NOW,
  MemoryCaseNotApplicable,
  memoryScoringConformanceSuite,
  type ConformanceEmbedder,
  type EmbedderFactory,
  type MemoryScoringCase,
} from "./memoryScoringConformance.js";
