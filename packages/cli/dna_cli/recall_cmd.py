"""``dna recall`` / ``dna search`` — hybrid semantic search over the scope.

Kernel-bound, no server. Registers the embeddable ``SqliteVecRecordSearchProvider``
(the ``search-sqlite`` extra) on the local kernel, indexes the requested record
kinds on demand (idempotent by text hash), and runs ``kernel.search()`` — which
uses the registered provider (dense sqlite-vec + lexical FTS5, fused with RRF).
When the ``embed-onnx`` extra is also installed it wires the local ONNX embedder
(all-MiniLM-L6-v2) so the dense plane is REAL semantic similarity rather than the
deterministic fake-hash floor — fully offline, no external API (see
:func:`_register_embedder`).

Degrades HONESTLY: when the ``search-sqlite`` extra is not installed, it prints
a one-line notice and falls back to ``kernel.search()`` with no provider — the
kernel's lexical token-match scan (``degraded: true``). Search is a read; it
never raises on a missing extra.

    dna recall "memory similarity"                 # over every kind in the scope
    dna recall "reciprocal rank fusion" --kind Story
    dna search "banana" --scope demo -k 5 --json

``dna recall`` and ``dna search`` are aliases (recall is the memory-facing verb;
search the neutral one).
"""
from __future__ import annotations

from typing import Any

import click

from dna_cli._ctx import dna_session, print_json


def _register_embedder(kernel: Any) -> None:
    """Wire the local ONNX embedder (the ``embed-onnx`` extra) so the dense
    plane is REAL semantic similarity rather than the deterministic fake-hash
    floor.

    The floor (``FakeEmbeddingProvider``) is a bag-of-words hash — for a
    paraphrase with no shared tokens its cosine is ~0 (orthogonal), so a recall
    reporting ``semantic: true`` over it is lexical-only in disguise. The ONNX
    provider (all-MiniLM-L6-v2 via ``fastembed`` on ``onnxruntime``) gives true
    paraphrase similarity and is fully OFFLINE: the model artifact is
    fetched+cached on first embed (the Chroma pattern), never an external API at
    query time. ``OnnxEmbeddingProvider.__init__`` is lazy, so registering it
    here costs nothing until the first ``kernel.embed``.

    No-op — the kernel keeps its fake floor — when the extra is absent OR an
    embedder was already registered (respect explicit boot-time / config
    wiring). Sibling of the search-provider registration below: same
    "extra present → use it" philosophy, so the ``dna`` CLI and the MCP
    ``boot_live`` (which both route through :func:`_register_provider`) get
    offline semantic recall the moment ``dna-sdk[embed-onnx]`` is installed."""
    if getattr(kernel, "_embedding_provider", None) is not None:
        return
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return
    from dna.adapters.embedding.onnx import OnnxEmbeddingProvider

    kernel.embedding_provider(OnnxEmbeddingProvider())


def _register_provider(session: Any) -> Any | None:
    """Build + register the sqlite-vec provider on the session's kernel.
    Returns the provider, or ``None`` when the ``search-sqlite`` extra is
    absent (caller degrades to the lexical fallback).

    Also wires the local ONNX embedder (:func:`_register_embedder`) so the
    dense plane is genuinely semantic — offline, no API — when the
    ``embed-onnx`` extra is present."""
    try:
        import sqlite_vec  # noqa: F401
    except ImportError:
        return None
    import os
    from pathlib import Path

    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider

    kernel = session.kernel
    # Store lives beside the source (a `.dna-search/` sibling of `.dna/`), so
    # re-runs reuse the index (hash-skip). Overridable via DNA_SEARCH_DIR.
    search_dir = os.getenv("DNA_SEARCH_DIR")
    if not search_dir:
        base = getattr(getattr(kernel, "_source", None), "base_dir", None) or ".dna"
        base_path = Path(base)
        parent = base_path.parent if base_path.name == ".dna" else base_path
        search_dir = str(parent / ".dna-search")
    provider = SqliteVecRecordSearchProvider(kernel, db_dir=search_dir)
    kernel.record_search_provider(provider)
    # Upgrade the dense plane from the fake floor to real offline embeddings
    # when the local ONNX stack is installed (no-op otherwise).
    _register_embedder(kernel)
    return provider


