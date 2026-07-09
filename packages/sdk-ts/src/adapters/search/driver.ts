/**
 * SQLite driver shim for the sqlite-vec search provider — the ONE place that
 * papers over the two runtimes DNA's TS SDK runs under, so the provider itself
 * is runtime-agnostic:
 *
 *   - Bun (the test runner) → `bun:sqlite`. Bun auto-loads SQLite on the first
 *     `Database` open and extension loading must be enabled BEFORE that, via
 *     `Database.setCustomSQLite(libPath)`. We probe for a libsqlite3 that allows
 *     extensions (env `DNA_SQLITE_LIB`, then common macOS/Linux paths) exactly
 *     once, before opening anything. Bun's own bundled SQLite already allows it
 *     on most Linux builds, so the probe is a best-effort fallback.
 *   - Node ≥22.5 → `node:sqlite` (`DatabaseSync`, `{ allowExtension: true }`),
 *     which bundles a SQLite compiled with extension loading — no external lib.
 *
 * Both expose the tiny synchronous surface the provider needs. sqlite-vec is
 * loaded into every opened connection. If no runtime can load the extension,
 * `openSearchDb` throws `SqliteVecUnavailableError` — the provider surfaces it
 * and callers (CLI, conformance kit) degrade/skip with a clear reason rather
 * than crash.
 */

/** The minimal synchronous SQLite surface the provider drives. */
export interface SearchDb {
  exec(sql: string): void;
  run(sql: string, params?: unknown[]): { lastInsertRowid: number };
  get<T = Record<string, unknown>>(sql: string, params?: unknown[]): T | undefined;
  all<T = Record<string, unknown>>(sql: string, params?: unknown[]): T[];
  close(): void;
}

/** Thrown when no available runtime can load the sqlite-vec extension. */
export class SqliteVecUnavailableError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "SqliteVecUnavailableError";
  }
}

const isBun = typeof (globalThis as { Bun?: unknown }).Bun !== "undefined";

// Candidate libsqlite3 paths that permit extension loading. An explicit
// `DNA_SQLITE_LIB` override wins on any platform. Otherwise we only probe on
// macOS: Apple's system libsqlite3 (which Bun uses there) has extension loading
// DISABLED, so we point Bun at Homebrew's build. On Linux, Bun's bundled SQLite
// already allows loadExtension, so we add NO candidate and trust it — forcing a
// distro lib could regress if that build omitted extension support.
function libCandidates(): string[] {
  const out: string[] = [];
  const proc = (globalThis as {
    process?: { env?: Record<string, string>; platform?: string };
  }).process;
  if (proc?.env?.DNA_SQLITE_LIB) out.push(proc.env.DNA_SQLITE_LIB);
  if (proc?.platform === "darwin") {
    out.push(
      "/opt/homebrew/opt/sqlite/lib/libsqlite3.dylib",
      "/usr/local/opt/sqlite/lib/libsqlite3.dylib",
    );
  }
  return out;
}

let bunCustomSqliteChosen = false;

async function chooseBunSqlite(): Promise<void> {
  if (bunCustomSqliteChosen) return;
  bunCustomSqliteChosen = true; // decide once, before the first open
  const { Database } = (await import("bun:sqlite")) as {
    Database: { setCustomSQLite(path: string): void };
  };
  // Only set a custom lib if one exists on disk; otherwise trust Bun's bundled
  // SQLite (extension loading works on most Linux builds out of the box).
  let fs: { existsSync(p: string): boolean };
  try {
    fs = (await import("node:fs")) as typeof fs;
  } catch {
    return;
  }
  for (const path of libCandidates()) {
    if (fs.existsSync(path)) {
      try {
        Database.setCustomSQLite(path);
      } catch {
        /* already loaded or unsupported — fall through to bundled */
      }
      return;
    }
  }
}

async function openBun(path: string): Promise<SearchDb> {
  await chooseBunSqlite();
  const { Database } = (await import("bun:sqlite")) as {
    Database: new (p: string) => BunDatabase;
  };
  const sqliteVec = await import("sqlite-vec");
  const db = new Database(path);
  try {
    (sqliteVec as { load(db: unknown): void }).load(db);
  } catch (err) {
    db.close();
    throw new SqliteVecUnavailableError(
      "bun:sqlite could not load the sqlite-vec extension — set DNA_SQLITE_LIB "
        + "to a libsqlite3 that permits extension loading (e.g. Homebrew's "
        + "/opt/homebrew/opt/sqlite/lib/libsqlite3.dylib).",
      { cause: err },
    );
  }
  return {
    exec: (sql) => db.exec(sql),
    run: (sql, params = []) => {
      const info = db.query(sql).run(...(params as never[]));
      return { lastInsertRowid: Number(info.lastInsertRowid) };
    },
    get: (sql, params = []) => db.query(sql).get(...(params as never[])) as never,
    all: (sql, params = []) => db.query(sql).all(...(params as never[])) as never,
    close: () => db.close(),
  };
}

interface BunDatabase {
  exec(sql: string): void;
  query(sql: string): {
    run(...params: never[]): { lastInsertRowid: number | bigint };
    get(...params: never[]): unknown;
    all(...params: never[]): unknown[];
  };
  close(): void;
}

async function openNode(path: string): Promise<SearchDb> {
  let DatabaseSync: new (p: string, opts?: { allowExtension?: boolean }) => NodeDatabase;
  try {
    ({ DatabaseSync } = (await import("node:sqlite")) as {
      DatabaseSync: typeof DatabaseSync;
    });
  } catch (err) {
    throw new SqliteVecUnavailableError(
      "node:sqlite is unavailable (needs Node ≥22.5 with --experimental-sqlite "
        + "or ≥23.5). Run under Bun, or upgrade Node.",
      { cause: err },
    );
  }
  const sqliteVec = await import("sqlite-vec");
  const db = new DatabaseSync(path, { allowExtension: true });
  try {
    db.loadExtension((sqliteVec as { getLoadablePath(): string }).getLoadablePath());
  } catch (err) {
    db.close();
    throw new SqliteVecUnavailableError(
      "node:sqlite could not load the sqlite-vec extension.",
      { cause: err },
    );
  }
  return {
    exec: (sql) => db.exec(sql),
    run: (sql, params = []) => {
      const info = db.prepare(sql).run(...(params as never[]));
      return { lastInsertRowid: Number(info.lastInsertRowid) };
    },
    get: (sql, params = []) => db.prepare(sql).get(...(params as never[])) as never,
    all: (sql, params = []) => db.prepare(sql).all(...(params as never[])) as never,
    close: () => db.close(),
  };
}

interface NodeDatabase {
  exec(sql: string): void;
  prepare(sql: string): {
    run(...params: never[]): { lastInsertRowid: number | bigint };
    get(...params: never[]): unknown;
    all(...params: never[]): unknown[];
  };
  loadExtension(path: string): void;
  close(): void;
}

/**
 * Open a SQLite connection with sqlite-vec loaded, using whichever runtime
 * driver is available. Throws {@link SqliteVecUnavailableError} when neither
 * can load the extension.
 */
export async function openSearchDb(path: string): Promise<SearchDb> {
  return isBun ? openBun(path) : openNode(path);
}

/** Pack a float vector into sqlite-vec's float32 blob layout (parity with the
 *  Python `_serialize_f32`). */
export function serializeF32(vector: number[]): Uint8Array {
  return new Uint8Array(new Float32Array(vector).buffer);
}
