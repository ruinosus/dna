"""SqlAlchemySource — ONE adapter, TWO dialects, SAME tables (production).

SQLAlchemy Core 2.x async implementation of SourcePort + WritableSourcePort
against the EXISTING adapter schemas (promoted from the i-216 spike by
``s-sqlalchemy-source-production``):

  - sqlite  (aiosqlite):  ``instances`` / ``versions`` / ``bundle_entries``
    / ``layer_instances`` — byte-compatible with DBs built by the retired
    raw sqlite adapter, including the ``schema_migrations`` control table.
  - postgresql (asyncpg): ``{schema}.dna_instances`` / ``dna_versions`` /
    ``dna_bundle_entries`` / ``dna_layer_instances`` / ``dna_outbox`` /
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
    canonical ``instances.content`` row instead of silently serving an
    anemic spec (D-B hardening, mirrors raw PG).
  - **``spec.source_files`` net** in ``save_instance`` (kind-agnostic,
    s-sync-s3): carried bundle entries persist for every bundle kind
    whose writer doesn't consume them itself.
  - **Auto-publish**: ``save_instance`` UPSERTs ``instances`` in the same
    transaction (the raw-PG contract — ``kernel.write_instance`` treats
    save as the publish point and never calls ``publish()``).
  - **Genome catalog + layer surfaces**: ``list_module_versions`` /
    ``get_module_version`` / ``deprecate_module_version`` and
    ``save_layer_instance`` / ``delete_layer_instance`` / ``list_layers``
    / ``list_tenants`` — full parity with the raw adapters.

**The row key carries the Kind's identity** (revision
``0003_api_version``): a Kind is ``(apiVersion, kind)``, so ``instances``,
``versions`` and ``bundle_entries`` key on ``(scope, kind, api_version,
name[, tenant])``. Two workspaces may each declare a ``Deal`` under their
own namespace, and before the column the second save simply OVERWROTE the
first. Writes always know their apiVersion (they hold the instance);
reads take it as an OPTIONAL pin, and omitting it matches any Kind —
exactly the pre-column behaviour, which is why every shipped Kind (each
unique by name in its scope) resolves identically. Unpinned MUTATIONS on
a name that really does resolve to two Kinds are refused rather than
guessed (``_refuse_ambiguous_name``). ``''`` in the column is not an
apiVersion: it records that the stored instance declares none.

Honesty markers: every place the two dialects could NOT be expressed as
one Core construct is tagged ``# [dialect]``. Known inherited limitation:
the SQLite ``instances`` PK lacks ``tenant`` (i-092) — a tenant overlay
publish clobbers the base row. Schema debt, not a Core limitation (the
conformance matrix carries the strict xfail), and deliberately untouched
by 0003: widening one key at a time is what makes each change auditable.
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

#: ``bundle_entries`` PK — identical on both dialects (revision 0003 added
#: ``api_version``; a bundle entry belongs to an instance, hence to its Kind).
_BUNDLE_CONFLICT_COLS = [
    "scope", "kind", "api_version", "name", "entry_path", "tenant",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_name(raw: dict) -> str | None:
    meta = raw.get("metadata") or {}
    return meta.get("name") or raw.get("name")


def _doc_api_version(raw: dict) -> str:
    """The apiVersion the instance DECLARES, or ``''`` when it declares none.

    ``''`` is not a default apiVersion and is never treated as one: it records
    that the stored instance states nothing. Reads that do not pin an
    apiVersion match it exactly as they matched everything before the column
    existed.
    """
    value = raw.get("apiVersion")
    return value if isinstance(value, str) else ""


def _api_version_unknown(col: Any) -> Any:
    """SQL for "this apiVersion column says nothing".

    TWO sentinels, and they are not a choice this function made — they are the
    two the schema already has. ``NULL`` is ``to_api_version``'s (nullable, no
    default, i-110.3); ``''`` is ``from_api_version``'s (NOT NULL,
    ``server_default ''``, revision 0006), and the empty string is what every
    row written by a caller that passed no ``api_version=`` carries. A join
    that remembered only one of them would drop hops out of exactly the rows
    that pre-date the feature — which is the loss the tolerance exists to
    prevent.
    """
    return sa.or_(col.is_(None), col == sa.literal(""))


def _same_api_family(a: Any, b: Any) -> Any:
    """SQL for "these two edge ends can be the same Kind" (i-110.3).

    Deliberately PERMISSIVE, and the asymmetry is the whole design: it excludes
    a hop only when both ends state an apiVersion AND the two differ. Anything
    unknown passes, so the clause can never remove a hop the old ``(kind,
    name)`` join produced from data it could not tell apart — it only removes
    the ones it now CAN tell apart, and those were wrong.

    Written as a function rather than inline so the two directions of
    :meth:`SqlAlchemySource.traverse_edges` cannot drift into two rules.
    """
    return sa.or_(_api_version_unknown(a), _api_version_unknown(b), a == b)


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
        # [dialect] base-layer tenant sentinel on instances/versions:
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
        # [dialect] WORLD time is a pg-only column (revision 0010): sqlite has
        # no range type, no GiST and no EXCLUDE constraint, so it gets neither
        # the column nor the invariant. Declared as an ATTRIBUTE, not derived
        # from the method, because ``load_one_valid_at`` is defined on this
        # class for BOTH dialects (on sqlite it refuses) — a reflection oracle
        # that probed the method would certify a declaration that lies. Same
        # shape, same reason, as ``supports_cross_process_invalidation`` above.
        self.supports_valid_time = self._is_pg

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
        self.instances = tables.instances
        self.versions = tables.versions
        self.bundle_entries = tables.bundle_entries
        self.layer_instances = tables.layer_instances
        self.edges = tables.edges
        if self._is_pg:
            self.outbox = tables.outbox
            self.versions_seq = tables.versions_seq

    # ------------------------------------------------------------------
    # Dialect seams (each is [dialect] evidence)
    # ------------------------------------------------------------------

    def _doc_tenant(self, tenant: str | None) -> str | None:
        """Stored tenant value for instances/versions rows."""
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
        # [dialect] instances PK: pg = (scope,kind,api_version,name,tenant);
        # sqlite = (scope,kind,api_version,name) — i-092 lives HERE, in the
        # schema. ``api_version`` is in the key on both since 0003: a Kind is
        # identified by (apiVersion, kind), so two workspaces' `Deal`s must not
        # arbitrate for the same row.
        return ["scope", "kind", "api_version", "name", "tenant"] if self._is_pg \
            else ["scope", "kind", "api_version", "name"]

    @staticmethod
    def _api_version_where(
        col: sa.Column, api_version: str | None,
    ) -> list[sa.ColumnElement]:
        """Pin a query to ONE Kind, or leave it as wide as it always was.

        ``None`` means the caller has no apiVersion in hand and gets the
        pre-column behaviour: match the name under any Kind. That is what keeps
        every shipped Kind — all of which are unique by name in their scope —
        resolving byte-identically. A value pins the row EXACTLY.
        """
        return [] if api_version is None else [col == api_version]

    async def _refuse_ambiguous_name(
        self, conn, table: sa.Table, scope: str, kind: str, name: str,
        tenant: str | None, api_version: str | None, *, verb: str,
        extra: list[sa.ColumnElement] | None = None,
    ) -> None:
        """Refuse an unpinned MUTATION whose name resolves to two Kinds.

        Before ``api_version`` was part of the key the table could hold only one
        row per name, so an unpinned delete or publish was unambiguous by
        construction. Now that both rows can exist, an unpinned mutation would
        have to either pick one (a delete that misses, a publish that promotes
        the wrong instance) or take both (a delete that reaches into a Kind the
        caller never named). Neither is defensible, so the caller is told to say
        which — the same refusal the generic instance surface already makes for
        an ambiguous bare Kind name (``dna.application.instances``).

        READS are deliberately not covered: a read that matches both is a
        widened answer, not a wrong one, and the caller can tell the two apart
        by the ``apiVersion`` each instance carries.
        """
        if api_version is not None:
            return
        found = (await conn.execute(
            sa.select(table.c.api_version).distinct().where(
                table.c.scope == scope, table.c.kind == kind,
                table.c.name == name,
                self._tenant_where(table.c.tenant, tenant),
                *(extra or []),
            )
        )).scalars().all()
        if len(found) > 1:
            raise ValueError(
                f"ambiguous: {kind} {name!r} in scope {scope!r} "
                f"(tenant={tenant!r}) exists under {len(found)} apiVersions "
                f"({', '.join(sorted(found))}). A Kind is identified by "
                f"(apiVersion, kind), so this {verb} cannot tell which one you "
                f"mean — pass api_version=... to say."
            )

    def _json_expr(self, path: str) -> sa.ColumnElement:
        """Dotted field path → SQL expression over instances.content.

        Same path vocabulary as ``_pg_field_expr`` / ``_sqlite_field_expr``.
        """
        from dna.kernel.protocols import QueryError

        if not path or any(c in path for c in (";", "'", "\"", "(", ")")):
            raise QueryError(f"invalid field path: {path!r}")
        if path in ("name", "metadata.name"):
            return self.instances.c.name
        if path == "kind":
            return self.instances.c.kind
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
            expr: Any = sa.cast(self.instances.c.content, JSONB)
            for seg in segments[:-1]:
                expr = expr[seg]
            return expr[segments[-1]].astext
        # [dialect] sqlite: json_extract returns the NATIVE json type
        # (int stays int) — no cast dance, but a different function.
        return sa.func.json_extract(
            self.instances.c.content, "$." + ".".join(segments),
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
        # through THIS source invalidate directly (see save_instance);
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
        d = self.instances
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
        d, b = self.instances, self.bundle_entries
        entry_cols = [
            b.c.kind, b.c.api_version, b.c.name, b.c.entry_path, b.c.content,
        ]
        if self._is_pg:
            entry_cols.append(b.c.content_binary)  # [dialect]
        async with self._engine.connect() as conn:
            doc_rows = (await conn.execute(
                sa.select(d.c.kind, d.c.api_version, d.c.name, d.c.content).where(
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
        # Keyed by (kind, apiVersion, name): two Kinds sharing a name have
        # separate entry sets, and merging them would hand one Kind's bundle to
        # the other's reader.
        entries_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        for e in entry_rows:
            cb = e.content_binary if self._is_pg else None
            val: str | bytes = bytes(cb) if cb else e.content
            entries_by_key.setdefault(
                (e.kind, e.api_version, e.name), {},
            )[e.entry_path] = val

        from dna.kernel.bundle.handle import DictBundleHandle
        out: list[dict[str, Any]] = []
        for r in doc_rows:
            entries = entries_by_key.get((r.kind, r.api_version, r.name))
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
        ld = self.layer_instances
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
        d = self.instances
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

    async def find_instances_by_id_prefix(
        self, prefix: str, *, scope: str | None = None,
        tenant: str | None = None, limit: int = 64,
    ) -> "list[Any]":
        """Every instance whose ``id`` starts with ``prefix`` (i-114).

        Candidates only — this method does NOT decide. Arbitration lives in
        ``dna.kernel.identity.resolve_unique_prefix``, in one place, because two
        stores that each rounded the tie their own way would disagree exactly
        when it mattered.

        ``limit`` is a ceiling on how much ambiguity is worth reporting, not a
        page size: any prefix matching more than a handful is already a refusal,
        and the caller only needs enough matches to say so with examples. It is
        deliberately more than 1 — stopping at the first match would turn
        "ambiguous" into "resolved", which is the one outcome this feature
        exists to make impossible.

        ``scope=None`` searches every scope, which is right: an id is unique
        across the whole store by construction, and a caller who holds an id
        usually does NOT know which scope it lives in — that is most of what an
        id is for.
        """
        from dna.kernel.identity import InstanceRef  # noqa: PLC0415
        d = self.instances
        stmt = sa.select(
            d.c.id, d.c.scope, d.c.kind, d.c.api_version, d.c.name, d.c.tenant,
        ).where(
            d.c.id.is_not(None),
            d.c.id.like(prefix.replace("\\", "\\\\")
                              .replace("%", "\\%")
                              .replace("_", "\\_") + "%", escape="\\"),
        )
        if scope is not None:
            stmt = stmt.where(d.c.scope == scope)
        if tenant is not None:
            stmt = stmt.where(self._tenant_where(d.c.tenant, tenant))
        stmt = stmt.order_by(d.c.id).limit(limit)
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        return [
            InstanceRef(
                id=r.id, scope=r.scope, kind=r.kind,
                api_version=r.api_version or "", name=r.name,
                tenant=r.tenant or None,
            )
            for r in rows
        ]

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers: list | None = None,
        tenant: str | None = None,
        api_version: str | None = None,
    ) -> dict[str, Any] | None:
        """Load ONE instance with its bundle.

        ``api_version`` resolves the Kind EXACTLY. Two workspaces may each
        declare a ``Deal`` under their own namespace, and since revision 0003
        both of their instances can really be in the table at once — so a
        bare-name lookup answers with whichever row the database returns first.
        Passing the apiVersion makes the answer the caller's own Kind, and a
        pin that matches nothing returns ``None`` rather than someone else's
        instance. Omitting it keeps the pre-column behaviour exactly.
        """
        async with self._engine.connect() as conn:
            return await self._load_one_on(
                conn, scope, kind, name,
                readers=readers, tenant=tenant, api_version=api_version,
            )

    async def _load_one_on(
        self, conn, scope: str, kind: str, name: str, *,
        readers: list | None = None,
        tenant: str | None = None,
        api_version: str | None = None,
    ) -> dict[str, Any] | None:
        """:meth:`load_one`'s body, against a CALLER-SUPPLIED connection.

        Extracted (i-083) so the ``if_match`` guard in :meth:`save_instance` can
        read the stored instance INSIDE its own write transaction — which is
        what makes the guard a real compare-and-swap on this adapter rather than
        a narrowed race.

        Sharing the body is not tidiness. The guard compares a digest of the
        stored ``spec`` against a token the caller derived from a READ, so the
        two must reconstruct the instance identically. A bundle-format Kind
        (KindDefinition, Agent, Skill) does not round-trip through the
        ``content`` column alone — the readers re-assemble it from
        ``bundle_entries`` — so a guard that hashed ``json.loads(row.content)``
        would disagree with every read of those Kinds and refuse writes that were
        perfectly honest. One body, one answer to "what is stored".
        """
        effective_readers = list(self._readers)
        for r in (readers or []):
            if r not in effective_readers:
                effective_readers.append(r)
        d, b = self.instances, self.bundle_entries
        entry_cols = [b.c.entry_path, b.c.content]
        if self._is_pg:
            entry_cols.append(b.c.content_binary)  # [dialect]
        tenant_candidates: list[str | None] = [tenant, None] if tenant else [None]
        for t in tenant_candidates:
            row = (await conn.execute(
                sa.select(d.c.content, d.c.api_version).where(
                    d.c.scope == scope, d.c.kind == kind, d.c.name == name,
                    *self._api_version_where(d.c.api_version, api_version),
                    self._tenant_where(d.c.tenant, t),
                )
            )).first()
            if row is None:
                continue
            # The entries belong to the instance just found — key them on
            # ITS apiVersion, never on the (possibly absent) argument.
            erows = (await conn.execute(
                sa.select(*entry_cols).where(
                    b.c.scope == scope, b.c.kind == kind, b.c.name == name,
                    b.c.api_version == row.api_version,
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
        """Distinct non-base tenants observed in instances (optionally
        narrowed to one scope) — parity with FS + raw PG."""
        d = self.instances
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
        d = self.instances

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

        d = self.instances
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

    async def save_instance(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None = None,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        write_class: str = "substantive",
        version_retention: int | None = None,
        if_absent: bool = False,
        if_match: str | None = None,
        edges: "list[Any] | None" = None,
    ) -> str:
        if layer is not None:
            if layer[0] == "tenant" and tenant is None:
                tenant = layer[1]
            elif layer[0] != "tenant":
                raise NotImplementedError(
                    f"SqlAlchemySource does not support non-tenant layers in "
                    f"save_instance (got layer={layer!r}). "
                    "Use save_layer_instance directly."
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
        # i-114 — the ``id`` column is a PROJECTION of ``metadata.id``, which
        # the kernel's write pipeline stamped before handing the envelope down.
        # Read here, never minted: an adapter that invented an id would give
        # the same instance a second identity on any path that reaches storage
        # by another route, and two identities is strictly worse than none.
        from dna.kernel.identity import instance_id_of
        instance_id = instance_id_of(raw)
        # [dialect] WORLD time — the same PROJECTION discipline as ``id`` one
        # line up, applied to the other axis. ``spec.valid_from`` /
        # ``spec.valid_to`` are the authored fact and stay authoritative; the
        # column is derived from them on EVERY save, so there is no second way
        # to set it and no way for the two to disagree.
        #
        # ⭐ This is why the column is not a capability without a door: nothing
        # new has to learn to write it. ``dna.memory.remember`` already seeds
        # ``valid_from`` and ``dna.memory.forget`` already writes ``valid_to``
        # — both reachable from the MCP face, the CLI and a raw
        # ``write_instance`` on any Kind that carries the fields — and every
        # one of those writes lands here. Measured on the founder's store
        # (06/08/2026): 14 instances already carry a lower bound and 2 a closed
        # upper bound, so the column is populated by the first save of each.
        valid_at = self._valid_at_values(raw)
        d, v = self.instances, self.versions
        doc_tenant = self._doc_tenant(tenant)
        # The write HOLDS the instance, so it always knows the exact Kind —
        # no port kwarg needed and no registry lookup. Every key below is
        # widened with it so a `Deal` in one namespace cannot overwrite a
        # `Deal` in another.
        api_version = _doc_api_version(raw)
        spec_version = None
        if kind == "Genome":
            spec_version = ((raw.get("spec") or {}).get("version")) or None

        async with self._engine.begin() as conn:
            if if_match is not None:
                # i-083 — the GUARDED update, and on this adapter it is a real
                # compare-and-swap: the read happens on THIS connection, inside
                # the transaction the write below commits, so nothing can slip
                # between the check and the upsert. (The filesystem adapter has
                # no transaction to hold across the pair and says so.)
                #
                # FIRST in the transaction, before the ``if_absent`` claim and
                # before any version row is computed, so a refusal rolls back
                # having touched nothing.
                #
                # Pinned to the instance's OWN ``api_version``: this write
                # upserts the row keyed on it, so that row is precisely the one
                # the guard must ask about. Unpinned, a name shared by two
                # namespaces could compare against a neighbour's instance and
                # pass — which is the class of confusion the apiVersion column
                # exists to end.
                from dna.kernel.etag import check_if_match
                check_if_match(
                    await self._load_one_on(
                        conn, scope, kind, name,
                        tenant=tenant, api_version=api_version,
                    ),
                    if_match, scope=scope, kind=kind, name=name, tenant=tenant,
                )
            if if_absent:
                # The ATOMIC claim: INSERT the instances row FIRST, inside this
                # transaction, letting the composite primary key
                # (tenant, scope, kind, name) arbitrate. ``ON CONFLICT DO
                # NOTHING`` + rowcount is one round trip that both tests and
                # takes the name — a SELECT-then-INSERT would leave exactly the
                # window two concurrent creates squeeze through. The row is
                # overwritten with the real content by the upsert at the end of
                # this same transaction, so nothing observes the placeholder.
                claim = self._upsert(d).values(
                    scope=scope, kind=kind, api_version=api_version, name=name,
                    content=content, id=instance_id,
                    version=0, updated_at=_now(), tenant=doc_tenant,
                    # The placeholder carries the REAL window, not the default.
                    # An ``if_absent`` claim that inserted the unbounded default
                    # and left the final upsert to correct it would, for the
                    # duration of this transaction, assert a validity period the
                    # instance never declared — and the EXCLUDE constraint judges
                    # rows as they are INSERTED, so a claim under the wrong window
                    # can be refused for overlapping something it does not.
                    **valid_at,
                ).on_conflict_do_nothing(
                    index_elements=self._doc_conflict_cols(),
                )
                claimed = await conn.execute(claim)
                if claimed.rowcount == 0:
                    from dna.kernel.errors import InstanceNameTaken
                    raise InstanceNameTaken(
                        f"{kind} {name!r} already exists in scope {scope!r} "
                        f"(tenant={tenant!r}) — an if_absent write refuses to "
                        f"replace it. Pick a free name, or use an update verb "
                        f"if you meant to change the instance that is there."
                    )
            if spec_version:
                dup = (await conn.execute(
                    sa.select(sa.literal(1)).where(
                        v.c.scope == scope, v.c.kind == kind,
                        v.c.api_version == api_version, v.c.name == name,
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
                    v.c.scope == scope, v.c.kind == kind,
                    v.c.api_version == api_version, v.c.name == name,
                    self._tenant_where(v.c.tenant, tenant),
                )
            )).scalar_one() + 1
            await conn.execute(v.insert().values(
                scope=scope, kind=kind, api_version=api_version, name=name,
                content=content,
                version=next_version, is_draft=True, author=author,
                created_at=_now(), tenant=doc_tenant, semver=spec_version,
            ))
            if version_retention is not None and version_retention >= 0:
                await conn.execute(v.delete().where(
                    v.c.scope == scope, v.c.kind == kind,
                    v.c.api_version == api_version, v.c.name == name,
                    self._tenant_where(v.c.tenant, tenant),
                    v.c.version <= next_version - version_retention,
                ))
            if bundle_text is not None or bundle_bin is not None:
                await self._replace_bundle_entries(
                    conn, scope, kind, api_version, name, tenant_val,
                    bundle_text or {}, bundle_bin or {},
                )
            # Auto-publish — UPSERT into instances in the same transaction.
            # save_instance is the publish point (raw-PG contract):
            # kernel.write_instance never calls publish(), so a draft-only
            # save would leave kernel writes invisible.
            ins = self._upsert(d).values(
                scope=scope, kind=kind, api_version=api_version, name=name,
                content=content, id=instance_id,
                version=next_version, updated_at=_now(), tenant=doc_tenant,
                **valid_at,
            )
            await conn.execute(ins.on_conflict_do_update(
                index_elements=self._doc_conflict_cols(),
                set_={
                    "content": ins.excluded.content,
                    "version": ins.excluded.version,
                    "updated_at": ins.excluded.updated_at,
                    # Plain assignment, NOT the COALESCE the id gets below, and
                    # the asymmetry is the point. An id is minted once and never
                    # changes, so a write that omits it is a caller that does not
                    # know it, and keeping the stored value is the only
                    # non-destructive reading. A validity window is the OPPOSITE:
                    # it is re-derived from ``spec`` on every save, so an
                    # instance whose ``valid_to`` was cleared by an authored edit
                    # must see the column reopen. COALESCE here would make
                    # ``forget`` permanent and un-undoable at the column level
                    # while the JSON said otherwise — two sources of truth for
                    # one fact, disagreeing silently.
                    **({"valid_at": ins.excluded.valid_at} if valid_at else {}),
                    # COALESCE and not a plain assignment: a write that arrives
                    # WITHOUT an id (a caller below the kernel, a legacy path,
                    # an adapter test) must not erase the identity the row
                    # already holds. Losing an id is unrecoverable — every
                    # ``dna_edges.to_id`` naming it becomes a dangling pointer
                    # to an object that still exists. Keeping a stale one is
                    # not even possible: the id never changes.
                    "id": sa.func.coalesce(ins.excluded.id, d.c.id),
                },
            ))
            # The DERIVED reference graph — same transaction as the write, for
            # the same reason the outbox below is: the instance and the facts
            # about it must become true together. ``None`` means the kernel had
            # nothing trustworthy to say (producer off, or a read failed
            # mid-resolution) and the stored edges are left ALONE — an old,
            # known edge set beats a fresh, partial one.
            if edges is not None:
                await self._replace_edges(
                    conn, scope, kind, api_version, name, tenant_val,
                    edges, next_version,
                )
            # Eventbus (pg dialect only) — same transaction as the write.
            await self._events.emit(
                conn, scope=scope, tenant=tenant_val, kind=kind, name=name,
                op="write", doc_version=next_version, actor=author,
                write_class=write_class,
            )
        self.invalidate_view(scope)
        return str(next_version)

    # ------------------------------------------------------------------
    # The derived reference graph (spec-grafo-1)
    # ------------------------------------------------------------------

    def _edge_now(self) -> Any:
        """[dialect] pg stores a real ``TIMESTAMPTZ``; sqlite the ISO text its
        other tables use.

        A Python value on BOTH, not ``sa.func.now()`` on pg: the insert is an
        executemany over a list of parameter dicts, and asyncpg binds those as
        VALUES — a SQL function object handed to it is rejected outright
        (``expected a datetime, got 'now'``). Found by running these tests on
        the second dialect; SQLite would never have said a word.
        """
        return datetime.now(timezone.utc) if self._is_pg else _now()

    async def _replace_edges(
        self, conn, scope: str, kind: str, api_version: str, name: str,
        tenant_val: str, edges: "list[Any]", from_version: int,
    ) -> None:
        """DELETE this instance's outgoing edges, then INSERT the new set.

        Idempotent by construction — no diff, no leftovers, no trigger. The
        DELETE runs even when ``edges`` is empty, and that is the point: a
        instance that just lost its last reference (or whose Kind dropped the
        declaration) must lose its rows, and an empty INSERT with no DELETE
        would leave the graph asserting a relation the instance no longer
        makes. The cost is one index probe on a primary-key prefix inside a
        transaction that is already doing four statements.
        """
        e = self.edges
        await conn.execute(e.delete().where(
            e.c.scope == scope, e.c.tenant == tenant_val,
            e.c.from_api_version == api_version,
            e.c.from_kind == kind, e.c.from_name == name,
        ))
        if not edges:
            return
        ts = self._edge_now()
        await conn.execute(e.insert(), [
            {
                "scope": scope,
                "tenant": tenant_val,
                "from_api_version": api_version,
                "from_kind": kind,
                "from_name": name,
                "source_field": edge.field,
                "ordinal": edge.ordinal,
                "to_scope": edge.to_scope,
                "to_kind": edge.to_kind,
                "to_name": edge.value,
                # i-114 — name AND id, the ``ownerReferences`` pair. ``getattr``
                # because ``ResolvedEdge`` is also constructed by the backfill
                # and by tests that predate the field; an edge producer that
                # cannot say which instance it matched says NULL, not a guess.
                "to_id": getattr(edge, "to_id", None),
                # i-110.3 — the third field of the ``OwnerReference`` quartet,
                # and the one that stops ``to_kind`` from being a bare name.
                # Same ``getattr`` as ``to_id``, for the same reason. A
                # producer that cannot say which apiVersion it matched says
                # NULL — never ``api_version``, which is right there in scope
                # and would be a plausible, wrong and unfalsifiable value: the
                # WRITER's apiVersion has no bearing on the TARGET's.
                "to_api_version": getattr(edge, "to_api_version", None),
                "declared_to": " | ".join(edge.declared),
                "from_version": from_version,
                "updated_at": ts,
            }
            for edge in edges
        ])

    async def _replace_bundle_entries(
        self, conn, scope: str, kind: str, api_version: str, name: str,
        tenant_val: str,
        text_entries: dict[str, str], bin_entries: dict[str, bytes],
    ) -> None:
        b = self.bundle_entries
        key = [
            b.c.scope == scope, b.c.kind == kind,
            b.c.api_version == api_version, b.c.name == name,
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
                scope=scope, kind=kind, api_version=api_version, name=name,
                entry_path=entry_path,
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
                index_elements=_BUNDLE_CONFLICT_COLS,
                set_=set_,
            ))

    #: Hard ceiling on traversal depth, whatever a caller asks for. Two of the
    #: sixteen declared references are SELF-referential by design
    #: (``Spec.supersedes → Spec``, ``Story.dependencies → Story``), so an
    #: unbounded walk here is a production incident, not a theoretical risk.
    MAX_TRAVERSAL_DEPTH = 10
    #: Hard ceiling on rows returned. A wide fan-out at depth 3 multiplies.
    MAX_TRAVERSAL_ROWS = 5000

    async def replace_edges(
        self, scope: str, kind: str, name: str, edges: "list[Any]", *,
        api_version: str = "", tenant: str | None = None,
        from_version: int = 0,
    ) -> None:
        """Replace one instance's outgoing edges in a transaction of its own.

        The NON-atomic entry point, used by the backfill and by any repair that
        runs outside a write. The atomic one is the ``edges=`` kwarg of
        :meth:`save_instance`; this exists because instances written before the
        producer existed have no edges and must be able to get some without
        being rewritten.
        """
        async with self._engine.begin() as conn:
            await self._replace_edges(
                conn, scope, kind, api_version, name, tenant or "",
                edges, from_version,
            )

    async def list_instances_with_spec_field(
        self, kind: str, field: str, *, scope: str | None = None,
    ) -> list[dict[str, Any]]:
        """Instances of ``kind`` whose ``spec`` HAS ``field`` — the backfill's
        reader.

        [dialect] Postgres uses the JSONB key-existence operator ``?``, which
        the ``dna_insts_spec_gin_idx`` GIN index (baseline 0001) serves directly;
        SQLite uses ``json_extract``. Either way the query is per declared
        ``(Kind, field)`` PAIR — sixteen of them across the whole shipped
        registry today — and not a walk over every instance in the database.
        That distinction is the whole reason the backfill is affordable, and it
        is also why it is not a scanner: it asks the same declaration the
        producer reads, never a slug-shaped guess.
        """
        d = self.instances
        where: list[sa.ColumnElement] = [d.c.kind == kind]
        if scope is not None:
            where.append(d.c.scope == scope)
        if self._is_pg:
            # [dialect] ``content::jsonb->'spec' ? :field``. The ``?`` operator
            # collides with the DBAPI placeholder, so it is spelled through the
            # function form ``jsonb_exists``, which is the same operator and
            # uses the same index.
            from sqlalchemy.dialects.postgresql import JSONB  # noqa: PLC0415
            where.append(sa.func.jsonb_exists(
                sa.cast(d.c.content, JSONB)["spec"], field,
            ))
        else:
            where.append(sa.func.json_extract(
                d.c.content, f"$.spec.{field}",
            ).isnot(None))
        async with self._engine.connect() as conn:
            result = (await conn.execute(
                sa.select(
                    d.c.scope, d.c.kind, d.c.api_version, d.c.name,
                    d.c.version, d.c.tenant, d.c.content,
                ).where(*where)
            )).all()
        return [
            {
                "scope": r.scope, "kind": r.kind,
                "api_version": r.api_version or "", "name": r.name,
                "version": int(r.version or 0), "tenant": r.tenant or "",
                "raw": json.loads(r.content),
            }
            for r in result
        ]

    async def traverse_edges(
        self, scope: str, kind: str, name: str, *,
        tenant: str | None = None,
        direction: str = "out",
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Walk the derived reference graph from one instance.

        ONE recursive CTE, standard SQL, identical on Postgres and SQLite — no
        server extension, no second query language. (Apache AGE was considered
        and rejected in the spec: it is a server extension the Azure platform
        allowlists rather than we do, it would strand the SQLite and filesystem
        adapters the SDK carries as first-class citizens, and it brings
        openCypher to a walk that is fifteen lines of SQL.)

        Three refusals, each with a dedicated test:

        * **Depth is mandatory and capped.** Defaults to 1, is clamped to
          :data:`MAX_TRAVERSAL_DEPTH`, and a self-referential Kind makes that
          non-negotiable.
        * **Anti-cycle on the path**, on top of the depth cap. A two-node cycle
          would otherwise burn the whole budget producing duplicates before the
          cap stopped it. The check is exact containment via ``replace()``
          rather than ``LIKE`` — deliberately, because ``LIKE`` treats ``_`` as
          a wildcard and instance names are full of underscores, so a ``LIKE``
          test would silently stop walks it was never meant to stop. The edge
          that CLOSES a cycle is still reported once, flagged
          ``closes_cycle``, and merely not expanded FROM: it is a relation
          somebody really wrote, and dropping it would hide the cycle rather
          than survive it.
        * **``scope`` and ``tenant`` in EVERY branch**, not only in the anchor.
          Omitting them from the recursive step is the classic cross-tenant
          leak of this query shape, and it is one easy line to forget.

        **The hop joins on apiVersion too (i-110.3).** A multi-hop walk chains
        one edge's TO onto the next edge's FROM. That join used to be
        ``(kind, name)`` — a Kind NAME, which identifies a Kind only because
        ``dna.kernel.kinds.registry`` refuses name collisions across
        apiVersions (i-195), an invariant of another module carrying a live
        exception list. Two homonymous Kinds and the walk would silently step
        from one family into the other's edges. The join now also compares
        ``to_api_version``/``from_api_version`` — through
        :func:`_same_api_family`, which treats NULL *and* the empty string as
        "unknown" and lets the hop through. That tolerance is not a softening:
        it is what makes the tightening a strict improvement instead of a
        silent loss of every hop out of a pre-0009 row.

        ⚠️ **The ANCHOR is still by bare name, and this is the honest limit.**
        Asking "what points at ``Foo/bar``" cannot pin an apiVersion the caller
        never supplied — ``graph_refs`` takes none. So at depth 1 a homonymous
        pair still yields both families' edges; what CHANGED is that the rows
        now carry ``to_api_version``, so the ambiguity is visible to the reader
        instead of resolved by luck, and every hop AFTER depth 1 stays inside
        the family it started in.
        """
        if direction not in ("out", "in", "both"):
            raise ValueError(
                f"direction must be 'out', 'in' or 'both' (got {direction!r})"
            )
        if direction == "both":
            merged: list[dict[str, Any]] = []
            for one in ("out", "in"):
                merged.extend(await self.traverse_edges(
                    scope, kind, name, tenant=tenant, direction=one, depth=depth,
                ))
            return merged

        depth = max(1, min(int(depth), self.MAX_TRAVERSAL_DEPTH))
        tenant_val = tenant or ""
        e = self.edges

        def marker(kind_col, name_col):
            """``>Kind/name>`` — the delimiters make containment exact."""
            return (
                sa.literal(">") + sa.func.coalesce(kind_col, sa.literal(""))
                + sa.literal("/") + name_col + sa.literal(">")
            )

        def tail(kind_col, name_col):
            """The same marker without its leading ``>``; the path already
            ends with one, and the shared delimiter is what makes
            ``>A>B>C>`` contain ``>B>``."""
            return (
                sa.func.coalesce(kind_col, sa.literal(""))
                + sa.literal("/") + name_col + sa.literal(">")
            )

        outward = direction == "out"
        # The node an edge ARRIVES at, for this direction. Walking "in" is the
        # same query with the join mirrored, served by the `_in` index.
        node_kind = e.c.to_kind if outward else e.c.from_kind
        node_name = e.c.to_name if outward else e.c.from_name
        anchor_kind = e.c.from_kind if outward else e.c.to_kind
        anchor_name = e.c.from_name if outward else e.c.to_name

        cols = [
            e.c.from_api_version, e.c.from_kind, e.c.from_name,
            e.c.source_field, e.c.ordinal,
            e.c.to_scope, e.c.to_api_version, e.c.to_kind, e.c.to_name,
            e.c.to_id, e.c.declared_to, e.c.from_version,
        ]
        def closes(prev, kind_col, name_col):
            """1 when ``prev`` already visited this row's target node.

            Exact containment through ``replace()``: removing the marker
            changes the string only if the marker was there. ``LIKE`` would be
            the obvious spelling and the wrong one — ``_`` is a wildcard there
            and instance names are full of underscores, so it would stop walks
            it was never meant to stop.
            """
            m = marker(kind_col, name_col)
            return sa.case(
                (sa.func.replace(prev, m, sa.literal("")) != prev, sa.literal(1)),
                else_=sa.literal(0),
            )

        start = sa.literal(f">{kind}/") + sa.literal(f"{name}>")
        anchor = sa.select(
            *cols,
            sa.literal(1).label("depth"),
            (start + tail(node_kind, node_name)).label("path"),
            # A self-loop closes a cycle at the very first hop.
            closes(start, node_kind, node_name).label("closes_cycle"),
        ).where(
            e.c.scope == scope, e.c.tenant == tenant_val,
            anchor_kind == kind, anchor_name == name,
        )
        walk = anchor.cte("walk", recursive=True)

        ea = e.alias("ee")
        ea_node_kind = ea.c.to_kind if outward else ea.c.from_kind
        ea_node_name = ea.c.to_name if outward else ea.c.from_name
        ea_anchor_kind = ea.c.from_kind if outward else ea.c.to_kind
        ea_anchor_name = ea.c.from_name if outward else ea.c.to_name
        walk_node_kind = walk.c.to_kind if outward else walk.c.from_kind
        walk_node_name = walk.c.to_name if outward else walk.c.from_name
        # i-110.3 — the apiVersion halves of the SAME two sides the join above
        # pairs, derived from ``outward`` exactly like the kind/name pair so the
        # two can never be mirrored inconsistently.
        ea_anchor_apiv = ea.c.from_api_version if outward else ea.c.to_api_version
        walk_node_apiv = walk.c.to_api_version if outward else walk.c.from_api_version

        recursive = sa.select(
            ea.c.from_api_version, ea.c.from_kind, ea.c.from_name,
            ea.c.source_field, ea.c.ordinal,
            ea.c.to_scope, ea.c.to_api_version, ea.c.to_kind, ea.c.to_name,
            ea.c.to_id, ea.c.declared_to, ea.c.from_version,
            (walk.c.depth + 1).label("depth"),
            (walk.c.path + tail(ea_node_kind, ea_node_name)).label("path"),
            closes(walk.c.path, ea_node_kind, ea_node_name).label("closes_cycle"),
        ).select_from(ea.join(
            walk,
            sa.and_(
                ea_anchor_kind == walk_node_kind,
                ea_anchor_name == walk_node_name,
                # i-110.3 — and the apiVersion, whenever BOTH sides know
                # theirs. Without this the hop chains on a Kind NAME, which
                # identifies a Kind only by the registry's i-195 guard; see the
                # method docstring.
                _same_api_family(ea_anchor_apiv, walk_node_apiv),
                # i-110.3 — and the apiVersion, whenever BOTH sides know
                # theirs. Without this the hop chains on a Kind NAME, which
                # identifies a Kind only by the registry's i-195 guard; see the
                # method docstring.
                # i-110.3 — and the apiVersion, whenever BOTH sides know
                # theirs. Without this the hop chains on a Kind NAME, which
                # identifies a Kind only by the registry's i-195 guard; see the
                # method docstring.
            ),
        )).where(
            # ⚠️ THE tenant/scope line. In the recursive step, not only the
            # anchor — without it a walk starting in one tenant follows edges
            # belonging to another the moment two instances share a name.
            ea.c.scope == scope,
            ea.c.tenant == tenant_val,
            walk.c.depth < depth,
            # Anti-cycle: do not expand FROM a row that already closed one.
            # The closing edge itself was emitted by the level that found it,
            # so the cycle is visible AND finite — a walk that simply dropped
            # the row would hide the very thing worth reporting.
            walk.c.closes_cycle == 0,
        )
        walk = walk.union_all(recursive)

        async with self._engine.connect() as conn:
            rows = (await conn.execute(
                sa.select(walk)
                .order_by(sa.text("depth"))
                .limit(self.MAX_TRAVERSAL_ROWS)
            )).all()
        # A CTE enumerates PATHS, so a diamond reports the same edge once per
        # route into it. The question the face asks is about EDGES ("what
        # points at this, and how far away"), so collapse to one row per edge
        # at its shortest depth. Done here rather than in SQL because
        # ``DISTINCT ON`` is Postgres-only and a portable ``GROUP BY`` over a
        # recursive CTE is markedly harder to read than four lines of Python.
        out: dict[tuple, dict[str, Any]] = {}
        for r in rows:
            # i-110.3 — ``from_api_version`` is in the key because it is in the
            # table's PRIMARY KEY. Without it this dictionary is a narrower key
            # than the storage, so two rows that legally coexist — the same
            # field/ordinal on two homonymous Kinds — collapse into one and the
            # walk silently loses a whole family's edges. That the bug never
            # fired is the registry's i-195 guard doing this dictionary's job
            # from another module, which is precisely the borrowed invariant
            # this slice is repaying.
            key = (r.from_api_version, r.from_kind, r.from_name,
                   r.source_field, int(r.ordinal))
            if key in out:
                continue
            out[key] = {
                "direction": direction,
                "depth": int(r.depth),
                "from_api_version": r.from_api_version or "",
                "from_kind": r.from_kind, "from_name": r.from_name,
                "source_field": r.source_field, "ordinal": int(r.ordinal),
                "to_scope": r.to_scope, "to_kind": r.to_kind,
                "to_name": r.to_name,
                # i-110.3 — WHICH Kind, not which Kind NAME. NULL when the edge
                # is dangling, or when the row predates revision 0009 and the
                # backfill could not reach its target.
                "to_api_version": r.to_api_version,
                # i-114 — the id of the instance this edge ACTUALLY resolved
                # to, beside the name the author wrote. NULL when dangling or
                # when the target predates the id.
                "to_id": r.to_id,
                "declared_to": tuple(
                    t for t in (r.declared_to or "").split(" | ") if t
                ),
                # ``to_kind is None`` is the DANGLING edge — declared, written,
                # resolving to nothing. It is reported, never filtered: it is
                # the list of what is broken.
                "resolved": r.to_kind is not None,
                # This edge points back at a node the walk had already
                # visited. Reported, not hidden: a cycle in the data is
                # information, and ``Story.dependencies → Story`` makes cycles
                # ordinary rather than corrupt.
                "closes_cycle": bool(r.closes_cycle),
                "from_version": int(r.from_version or 0),
            }
        return list(out.values())

    async def publish(
        self, scope: str, kind: str, name: str, *, tenant: str | None = None,
        api_version: str | None = None,
    ) -> str:
        """Promote the newest draft to the published ``instances`` row.

        ``api_version`` pins WHICH Kind's draft is promoted. Without it a name
        that two Kinds share would promote whichever draft happens to have the
        higher version number — a publish that silently republishes the other
        workspace's content — so that case is refused rather than guessed. The
        published row is always written under the DRAFT'S OWN apiVersion, never
        under a value supplied by the caller, so publish cannot mint a row that
        contradicts the instance it is publishing.
        """
        v, d = self.versions, self.instances
        tenant_val = tenant or ""
        async with self._engine.begin() as conn:
            await self._refuse_ambiguous_name(
                conn, v, scope, kind, name, tenant, api_version, verb="publish",
                extra=[v.c.is_draft.is_(True)],
            )
            row = (await conn.execute(
                sa.select(v.c.id, v.c.content, v.c.version, v.c.api_version).where(
                    v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                    *self._api_version_where(v.c.api_version, api_version),
                    self._tenant_where(v.c.tenant, tenant),
                    v.c.is_draft.is_(True),
                ).order_by(v.c.version.desc()).limit(1)
            )).first()
            if row is None:
                raise ValueError("no_draft")
            ins = self._upsert(d).values(
                scope=scope, kind=kind, api_version=row.api_version, name=name,
                content=row.content,
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

    async def delete_instance(
        self, scope: str, kind: str, name: str,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        api_version: str | None = None,
    ) -> None:
        # ``api_version`` now has a column to land in (revision 0003): the row
        # key is (scope, kind, api_version, name, tenant), so this pins the
        # delete to the exact Kind instead of to whichever row the bare name
        # reaches. Unpinned deletes keep working — and are refused, not guessed,
        # when the name really does resolve to two Kinds.
        if layer is not None:
            if layer[0] == "tenant" and tenant is None:
                tenant = layer[1]
            elif layer[0] != "tenant":
                raise NotImplementedError(
                    f"SqlAlchemySource does not support non-tenant layers in "
                    f"delete_instance (got layer={layer!r}). "
                    "Use delete_layer_instance directly."
                )
        d, v, b = self.instances, self.versions, self.bundle_entries
        tenant_val = tenant or ""
        async with self._engine.begin() as conn:
            await self._refuse_ambiguous_name(
                conn, d, scope, kind, name, tenant, api_version, verb="delete",
            )
            key = lambda t: [  # noqa: E731
                t.c.scope == scope, t.c.kind == kind, t.c.name == name,
                *self._api_version_where(t.c.api_version, api_version),
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
            # The instance's OUTGOING edges go with it: they were assertions
            # this instance made, and the instance is gone.
            #
            # Its INCOMING edges deliberately DO NOT. They belong to OTHER
            # instances, which still say what they said; what changed is that
            # those statements no longer resolve. Deleting them would erase the
            # evidence that this delete just broke three things — and the delete
            # path has no reference gate at all (``pipeline.delete``: "deletes
            # have NO pre_save veto"), so that evidence is the only trace there
            # is. They become dangling, which is exactly what happened.
            eg = self.edges
            await conn.execute(eg.delete().where(
                eg.c.scope == scope, eg.c.tenant == tenant_val,
                eg.c.from_kind == kind, eg.c.from_name == name,
                *self._api_version_where(eg.c.from_api_version, api_version),
            ))
            # doc_version=0 is the documented sentinel for delete.
            await self._events.emit(
                conn, scope=scope, tenant=tenant_val, kind=kind, name=name,
                op="delete", doc_version=0,
            )
        self.invalidate_view(scope)

    async def save_manifest(self, scope: str, manifest: dict) -> str:
        kind = manifest.get("kind") or "Genome"
        return await self.save_instance(
            scope, kind, manifest.get("metadata", {}).get("name", scope), manifest,
        )

    # ------------------------------------------------------------------
    # Layer operations (non-tenant layers → legacy layer_instances table)
    # ------------------------------------------------------------------

    async def save_layer_instance(
        self, scope: str, layer_id: str, layer_value: str,
        kind: str, name: str, raw: dict,
    ) -> None:
        # Tenant overlays live in instances.tenant (Phase 8a) — route
        # through save_instance so save+load round-trip (raw-PG parity).
        if layer_id == "tenant":
            return await self.save_instance(
                scope, kind, name, raw, tenant=layer_value,
            )
        ld = self.layer_instances
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

    async def delete_layer_instance(
        self, scope: str, layer_id: str, layer_value: str,
        kind: str, name: str,
    ) -> None:
        ld = self.layer_instances
        async with self._engine.begin() as conn:
            await conn.execute(ld.delete().where(
                ld.c.scope == scope, ld.c.layer_id == layer_id,
                ld.c.layer_value == layer_value,
                ld.c.kind == kind, ld.c.name == name,
            ))

    async def list_layers(self, scope: str) -> list[dict[str, str]]:
        """Legacy layer_instances entries merged with the tenant overlays
        observed in instances.tenant (raw-PG parity)."""
        ld = self.layer_instances
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

    async def list_versions(
        self, scope: str, kind: str, name: str, *,
        api_version: str | None = None,
    ) -> list[dict]:
        v = self.versions
        async with self._engine.connect() as conn:
            rows = (await conn.execute(
                sa.select(v.c.id, v.c.version, v.c.is_draft, v.c.author,
                          v.c.created_at).where(
                    v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                    *self._api_version_where(v.c.api_version, api_version),
                ).order_by(v.c.version.desc())
            )).mappings().all()
        return [dict(r) for r in rows]

    async def get_version(
        self, scope: str, kind: str, name: str, version_id: str, *,
        api_version: str | None = None,
    ) -> dict:
        v = self.versions
        async with self._engine.connect() as conn:
            row = (await conn.execute(
                sa.select(v).where(
                    v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                    *self._api_version_where(v.c.api_version, api_version),
                    v.c.version == int(version_id),
                )
            )).mappings().first()
        if row is None:
            raise ValueError("version_not_found")
        result = dict(row)
        result["content"] = json.loads(result["content"])
        return result

    async def load_one_as_of(
        self, scope: str, kind: str, name: str, *,
        as_of: str,
        tenant: str | None = None,
        api_version: str | None = None,
    ) -> dict[str, Any]:
        """TRANSACTION-time read — the instance AS THIS STORE RECORDED IT at ``as_of``.

        The second time axis. ``valid_from``/``valid_to`` on a spec are WORLD
        time: when a fact was true. ``dna_versions.created_at`` is TRANSACTION
        time: when this store came to believe it. They answer different
        questions, and only the second one answers *"what did the system believe
        at T-1?"* — a fact recorded today about last year is valid then and
        believed now.

        No new column: ``created_at`` has been the transaction stamp since
        revision 0001, and ``content`` holds the FULL envelope per write (not a
        diff, not a pointer), so the belief state is reconstructable from what
        is already on disk.

        Returns ``{raw, version, recorded_at, truncated}``:

        - ``raw`` is the envelope of the newest version recorded at or before
          ``as_of``, or ``None``.
        - ``truncated`` distinguishes the two ways ``raw`` can be ``None``, and
          the distinction is the whole point of the field. ``False`` = the
          instance DID NOT EXIST yet (its version 1 is newer than ``as_of``) —
          an answer. ``True`` = version 1 was PRUNED away
          (``VERSION_CHURN_RETENTION`` caps Engram at 3), so the store cannot
          know what it believed then — a refusal. Collapsing the two would let a
          caller read "no memory" out of "no record", which is the one mistake a
          history read must never make.

        ``as_of`` is an ISO-8601 UTC string compared lexicographically against
        ``created_at``, which is written by :func:`_now` in exactly that shape —
        fixed-width ISO fields sort lexicographically, so the comparison is the
        chronological one. Normalize through
        :func:`dna.memory.as_of.normalize_as_of` rather than formatting by hand.

        ⚠️ Bundle-format Kinds (a Research's ``source_files``) live in
        ``dna_bundle_entries``, which keeps NO history — the envelope comes back
        as-of, its bundle does not. Engram, the memory Kind this exists for, is
        not bundle-format.
        """
        v = self.versions
        # Overlay first, base second — the same precedence `_load_one_on` uses,
        # so an as-of read resolves the tenant lane a live read would have.
        tenant_candidates: list[str | None] = [tenant, None] if tenant else [None]
        async with self._engine.connect() as conn:
            for t in tenant_candidates:
                where = [
                    v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                    *self._api_version_where(v.c.api_version, api_version),
                    self._tenant_where(v.c.tenant, t),
                ]
                row = (await conn.execute(
                    sa.select(v.c.version, v.c.content, v.c.created_at)
                    .where(*where, v.c.created_at <= as_of)
                    .order_by(v.c.version.desc()).limit(1)
                )).first()
                if row is not None:
                    return {
                        "raw": json.loads(row.content),
                        "version": int(row.version),
                        "recorded_at": row.created_at,
                        "truncated": False,
                    }
                oldest = (await conn.execute(
                    sa.select(v.c.version, v.c.created_at).where(*where)
                    .order_by(v.c.version.asc()).limit(1)
                )).first()
                if oldest is None:
                    continue  # nothing on this lane at all — fall through to base
                return {
                    "raw": None, "version": None, "recorded_at": None,
                    # v1 still on disk ⇒ the doc genuinely post-dates `as_of`.
                    # v1 pruned ⇒ we are blind, and must say so.
                    "truncated": int(oldest.version) > 1,
                }
        return {"raw": None, "version": None, "recorded_at": None, "truncated": False}

    # ------------------------------------------------------------------
    # WORLD time — the OTHER axis (revision 0010, spec-topologia fatia 3)
    # ------------------------------------------------------------------

    def _valid_at_values(self, raw: object) -> dict[str, Any]:
        """``{"valid_at": Range(...)}`` on pg, ``{}`` on sqlite.

        A dict rather than a value so the sqlite path emits no column at all:
        there IS no ``valid_at`` on that dialect (see ``schema.py``), and
        passing ``None`` for it would be a different statement — "the column
        exists and this row declines to fill it".

        The window itself comes from :func:`dna.kernel.valid_time.valid_window_of`
        — the SAME function revision 0010's backfill mirrors in SQL. If the two
        ever disagreed, the column would mean one thing on rows written before
        the migration and another on rows written after, and nobody would find
        out, because both readings are plausible.
        """
        if not self._is_pg:
            return {}
        from sqlalchemy.dialects.postgresql import Range

        from dna.kernel.valid_time import valid_window_of
        w = valid_window_of(raw)
        # ``Range(None, None)`` is UNBOUNDED on both ends, not empty — the same
        # ``(-infinity, infinity)`` the column defaults to. An instance that
        # says nothing about world time is true for all of it, which is exactly
        # what ``dna.memory.decay.currently_valid`` has always meant.
        return {"valid_at": Range(w.lower, w.upper, bounds="[)")}

    async def load_one_valid_at(
        self, scope: str, kind: str, name: str, *,
        valid_at: Any,
        tenant: str | None = None,
        api_version: str | None = None,
    ) -> dict[str, Any] | None:
        """WORLD-time read — the instance IF the fact it states was true at ``valid_at``.

        The mirror of :meth:`load_one_as_of`, one axis over, and the pair is
        only useful because they are separate. ``as_of`` asks *what did this
        store BELIEVE at T* and reads ``dna_versions.created_at``. This asks
        *was this TRUE at T* and reads ``dna_instances.valid_at``. A note
        written today about last year is found by this read at last year and
        must not be found by that one.

        Returns the same shape as :meth:`load_one` (the envelope dict) or
        ``None`` — and ``None`` here is an ANSWER, not a refusal: the instance
        exists and its declared window does not contain that instant. The
        refusal is :class:`~dna.kernel.valid_time.ValidTimeUnsupported`, raised
        below when this binding has no column, because a store without the
        column filtering nothing and returning the row would be answering *"yes,
        it was true then"* on no evidence whatsoever.

        The predicate is ``valid_at @> :instant`` — evaluated by the GiST index
        the EXCLUDE constraint already maintains, so the world-time filter costs
        nothing extra to keep. Half-open ``[from, to)``: an instance whose
        window ends at T is NOT current at T, which is what lets a supersession
        chain hand off cleanly.
        """
        if not self._is_pg:
            from dna.kernel.valid_time import ValidTimeUnsupported
            raise ValidTimeUnsupported(
                f"world-time reads need a store that keeps the validity window "
                f"as a column; this deployment's source is bound to "
                f"{self._engine.dialect.name!r}, which has no range type, no "
                f"GiST and no EXCLUDE constraint, so revision 0010 does not "
                f"create the column there. Refusing rather than returning "
                f"{kind} {name!r} unfiltered, which would assert it was true at "
                f"an instant this store cannot check."
            )
        from dna.kernel.valid_time import normalize_valid_at
        instant = normalize_valid_at(valid_at)
        d = self.instances
        # Overlay first, base second — the same precedence ``_load_one_on`` and
        # ``load_one_as_of`` use, so a world-time read resolves the tenant lane
        # a live read would have.
        tenant_candidates: list[str | None] = [tenant, None] if tenant else [None]
        async with self._engine.connect() as conn:
            for t in tenant_candidates:
                row = (await conn.execute(
                    sa.select(d.c.content).where(
                        d.c.scope == scope, d.c.kind == kind, d.c.name == name,
                        *self._api_version_where(d.c.api_version, api_version),
                        self._tenant_where(d.c.tenant, t),
                        d.c.valid_at.contains(instant),
                    ).limit(1)
                )).first()
                if row is not None:
                    return json.loads(row.content)
        return None

    async def load_drafts(self, scope: str) -> list[dict]:
        v = self.versions
        # Grouped by (kind, apiVersion, name): two Kinds sharing a name keep
        # separate drafts, and collapsing them would hide one of the two.
        latest = sa.select(
            v.c.kind, v.c.api_version, v.c.name,
            sa.func.max(v.c.version).label("max_v"),
        ).where(
            v.c.scope == scope, v.c.is_draft.is_(True),
        ).group_by(v.c.kind, v.c.api_version, v.c.name).subquery()
        stmt = sa.select(
            v.c.kind, v.c.api_version, v.c.name, v.c.content, v.c.version,
            v.c.created_at,
        ).join(latest, sa.and_(
            v.c.kind == latest.c.kind,
            v.c.api_version == latest.c.api_version,
            v.c.name == latest.c.name,
            v.c.version == latest.c.max_v,
        )).where(v.c.scope == scope, v.c.is_draft.is_(True))
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]

    async def list_scopes(self) -> list[str]:
        d = self.instances
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
        mirror to the latest ``instances`` pointer when it matches."""
        v, d = self.versions, self.instances
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                sa.select(v.c.content, v.c.api_version).where(
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
                v.c.api_version == row.api_version,
                self._tenant_where(v.c.tenant, tenant),
                v.c.semver == version,
            ).values(content=new_content))
            # Mirror to the published pointer of the SAME Kind — the archived
            # row's own apiVersion, never a bare-name match.
            latest = (await conn.execute(
                sa.select(d.c.content).where(
                    d.c.scope == scope, d.c.kind == "Genome", d.c.name == scope,
                    d.c.api_version == row.api_version,
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
                            d.c.api_version == row.api_version,
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
        api_version: str | None = None,
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
                        *self._api_version_where(b.c.api_version, api_version),
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
            f"kind={kind!r} name={name!r} entry={entry!r} tenant={tenant!r} "
            f"api_version={api_version!r}"
        )

    async def _owning_api_version(
        self, conn, scope: str, kind: str, name: str, tenant_val: str,
    ) -> str:
        """The apiVersion of the instance a bundle entry belongs to.

        A bundle entry is a FILE inside an instance's bundle; it carries no
        apiVersion of its own. Callers that reach this surface directly (the
        Strain file-fork editor, the bundle-overlay paths) pass a container and
        a name, not an instance — so when they do not pin the Kind the owner is
        looked up: the published ``instances`` row first, then the newest
        ``versions`` row. ``''`` when neither exists, which is the same value
        the migration records for an orphan.
        """
        d, v = self.instances, self.versions
        row = (await conn.execute(
            sa.select(d.c.api_version).where(
                d.c.scope == scope, d.c.kind == kind, d.c.name == name,
                self._tenant_where(d.c.tenant, tenant_val or None),
            ).limit(1)
        )).first()
        if row is not None:
            return row.api_version
        row = (await conn.execute(
            sa.select(v.c.api_version).where(
                v.c.scope == scope, v.c.kind == kind, v.c.name == name,
                self._tenant_where(v.c.tenant, tenant_val or None),
            ).order_by(v.c.version.desc()).limit(1)
        )).first()
        return row.api_version if row is not None else ""

    async def write_bundle_entry(
        self, scope: str, container: str, name: str, entry: str,
        content: bytes | str,
        *, tenant: str | None = None, kind: str | None = None,
        api_version: str | None = None,
    ) -> None:
        b = self.bundle_entries
        kind_key = kind or container
        tenant_val = tenant or ""
        set_: dict[str, Any]
        async with self._engine.begin() as conn:
            # A WRITE has to commit to one Kind — "any" is not a value a row
            # can hold. When the caller does not pin it, inherit the owning
            # instance's apiVersion rather than inventing one.
            owner = api_version if api_version is not None else \
                await self._owning_api_version(
                    conn, scope, kind_key, name, tenant_val,
                )
            values: dict[str, Any] = dict(
                scope=scope, kind=kind_key, api_version=owner, name=name,
                entry_path=entry, updated_at=_now(), tenant=tenant_val,
            )
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
            await conn.execute(ins.on_conflict_do_update(
                index_elements=_BUNDLE_CONFLICT_COLS,
                set_=set_,
            ))
        self.invalidate_view(scope)

    async def list_bundle_entries(
        self, scope: str, container: str, name: str,
        *, tenant: str | None = None, only_tenant: bool = False,
        kind: str | None = None, api_version: str | None = None,
    ) -> list[str]:
        """s-strain-bundle-fork B1 — list entry paths for a bundle. Composed
        (default) = tenant overlay ∪ base; ``only_tenant`` restricts to the
        tenant's own override rows (base sentinel ``""`` when no tenant)."""
        b = self.bundle_entries
        kind_key = kind or container
        tenants = [tenant or ""] if only_tenant else ([tenant, ""] if tenant else [""])
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                sa.select(b.c.entry_path).where(
                    b.c.scope == scope, b.c.kind == kind_key, b.c.name == name,
                    *self._api_version_where(b.c.api_version, api_version),
                    b.c.tenant.in_(tenants),
                )
            )
            return sorted({r.entry_path for r in rows})

    async def delete_bundle_entry(
        self, scope: str, container: str, name: str, entry: str,
        *, tenant: str | None = None, kind: str | None = None,
        api_version: str | None = None,
    ) -> bool:
        """s-strain-bundle-fork B1 — delete ONE entry row for ``tenant``
        (base sentinel ``""`` when None). Returns True if a row existed."""
        b = self.bundle_entries
        kind_key = kind or container
        async with self._engine.begin() as conn:
            res = await conn.execute(
                b.delete().where(
                    b.c.scope == scope, b.c.kind == kind_key, b.c.name == name,
                    b.c.entry_path == entry,
                    *self._api_version_where(b.c.api_version, api_version),
                    b.c.tenant == (tenant or ""),
                )
            )
        self.invalidate_view(scope)
        return (res.rowcount or 0) > 0

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
            # (scope, kind, api_version, name[, tenant]) is the row key since
            # revision 0003 — the store itself keeps two Kinds apart.
            api_version_identity=True,
            # `dna_versions` keeps the FULL envelope per write with a
            # `created_at` transaction stamp, so this adapter can reconstruct a
            # past belief state (`load_one_as_of`).
            as_of_reads=True,
            # The derived reference graph is written inside the save
            # transaction (`edges=` in write_kwargs) and walked by
            # `traverse_edges`. Both halves, or the face would be entitled to
            # serve an empty list it cannot back.
            edge_graph=True,
            # [dialect] the ONE capability that differs between this class's two
            # bindings. Postgres has ``dna_instances.valid_at`` (a ``tstzrange``)
            # plus the EXCLUDE constraint that makes overlapping validity
            # periods impossible; SQLite has no range type, no GiST and no
            # EXCLUDE, so revision 0010 does not create the column there and
            # ``load_one_valid_at`` refuses instead of filtering nothing.
            valid_time=self.supports_valid_time,
        )
