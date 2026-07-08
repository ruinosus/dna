"""SqliteSource — WritableSourcePort backed by SQLite (async via aiosqlite)."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator

import aiosqlite

if TYPE_CHECKING:
    from dna.kernel.capabilities import SourceCapabilities

logger = logging.getLogger(__name__)


class SqliteSource:
    """WritableSourcePort implementation backed by a SQLite database.

    Supports drafts, versioning, and forward-only migrations.

    Usage::

        source = SqliteSource("path/to/db.sqlite")
        await source.connect()
        # ... use source ...
        await source.close()
    """

    supports_readers: bool = False

    # s-sqlite-cross-process-invalidation — SQLite has no outbox/LISTEN-NOTIFY
    # (that's Postgres/Phase 15.1 only), so a SECOND process never learns of this
    # process's writes. A multi-process SQLite deployment serves stale data; the
    # source_factory warns loudly at boot (or refuses, opt-in). False here is the
    # honest signal callers/tests introspect.
    supports_cross_process_invalidation: bool = False

    def __init__(
        self,
        db_path: str,
        writers: list | None = None,
        readers: list | None = None,
    ) -> None:
        self._db_path = db_path
        self._writers = writers or []
        self._readers = readers or []
        self._kernel: object | None = None
        self._connected = False

    def attach_kernel(self, kernel: object) -> None:
        """H2 — KernelAttachable Protocol implementation.

        Copies the kernel's registered writers + readers into this
        source so bundle writes (which depend on ``self._writers``
        producing serialised entries via ``WriterPort.write``) work
        even when this source was instantiated directly via
        ``Kernel.auto(source=SqliteSource(...))``. Idempotent — only
        replaces lists when they're empty (preserves explicit
        constructor injection from ``source_factory``).
        """
        from dna.kernel import Kernel as _KernelType
        if not isinstance(kernel, _KernelType):
            raise TypeError(
                f"attach_kernel requires a Kernel instance; got {type(kernel).__name__}"
            )
        self._kernel = kernel
        if not self._writers:
            self._writers = list(kernel._writers)
        if not self._readers:
            self._readers = list(kernel._readers)

    @asynccontextmanager
    async def _acquire(self) -> AsyncIterator[aiosqlite.Connection]:
        """Yield a FRESH connection per operation (s-sqlite-single-connection).

        Replaces the single shared ``self._conn`` that serialized every caller and
        could leave a cursor mid-flight when a coroutine was cancelled. Each
        operation gets its own aiosqlite connection (WAL persists in the file;
        ``foreign_keys`` is per-connection so it's re-applied here) and the
        connection is ALWAYS closed in ``finally`` — so a cancelled coroutine
        cleans up its own cursor/transaction instead of corrupting a shared one.
        """
        conn = await aiosqlite.connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            await conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            await conn.close()

    async def connect(self) -> None:
        """Configure the database (WAL pragma persisted to the file) + run
        migrations once. No persistent connection is kept — operations acquire
        their own via ``_acquire`` (s-sqlite-single-connection)."""
        async with self._acquire() as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await self._run_migrations(conn)
        self._connected = True

    async def close(self) -> None:
        """No-op: connections are per-operation now (nothing persistent to close)."""
        self._connected = False

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    async def _run_migrations(self, conn: aiosqlite.Connection) -> None:
        from .migrations import MIGRATIONS

        # Ensure schema_migrations table exists (bootstrap)
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        await conn.commit()

        cursor = await conn.execute("SELECT version FROM schema_migrations")
        rows = await cursor.fetchall()
        applied = {row["version"] for row in rows}

        for version in sorted(MIGRATIONS):
            if version in applied:
                continue
            logger.info("Applying migration v%d", version)
            await conn.executescript(MIGRATIONS[version])
            await conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _now()),
            )
            await conn.commit()

    # ------------------------------------------------------------------
    # SourcePort (read)
    # ------------------------------------------------------------------

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return Genome + KindDefinition + LayerPolicy via fast WHERE filter.

        Phase 16. Uses ``WHERE kind IN (...)`` so cold-start fetches a
        constant-bounded number of rows instead of the full scope.

        Tenant semantics: when ``tenant`` is set, the tenant-published
        ``Genome`` shadows the platform Genome (Phase 9). KindDefinition
        and LayerPolicy are non-overlayable per Phase 16 — always read
        from platform (tenant IS NULL).
        """
        async with self._acquire() as conn:
            from dna.kernel.protocols import BOOTSTRAP_KIND_NAMES
            placeholders = ",".join("?" for _ in BOOTSTRAP_KIND_NAMES)
            cursor = await conn.execute(
                f"SELECT content FROM documents WHERE scope=? "
                f"AND kind IN ({placeholders}) AND tenant IS NULL",
                (scope, *BOOTSTRAP_KIND_NAMES),
            )
            rows = await cursor.fetchall()
            out = [json.loads(dict(r)["content"]) for r in rows]

            if tenant:
                cursor = await conn.execute(
                    "SELECT content FROM documents WHERE scope=? "
                    "AND kind='Genome' AND tenant=? LIMIT 1",
                    (scope, tenant),
                )
                tpkg_row = await cursor.fetchone()
                if tpkg_row is not None:
                    tenant_pkg = json.loads(dict(tpkg_row)["content"])
                    out = [d for d in out if d.get("kind") != "Genome"]
                    out.append(tenant_pkg)
            return out

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        # Merge instance readers with caller-passed ones (deduplicate by identity)
        async with self._acquire() as conn:
            effective_readers = list(self._readers)
            for r in (readers or []):
                if r not in effective_readers:
                    effective_readers.append(r)

            cursor = await conn.execute(
                "SELECT kind, name, content FROM documents WHERE scope=?",
                (scope,),
            )
            rows = await cursor.fetchall()

            from dna.kernel.bundle_handle import DictBundleHandle

            out: list[dict[str, Any]] = []
            for row in rows:
                row_dict = dict(row)
                entries = await self._load_bundle_entries(scope, row_dict["kind"], row_dict["name"])
                if entries and effective_readers:
                    handle = DictBundleHandle(row_dict["name"], entries)
                    matched = False
                    for reader in effective_readers:
                        try:
                            if reader.detect(handle):
                                out.append(reader.read(handle))
                                matched = True
                                break
                        except Exception:
                            continue
                    if matched:
                        continue
                # Fallback: cached parsed dict
                out.append(json.loads(row_dict["content"]))
            return out

    async def list_doc_refs(
        self, scope: str, *, kind: str | None = None,
        tenant: str | None = None,
    ) -> list[tuple[str, str]]:
        """L1 granular access — single SELECT indexed.

        SQLite adapter pre-data tenant column; ignore tenant kwarg
        until layer support lands (back-compat).
        """
        async with self._acquire() as conn:
            _ = tenant  # SQLite source pre-Phase-8a; no tenant column.
            if kind:
                cursor = await conn.execute(
                    "SELECT kind, name FROM documents "
                    "WHERE scope=? AND kind=? ORDER BY kind, name",
                    (scope, kind),
                )
            else:
                cursor = await conn.execute(
                    "SELECT kind, name FROM documents "
                    "WHERE scope=? ORDER BY kind, name",
                    (scope,),
                )
            rows = await cursor.fetchall()
            return [(dict(r)["kind"], dict(r)["name"]) for r in rows]

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers: list | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """L1 granular access — load 1 doc + bundle entries."""
        async with self._acquire() as conn:
            _ = tenant  # SQLite source pre-Phase-8a; no tenant column.
            effective_readers = list(self._readers)
            for r in (readers or []):
                if r not in effective_readers:
                    effective_readers.append(r)

            cursor = await conn.execute(
                "SELECT content FROM documents "
                "WHERE scope=? AND kind=? AND name=?",
                (scope, kind, name),
            )
            row = await cursor.fetchone()
            if row is None:
                return None

            entries = await self._load_bundle_entries(scope, kind, name)
            from dna.kernel.bundle_handle import DictBundleHandle
            if entries and effective_readers:
                handle = DictBundleHandle(name, entries)
                for reader in effective_readers:
                    try:
                        if reader.detect(handle):
                            return reader.read(handle)
                    except Exception:  # noqa: BLE001
                        continue
            return json.loads(dict(row)["content"])

    async def _load_bundle_entries(
        self, scope: str, kind: str, name: str, *, tenant: str = "",
    ) -> dict[str, str]:
        """Fetch all entries for a bundle as {entry_path: content}.

        Tenant-scoped: since migration v8 the PK includes tenant, so the
        same (scope, kind, name, entry_path) can hold one row per tenant.
        We filter to a single tenant (base layer ``''`` by default) so an
        overlay tenant's entries don't leak into a base-layer bundle load
        (which would collide on entry_path in the dict comprehension).
        """
        async with self._acquire() as conn:
            cursor = await conn.execute(
                "SELECT entry_path, content FROM bundle_entries "
                "WHERE scope=? AND kind=? AND name=? AND COALESCE(tenant, '')=?",
                (scope, kind, name, tenant),
            )
            rows = await cursor.fetchall()
            return {dict(r)["entry_path"]: dict(r)["content"] for r in rows}

    async def fetch_bundle_entry(
        self,
        scope: str,
        container: str,
        name: str,
        entry: str,
        *,
        tenant: str | None = None,
        kind: str | None = None,
    ) -> bytes:
        """Read a single bundle entry by name (Phase 14w cross-adapter
        capability). Mirrors PostgresWritableSource.fetch_bundle_entry.

        Tenant overlay is preferred when present, base layer is the
        fallback. SQLite stores ``tenant`` as nullable TEXT (Phase 2c
        migration); rows from before the migration have
        ``tenant IS NULL`` which we treat as base-layer rows.

        Disambiguation: ``kind`` (when provided by the kernel)
        narrows the lookup to a specific Kind's bundle table rows so
        a ``Skill`` named ``foo`` and a ``GraphifyArtifact`` named
        ``foo`` in the same scope don't collide. Without ``kind`` we
        fall back to ``(scope, name, entry_path)`` and accept the
        rare collision risk — older callers that built the kernel
        before the protocol gained the kwarg fall through this path.
        """
        async with self._acquire() as conn:
            candidates: list[str] = []
            if tenant:
                candidates.append(tenant)
            candidates.append("")  # base layer fallback

            for tenant_val in candidates:
                if kind is not None:
                    cursor = await conn.execute(
                        "SELECT content FROM bundle_entries "
                        "WHERE scope=? AND kind=? AND name=? AND entry_path=? "
                        "AND COALESCE(tenant, '')=? LIMIT 1",
                        (scope, kind, name, entry, tenant_val),
                    )
                else:
                    cursor = await conn.execute(
                        "SELECT content FROM bundle_entries "
                        "WHERE scope=? AND name=? AND entry_path=? "
                        "AND COALESCE(tenant, '')=? LIMIT 1",
                        (scope, name, entry, tenant_val),
                    )
                row = await cursor.fetchone()
                if row is not None:
                    content = dict(row)["content"]
                    if isinstance(content, str):
                        return content.encode("utf-8")
                    return bytes(content)
            raise FileNotFoundError(
                f"Bundle entry not found: scope={scope!r} container={container!r} "
                f"kind={kind!r} name={name!r} entry={entry!r} tenant={tenant!r}"
            )

    async def write_bundle_entry(
        self,
        scope: str,
        container: str,
        name: str,
        entry: str,
        content: bytes | str,
        *,
        tenant: str | None = None,
        kind: str | None = None,
    ) -> None:
        """BundleEntryWritable impl — UPSERT a binary entry idempotently.

        Mirrors the Postgres adapter. ``tenant`` lives in the
        ``tenant`` column so the bundle row aligns with the
        ``documents`` row (delete joins both on tenant) — fixing the
        same orphan-bundle bug class observed on Postgres
        (2026-05-21).

        Content is stored as BLOB. SQLite's TEXT vs BLOB distinction
        is loose at the storage layer but explicit on read: the
        ``fetch_bundle_entry`` returns bytes whether the row holds a
        str or bytes payload.
        """
        async with self._acquire() as conn:
            kind_key = kind or container
            tenant_val = tenant or ""
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).isoformat()
            # s-sqlite-bundle-tenant-pk — bundle_entries' PRIMARY KEY now includes
            # tenant (migration v8 rebuild), matching the Postgres adapter's
            # 5-tuple key. Two tenants writing the same (scope, kind, name,
            # entry_path) no longer collide. The ON CONFLICT target is the full
            # 5-tuple; tenant_val coalesces None→'' to align with the PK's
            # NOT NULL DEFAULT '' column. (i-083 was the interim PK-only fix; this
            # supersedes it.)
            await conn.execute(
                "INSERT INTO bundle_entries "
                "(scope, kind, name, entry_path, content, updated_at, tenant) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(scope, kind, name, entry_path, tenant) "
                "DO UPDATE SET content=excluded.content, "
                "updated_at=excluded.updated_at",
                (scope, kind_key, name, entry, content, ts, tenant_val),
            )
            await conn.commit()

    async def resolve_ref(self, scope: str, ref: str) -> str:
        return ""

    async def query(
        self, scope: str, kind: str, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant=None,
    ):
        """Marco A — native push-down via json_extract.

        SQLite cousin of PostgresSource.query (Story s-postgres-source-query-impl).
        Translates QueryFilter into ``WHERE json_extract(content, '$.spec.X') = ?``
        + composes ORDER BY / LIMIT / OFFSET. Tenant overlay: 2 fetches
        + merge in Python, mirror of PG semantics. Projection applied
        in Python via the shared ``_project_doc`` helper.

        Index coverage (migration v7):
          - $.spec.status, $.spec.feature, $.spec.updated_at — B-tree
            expression indices. Other spec.X queries fall back to scan
            (SQLite has no GIN equivalent).

        Tenant column semantics differ from PG: SQLite uses ``tenant IS NULL``
        for base layer (Phase 2c convention); PG uses ``tenant=''``. The
        SQL fragments below encode that difference; everything else mirrors
        PG.
        """
        from dna.kernel.protocols import (
            QueryError, _project_doc, _apply_order_by,
        )

        if filter is not None and not isinstance(filter, dict):
            raise QueryError(f"filter must be dict, got {type(filter).__name__}")

        # Materialize ALL matching docs WHILE the connection is open, then close
        # it BEFORE yielding. Holding the connection open across ``yield`` leaks
        # aiosqlite's (non-daemon) worker thread when a consumer breaks early —
        # e.g. ``mi.one()`` takes the first row and stops, so this generator
        # suspends at the yield, the ``async with`` __aexit__ never runs, the
        # connection never closes, its worker thread never joins, and the
        # interpreter HANGS at exit waiting on it. That is exactly what stalled
        # CI shard 3 for 17min after "456 passed". (s-sqlite-single-connection)
        async with self._acquire() as conn:
            async def _fetch_one_tenant(t: str | None) -> list[dict[str, Any]]:
                # Base params: scope=$1, kind=$2. Tenant predicate is either
                # "tenant IS NULL" (no param) or "tenant=?" (1 param).
                params: list[Any] = [scope, kind]
                tenant_clause = "tenant IS NULL" if t is None else "tenant=?"
                if t is not None:
                    params.append(t)
                where_sql, where_params = _build_sqlite_where(filter)
                params.extend(where_params)
                order_sql = _build_sqlite_order(order_by) if order_by else ""
                limit_sql = ""
                if limit is not None:
                    limit_sql += " LIMIT ?"
                    params.append(int(limit))
                if offset is not None and offset > 0:
                    limit_sql += " OFFSET ?"
                    params.append(int(offset))
                sql = (
                    f"SELECT name, kind, content FROM documents "
                    f"WHERE scope=? AND kind=? AND {tenant_clause}"
                    f"{where_sql}"
                    f"{order_sql}"
                    f"{limit_sql}"
                )
                cursor = await conn.execute(sql, tuple(params))
                rows = await cursor.fetchall()
                return [json.loads(dict(r)["content"]) for r in rows]

            if tenant is None:
                docs = await _fetch_one_tenant(None)
            else:
                overlay_docs = await _fetch_one_tenant(tenant)
                base_docs = await _fetch_one_tenant(None)
                shadow_keys = {
                    (d.get("kind"), (d.get("metadata") or {}).get("name"))
                    for d in overlay_docs
                }
                docs = [
                    d for d in base_docs
                    if (d.get("kind"), (d.get("metadata") or {}).get("name")) not in shadow_keys
                ]
                docs.extend(overlay_docs)
                if order_by:
                    docs = _apply_order_by(docs, order_by)
                if offset:
                    docs = docs[int(offset):]
                if limit is not None:
                    docs = docs[: int(limit)]

        # Connection is CLOSED here — yield from the in-memory list so an
        # early-breaking consumer can never leak a connection/worker thread.
        for doc in docs:
            if projection:
                yield _project_doc(doc, projection)
            else:
                yield doc

    async def count(
        self, scope: str, kind: str, *,
        filter=None, group_by=None, tenant=None,
    ) -> dict[str, Any]:
        """F2 — rides this adapter's native ``query`` push-down for the
        filter via the shared aggregation helper
        (``query_fallback.count_via_query``); grouping is a Counter in
        Python. Native ``SELECT count(*) … GROUP BY`` push-down can land
        later if SQLite scopes grow."""
        from dna.kernel.query_fallback import count_via_query
        return await count_via_query(
            self, scope, kind, filter=filter, group_by=group_by, tenant=tenant,
        )

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]:
        async with self._acquire() as conn:
            cursor = await conn.execute(
                "SELECT content FROM layer_documents "
                "WHERE scope=? AND layer_id=? AND layer_value=?",
                (scope, layer_id, layer_value),
            )
            rows = await cursor.fetchall()
            return [json.loads(dict(r)["content"]) for r in rows]

    async def save_layer_document(
        self, scope: str, layer_id: str, layer_value: str,
        kind: str, name: str, raw: dict,
    ) -> None:
        """Save a document into a layer overlay."""
        async with self._acquire() as conn:
            await conn.execute(
                "INSERT INTO layer_documents (scope, layer_id, layer_value, kind, name, content, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(scope, layer_id, layer_value, kind, name) DO UPDATE SET "
                "content=excluded.content, updated_at=excluded.updated_at",
                (scope, layer_id, layer_value, kind, name, json.dumps(raw), _now()),
            )
            await conn.commit()

    async def delete_layer_document(
        self, scope: str, layer_id: str, layer_value: str,
        kind: str, name: str,
    ) -> None:
        """Remove a document from a layer overlay."""
        async with self._acquire() as conn:
            await conn.execute(
                "DELETE FROM layer_documents "
                "WHERE scope=? AND layer_id=? AND layer_value=? AND kind=? AND name=?",
                (scope, layer_id, layer_value, kind, name),
            )
            await conn.commit()

    async def list_layers(self, scope: str) -> list[dict[str, str]]:
        """List all available layer_id:layer_value pairs for a scope."""
        async with self._acquire() as conn:
            cursor = await conn.execute(
                "SELECT DISTINCT layer_id, layer_value FROM layer_documents "
                "WHERE scope=? ORDER BY layer_id, layer_value",
                (scope,),
            )
            rows = await cursor.fetchall()
            return [{"layer_id": dict(r)["layer_id"], "layer_value": dict(r)["layer_value"]} for r in rows]

    # ------------------------------------------------------------------
    # WritableSourcePort (write)
    # ------------------------------------------------------------------

    async def save_document(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None = None,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        write_class: str = "substantive",
        version_retention: int | None = None,
    ) -> str:
        # version_retention (s-version-prune-record-plane-churn): keep only the
        # last N versions for this doc (record-plane Kinds pass 3); None = full
        # history. The latest version IS the current doc here, so prune never
        # touches it (we keep the top-N by version number).
        # write_class is part of the WritableSourcePort contract (Postgres NOTIFY
        # classification); SQLite emits no events, so it accepts and ignores it
        # (s-buswrite-class-substantive-cue).
        # Phase 2c: tenant is stored as a first-class column. Layer arg
        # is folded into tenant when layer=("tenant", X) — matches FS
        # adapter back-compat. Other layer ids are not yet supported by
        # SqliteSource (would need save_layer_document).
        async with self._acquire() as conn:
            if layer is not None and layer[0] == "tenant" and tenant is None:
                tenant = layer[1]
            elif layer is not None:
                raise NotImplementedError(
                    f"SqliteSource does not yet support non-tenant layers "
                    f"(got layer={layer!r}). Use save_layer_document directly."
                )

            # Try registered writers — bundle path
            bundle_entries: dict[str, str] | None = None
            from dna.kernel.bundle_handle import DictBundleHandle
            for w in self._writers:
                if w.can_write(raw):
                    handle = DictBundleHandle(name, {})
                    w.write(handle, raw)
                    bundle_entries = {
                        e: handle.read_text(e)
                        for e in handle.iter_entries(recursive=True)
                    }
                    break

            # Phase 10g — extract semver for the Genome catalog. Pre-check
            # immutability so we surface a typed exception rather than letting
            # SQLite raise an opaque IntegrityError on the partial unique index.
            spec_version = None
            if kind == "Genome":
                spec_version = ((raw.get("spec") or {}).get("version")) or None
            if spec_version:
                if tenant is None:
                    cur = await conn.execute(
                        "SELECT 1 FROM versions WHERE scope=? AND kind=? AND name=? "
                        "AND tenant IS NULL AND semver=? LIMIT 1",
                        (scope, kind, name, spec_version),
                    )
                else:
                    cur = await conn.execute(
                        "SELECT 1 FROM versions WHERE scope=? AND kind=? AND name=? "
                        "AND tenant=? AND semver=? LIMIT 1",
                        (scope, kind, name, tenant, spec_version),
                    )
                if (await cur.fetchone()) is not None:
                    from dna.kernel.protocols import VersionAlreadyPublished
                    raise VersionAlreadyPublished(
                        f"Module {name!r} version {spec_version!r} already "
                        f"published to scope {scope!r} (tenant={tenant!r}). "
                        "Bump and republish."
                    )

            # Determine next version number (per-tenant scope)
            if tenant is None:
                cursor = await conn.execute(
                    "SELECT COALESCE(MAX(version), 0) AS max_v FROM versions "
                    "WHERE scope=? AND kind=? AND name=? AND tenant IS NULL",
                    (scope, kind, name),
                )
            else:
                cursor = await conn.execute(
                    "SELECT COALESCE(MAX(version), 0) AS max_v FROM versions "
                    "WHERE scope=? AND kind=? AND name=? AND tenant=?",
                    (scope, kind, name, tenant),
                )
            row = await cursor.fetchone()
            next_version = dict(row)["max_v"] + 1

            await conn.execute(
                "INSERT INTO versions "
                "(scope, kind, name, content, version, is_draft, author, "
                "created_at, tenant, semver) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                (scope, kind, name, json.dumps(raw), next_version,
                 author, _now(), tenant, spec_version),
            )

            # s-version-prune-record-plane-churn — keep only the last N versions
            # for record-plane Kinds (prune older by version number). The latest
            # version (the current doc) is always in the kept top-N.
            if version_retention is not None and version_retention >= 0:
                cutoff = next_version - version_retention
                if tenant is None:
                    await conn.execute(
                        "DELETE FROM versions WHERE scope=? AND kind=? AND name=? "
                        "AND tenant IS NULL AND version <= ?",
                        (scope, kind, name, cutoff),
                    )
                else:
                    await conn.execute(
                        "DELETE FROM versions WHERE scope=? AND kind=? AND name=? "
                        "AND tenant=? AND version <= ?",
                        (scope, kind, name, tenant, cutoff),
                    )

            if bundle_entries is not None:
                # Full-replace semantics: wipe old entries, then reinsert (per-tenant).
                # tenant is part of the PK since migration v8 with '' as the canonical
                # base-layer sentinel (NOT NULL) — coalesce None→'' on both wipe + write.
                tenant_val = tenant or ""
                await conn.execute(
                    "DELETE FROM bundle_entries "
                    "WHERE scope=? AND kind=? AND name=? AND COALESCE(tenant, '')=?",
                    (scope, kind, name, tenant_val),
                )
                ts = _now()
                for entry_path, body in bundle_entries.items():
                    await conn.execute(
                        "INSERT INTO bundle_entries "
                        "(scope, kind, name, entry_path, content, updated_at, tenant) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (scope, kind, name, entry_path, body, ts, tenant_val),
                    )

            await conn.commit()
            return str(next_version)

    async def publish(self, scope: str, kind: str, name: str) -> str:
        # Find latest draft
        async with self._acquire() as conn:
            cursor = await conn.execute(
                "SELECT id, content, version FROM versions "
                "WHERE scope=? AND kind=? AND name=? AND is_draft=1 "
                "ORDER BY version DESC LIMIT 1",
                (scope, kind, name),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError("no_draft")

            row_dict = dict(row)
            version = row_dict["version"]
            content = row_dict["content"]
            version_id = row_dict["id"]

            # UPSERT into documents
            await conn.execute(
                "INSERT INTO documents (scope, kind, name, content, version, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(scope, kind, name) DO UPDATE SET "
                "content=excluded.content, version=excluded.version, updated_at=excluded.updated_at",
                (scope, kind, name, content, version, _now()),
            )

            # Mark draft as published
            await conn.execute(
                "UPDATE versions SET is_draft=0 WHERE id=?",
                (version_id,),
            )
            await conn.commit()
            return str(version)

    async def delete_document(
        self, scope: str, kind: str, name: str,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
    ) -> None:
        # Phase 2c: tenant + layer back-compat (see save_document).
        async with self._acquire() as conn:
            if layer is not None and layer[0] == "tenant" and tenant is None:
                tenant = layer[1]
            elif layer is not None:
                raise NotImplementedError(
                    f"SqliteSource does not yet support non-tenant layers "
                    f"(got layer={layer!r})."
                )

            if tenant is None:
                tenant_filter = "AND tenant IS NULL"
                params: tuple = (scope, kind, name)
            else:
                tenant_filter = "AND tenant = ?"
                params = (scope, kind, name, tenant)

            cursor = await conn.execute(
                f"SELECT 1 FROM documents "
                f"WHERE scope=? AND kind=? AND name=? {tenant_filter}",
                params,
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError("not_found")

            await conn.execute(
                f"DELETE FROM documents "
                f"WHERE scope=? AND kind=? AND name=? {tenant_filter}",
                params,
            )
            await conn.execute(
                f"DELETE FROM versions "
                f"WHERE scope=? AND kind=? AND name=? {tenant_filter}",
                params,
            )
            # bundle_entries' base layer is tenant='' (NOT NULL, migration v8), not
            # NULL like documents/versions — coalesce so a None tenant wipes base rows.
            await conn.execute(
                "DELETE FROM bundle_entries "
                "WHERE scope=? AND kind=? AND name=? AND COALESCE(tenant, '')=?",
                (scope, kind, name, tenant or ""),
            )
            await conn.commit()

    async def save_manifest(self, scope: str, manifest: dict) -> str:
        kind = manifest.get("kind") or "Genome"
        return await self.save_document(
            scope, kind,
            manifest.get("metadata", {}).get("name", scope),
            manifest,
        )

    async def list_versions(
        self, scope: str, kind: str, name: str,
    ) -> list[dict]:
        async with self._acquire() as conn:
            cursor = await conn.execute(
                "SELECT id, version, is_draft, author, created_at FROM versions "
                "WHERE scope=? AND kind=? AND name=? ORDER BY version DESC",
                (scope, kind, name),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_version(
        self, scope: str, kind: str, name: str, version_id: str,
    ) -> dict:
        async with self._acquire() as conn:
            cursor = await conn.execute(
                "SELECT id, scope, kind, name, content, version, is_draft, author, created_at "
                "FROM versions WHERE scope=? AND kind=? AND name=? AND version=?",
                (scope, kind, name, int(version_id)),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError("version_not_found")
            result = dict(row)
            result["content"] = json.loads(result["content"])
            return result

    async def load_drafts(self, scope: str) -> list[dict]:
        async with self._acquire() as conn:
            cursor = await conn.execute(
                "SELECT v.kind, v.name, v.content, v.version, v.created_at "
                "FROM versions v "
                "INNER JOIN ("
                "  SELECT kind, name, MAX(version) AS max_v "
                "  FROM versions WHERE scope=? AND is_draft=1 "
                "  GROUP BY kind, name"
                ") latest ON v.kind=latest.kind AND v.name=latest.name AND v.version=latest.max_v "
                "WHERE v.scope=? AND v.is_draft=1",
                (scope, scope),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def list_scopes(self) -> list[str]:
        async with self._acquire() as conn:
            cursor = await conn.execute(
                "SELECT DISTINCT scope FROM documents ORDER BY scope"
            )
            rows = await cursor.fetchall()
            return [dict(r)["scope"] for r in rows]

    # ── Phase 10g — Module catalog version surface ────────────────────

    async def list_module_versions(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict]:
        """List published semver releases of a Module. See Postgres twin."""
        async with self._acquire() as conn:
            if tenant is None:
                cursor = await conn.execute(
                    "SELECT semver, content, created_at FROM versions "
                    "WHERE scope=? AND kind='Genome' AND name=? "
                    "AND tenant IS NULL AND semver IS NOT NULL "
                    "ORDER BY created_at ASC",
                    (scope, scope),
                )
            else:
                cursor = await conn.execute(
                    "SELECT semver, content, created_at FROM versions "
                    "WHERE scope=? AND kind='Genome' AND name=? AND tenant=? "
                    "AND semver IS NOT NULL "
                    "ORDER BY created_at ASC",
                    (scope, scope, tenant),
                )
            rows = await cursor.fetchall()
            out: list[dict] = []
            for r in rows:
                d = dict(r)
                try:
                    spec = json.loads(d["content"]).get("spec") or {}
                except Exception:
                    spec = {}
                out.append({
                    "version": d["semver"],
                    "deprecated": bool(spec.get("deprecated", False)),
                    "deprecated_message": spec.get("deprecated_message"),
                    "published_at": d["created_at"],
                })
            return out

    async def get_module_version(
        self, scope: str, version: str, *, tenant: str | None = None,
    ) -> dict | None:
        """Return the frozen Module manifest for ``scope@version``."""
        async with self._acquire() as conn:
            if tenant is None:
                cursor = await conn.execute(
                    "SELECT content FROM versions WHERE scope=? AND kind='Genome' "
                    "AND name=? AND tenant IS NULL AND semver=? LIMIT 1",
                    (scope, scope, version),
                )
            else:
                cursor = await conn.execute(
                    "SELECT content FROM versions WHERE scope=? AND kind='Genome' "
                    "AND name=? AND tenant=? AND semver=? LIMIT 1",
                    (scope, scope, tenant, version),
                )
            row = await cursor.fetchone()
            if row is None:
                return None
            try:
                return json.loads(dict(row)["content"])
            except Exception:
                return None

    async def deprecate_module_version(
        self, scope: str, version: str, *,
        tenant: str | None = None, message: str | None = None,
    ) -> bool:
        """Flip ``spec.deprecated=true`` on the archived row in-place."""
        async with self._acquire() as conn:
            existing = await self.get_module_version(scope, version, tenant=tenant)
            if existing is None:
                return False
            spec = existing.setdefault("spec", {})
            spec["deprecated"] = True
            if message:
                spec["deprecated_message"] = message
            new_content = json.dumps(existing)
            if tenant is None:
                await conn.execute(
                    "UPDATE versions SET content=? "
                    "WHERE scope=? AND kind='Genome' AND name=? AND tenant IS NULL AND semver=?",
                    (new_content, scope, scope, version),
                )
            else:
                await conn.execute(
                    "UPDATE versions SET content=? "
                    "WHERE scope=? AND kind='Genome' AND name=? AND tenant=? AND semver=?",
                    (new_content, scope, scope, tenant, version),
                )
            # Mirror to latest pointer when applicable
            if tenant is None:
                cur = await conn.execute(
                    "SELECT content FROM documents WHERE scope=? AND kind='Genome' "
                    "AND name=? AND tenant IS NULL",
                    (scope, scope),
                )
            else:
                cur = await conn.execute(
                    "SELECT content FROM documents WHERE scope=? AND kind='Genome' "
                    "AND name=? AND tenant=?",
                    (scope, scope, tenant),
                )
            row = await cur.fetchone()
            if row is not None:
                try:
                    cur_spec = json.loads(dict(row)["content"]).get("spec") or {}
                    if cur_spec.get("version") == version:
                        if tenant is None:
                            await conn.execute(
                                "UPDATE documents SET content=? "
                                "WHERE scope=? AND kind='Genome' AND name=? AND tenant IS NULL",
                                (new_content, scope, scope),
                            )
                        else:
                            await conn.execute(
                                "UPDATE documents SET content=? "
                                "WHERE scope=? AND kind='Genome' AND name=? AND tenant=?",
                                (new_content, scope, scope, tenant),
                            )
                except Exception:
                    pass
            await conn.commit()
            return True

    def capabilities(self) -> "SourceCapabilities":
        """Explicit contract declaration (s-sourceport-contract-cleanup) --
        kept honest by the adapter conformance test (declaration ==
        reflection-derived oracle)."""
        from dna.kernel.capabilities import (
            DELETE_OPTIONAL_KWARGS,
            SAVE_OPTIONAL_KWARGS,
            SourceCapabilities,
        )
        return SourceCapabilities(
            source="sqlite",
            drafts=True,
            versions=True,
            layers=True,
            bundle_read=True,
            bundle_write=True,
            kernel_attachable=True,
            granular_list=True,
            granular_one=True,
            query_pushdown=True,
            tenant_layer_writes=True,
            write_kwargs=SAVE_OPTIONAL_KWARGS,
            delete_kwargs=DELETE_OPTIONAL_KWARGS,
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Marco A — SQLite SQL helpers (s-sqlite-source-query-impl).
#
# Mirrors python/dna/adapters/postgres/source.py with SQLite dialect:
#   - json_extract(content, '$.spec.X') instead of content::jsonb->...
#   - `?` placeholder instead of $N
#   - IN expanded to (?, ?, ?) instead of = ANY($N::text[])
# ---------------------------------------------------------------------------

_SQLITE_OP_MAP = {
    "eq": "=", "neq": "<>",
    "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "like": "LIKE",
}


def _sqlite_field_expr(path: str) -> str:
    """Translate a dotted ``field_path`` into a SQLite expression referencing
    ``documents``. SQLite-specific equivalent of ``_pg_field_expr``.

    Path mapping:
      - ``name`` / ``metadata.name`` → ``name``       (dedicated column)
      - ``kind``                     → ``kind``        (dedicated column)
      - ``apiVersion``               → ``json_extract(content, '$.apiVersion')``
      - ``spec.X.Y`` / ``X``         → ``json_extract(content, '$.spec.X.Y')``
      - ``metadata.X``               → ``json_extract(content, '$.metadata.X')``
    """
    from dna.kernel.protocols import QueryError

    if not path or any(c in path for c in (";", "'", "\"", "(", ")")):
        raise QueryError(f"invalid field path: {path!r}")

    if path == "name" or path == "metadata.name":
        return "name"
    if path == "kind":
        return "kind"
    if path == "apiVersion":
        return "json_extract(content, '$.apiVersion')"

    if path.startswith("metadata.") or path.startswith("spec."):
        json_path = "$." + path
    else:
        json_path = "$.spec." + path

    # Quote escape: single quotes get doubled in SQLite literals. We
    # already rejected paths containing ', but defense in depth.
    json_path = json_path.replace("'", "''")
    return f"json_extract(content, '{json_path}')"


def _build_sqlite_where(filter: dict | None) -> tuple[str, list[Any]]:
    """Build a SQL WHERE fragment + param tuple from a QueryFilter.
    Returns ``("", [])`` when filter is empty. Fragment is prefixed
    with ``" AND "`` so it slots after the static scope/kind/tenant
    clause.
    """
    from dna.kernel.protocols import QueryError

    if not filter:
        return "", []

    clauses: list[str] = []
    params: list[Any] = []

    for path, expected in filter.items():
        field_expr = _sqlite_field_expr(path)

        if isinstance(expected, dict) and len(expected) == 1:
            op, val = next(iter(expected.items()))
            if op == "in":
                if not isinstance(val, (list, tuple)) or not val:
                    raise QueryError("'in' value must be non-empty list/tuple")
                placeholders = ",".join("?" for _ in val)
                clauses.append(f"{field_expr} IN ({placeholders})")
                params.extend(_sqlite_coerce_value(v) for v in val)
                continue
            if op not in _SQLITE_OP_MAP:
                raise QueryError(
                    f"unknown query operator {op!r} on field {path!r}; "
                    f"valid: {sorted(set(_SQLITE_OP_MAP) | {'in'})}"
                )
            clauses.append(f"{field_expr} {_SQLITE_OP_MAP[op]} ?")
            params.append(_sqlite_coerce_value(val))
        else:
            clauses.append(f"{field_expr} = ?")
            params.append(_sqlite_coerce_value(expected))

    return " AND " + " AND ".join(clauses), params


def _sqlite_coerce_value(val: Any) -> Any:
    """json_extract returns the native JSON type when scalar (int → int,
    str → str, bool → 0/1). For maximum portability with our shorthand
    syntax (``{"priority": 5}`` → equality on a TEXT or INT), coerce
    primitives to str to match how the Python fallback compares —
    avoids "5" != 5 surprises. Lists pass through (for IN handling)."""
    if val is None:
        return None
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, (str, int, float, list, tuple)):
        return val
    return str(val)


def _build_sqlite_order(order_by: list[str]) -> str:
    """Build a SQL ORDER BY fragment from a QueryOrder list. NULLS LAST
    applied universally (SQLite 3.30+). Older SQLite would need an
    ``ORDER BY column IS NULL, column`` trick — we require 3.30+ which
    has been default on macOS / Debian stable / pip wheels for years.
    """
    parts: list[str] = []
    for spec in order_by:
        descending = spec.startswith("-")
        path = spec[1:] if descending else spec
        expr = _sqlite_field_expr(path)
        direction = "DESC" if descending else "ASC"
        parts.append(f"{expr} {direction} NULLS LAST")
    return " ORDER BY " + ", ".join(parts) if parts else ""
