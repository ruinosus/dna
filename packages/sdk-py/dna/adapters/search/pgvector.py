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

⭐ The store schema is owned by ALEMBIC — this module runs ZERO DDL
------------------------------------------------------------------
``s-indice-por-dimensao``. The tables are created by revision
``0013_uma_tabela_por_dimensao``, the same ladder that owns every other DNA
table, because ``CLAUDE.md`` says *"Data-access code never runs DDL"* and that
is what makes the schema property of a migration, reviewable in a PR. This
module's job is to READ the schema and refuse loudly when the one it needs is
absent — never to create it. (It used to carry its own numbered ladder in
``pgvector_migrations.py``, run at first search; that file is gone.)

There is one table per embedding WIDTH (``dna_search_docs_384`` …
``dna_search_docs_3072``) because ``vector(N)`` is the column's TYPE and so the
width cannot be a column. Routing needs no configuration: ``EmbeddingPort``
already publishes ``dims``, this provider reads ``kernel.embedding_dims`` and
:func:`dna.adapters.search.dimensions.search_table` maps it. An unknown width
raises :class:`~dna.adapters.search.dimensions.UnsupportedEmbeddingDims`
naming the migration to write. See ``dimensions.py`` for the whole decision.

⚠️ ``model_id`` is a FILTER, not a label. Two collections at the same width but
different embedders share a table and are NOT comparable (the port's contract
says so), so every read and every write carries ``AND model_id = …``. That
filter is what lets a tenant pick its own embedder; without it, a shared table
would rank one space's vectors against the other's and call it relevance.

Overlay/tenant-aware: ``tenant`` is a column ('' = base). A tenant search reads
base ∪ overlay and the overlay row shadows the base row for the same
``(kind, name)`` — mirroring the source reader's overlay merge and the sqlite
provider byte-for-byte.

Language parity — Py-primary, behavioral parity via the kit
-----------------------------------------------------------
sqlite-vec is the *embeddable offline floor*; pgvector is the *scale/server*
adapter, only meaningful against a running Postgres. They share no plumbing —
and they do not need to:

  * Correctness is guaranteed the way the port intends: the SAME
    ``record_search_conformance_suite`` is the contract. Any future provider
    is correct exactly when it passes the same 8 cases — the kit is the
    guarantee, not a hand-diffed second implementation.
  * RRF, the only ranking-affecting logic, is REUSED here unchanged
    (``rrf.py``).

So the asymmetry is: dense/lexical *plumbing* differs; *ranking behavior* is
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

