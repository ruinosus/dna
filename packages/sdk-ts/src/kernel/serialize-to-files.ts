import type { Kernel } from "./index.js";

/**
 * A single file emitted by a document serializer. Re-exports the
 * canonical shape from protocols.ts (L3 2026-05-25: now accepts
 * `contentBytes?: Uint8Array` for binary entries alongside `content`).
 *
 * `relativePath` is relative to the manifest scope directory. The file-based
 * adapter composing this helper is responsible for prefixing `<baseDir>/<scope>/`
 * when it writes to disk.
 */
export type { SerializedFile } from "./protocols.js";
import type { SerializedFile as _SerializedFile } from "./protocols.js";

/**
 * Turn a raw document into the files a file-based adapter should write.
 *
 * Pure computation — no I/O, no mutation of `raw`. Adapters compose this
 * with their filesystem I/O (TauriWritableSource, FilesystemWritableSource
 * when it ports to TS, etc.).
 *
 * Internally delegates to `kernel.serializeDocument`, which already
 * encapsulates the Kind/Writer lookup + StorageDescriptor path prefixing.
 * Extracting this as a named helper is a contract move: adapters should
 * import `serializeRawToFiles`, not reach into the Kernel's internals.
 *
 * The scope argument is intentionally NOT exposed here — scope is a
 * path-prefix concern the ADAPTER applies. `serializeDocument` treats it
 * as "" internally, so paths come back relative to the scope root.
 */
export function serializeRawToFiles(
  raw: Record<string, unknown>,
  kernel: Kernel,
): readonly _SerializedFile[] {
  const scope = "";
  const kind = String(raw.kind ?? "");
  const name = String(
    ((raw.metadata ?? {}) as Record<string, unknown>).name ?? "",
  );
  const payload = kernel.serializeDocument(scope, kind, name, raw);
  return payload.files;
}
