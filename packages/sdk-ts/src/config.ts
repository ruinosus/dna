/**
 * `dna.config.yaml` — declarative port wiring (s-dx-kernel-from-config).
 *
 * 1:1 parity with python `dna/config.py`. The SAME file drives both SDKs — the
 * schema is language-agnostic:
 *
 * ```yaml
 * # dna.config.yaml
 * source: postgresql://user:pass@host/db   # or sqlite:///./dev.db, file://.dna
 * search: pgvector        # pgvector | sqlite-vec | off   (default: off)
 * embedding: onnx         # onnx | fake | off             (default: off / fake floor)
 * ```
 *
 * Only `source` is required. This module parses + VALIDATES the file (unknown
 * keys and bad enum values fail loud); the wiring lives in `fromConfig()`.
 *
 * Runtime asymmetry (documented, not silent): the TS runtime ships the
 * filesystem + postgres source adapters; `sqlite://` is Python-only (it rides
 * the Python-only SqlAlchemy adapter). A `sqlite://` source — or a `pgvector`
 * search — in a TS host fails loud with that explanation at wire time.
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import yaml from "js-yaml";

export const CONFIG_FILENAME = "dna.config.yaml";

const VALID_SEARCH = ["off", "pgvector", "sqlite-vec"] as const;
const VALID_EMBEDDING = ["off", "fake", "onnx"] as const;
const KNOWN_KEYS = new Set(["source", "search", "embedding", "auth"]);

export type SearchMode = (typeof VALID_SEARCH)[number];
export type EmbeddingMode = (typeof VALID_EMBEDDING)[number];

/** Parsed + validated `dna.config.yaml`. */
export interface DnaConfig {
  /** Scheme URL: `file://` | `sqlite://` | `postgresql://`. */
  source: string;
  /** Record-search provider selector (default `off`). */
  search: SearchMode;
  /** Embedding provider selector (default `off`). */
  embedding: EmbeddingMode;
  /**
   * Opaque passthrough of the `auth:` section — the SDK only checks it is a
   * mapping; its detailed schema (`providers[]` — the pluggable N-provider IdP
   * layer of the MCP runtime face) is owned by the consumer (the CLI's
   * `_mcp_auth.parse_auth_providers`). `null` when the file has no `auth:`.
   */
  auth: Record<string, unknown> | null;
  /** Where it was loaded from (`null` for a synthesized default). */
  path: string | null;
}

/**
 * Path to `dna.config.yaml` in `start` (default: cwd), or `null` if absent.
 * Deliberately NOT a walk-up — a config's meaning is tied to the boot dir.
 */
export function findConfig(start?: string): string | null {
  const candidate = join(start ?? process.cwd(), CONFIG_FILENAME);
  return existsSync(candidate) ? candidate : null;
}

/**
 * Load + validate `dna.config.yaml`.
 *
 * - `path` given → it MUST exist (a typo'd path is an error, not a silent
 *   fallback); parsed and validated.
 * - `path` omitted → look for `dna.config.yaml` in cwd. Found → parsed. Absent
 *   → `null` (the caller keeps its default: a filesystem `.dna` source).
 *
 * Throws on: not-a-mapping, missing `source`, unknown keys, or an out-of-enum
 * `search` / `embedding` value.
 */
export function loadConfig(path?: string): DnaConfig | null {
  let resolved: string;
  if (path !== undefined) {
    if (!existsSync(path)) {
      throw new Error(
        `dna config not found at ${path} — pass a path to an existing ` +
          `${CONFIG_FILENAME}, or omit it to auto-discover one in the ` +
          `current directory.`,
      );
    }
    resolved = path;
  } else {
    const found = findConfig();
    if (found === null) return null;
    resolved = found;
  }

  const raw = yaml.load(readFileSync(resolved, "utf-8"));
  return parse(raw, resolved);
}

function parse(raw: unknown, path: string): DnaConfig {
  if (raw === null || raw === undefined) {
    throw new Error(
      `${path} is empty — it must at least declare a \`source:\` URL ` +
        `(e.g. \`source: file://.dna\`).`,
    );
  }
  if (typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error(`${path} must be a YAML mapping (key: value).`);
  }
  const obj = raw as Record<string, unknown>;

  const unknown = Object.keys(obj).filter((k) => !KNOWN_KEYS.has(k)).sort();
  if (unknown.length > 0) {
    throw new Error(
      `${path}: unknown key(s) ${JSON.stringify(unknown)} — supported keys ` +
        `are ${JSON.stringify([...KNOWN_KEYS].sort())}.`,
    );
  }

  const source = obj.source;
  if (typeof source !== "string" || source.length === 0) {
    throw new Error(
      `${path}: \`source:\` is required and must be a URL string ` +
        `(file:// | sqlite:// | postgresql://).`,
    );
  }

  const search = String(obj.search ?? "off").trim() || "off";
  if (!(VALID_SEARCH as readonly string[]).includes(search)) {
    throw new Error(
      `${path}: \`search: ${search}\` is not valid — choose one of ` +
        `${JSON.stringify(VALID_SEARCH)}.`,
    );
  }

  const embedding = String(obj.embedding ?? "off").trim() || "off";
  if (!(VALID_EMBEDDING as readonly string[]).includes(embedding)) {
    throw new Error(
      `${path}: \`embedding: ${embedding}\` is not valid — choose one of ` +
        `${JSON.stringify(VALID_EMBEDDING)}.`,
    );
  }

  const rawAuth = obj.auth;
  if (
    rawAuth !== undefined &&
    rawAuth !== null &&
    (typeof rawAuth !== "object" || Array.isArray(rawAuth))
  ) {
    throw new Error(
      `${path}: \`auth:\` must be a mapping (its \`providers:\` list configures ` +
        `the MCP IdP layer).`,
    );
  }
  const auth = (rawAuth ?? null) as Record<string, unknown> | null;

  return {
    source,
    search: search as SearchMode,
    embedding: embedding as EmbeddingMode,
    auth,
    path,
  };
}
