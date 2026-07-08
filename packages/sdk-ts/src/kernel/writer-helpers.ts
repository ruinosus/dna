/**
 * Shared helpers for KindPort writers — TS twin of
 * `dna.kernel.writer_helpers` (Python).
 *
 * L3 (s-writer-binary-entries 2026-05-25): user-content bundle Kinds
 * (HtmlArtifact, ImagePrompt, Pictogram, Asset) share the
 * convention `spec.source_files: Record<string, string | Uint8Array>`
 * which becomes sibling bundle entries alongside the writer's primary
 * marker. Centralising the pop+convert+write logic keeps writers honest
 * and lets adapter-level enhancements land in one place.
 */
import type { BundleHandle } from "./bundle-handle.js";
import type { SerializedFile } from "./protocols.js";

/**
 * Pop `spec.source_files` from spec (mutates) and convert each file
 * to a bundle-entry dict. Returns SerializedFile[] using `content`
 * for strings and `contentBytes` for binary.
 */
export function popSourceFilesAsEntries(
  spec: Record<string, unknown>,
  kindName: string,
): SerializedFile[] {
  const extra = spec.source_files;
  delete spec.source_files;
  if (extra == null) return [];
  if (typeof extra !== "object" || Array.isArray(extra)) {
    throw new TypeError(
      `${kindName}.spec.source_files must be a Record<string, string|Uint8Array>, got ${typeof extra}`,
    );
  }
  const out: SerializedFile[] = [];
  for (const [relPath, payload] of Object.entries(extra as Record<string, unknown>)) {
    if (payload instanceof Uint8Array) {
      out.push({ relativePath: relPath, contentBytes: payload });
    } else if (typeof payload === "string") {
      out.push({ relativePath: relPath, content: payload });
    } else {
      throw new TypeError(
        `${kindName}.spec.source_files[${JSON.stringify(relPath)}] must be ` +
        `string or Uint8Array, got ${typeof payload}`,
      );
    }
  }
  return out;
}

/**
 * Write a list of bundle entries (mixed text/binary) to a BundleHandle.
 * Dispatches each entry to bundle.writeText or bundle.writeBytes.
 */
export async function writeEntriesToHandle(
  bundle: BundleHandle,
  entries: SerializedFile[],
): Promise<void> {
  for (const f of entries) {
    if (f.contentBytes !== undefined) {
      await bundle.writeBytes(f.relativePath, f.contentBytes);
    } else if (f.content !== undefined) {
      await bundle.writeText(f.relativePath, f.content);
    }
  }
}
