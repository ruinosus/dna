"""PgVecRecordSearchProvider — the scale ``RecordSearchProvider`` (Postgres + pgvector).

The server-side sibling of ``SqliteVecRecordSearchProvider``. Same port, same RRF
core, same overlay-shadow semantics — it just swaps the embeddable one-file-per-scope
SQLite store for a shared Postgres database, reusing the DNA Postgres that already
backs the source plane. Promotes from sqlite-vec WITHOUT changing the contract:
both pass the SAME ``record_search_conformance_suite``.

  * dense plane   — pgvector ``<=>`` cosine distance over ``kernel.embed()``
                    vectors, accelerated by an IVFFlat index.
  * lexical plane — a ``tsvector`` generated column (``to_tsvector('simple', …)``)
                    ranked with ``ts_rank`` (BM25-ish), accelerated by a GIN index.
  * fusion        — Reciprocal Rank Fusion (``rrf.reciprocal_rank_fusion``, the
                    pure function shared with the sqlite-vec provider and the TS
                    twin — NOT reimplemented here).

The store schema is OWNED by the shared migration contract
(``pgvector_migrations.build_pg_migrations`` + ``adapters/_migrations.run_migrations``)
— closing the same f-embeddings-ddl-debt the sqlite store closed. Every table is
created by a numbered, append-only, idempotent migration recorded in the store's
own ``{schema}.dna_search_migrations`` control table; a re-boot against an
up-to-date store applies nothing.

Overlay/tenant-aware: ``tenant`` is a column ('' = base). A tenant search reads
base ∪ overlay and the overlay row shadows the base row for the same
``(kind, name)`` — mirroring the source reader's overlay merge and the sqlite
provider byte-for-byte.

Language parity — Py-primary, behavioral parity via the kit
-----------------------------------------------------------
This provider is **Python-only by design**, and that asymmetry is deliberate,
not an omission:

  * The sqlite-vec provider has a TS twin because sqlite-vec is the *embeddable
    offline floor* both language SDKs ship and run in-process (browser/Bun
    included). pgvector is the *scale/server* adapter — it only makes sense
    against a running Postgres, which the TS SDK reaches through the ``pg``
    driver used by its own ``adapters/postgres`` source, a different surface
    from this asyncpg path.
  * Behavioral parity is guaranteed the way the port intends: the SAME
    ``record_search_conformance_suite`` (its TS twin is
    ``src/testing/recordSearchConformance.ts``) is the contract. A future TS
    pgvector twin, if ever needed, must pass the same 8 cases — the kit is the
    parity guarantee, not a hand-diffed second implementation.
  * RRF, the only ranking-affecting logic, is already bit-identical Py↔TS
    (``rrf.py`` ↔ ``rrf.ts``) and is REUSED here unchanged.

So the assimetry is: dense/lexical *plumbing* is Py-only; *ranking behavior* is
cross-language via the shared pure RRF core + the shared conformance kit.

Requires asyncpg + a pgvector-enabled Postgres. Install: ``pip install
'dna-sdk[search-pgvector]'`` (asyncpg) and run against a database where the
``vector`` extension is available (``pgvector/pgvector:pg16`` in CI). Nothing in
the default install imports this module (guard:
``tests/test_search_import_isolation.py``).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, TYPE_CHECKING

from dna.adapters.search.rrf import DEFAULT_RRF_K, reciprocal_rank_fusion
# Pure, extension-free helpers shared with the sqlite-vec provider (importing
# this module does NOT load the sqlite-vec C extension — that load is lazy,
# inside SqliteVecRecordSearchProvider._conn_for). Reusing them keeps ONE
# definition of the searchable-text derivation + snippet across both stores.
from dna.adapters.search.sqlite_vec import document_text, _snippet

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

logger = logging.getLogger(__name__)

#: How many candidates to pull from each plane before fusing + filtering — same
#: over-fetch discipline as the sqlite provider so the final top-k is stable
#: after the kind/tenant/overlay filter (which runs AFTER ranking).
_OVERFETCH = 4
_MIN_CANDIDATES = 40

#: The schema identifier is f-string-interpolated into the DDL/DML (it can't be
#: a bind parameter), so validate it once against a conservative allowlist —
#: same guard the PostgresSource applies (trusted-config-only, never request
#: input).
_VALID_SCHEMA_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _ts_query(query_text: str) -> str:
    """Turn free text into a safe ``to_tsquery('simple', …)`` string: an OR of
    the alphanumeric tokens. Mirrors the sqlite provider's ``_fts_query`` (OR of
    tokens) so both stores see the same lexical corpus/matching. Tokens are pure
    ``[a-z0-9]+`` so they can never be interpreted as tsquery operators."""
    tokens = _TOKEN_RE.findall(query_text.lower())
    return " | ".join(tokens)


def _vec_literal(vector: list[float]) -> str:
    """Render a float vector as a pgvector text literal ``[v1,v2,…]`` for a
    ``$n::vector`` cast (asyncpg has no native vector codec; the text form is
    pgvector's canonical input)."""
    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


class PgVecRecordSearchProvider:
    """``RecordSearchProvider`` backed by Postgres + pgvector + tsvector + RRF.

    Construct with the kernel (for ``embed``) and EITHER a ready ``pool``
    (``asyncpg.Pool``) or a ``dsn`` connection string (a pool is created lazily,
    in the loop that first uses it, and owned/closed by the provider). ``schema``
    defaults to ``public``. Register via ``kernel.record_search_provider(provider)``.
    """

    def __init__(
        self,
        kernel: Any,
        *,
        pool: "asyncpg.Pool | None" = None,
        dsn: str | None = None,
        schema: str = "public",
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        if pool is None and not dsn:
            raise ValueError(
                "PgVecRecordSearchProvider needs either a pool or a dsn "
                "(e.g. dsn='postgresql://user:pass@host/db')"
            )
        if not isinstance(schema, str) or not _VALID_SCHEMA_IDENT.match(schema):
            raise ValueError(
                f"Invalid Postgres schema identifier {schema!r}: must match "
                f"{_VALID_SCHEMA_IDENT.pattern} (trusted-config-only)."
            )
        self._kernel = kernel
        self._pool = pool
        self._owns_pool = pool is None
        self._dsn = dsn
        self._schema = schema
        self._rrf_k = rrf_k
        self._ready = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # store / schema (migration-owned)
    # ------------------------------------------------------------------

    async def _get_pool(self) -> "asyncpg.Pool":
        if self._pool is None:
            try:
                import asyncpg
            except ImportError as exc:  # pragma: no cover — exercised via extra
                raise ImportError(
                    "PgVecRecordSearchProvider needs the 'search-pgvector' extra: "
                    "pip install 'dna-sdk[search-pgvector]'"
                ) from exc
            self._pool = await asyncpg.create_pool(self._dsn)
        return self._pool

    async def _ensure_ready(self) -> None:
        """Migrate the store schema + pin the embedding identity, once. Guarded
        by a lock so a concurrent first-hit burst migrates exactly once."""
        if self._ready:
            return
        async with self._lock:
            if self._ready:
                return
            await self._migrate()
            await self._pin_identity()
            self._ready = True

    async def _migrate(self) -> list[int]:
        """Apply pending migrations through the shared forward-only runner —
        the search store's schema has a real owner (closes f-embeddings-ddl-debt).
        Preserves Postgres semantics: ONE transaction per version wrapping every
        statement + the control-table record."""
        from dna.adapters._migrations import run_migrations
        from dna.adapters.search.pgvector_migrations import build_pg_migrations

        dims = int(self._kernel.embedding_dims)
        migrations = build_pg_migrations(dims)
        pool = await self._get_pool()
        schema = self._schema

        async def ensure_control_table() -> None:
            async with pool.acquire() as conn:
                await conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {schema}.dna_search_migrations "
                    "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )

        async def fetch_applied() -> list[int]:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT version FROM {schema}.dna_search_migrations"
                )
                return [r["version"] for r in rows]

        async def apply_version(version: int, statements: list[str]) -> None:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    for stmt in statements:
                        await conn.execute(stmt.format(schema=schema))
                    await conn.execute(
                        f"INSERT INTO {schema}.dna_search_migrations "
                        "(version, applied_at) VALUES ($1, $2)",
                        version, _now(),
                    )

        return await run_migrations(
            migrations,
            ensure_control_table=ensure_control_table,
            fetch_applied=fetch_applied,
            apply_version=apply_version,
            dialect="Postgres(search)",
        )

    async def _pin_identity(self) -> None:
        """Refuse to reuse a store built for a different embedding space —
        mixing vectors from different (dims, model_id) is silently wrong."""
        dims = str(int(self._kernel.embedding_dims))
        model_id = str(self._kernel.embedding_model_id)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT key, value FROM {self._schema}.dna_search_meta"
            )
            existing = {r["key"]: r["value"] for r in rows}
            if not existing:
                await conn.executemany(
                    f"INSERT INTO {self._schema}.dna_search_meta (key, value) "
                    "VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                    [("embedding_dims", dims), ("embedding_model_id", model_id)],
                )
                return
        if (
            existing.get("embedding_dims") != dims
            or existing.get("embedding_model_id") != model_id
        ):
            raise ValueError(
                "search store was built for embedding space "
                f"({existing.get('embedding_model_id')}, "
                f"dims={existing.get('embedding_dims')}) "
                f"but the active provider is ({model_id}, dims={dims}) — "
                "the vectors are incomparable. Use a fresh schema or re-index."
            )

    # ------------------------------------------------------------------
    # index / delete
    # ------------------------------------------------------------------

    async def index(self, records: list[dict[str, Any]]) -> int:
        """Index (upsert) records into the store.

        Each record: ``{scope, kind, name, tenant?, text?, raw?, title?,
        snippet?}``. ``text`` is used verbatim if present; otherwise derived from
        ``raw`` via :func:`document_text`. Idempotent by text hash — re-indexing
        unchanged text is skipped (no re-embed). Returns the number of records
        actually (re)embedded."""
        if not records:
            return 0
        await self._ensure_ready()
        pool = await self._get_pool()

        # Derive text + hash for every record.
        pending: list[tuple[dict[str, Any], str, str]] = []
        for rec in records:
            text = rec.get("text")
            if text is None:
                text = document_text(rec.get("raw") or {})
            text = text or ""
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            pending.append((rec, text, h))

        # Decide which need (re)embedding — skip rows whose hash is unchanged.
        to_embed: list[tuple[dict[str, Any], str, str]] = []
        async with pool.acquire() as conn:
            for rec, text, h in pending:
                row = await conn.fetchrow(
                    f"SELECT text_hash FROM {self._schema}.dna_search_docs "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                    rec["scope"], rec["kind"], rec["name"], rec.get("tenant") or "",
                )
                if row is not None and row["text_hash"] == h:
                    continue
                to_embed.append((rec, text, h))

        if not to_embed:
            return 0

        vectors = await self._kernel.embed([t for _, t, _ in to_embed])
        async with pool.acquire() as conn:
            async with conn.transaction():
                for (rec, text, h), vector in zip(to_embed, vectors):
                    await self._upsert(conn, rec, text, h, vector)
        return len(to_embed)

    async def _upsert(
        self, conn: Any, rec: dict[str, Any], text: str, text_hash: str,
        vector: list[float],
    ) -> None:
        scope, kind, name = rec["scope"], rec["kind"], rec["name"]
        tenant = rec.get("tenant") or ""
        title = rec.get("title")
        snippet = rec.get("snippet") or _snippet(text)
        # One idempotent UPSERT keyed on the unique (scope, kind, name, tenant):
        # re-indexing changed text replaces embedding + body (and the generated
        # fts column recomputes) without duplicating the row.
        await conn.execute(
            f"INSERT INTO {self._schema}.dna_search_docs "
            "(scope, kind, name, tenant, text_hash, title, snippet, body, embedding) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::vector) "
            "ON CONFLICT (scope, kind, name, tenant) DO UPDATE SET "
            "text_hash=EXCLUDED.text_hash, title=EXCLUDED.title, "
            "snippet=EXCLUDED.snippet, body=EXCLUDED.body, embedding=EXCLUDED.embedding",
            scope, kind, name, tenant, text_hash, title, snippet, text,
            _vec_literal(vector),
        )

    async def delete(self, ids: list[dict[str, Any] | tuple]) -> int:
        """Delete indexed records. Each id is a dict ``{scope, kind, name,
        tenant?}`` or a ``(scope, kind, name[, tenant])`` tuple. Returns the
        number of rows removed."""
        await self._ensure_ready()
        pool = await self._get_pool()
        removed = 0
        async with pool.acquire() as conn:
            for ident in ids:
                if isinstance(ident, dict):
                    scope, kind, name = ident["scope"], ident["kind"], ident["name"]
                    tenant = ident.get("tenant") or ""
                else:
                    scope, kind, name = ident[0], ident[1], ident[2]
                    tenant = ident[3] if len(ident) > 3 and ident[3] else ""
                result = await conn.execute(
                    f"DELETE FROM {self._schema}.dna_search_docs "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                    scope, kind, name, tenant,
                )
                # asyncpg returns "DELETE <n>"
                try:
                    removed += int(result.split()[-1])
                except (ValueError, IndexError):  # pragma: no cover
                    pass
        return removed

    # ------------------------------------------------------------------
    # search (RecordSearchProvider)
    # ------------------------------------------------------------------

    async def search(
        self, *, scope: str, query_text: str, kind: str | None = None,
        k: int = 10, tenant: str = "",
    ) -> list[dict[str, Any]]:
        """Hybrid dense+lexical search fused with RRF. Returns hits shaped
        ``{scope, kind, name, score, title?, snippet?, rank_dense?,
        rank_lexical?}`` (the port's guaranteed keys plus optional extras),
        ordered best-first. Overlay-aware: base ∪ overlay, overlay shadows base."""
        if not query_text.strip() or k <= 0:
            return []
        await self._ensure_ready()
        pool = await self._get_pool()
        overfetch = max(_MIN_CANDIDATES, k * _OVERFETCH)

        query_vec = (await self._kernel.embed([query_text]))[0]

        async with pool.acquire() as conn:
            # Dense plane — cosine KNN over the query embedding. Scoped to the
            # store's scope so the ANN scan stays cheap; all-zero query (no
            # tokens) skips the dense plane (its distances are meaningless).
            dense_ranked: list[int] = []
            if any(query_vec):
                dense_rows = await conn.fetch(
                    f"SELECT id FROM {self._schema}.dna_search_docs "
                    "WHERE scope=$1 AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> $2::vector LIMIT $3",
                    scope, _vec_literal(query_vec), overfetch,
                )
                dense_ranked = [r["id"] for r in dense_rows]

            # Lexical plane — tsvector match ranked by ts_rank. An empty/
            # unparseable query just contributes no lexical ranks.
            lexical_ranked: list[int] = []
            ts = _ts_query(query_text)
            if ts:
                lex_rows = await conn.fetch(
                    f"SELECT id FROM {self._schema}.dna_search_docs "
                    "WHERE scope=$1 AND fts @@ to_tsquery('simple', $2) "
                    "ORDER BY ts_rank(fts, to_tsquery('simple', $2)) DESC LIMIT $3",
                    scope, ts, overfetch,
                )
                lexical_ranked = [r["id"] for r in lex_rows]

            if not dense_ranked and not lexical_ranked:
                return []

            # Fuse ranks (RRF is pure + string-keyed → stringify ids).
            fused = reciprocal_rank_fusion(
                [[str(r) for r in dense_ranked], [str(r) for r in lexical_ranked]],
                k=self._rrf_k,
            )
            dense_pos = {r: i + 1 for i, r in enumerate(dense_ranked)}
            lexical_pos = {r: i + 1 for i, r in enumerate(lexical_ranked)}

            # Resolve metadata for the fused candidates.
            ids = [int(rid) for rid, _ in fused]
            meta = await self._resolve_meta(conn, ids)

        best: dict[tuple[str, str], dict[str, Any]] = {}
        for rid, score in fused:
            row_id = int(rid)
            m = meta.get(row_id)
            if m is None:
                continue
            if kind is not None and m["kind"] != kind:
                continue
            row_tenant = m["tenant"] or ""
            if row_tenant not in ("", tenant or ""):
                continue  # a different tenant's overlay — never leaks
            key = (m["kind"], m["name"])
            prev = best.get(key)
            if prev is None:
                best[key] = _hit(
                    scope, m, score, dense_pos.get(row_id), lexical_pos.get(row_id)
                )
            else:
                prev_is_base = prev["_tenant"] == ""
                this_is_overlay = row_tenant != "" and row_tenant == (tenant or "")
                if this_is_overlay and prev_is_base:
                    best[key] = _hit(
                        scope, m, score, dense_pos.get(row_id), lexical_pos.get(row_id)
                    )

        hits = sorted(best.values(), key=lambda h: -h["score"])
        for h in hits:
            h.pop("_tenant", None)
        return hits[:k]

    async def _resolve_meta(
        self, conn: Any, ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        if not ids:
            return {}
        rows = await conn.fetch(
            f"SELECT id, scope, kind, name, tenant, title, snippet "
            f"FROM {self._schema}.dna_search_docs WHERE id = ANY($1::bigint[])",
            ids,
        )
        return {r["id"]: dict(r) for r in rows}

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the pool IF this provider created it (a caller-supplied pool is
        the caller's to close)."""
        if self._owns_pool and self._pool is not None:
            try:
                await self._pool.close()
            except Exception:  # noqa: BLE001
                pass
            self._pool = None
            self._ready = False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _hit(
    scope: str, m: dict[str, Any], score: float,
    rank_dense: int | None, rank_lexical: int | None,
) -> dict[str, Any]:
    hit: dict[str, Any] = {
        "scope": scope, "kind": m["kind"], "name": m["name"], "score": score,
        "_tenant": m["tenant"] or "",
    }
    if m["title"]:
        hit["title"] = m["title"]
    if m["snippet"]:
        hit["snippet"] = m["snippet"]
    if rank_dense is not None:
        hit["rank_dense"] = rank_dense
    if rank_lexical is not None:
        hit["rank_lexical"] = rank_lexical
    return hit
