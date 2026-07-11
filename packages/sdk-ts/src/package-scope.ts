/**
 * Resolve a DNA scope embedded as PACKAGE DATA (`s-scope-as-package-data`).
 *
 * 1:1 parity with python `dna/package_scope.py`. A consumer that deploys an
 * app used to make the scope travel by hand — a brittle
 * `path.resolve(__dirname, "../../.dna")` plus a manual `COPY .dna` in the
 * Dockerfile. The image is the *app*, not the repo; forget the COPY and the
 * app boots with no scope. This module owns the deploy-safe alternative:
 * resolve the scope from INSIDE the installed package.
 *
 * The TS mechanism mirrors how the SDK finds its OWN bundled `*.kind.yaml`
 * (see `kernel/descriptor-loader.ts`): resolve relative to a module. Here the
 * anchor is a package NAME, so we resolve its `package.json` via
 * `createRequire(import.meta.url)` — the package root is that file's dir —
 * then join the scopes-root subpath (`.dna` by default). `npm`/`bun`/`pnpm`
 * install the package UNPACKED into `node_modules`, and the package's `files`
 * field carries the scope into the published tarball and into a Docker image,
 * so resolution works from a source checkout, an installed dependency, and a
 * container whose CWD is not the repo — zero path navigation, zero manual copy.
 *
 * Read-only by nature: package data is composition input, never a write
 * target. To WRITE a scope, use a filesystem or postgres source.
 */
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { dirname, isAbsolute, join } from "node:path";

/** The conventional scopes-root sub-directory inside a package (matches the
 * repo's own `.dna/<scope>/` layout). */
export const DEFAULT_SUBPATH = ".dna";

/** Raised when an `anchor` package / subpath can't be resolved to a real
 * on-disk scopes-root directory. */
export class PackageScopeNotFound extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PackageScopeNotFound";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

const require = createRequire(import.meta.url);

/**
 * Resolve the `.dna` scopes-root embedded in package `anchor`.
 *
 * `anchor` is a resolvable package specifier (e.g. `"app"`); `subpath` is the
 * scopes-root dir inside it (default `.dna`). Returns the concrete filesystem
 * path of `<anchor-package>/<subpath>` — the `baseDir` a FilesystemSource
 * consumes. Fails loud (`PackageScopeNotFound`) when the package cannot be
 * resolved or the subpath does not exist in the installed package.
 */
export function anchorScopesRoot(
  anchor: string,
  subpath: string = DEFAULT_SUBPATH,
): string {
  const pkgRoot = resolvePackageRoot(anchor);
  const base = subpath ? join(pkgRoot, subpath) : pkgRoot;
  if (!existsSync(base)) {
    throw new PackageScopeNotFound(
      `anchor '${anchor}' is installed, but its scopes-root '${subpath}' was ` +
        `not found at ${base}. Declare the scope files as package data so ` +
        `they ship in the tarball/image: add the scopes dir to the package's ` +
        `"files" array in package.json (e.g. "files": ["dist", "${subpath}"]). ` +
        `See the guide "Shipping a scope with your app".`,
    );
  }
  return base;
}

/** Locate a package's root dir from its name, via its `package.json`. */
function resolvePackageRoot(anchor: string): string {
  // Primary: resolve the package's package.json — its dir IS the package root.
  // (A package can gate this behind "exports"; the example adds the standard
  // `"./package.json": "./package.json"` so it always resolves.)
  try {
    return dirname(require.resolve(join(anchor, "package.json")));
  } catch {
    // Fallback: an absolute/relative path anchor (a directory, not a package
    // name) — treat it as the package root directly.
    if (isAbsolute(anchor) && existsSync(anchor)) return anchor;
    try {
      // Last resort: resolve the package entry point and use its dir. Only
      // reliable for a flat single-file package, but better than nothing.
      return dirname(require.resolve(anchor));
    } catch (err) {
      throw new PackageScopeNotFound(
        `anchor '${anchor}' is not resolvable — it must be an INSTALLED ` +
          `package that embeds the scope as package data (npm/bun install it, ` +
          `and list the scopes dir in the package's "files" so it ships). ` +
          `If it uses "exports", add "./package.json": "./package.json". ` +
          `Original resolve error: ${(err as Error).message}`,
      );
    }
  }
}
