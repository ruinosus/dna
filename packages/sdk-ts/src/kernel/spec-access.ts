/**
 * Generic accessors for Document.spec — lets consumers read fields without
 * knowing the kind's typed model. Returns undefined / [] / {} for missing
 * fields; throws a clear error on type mismatch (wrong field type in the
 * actual doc).
 *
 * Use these in extension code, renderers, and tools that operate across
 * many kinds. For single-kind code that already branched on kind, using
 * the typed model via `doc.typed` is fine.
 */
import type { Document } from "./document.js";

function getSpec(doc: Document | { spec?: Record<string, unknown> }): Record<string, unknown> {
  const spec = (doc as any).spec;
  return (spec && typeof spec === "object") ? spec as Record<string, unknown> : {};
}

export function readSpecString(
  doc: Document | { spec?: Record<string, unknown> },
  field: string,
): string | undefined {
  const v = getSpec(doc)[field];
  if (v === undefined || v === null) return undefined;
  if (typeof v !== "string") {
    throw new TypeError(`spec['${field}']: expected string, got ${typeof v}`);
  }
  return v;
}

export function readSpecStringArray(
  doc: Document | { spec?: Record<string, unknown> },
  field: string,
): string[] {
  const v = getSpec(doc)[field];
  if (v === undefined || v === null) return [];
  if (!Array.isArray(v)) {
    throw new TypeError(`spec['${field}']: expected array, got ${typeof v}`);
  }
  return v as string[];
}

export function readSpecRecord(
  doc: Document | { spec?: Record<string, unknown> },
  field: string,
): Record<string, unknown> {
  const v = getSpec(doc)[field];
  if (v === undefined || v === null) return {};
  if (typeof v !== "object" || Array.isArray(v)) {
    throw new TypeError(`spec['${field}']: expected object, got ${typeof v}`);
  }
  return v as Record<string, unknown>;
}

export function readSpecRecordArray(
  doc: Document | { spec?: Record<string, unknown> },
  field: string,
): Record<string, unknown>[] {
  const v = getSpec(doc)[field];
  if (v === undefined || v === null) return [];
  if (!Array.isArray(v)) {
    throw new TypeError(`spec['${field}']: expected array, got ${typeof v}`);
  }
  return v as Record<string, unknown>[];
}
