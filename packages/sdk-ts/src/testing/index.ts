/**
 * Public testing kit for TS SDK port adapters (twin of Python `dna.testing`).
 *
 * Ship-with-the-SDK conformance suites: an adapter author hands us a factory
 * for their adapter and gets back the battery of cases every conforming
 * implementation must pass. Currently the RecordSearchProvider search-plane kit.
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
