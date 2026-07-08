"""PostgresSource — WritableSourcePort backed by PostgreSQL (asyncpg).

Schema mirrors SqliteSource for consistency:
  - documents: published documents (scope, kind, name, content, version)
  - versions: all versions with draft tracking
  - layer_documents: layer overlay documents

Requires asyncpg. Install: pip install asyncpg

Usage:
    import asyncpg
    from dna.adapters.postgres import PostgresSource

    pool = await asyncpg.create_pool("postgresql://user:pass@localhost/dna")
    source = PostgresSource(pool)
    await source.init()  # runs migrations
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg
    from dna.kernel.capabilities import SourceCapabilities

logger = logging.getLogger(__name__)

# s-pg-schema-identifier-guard: the schema is a SQL *identifier* — it can't be a
# bind parameter, so it's interpolated into ~40 statements via f-string. Validate
# it ONCE at construction against a conservative allowlist (unquoted lower-case
# Postgres identifier). The schema is trusted-config-only — it comes from
# env/deploy config (DNA_SOURCE_URL / wiring), NEVER from a request — but this
# guard removes the latent injection vector at the write hot path.
_VALID_SCHEMA_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

# Phase 15.1 — KernelEventBus channel name. Subscribers LISTEN on this.
# Single channel per database; payload differentiates by scope/tenant.
KERNEL_EVENTBUS_CHANNEL = "kernel_writes"


def _build_notify_payload(
    outbox_id: int,
    scope: str,
    tenant: str,
    kind: str,
    name: str,
    op: str,
    doc_version: int,
    author: str | None,
    write_class: str = "substantive",
) -> str:
    """Build the ``kernel_writes`` NOTIFY payload (i-076).

    MUST include ``author``: the ObserverBus bridge (cognitive-api) reads it
    to honor each hook's ``skip_if_authored_by_self`` /
    ``skip_if_authored_by_any_hook`` loop guards. Dropping it makes every
    cross-process event look human-authored, which defeated the guards and
    let scribe writes drive a self-sustaining feedback loop that saturated
    kinds-api. Pure + tiny so the contract is unit-tested without a DB.

    ``write_class`` (s-buswrite-class-substantive-cue / f-autopilot-rewrite)
    classifies the write as ``substantive`` (a real doc create/change) or
    ``cue`` (a pure metadata bump, e.g. oracle-cue raising a LessonLearned's
    surface_count). Cognitive hooks that react to substantive writes filter
    out ``cue`` events BY CLASS — so the H7↔S2 feedback cycle can't close by
    construction, instead of relying on the coarse "skip any hook author".
    """
    return json.dumps(
        {
            "id": outbox_id, "scope": scope, "tenant": tenant,
            "kind": kind, "name": name, "op": op,
            "doc_version": doc_version, "author": author or "",
            "write_class": write_class or "substantive",
        },
        separators=(",", ":"),
    )


class PostgresSource:
    """WritableSourcePort implementation backed by PostgreSQL (asyncpg)."""

    supports_readers: bool = False

    # s-sqlite-cross-process-invalidation — Postgres DOES propagate writes across
    # processes: every write logs to dna_outbox + pg_notify on KERNEL_EVENTBUS_CHANNEL
    # (Phase 15.1, see _emit_outbox), and subscribers LISTEN + invalidate. True.
    supports_cross_process_invalidation: bool = True

    def __init__(
        self,
        pool: "asyncpg.Pool",
        schema: str = "public",
        writers: list | None = None,
        readers: list | None = None,
    ) -> None:
        # Single asyncpg pool, tied to the loop it was created on.
        # Phase 15 — async-first bootstrap guarantees the pool is created
        # in the loop that will use it (uvicorn lifespan loop OR worker
        # asyncio.run loop). Pool-per-loop hack from earlier removed.
        self._pool = pool
        # s-pg-schema-identifier-guard: validate the schema identifier once
        # (trusted-config-only) — it's f-string-interpolated into ~40 statements
        # and can't be a bind param, so an unvalidated value would be a latent
        # SQL-injection vector on the write hot path.
        if not isinstance(schema, str) or not _VALID_SCHEMA_IDENT.match(schema):
            raise ValueError(
                f"Invalid Postgres schema identifier {schema!r}: must match "
                f"{_VALID_SCHEMA_IDENT.pattern} (trusted-config-only — set via "
                "deploy config, never from request input)."
            )
        self._schema = schema
        self._migrated = False
        self._writers = writers or []
        self._readers = readers or []
        self._kernel: object | None = None
        # Phase 15.1 — actor/cause for outbox attribution. Set at
        # __init__ (not attach_kernel) so direct callers like seed
        # scripts that bypass Kernel.auto still have these defaults
        # populated. Kernel-attached path overrides via attach_kernel
        # if needed.
        self._default_actor: str | None = os.environ.get("USER") or "system"
        self._default_cause: str | None = None
        # Perf (s-query-loadview-cache, 2026-05-28): memoize _load_view
        # per (scope, tenant). The query slow-path + load_all re-ran a
        # full-scope SQL load + per-doc reader-parse on EVERY call —
        # O(scope), event-loop-blocking, serialized under concurrency
        # (~1.2s/call on heavy scopes; 10 concurrent → ~12s). Cache the
        # canonical view; callers get deep copies so they may mutate
        # freely (the kinds-api list handler stamps inherited_from on
        # rows). Invalidated via on_write (the SAME proven path that
        # invalidates the kinds-api holder MI cache for local AND
        # cross-process writes) — wired in attach_kernel.
        self._view_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._view_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._view_invalidation_wired = False

    def attach_kernel(self, kernel: object) -> None:
        """H2 — KernelAttachable Protocol implementation. Mirrors the
        SQLite + Filesystem impls. Idempotent; preserves explicit
        constructor injection from ``source_factory``."""
        from dna.kernel import Kernel as _KernelType
        if not isinstance(kernel, _KernelType):
            raise TypeError(
                f"attach_kernel requires a Kernel instance; got {type(kernel).__name__}"
            )
        self._kernel = kernel
        # Wire view-cache invalidation onto the kernel's on_write bus.
        # on_write fires for local writes (kernel.write_document) AND
        # cross-process writes (EventBus pg_notify → kernel → on_write),
        # the identical mechanism that keeps the kinds-api holder cache
        # coherent (see app main.py). Guard so repeated (idempotent)
        # attach_kernel calls don't stack observers.
        if not self._view_invalidation_wired:
            try:
                kernel.on_write(  # type: ignore[attr-defined]
                    lambda scope, kind, name, op: self.invalidate_view(scope)
                )
                self._view_invalidation_wired = True
            except Exception:  # noqa: BLE001 — best-effort; never block attach
                pass
        if not self._writers:
            self._writers = list(kernel._writers)
        if not self._readers:
            self._readers = list(kernel._readers)

    async def init(self) -> None:
        """Run migrations. Call once after construction or let methods auto-init."""
        if not self._migrated:
            await self._run_migrations()
            self._migrated = True

    async def _ensure_migrated(self) -> None:
        if not self._migrated:
            await self.init()

    # ------------------------------------------------------------------
    # Connection safety
    # ------------------------------------------------------------------

    def _acquire_safe(self):
        """Pool acquire that DISCARDS connections cancelled mid-query.

        Plain ``pool.acquire()`` calls ``conn.reset()`` on release. If the
        caller was cancelled mid-fetch (e.g. SSE client disconnect from
        ``/agent/<scope>/<name>`` while a query was in flight), the
        underlying protocol is in state ``in_progress`` and the reset
        raises ``InterfaceError: cannot perform operation: another
        operation is in progress``. The exception is fatal to that
        connection AND poisons the pool — next caller acquiring the
        slot hits the same error indefinitely.

        This wrapper catches both ``CancelledError`` (caller cancelled)
        and ``asyncpg.InterfaceError`` (mid-protocol failure) and calls
        ``conn.terminate()`` (sync, immediate close) BEFORE release.
        ``Pool.release()`` then sees a closed connection and discards
        it instead of triggering ``reset_query`` on a corrupted
        protocol state. The exception still propagates to the caller.
        """
        import contextlib
        try:
            import asyncpg as _asyncpg
            _interface_err: type[BaseException] = _asyncpg.InterfaceError
        except Exception:
            _interface_err = type("_NoInterfaceError", (BaseException,), {})

        @contextlib.asynccontextmanager
        async def _cm():
            conn = await self._pool.acquire()
            try:
                yield conn
            except (asyncio.CancelledError, _interface_err):
                try:
                    conn.terminate()
                except Exception:
                    pass
                try:
                    await self._pool.release(conn)
                except Exception:
                    pass
                raise
            else:
                await self._pool.release(conn)
        return _cm()

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    async def _run_migrations(self) -> None:
        async with self._acquire_safe() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._schema}.dna_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)

            rows = await conn.fetch(
                f"SELECT version FROM {self._schema}.dna_schema_migrations"
            )
            applied = {row["version"] for row in rows}

        for version, statements in sorted(_MIGRATIONS.items()):
            if version in applied:
                continue
            logger.info("Applying Postgres migration v%d", version)
            async with self._acquire_safe() as conn:
                async with conn.transaction():
                    for stmt in statements:
                        await conn.execute(stmt.format(schema=self._schema))
                    await conn.execute(
                        f"INSERT INTO {self._schema}.dna_schema_migrations "
                        "(version, applied_at) VALUES ($1, $2)",
                        version, _now(),
                    )

    # ------------------------------------------------------------------
    # SourcePort (read)
    # ------------------------------------------------------------------

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return Genome + KindDefinition + LayerPolicy via fast WHERE filter.

        Phase 16. ``WHERE kind = ANY($2)`` over ``dna_documents`` is a
        constant-bounded query (bootstrap kind set is fixed at 3) so
        cold-start cost stays in the milliseconds even for scopes with
        thousands of Agent / Skill / Soul docs.

        Tenant semantics: when ``tenant`` is set, the tenant-published
        ``Genome`` (or legacy ``Module``) shadows the platform one
        (Phase 9 multi-tenant publishing). ``KindDefinition`` and
        ``LayerPolicy`` are non-overlayable per Phase 16 — always
        read from platform (tenant='').
        """
        from dna.kernel.protocols import BOOTSTRAP_KIND_NAMES
        await self._ensure_migrated()
        async with self._acquire_safe() as conn:
            rows = await conn.fetch(
                f"SELECT content, kind FROM {self._schema}.dna_documents "
                "WHERE scope=$1 AND kind = ANY($2::text[]) AND tenant=''",
                scope, list(BOOTSTRAP_KIND_NAMES),
            )
        out = [json.loads(r["content"]) for r in rows]

        if tenant:
            # Tenant-published Genome shadows platform.
            async with self._acquire_safe() as conn:
                tpkg_rows = await conn.fetch(
                    f"SELECT content FROM {self._schema}.dna_documents "
                    "WHERE scope=$1 AND kind='Genome' "
                    "AND tenant=$2 LIMIT 1",
                    scope, tenant,
                )
            if tpkg_rows:
                tenant_pkg = json.loads(tpkg_rows[0]["content"])
                out = [d for d in out if d.get("kind") != "Genome"]
                out.append(tenant_pkg)
        return out

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        """Load the BASE view of a scope (tenant=''). Tenant overlays are
        delivered via load_layer() on demand, exactly like FS adapter.

        R1-fix (2026-05-14): was N+1 (1 SELECT docs + N SELECT bundle_entries).
        Now 2 queries total — docs + all bundle_entries for the scope/tenant
        in a single round-trip — joined in Python. For a typical 75-doc scope
        that's 76 queries → 2 queries → 38× reduction in DB round-trips.
        """
        return await self._load_view(scope, tenant="", readers=readers)

    async def _load_view(
        self, scope: str, *, tenant: str, readers: list | None,
    ) -> list[dict[str, Any]]:
        """Cached front for :meth:`_load_view_uncached`.

        Memoizes the canonical (scope, tenant) view and returns DEEP
        COPIES so callers may mutate rows without corrupting the cache
        (the kinds-api list handler stamps ``inherited_from`` on rows).
        A single-flight lock collapses a concurrent first-hit burst — the
        thundering herd that made 10 parallel list loads serialize to
        ~12s — into one compute. Invalidated via on_write (attach_kernel).

        ``readers`` affects output but is NOT part of the key: readers are
        registered once at boot and stable thereafter, so keying on them
        would only ever miss. Callers passing readers that alter output
        must invalidate explicitly.
        """
        key = (scope, tenant)
        cached = self._view_cache.get(key)
        if cached is None:
            lock = self._view_locks.setdefault(key, asyncio.Lock())
            async with lock:
                cached = self._view_cache.get(key)  # re-check under lock
                if cached is None:
                    cached = await self._load_view_uncached(
                        scope, tenant=tenant, readers=readers,
                    )
                    self._view_cache[key] = cached
        # Deep copy (rows are JSON-origin dicts) so mutation by callers
        # never leaks back into the cache.
        return [json.loads(json.dumps(d)) for d in cached]

    def invalidate_view(self, scope: str | None = None) -> None:
        """Drop cached views. ``scope=None`` clears all; otherwise only
        entries for that scope (every tenant). Best-effort, never raises
        — wired as an on_write observer in :meth:`attach_kernel`."""
        try:
            if scope is None:
                self._view_cache.clear()
                return
            for k in [k for k in self._view_cache if k[0] == scope]:
                self._view_cache.pop(k, None)
        except Exception:  # noqa: BLE001
            pass

    async def _load_view_uncached(
        self, scope: str, *, tenant: str, readers: list | None,
    ) -> list[dict[str, Any]]:
        """Shared loader for load_all (base) and load_layer (tenant overlay).
        Issues exactly 2 SQL queries: one for docs, one for bundle entries.
        """
        await self._ensure_migrated()
        # Merge instance readers with caller-passed ones (deduplicate by identity)
        effective_readers = list(self._readers)
        for r in (readers or []):
            if r not in effective_readers:
                effective_readers.append(r)

        async with self._acquire_safe() as conn:
            doc_rows = await conn.fetch(
                f"SELECT kind, name, content FROM {self._schema}.dna_documents "
                "WHERE scope=$1 AND tenant=$2",
                scope, tenant,
            )
            entry_rows = await conn.fetch(
                f"SELECT kind, name, entry_path, content, content_binary "
                f"FROM {self._schema}.dna_bundle_entries "
                "WHERE scope=$1 AND tenant=$2",
                scope, tenant,
            )

        # Group bundle entries by (kind, name) once — O(E) — so each doc
        # lookup is O(1) instead of an extra SQL round-trip. Binary
        # entries (Phase 16-pre) come back as `bytes`; text entries as
        # `str`. DictBundleHandle accepts either.
        entries_by_key: dict[tuple[str, str], dict[str, str | bytes]] = {}
        for e in entry_rows:
            key = (e["kind"], e["name"])
            cb = e["content_binary"]
            val: str | bytes = (
                bytes(cb) if cb is not None and len(cb) > 0 else e["content"]
            )
            entries_by_key.setdefault(key, {})[e["entry_path"]] = val

        from dna.kernel.bundle_handle import DictBundleHandle
        from dna.kernel.generic_rw import FrontmatterParseWarning
        import warnings as _w

        out: list[dict[str, Any]] = []
        for r in doc_rows:
            entries = entries_by_key.get((r["kind"], r["name"]))
            if entries and effective_readers:
                handle = DictBundleHandle(r["name"], entries)
                matched = False
                for reader in effective_readers:
                    try:
                        if not reader.detect(handle):
                            continue
                        # D-B hardening (2026-05-19): when a bundle marker
                        # has corrupt YAML frontmatter, the reader emits a
                        # FrontmatterParseWarning and returns a doc with
                        # an anemic spec (body field only). For the PG
                        # adapter the canonical doc lives in
                        # ``dna_documents.content`` — promote that JSONB
                        # to the response instead of letting the broken
                        # marker silently wipe the row. Catch the
                        # warning via ``warnings.catch_warnings`` so we
                        # can detect-and-fall-back without changing the
                        # global reader contract.
                        with _w.catch_warnings(record=True) as caught:
                            _w.simplefilter("always", FrontmatterParseWarning)
                            doc_from_marker = reader.read(handle)
                        parse_failed = any(
                            issubclass(w.category, FrontmatterParseWarning)
                            for w in caught
                        )
                        if parse_failed:
                            # Surface ONCE per call (so the user still
                            # sees the parse error in logs / CLI output)
                            # but use the canonical JSONB row for the
                            # response.
                            for w in caught:
                                _w.warn_explicit(
                                    str(w.message), w.category, w.filename, w.lineno,
                                )
                            out.append(json.loads(r["content"]))
                        else:
                            out.append(doc_from_marker)
                        matched = True
                        break
                    except Exception:
                        continue
                if matched:
                    continue
            # Fallback: cached parsed dict (no readers, no bundle entries,
            # or detect/read raised hard).
            out.append(json.loads(r["content"]))
        return out

    async def list_doc_refs(
        self, scope: str, *, kind: str | None = None,
        tenant: str | None = None,
    ) -> list[tuple[str, str]]:
        """L1 granular access — list (kind, name) sem load.

        Single SELECT indexed em ``dna_documents``. Tenant=None retorna
        só base layer (tenant=''); tenant=<slug> retorna união base+overlay
        (overlay shadows base via DISTINCT ON ordering).
        """
        await self._ensure_migrated()
        async with self._acquire_safe() as conn:
            if tenant:
                # Union: tenant rows + base rows where (kind,name) not in tenant.
                # Done via DISTINCT ON ordered by tenant DESC so tenant wins.
                if kind:
                    rows = await conn.fetch(
                        f"SELECT DISTINCT ON (kind, name) kind, name "
                        f"FROM {self._schema}.dna_documents "
                        "WHERE scope=$1 AND tenant IN ('', $2) AND kind=$3 "
                        "ORDER BY kind, name, tenant DESC",
                        scope, tenant, kind,
                    )
                else:
                    rows = await conn.fetch(
                        f"SELECT DISTINCT ON (kind, name) kind, name "
                        f"FROM {self._schema}.dna_documents "
                        "WHERE scope=$1 AND tenant IN ('', $2) "
                        "ORDER BY kind, name, tenant DESC",
                        scope, tenant,
                    )
            else:
                if kind:
                    rows = await conn.fetch(
                        f"SELECT kind, name FROM {self._schema}.dna_documents "
                        "WHERE scope=$1 AND tenant='' AND kind=$2 "
                        "ORDER BY kind, name",
                        scope, kind,
                    )
                else:
                    rows = await conn.fetch(
                        f"SELECT kind, name FROM {self._schema}.dna_documents "
                        "WHERE scope=$1 AND tenant='' "
                        "ORDER BY kind, name",
                        scope,
                    )
        return [(r["kind"], r["name"]) for r in rows]

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers: list | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """L1 granular access — load 1 doc por (scope, kind, name).

        Custo: 1 SELECT pra master + 1 SELECT pra bundle_entries (se
        bundle Kind). 5-10ms total no PG indexed.

        Tenant: tenant=<slug> prefere overlay; cai pra base se overlay
        ausente. tenant=None = base only.
        """
        await self._ensure_migrated()
        effective_readers = list(self._readers)
        for r in (readers or []):
            if r not in effective_readers:
                effective_readers.append(r)

        # Try tenant overlay first when requested, fallback to base.
        tenant_keys = [tenant, ""] if tenant else [""]
        async with self._acquire_safe() as conn:
            for t in tenant_keys:
                row = await conn.fetchrow(
                    f"SELECT content FROM {self._schema}.dna_documents "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                    scope, kind, name, t,
                )
                if row is None:
                    continue

                # Reuse the outer conn — avoids nested pool.acquire that
                # was triggering "another operation in progress" on the
                # outer's reset() during concurrent insights ask gather.
                entries = await self._load_bundle_entries(
                    scope, kind, name, t, conn=conn,
                )
                from dna.kernel.bundle_handle import DictBundleHandle
                from dna.kernel.generic_rw import FrontmatterParseWarning
                import warnings as _w
                if entries and effective_readers:
                    handle = DictBundleHandle(name, entries)
                    for reader in effective_readers:
                        try:
                            if not reader.detect(handle):
                                continue
                            # D-B hardening (2026-05-19): same fallback
                            # logic as ``_load_view`` — when the bundle
                            # marker emits a FrontmatterParseWarning the
                            # spec is anemic; prefer the canonical
                            # ``dna_documents.content`` JSONB row.
                            with _w.catch_warnings(record=True) as caught:
                                _w.simplefilter("always", FrontmatterParseWarning)
                                doc_from_marker = reader.read(handle)
                            parse_failed = any(
                                issubclass(w.category, FrontmatterParseWarning)
                                for w in caught
                            )
                            if parse_failed:
                                for w in caught:
                                    _w.warn_explicit(
                                        str(w.message), w.category, w.filename, w.lineno,
                                    )
                                return json.loads(row["content"])
                            return doc_from_marker
                        except Exception:  # noqa: BLE001
                            continue
                # Fallback: cached parsed dict
                return json.loads(row["content"])
        return None

    async def _load_bundle_entries(
        self, scope: str, kind: str, name: str, tenant: str = "",
        *, conn: Any = None,
    ) -> dict[str, str | bytes]:
        """Fetch all entries for a bundle as {entry_path: content}.

        Phase 8a: tenant defaults to '' (base) so legacy callers see the
        same rows. Tenant-resolved reads from load_layer pass the
        tenant slug.

        Phase 16-pre (2026-05-20): the table now has a ``content_binary``
        BYTEA column for binary entries (image uploads, etc). When it's
        non-null we return the bytes; otherwise we fall back to the
        legacy TEXT ``content`` column. ``DictBundleHandle`` already
        accepts ``str | bytes`` per-entry.

        F8.7 bug fix: optional ``conn`` kwarg — when called from inside
        another ``async with self._pool.acquire()`` block (load_one
        does this), reuse the existing conn instead of nesting a fresh
        acquire. Nested acquire works in isolation but races on
        ``conn.reset()`` under concurrent insights ask gather → 'another
        operation in progress' tracebacks at exit-release time.
        """
        if conn is not None:
            rows = await conn.fetch(
                f"SELECT entry_path, content, content_binary "
                f"FROM {self._schema}.dna_bundle_entries "
                "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                scope, kind, name, tenant,
            )
        else:
            async with self._acquire_safe() as conn2:
                rows = await conn2.fetch(
                    f"SELECT entry_path, content, content_binary "
                    f"FROM {self._schema}.dna_bundle_entries "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                    scope, kind, name, tenant,
                )
        out: dict[str, str | bytes] = {}
        for r in rows:
            cb = r["content_binary"]
            if cb is not None and len(cb) > 0:
                out[r["entry_path"]] = bytes(cb)
            else:
                out[r["entry_path"]] = r["content"]
        return out

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
        """Phase 15 Fase E follow-up — implement Kernel.fetch_bundle_entry
        for the Postgres adapter (was NotImplementedError).

        Disambiguation: when the kernel supplies ``kind`` (e.g.
        ``"GraphifyArtifact"``), the WHERE clause includes
        ``kind=$N``, scoping the lookup to that exact Kind's bundle
        rows. Without ``kind`` we fall back to a name+entry-only
        match and accept the rare collision risk between two Kinds
        sharing a bundle ``name`` in the same scope (e.g. a Skill
        ``foo`` and a Persona ``foo``). The fall-through path
        exists for older callers that built ``Kernel`` before the
        protocol gained the kwarg.

        Tenant routing: prefer the tenant overlay if present, fall back
        to base layer (matches FilesystemWritableSource semantics).
        """
        await self._ensure_migrated()
        candidates: list[str] = []
        if tenant:
            candidates.append(tenant)
        candidates.append("")  # base layer fallback

        async with self._acquire_safe() as conn:
            for tenant_val in candidates:
                if kind is not None:
                    row = await conn.fetchrow(
                        f"SELECT content, content_binary FROM "
                        f"{self._schema}.dna_bundle_entries "
                        "WHERE scope=$1 AND kind=$2 AND name=$3 "
                        "AND entry_path=$4 AND tenant=$5 LIMIT 1",
                        scope, kind, name, entry, tenant_val,
                    )
                else:
                    row = await conn.fetchrow(
                        f"SELECT content, content_binary FROM "
                        f"{self._schema}.dna_bundle_entries "
                        "WHERE scope=$1 AND name=$2 AND entry_path=$3 "
                        "AND tenant=$4 LIMIT 1",
                        scope, name, entry, tenant_val,
                    )
                if row is not None:
                    # Prefer binary column when present (PNG/JPG/binary
                    # entries written via write_bundle_entry); fall
                    # back to the text column for legacy/text entries
                    # written via Writer.serialize. Returning empty
                    # bytes when both are empty preserves the
                    # "row-exists, no payload" semantic.
                    raw_bin = row["content_binary"]
                    if raw_bin is not None and len(raw_bin) > 0:
                        return bytes(raw_bin)
                    raw = row["content"]
                    if isinstance(raw, str):
                        return raw.encode("utf-8")
                    return bytes(raw or b"")
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
        """BundleEntryWritable impl — persist a text OR binary entry idempotently.

        Source of truth for bundle binaries (PNG/JPG/...) in the
        Postgres adapter. Used by ``Kernel.write_bundle_entry_async``,
        which is the canonical path for tools and HTTP handlers —
        replaces 4 callsites that previously did
        ``INSERT INTO dna_bundle_entries`` directly via
        ``getattr(kernel, "_source")._pool``.

        Tenant alignment: ``tenant`` is stored in the ``tenant``
        column to keep parity with the ``dna_documents`` row written
        by ``save_document``. ``delete_document`` joins both tables
        on ``(scope, kind, name, tenant)`` — mismatched tenants
        produce orphans the delete path can't reach. The previous
        direct-INSERT code hardcoded ``tenant=''`` and left orphans
        whenever a tenant-scoped tool called this path (bug observed
        2026-05-21 with generate_image).

        Atomicity: a single INSERT … ON CONFLICT DO UPDATE round-trip,
        so re-uploading the same entry replaces content without
        creating a duplicate row.
        """
        # ``container`` is passed by the Kernel wrapper (from the
        # Kind's StorageDescriptor) but the SQL key uses ``kind``
        # alongside ``(scope, name, entry_path, tenant)``. Default to
        # container when kind isn't supplied — they're the same for
        # most Kinds (ImagePrompt's container == "image-prompts" but
        # the kind name "ImagePrompt" is what dna_documents indexes
        # on, so prefer kind when present).
        kind_key = kind or container
        tenant_val = tenant or ""
        await self._ensure_migrated()
        # i-083 — type-aware routing: TEXT entries (instruction fragments,
        # asset.json, scripts) go to the `content` column; BINARY entries
        # (images, fonts) to `content_binary`. The path was binary-only
        # (hardcoded content=''), so `dna doc apply` — which force-encoded
        # every entry to bytes — buried text payloads in content_binary,
        # leaving `content` empty for readers that only check the text column.
        is_text = isinstance(content, str)
        text_col = content if is_text else ""
        bin_col = None if is_text else content
        async with self._acquire_safe() as conn:
            await conn.execute(
                f"INSERT INTO {self._schema}.dna_bundle_entries "
                "(scope, kind, name, entry_path, content, content_binary, "
                "updated_at, tenant) "
                "VALUES ($1, $2, $3, $4, $5, $6, now()::text, $7) "
                "ON CONFLICT (scope, kind, name, entry_path, tenant) "
                "DO UPDATE SET content=EXCLUDED.content, "
                "content_binary=EXCLUDED.content_binary, "
                "updated_at=EXCLUDED.updated_at",
                scope, kind_key, name, entry, text_col, bin_col, tenant_val,
            )

    async def resolve_ref(self, scope: str, ref: str) -> str:
        return ""

    def _live_readers(self) -> list:
        """Kernel's live readers list (s-composition-and-nav-lazy):
        ``self._readers`` is a snapshot captured at attach_kernel time,
        BEFORE extensions register their generic bundle readers via
        ``_ensure_generic_readers_writers`` lazy init — prefer the
        kernel's current list when attached."""
        if getattr(self, "_kernel", None) is not None:
            return list(getattr(self._kernel, "_readers", []))
        return list(getattr(self, "_readers", None) or [])

    def _reader_can_produce(self, kind: str, live_readers: list | None = None) -> bool:
        """Bundle-override gate shared by ``query()`` and ``count()``
        (parity-critical — F2 T7 review): True when a registered reader can
        produce ``kind``, i.e. bundle docs may masquerade as this kind and
        pure SQL push-down would diverge from ``load_all`` semantics."""
        readers = self._live_readers() if live_readers is None else live_readers
        return any(getattr(r, "_kind", None) == kind for r in readers)

    async def query(
        self, scope: str, kind: str, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant=None,
    ):
        """Marco A — native push-down via jsonb operators.

        Substitui o Protocol fallback por SQL nativo. WHERE/ORDER BY/LIMIT
        rodam no banco — só os rows que casam viajam de volta. Projection
        é aplicada em Python pós-fetch (helpers compartilhados com o
        Protocol fallback) porque jsonb_build_object adicionaria parsing
        complexo sem ganho mensurável: rows típicas têm <20KB de content.

        Tenant overlay (Phase 9 multi-tenant): quando ``tenant`` é dado,
        consultamos base (tenant='') + overlay (tenant=<slug>) e mergeamos
        em Python com overlay shadowing base por (kind, name). Mantém a
        semântica do Protocol fallback + tests parity.

        Bundle override (s-composition-and-nav-lazy, 2026-05-14): para
        kinds presentes em ``dna_bundle_entries`` que cruzam containers
        (ex.: um bundle cujo dna_documents.kind diverge do kind que o
        reader detecta a partir do marker file),
        o filtro SQL puro `WHERE kind=$X` perde docs cujo dna_documents
        .kind diverge do reader-output kind. Rota slow-path delega a
        ``_load_view`` (load_all com bundle resolution) quando há
        reader registered que pode produzir esse kind — garante parity
        com ``load_all`` (e por extensão com ``mi.documents``).
        """
        from dna.kernel.protocols import (
            QueryError, _project_doc, _apply_order_by, _match_filter,
        )
        await self._ensure_migrated()

        if filter is not None and not isinstance(filter, dict):
            raise QueryError(f"filter must be dict, got {type(filter).__name__}")

        # Slow-path: when a reader can produce this kind (i.e., bundle
        # override is possible), fall back to load_all+filter to match
        # the load_all semantics. Otherwise the fast SQL push-down is
        # safe (no bundle docs masquerade as this kind).
        _live_readers = self._live_readers()
        readers = _live_readers
        if self._reader_can_produce(kind, _live_readers):
            # Story s-mi-class-death fix: when tenant is set, query MUST
            # union base + overlay (not just overlay). Mirrors the fast
            # path semantics (and the legacy mi.resolve_async behavior).
            # Without this, agents that live only in base "disappear"
            # for any tenant request — talent-screener for dev-tenant
            # was the canary.
            base_docs = await self._load_view(scope, tenant="", readers=readers)
            if tenant:
                overlay_docs = await self._load_view(scope, tenant=tenant, readers=readers)
                shadow = {
                    (d.get("kind"), (d.get("metadata") or {}).get("name"))
                    for d in overlay_docs
                }
                base_filtered = [
                    d for d in base_docs
                    if (d.get("kind"), (d.get("metadata") or {}).get("name")) not in shadow
                ]
                raw_docs = base_filtered + overlay_docs
            else:
                raw_docs = base_docs
            kind_docs = [d for d in raw_docs if d.get("kind") == kind]
            if filter:
                kind_docs = [d for d in kind_docs if _match_filter(d, filter)]
            if order_by:
                kind_docs = _apply_order_by(kind_docs, order_by)
            start = offset or 0
            end = (start + limit) if limit is not None else None
            page = kind_docs[start:end]
            for doc in page:
                yield _project_doc(doc, projection) if projection else doc
            return

        # Tenant: when None, base only; when set, query union of base
        # + overlay (overlay shadows base) — split into 2 fetches and
        # merge here for simplicity (matches fallback semantics).
        async def _fetch_one_tenant(t: str) -> list[dict[str, Any]]:
            local_params: list[Any] = [scope, kind, t]
            local_idx = 4  # $4 reserved for the next placeholder
            where_sql, where_params = _build_pg_where(filter, start_idx=local_idx)
            local_params.extend(where_params)
            local_idx += len(where_params)
            order_sql = _build_pg_order(order_by) if order_by else ""
            limit_sql = ""
            if limit is not None:
                limit_sql += f" LIMIT ${local_idx}"
                local_params.append(int(limit))
                local_idx += 1
            if offset is not None and offset > 0:
                limit_sql += f" OFFSET ${local_idx}"
                local_params.append(int(offset))
                local_idx += 1
            sql = (
                f"SELECT name, kind, content FROM {self._schema}.dna_documents "
                f"WHERE scope=$1 AND kind=$2 AND tenant=$3"
                f"{where_sql}"
                f"{order_sql}"
                f"{limit_sql}"
            )
            async with self._acquire_safe() as conn:
                rows = await conn.fetch(sql, *local_params)
            return [json.loads(r["content"]) for r in rows]

        if tenant is None:
            docs = await _fetch_one_tenant("")
        else:
            # Union base + overlay; overlay shadows base by name.
            # We pull MORE than `limit` from each (overlay rarely shadows
            # > some of base) and then re-apply limit after merge.
            # For typical scopes the overhead is negligible.
            overlay_docs = await _fetch_one_tenant(tenant)
            base_docs = await _fetch_one_tenant("")
            shadow_keys = {
                (d.get("kind"), (d.get("metadata") or {}).get("name"))
                for d in overlay_docs
            }
            docs = [
                d for d in base_docs
                if (d.get("kind"), (d.get("metadata") or {}).get("name")) not in shadow_keys
            ]
            docs.extend(overlay_docs)

        # s-composition-and-nav-lazy (2026-05-14): fast-path returned all
        # docs where dna_documents.kind matches the target. But docs whose
        # bundle entries' readers would OVERRIDE the kind (a bundle stored
        # under one kind whose marker file is detected as a DIFFERENT kind
        # by another reader) must be EXCLUDED from the
        # raw kind's result — load_all hands them out under the
        # reader-output kind only. To match parity, walk bundle_entries
        # and skip docs whose (kind, name) has reader-coverage for a
        # DIFFERENT kind.
        names_to_drop: set[str] = set()
        if docs and _live_readers:
            doc_keys = [
                (kind, (d.get("metadata") or {}).get("name") or "")
                for d in docs
            ]
            if doc_keys:
                # Single SELECT: which (kind, name) in our set have bundle entries?
                async with self._acquire_safe() as conn:
                    erows = await conn.fetch(
                        f"SELECT name, entry_path, content FROM "
                        f"{self._schema}.dna_bundle_entries "
                        f"WHERE scope=$1 AND tenant=$2 AND kind=$3 "
                        f"AND name = ANY($4::text[])",
                        scope, (tenant or ""), kind,
                        [n for _k, n in doc_keys],
                    )
                from dna.kernel.bundle_handle import DictBundleHandle
                entries_by_name: dict[str, dict[str, str]] = {}
                for e in erows:
                    entries_by_name.setdefault(e["name"], {})[e["entry_path"]] = e["content"]
                for name, entries in entries_by_name.items():
                    handle = DictBundleHandle(name, entries)
                    for reader in _live_readers:
                        try:
                            if reader.detect(handle):
                                produced = getattr(reader, "_kind", None)
                                if produced and produced != kind:
                                    names_to_drop.add(name)
                                break
                        except Exception:
                            continue
        if names_to_drop:
            docs = [
                d for d in docs
                if (d.get("metadata") or {}).get("name") not in names_to_drop
            ]
            # Re-apply order_by + limit after merge (SQL ordering on
            # the union doesn't survive the merge).
            if order_by:
                docs = _apply_order_by(docs, order_by)
            if offset:
                docs = docs[int(offset):]
            if limit is not None:
                docs = docs[: int(limit)]

        # Projection in Python — keeps SQL simple.
        for doc in docs:
            if projection:
                yield _project_doc(doc, projection)
            else:
                yield doc

    async def count(
        self, scope: str, kind: str, *,
        filter=None, group_by=None, tenant: str | None = None,
    ) -> dict[str, Any]:
        """Native COUNT push-down (F2 D2, s-f2-recordstore-port) — only
        aggregates travel back, never rows.

        Two variants:
          - Sem tenant: ``SELECT count(*) … WHERE scope/kind/tenant=''``
            (group: ``SELECT {expr} AS key, count(*) … GROUP BY 1``).
          - Com tenant: dedup por name com overlay shadowing base via
            ``DISTINCT ON (name) … ORDER BY name, tenant DESC`` (overlay
            vence: qualquer slug > '' lexicograficamente) numa subquery,
            espelhando a semântica do ``query()`` nativo. O ``filter``
            aplica DENTRO da subquery, por linha física — igual ao
            ``query()``, que filtra cada tenant-fetch em SQL antes do
            merge (um doc base que casa o filter NÃO é sombreado por um
            overlay que não casa).

        Bundle-override guard (espelha o slow-path do ``query`` acima):
        quando um reader registrado pode produzir este kind, bundle docs
        podem cruzar containers e o SQL puro divergiria — caímos no
        fallback in-memory (``query_fallback.count_via_query``), que ride
        o ``query`` deste adapter e herda a resolução de bundle do slow-path.
        Divergência residual DECLARADA: o fast-path do ``query()`` ainda
        aplica o post-filter ``names_to_drop`` (bundle entries cujo
        reader produz OUTRO kind) que este COUNT não replica — aceitável
        porque record kinds não cruzam containers de bundle (nenhum
        reader os produz; nesse caso o guard nem dispara), declarado em
        vez de silencioso.

        Group ordering: count DESC, key ASC NULLS LAST — paridade com o
        protocol-default (``-count, key-is-None, str(key)``). Edge
        conhecido (pin no fixture de paridade T11): keys NUMÉRICAS — o
        fallback retorna o valor JSON cru (int/float) e desempata por
        ``str(key)`` lexicográfico, enquanto aqui ``->>`` extrai TEXT
        (key vira str, ordenação text). Shape e desempate podem divergir
        pra group_by sobre campos numéricos; sem mudança de comportamento
        nesta fase.
        """
        from dna.kernel.protocols import QueryError
        from dna.kernel.query_fallback import count_via_query
        await self._ensure_migrated()

        if filter is not None and not isinstance(filter, dict):
            raise QueryError(f"filter must be dict, got {type(filter).__name__}")

        # Bundle-override guard — same gate as query()'s slow-path
        # (extracted helper, parity-critical).
        if self._reader_can_produce(kind):
            return await count_via_query(
                self, scope, kind, filter=filter, group_by=group_by, tenant=tenant,
            )

        where_sql, where_params = _build_pg_where(filter, start_idx=4)
        group_expr = _pg_field_expr(group_by) if group_by else None

        if tenant is None:
            params: list[Any] = [scope, kind, "", *where_params]
            base = (
                f"FROM {self._schema}.dna_documents "
                f"WHERE scope=$1 AND kind=$2 AND tenant=$3{where_sql}"
            )
            if group_expr is None:
                sql = f"SELECT count(*) AS cnt {base}"
                async with self._acquire_safe() as conn:
                    row = await conn.fetchrow(sql, *params)
                return {"total": int(row["cnt"]), "groups": None}
            sql = (
                f"SELECT {group_expr} AS key, count(*) AS cnt {base} "
                f"GROUP BY 1 ORDER BY 2 DESC, 1 ASC NULLS LAST"
            )
            async with self._acquire_safe() as conn:
                rows = await conn.fetch(sql, *params)
        else:
            params = [scope, kind, tenant, *where_params]
            inner_cols = "name" + (f", {group_expr} AS key" if group_expr else "")
            inner = (
                f"SELECT DISTINCT ON (name) {inner_cols} "
                f"FROM {self._schema}.dna_documents "
                f"WHERE scope=$1 AND kind=$2 AND tenant IN ('', $3){where_sql} "
                f"ORDER BY name, tenant DESC"
            )
            if group_expr is None:
                sql = f"SELECT count(*) AS cnt FROM ({inner}) t"
                async with self._acquire_safe() as conn:
                    row = await conn.fetchrow(sql, *params)
                return {"total": int(row["cnt"]), "groups": None}
            sql = (
                f"SELECT key, count(*) AS cnt FROM ({inner}) t "
                f"GROUP BY key ORDER BY 2 DESC, 1 ASC NULLS LAST"
            )
            async with self._acquire_safe() as conn:
                rows = await conn.fetch(sql, *params)

        groups = [{"key": r["key"], "count": int(r["cnt"])} for r in rows]
        return {"total": sum(g["count"] for g in groups), "groups": groups}

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]:
        """Load layer overlay docs for (scope, layer_id, layer_value).

        Phase 8a: when ``layer_id == 'tenant'``, query the new ``tenant``
        column on dna_documents directly — that's where Phase 8a writes
        land. The legacy dna_layer_documents table still services other
        layer_id values for back-compat.
        """
        await self._ensure_migrated()

        if layer_id == "tenant":
            # R1-fix (2026-05-14): reuses _load_view (2 queries total)
            # instead of N+1.
            return await self._load_view(
                scope, tenant=layer_value, readers=readers,
            )

        # Non-tenant layer: legacy table.
        async with self._acquire_safe() as conn:
            rows = await conn.fetch(
                f"SELECT content FROM {self._schema}.dna_layer_documents "
                "WHERE scope=$1 AND layer_id=$2 AND layer_value=$3",
                scope, layer_id, layer_value,
            )
        return [json.loads(r["content"]) for r in rows]

    async def list_tenants(self, scope: str | None = None) -> list[str]:
        """Phase 8a parity with FilesystemWritableSource — distinct
        non-empty tenants observed in dna_documents (optionally narrowed
        to one scope)."""
        await self._ensure_migrated()
        async with self._acquire_safe() as conn:
            if scope is None:
                rows = await conn.fetch(
                    f"SELECT DISTINCT tenant FROM {self._schema}.dna_documents "
                    "WHERE tenant <> '' ORDER BY tenant"
                )
            else:
                rows = await conn.fetch(
                    f"SELECT DISTINCT tenant FROM {self._schema}.dna_documents "
                    "WHERE scope=$1 AND tenant <> '' ORDER BY tenant",
                    scope,
                )
        return [r["tenant"] for r in rows]

    # ------------------------------------------------------------------
    # WritableSourcePort (write)
    # ------------------------------------------------------------------

    async def _emit_outbox(
        self,
        conn,
        *,
        scope: str,
        tenant: str,
        kind: str,
        name: str,
        op: str,
        doc_version: int,
        actor: str | None = None,
        cause: str | None = None,
        write_class: str = "substantive",
    ) -> int:
        """Phase 15.1 — append KernelEventBus event atomically with the
        caller's data write. Three operations in the same transaction:
          1. INSERT into dna_outbox (durable, FIFO event log).
          2. UPSERT dna_versions_seq (per-(scope, tenant) checkpoint).
          3. pg_notify on KERNEL_EVENTBUS_CHANNEL.

        ``write_class`` (substantive|cue) rides on the NOTIFY payload so the
        ObserverBus can filter cue-bumps by class (s-buswrite-class-substantive-cue).
        """
        actor_val = actor if actor is not None else self._default_actor
        cause_val = cause if cause is not None else self._default_cause

        outbox_id: int = await conn.fetchval(
            f"INSERT INTO {self._schema}.dna_outbox "
            "(scope, tenant, kind, name, op, doc_version, actor, cause) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id",
            scope, tenant, kind, name, op, doc_version, actor_val, cause_val,
        )
        await conn.execute(
            f"INSERT INTO {self._schema}.dna_versions_seq "
            "(scope, tenant, last_id, last_at) "
            "VALUES ($1, $2, $3, now()) "
            "ON CONFLICT (scope, tenant) DO UPDATE SET "
            "last_id = EXCLUDED.last_id, last_at = EXCLUDED.last_at",
            scope, tenant, outbox_id,
        )
        payload = _build_notify_payload(
            outbox_id, scope, tenant, kind, name, op, doc_version, actor_val,
            write_class,
        )
        await conn.execute(
            f"SELECT pg_notify('{KERNEL_EVENTBUS_CHANNEL}', $1)",
            payload,
        )
        return outbox_id

    async def save_document(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None = None,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        write_class: str = "substantive",
        version_retention: int | None = None,
    ) -> str:
        """Persist a document. Phase 8a: ``tenant`` is first-class.

        ``version_retention`` (s-version-prune-record-plane-churn): when set,
        keep only the last N version snapshots for this doc (record-plane Kinds
        pass 3). ``None`` = keep full history (manifest-plane default).

        ``layer`` is back-compat translated by the kernel into ``tenant``
        when ``layer == ("tenant", X)``. Other layer keys are not
        supported by this adapter (raises NotImplementedError — those
        belong on FilesystemWritableSource until we add a real layer
        identity tuple to the schema).
        """
        if layer is not None:
            if isinstance(layer, tuple) and len(layer) == 2 and layer[0] == "tenant":
                # Belt-and-suspenders: kernel should already have folded
                # this into tenant=X, but accept it directly too.
                tenant = layer[1]
            else:
                raise NotImplementedError(
                    f"PostgresWritableSource: layer writes for layer_id={layer[0]!r} "
                    "are not supported (only layer_id='tenant' has a column). "
                    "Use FilesystemWritableSource for non-tenant layers."
                )
        await self._ensure_migrated()
        # Empty string = legacy/global. Matches the column DEFAULT and
        # keeps the PRIMARY KEY non-null.
        tenant_val = tenant or ""

        # s-sync-s3 — KIND-AGNOSTIC source_files net. Pop spec.source_files
        # BEFORE the writer runs (keeps stored content bloat-free + avoids
        # double-handling) and merge its entries after. This persists carried
        # bundle entries (the instruction_file fragment, fonts, images,
        # scripts/) for EVERY bundle kind whose writer doesn't itself consume
        # source_files — not just Agent. It's the structural fix behind
        # i-061/i-062 (the CLI band-aids only covered agents); writers that DO
        # pop source_files themselves leave nothing here, so this never double-
        # writes.
        _net_text: dict[str, str] = {}
        _net_binary: dict[str, bytes] = {}
        _net_spec = raw.get("spec")
        if isinstance(_net_spec, dict) and _net_spec.get("source_files"):
            from dna.kernel.writer_helpers import pop_source_files_as_entries
            for _e in pop_source_files_as_entries(_net_spec, kind):
                if "content_bytes" in _e:
                    _net_binary[_e["relativePath"]] = _e["content_bytes"]
                else:
                    _net_text[_e["relativePath"]] = _e["content"]

        # Try registered writers — bundle path.
        # bundle_entries holds TEXT entries (str); bundle_binary_entries
        # holds BINARY entries (bytes). Writers can emit both via
        # handle.write_text() / handle.write_bytes(). The split lets the
        # adapter write to the appropriate column (content vs content_binary).
        bundle_entries: dict[str, str] | None = None
        bundle_binary_entries: dict[str, bytes] | None = None
        from dna.kernel.bundle_handle import DictBundleHandle
        for w in self._writers:
            if w.can_write(raw):
                handle = DictBundleHandle(name, {})
                w.write(handle, raw)
                bundle_entries = {}
                bundle_binary_entries = {}
                for e in handle.iter_entries(recursive=True):
                    raw_val = handle._entries.get(e)  # peek raw type
                    if isinstance(raw_val, bytes):
                        bundle_binary_entries[e] = raw_val
                    else:
                        bundle_entries[e] = handle.read_text(e)
                break

        # Merge the carried source_files net (authored bytes win on conflict).
        if _net_text or _net_binary:
            if bundle_entries is None:
                bundle_entries, bundle_binary_entries = {}, {}
            bundle_entries.update(_net_text)
            bundle_binary_entries.update(_net_binary)

        content = json.dumps(raw)  # source_files already popped → no bloat
        # Phase 10g — extract semver from spec.version for the Genome
        # catalog. Non-Genome kinds + Genomes without spec.version stay
        # NULL → uniqueness constraint is partial (WHERE semver IS NOT NULL)
        # so they're untouched.
        spec_version = None
        if kind == "Genome":
            spec_version = ((raw.get("spec") or {}).get("version")) or None
        async with self._acquire_safe() as conn:
            async with conn.transaction():
                # Pre-check immutability for Genome + semver. Postgres would
                # raise unique_violation on insert too, but the explicit
                # check lets us emit our typed exception.
                if spec_version:
                    existing = await conn.fetchrow(
                        f"SELECT 1 FROM {self._schema}.dna_versions "
                        "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4 AND semver=$5 "
                        "LIMIT 1",
                        scope, kind, name, tenant_val, spec_version,
                    )
                    if existing is not None:
                        from dna.kernel.protocols import (
                            VersionAlreadyPublished,
                        )
                        raise VersionAlreadyPublished(
                            f"Module {name!r} version {spec_version!r} already "
                            f"published to scope {scope!r} (tenant={tenant_val!r}). "
                            "Bump and republish."
                        )

                next_version = await conn.fetchval(
                    f"SELECT COALESCE(MAX(version), 0) FROM {self._schema}.dna_versions "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                    scope, kind, name, tenant_val,
                )
                next_version += 1

                await conn.execute(
                    f"INSERT INTO {self._schema}.dna_versions "
                    "(scope, kind, name, content, version, is_draft, author, "
                    "created_at, tenant, semver) "
                    "VALUES ($1, $2, $3, $4, $5, true, $6, $7, $8, $9)",
                    scope, kind, name, content, next_version, author, _now(),
                    tenant_val, spec_version,
                )

                # s-version-prune-record-plane-churn — keep only the last N
                # snapshots for record-plane Kinds (prune older by version), so
                # machine churn doesn't grow the history unbounded. dna_documents
                # (current state) is untouched; only stale HISTORY is trimmed.
                if version_retention is not None and version_retention >= 0:
                    await conn.execute(
                        f"DELETE FROM {self._schema}.dna_versions "
                        "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4 "
                        "AND version <= $5",
                        scope, kind, name, tenant_val,
                        next_version - version_retention,
                    )

                if bundle_entries is not None:
                    # Phase 16-pre (2026-05-20): preserve binary entries
                    # across writes. Writer.serialize emits ONLY text
                    # bundle entries (PROMPT.md, SOUL.md, etc) — it
                    # has no way to round-trip the binary blobs
                    # (output.png, etc) that live alongside in the
                    # bundle. The pre-fix "DELETE all + INSERT text"
                    # semantics wiped the binary on every spec edit.
                    #
                    # New semantics: DELETE only TEXT entries
                    # (content_binary IS NULL) and ones we're about to
                    # re-insert. Binaries — entries with non-null
                    # content_binary — are untouched. Writers that
                    # WANT to delete a binary must do it via a
                    # separate dedicated endpoint (e.g. the
                    # ImagePrompt upload endpoint replaces the
                    # binary on re-upload).
                    new_paths = list(bundle_entries.keys())
                    if new_paths:
                        await conn.execute(
                            f"DELETE FROM {self._schema}.dna_bundle_entries "
                            "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4 "
                            "AND (content_binary IS NULL OR entry_path = ANY($5))",
                            scope, kind, name, tenant_val, new_paths,
                        )
                    else:
                        # No text entries to write — still drop the
                        # text ones (writer chose to emit nothing).
                        await conn.execute(
                            f"DELETE FROM {self._schema}.dna_bundle_entries "
                            "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4 "
                            "AND content_binary IS NULL",
                            scope, kind, name, tenant_val,
                        )
                    ts = _now()
                    for entry_path, body in bundle_entries.items():
                        await conn.execute(
                            f"INSERT INTO {self._schema}.dna_bundle_entries "
                            "(scope, kind, name, entry_path, content, updated_at, tenant) "
                            "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                            "ON CONFLICT (scope, kind, name, entry_path, tenant) "
                            "DO UPDATE SET content=EXCLUDED.content, "
                            "updated_at=EXCLUDED.updated_at",
                            scope, kind, name, entry_path, body, ts, tenant_val,
                        )

                # Binary entries (L3.1, 2026-05-25). Writers can emit
                # bytes via handle.write_bytes() — eg HtmlArtifactWriter
                # pops spec.source_files and writes output.html as bytes,
                # ImagePromptWriter writes output.png, etc. Stored in
                # the content_binary column. Same upsert semantics as
                # text entries above.
                if bundle_binary_entries:
                    ts_bin = _now()
                    for entry_path, body_bytes in bundle_binary_entries.items():
                        await conn.execute(
                            f"INSERT INTO {self._schema}.dna_bundle_entries "
                            "(scope, kind, name, entry_path, content, "
                            "content_binary, updated_at, tenant) "
                            "VALUES ($1, $2, $3, $4, '', $5, $6, $7) "
                            "ON CONFLICT (scope, kind, name, entry_path, tenant) "
                            "DO UPDATE SET content_binary=EXCLUDED.content_binary, "
                            "updated_at=EXCLUDED.updated_at",
                            scope, kind, name, entry_path, body_bytes,
                            ts_bin, tenant_val,
                        )

                # Auto-publish: also UPSERT into dna_documents. The
                # historical Postgres adapter required an explicit
                # publish() call, but every other writer in the codebase
                # treats save_document as the publish point. Match that
                # contract so the new tenant column actually lands in
                # dna_documents (which is what load_all reads from).
                await conn.execute(
                    f"INSERT INTO {self._schema}.dna_documents "
                    "(scope, kind, name, content, version, updated_at, tenant) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                    "ON CONFLICT (scope, kind, name, tenant) DO UPDATE SET "
                    "content=EXCLUDED.content, version=EXCLUDED.version, "
                    "updated_at=EXCLUDED.updated_at",
                    scope, kind, name, content, next_version, _now(), tenant_val,
                )

                # Phase 15.1 — emit KernelEventBus event atomically.
                await self._emit_outbox(
                    conn,
                    scope=scope, tenant=tenant_val,
                    kind=kind, name=name,
                    op="write", doc_version=next_version,
                    actor=author,
                    write_class=write_class,
                )

        return str(next_version)

    async def publish(
        self, scope: str, kind: str, name: str,
        *, tenant: str | None = None,
    ) -> str:
        """Promote the latest draft version to published.

        Phase 8a: ``tenant`` selects which tenant's draft to publish.
        save_document already auto-publishes, so this is mostly here for
        clients that explicitly use the draft → publish workflow.
        """
        await self._ensure_migrated()
        tenant_val = tenant or ""
        async with self._acquire_safe() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"SELECT id, content, version FROM {self._schema}.dna_versions "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4 AND is_draft=true "
                    "ORDER BY version DESC LIMIT 1",
                    scope, kind, name, tenant_val,
                )
                if row is None:
                    raise ValueError("no_draft")

                vid = row["id"]
                content = row["content"]
                version = row["version"]

                # UPSERT into documents (PK now includes tenant)
                await conn.execute(
                    f"INSERT INTO {self._schema}.dna_documents "
                    "(scope, kind, name, content, version, updated_at, tenant) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                    "ON CONFLICT (scope, kind, name, tenant) DO UPDATE SET "
                    "content=EXCLUDED.content, version=EXCLUDED.version, updated_at=EXCLUDED.updated_at",
                    scope, kind, name, content, version, _now(), tenant_val,
                )
                await conn.execute(
                    f"UPDATE {self._schema}.dna_versions SET is_draft=false WHERE id=$1",
                    vid,
                )

                # Phase 15.1 — emit KernelEventBus event atomically.
                await self._emit_outbox(
                    conn,
                    scope=scope, tenant=tenant_val,
                    kind=kind, name=name,
                    op="write", doc_version=version,
                )
        return str(version)

    async def delete_document(
        self, scope: str, kind: str, name: str,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
    ) -> None:
        if layer is not None:
            if isinstance(layer, tuple) and len(layer) == 2 and layer[0] == "tenant":
                tenant = layer[1]
            else:
                raise NotImplementedError(
                    f"PostgresWritableSource: delete for layer_id={layer[0]!r} "
                    "is not supported."
                )
        await self._ensure_migrated()
        tenant_val = tenant or ""
        async with self._acquire_safe() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"SELECT 1 FROM {self._schema}.dna_documents "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                    scope, kind, name, tenant_val,
                )
                if row is None:
                    raise ValueError("not_found")
                await conn.execute(
                    f"DELETE FROM {self._schema}.dna_documents "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                    scope, kind, name, tenant_val,
                )
                await conn.execute(
                    f"DELETE FROM {self._schema}.dna_versions "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                    scope, kind, name, tenant_val,
                )
                await conn.execute(
                    f"DELETE FROM {self._schema}.dna_bundle_entries "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                    scope, kind, name, tenant_val,
                )

                # Phase 15.1 — emit KernelEventBus event atomically.
                # doc_version=0 is the documented sentinel for delete.
                await self._emit_outbox(
                    conn,
                    scope=scope, tenant=tenant_val,
                    kind=kind, name=name,
                    op="delete", doc_version=0,
                )

    async def save_manifest(self, scope: str, manifest: dict) -> str:
        name = manifest.get("metadata", {}).get("name", scope)
        kind = manifest.get("kind") or "Genome"
        return await self.save_document(scope, kind, name, manifest)

    async def list_versions(self, scope: str, kind: str, name: str) -> list[dict]:
        await self._ensure_migrated()
        async with self._acquire_safe() as conn:
            rows = await conn.fetch(
                f"SELECT id, version, is_draft, author, created_at "
                f"FROM {self._schema}.dna_versions "
                "WHERE scope=$1 AND kind=$2 AND name=$3 ORDER BY version DESC",
                scope, kind, name,
            )
        return [dict(row) for row in rows]

    async def get_version(self, scope: str, kind: str, name: str, version_id: str) -> dict:
        await self._ensure_migrated()
        async with self._acquire_safe() as conn:
            row = await conn.fetchrow(
                f"SELECT id, scope, kind, name, content, version, is_draft, author, created_at "
                f"FROM {self._schema}.dna_versions "
                "WHERE scope=$1 AND kind=$2 AND name=$3 AND version=$4",
                scope, kind, name, int(version_id),
            )
        if row is None:
            raise ValueError("version_not_found")
        result = dict(row)
        result["content"] = json.loads(result["content"])
        return result

    async def load_drafts(self, scope: str) -> list[dict]:
        await self._ensure_migrated()
        async with self._acquire_safe() as conn:
            rows = await conn.fetch(
                f"SELECT v.kind, v.name, v.content, v.version, v.created_at "
                f"FROM {self._schema}.dna_versions v "
                "INNER JOIN ("
                f"  SELECT kind, name, MAX(version) AS max_v "
                f"  FROM {self._schema}.dna_versions "
                "  WHERE scope=$1 AND is_draft=true GROUP BY kind, name"
                ") latest ON v.kind=latest.kind AND v.name=latest.name AND v.version=latest.max_v "
                "WHERE v.scope=$2 AND v.is_draft=true",
                scope, scope,
            )
        return [
            {
                "kind": r["kind"],
                "name": r["name"],
                "content": r["content"],
                "version": r["version"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # -- Layer operations --

    async def save_layer_document(
        self, scope: str, layer_id: str, layer_value: str,
        kind: str, name: str, raw: dict,
    ) -> None:
        await self._ensure_migrated()

        # Phase 15 Fase E (E4) — fix asymmetric save/load. Phase 8a moved
        # tenant overlay reads to dna_documents.tenant; this route writes
        # to the same table so save+load round-trip correctly. Other
        # layer_ids (branch, env, etc.) keep using dna_layer_documents
        # until they get a typed column too.
        if layer_id == "tenant":
            return await self.save_document(
                scope, kind, name, raw, tenant=layer_value,
            )

        async with self._acquire_safe() as conn:
            await conn.execute(
                f"INSERT INTO {self._schema}.dna_layer_documents "
                "(scope, layer_id, layer_value, kind, name, content, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "ON CONFLICT (scope, layer_id, layer_value, kind, name) DO UPDATE SET "
                "content=EXCLUDED.content, updated_at=EXCLUDED.updated_at",
                scope, layer_id, layer_value, kind, name, json.dumps(raw), _now(),
            )

    async def delete_layer_document(
        self, scope: str, layer_id: str, layer_value: str,
        kind: str, name: str,
    ) -> None:
        await self._ensure_migrated()
        async with self._acquire_safe() as conn:
            await conn.execute(
                f"DELETE FROM {self._schema}.dna_layer_documents "
                "WHERE scope=$1 AND layer_id=$2 AND layer_value=$3 AND kind=$4 AND name=$5",
                scope, layer_id, layer_value, kind, name,
            )

    async def list_layers(self, scope: str) -> list[dict[str, str]]:
        await self._ensure_migrated()
        # Phase 15 Fase E (E4) — Phase 8a stores tenant overlays in
        # dna_documents.tenant; merge those with the legacy
        # dna_layer_documents entries so list_layers surfaces both.
        async with self._acquire_safe() as conn:
            legacy = await conn.fetch(
                f"SELECT DISTINCT layer_id, layer_value FROM {self._schema}.dna_layer_documents "
                "WHERE scope=$1",
                scope,
            )
            tenants = await conn.fetch(
                f"SELECT DISTINCT tenant FROM {self._schema}.dna_documents "
                "WHERE scope=$1 AND tenant != ''",
                scope,
            )
        out = [{"layer_id": r["layer_id"], "layer_value": r["layer_value"]} for r in legacy]
        out.extend({"layer_id": "tenant", "layer_value": r["tenant"]} for r in tenants)
        out.sort(key=lambda x: (x["layer_id"], x["layer_value"]))
        return out

    async def list_scopes(self) -> list[str]:
        await self._ensure_migrated()
        async with self._acquire_safe() as conn:
            rows = await conn.fetch(
                f"SELECT DISTINCT scope FROM {self._schema}.dna_documents ORDER BY scope"
            )
        return [r["scope"] for r in rows]

    # ── Phase 10g — Module catalog version surface ────────────────────

    async def list_module_versions(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return semver releases of a Module published to this (scope, tenant).

        Each entry: ``{semver, deprecated, deprecated_message,
        published_at}``. Sorted by created_at ASC (oldest first; the
        harness layer can reverse for display).

        Filters out rows with ``semver IS NULL`` (Phase 9 unversioned
        publishes don't enter the catalog timeline).
        """
        await self._ensure_migrated()
        tenant_val = tenant or ""
        async with self._acquire_safe() as conn:
            rows = await conn.fetch(
                f"SELECT semver, content, created_at FROM {self._schema}.dna_versions "
                "WHERE scope=$1 AND kind='Genome' AND name=$2 AND tenant=$3 "
                "AND semver IS NOT NULL "
                "ORDER BY created_at ASC",
                scope, scope, tenant_val,
            )
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                spec = json.loads(r["content"]).get("spec") or {}
            except Exception:
                spec = {}
            out.append({
                "version": r["semver"],
                "deprecated": bool(spec.get("deprecated", False)),
                "deprecated_message": spec.get("deprecated_message"),
                "published_at": r["created_at"],
            })
        return out

    async def get_module_version(
        self, scope: str, version: str, *, tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the frozen Module manifest for ``scope@version``.

        Returns the parsed raw dict, or None when the version doesn't
        exist for this (scope, tenant). The tenant fallback path
        (tenant overlay → platform) is intentional NOT applied here —
        this endpoint surfaces the exact archive row.
        """
        await self._ensure_migrated()
        tenant_val = tenant or ""
        async with self._acquire_safe() as conn:
            row = await conn.fetchrow(
                f"SELECT content FROM {self._schema}.dna_versions "
                "WHERE scope=$1 AND kind='Genome' AND name=$2 AND tenant=$3 AND semver=$4 "
                "LIMIT 1",
                scope, scope, tenant_val, version,
            )
        if row is None:
            return None
        try:
            return json.loads(row["content"])
        except Exception:
            return None

    async def deprecate_module_version(
        self, scope: str, version: str, *,
        tenant: str | None = None, message: str | None = None,
    ) -> bool:
        """Flip ``spec.deprecated=true`` on the archived row in-place.

        Mutates the JSON content in dna_versions. The bare dna_documents
        row (latest pointer) is updated only if its current version
        equals ``version`` — same convention as the FS adapter.
        """
        await self._ensure_migrated()
        tenant_val = tenant or ""
        async with self._acquire_safe() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"SELECT content FROM {self._schema}.dna_versions "
                    "WHERE scope=$1 AND kind='Genome' AND name=$2 AND tenant=$3 AND semver=$4 "
                    "LIMIT 1",
                    scope, scope, tenant_val, version,
                )
                if row is None:
                    return False
                raw = json.loads(row["content"])
                spec = raw.setdefault("spec", {})
                spec["deprecated"] = True
                if message:
                    spec["deprecated_message"] = message
                new_content = json.dumps(raw)
                await conn.execute(
                    f"UPDATE {self._schema}.dna_versions SET content=$1 "
                    "WHERE scope=$2 AND kind='Genome' AND name=$3 AND tenant=$4 AND semver=$5",
                    new_content, scope, scope, tenant_val, version,
                )
                # Mirror to latest pointer when applicable
                latest = await conn.fetchrow(
                    f"SELECT content FROM {self._schema}.dna_documents "
                    "WHERE scope=$1 AND kind='Genome' AND name=$2 AND tenant=$3",
                    scope, scope, tenant_val,
                )
                if latest is not None:
                    try:
                        cur_spec = json.loads(latest["content"]).get("spec") or {}
                        if cur_spec.get("version") == version:
                            await conn.execute(
                                f"UPDATE {self._schema}.dna_documents SET content=$1 "
                                "WHERE scope=$2 AND kind='Genome' AND name=$3 AND tenant=$4",
                                new_content, scope, scope, tenant_val,
                            )
                    except Exception:
                        pass
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
            source="postgres",
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._pool.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Marco A — Source.query SQL helpers (s-postgres-source-query-impl).
#
# Translate a QueryFilter / QueryOrder into Postgres SQL fragments + params.
# Shared by ``PostgresSource.query``. Kept module-level so they're testable
# in isolation without instantiating a pool.
# ---------------------------------------------------------------------------

_PG_OP_MAP = {
    "eq": "=", "neq": "<>",
    "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "like": "LIKE",
}


def _pg_field_expr(path: str) -> str:
    """Translate a dotted ``field_path`` (QueryFilter convention) into a
    Postgres expression referencing ``dna_documents``.

    Path mapping:
      - ``name``                → ``name``          (dedicated column)
      - ``kind``                → ``kind``          (dedicated column)
      - ``metadata.name``       → ``name``          (canonical column)
      - ``apiVersion``          → ``content::jsonb->>'apiVersion'``
      - ``spec.X.Y.Z`` / ``X``  → ``content::jsonb->'spec'->...->>'Z'``

    Unprefixed paths resolve under ``spec.``. Multi-segment paths walk
    via the ``->`` operator (jsonb) and terminate with ``->>`` (text).
    """
    from dna.kernel.protocols import QueryError

    # Validate (no SQL identifiers as values — defense in depth).
    if not path or any(c in path for c in (";", "'", "\"", "(", ")")):
        raise QueryError(f"invalid field path: {path!r}")

    if path == "name" or path == "metadata.name":
        return "name"
    if path == "kind":
        return "kind"
    if path == "apiVersion":
        return "(content::jsonb->>'apiVersion')"

    if path.startswith("metadata."):
        segments = path.split(".")[1:]
        prefix = "content::jsonb->'metadata'"
    elif path.startswith("spec."):
        segments = path.split(".")[1:]
        prefix = "content::jsonb->'spec'"
    else:
        # Unprefixed → spec.X
        segments = path.split(".")
        prefix = "content::jsonb->'spec'"

    if not segments:
        raise QueryError(f"empty field path after prefix: {path!r}")

    # Walk: all-but-last as ->, last as ->> (text).
    for seg in segments[:-1]:
        prefix += f"->'{seg}'"
    prefix += f"->>'{segments[-1]}'"
    return f"({prefix})"


def _build_pg_where(
    filter: dict | None, *, start_idx: int,
) -> tuple[str, list[Any]]:
    """Build a SQL WHERE fragment + asyncpg params from a QueryFilter.
    Returns ``("", [])`` when filter is empty.

    The fragment is prefixed with ``" AND "`` so it slots after the
    static ``WHERE scope=$1 AND kind=$2 AND tenant=$3`` clause.
    """
    from dna.kernel.protocols import QueryError

    if not filter:
        return "", []

    clauses: list[str] = []
    params: list[Any] = []
    idx = start_idx

    for path, expected in filter.items():
        field_expr = _pg_field_expr(path)

        if isinstance(expected, dict) and len(expected) == 1:
            op, val = next(iter(expected.items()))
            if op == "in":
                if not isinstance(val, (list, tuple)) or not val:
                    raise QueryError(f"'in' value must be non-empty list/tuple")
                # asyncpg supports = ANY($N::text[]) for IN semantics.
                clauses.append(f"{field_expr} = ANY(${idx}::text[])")
                params.append([str(v) for v in val])
                idx += 1
                continue
            if op not in _PG_OP_MAP:
                raise QueryError(
                    f"unknown query operator {op!r} on field {path!r}; "
                    f"valid: {sorted(set(_PG_OP_MAP) | {'in'})}"
                )
            clause, param = _pg_compare_clause(field_expr, _PG_OP_MAP[op], val, idx)
            clauses.append(clause)
            params.append(param)
            idx += 1
        else:
            # Shorthand {field: value} = equality.
            clause, param = _pg_compare_clause(field_expr, "=", expected, idx)
            clauses.append(clause)
            params.append(param)
            idx += 1

    return " AND " + " AND ".join(clauses), params


def _pg_compare_clause(
    field_expr: str, sql_op: str, val: Any, idx: int,
) -> tuple[str, Any]:
    """Build one comparison clause + its bound param, typed by ``val``.

    s-pg-query-pushdown-typing — the JSON field is extracted as TEXT
    (``content::jsonb->>'x'``). Comparing a TEXT extraction against a
    str-coerced param made ``{priority: {gt: 9}}`` compare ``'9' > '10'``
    LEXICOGRAPHICALLY, diverging from the Python fallback (``_match_filter``)
    which compares natively (``10 > 9`` numerically). Cast by the Python type
    of ``val`` so push-down matches the fallback:

      - bool  → ``(field)::boolean op $idx`` (param bound as bool)
      - int/float → guarded numeric cast; rows whose TEXT isn't numeric fail
        the regex guard → NULL → excluded, mirroring the fallback's None-guard
      - str/other → TEXT comparison (unchanged), via ``_pg_coerce_value``
    """
    if isinstance(val, bool):
        return f"({field_expr})::boolean {sql_op} ${idx}", val
    if isinstance(val, (int, float)):
        numeric_field = (
            f"(CASE WHEN {field_expr} ~ '^-?[0-9]+(\\.[0-9]+)?$' "
            f"THEN ({field_expr})::numeric END)"
        )
        return f"{numeric_field} {sql_op} ${idx}::numeric", val
    return f"{field_expr} {sql_op} ${idx}", _pg_coerce_value(val)


def _pg_coerce_value(val: Any) -> Any:
    """asyncpg requires str for ->>'X' comparisons. Coerce primitives
    to str; lists pass through (handled by ANY()). None becomes empty
    string (matches PG behavior for null-on-text JSON paths)."""
    if val is None:
        return ""
    if isinstance(val, (str, list, tuple)):
        return val
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


def _build_pg_order(order_by: list[str]) -> str:
    """Build a SQL ORDER BY fragment from a QueryOrder list. Prefix ``-``
    means DESC. NULLS LAST applied universally for consistency with the
    Python fallback's ``None``-last sort.
    """
    parts: list[str] = []
    for spec in order_by:
        descending = spec.startswith("-")
        path = spec[1:] if descending else spec
        expr = _pg_field_expr(path)
        direction = "DESC" if descending else "ASC"
        parts.append(f"{expr} {direction} NULLS LAST")
    return " ORDER BY " + ", ".join(parts) if parts else ""


# Migrations: each value is a list of individual SQL statements (asyncpg
# does not support multiple statements in a single execute call).
_MIGRATIONS: dict[int, list[str]] = {
    1: [
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_documents (
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope, kind, name)
)
""",
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_versions (
    id         SERIAL PRIMARY KEY,
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    version    INTEGER NOT NULL,
    is_draft   BOOLEAN NOT NULL DEFAULT true,
    author     TEXT,
    created_at TEXT NOT NULL
)
""",
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_layer_documents (
    scope       TEXT NOT NULL,
    layer_id    TEXT NOT NULL,
    layer_value TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    content     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (scope, layer_id, layer_value, kind, name)
)
""",
    ],
    2: [
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_bundle_entries (
    scope       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    entry_path  TEXT NOT NULL,
    content     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (scope, kind, name, entry_path)
)
""",
        """
CREATE INDEX IF NOT EXISTS dna_bundle_entries_scope_kind_idx
    ON {schema}.dna_bundle_entries (scope, kind)
""",
    ],
    3: [
        # Phase 8a — tenant first-class column. Empty string ('') means
        # "legacy/global write" (back-compat with pre-Phase-2c rows). The
        # default lets us include tenant in the PRIMARY KEY without NULLs
        # killing uniqueness (Postgres treats NULLs as distinct).
        # New TENANTED writes populate tenant via the KindPort.scope check
        # in the kernel.
        """
ALTER TABLE {schema}.dna_documents
    ADD COLUMN IF NOT EXISTS tenant TEXT NOT NULL DEFAULT ''
""",
        """
ALTER TABLE {schema}.dna_versions
    ADD COLUMN IF NOT EXISTS tenant TEXT NOT NULL DEFAULT ''
""",
        """
ALTER TABLE {schema}.dna_bundle_entries
    ADD COLUMN IF NOT EXISTS tenant TEXT NOT NULL DEFAULT ''
""",
        # Swap PKs to include tenant. Same (scope, kind, name) across two
        # tenants is now legal. NULLs not in play because of the default.
        """
ALTER TABLE {schema}.dna_documents DROP CONSTRAINT IF EXISTS dna_documents_pkey
""",
        """
ALTER TABLE {schema}.dna_documents
    ADD CONSTRAINT dna_documents_pkey
    PRIMARY KEY (scope, kind, name, tenant)
""",
        """
ALTER TABLE {schema}.dna_bundle_entries DROP CONSTRAINT IF EXISTS dna_bundle_entries_pkey
""",
        """
ALTER TABLE {schema}.dna_bundle_entries
    ADD CONSTRAINT dna_bundle_entries_pkey
    PRIMARY KEY (scope, kind, name, entry_path, tenant)
""",
        # Composite indexes for tenant-scoped queries.
        """
CREATE INDEX IF NOT EXISTS dna_documents_tenant_idx
    ON {schema}.dna_documents (tenant, scope, kind, name)
""",
        """
CREATE INDEX IF NOT EXISTS dna_versions_tenant_idx
    ON {schema}.dna_versions (tenant, scope, kind, name)
""",
        """
CREATE INDEX IF NOT EXISTS dna_bundle_entries_tenant_idx
    ON {schema}.dna_bundle_entries (tenant, scope, kind)
""",
    ],
    4: [
        # Phase 10g — semver column on dna_versions for the Module
        # catalog. NULL means "no semver published" (Phase 9 unversioned
        # path or non-Module kinds). When set, (scope, kind, name,
        # tenant, semver) is unique — that's what immutable releases
        # mean.
        """
ALTER TABLE {schema}.dna_versions ADD COLUMN IF NOT EXISTS semver TEXT
""",
        """
CREATE UNIQUE INDEX IF NOT EXISTS dna_versions_semver_unique
    ON {schema}.dna_versions (scope, kind, name, tenant, semver)
    WHERE semver IS NOT NULL
""",
        """
CREATE INDEX IF NOT EXISTS dna_versions_module_lookup
    ON {schema}.dna_versions (kind, scope, tenant, semver)
    WHERE kind = 'Module' AND semver IS NOT NULL
""",
    ],
    5: [
        # Phase 15.1 — KernelEventBus (Outbox + LISTEN/NOTIFY).
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_outbox (
    id           BIGSERIAL PRIMARY KEY,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    scope        TEXT NOT NULL,
    tenant       TEXT NOT NULL DEFAULT '',
    kind         TEXT NOT NULL,
    name         TEXT NOT NULL,
    op           TEXT NOT NULL,
    doc_version  INTEGER NOT NULL,
    actor        TEXT,
    cause        TEXT
)
""",
        """
CREATE INDEX IF NOT EXISTS dna_outbox_scope_id_idx
    ON {schema}.dna_outbox (scope, tenant, id)
""",
        """
CREATE INDEX IF NOT EXISTS dna_outbox_occurred_at_idx
    ON {schema}.dna_outbox (occurred_at)
""",
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_versions_seq (
    scope    TEXT NOT NULL,
    tenant   TEXT NOT NULL DEFAULT '',
    last_id  BIGINT NOT NULL,
    last_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, tenant)
)
""",
    ],
    6: [
        # Phase 16 cleanup: Module Kind class deleted, Genome replaces it.
        # Drop the v4 ``kind = 'Module'`` partial index and recreate it as
        # ``kind = 'Genome'``. Existing Module rows on databases populated
        # before Phase 16 stay untouched — ``load_bootstrap_docs`` no longer
        # surfaces them, the catalog/install path queries Genome, and the
        # old index simply has nothing to match against post-cleanup.
        """
DROP INDEX IF EXISTS {schema}.dna_versions_module_lookup
""",
        """
CREATE INDEX IF NOT EXISTS dna_versions_package_lookup
    ON {schema}.dna_versions (kind, scope, tenant, semver)
    WHERE kind = 'Genome' AND semver IS NOT NULL
""",
    ],
    8: [
        # s-postgres-source-query-impl (2026-05-14) — hot-field indices
        # for the new Source.query push-down. Without these, the WHERE
        # `content->'spec'->>'status' = $N` does a full table scan; with
        # them, the filter is index-resolved in <50ms for typical scopes.
        #
        # We index ONLY the 3 hottest fields observed in Studio request
        # logs (status, feature, updated_at) plus a GIN over content->
        # 'spec' for arbitrary spec.X equality queries we can't predict.
        #
        # Idempotent: CREATE INDEX IF NOT EXISTS — no-op on re-apply.
        """
CREATE INDEX IF NOT EXISTS dna_docs_status_idx
    ON {schema}.dna_documents ((content::jsonb->'spec'->>'status'))
    WHERE content::jsonb ? 'spec'
""",
        """
CREATE INDEX IF NOT EXISTS dna_docs_feature_idx
    ON {schema}.dna_documents ((content::jsonb->'spec'->>'feature'))
    WHERE content::jsonb ? 'spec'
""",
        """
CREATE INDEX IF NOT EXISTS dna_docs_updated_at_idx
    ON {schema}.dna_documents ((content::jsonb->'spec'->>'updated_at'))
    WHERE content::jsonb ? 'spec'
""",
        """
CREATE INDEX IF NOT EXISTS dna_docs_spec_gin_idx
    ON {schema}.dna_documents USING gin ((content::jsonb->'spec'))
    WHERE content::jsonb ? 'spec'
""",
    ],
    7: [
        # s-edge-table-materializer (2026-05-12) — cross-doc citation
        # graph materialized in a sidecar table. Populated by an
        # observer in app.py write-hook that parses spec for slugs
        # (s-/f-/e-/spec-/plan-/cycle-/rem-/dream-/forget-/verdict-)
        # and upserts edges. Dropped freely without losing doc data
        # (same design as dna_doc_embeddings sidecar).
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_edges (
    scope        TEXT NOT NULL,
    from_kind    TEXT NOT NULL,
    from_name    TEXT NOT NULL,
    to_kind      TEXT NOT NULL,
    to_name      TEXT NOT NULL,
    edge_type    TEXT NOT NULL DEFAULT 'spec-ref',
    source_field TEXT,
    tenant       TEXT NOT NULL DEFAULT '',
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, from_kind, from_name, to_kind, to_name, edge_type, tenant)
)
""",
        """
CREATE INDEX IF NOT EXISTS dna_edges_from_lookup
    ON {schema}.dna_edges (scope, from_kind, from_name, tenant)
""",
        """
CREATE INDEX IF NOT EXISTS dna_edges_to_lookup
    ON {schema}.dna_edges (scope, to_kind, to_name, tenant)
""",
    ],
    9: [
        # F2 fix (found by test_postgres_source_count's bundle-guard test,
        # 2026-06-10): da74b845 (binary bundle entries, 2026-05-25) added
        # all the code reading/writing ``content_binary`` but never a
        # migration — the dev DB got the column by hand, so EVERY fresh
        # schema bootstrap broke on the first bundle-entry read/write
        # (UndefinedColumnError in _load_view / save_document /
        # fetch_bundle_entry). Idempotent: IF NOT EXISTS no-ops on DBs
        # already patched manually (e.g. dev public).
        """
ALTER TABLE {schema}.dna_bundle_entries
    ADD COLUMN IF NOT EXISTS content_binary BYTEA
""",
    ],
}
