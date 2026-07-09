"""SqliteVecRecordSearchProvider — the embeddable default RecordSearchProvider.

rsh-memory-similarity-evolution → rec-embeddable-provider. The FIRST real
implementation of the ``RecordSearchProvider`` port (the kernel shipped only
the port + an honest lexical fallback). Hybrid search entirely inside one
SQLite file per scope, offline, no server:

  * dense plane   — sqlite-vec ``vec0`` KNN over ``kernel.embed()`` vectors
                    (the deterministic ``FakeEmbeddingProvider`` floor by
                    default; any registered ``EmbeddingPort`` transparently).
  * lexical plane — FTS5 BM25 over the same text.
  * fusion        — Reciprocal Rank Fusion (``rrf.reciprocal_rank_fusion``, a
                    pure function shared with the TS twin and any future
                    pgvector provider).

The store schema is OWNED by the shared migration contract (``migrations.py`` +
``adapters/_migrations.run_migrations``) — closing f-embeddings-ddl-debt.

Overlay/tenant-aware: one ``.db`` per scope, ``tenant`` a column ('' = base).
A tenant search reads base ∪ overlay and the overlay row shadows the base row
for the same ``(kind, name)`` — mirroring the source reader's overlay merge.

Parity: the TS twin is ``src/adapters/search/sqlite-vec.ts`` (same tables, same
RRF, same overlay-shadow); both are exercised by the shared
``record_search_conformance_suite`` with the fake embedder, offline.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import struct
from pathlib import Path
from typing import Any, Iterable

from dna.adapters.search.rrf import DEFAULT_RRF_K, reciprocal_rank_fusion

logger = logging.getLogger(__name__)

#: How many candidates to pull from each plane before fusing + filtering. The
#: over-fetch absorbs attrition from the kind/tenant/overlay filter (which runs
#: AFTER ranking) so the final top-k is stable. Scales with the requested k.
_OVERFETCH = 4
_MIN_CANDIDATES = 40


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec loadable extension into ``conn``. The ``sqlite-vec``
    pip package bundles the platform extension + a ``load`` helper."""
    try:
        import sqlite_vec
    except ImportError as exc:  # pragma: no cover — exercised via the extra
        raise ImportError(
            "SqliteVecRecordSearchProvider needs the 'search-sqlite' extra: "
            "pip install 'dna-sdk[search-sqlite]'"
        ) from exc
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def _serialize_f32(vector: Iterable[float]) -> bytes:
    """Pack a float vector into sqlite-vec's compact float32 blob layout."""
    vec = list(vector)
    return struct.pack(f"{len(vec)}f", *vec)


def document_text(raw: dict[str, Any]) -> str:
    """Derive the searchable text blob for a raw document.

    Walks the doc's ``spec`` (and top-level ``metadata.name``) collecting every
    STRING value, in document order — the same "string values only" discipline
    the kernel's lexical fallback uses, so dense/lexical see the same corpus.
    Callers may override by passing an explicit ``text`` to ``index``.
    """
    parts: list[str] = []
    meta = raw.get("metadata") or {}
    name = meta.get("name") or raw.get("name")
    if isinstance(name, str):
        parts.append(name)

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                _walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                _walk(value)

    _walk(raw.get("spec") or {})
    return "\n".join(p for p in parts if p)


