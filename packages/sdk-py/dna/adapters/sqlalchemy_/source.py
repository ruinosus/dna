"""SqlAlchemySource — ONE adapter, TWO dialects, SAME tables (production).

SQLAlchemy Core 2.x async implementation of SourcePort + WritableSourcePort
against the EXISTING adapter schemas (promoted from the i-216 spike by
``s-sqlalchemy-source-production``):

  - sqlite  (aiosqlite):  ``documents`` / ``versions`` / ``bundle_entries``
    / ``layer_documents`` — byte-compatible with DBs built by the retired
    raw sqlite adapter, including the ``schema_migrations`` control table.
  - postgresql (asyncpg): ``{schema}.dna_documents`` / ``dna_versions`` /
    ``dna_bundle_entries`` / ``dna_layer_documents`` / ``dna_outbox`` /
    ``dna_versions_seq`` — byte-compatible with schemas built by the retired
    raw PG adapter, including ``dna_schema_migrations``.

The adapter REUSES each dialect's existing migration payloads (it invents
no schema); the shared forward-only runner (``adapters/_migrations.py``)
applies them, so a DB touched by this adapter is indistinguishable from
one touched by the raw adapters — **switching adapters is pure
instantiation, zero data migration** (see docs/PORT-CONTRACT.md §
"Using the SQLAlchemy adapter").

Production behaviors (each mirrors the raw adapter that pioneered it):

  - **PG eventbus as a dialect strategy** (:class:`_PgOutboxEmitter`):
    every write on the postgresql dialect appends to ``dna_outbox``,
    checkpoints ``dna_versions_seq`` and fires ``pg_notify`` on
    ``KERNEL_EVENTBUS_CHANNEL`` **inside the same transaction** as the
    data write — Phase 15.1 semantics. The NOTIFY payload is built by
    ``dna.kernel.boot.eventbus.build_notify_payload`` — the same producer
    contract the retired raw ``PostgresSource`` used, now co-located with
    the channel constant. SQLite gets :class:`_NullEventEmitter` (no bus
    — H2).
  - **Memo-cached ``_load_view``** (dialect-agnostic): the canonical
    (scope, tenant) view is memoized with a single-flight lock and served
    as deep copies (s-query-loadview-cache semantics). Invalidation is a
    superset of the raw PG adapter's: local writes through THIS source
    invalidate directly, and ``attach_kernel`` additionally wires
    ``kernel.on_write`` so kernel-path + cross-process (EventBus) writes
    invalidate too.
  - **FrontmatterParseWarning net** in ``_load_view`` / ``load_one``:
    a bundle marker with corrupt YAML frontmatter falls back to the
    canonical ``documents.content`` row instead of silently serving an
    anemic spec (D-B hardening, mirrors raw PG).
  - **``spec.source_files`` net** in ``save_document`` (kind-agnostic,
    s-sync-s3): carried bundle entries persist for every bundle kind
    whose writer doesn't consume them itself.
  - **Auto-publish**: ``save_document`` UPSERTs ``documents`` in the same
    transaction (the raw-PG contract — ``kernel.write_document`` treats
    save as the publish point and never calls ``publish()``).
  - **Genome catalog + layer surfaces**: ``list_module_versions`` /
    ``get_module_version`` / ``deprecate_module_version`` and
    ``save_layer_document`` / ``delete_layer_document`` / ``list_layers``
    / ``list_tenants`` — full parity with the raw adapters.

Honesty markers: every place the two dialects could NOT be expressed as
one Core construct is tagged ``# [dialect]``. Known inherited limitation:
the SQLite ``documents`` PK lacks ``tenant`` (i-092) — a tenant overlay
publish clobbers the base row. Schema debt, not a Core limitation (the
conformance matrix carries the strict xfail).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from dna.kernel.protocols import WritableSourcePort

# Single source of truth for the Phase 15.1 event contract — the payload
# builder + channel name live with the KernelEventBus contract itself
# (dna/kernel/eventbus.py), shared with the PostgresEventBus subscriber.
from dna.kernel.boot.eventbus import KERNEL_EVENTBUS_CHANNEL, build_notify_payload

if TYPE_CHECKING:
    from dna.kernel.capabilities import SourceCapabilities

logger = logging.getLogger(__name__)

_OPS = ("eq", "neq", "gt", "gte", "lt", "lte", "like")
_PG_NUMERIC_RE = r"^-?[0-9]+(\.[0-9]+)?$"

# s-pg-schema-identifier-guard (inherited from the retired raw Postgres
# adapter): the schema identifier is f-string-interpolated into the
# migration DDL + control-table statements and can't be a bind param, so
# validate it ONCE at construction against a conservative allowlist —
# trusted-config-only, never request input.
_VALID_SCHEMA_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_name(raw: dict) -> str | None:
    meta = raw.get("metadata") or {}
    return meta.get("name") or raw.get("name")


class _NullEventEmitter:
    """SQLite dialect: no cross-process bus (H2) — emission is a no-op."""

    async def emit(self, conn: Any, **event: Any) -> None:
        return None


class _PgOutboxEmitter:
    """Postgres dialect strategy — Phase 15.1 outbox + LISTEN/NOTIFY.

    Emits the KernelEventBus event atomically with the caller's data
    write (the caller passes the open ``engine.begin()`` connection).
    Three operations, same transaction — the contract the retired raw PG
    adapter's ``_emit_outbox`` pioneered:

      1. INSERT into ``dna_outbox`` (durable, FIFO event log).
      2. UPSERT ``dna_versions_seq`` (per-(scope, tenant) checkpoint).
      3. ``pg_notify`` on :data:`KERNEL_EVENTBUS_CHANNEL`.

    The payload is produced by ``dna.kernel.boot.eventbus.build_notify_payload``
    (the shared producer contract), so ``PostgresEventBus`` subscribers
    see the exact same wire shape the retired raw adapter emitted.
    """

    def __init__(self, source: "SqlAlchemySource") -> None:
        self._src = source

    async def emit(
        self,
        conn: Any,
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
        src = self._src
        actor_val = actor if actor is not None else src._default_actor
        cause_val = cause if cause is not None else src._default_cause

        outbox_id: int = (await conn.execute(
            src.outbox.insert().returning(src.outbox.c.id).values(
                scope=scope, tenant=tenant, kind=kind, name=name,
                op=op, doc_version=doc_version,
                actor=actor_val, cause=cause_val,
            )
        )).scalar_one()
        ins = src._upsert(src.versions_seq).values(
            scope=scope, tenant=tenant,
            last_id=outbox_id, last_at=sa.func.now(),
        )
        await conn.execute(ins.on_conflict_do_update(
            index_elements=["scope", "tenant"],
            set_={"last_id": ins.excluded.last_id,
                  "last_at": ins.excluded.last_at},
        ))
        payload = build_notify_payload(
            outbox_id, scope, tenant, kind, name, op, doc_version,
            actor_val, write_class,
        )
        await conn.execute(
            sa.select(sa.func.pg_notify(KERNEL_EVENTBUS_CHANNEL, payload))
        )
        return outbox_id


class SqlAlchemySource(WritableSourcePort):
    """WritableSourcePort over SQLAlchemy Core async (aiosqlite | asyncpg).

    Usage::

        src = SqlAlchemySource("sqlite+aiosqlite:///path/to.db")
        src = SqlAlchemySource("postgresql+asyncpg://u:p@h/db", schema="dna_x")
        await src.connect()   # runs the dialect's existing migrations
    """

    supports_readers: bool = False
    # Instance-level on __init__: True on the postgresql dialect (the
    # outbox emitter propagates writes cross-process, Phase 15.1),
    # False on sqlite. Class default kept for introspection safety.
    supports_cross_process_invalidation: bool = False

    def __init__(
        self,
        url: str,
        *,
        schema: str | None = None,
        writers: list | None = None,
        readers: list | None = None,
    ) -> None:
        self._engine: AsyncEngine = create_async_engine(url)
        self._is_pg = self._engine.dialect.name == "postgresql"
        # [dialect] pg keeps its namespaced schema; sqlite has none.
        if schema is not None and not _VALID_SCHEMA_IDENT.match(schema):
            raise ValueError(
                f"Invalid Postgres schema identifier {schema!r}: must match "
                f"{_VALID_SCHEMA_IDENT.pattern} (trusted-config-only — set via "
                "deploy config, never from request input)."
            )
        self._schema = schema if self._is_pg else None
        # [dialect] base-layer tenant sentinel on documents/versions:
        # pg uses '' (NOT NULL DEFAULT ''), sqlite uses NULL (Phase 2c).
        self._doc_base: str | None = "" if self._is_pg else None
        self._writers = writers or []
        self._readers = readers or []
        self._kernel: object | None = None
        # Phase 15.1 — actor/cause defaults for outbox attribution (set at
        # __init__ so direct callers that bypass Kernel.auto are covered).
        self._default_actor: str | None = os.environ.get("USER") or "system"
        self._default_cause: str | None = None
        # Perf (s-query-loadview-cache parity): memoize _load_view per
        # (scope, tenant) with a single-flight lock; deep copies out.
        self._view_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._view_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._view_invalidation_wired = False
        self._build_tables()
        # [dialect] eventbus emission is a pg-only strategy (H2): the
        # outbox/NOTIFY machinery is Postgres infrastructure; sqlite has
        # no cross-process bus and gets the no-op emitter.
        self._events: _PgOutboxEmitter | _NullEventEmitter = (
            _PgOutboxEmitter(self) if self._is_pg else _NullEventEmitter()
        )
        self.supports_cross_process_invalidation = self._is_pg

    # ------------------------------------------------------------------
    # Table metadata — the ONE model, shared with Alembic autogenerate
    # ------------------------------------------------------------------

    def _build_tables(self) -> None:
        """Bind to the table model in ``schema.py``.

        The model used to be defined inline here, in parallel with the DDL
        payloads in ``migrations.py``, with nothing checking they agreed —
        the drift that cost two weeks (``content_binary``). Now there is
        one definition, and it is also Alembic's ``target_metadata``, so a
        disagreement between the model and a real database is a test
        failure (tests/test_schema_autogenerate_guard.py).
        """
        from .schema import build_metadata

        tables = build_metadata(is_pg=self._is_pg, schema=self._schema)
        self.metadata = tables.metadata
        self.documents = tables.documents
        self.versions = tables.versions
        self.bundle_entries = tables.bundle_entries
        self.layer_documents = tables.layer_documents
        if self._is_pg:
            self.outbox = tables.outbox
            self.versions_seq = tables.versions_seq

    # ------------------------------------------------------------------
    # Dialect seams (each is [dialect] evidence)
    # ------------------------------------------------------------------

    def _doc_tenant(self, tenant: str | None) -> str | None:
        """Stored tenant value for documents/versions rows."""
        return tenant if tenant else self._doc_base

    def _tenant_where(self, col: sa.Column, tenant: str | None) -> sa.ColumnElement:
        v = self._doc_tenant(tenant)
        # [dialect] NULL sentinel (sqlite) can't be compared with `=`.
        return col.is_(None) if v is None else col == v

    def _upsert(self, table: sa.Table):
        # [dialect] Core 2.x has NO generic upsert — the two dialect
        # constructs share an identical API, so ONE seam picks the factory.
        if self._is_pg:
            from sqlalchemy.dialects.postgresql import insert as _insert
        else:
            from sqlalchemy.dialects.sqlite import insert as _insert
        return _insert(table)

    def _doc_conflict_cols(self) -> list[str]:
        # [dialect] documents PK: pg = (scope,kind,name,tenant);
        # sqlite = (scope,kind,name) — i-092 lives HERE, in the schema.
        return ["scope", "kind", "name", "tenant"] if self._is_pg \
            else ["scope", "kind", "name"]

    def _json_expr(self, path: str) -> sa.ColumnElement:
        """Dotted field path → SQL expression over documents.content.

        Same path vocabulary as ``_pg_field_expr`` / ``_sqlite_field_expr``.
        """
        from dna.kernel.protocols import QueryError

        if not path or any(c in path for c in (";", "'", "\"", "(", ")")):
            raise QueryError(f"invalid field path: {path!r}")
        if path in ("name", "metadata.name"):
            return self.documents.c.name
        if path == "kind":
            return self.documents.c.kind
        if path == "apiVersion":
            segments = ["apiVersion"]
        elif path.startswith(("metadata.", "spec.")):
            segments = path.split(".")
        else:
            segments = ["spec", *path.split(".")]
        if self._is_pg:
            # [dialect] legacy column is TEXT → explicit JSONB cast, then
            # -> walk + ->> terminal (astext). Core can't hide this while
            # the column type stays TEXT.
            from sqlalchemy.dialects.postgresql import JSONB
            expr: Any = sa.cast(self.documents.c.content, JSONB)
            for seg in segments[:-1]:
                expr = expr[seg]
            return expr[segments[-1]].astext
        # [dialect] sqlite: json_extract returns the NATIVE json type
        # (int stays int) — no cast dance, but a different function.
        return sa.func.json_extract(
            self.documents.c.content, "$." + ".".join(segments),
        )

    def _typed_cmp(self, path: str, val: Any) -> tuple[sa.ColumnElement, Any]:
        """(expr, bind) typed so gt/lt compare like the Python fallback."""
        expr = self._json_expr(path)
        if not self._is_pg:
            # [dialect] sqlite json_extract is already native-typed;
            # only bool needs the 0/1 coercion.
            if isinstance(val, bool):
                return expr, (1 if val else 0)
            return expr, val
        # [dialect] pg ->> yields TEXT: bool → ::boolean cast; numbers →
        # regex-guarded ::numeric CASE (mirrors _pg_compare_clause).
        if isinstance(val, bool):
            return sa.cast(expr, sa.Boolean), val
        if isinstance(val, (int, float)):
            guarded = sa.case(
                (expr.op("~")(_PG_NUMERIC_RE), sa.cast(expr, sa.Numeric)),
            )
            return guarded, val
        return expr, (str(val) if not isinstance(val, str) else val)

    # ------------------------------------------------------------------
    # Search wiring (i-069)
    # ------------------------------------------------------------------

    def pg_search_binding(self) -> tuple[str, str] | None:
        """The ``(dsn, schema)`` pair for wiring a pgvector search provider
        NEXT TO this source — ``None`` on sqlite.

        The scale search adapter (:class:`~dna.adapters.search.pgvector.
        PgVecRecordSearchProvider`) reuses the SAME Postgres this source
        already runs on; this method is the one sanctioned way for a boot
        path to derive its connection from the source instead of re-parsing
        environment URLs. The DSN is rendered DRIVERLESS
        (``postgresql://…``, password preserved) because the provider speaks
        native asyncpg, not SQLAlchemy; the schema falls back to ``public``,
        matching the provider's own default.
        """
        if not self._is_pg:
            return None
        dsn = self._engine.url.set(drivername="postgresql").render_as_string(
            hide_password=False
        )
        return dsn, (self._schema or "public")

    # ------------------------------------------------------------------
    # Migrations — Alembic (i-038)
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        if not self._is_pg:
            async with self._engine.connect() as conn:
                await conn.exec_driver_sql("PRAGMA journal_mode=WAL")  # [dialect]
        await self.run_schema_migrations()

    async def run_schema_migrations(self) -> list[str]:
        """Bring the backing database to the current schema head.

        Applied automatically by ``connect()`` — unchanged from the retired
        runner, and deliberately so: this library owns tables in its
        consumer's database, and consumers (dna-cloud's four containers)
        rely on boot-time application.

        Returns:
            The Alembic revision ids applied by THIS call, in application
            order. ``[]`` means the database was already at head — the
            idempotent re-boot every service performs.

            NOTE: the retired runner returned ``list[int]``, the numbered
            ladder's version numbers. Alembic identifies a revision by
            string id, so the contract is now ``list[str]``; the public
            conformance kit was updated to match (see
            ``dna/testing/source_conformance.py`` and
            docs/PORT-CONTRACT.md § "Schema migrations").
        """
        from .migrate import upgrade_sync

        async with self._engine.begin() as conn:
            return await conn.run_sync(
                lambda sync_conn: upgrade_sync(sync_conn, self._schema)
            )

    # ------------------------------------------------------------------
    # Kernel wiring
    # ------------------------------------------------------------------

    def attach_kernel(self, kernel: object) -> None:
        from dna.kernel import Kernel as _KernelType
        if not isinstance(kernel, _KernelType):
            raise TypeError(
                f"attach_kernel requires a Kernel instance; got {type(kernel).__name__}"
            )
        self._kernel = kernel
        # Wire view-cache invalidation onto the kernel's on_write bus —
        # fires for kernel-path writes AND cross-process writes (EventBus
        # pg_notify → kernel.invalidate → observer fan-out). Local writes
        # through THIS source invalidate directly (see save_document);
        # this wiring covers everything else. Guarded so idempotent
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

    def _live_readers(self) -> list:
        """Kernel's live readers list (s-composition-and-nav-lazy):
        ``self._readers`` is a snapshot captured at attach_kernel time,
        BEFORE extensions register their generic bundle readers — prefer
        the kernel's current list when attached."""
        if getattr(self, "_kernel", None) is not None:
            return list(getattr(self._kernel, "_readers", []))
        return list(getattr(self, "_readers", None) or [])

    def _reader_can_produce(self, kind: str, live_readers: list | None = None) -> bool:
        """Bundle-override gate shared by ``query()`` (and, via
        ``count_via_query``, ``count()``): True when a registered reader
        can produce ``kind`` — bundle docs may masquerade as this kind and
        pure SQL push-down would diverge from ``load_all`` semantics."""
        readers = self._live_readers() if live_readers is None else live_readers
        return any(getattr(r, "_kind", None) == kind for r in readers)

    # ------------------------------------------------------------------
    # SourcePort (read)
    # ------------------------------------------------------------------

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        from dna.kernel.protocols import BOOTSTRAP_KIND_NAMES
        d = self.documents
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                sa.select(d.c.content).where(
                    d.c.scope == scope,
                    d.c.kind.in_(BOOTSTRAP_KIND_NAMES),
                    self._tenant_where(d.c.tenant, None),
                )
            )
            out = [json.loads(r.content) for r in rows]
            if tenant:
                trow = (await conn.execute(
                    sa.select(d.c.content).where(
                        d.c.scope == scope, d.c.kind == "Genome",
                        d.c.tenant == tenant,
                    ).limit(1)
                )).first()
                if trow is not None:
                    out = [x for x in out if x.get("kind") != "Genome"]
                    out.append(json.loads(trow.content))
        return out

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        return await self._load_view(scope, tenant=None, readers=readers)

    async def _load_view(
        self, scope: str, *, tenant: str | None, readers: list | None,
    ) -> list[dict[str, Any]]:
        """Cached front for :meth:`_load_view_uncached`.

        Memoizes the canonical (scope, tenant) view and returns DEEP
        COPIES so callers may mutate rows without corrupting the cache.
        A single-flight lock collapses a concurrent first-hit burst into
        one compute (s-query-loadview-cache). Invalidated by local writes
        (save/publish/delete on this source) and by ``kernel.on_write``
        (attach_kernel) for kernel-path + cross-process writes.

        ``readers`` affects output but is NOT part of the key: readers
        are registered once at boot and stable thereafter.
        """
        key = (scope, tenant or "")
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
        entries for that scope (every tenant). Best-effort, never raises."""
        try:
            if scope is None:
                self._view_cache.clear()
                return
            for k in [k for k in self._view_cache if k[0] == scope]:
                self._view_cache.pop(k, None)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _read_with_frontmatter_net(reader: Any, handle: Any, canonical: str) -> dict:
        """Reader.read with the FrontmatterParseWarning fallback (D-B
        hardening, mirrors raw PG): when the bundle marker has corrupt
        YAML frontmatter the reader warns and returns an anemic spec —
        surface the warning ONCE but serve the canonical ``content`` row
        instead of letting the broken marker silently wipe the doc."""
        import warnings as _w

        from dna.kernel.source.generic_rw import FrontmatterParseWarning

        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always", FrontmatterParseWarning)
            doc_from_marker = reader.read(handle)
        parse_failed = any(
            issubclass(w.category, FrontmatterParseWarning) for w in caught
        )
        if parse_failed:
            for w in caught:
                _w.warn_explicit(str(w.message), w.category, w.filename, w.lineno)
            return json.loads(canonical)
        return doc_from_marker

    async def _load_view_uncached(
        self, scope: str, *, tenant: str | None, readers: list | None,
    ) -> list[dict[str, Any]]:
        """2-query scope view (docs + bundle entries) with reader resolution.

        This whole method is dialect-FREE — the biggest unification win:
        the raw adapters carry two divergent copies of it.
        """
        effective_readers = list(self._readers)
        for r in (readers or []):
            if r not in effective_readers:
                effective_readers.append(r)
        d, b = self.documents, self.bundle_entries
        entry_cols = [b.c.kind, b.c.name, b.c.entry_path, b.c.content]
        if self._is_pg:
            entry_cols.append(b.c.content_binary)  # [dialect]
        async with self._engine.connect() as conn:
            doc_rows = (await conn.execute(
                sa.select(d.c.kind, d.c.name, d.c.content).where(
                    d.c.scope == scope,
                    self._tenant_where(d.c.tenant, tenant),
                )
            )).all()
            entry_rows = (await conn.execute(
                sa.select(*entry_cols).where(
                    b.c.scope == scope,
                    b.c.tenant == (tenant or ""),  # bundle sentinel is '' on BOTH
                )
            )).all()
        entries_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for e in entry_rows:
            cb = e.content_binary if self._is_pg else None
            val: str | bytes = bytes(cb) if cb else e.content
            entries_by_key.setdefault((e.kind, e.name), {})[e.entry_path] = val

        from dna.kernel.bundle.handle import DictBundleHandle
        out: list[dict[str, Any]] = []
        for r in doc_rows:
            entries = entries_by_key.get((r.kind, r.name))
            if entries and effective_readers:
                handle = DictBundleHandle(r.name, entries)
                matched = False
                for reader in effective_readers:
                    try:
                        if not reader.detect(handle):
                            continue
                        out.append(self._read_with_frontmatter_net(
                            reader, handle, r.content,
                        ))
                        matched = True
                        break
                    except Exception:  # noqa: BLE001
                        continue
                if matched:
                    continue
            out.append(json.loads(r.content))
        return out

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]:
        if layer_id == "tenant":
            return await self._load_view(scope, tenant=layer_value, readers=readers)
        ld = self.layer_documents
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                sa.select(ld.c.content).where(
                    ld.c.scope == scope, ld.c.layer_id == layer_id,
                    ld.c.layer_value == layer_value,
                )
            )
            return [json.loads(r.content) for r in rows]

    async def resolve_ref(self, scope: str, ref: str) -> str:
        return ""

    async def close(self) -> None:
        await self._engine.dispose()

    async def list_doc_refs(
        self, scope: str, *, kind: str | None = None,
        tenant: str | None = None,
    ) -> list[tuple[str, str]]:
        d = self.documents
        tenant_pred = self._tenant_where(d.c.tenant, tenant) if tenant \
            else self._tenant_where(d.c.tenant, None)
        if tenant:
            tenant_pred = sa.or_(
                self._tenant_where(d.c.tenant, None), d.c.tenant == tenant,
            )
        stmt = sa.select(d.c.kind, d.c.name).where(d.c.scope == scope, tenant_pred)
        if kind:
            stmt = stmt.where(d.c.kind == kind)
        stmt = stmt.order_by(d.c.kind, d.c.name)
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        seen: dict[tuple[str, str], None] = {}
        for r in rows:  # overlay+base dedupe in Python (portable)
            seen.setdefault((r.kind, r.name), None)
        return list(seen.keys())

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers: list | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        effective_readers = list(self._readers)
        for r in (readers or []):
            if r not in effective_readers:
                effective_readers.append(r)
        d, b = self.documents, self.bundle_entries
        entry_cols = [b.c.entry_path, b.c.content]
        if self._is_pg:
            entry_cols.append(b.c.content_binary)  # [dialect]
        tenant_candidates: list[str | None] = [tenant, None] if tenant else [None]
        async with self._engine.connect() as conn:
            for t in tenant_candidates:
                row = (await conn.execute(
                    sa.select(d.c.content).where(
                        d.c.scope == scope, d.c.kind == kind, d.c.name == name,
                        self._tenant_where(d.c.tenant, t),
                    )
                )).first()
                if row is None:
                    continue
                erows = (await conn.execute(
                    sa.select(*entry_cols).where(
                        b.c.scope == scope, b.c.kind == kind, b.c.name == name,
                        b.c.tenant == (t or ""),
                    )
                )).all()
                entries: dict[str, str | bytes] = {}
                for e in erows:
                    cb = e.content_binary if self._is_pg else None
                    entries[e.entry_path] = bytes(cb) if cb else e.content
                if entries and effective_readers:
                    from dna.kernel.bundle.handle import DictBundleHandle
                    handle = DictBundleHandle(name, entries)
                    for reader in effective_readers:
                        try:
                            if not reader.detect(handle):
                                continue
                            return self._read_with_frontmatter_net(
                                reader, handle, row.content,
                            )
                        except Exception:  # noqa: BLE001
                            continue
                return json.loads(row.content)
        return None

    async def list_tenants(self, scope: str | None = None) -> list[str]:
        """Distinct non-base tenants observed in documents (optionally
        narrowed to one scope) — parity with FS + raw PG."""
        d = self.documents
        # Non-base predicate covers BOTH sentinels (pg '' / sqlite NULL).
        pred = sa.and_(d.c.tenant.isnot(None), d.c.tenant != "")
        stmt = sa.select(d.c.tenant).distinct().where(pred).order_by(d.c.tenant)
        if scope is not None:
            stmt = stmt.where(d.c.scope == scope)
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        return [r.tenant for r in rows]

    # ------------------------------------------------------------------
    # query / count push-down
    # ------------------------------------------------------------------

    def _build_where(self, filter: dict | None) -> list[sa.ColumnElement]:
        from dna.kernel.protocols import QueryError

        clauses: list[sa.ColumnElement] = []
        for path, expected in (filter or {}).items():
            if isinstance(expected, dict) and len(expected) == 1:
                op, val = next(iter(expected.items()))
                if op == "in":
                    if not isinstance(val, (list, tuple)) or not val:
                        raise QueryError("'in' value must be non-empty list/tuple")
                    expr = self._json_expr(path)
                    vals = [str(v) for v in val] if self._is_pg else list(val)
                    clauses.append(expr.in_(vals))
                    continue
                if op not in _OPS:
                    raise QueryError(
                        f"unknown query operator {op!r} on field {path!r}; "
                        f"valid: {sorted(set(_OPS) | {'in'})}"
                    )
                expr, bind = self._typed_cmp(path, val)
                clauses.append({
                    "eq": expr == bind, "neq": expr != bind,
                    "gt": expr > bind, "gte": expr >= bind,
                    "lt": expr < bind, "lte": expr <= bind,
                    "like": expr.like(bind),
                }[op])
            else:
                expr, bind = self._typed_cmp(path, expected)
                clauses.append(expr == bind)
        return clauses

    def _build_order(self, order_by: list[str]) -> list[sa.ColumnElement]:
        out = []
        for spec in order_by:
            desc = spec.startswith("-")
            expr = self._json_expr(spec[1:] if desc else spec)
            out.append((expr.desc() if desc else expr.asc()).nulls_last())
        return out

    async def query(
        self, scope: str, kind: str, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant=None,
    ):
        from dna.kernel.protocols import (
            QueryError, _apply_order_by, _match_filter, _page_unordered_union,
            _project_doc,
        )
        if filter is not None and not isinstance(filter, dict):
            raise QueryError(f"filter must be dict, got {type(filter).__name__}")
        d = self.documents

        # Slow-path (bundle-override guard, parity with raw PG): when a
        # registered reader can produce this kind, bundle docs may
        # masquerade as it and pure SQL push-down would diverge from
        # load_all — route through the (cached) view + Python filter.
        _live_readers = self._live_readers()
        if self._reader_can_produce(kind, _live_readers):
            base_docs = await self._load_view(
                scope, tenant=None, readers=_live_readers,
            )
            if tenant:
                overlay_docs = await self._load_view(
                    scope, tenant=tenant, readers=_live_readers,
                )
                shadow = {(x.get("kind"), _doc_name(x)) for x in overlay_docs}
                raw_docs = [
                    x for x in base_docs
                    if (x.get("kind"), _doc_name(x)) not in shadow
                ] + overlay_docs
            else:
                raw_docs = base_docs
            kind_docs = [x for x in raw_docs if x.get("kind") == kind]
            if filter:
                kind_docs = [x for x in kind_docs if _match_filter(x, filter)]
            if order_by:
                kind_docs = _apply_order_by(kind_docs, order_by)
                start = offset or 0
                end = (start + limit) if limit is not None else None
                kind_docs = kind_docs[start:end]
            else:
                # i-069: unordered limited union — the overlay (the caller's
                # OWN partition) must survive the cut; see _page_unordered_union.
                overlay_ids = frozenset(
                    id(x) for x in (overlay_docs if tenant else ())
                )
                kind_docs = _page_unordered_union(
                    kind_docs, overlay_ids, offset, limit,
                )
            for doc in kind_docs:
                yield _project_doc(doc, projection) if projection else doc
            return

        async def _fetch_one_tenant(conn, t: str | None) -> list[dict[str, Any]]:
            stmt = sa.select(d.c.content).where(
                d.c.scope == scope, d.c.kind == kind,
                self._tenant_where(d.c.tenant, t),
                *self._build_where(filter),
            )
            if order_by:
                stmt = stmt.order_by(*self._build_order(order_by))
            if limit is not None:
                stmt = stmt.limit(int(limit))
            if offset is not None and offset > 0:
                stmt = stmt.offset(int(offset))
            rows = (await conn.execute(stmt)).all()
            return [json.loads(r.content) for r in rows]

        # Materialize while connected, yield after close (same leak-guard
        # rationale as s-sqlite-single-connection).
        async with self._engine.connect() as conn:
            if tenant is None:
                docs = await _fetch_one_tenant(conn, None)
            else:
                overlay = await _fetch_one_tenant(conn, tenant)
                base = await _fetch_one_tenant(conn, None)
                shadow = {
                    (x.get("kind"), _doc_name(x)) for x in overlay
                }
                docs = [x for x in base if (x.get("kind"), _doc_name(x)) not in shadow]
                docs.extend(overlay)
                if order_by:
                    docs = _apply_order_by(docs, order_by)
                    if offset:
                        docs = docs[int(offset):]
                    if limit is not None:
                        docs = docs[: int(limit)]
                else:
                    # i-069: unordered limited union — a plain [:limit] cut
                    # starved the overlay (the caller's OWN partition, e.g.
                    # personal:<oid>) the moment the base leg alone reached
                    # the limit: a personal recall's lexical scan then read
                    # N base rows and NONE of the caller's own memories.
                    docs = _page_unordered_union(
                        docs, frozenset(id(x) for x in overlay), offset, limit,
                    )

            # Fast-path bundle-override exclusion (parity with raw PG):
            # docs whose bundle entries are detected by a reader that
            # produces a DIFFERENT kind must be excluded — load_all hands
            # them out under the reader-output kind only.
            names_to_drop: set[str] = set()
            if docs and _live_readers:
                b = self.bundle_entries
                names = [_doc_name(x) or "" for x in docs]
                erows = (await conn.execute(
                    sa.select(b.c.name, b.c.entry_path, b.c.content).where(
                        b.c.scope == scope, b.c.tenant == (tenant or ""),
                        b.c.kind == kind, b.c.name.in_(names),
                    )
                )).all()
                if erows:
                    from dna.kernel.bundle.handle import DictBundleHandle
                    entries_by_name: dict[str, dict[str, str]] = {}
                    for e in erows:
                        entries_by_name.setdefault(e.name, {})[e.entry_path] = e.content
                    for name, entries in entries_by_name.items():
                        handle = DictBundleHandle(name, entries)
                        for reader in _live_readers:
                            try:
                                if reader.detect(handle):
                                    produced = getattr(reader, "_kind", None)
                                    if produced and produced != kind:
                                        names_to_drop.add(name)
                                    break
                            except Exception:  # noqa: BLE001
                                continue
        if names_to_drop:
            docs = [x for x in docs if _doc_name(x) not in names_to_drop]
            # Re-apply order_by + limit after the drop (SQL ordering on
            # the pre-drop set doesn't survive it).
            if order_by:
                docs = _apply_order_by(docs, order_by)
            if offset:
                docs = docs[int(offset):]
            if limit is not None:
                docs = docs[: int(limit)]

        for doc in docs:
            yield _project_doc(doc, projection) if projection else doc

    async def count(
        self, scope: str, kind: str, *,
        filter=None, group_by=None, tenant=None,
    ) -> dict[str, Any]:
        """COUNT push-down (F2 D2) — the pg dialect aggregates natively in
        SQL (only aggregates travel back, never rows), inheriting the
        retired raw PG adapter's native count. The sqlite dialect rides
        this adapter's ``query()`` via the shared helper — the raw sqlite
        adapter's documented choice ("native push-down can land later if
        sqlite scopes grow").

        Bundle-override guard (mirrors ``query()``'s slow-path): when a
        registered reader can produce this kind, bundle docs may cross
        containers and pure SQL would diverge — ride the protocol default,
        which inherits query()'s slow-path bundle resolution.

        Tenant dedup (pg): ``DISTINCT ON (name) … ORDER BY name, tenant
        DESC`` (overlay wins: any slug > '' lexicographically) in a
        subquery; the ``filter`` applies INSIDE, per physical row —
        matching ``query()``'s per-tenant fetches (a base row that matches
        the filter is not shadowed by an overlay that doesn't).

        Group ordering: count DESC, key ASC NULLS LAST — parity with the
        protocol default (``-count, key-is-None, str(key)``).
        """
        from dna.kernel.protocols import QueryError
        from dna.kernel.query.fallback import count_via_query

        if filter is not None and not isinstance(filter, dict):
            raise QueryError(f"filter must be dict, got {type(filter).__name__}")

        if self._reader_can_produce(kind) or not self._is_pg:
            # [dialect] the guard applies to both dialects; sqlite always
            # rides query() (no native aggregation, as before).
            return await count_via_query(
                self, scope, kind, filter=filter, group_by=group_by, tenant=tenant,
            )

        d = self.documents
        where = self._build_where(filter)
        key_expr = self._json_expr(group_by) if group_by else None

        async with self._engine.connect() as conn:
            if tenant is None:
                pred = [d.c.scope == scope, d.c.kind == kind,
                        self._tenant_where(d.c.tenant, None), *where]
                if key_expr is None:
                    total = (await conn.execute(
                        sa.select(sa.func.count()).where(*pred)
                    )).scalar_one()
                    return {"total": int(total), "groups": None}
                key = key_expr.label("key")
                cnt = sa.func.count().label("cnt")
                rows = (await conn.execute(
                    sa.select(key, cnt).where(*pred).group_by(key)
                    .order_by(cnt.desc(), key.asc().nulls_last())
                )).all()
            else:
                # [dialect] DISTINCT ON is a pg-only construct — fine, this
                # whole branch is pg-only (sqlite returned above).
                inner_cols: list[Any] = [d.c.name]
                if key_expr is not None:
                    inner_cols.append(key_expr.label("key"))
                inner = (
                    sa.select(*inner_cols)
                    .distinct(d.c.name)
                    .where(d.c.scope == scope, d.c.kind == kind,
                           d.c.tenant.in_(["", tenant]), *where)
                    .order_by(d.c.name, d.c.tenant.desc())
                ).subquery("t")
                if key_expr is None:
                    total = (await conn.execute(
                        sa.select(sa.func.count()).select_from(inner)
                    )).scalar_one()
                    return {"total": int(total), "groups": None}
                cnt = sa.func.count().label("cnt")
                rows = (await conn.execute(
                    sa.select(inner.c.key, cnt).group_by(inner.c.key)
                    .order_by(cnt.desc(), inner.c.key.asc().nulls_last())
                )).all()

        groups = [{"key": r.key, "count": int(r.cnt)} for r in rows]
        return {"total": sum(g["count"] for g in groups), "groups": groups}

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
        if layer is not None:
            if layer[0] == "tenant" and tenant is None:
                tenant = layer[1]
            elif layer[0] != "tenant":
                raise NotImplementedError(
                    f"SqlAlchemySource does not support non-tenant layers in "
                    f"save_document (got layer={layer!r}). "
                    "Use save_layer_document directly."
                )
        tenant_val = tenant or ""

        # s-sync-s3 — KIND-AGNOSTIC source_files net (mirrors raw PG). Pop
        # spec.source_files BEFORE the writer runs (keeps stored content
        # bloat-free) and merge its entries after; writers that consume
        # source_files themselves leave nothing here — never double-writes.
        _net_text: dict[str, str] = {}
        _net_binary: dict[str, bytes] = {}
        _net_spec = raw.get("spec")
        if isinstance(_net_spec, dict) and _net_spec.get("source_files"):
            from dna.kernel.write.helpers import pop_source_files_as_entries
            for _e in pop_source_files_as_entries(_net_spec, kind):
                if "content_bytes" in _e:
                    _net_binary[_e["relativePath"]] = _e["content_bytes"]
                else:
                    _net_text[_e["relativePath"]] = _e["content"]

        # Writers → bundle entries (text vs bytes split; pure Python,
        # identical logic to both raw adapters).
        bundle_text: dict[str, str] | None = None
        bundle_bin: dict[str, bytes] | None = None
        from dna.kernel.bundle.handle import DictBundleHandle
        for w in self._writers:
            if w.can_write(raw):
                handle = DictBundleHandle(name, {})
                w.write(handle, raw)
                bundle_text, bundle_bin = {}, {}
                for e in handle.iter_entries(recursive=True):
                    v = handle._entries.get(e)
                    if isinstance(v, bytes):
                        bundle_bin[e] = v
                    else:
                        bundle_text[e] = handle.read_text(e)
                break

        # Merge the carried source_files net (authored bytes win on conflict
        # — same rule as raw PG).
        if _net_text or _net_binary:
            if bundle_text is None:
                bundle_text = {}
            if bundle_bin is None:
                bundle_bin = {}
            bundle_text.update(_net_text)
            bundle_bin.update(_net_binary)

        content = json.dumps(raw)  # source_files already popped → no bloat
        d, v = self.documents, self.versions
        doc_tenant = self._doc_tenant(tenant)
        spec_version = None
        if kind == "Genome":
            spec_version = ((raw.get("spec") or {}).get("version")) or None

        async with self._engine.begin() as conn:
            if spec_version:
                dup = (await conn.execute(
                    sa.select(sa.literal(1)).where(
                        v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                        self._tenant_where(v.c.tenant, tenant),
                        v.c.semver == spec_version,
                    ).limit(1)
                )).first()
                if dup is not None:
                    from dna.kernel.protocols import VersionAlreadyPublished
                    raise VersionAlreadyPublished(
                        f"Module {name!r} version {spec_version!r} already "
                        f"published to scope {scope!r} (tenant={tenant!r}). "
                        "Bump and republish."
                    )
            next_version = (await conn.execute(
                sa.select(sa.func.coalesce(sa.func.max(v.c.version), 0)).where(
                    v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                    self._tenant_where(v.c.tenant, tenant),
                )
            )).scalar_one() + 1
            await conn.execute(v.insert().values(
                scope=scope, kind=kind, name=name, content=content,
                version=next_version, is_draft=True, author=author,
                created_at=_now(), tenant=doc_tenant, semver=spec_version,
            ))
            if version_retention is not None and version_retention >= 0:
                await conn.execute(v.delete().where(
                    v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                    self._tenant_where(v.c.tenant, tenant),
                    v.c.version <= next_version - version_retention,
                ))
            if bundle_text is not None or bundle_bin is not None:
                await self._replace_bundle_entries(
                    conn, scope, kind, name, tenant_val,
                    bundle_text or {}, bundle_bin or {},
                )
            # Auto-publish — UPSERT into documents in the same transaction.
            # save_document is the publish point (raw-PG contract):
            # kernel.write_document never calls publish(), so a draft-only
            # save would leave kernel writes invisible.
            ins = self._upsert(d).values(
                scope=scope, kind=kind, name=name, content=content,
                version=next_version, updated_at=_now(), tenant=doc_tenant,
            )
            await conn.execute(ins.on_conflict_do_update(
                index_elements=self._doc_conflict_cols(),
                set_={
                    "content": ins.excluded.content,
                    "version": ins.excluded.version,
                    "updated_at": ins.excluded.updated_at,
                },
            ))
            # Eventbus (pg dialect only) — same transaction as the write.
            await self._events.emit(
                conn, scope=scope, tenant=tenant_val, kind=kind, name=name,
                op="write", doc_version=next_version, actor=author,
                write_class=write_class,
            )
        self.invalidate_view(scope)
        return str(next_version)

    async def _replace_bundle_entries(
        self, conn, scope: str, kind: str, name: str, tenant_val: str,
        text_entries: dict[str, str], bin_entries: dict[str, bytes],
    ) -> None:
        b = self.bundle_entries
        key = [
            b.c.scope == scope, b.c.kind == kind, b.c.name == name,
            b.c.tenant == tenant_val,
        ]
        if self._is_pg:
            # [dialect] preserve-binary semantics (raw-PG parity,
            # Phase 16-pre): writers can't round-trip binary blobs, so a
            # spec edit must NOT wipe them — delete only TEXT rows plus
            # the paths being re-written.
            cond = b.c.content_binary.is_(None)
            new_paths = list(text_entries.keys()) + list(bin_entries.keys())
            if new_paths:
                cond = sa.or_(cond, b.c.entry_path.in_(new_paths))
            await conn.execute(b.delete().where(*key, cond))
        else:
            # [dialect] sqlite has one flexible-affinity column — full
            # replace, exactly like the retired raw sqlite adapter did.
            await conn.execute(b.delete().where(*key))
        ts = _now()
        for entry_path, body in {**text_entries, **bin_entries}.items():
            values: dict[str, Any] = dict(
                scope=scope, kind=kind, name=name, entry_path=entry_path,
                updated_at=ts, tenant=tenant_val,
            )
            set_: dict[str, Any] = {"updated_at": ts}
            if self._is_pg and isinstance(body, bytes):
                # [dialect] pg routes bytes to content_binary.
                values.update(content="", content_binary=body)
                set_["content_binary"] = body
            else:
                values.update(content=body)
                set_["content"] = body
            ins = self._upsert(b).values(**values)
            await conn.execute(ins.on_conflict_do_update(
                index_elements=["scope", "kind", "name", "entry_path", "tenant"],
                set_=set_,
            ))

    async def publish(
        self, scope: str, kind: str, name: str, *, tenant: str | None = None,
    ) -> str:
        v, d = self.versions, self.documents
        tenant_val = tenant or ""
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                sa.select(v.c.id, v.c.content, v.c.version).where(
                    v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                    self._tenant_where(v.c.tenant, tenant),
                    v.c.is_draft.is_(True),
                ).order_by(v.c.version.desc()).limit(1)
            )).first()
            if row is None:
                raise ValueError("no_draft")
            ins = self._upsert(d).values(
                scope=scope, kind=kind, name=name, content=row.content,
                version=row.version, updated_at=_now(),
                tenant=self._doc_tenant(tenant),
            )
            await conn.execute(ins.on_conflict_do_update(
                index_elements=self._doc_conflict_cols(),
                set_={
                    "content": ins.excluded.content,
                    "version": ins.excluded.version,
                    "updated_at": ins.excluded.updated_at,
                },
            ))
            await conn.execute(
                v.update().where(v.c.id == row.id).values(is_draft=False)
            )
            await self._events.emit(
                conn, scope=scope, tenant=tenant_val, kind=kind, name=name,
                op="write", doc_version=row.version,
            )
        self.invalidate_view(scope)
        return str(row.version)

    async def delete_document(
        self, scope: str, kind: str, name: str,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
    ) -> None:
        if layer is not None:
            if layer[0] == "tenant" and tenant is None:
                tenant = layer[1]
            elif layer[0] != "tenant":
                raise NotImplementedError(
                    f"SqlAlchemySource does not support non-tenant layers in "
                    f"delete_document (got layer={layer!r}). "
                    "Use delete_layer_document directly."
                )
        d, v, b = self.documents, self.versions, self.bundle_entries
        tenant_val = tenant or ""
        async with self._engine.begin() as conn:
            key = lambda t: [  # noqa: E731
                t.c.scope == scope, t.c.kind == kind, t.c.name == name,
            ]
            row = (await conn.execute(
                sa.select(sa.literal(1)).where(
                    *key(d), self._tenant_where(d.c.tenant, tenant),
                ).limit(1)
            )).first()
            if row is None:
                raise ValueError("not_found")
            await conn.execute(d.delete().where(
                *key(d), self._tenant_where(d.c.tenant, tenant)))
            await conn.execute(v.delete().where(
                *key(v), self._tenant_where(v.c.tenant, tenant)))
            await conn.execute(b.delete().where(
                *key(b), b.c.tenant == tenant_val))
            # doc_version=0 is the documented sentinel for delete.
            await self._events.emit(
                conn, scope=scope, tenant=tenant_val, kind=kind, name=name,
                op="delete", doc_version=0,
            )
        self.invalidate_view(scope)

    async def save_manifest(self, scope: str, manifest: dict) -> str:
        kind = manifest.get("kind") or "Genome"
        return await self.save_document(
            scope, kind, manifest.get("metadata", {}).get("name", scope), manifest,
        )

    # ------------------------------------------------------------------
    # Layer operations (non-tenant layers → legacy layer_documents table)
    # ------------------------------------------------------------------

    async def save_layer_document(
        self, scope: str, layer_id: str, layer_value: str,
        kind: str, name: str, raw: dict,
    ) -> None:
        # Tenant overlays live in documents.tenant (Phase 8a) — route
        # through save_document so save+load round-trip (raw-PG parity).
        if layer_id == "tenant":
            return await self.save_document(
                scope, kind, name, raw, tenant=layer_value,
            )
        ld = self.layer_documents
        ins = self._upsert(ld).values(
            scope=scope, layer_id=layer_id, layer_value=layer_value,
            kind=kind, name=name, content=json.dumps(raw), updated_at=_now(),
        )
        async with self._engine.begin() as conn:
            await conn.execute(ins.on_conflict_do_update(
                index_elements=["scope", "layer_id", "layer_value", "kind", "name"],
                set_={
                    "content": ins.excluded.content,
                    "updated_at": ins.excluded.updated_at,
                },
            ))

    async def delete_layer_document(
        self, scope: str, layer_id: str, layer_value: str,
        kind: str, name: str,
    ) -> None:
        ld = self.layer_documents
        async with self._engine.begin() as conn:
            await conn.execute(ld.delete().where(
                ld.c.scope == scope, ld.c.layer_id == layer_id,
                ld.c.layer_value == layer_value,
                ld.c.kind == kind, ld.c.name == name,
            ))

    async def list_layers(self, scope: str) -> list[dict[str, str]]:
        """Legacy layer_documents entries merged with the tenant overlays
        observed in documents.tenant (raw-PG parity)."""
        ld = self.layer_documents
        async with self._engine.connect() as conn:
            legacy = (await conn.execute(
                sa.select(ld.c.layer_id, ld.c.layer_value).distinct().where(
                    ld.c.scope == scope,
                )
            )).all()
        tenants = await self.list_tenants(scope)
        out = [{"layer_id": r.layer_id, "layer_value": r.layer_value}
               for r in legacy]
        out.extend({"layer_id": "tenant", "layer_value": t} for t in tenants)
        out.sort(key=lambda x: (x["layer_id"], x["layer_value"]))
        return out

    # ------------------------------------------------------------------
    # Versions / drafts / scopes
    # ------------------------------------------------------------------

    async def list_versions(self, scope: str, kind: str, name: str) -> list[dict]:
        v = self.versions
        async with self._engine.connect() as conn:
            rows = (await conn.execute(
                sa.select(v.c.id, v.c.version, v.c.is_draft, v.c.author,
                          v.c.created_at).where(
                    v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                ).order_by(v.c.version.desc())
            )).mappings().all()
        return [dict(r) for r in rows]

    async def get_version(
        self, scope: str, kind: str, name: str, version_id: str,
    ) -> dict:
        v = self.versions
        async with self._engine.connect() as conn:
            row = (await conn.execute(
                sa.select(v).where(
                    v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                    v.c.version == int(version_id),
                )
            )).mappings().first()
        if row is None:
            raise ValueError("version_not_found")
        result = dict(row)
        result["content"] = json.loads(result["content"])
        return result

    async def load_drafts(self, scope: str) -> list[dict]:
        v = self.versions
        latest = sa.select(
            v.c.kind, v.c.name, sa.func.max(v.c.version).label("max_v"),
        ).where(
            v.c.scope == scope, v.c.is_draft.is_(True),
        ).group_by(v.c.kind, v.c.name).subquery()
        stmt = sa.select(
            v.c.kind, v.c.name, v.c.content, v.c.version, v.c.created_at,
        ).join(latest, sa.and_(
            v.c.kind == latest.c.kind, v.c.name == latest.c.name,
            v.c.version == latest.c.max_v,
        )).where(v.c.scope == scope, v.c.is_draft.is_(True))
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]

    async def list_scopes(self) -> list[str]:
        d = self.documents
        async with self._engine.connect() as conn:
            rows = (await conn.execute(
                sa.select(d.c.scope).distinct().order_by(d.c.scope)
            )).all()
        return [r.scope for r in rows]

    # ------------------------------------------------------------------
    # Phase 10g — Genome catalog version surface (raw-adapter parity)
    # ------------------------------------------------------------------

    async def list_module_versions(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semver releases of the scope Genome published to (scope, tenant).

        Each entry: ``{version, deprecated, deprecated_message,
        published_at}``, sorted by created_at ASC. Rows with
        ``semver IS NULL`` (unversioned publishes) never enter the
        catalog timeline. Dialect-FREE — one Core body replaces the two
        divergent raw copies.
        """
        v = self.versions
        stmt = sa.select(v.c.semver, v.c.content, v.c.created_at).where(
            v.c.scope == scope, v.c.kind == "Genome", v.c.name == scope,
            self._tenant_where(v.c.tenant, tenant),
            v.c.semver.isnot(None),
        ).order_by(v.c.created_at.asc())
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                spec = json.loads(r.content).get("spec") or {}
            except Exception:  # noqa: BLE001
                spec = {}
            out.append({
                "version": r.semver,
                "deprecated": bool(spec.get("deprecated", False)),
                "deprecated_message": spec.get("deprecated_message"),
                "published_at": r.created_at,
            })
        return out

    async def get_module_version(
        self, scope: str, version: str, *, tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """The frozen Genome manifest for ``scope@version`` (exact archive
        row — no tenant fallback, by design)."""
        v = self.versions
        async with self._engine.connect() as conn:
            row = (await conn.execute(
                sa.select(v.c.content).where(
                    v.c.scope == scope, v.c.kind == "Genome", v.c.name == scope,
                    self._tenant_where(v.c.tenant, tenant),
                    v.c.semver == version,
                ).limit(1)
            )).first()
        if row is None:
            return None
        try:
            return json.loads(row.content)
        except Exception:  # noqa: BLE001
            return None

    async def deprecate_module_version(
        self, scope: str, version: str, *,
        tenant: str | None = None, message: str | None = None,
    ) -> bool:
        """Flip ``spec.deprecated=true`` on the archived row in-place;
        mirror to the latest ``documents`` pointer when it matches."""
        v, d = self.versions, self.documents
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                sa.select(v.c.content).where(
                    v.c.scope == scope, v.c.kind == "Genome", v.c.name == scope,
                    self._tenant_where(v.c.tenant, tenant),
                    v.c.semver == version,
                ).limit(1)
            )).first()
            if row is None:
                return False
            raw = json.loads(row.content)
            spec = raw.setdefault("spec", {})
            spec["deprecated"] = True
            if message:
                spec["deprecated_message"] = message
            new_content = json.dumps(raw)
            await conn.execute(v.update().where(
                v.c.scope == scope, v.c.kind == "Genome", v.c.name == scope,
                self._tenant_where(v.c.tenant, tenant),
                v.c.semver == version,
            ).values(content=new_content))
            latest = (await conn.execute(
                sa.select(d.c.content).where(
                    d.c.scope == scope, d.c.kind == "Genome", d.c.name == scope,
                    self._tenant_where(d.c.tenant, tenant),
                )
            )).first()
            if latest is not None:
                try:
                    cur_spec = json.loads(latest.content).get("spec") or {}
                    if cur_spec.get("version") == version:
                        await conn.execute(d.update().where(
                            d.c.scope == scope, d.c.kind == "Genome",
                            d.c.name == scope,
                            self._tenant_where(d.c.tenant, tenant),
                        ).values(content=new_content))
                except Exception:  # noqa: BLE001
                    pass
        self.invalidate_view(scope)
        return True

    # ------------------------------------------------------------------
    # Bundle entries
    # ------------------------------------------------------------------

    async def fetch_bundle_entry(
        self, scope: str, container: str, name: str, entry: str,
        *, tenant: str | None = None, kind: str | None = None,
    ) -> bytes:
        b = self.bundle_entries
        kind_key = kind or container
        candidates = ([tenant] if tenant else []) + [""]
        cols = [b.c.content]
        if self._is_pg:
            cols.append(b.c.content_binary)  # [dialect]
        async with self._engine.connect() as conn:
            for tenant_val in candidates:
                row = (await conn.execute(
                    sa.select(*cols).where(
                        b.c.scope == scope, b.c.kind == kind_key,
                        b.c.name == name, b.c.entry_path == entry,
                        b.c.tenant == tenant_val,
                    ).limit(1)
                )).first()
                if row is None:
                    continue
                if self._is_pg and row.content_binary:  # [dialect]
                    return bytes(row.content_binary)
                content = row.content
                if isinstance(content, str):
                    return content.encode("utf-8")
                return bytes(content or b"")
        raise FileNotFoundError(
            f"Bundle entry not found: scope={scope!r} container={container!r} "
            f"kind={kind!r} name={name!r} entry={entry!r} tenant={tenant!r}"
        )

    async def write_bundle_entry(
        self, scope: str, container: str, name: str, entry: str,
        content: bytes | str,
        *, tenant: str | None = None, kind: str | None = None,
    ) -> None:
        b = self.bundle_entries
        values: dict[str, Any] = dict(
            scope=scope, kind=(kind or container), name=name, entry_path=entry,
            updated_at=_now(), tenant=(tenant or ""),
        )
        set_: dict[str, Any]
        if self._is_pg:
            # [dialect] pg: text → content, bytes → content_binary.
            is_text = isinstance(content, str)
            values.update(
                content=content if is_text else "",
                content_binary=None if is_text else content,
            )
        else:
            # [dialect] sqlite: single flexible-affinity column.
            values.update(content=content)
        ins = self._upsert(b).values(**values)
        set_ = {
            "content": ins.excluded.content,
            "updated_at": ins.excluded.updated_at,
        }
        if self._is_pg:
            set_["content_binary"] = ins.excluded.content_binary  # [dialect]
        async with self._engine.begin() as conn:
            await conn.execute(ins.on_conflict_do_update(
                index_elements=["scope", "kind", "name", "entry_path", "tenant"],
                set_=set_,
            ))
        self.invalidate_view(scope)

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    def capabilities(self) -> "SourceCapabilities":
        from dna.kernel.capabilities import (
            DELETE_OPTIONAL_KWARGS,
            SAVE_OPTIONAL_KWARGS,
            SourceCapabilities,
        )
        return SourceCapabilities(
            source="sqlalchemy",
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
