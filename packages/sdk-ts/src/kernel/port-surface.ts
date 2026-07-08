/**
 * PORT_SURFACE — static member manifest of the public port interfaces
 * (s-dna-port-surface-parity).
 *
 * TS interfaces are erased at runtime, so the port-surface parity test
 * can't introspect them the way the Python twin introspects its
 * `typing.Protocol`s. Instead, this module declares each port's member
 * list as a const — and BINDS it to the real interface at compile time:
 *
 *   - every listed member must be a `keyof` the interface (no phantom
 *     members), and
 *   - the list must be EXHAUSTIVE (a member added to the interface but
 *     not listed here fails `tsc --noEmit` with the missing name in the
 *     error type).
 *
 * `tests/port-surface-parity.test.ts` then compares this manifest against
 * the shared fixture `tests/parity-fixtures/port-surface-parity.json`
 * (which the Py suite checks against the real Protocols) — so the two
 * SDKs' port surfaces can only drift through an explicit, justified
 * fixture edit.
 */

import type {
  CachePort,
  Extension,
  ExtensionHost,
  KindPort,
  ReaderPort,
  RecordSearchProvider,
  ResolverPort,
  SourcePort,
  ToolPort,
  WritableSourcePort,
  WriterPort,
} from "./protocols.js";
import type {
  BundleEntryReadable,
  KernelAttachable,
  SourceCapabilities,
  Versionable,
} from "./capabilities.js";

/** Interface keys not covered by the declared list (→ compile error). */
type MissingKeys<T, K extends readonly (keyof T & string)[]> =
  Exclude<keyof T & string, K[number]>;

/**
 * Compile-time exhaustive-keys binder. `keysOf<T>()([...])` only accepts
 * an array whose entries are ALL keys of `T` and which covers EVERY key
 * of `T` — otherwise the intersection with the `__missing_members__`
 * brand fails to typecheck, naming the missing key(s) in the error.
 */
function keysOf<T>() {
  return <const K extends readonly (keyof T & string)[]>(
    keys: [MissingKeys<T, K>] extends [never]
      ? K
      : K & { __missing_members__: MissingKeys<T, K> },
  ): readonly string[] => keys;
}

/**
 * Compile-time existence proof for the capability interfaces tracked as
 * NAMES (not keys) in the fixture's `CapabilityProtocols` pseudo-port —
 * deleting/renaming one breaks this alias.
 */
export type CapabilityProtocolsProof = [
  BundleEntryReadable,
  KernelAttachable,
  Versionable,
];

export const PORT_SURFACE: Readonly<Record<string, readonly string[]>> = {
  SourcePort: keysOf<SourcePort>()([
    "supportsReaders",
    "loadBootstrapDocs",
    "loadAll",
    "resolveRef",
    "loadLayer",
    "close",
    "listDocRefs",
    "loadOne",
    "query",
    "count",
    "capabilities",
  ]),
  // OWN members only — the inherited SourcePort half is tracked above.
  WritableSourcePort: keysOf<Omit<WritableSourcePort, keyof SourcePort>>()([
    "saveDocument",
    "deleteDocument",
    "listVersions",
    "getVersion",
    "publish",
  ]),
  CachePort: keysOf<CachePort>()([
    "has",
    "store",
    "loadKey",
    "loadAll",
  ]),
  ResolverPort: keysOf<ResolverPort>()([
    "resolve",
    "cacheKey",
  ]),
  ReaderPort: keysOf<ReaderPort>()([
    "detect",
    "read",
    "_ownerContainer",
  ]),
  WriterPort: keysOf<WriterPort>()([
    "canWrite",
    "write",
    "serialize",
  ]),
  KindPort: keysOf<KindPort>()([
    "apiVersion",
    "kind",
    "alias",
    "origin",
    "scope",
    "docs",
    "isRoot",
    "isPromptTarget",
    "promptTargetPriority",
    "flattenInContext",
    "storage",
    "isRuntimeArtifact",
    "isSchemaAffecting",
    "isOverlayable",
    "scopeInheritable",
    "plane",
    "depFilters",
    "getDefaultAgentName",
    "getLayerPolicies",
    "parse",
    "describe",
    "summary",
    "promptTemplate",
    "schema",
    "dependencies",
    "preview",
    "graphStyle",
    "asciiIcon",
    "displayLabel",
    "graphMeta",
  ]),
  ToolPort: keysOf<ToolPort>()([
    "name",
    "group",
    "description",
    "summary",
    "argsSchema",
    "hitl",
    "scope",
    "source",
    "getCallable",
  ]),
  ExtensionHost: keysOf<ExtensionHost>()([
    "hooks",
    "kind",
    "kindFromDescriptor",
    "reader",
    "writer",
    "on",
    "onVeto",
    "tool",
    "compositionProfile",
  ]),
  Extension: keysOf<Extension>()([
    "name",
    "version",
    "register",
    "templates",
  ]),
  RecordSearchProvider: keysOf<RecordSearchProvider>()([
    "search",
  ]),
  SourceCapabilities: keysOf<SourceCapabilities>()([
    "source",
    "drafts",
    "versions",
    "layers",
    "bundleRead",
    "bundleWrite",
    "kernelAttachable",
    "granularList",
    "granularOne",
    "queryPushdown",
  ]),
  // Interface NAMES (see CapabilityProtocolsProof above for the
  // compile-time existence binding).
  CapabilityProtocols: [
    "BundleEntryReadable",
    "KernelAttachable",
    "Versionable",
  ],
};