class SqliteVecRecordSearchProvider:
    """``RecordSearchProvider`` backed by sqlite-vec + FTS5 + RRF.

    Construct with the kernel (for ``embed``) and either a ``db_dir`` (one
    ``<scope>.db`` per scope, the production shape) or an explicit ``db_path``
    (a single file — handy for tests). Register via
    ``kernel.record_search_provider(provider)``.
    """

    def __init__(
        self,
        kernel: Any,
        *,
        db_dir: str | os.PathLike[str] | None = None,
        db_path: str | os.PathLike[str] | None = None,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        if db_dir is None and db_path is None:
            db_dir = os.getenv("DNA_SEARCH_DIR") or ".dna-search"
        self._kernel = kernel
        self._db_dir = Path(db_dir) if db_dir is not None else None
        self._single_path = Path(db_path) if db_path is not None else None
        self._rrf_k = rrf_k
        self._conns: dict[str, sqlite3.Connection] = {}

    # ------------------------------------------------------------------
    # store / schema (migration-owned)
    # ------------------------------------------------------------------

    def _path_for(self, scope: str) -> Path:
        if self._single_path is not None:
            return self._single_path
        assert self._db_dir is not None
        self._db_dir.mkdir(parents=True, exist_ok=True)
        safe = scope.replace(os.sep, "_").replace("/", "_")
        return self._db_dir / f"{safe}.db"

    async def _conn_for(self, scope: str) -> sqlite3.Connection:
        """Open (once per store path) a connection with sqlite-vec loaded and
        the schema migrated + identity-pinned. Cached for the provider's life.

        Async because the shared migration runner is async-shaped; the sqlite3
        work inside the callbacks is synchronous and stays on this thread/loop
        (no cross-thread connection use)."""
        path = str(self._path_for(scope))
        conn = self._conns.get(path)
        if conn is not None:
            return conn
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        _load_sqlite_vec(conn)
        await self._migrate(conn)
        self._pin_identity(conn)
        self._conns[path] = conn
        return conn

    async def _migrate(self, conn: sqlite3.Connection) -> list[int]:
        """Apply pending migrations through the shared forward-only runner —
        the search store's schema has a real owner (closes f-embeddings-ddl-debt)."""
        from dna.adapters._migrations import run_migrations
        from dna.adapters.search.migrations import build_migrations

        dims = int(self._kernel.embedding_dims)
        migrations = build_migrations(dims)

        async def ensure_control_table() -> None:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            conn.commit()

        async def fetch_applied() -> list[int]:
            return [r["version"] for r in conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()]

        async def apply_version(version: int, script: str) -> None:
            conn.executescript(script)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _now()),
            )
            conn.commit()

        return await run_migrations(
            migrations,
            ensure_control_table=ensure_control_table,
            fetch_applied=fetch_applied,
            apply_version=apply_version,
            dialect="SQLite(search)",
        )

    def _pin_identity(self, conn: sqlite3.Connection) -> None:
        """Refuse to reuse a store built for a different embedding space —
        mixing vectors from different (dims, model_id) is silently wrong."""
        dims = str(int(self._kernel.embedding_dims))
        model_id = str(self._kernel.embedding_model_id)
        rows = {r["key"]: r["value"] for r in conn.execute(
            "SELECT key, value FROM search_meta"
        ).fetchall()}
        if not rows:
            conn.executemany(
                "INSERT INTO search_meta (key, value) VALUES (?, ?)",
                [("embedding_dims", dims), ("embedding_model_id", model_id)],
            )
            conn.commit()
            return
        if rows.get("embedding_dims") != dims or rows.get("embedding_model_id") != model_id:
            raise ValueError(
                "search store was built for embedding space "
                f"({rows.get('embedding_model_id')}, dims={rows.get('embedding_dims')}) "
                f"but the active provider is ({model_id}, dims={dims}) — "
                "the vectors are incomparable. Use a fresh store dir or re-index."
            )

    # ------------------------------------------------------------------
    # index / delete
    # ------------------------------------------------------------------

    async def index(self, records: list[dict[str, Any]]) -> int:
        """Index (upsert) records into their scope's store.

        Each record: ``{scope, kind, name, tenant?, text?, raw?, title?,
        snippet?}``. ``text`` is used verbatim if present; otherwise it is
        derived from ``raw`` via :func:`document_text`. Idempotent by text
        hash — re-indexing unchanged text is skipped (no re-embed). Returns
        the number of records actually (re)embedded.
        """
        if not records:
            return 0
        # Group by scope so each store is touched once; embed in one batch.
        pending: list[tuple[dict[str, Any], str, str]] = []  # (rec, text, hash)
        for rec in records:
            text = rec.get("text")
            if text is None:
                text = document_text(rec.get("raw") or {})
            text = text or ""
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            pending.append((rec, text, h))

        # Decide which need (re)embedding — skip rows whose hash is unchanged.
        to_embed: list[tuple[dict[str, Any], str, str]] = []
        for rec, text, h in pending:
            conn = await self._conn_for(rec["scope"])
            existing = conn.execute(
                "SELECT text_hash FROM search_docs "
                "WHERE scope=? AND kind=? AND name=? AND tenant=?",
                (rec["scope"], rec["kind"], rec["name"], rec.get("tenant") or ""),
            ).fetchone()
            if existing is not None and existing["text_hash"] == h:
                continue
            to_embed.append((rec, text, h))

        if not to_embed:
            return 0

        vectors = await self._kernel.embed([t for _, t, _ in to_embed])
        for (rec, text, h), vector in zip(to_embed, vectors):
            self._upsert(rec, text, h, vector)
        for scope in {rec["scope"] for rec, _, _ in to_embed}:
            self._cached_conn(scope).commit()
        return len(to_embed)

    def _cached_conn(self, scope: str) -> sqlite3.Connection:
        """The already-open connection for ``scope`` (opened by ``_conn_for``
        earlier in the same async call). Sync helpers use this so they never
        need to await."""
        return self._conns[str(self._path_for(scope))]

    def _upsert(
        self, rec: dict[str, Any], text: str, text_hash: str, vector: list[float],
    ) -> None:
        conn = self._cached_conn(rec["scope"])
        scope, kind, name = rec["scope"], rec["kind"], rec["name"]
        tenant = rec.get("tenant") or ""
        title = rec.get("title")
        snippet = rec.get("snippet") or _snippet(text)
        # Upsert metadata; capture the stable rowid for the virtual tables.
        row = conn.execute(
            "SELECT rowid FROM search_docs "
            "WHERE scope=? AND kind=? AND name=? AND tenant=?",
            (scope, kind, name, tenant),
        ).fetchone()
        if row is None:
            cur = conn.execute(
                "INSERT INTO search_docs "
                "(scope, kind, name, tenant, text_hash, title, snippet, text) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (scope, kind, name, tenant, text_hash, title, snippet, text),
            )
            rowid = cur.lastrowid
        else:
            rowid = row["rowid"]
            conn.execute(
                "UPDATE search_docs SET text_hash=?, title=?, snippet=?, text=? "
                "WHERE rowid=?",
                (text_hash, title, snippet, text, rowid),
            )
            conn.execute("DELETE FROM search_vec WHERE doc_rowid=?", (rowid,))
            conn.execute("DELETE FROM search_fts WHERE rowid=?", (rowid,))
        conn.execute(
            "INSERT INTO search_vec (doc_rowid, embedding) VALUES (?, ?)",
            (rowid, _serialize_f32(vector)),
        )
        conn.execute(
            "INSERT INTO search_fts (rowid, text) VALUES (?, ?)", (rowid, text),
        )

    async def delete(self, ids: list[dict[str, Any] | tuple]) -> int:
        """Delete indexed records. Each id is a dict ``{scope, kind, name,
        tenant?}`` or a ``(scope, kind, name[, tenant])`` tuple. Returns the
        number of rows removed."""
        removed = 0
        touched: set[str] = set()
        for ident in ids:
            if isinstance(ident, dict):
                scope, kind, name = ident["scope"], ident["kind"], ident["name"]
                tenant = ident.get("tenant") or ""
            else:
                scope, kind, name = ident[0], ident[1], ident[2]
                tenant = ident[3] if len(ident) > 3 and ident[3] else ""
            conn = await self._conn_for(scope)
            row = conn.execute(
                "SELECT rowid FROM search_docs "
                "WHERE scope=? AND kind=? AND name=? AND tenant=?",
                (scope, kind, name, tenant),
            ).fetchone()
            if row is None:
                continue
            rowid = row["rowid"]
            conn.execute("DELETE FROM search_vec WHERE doc_rowid=?", (rowid,))
            conn.execute("DELETE FROM search_fts WHERE rowid=?", (rowid,))
            conn.execute("DELETE FROM search_docs WHERE rowid=?", (rowid,))
            removed += 1
            touched.add(scope)
        for scope in touched:
            self._cached_conn(scope).commit()
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
        conn = await self._conn_for(scope)
        overfetch = max(_MIN_CANDIDATES, k * _OVERFETCH)

        # Dense plane — vec0 KNN over the query embedding.
        query_vec = (await self._kernel.embed([query_text]))[0]
        dense_ranked: list[int] = []
        if any(query_vec):  # all-zero query (no tokens) → skip dense plane
            dense_ranked = [r["doc_rowid"] for r in conn.execute(
                "SELECT doc_rowid FROM search_vec "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (_serialize_f32(query_vec), overfetch),
            ).fetchall()]

        # Lexical plane — FTS5 BM25. An unparseable MATCH query is not an error;
        # it just contributes no lexical ranks.
        lexical_ranked: list[int] = []
        fts_query = _fts_query(query_text)
        if fts_query:
            try:
                lexical_ranked = [r["rowid"] for r in conn.execute(
                    "SELECT rowid FROM search_fts "
                    "WHERE search_fts MATCH ? ORDER BY bm25(search_fts) LIMIT ?",
                    (fts_query, overfetch),
                ).fetchall()]
            except sqlite3.OperationalError:
                lexical_ranked = []

        if not dense_ranked and not lexical_ranked:
            return []

        # Fuse ranks (RRF is pure + string-keyed → stringify rowids).
        fused = reciprocal_rank_fusion(
            [[str(r) for r in dense_ranked], [str(r) for r in lexical_ranked]],
            k=self._rrf_k,
        )
        dense_pos = {r: i + 1 for i, r in enumerate(dense_ranked)}
        lexical_pos = {r: i + 1 for i, r in enumerate(lexical_ranked)}

        # Resolve metadata + apply kind/tenant filter with overlay shadowing.
        rowids = [int(rid) for rid, _ in fused]
        meta = self._resolve_meta(conn, rowids)
        best: dict[tuple[str, str], dict[str, Any]] = {}
        for rid, score in fused:
            rowid = int(rid)
            m = meta.get(rowid)
            if m is None:
                continue
            if kind is not None and m["kind"] != kind:
                continue
            row_tenant = m["tenant"] or ""
            if row_tenant not in ("", tenant or ""):
                continue  # a different tenant's overlay — never leaks
            key = (m["kind"], m["name"])
            prev = best.get(key)
            # Overlay (matching tenant) shadows base (''); otherwise higher
            # fused score wins.
            if prev is None:
                best[key] = _hit(scope, m, score, dense_pos.get(rowid), lexical_pos.get(rowid))
            else:
                prev_is_base = prev["_tenant"] == ""
                this_is_overlay = row_tenant != "" and row_tenant == (tenant or "")
                if this_is_overlay and prev_is_base:
                    best[key] = _hit(scope, m, score, dense_pos.get(rowid), lexical_pos.get(rowid))

        hits = sorted(best.values(), key=lambda h: -h["score"])
        for h in hits:
            h.pop("_tenant", None)
        return hits[:k]

    def _resolve_meta(
        self, conn: sqlite3.Connection, rowids: list[int],
    ) -> dict[int, sqlite3.Row]:
        if not rowids:
            return {}
        placeholders = ",".join("?" * len(rowids))
        rows = conn.execute(
            f"SELECT rowid, scope, kind, name, tenant, title, snippet "
            f"FROM search_docs WHERE rowid IN ({placeholders})",
            rowids,
        ).fetchall()
        return {r["rowid"]: r for r in rows}

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        for conn in self._conns.values():
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        self._conns.clear()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _snippet(text: str, max_len: int = 200) -> str:
    flat = " ".join(text.split())
    return flat[:max_len] + ("…" if len(flat) > max_len else "")


def _hit(
    scope: str, m: sqlite3.Row, score: float,
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


def _fts_query(query_text: str) -> str:
    """Turn free text into a safe FTS5 MATCH query: OR of the alphanumeric
    tokens, each quoted so FTS5 never interprets a token as an operator."""
    import re
    tokens = re.findall(r"[a-z0-9]+", query_text.lower())
    return " OR ".join(f'"{t}"' for t in tokens)
