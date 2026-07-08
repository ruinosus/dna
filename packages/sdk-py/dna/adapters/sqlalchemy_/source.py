"""SPIKE (i-216) — SqlAlchemySource: ONE adapter, TWO dialects, SAME tables.

SQLAlchemy Core 2.x async prototype that implements SourcePort +
WritableSourcePort against the EXISTING adapter schemas:

  - sqlite  (aiosqlite):  ``documents`` / ``versions`` / ``bundle_entries``
    / ``layer_documents`` — byte-compatible with ``SqliteSource`` DBs,
    including the ``schema_migrations`` control table.
  - postgresql (asyncpg): ``{schema}.dna_documents`` / ``dna_versions`` /
    ``dna_bundle_entries`` / ``dna_layer_documents`` — byte-compatible with
    ``PostgresSource`` schemas, including ``dna_schema_migrations``.

The spike REUSES each dialect's existing migration payloads (it invents no
schema); the shared forward-only runner (``adapters/_migrations.py``)
applies them, so a DB touched by this adapter is indistinguishable from
one touched by the raw adapters.

Honesty markers: every place the two dialects could NOT be expressed as
one Core construct is tagged with ``# [dialect]`` — ``grep -c "\\[dialect\\]"``
is the H1/H3/H4 evidence the spike report cites. Deliberate scope cuts
(time-boxed prototype, NOT production):

  - No outbox / pg_notify / eventbus emission (H2 — stays out regardless).
  - No ``_load_view`` memo cache, no FrontmatterParseWarning fallback,
    no ``spec.source_files`` net, no Module-catalog surface
    (``list_module_versions`` / ``deprecate_module_version``), no
    ``list_layers`` / ``save_layer_document``.
  - SQLite dialect inherits i-092 (documents PK lacks ``tenant`` → a
    tenant overlay publish clobbers the base row). Schema limitation,
    not a Core limitation.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from dna.kernel.protocols import WritableSourcePort

if TYPE_CHECKING:
    from dna.kernel.capabilities import SourceCapabilities

logger = logging.getLogger(__name__)

_OPS = ("eq", "neq", "gt", "gte", "lt", "lte", "like")
_PG_NUMERIC_RE = r"^-?[0-9]+(\.[0-9]+)?$"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_name(raw: dict) -> str | None:
    meta = raw.get("metadata") or {}
    return meta.get("name") or raw.get("name")


class SqlAlchemySource(WritableSourcePort):
    """WritableSourcePort over SQLAlchemy Core async (aiosqlite | asyncpg).

    Usage::

        src = SqlAlchemySource("sqlite+aiosqlite:///path/to.db")
        src = SqlAlchemySource("postgresql+asyncpg://u:p@h/db", schema="dna_x")
        await src.connect()   # runs the dialect's existing migrations
    """

    supports_readers: bool = False
    # H2 — the prototype emits no outbox/pg_notify even on Postgres; a
    # promoted version would keep the eventbus as a PG-only mixin anyway.
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
        self._schema = schema if self._is_pg else None
        # [dialect] base-layer tenant sentinel on documents/versions:
        # pg uses '' (NOT NULL DEFAULT ''), sqlite uses NULL (Phase 2c).
        self._doc_base: str | None = "" if self._is_pg else None
        self._writers = writers or []
        self._readers = readers or []
        self._kernel: object | None = None
        self._build_tables()

    # ------------------------------------------------------------------
    # Table metadata — SAME tables the raw adapters own
    # ------------------------------------------------------------------

    def _build_tables(self) -> None:
        md = sa.MetaData(schema=self._schema)
        # [dialect] pg tables are dna_-prefixed; sqlite's are bare.
        p = "dna_" if self._is_pg else ""
        self.documents = sa.Table(
            f"{p}documents", md,
            sa.Column("scope", sa.Text), sa.Column("kind", sa.Text),
            sa.Column("name", sa.Text), sa.Column("content", sa.Text),
            sa.Column("version", sa.Integer), sa.Column("updated_at", sa.Text),
            sa.Column("tenant", sa.Text),
        )
        self.versions = sa.Table(
            f"{p}versions", md,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("scope", sa.Text), sa.Column("kind", sa.Text),
            sa.Column("name", sa.Text), sa.Column("content", sa.Text),
            sa.Column("version", sa.Integer), sa.Column("is_draft", sa.Boolean),
            sa.Column("author", sa.Text), sa.Column("created_at", sa.Text),
            sa.Column("tenant", sa.Text), sa.Column("semver", sa.Text),
        )
        bundle_cols = [
            sa.Column("scope", sa.Text), sa.Column("kind", sa.Text),
            sa.Column("name", sa.Text), sa.Column("entry_path", sa.Text),
            sa.Column("content", sa.Text), sa.Column("updated_at", sa.Text),
            sa.Column("tenant", sa.Text),
        ]
        if self._is_pg:
            # [dialect] only pg has the BYTEA column (migration v9);
            # sqlite stores bytes in `content` via type affinity.
            bundle_cols.append(sa.Column("content_binary", sa.LargeBinary))
        self.bundle_entries = sa.Table(f"{p}bundle_entries", md, *bundle_cols)
        self.layer_documents = sa.Table(
            f"{p}layer_documents", md,
            sa.Column("scope", sa.Text), sa.Column("layer_id", sa.Text),
            sa.Column("layer_value", sa.Text), sa.Column("kind", sa.Text),
            sa.Column("name", sa.Text), sa.Column("content", sa.Text),
            sa.Column("updated_at", sa.Text),
        )

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
    # Migrations — the EXISTING per-dialect payloads, shared runner
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        if not self._is_pg:
            async with self._engine.connect() as conn:
                await conn.exec_driver_sql("PRAGMA journal_mode=WAL")  # [dialect]
        await self.run_schema_migrations()

    async def run_schema_migrations(self) -> list[int]:
        from .._migrations import run_migrations

        if self._is_pg:
            # [dialect] pg payload: list[str] with {schema} placeholder,
            # one tx per version (existing PostgresSource semantics).
            from ..postgres.source import _MIGRATIONS as PG_MIGRATIONS
            control = f"{self._schema or 'public'}.dna_schema_migrations"

            async def ensure_control_table() -> None:
                async with self._engine.begin() as conn:
                    await conn.exec_driver_sql(
                        f"CREATE TABLE IF NOT EXISTS {control} "
                        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                    )

            async def fetch_applied() -> list[int]:
                async with self._engine.connect() as conn:
                    rows = await conn.exec_driver_sql(
                        f"SELECT version FROM {control}"
                    )
                    return [r[0] for r in rows]

            async def apply_version(version: int, statements: list[str]) -> None:
                async with self._engine.begin() as conn:
                    for stmt in statements:
                        await conn.exec_driver_sql(
                            stmt.format(schema=self._schema or "public")
                        )
                    await conn.execute(
                        sa.text(
                            f"INSERT INTO {control} (version, applied_at) "
                            "VALUES (:v, :at)"
                        ),
                        {"v": version, "at": _now()},
                    )

            return await run_migrations(
                PG_MIGRATIONS, ensure_control_table=ensure_control_table,
                fetch_applied=fetch_applied, apply_version=apply_version,
                dialect="Postgres(SQLAlchemy)",
            )

        # [dialect] sqlite payload: one multi-statement SCRIPT per version
        # (executescript semantics) — split into statements for Core.
        from ..sqlite.migrations import MIGRATIONS as SQLITE_MIGRATIONS

        async def ensure_control_table() -> None:
            async with self._engine.begin() as conn:
                await conn.exec_driver_sql(
                    "CREATE TABLE IF NOT EXISTS schema_migrations "
                    "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )

        async def fetch_applied() -> list[int]:
            async with self._engine.connect() as conn:
                rows = await conn.exec_driver_sql(
                    "SELECT version FROM schema_migrations"
                )
                return [r[0] for r in rows]

        async def apply_version(version: int, script: str) -> None:
            # Strip full-line `--` comments FIRST (they may contain `;`),
            # then split the executescript payload into statements.
            sql_only = "\n".join(
                line for line in script.splitlines()
                if not line.strip().startswith("--")
            )
            async with self._engine.begin() as conn:
                for stmt in sql_only.split(";"):
                    if stmt.strip():
                        await conn.exec_driver_sql(stmt)
                await conn.execute(
                    sa.text(
                        "INSERT INTO schema_migrations (version, applied_at) "
                        "VALUES (:v, :at)"
                    ),
                    {"v": version, "at": _now()},
                )

        return await run_migrations(
            SQLITE_MIGRATIONS, ensure_control_table=ensure_control_table,
            fetch_applied=fetch_applied, apply_version=apply_version,
            dialect="SQLite(SQLAlchemy)",
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
        if not self._writers:
            self._writers = list(kernel._writers)
        if not self._readers:
            self._readers = list(kernel._readers)

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
        """2-query scope view (docs + bundle entries) with reader resolution.

        This whole method is dialect-FREE — the biggest unification win:
        the raw adapters carry two divergent copies of it.
        """
        effective_readers = list(self._readers)
        for r in (readers or []):
            if r not in effective_readers:
                effective_readers.append(r)
        d, b = self.documents, self.bundle_entries
        async with self._engine.connect() as conn:
            doc_rows = (await conn.execute(
                sa.select(d.c.kind, d.c.name, d.c.content).where(
                    d.c.scope == scope,
                    self._tenant_where(d.c.tenant, tenant),
                )
            )).all()
            entry_rows = (await conn.execute(
                sa.select(b.c.kind, b.c.name, b.c.entry_path, b.c.content).where(
                    b.c.scope == scope,
                    b.c.tenant == (tenant or ""),  # bundle sentinel is '' on BOTH
                )
            )).all()
        entries_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for e in entry_rows:
            entries_by_key.setdefault((e.kind, e.name), {})[e.entry_path] = e.content

        from dna.kernel.bundle_handle import DictBundleHandle
        out: list[dict[str, Any]] = []
        for r in doc_rows:
            entries = entries_by_key.get((r.kind, r.name))
            if entries and effective_readers:
                handle = DictBundleHandle(r.name, entries)
                matched = False
                for reader in effective_readers:
                    try:
                        if reader.detect(handle):
                            out.append(reader.read(handle))
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
                    sa.select(b.c.entry_path, b.c.content).where(
                        b.c.scope == scope, b.c.kind == kind, b.c.name == name,
                        b.c.tenant == (t or ""),
                    )
                )).all()
                entries = {e.entry_path: e.content for e in erows}
                if entries and effective_readers:
                    from dna.kernel.bundle_handle import DictBundleHandle
                    handle = DictBundleHandle(name, entries)
                    for reader in effective_readers:
                        try:
                            if reader.detect(handle):
                                return reader.read(handle)
                        except Exception:  # noqa: BLE001
                            continue
                return json.loads(row.content)
        return None

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
            QueryError, _apply_order_by, _project_doc,
        )
        if filter is not None and not isinstance(filter, dict):
            raise QueryError(f"filter must be dict, got {type(filter).__name__}")
        d = self.documents

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

        for doc in docs:
            yield _project_doc(doc, projection) if projection else doc

    async def count(
        self, scope: str, kind: str, *,
        filter=None, group_by=None, tenant=None,
    ) -> dict[str, Any]:
        from dna.kernel.query_fallback import count_via_query
        return await count_via_query(
            self, scope, kind, filter=filter, group_by=group_by, tenant=tenant,
        )

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
        _ = write_class  # no eventbus in the prototype (H2)
        if layer is not None:
            if layer[0] == "tenant" and tenant is None:
                tenant = layer[1]
            elif layer[0] != "tenant":
                raise NotImplementedError(
                    f"SqlAlchemySource does not support non-tenant layers "
                    f"(got layer={layer!r})."
                )
        # Writers → bundle entries (text vs bytes split; pure Python,
        # identical logic to both raw adapters).
        bundle_text: dict[str, str] | None = None
        bundle_bin: dict[str, bytes] | None = None
        from dna.kernel.bundle_handle import DictBundleHandle
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

        v = self.versions
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
                scope=scope, kind=kind, name=name, content=json.dumps(raw),
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
                    conn, scope, kind, name, tenant or "",
                    bundle_text or {}, bundle_bin or {},
                )
        return str(next_version)

    async def _replace_bundle_entries(
        self, conn, scope: str, kind: str, name: str, tenant_val: str,
        text_entries: dict[str, str], bin_entries: dict[str, bytes],
    ) -> None:
        b = self.bundle_entries
        await conn.execute(b.delete().where(
            b.c.scope == scope, b.c.kind == kind, b.c.name == name,
            b.c.tenant == tenant_val,
        ))
        ts = _now()
        for entry_path, body in {**text_entries, **bin_entries}.items():
            values: dict[str, Any] = dict(
                scope=scope, kind=kind, name=name, entry_path=entry_path,
                updated_at=ts, tenant=tenant_val,
            )
            if self._is_pg and isinstance(body, bytes):
                # [dialect] pg routes bytes to content_binary.
                values.update(content="", content_binary=body)
            else:
                values.update(content=body)
            await conn.execute(b.insert().values(**values))

    async def publish(
        self, scope: str, kind: str, name: str, *, tenant: str | None = None,
    ) -> str:
        v, d = self.versions, self.documents
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
                    f"SqlAlchemySource does not support non-tenant layers "
                    f"(got layer={layer!r})."
                )
        d, v, b = self.documents, self.versions, self.bundle_entries
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
                *key(b), b.c.tenant == (tenant or "")))

    async def save_manifest(self, scope: str, manifest: dict) -> str:
        kind = manifest.get("kind") or "Genome"
        return await self.save_document(
            scope, kind, manifest.get("metadata", {}).get("name", scope), manifest,
        )

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
