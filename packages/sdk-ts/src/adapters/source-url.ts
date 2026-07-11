/**
 * `sourceFromUrl` — the URL → SourcePort factory, as a PUBLIC SDK surface.
 *
 * 1:1 parity with python `dna/adapters/source_url.py`. Promotes URL→adapter
 * resolution out of ad-hoc host code so `fromConfig()` and any host share ONE
 * factory.
 *
 * Scheme map (TS runtime):
 *
 *   file:// <path>      → FilesystemSource (read/write on disk)
 *   fs:// <path>        → alias of file://
 *   <plain path>        → treated as file://<path>
 *   pkg://<pkg>[/sub]   → FilesystemSource (READ-ONLY) over a scope embedded
 *                         as PACKAGE DATA of <pkg> (sub defaults to .dna);
 *                         travels with the app (tarball / Docker)
 *   postgresql:// …     → PostgresSource (node-postgres)
 *   postgres:// …       → alias of postgresql://
 *   sqlite:// <path>    → NOT SUPPORTED in the TS runtime (Python-only; the
 *                         SqlAlchemy adapter is a Python thing) — fails loud.
 *
 * An unknown scheme fails loud with the supported set.
 */
import type { SourcePort } from "../kernel/protocols.js";

export class UnsupportedSourceScheme extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UnsupportedSourceScheme";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

interface SourceFromUrlOptions {
  /** Postgres schema namespace (postgres sources only). */
  schema?: string;
}

function urlToFsPath(url: string): string {
  // Mirror the Python rule (join netloc + path so `fs://./x` stays RELATIVE).
  const m = /^([a-zA-Z][a-zA-Z0-9+.-]*):\/\/(.*)$/.exec(url);
  if (!m) return url; // plain path, no scheme
  return m[2]; // everything after scheme:// (host+path joined)
}

function schemeOf(url: string): string {
  const m = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(url);
  return (m ? m[1] : "file").toLowerCase();
}

/**
 * Split `pkg://<package>[/<subpath>]` into `{ pkg, subpath }`. Parity with the
 * python `_parse_pkg_url`: `pkg://app` → `{pkg:"app", subpath:""}`;
 * `pkg://app/.dna` → `{pkg:"app", subpath:".dna"}`. The package is the netloc
 * (a dotted `pkg://my.app` stays `my.app`).
 */
function parsePkgUrl(url: string): { pkg: string; subpath: string } {
  const m = /^pkg:\/\/([^/]*)(?:\/(.*))?$/.exec(url);
  const pkg = m?.[1] ?? "";
  if (!pkg) {
    throw new UnsupportedSourceScheme(
      `pkg:// source URL is missing a package name — use ` +
        `pkg://<package>[/<subpath>] (e.g. pkg://app or pkg://app/.dna). ` +
        `Got: ${url}`,
    );
  }
  return { pkg, subpath: m?.[2] ?? "" };
}

/**
 * Build a source from a scheme URL (see module docstring).
 *
 * Postgres sources run their migrations on first use; this awaits `init()` so
 * the returned source is ready.
 */
export async function sourceFromUrl(
  url: string,
  opts: SourceFromUrlOptions = {},
): Promise<SourcePort> {
  const scheme = schemeOf(url);
  const base = scheme.split("+", 1)[0];

  if (scheme === "file" || scheme === "fs" || scheme === "") {
    const { FilesystemSource } = await import("./filesystem/source.js");
    return new FilesystemSource(urlToFsPath(url) || url);
  }

  if (scheme === "pkg") {
    // A scope embedded as PACKAGE DATA — resolve it from inside the installed
    // package so it travels with the app (tarball / Docker), no path
    // navigation and no manual copy. READ-ONLY: FilesystemSource has no write
    // surface here (to write, use file:// or postgresql://).
    const { FilesystemSource } = await import("./filesystem/source.js");
    const { anchorScopesRoot, DEFAULT_SUBPATH } = await import(
      "../package-scope.js"
    );
    const { pkg, subpath } = parsePkgUrl(url);
    return new FilesystemSource(anchorScopesRoot(pkg, subpath || DEFAULT_SUBPATH));
  }

  if (base === "postgresql" || base === "postgres") {
    const { PostgresSource } = await import("./postgres/source.js");
    const src = new PostgresSource({ connectionString: url, schema: opts.schema });
    await src.init();
    return src as unknown as SourcePort;
  }

  if (base === "sqlite") {
    throw new UnsupportedSourceScheme(
      `sqlite:// sources are Python-only — they ride the Python SqlAlchemy ` +
        `adapter, which the TypeScript runtime does not ship. Use file:// ` +
        `(filesystem) or postgresql:// here. Got: ${url}`,
    );
  }

  throw new UnsupportedSourceScheme(
    `unsupported source URL scheme '${scheme}://' — the TS runtime ships ` +
      `file:// (filesystem), pkg:// (read-only package-data scope) and ` +
      `postgresql:// adapters. Got: ${url}`,
  );
}

/**
 * The `file://` URL the SDK falls back to with no explicit config.
 * Priority: explicit override > `DNA_BASE_DIR` env > `./.dna`.
 */
export function resolveDefaultFsUrl(baseDirOverride?: string): string {
  const base = baseDirOverride ?? process.env.DNA_BASE_DIR;
  if (base) return `file://${base}`;
  return "file://.dna";
}