def _scope_kinds(session: Any) -> list[str]:
    """The record kinds present in the scope (from the built instance)."""
    mi = session.mi
    kinds: list[str] = []
    for doc in getattr(mi, "documents", []) or []:
        if doc.kind not in kinds:
            kinds.append(doc.kind)
    return kinds


async def _index_kinds(
    session: Any, provider: Any, scope: str, kinds: list[str], tenant: str | None,
) -> int:
    from dna.adapters.search.sqlite_vec import document_text

    kernel = session.kernel
    records: list[dict[str, Any]] = []
    for kind in kinds:
        async for raw in kernel.query(scope, kind, tenant=tenant):
            meta = raw.get("metadata") or {}
            name = meta.get("name") or raw.get("name")
            if not name:
                continue
            records.append({
                "scope": scope, "kind": kind, "name": name,
                "tenant": tenant or "",
                "text": document_text(raw),
                "title": (raw.get("spec") or {}).get("title") or name,
            })
    if not records:
        return 0
    return await provider.index(records)


@click.command(name="recall")
@click.argument("query")
@click.option("--scope", default=None, help="Scope to search (default: first/only scope).")
@click.option("--kind", "kinds", multiple=True, help="Restrict to a record kind (repeatable). Default: every kind in the scope.")
@click.option("--tenant", default=None, help="Tenant overlay (base ∪ overlay; overlay shadows base).")
@click.option("-k", "--limit", "k", default=10, show_default=True, help="Max hits.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def recall(
    query: str, scope: str | None, kinds: tuple[str, ...],
    tenant: str | None, k: int, as_json: bool,
) -> None:
    """Hybrid semantic search (dense + lexical + RRF) over the scope's records."""
    with dna_session(scope) as s:
        provider = _register_provider(s)
        target_scope = s.scope
        kind_list = list(kinds) or _scope_kinds(s)

        # Single-kind search keeps the kernel's lexical fallback meaningful when
        # the provider is absent (the fallback requires a kind); the provider
        # itself searches across all indexed kinds regardless.
        single_kind = kind_list[0] if len(kind_list) == 1 else None

        if provider is not None:
            try:
                s.run(_index_kinds(s, provider, target_scope, kind_list, tenant))
            except Exception as exc:  # noqa: BLE001 — indexing failure degrades to lexical
                click.secho(f"⚠ index failed ({exc}); lexical fallback", fg="yellow", err=True)
        else:
            click.secho(
                "⚠ search-sqlite extra not installed — degrading to lexical "
                "scan (pip install 'dna-sdk[search-sqlite]' for semantic recall)",
                fg="yellow", err=True,
            )

        result = s.run(s.kernel.search(
            target_scope, query, kind=single_kind, k=k, tenant=tenant,
        ))
        if provider is not None:
            provider.close()

    hits = result.get("hits", [])
    degraded = result.get("degraded", False)
    if as_json:
        print_json({"query": query, "scope": target_scope, "degraded": degraded, "hits": hits})
        return

    mode = "lexical (degraded)" if degraded else "hybrid (dense+lexical+RRF)"
    click.secho(f"\n🔎 {mode} · scope={target_scope} · '{query}'", bold=True)
    if not hits:
        click.echo("  (no matches)")
        return
    for i, h in enumerate(hits, 1):
        score = h.get("score", 0.0)
        line = f"  {i:>2}. {h.get('kind','?')}/{h.get('name','?')}  ({score:.4f})"
        click.echo(line)
        snippet = h.get("snippet")
        if snippet:
            click.secho(f"      {snippet}", fg="bright_black")


# ``dna search`` — neutral alias of the same command.
@click.command(name="search")
@click.argument("query")
@click.option("--scope", default=None)
@click.option("--kind", "kinds", multiple=True)
@click.option("--tenant", default=None)
@click.option("-k", "--limit", "k", default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def search(ctx: click.Context, **kwargs: Any) -> None:
    """Alias of ``dna recall`` (neutral naming)."""
    ctx.invoke(recall, **kwargs)
