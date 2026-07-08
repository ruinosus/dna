/**
 * Document preview API.
 *
 * The Studio's "preview" pane consumes structured `PreviewBlock`s instead
 * of raw markdown so each kind can render however makes sense (markdown,
 * code, tabular fields). The polymorphism lives inside each KindPort
 * (`KindPort.preview?`); this module is only the type definition,
 * generic fallback, and a cross-document consumer scan.
 */
import type { Document } from "./document.js";
import type { ManifestInstance } from "./instance.js";

/**
 * A single renderable section of a document preview. Documents can produce
 * multiple blocks (e.g. a Soul has SOUL.md + STYLE.md + soul.json), which
 * the Studio renders stacked.
 *
 * `kind` is the renderer hint:
 *   - "markdown"  → MarkdownBlock (prose, headings, lists)
 *   - "code"      → CodeBlock (yaml, json, plain text in monospace)
 *   - "fields"    → FieldsBlock (key/value pairs)
 *   - "empty"     → no body, just the title (used for empty states)
 */
export type PreviewBlockKind = "markdown" | "code" | "fields" | "empty";

export interface PreviewBlock {
  kind: PreviewBlockKind;
  /** Section header shown above the body. */
  title: string;
  /** Free-form body content. Type depends on `kind`. */
  body?: string;
  /** Used by code blocks to choose syntax highlighting. */
  language?: string;
  /** Used by fields blocks. Ordered. */
  fields?: Array<{ label: string; value: string }>;
}

/**
 * Last-resort renderer used by `ManifestInstance.renderDoc` when the
 * KindPort doesn't implement `preview()`. Always returns SOMETHING so the
 * Studio never has a blank pane — even unknown kinds get a JSON dump of
 * their spec.
 */
export function genericSpecDump(doc: Document): PreviewBlock[] {
  const spec = (doc.spec ?? {}) as Record<string, unknown>;
  if (!spec || Object.keys(spec).length === 0) {
    return [{ kind: "empty", title: `${doc.kind} (empty spec)` }];
  }
  return [
    {
      kind: "code",
      title: `${doc.kind} spec`,
      body: JSON.stringify(spec, null, 2),
      language: "json",
    },
  ];
}

/**
 * Walk every document in the manifest and return those that reference the
 * given target via a dep_filters declaration on their KindPort.
 *
 * Uses `instance.iterDocDeps(doc)` under the hood — the kernel method
 * that dynamically walks `KindPort.depFilters()` for each doc. No
 * hardcoded field-to-kind map needed; any extension that declares its
 * deps via depFilters participates automatically.
 */
export function findConsumers(
  instance: ManifestInstance,
  target: { kind: string; name: string },
): Array<{ kind: string; name: string }> {
  const out: Array<{ kind: string; name: string }> = [];
  const seen = new Set<string>();
  const iterFn = (
    instance as unknown as {
      iterDocDeps?: (d: Document) => Array<{
        label: string;
        targetKind: string;
        names: string[];
      }>;
    }
  ).iterDocDeps;

  for (const doc of instance.documents) {
    if (doc.kind === target.kind && doc.name === target.name) continue;
    const deps = iterFn?.call(instance, doc) ?? [];
    let hit = false;
    for (const dep of deps) {
      if (dep.targetKind !== target.kind) continue;
      if (dep.names.includes(target.name)) {
        hit = true;
        break;
      }
    }
    const key = `${doc.kind}/${doc.name}`;
    if (hit && !seen.has(key)) {
      seen.add(key);
      out.push({ kind: doc.kind, name: doc.name });
    }
  }
  return out;
}