from dna.adapters.search.dimensions import SUPPORTED_DIMS, search_table
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
#: same guard SqlAlchemySource applies (trusted-config-only, never request
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
        #: Tables whose existence this provider has already confirmed. NOT a
        #: single ``_ready`` flag: the width is read from the kernel's embedding
        #: provider on EVERY call, so a provider swapped at runtime routes to
        #: the new table instead of writing 1536-wide vectors into the 384 one
        #: that a cached flag would have kept pointing at.
        self._verified: set[str] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # routing — which table, which space (migration-owned schema)
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
            from dna.adapters.asyncpg_dsn import asyncpg_connect_args

            # The DSN arrives from the source's engine URL (``pg_search_binding``)
            # or straight from config, so its query params are CONNECT arguments
            # in SQLAlchemy's dialect. asyncpg's own parser forwards the ones it
            # does not recognise as SERVER SETTINGS — i-091: ``?ssl=require``
            # became ``SET ssl`` and every pool connection died with
            # ``CantChangeRuntimeParamError``, so no index refresh could run and
            # ``recall`` quietly stopped being read-your-writes.
            dsn, connect_kwargs = asyncpg_connect_args(self._dsn)
            self._pool = await asyncpg.create_pool(dsn, **connect_kwargs)
        return self._pool

    async def _table(self) -> str:
        """The table for the ACTIVE embedding width, verified to exist.

        Two steps, and the order matters:

        1. ``search_table(kernel.embedding_dims)`` — pure. An unseen width
           raises ``UnsupportedEmbeddingDims`` HERE, before any connection is
           acquired and before a single row is touched, with a message naming
           the migration to write.
        2. one ``to_regclass`` per table name, cached. A width that IS known but
           whose migration has not been applied to this schema fails loud too —
           and points at the revision, not at "relation does not exist".

        ⛔ Neither step creates anything. That is not an omission; it is the
        rule this design exists to obey (``CLAUDE.md``: data-access code never
        runs DDL). If you ever find yourself wanting a ``CREATE TABLE`` here,
        the answer is a migration, not a branch.
        """
        table = search_table(int(self._kernel.embedding_dims))
        if table in self._verified:
            return table
        async with self._lock:
            if table in self._verified:
                return table
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                present = await conn.fetchval(
                    "SELECT to_regclass($1)", f"{self._schema}.{table}"
                )
            if present is None:
                raise RuntimeError(
                    f"search table {self._schema}.{table} does not exist. It is "
                    "created by alembic revision 0013_uma_tabela_por_dimensao, "
                    "applied by SqlAlchemySource.run_schema_migrations() at "
                    "boot. This provider does NOT create it — the schema is "
                    "owned by the migration ladder, not by data-access code."
                )
            self._verified.add(table)
        return table

    def _model_id(self) -> str:
        """The active embedding SPACE. Every read and every write filters on it:
        the port's contract says vectors from different ``model_id`` are not
        comparable, and two spaces of the same width share a table."""
        return str(self._kernel.embedding_model_id)

    # ------------------------------------------------------------------
    # index / delete
    # ------------------------------------------------------------------

    async def index(self, records: list[dict[str, Any]]) -> int:
        """Index (upsert) records into the store.

        Each record: ``{scope, kind, name, tenant?, text?, raw?, title?,
        snippet?}``. ``text`` is used verbatim if present; otherwise derived from
        ``raw`` via :func:`document_text`. Idempotent by text hash — re-indexing
        unchanged text is skipped (no re-embed). Returns the number of records
        actually (re)embedded.

        Writes into the table of the ACTIVE width, stamped with the active
        ``model_id``: the same record embedded by two models is two rows, in the
        same table when the widths match, and they never meet in a search."""
        if not records:
            return 0
        table = await self._table()
        model_id = self._model_id()
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
                    f"SELECT text_hash FROM {self._schema}.{table} "
                    "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4 "
                    "AND model_id=$5",
                    rec["scope"], rec["kind"], rec["name"], rec.get("tenant") or "",
                    model_id,
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
                    await self._upsert(conn, table, model_id, rec, text, h, vector)
        return len(to_embed)

    async def _upsert(
        self, conn: Any, table: str, model_id: str, rec: dict[str, Any],
        text: str, text_hash: str, vector: list[float],
    ) -> None:
        scope, kind, name = rec["scope"], rec["kind"], rec["name"]
        tenant = rec.get("tenant") or ""
        title = rec.get("title")
        snippet = rec.get("snippet") or _snippet(text)
        # One idempotent UPSERT keyed on the unique (scope, kind, name, tenant,
        # model_id): re-indexing changed text replaces embedding + body (and the
        # generated fts column recomputes) without duplicating the row.
        # ``model_id`` is IN the key on purpose — re-indexing the same record
        # under a second embedder must ADD a row, not overwrite the first
        # space's vector with one it cannot be compared to.
        await conn.execute(
            f"INSERT INTO {self._schema}.{table} "
            "(scope, kind, name, tenant, model_id, text_hash, title, snippet, "
            "body, embedding) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::vector) "
            "ON CONFLICT (scope, kind, name, tenant, model_id) DO UPDATE SET "
            "text_hash=EXCLUDED.text_hash, title=EXCLUDED.title, "
            "snippet=EXCLUDED.snippet, body=EXCLUDED.body, embedding=EXCLUDED.embedding",
            scope, kind, name, tenant, model_id, text_hash, title, snippet, text,
            _vec_literal(vector),
        )

    async def delete(self, ids: list[dict[str, Any] | tuple]) -> int:
        """Delete indexed records. Each id is a dict ``{scope, kind, name,
        tenant?}`` or a ``(scope, kind, name[, tenant])`` tuple. Returns the
        number of rows removed.

        ⭐ Sweeps EVERY dimension table and does NOT filter by ``model_id`` —
        the deliberate asymmetry with index/search. Those two are about the
        SPACE (a search must never cross one); delete is about the RECORD, and
        a record that no longer exists in the source has no business staying
        indexed in some other embedder's space where nobody is looking. The
        return is therefore a row count, not a record count: a record indexed
        under two embedders removes two rows."""
        pool = await self._get_pool()
        removed = 0
        async with pool.acquire() as conn:
            for table in await self._all_tables(conn):
                for ident in ids:
                    if isinstance(ident, dict):
                        scope, kind = ident["scope"], ident["kind"]
                        name = ident["name"]
                        tenant = ident.get("tenant") or ""
                    else:
                        scope, kind, name = ident[0], ident[1], ident[2]
                        tenant = ident[3] if len(ident) > 3 and ident[3] else ""
                    result = await conn.execute(
                        f"DELETE FROM {self._schema}.{table} "
                        "WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4",
                        scope, kind, name, tenant,
                    )
                    # asyncpg returns "DELETE <n>"
                    try:
                        removed += int(result.split()[-1])
                    except (ValueError, IndexError):  # pragma: no cover
                        pass
        return removed

    async def _all_tables(self, conn: Any) -> list[str]:
        """Every dimension table that EXISTS in this schema, for the sweeping
        delete. Reads the catalog rather than assuming: a schema migrated to a
        revision older than 0013 has none of them, and a delete against a store
        nobody has indexed into yet is a no-op, not a crash."""
        rows = await conn.fetch(
            "SELECT $1::text || t AS present FROM unnest($2::text[]) AS t "
            "WHERE to_regclass($1::text || t) IS NOT NULL",
            f"{self._schema}.",
            [search_table(d) for d in SUPPORTED_DIMS],
        )
        return [r["present"].split(".", 1)[1] for r in rows]

    # ------------------------------------------------------------------
    # search (RecordSearchProvider)
    # ------------------------------------------------------------------

    async def search(
        self, *, scope: str, query_text: str, kind: str | None = None,
        k: int = 10, tenant: str = "",
    ) -> list[dict[str, Any]]:
        """Hybrid dense+lexical search fused with RRF. Returns hits shaped
        ``{scope, kind, name, score, title?, snippet?, rank_dense?,
        rank_lexical?, similarity?, lexical_score?}`` (the port's guaranteed
        keys plus optional extras), ordered best-first. Overlay-aware:
        base ∪ overlay, overlay shadows base.

        ⚠️ ``score`` is the FUSED RRF value and is a function of RANK ALONE —
        it says where a candidate placed, never whether it belongs. i-103:
        ``similarity`` (cosine against the query, dense plane) and
        ``lexical_score`` (token-overlap strength, higher is better on BOTH
        stores) travel beside it so a caller can see the number the rank was
        derived from. Both are OPTIONAL by contract: a lexical-only hit has no
        ``similarity`` and a dense-only hit has no ``lexical_score``.

        No relevance floor is applied here and none is shipped anywhere — see
        :mod:`dna.kernel.query.relevance` for the measurement that refuses a
        constant. Filtering is the caller's policy (``kernel.search
        (min_similarity=…)``), never the store's.

        ⚠️ And whatever the caller filters on, it reads ONE embedding space:
        the table of the active width, restricted to the active ``model_id``.
        Both halves are load-bearing. Dropping the table routing would compare
        vectors of different lengths; dropping the ``model_id`` filter would
        compare vectors of the SAME length produced by different models — which
        the port's contract says are not comparable, and which no error would
        ever announce, because the ``similarity`` above would come out looking
        exactly like relevance."""
        if not query_text.strip() or k <= 0:
            return []
        table = await self._table()
        model_id = self._model_id()
        pool = await self._get_pool()
        overfetch = max(_MIN_CANDIDATES, k * _OVERFETCH)

        query_vec = (await self._kernel.embed([query_text]))[0]

        async with pool.acquire() as conn:
            # Dense plane — cosine KNN over the query embedding. Scoped to the
            # store's scope so the ANN scan stays cheap; all-zero query (no
            # tokens) skips the dense plane (its distances are meaningless).
            #
            # i-103: the DISTANCE travels with the rank. ``<=>`` is cosine
            # distance, so ``1 - distance`` is the cosine similarity defined by
            # ``kernel.query.relevance.cosine_similarity`` — the raw number the
            # rank was hiding, and the only one that carries any relevance
            # signal at all.
            #
            # s-indice-por-dimensao: ``model_id`` is in the PREDICATE, not
            # applied afterwards. A post-filter would let a foreign space's
            # vectors CROWD OUT real candidates inside the LIMIT and silently
            # shorten the result — and, worse next to i-103, it would compute a
            # ``similarity`` against a vector that is not comparable at all.
            dense_ranked: list[int] = []
            dense_sim: dict[int, float] = {}
            if any(query_vec):
                dense_rows = await conn.fetch(
                    f"SELECT id, embedding <=> $3::vector AS distance "
                    f"FROM {self._schema}.{table} "
                    "WHERE scope=$1 AND model_id=$2 AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> $3::vector LIMIT $4",
                    scope, model_id, _vec_literal(query_vec), overfetch,
                )
                dense_ranked = [r["id"] for r in dense_rows]
                dense_sim = {
                    r["id"]: 1.0 - float(r["distance"]) for r in dense_rows
                }

            # Lexical plane — tsvector match ranked by ts_rank. An empty/
            # unparseable query just contributes no lexical ranks. Filtered by
            # ``model_id`` for the same reason as the dense plane AND one more:
            # the lexical plane does not look at vectors at all, so without the
            # filter a foreign space's row would reach the fusion on words
            # alone — the leak that looks most like a legitimate hit.
            lexical_ranked: list[int] = []
            lexical_score: dict[int, float] = {}
            ts = _ts_query(query_text)
            if ts:
                lex_rows = await conn.fetch(
                    f"SELECT id, ts_rank(fts, to_tsquery('simple', $3)) AS rank "
                    f"FROM {self._schema}.{table} "
                    "WHERE scope=$1 AND model_id=$2 "
                    "AND fts @@ to_tsquery('simple', $3) "
                    "ORDER BY ts_rank(fts, to_tsquery('simple', $3)) DESC LIMIT $4",
                    scope, model_id, ts, overfetch,
                )
                lexical_ranked = [r["id"] for r in lex_rows]
                lexical_score = {r["id"]: float(r["rank"]) for r in lex_rows}

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
            meta = await self._resolve_meta(conn, table, ids)

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
                    scope, m, score, dense_pos.get(row_id), lexical_pos.get(row_id),
                    dense_sim.get(row_id), lexical_score.get(row_id),
                )
            else:
                prev_is_base = prev["_tenant"] == ""
                this_is_overlay = row_tenant != "" and row_tenant == (tenant or "")
                if this_is_overlay and prev_is_base:
                    best[key] = _hit(
                        scope, m, score, dense_pos.get(row_id),
                        lexical_pos.get(row_id),
                        dense_sim.get(row_id), lexical_score.get(row_id),
                    )

        hits = sorted(best.values(), key=lambda h: -h["score"])
        for h in hits:
            h.pop("_tenant", None)
        return hits[:k]

    async def _resolve_meta(
        self, conn: Any, table: str, ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        """Metadata for ids that the two planes ALREADY constrained.

        Deliberately NOT re-filtered by ``model_id``. A third copy of the filter
        would make the two that matter untestable: remove either plane's filter
        and this one would quietly swallow the leak, so the mutant would stay
        green while the bug it plants is real. The filter belongs where the
        candidates are chosen."""
        if not ids:
            return {}
        rows = await conn.fetch(
            f"SELECT id, scope, kind, name, tenant, title, snippet "
            f"FROM {self._schema}.{table} WHERE id = ANY($1::bigint[])",
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
            self._verified.clear()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _hit(
    scope: str, m: dict[str, Any], score: float,
    rank_dense: int | None, rank_lexical: int | None,
    similarity: float | None = None, lexical_score: float | None = None,
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
    # i-103 — the RAW scores, beside the ranks that were derived from them.
    # ``score`` above is the FUSED RRF value and is a function of rank alone:
    # it is identical for the #1 hit of a perfect match and the #1 hit of a
    # query about nothing. These two are what actually vary.
    if similarity is not None:
        hit["similarity"] = similarity
    if lexical_score is not None:
        hit["lexical_score"] = lexical_score
    return hit
