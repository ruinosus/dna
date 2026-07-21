"""Memory verbs — remember / recall / forget / consolidate.

Memory in DNA is NOT a new subsystem: it is the Kinds DNA already has
(Engram, Research, Evidence) written + recalled through the SAME
kernel + RecordSearchProvider that everything else uses. These four verbs
formalize the lifecycle over those Kinds. The scoring is the deterministic
pure core (``dna.memory.{ecphory,retrieval,decay,...}``); the LLM scribes /
schedulers / deep-sleep / workers that lived next to it upstream are
DELIBERATELY out — those are a service, not the SDK.

- ``remember`` — write the Kind + stamp deterministic encoding-context +
  classify CoALA memory_type + set bi-temporal ``valid_from``; index into the
  registered search provider (when one is registered) so a later ``recall``
  finds it.
- ``recall``   — ``kernel.search()`` (hybrid when a provider is registered,
  honest lexical fallback otherwise), overlay/tenant-aware, bi-temporal
  (excludes memories whose ``valid_to`` is in the past), re-scored by
  Ebbinghaus retention × affect for memory hits, with a light reconsolidation
  side-effect (cues_history append + confidence bump), fail-soft.
- ``forget``   — bi-temporal DEMOTION: set ``valid_to`` (+ optional
  ``superseded_by_memory``). NEVER hard-delete.
- ``consolidate`` — a deterministic decay pass (NO LLM): recompute retention,
  report/soft-archive stale memories. LLM-driven consolidation is external.

s-memory-verbs (2026-07-09).
"""
from __future__ import annotations

import copy
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from dna.memory.decay import (
    affect_factor,
    currently_valid,
    days_since,
    decay_adjusted_score,
    stability_from_spec,
)
from dna.memory.ecphory import EngramRef
from dna.memory.encoding_context import stamp_encoding_context_if_absent
from dna.memory.memory_type import classify_memory_type
from dna.memory.personal import is_personal_tenant
from dna.memory.semantic import (
    engram_text,
    fuse_semantic_recall,
    semantic_scores_from_vectors,
)

logger = logging.getLogger(__name__)

#: The record Kinds that carry memory. Engram is the rich, affective,
#: bi-temporal engram; Research + Evidence are recall-able knowledge artifacts.
MEMORY_KINDS: tuple[str, ...] = ("Engram", "Research", "Evidence")


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def _resolve_api_version(kernel: Any, kind: str) -> str | None:
    """Best-effort api_version for a Kind from the kernel registry."""
    kinds = getattr(kernel, "_kinds", {}) or {}
    for kp in kinds.values():
        if getattr(kp, "kind", None) == kind:
            return getattr(kp, "api_version", None)
    return None


def _provider(kernel: Any) -> Any | None:
    return getattr(kernel, "_search_provider", None)


async def _index_doc(
    kernel: Any, scope: str, kind: str, name: str, spec: dict[str, Any],
    tenant: str | None,
) -> None:
    """Index one written memory into the registered provider (best-effort).
    No provider registered → no-op (recall degrades to lexical)."""
    prov = _provider(kernel)
    if prov is None:
        return
    try:
        from dna.adapters.search.sqlite_vec import document_text
        raw = {"metadata": {"name": name}, "spec": spec}
        await prov.index([{
            "scope": scope, "kind": kind, "name": name,
            "tenant": tenant or "",
            "text": document_text(raw),
            "title": spec.get("title") or spec.get("summary") or name,
        }])
    except Exception as exc:  # noqa: BLE001 — indexing is best-effort
        logger.warning("memory.remember: index failed for %s/%s: %s", kind, name, exc)


# ─────────────────────────── remember ───────────────────────────


async def remember(
    kernel: Any,
    scope: str,
    *,
    kind: str = "Engram",
    name: str,
    spec: dict[str, Any],
    tenant: str | None = None,
    index: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist a memory Kind + deterministic enrichment + index.

    Enrichment (Engram only, idempotent): stamp ``encoding_context`` if
    absent, classify ``memory_type`` if absent, seed ``valid_from`` = created_at.
    Then ``kernel.write_document`` (which runs the bi-temporal guard + hooks)
    and — when a search provider is registered — index the doc so ``recall``
    finds it. Returns ``{kind, name, spec, indexed}``.
    """
    if kind not in MEMORY_KINDS:
        raise ValueError(f"remember: {kind!r} is not a memory Kind {MEMORY_KINDS}")
    spec = dict(spec)  # never mutate the caller's dict
    now_iso = _now_iso(now)
    spec.setdefault("created_at", now_iso)

    if kind == "Engram":
        stamp_encoding_context_if_absent(spec)
        if not spec.get("memory_type"):
            spec["memory_type"] = classify_memory_type(spec)
        # Bi-temporal: world-time validity starts at creation unless given.
        spec.setdefault("valid_from", spec.get("created_at", now_iso))

    raw: dict[str, Any] = {"kind": kind, "metadata": {"name": name}, "spec": spec}
    api_version = _resolve_api_version(kernel, kind)
    if api_version:
        raw["apiVersion"] = api_version

    write_kernel = (
        kernel.with_tenant(tenant, allow_personal=is_personal_tenant(tenant))
        if tenant else kernel
    )
    await write_kernel.write_document(scope, kind, name, raw, invalidate_mode="doc")

    indexed = False
    if index:
        await _index_doc(kernel, scope, kind, name, spec, tenant)
        indexed = _provider(kernel) is not None
    return {"kind": kind, "name": name, "spec": spec, "indexed": indexed}


async def backfill_index(
    kernel: Any,
    scope: str,
    *,
    kinds: tuple[str, ...] | list[str] = MEMORY_KINDS,
    tenant: str | None = None,
) -> int:
    """Lazy-backfill the search index for memories that predate the provider.

    ``remember`` embeds on write, but memories written before a provider was
    registered — or recalled on a machine whose local ``.dna-search/`` store
    does not exist yet — have no vector. This is the deliberate migration
    story: instead of a schema migration, (re)index every memory Kind doc into
    the registered provider ON DEMAND. Idempotent by text hash (the provider
    skips unchanged docs — no re-embed), so calling it before every recall is
    cheap. Returns the number of records actually (re)embedded; no provider
    registered → 0 (recall stays lexical).
    """
    prov = _provider(kernel)
    if prov is None:
        return 0
    from dna.adapters.search.sqlite_vec import document_text

    records: list[dict[str, Any]] = []
    for kind in kinds:
        async for raw in kernel.query(scope, kind, tenant=tenant):
            name = (raw.get("metadata") or {}).get("name") or raw.get("name")
            if not name:
                continue
            spec = raw.get("spec") or {}
            records.append({
                "scope": scope, "kind": kind, "name": name,
                "tenant": tenant or "",
                "text": document_text(raw),
                "title": spec.get("title") or spec.get("summary") or name,
            })
    if not records:
        return 0
    return int(await prov.index(records))


# ─────────────────────────── recall ───────────────────────────

#: The spec fields recall projects onto each hit for DISPLAY (i-068). The hits
#: were pointers (``{scope,kind,name,score,title?,snippet?}``); a UI rendering
#: them had nothing to show. ``recall`` already loads every hit's spec for the
#: bi-temporal filter + decay re-score, so projecting these is zero extra I/O.
_DISPLAY_FIELDS: tuple[str, ...] = ("summary", "area", "affect", "tags")


def memory_created_at(spec: dict[str, Any]) -> str | None:
    """A memory's display timestamp: ``created_at``, else the bi-temporal
    ``valid_from`` seed, else the first reconsolidation cue's ``at`` — the SAME
    fallback chain ``list_memories`` uses, factored here so the recall hits and
    the list surface can never disagree about when a memory was born."""
    created = spec.get("created_at") or spec.get("valid_from")
    if not created:
        history = spec.get("cues_history") or []
        if isinstance(history, list) and history and isinstance(history[0], dict):
            created = history[0].get("at")
    return created


def _attach_display_fields(hit: dict[str, Any], spec: dict[str, Any]) -> None:
    """Project the display fields from the (already loaded) spec onto the hit.

    STRICTLY ADDITIVE: existing keys on the hit are never overwritten (a
    provider-supplied ``title``/``snippet`` wins), and a field the spec does not
    carry is simply absent — never fabricated. Lives here, ABOVE the search
    providers, so pgvector, sqlite-vec AND the lexical fallback all enrich at
    the same single point (the providers' hit contract is untouched)."""
    if not spec:
        return
    for field in _DISPLAY_FIELDS:
        value = spec.get(field)
        if value is None or field in hit:
            continue
        hit[field] = list(value) if field == "tags" else value
    if "created_at" not in hit:
        created = memory_created_at(spec)
        if created:
            hit["created_at"] = created
    if "title" not in hit:
        title = spec.get("title") or spec.get("summary")
        if title:
            hit["title"] = title


async def is_personal_doc(
    kernel: Any, scope: str, kind: str, name: str,
    spec: dict[str, Any], tenant: str | None,
) -> bool:
    """Whether this doc resolves from the caller's PERSONAL partition — the
    per-ITEM flag (i-068). A personal read unions the shared base with the
    ``personal:<oid>`` overlay, so "is it personal" is a property of each item,
    never of the call.

    The merged read cannot answer it (the source's overlay merge keeps no
    per-row provenance), so this asks the store the one question that does:
    does the doc exist in the BASE layer, unchanged? Absent from base → it can
    only have come from the personal overlay. Present but different → the
    overlay shadows it (the returned spec IS the personal copy). Present and
    identical → shared base content, not personal. Uses the SAME cached
    ``get_document`` primitive ``recall`` already reads through. Fail-soft:
    an errored base probe reports False (display flag; never breaks a read).
    """
    if not is_personal_tenant(tenant) or not spec:
        return False
    try:
        base = await kernel.get_document(scope, kind, name, tenant=None)
    except Exception:  # noqa: BLE001 — a display flag must never break recall
        return False
    if base is None:
        return True
    return (base.get("spec") or {}) != spec


async def _load_spec(
    kernel: Any, scope: str, kind: str, name: str, tenant: str | None,
) -> dict[str, Any]:
    """Load a doc's spec (deep-copied — the L2 cache hands back a shared ref)."""
    try:
        raw = await kernel.get_document(scope, kind, name, tenant=tenant)
    except Exception:  # noqa: BLE001
        return {}
    if not raw:
        return {}
    return copy.deepcopy(raw.get("spec") or {})


async def recall(
    kernel: Any,
    scope: str,
    query: str,
    *,
    kinds: tuple[str, ...] | list[str] = MEMORY_KINDS,
    tenant: str | None = None,
    k: int = 5,
    reconsolidate: bool = True,
    actor: str = "anonymous",
    semantic: bool | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Hybrid recall over the memory Kinds, bi-temporal + retention re-scored.

    Runs ``kernel.search()`` per memory Kind (provider-backed when registered;
    honest lexical fallback otherwise — search never raises), loads each hit's
    spec, DROPS memories whose ``valid_to`` is in the past (bi-temporal
    correctness — a forgotten/superseded memory never resurfaces), then
    re-ranks memory hits by ``search_score × retention × affect`` (Ebbinghaus
    decay + evocative palette).

    **Semantic recall (s-memory-semantic-recall):** ``semantic=None`` (auto)
    turns the semantic plane on when a search provider is registered; ``True``
    forces it (``kernel.embed`` always resolves — deterministic fake floor),
    ``False`` disables it. When active, the cue + every candidate are embedded
    in ONE ``kernel.embed`` batch, the per-memory cosine feeds the ecphory
    ranking (``score_engram`` Path 3 — the hook that was inert until this
    story), and the ecphory + recall rankings are fused with RRF
    (:func:`dna.memory.semantic.fuse_semantic_recall`). Fail-soft: an embed
    failure keeps the base ranking (and reports ``semantic: False``). When
    inactive, ranking and hit shape are IDENTICAL to the pre-semantic behavior
    (offline-first, zero breaking change).

    When ``reconsolidate`` is on, each surfaced memory gets a cues_history
    append + a small confidence bump (Nader light reconsolidation) via
    ``kernel.write_document`` — fail-soft.

    Returns ``{query, scope, degraded, semantic, hits:[{kind,name,score,
    retention?,semantic?,rank_recall?,rank_ecphory?,...}]}``. Each hit is
    additionally enriched for DISPLAY (i-068): ``summary``/``area``/``affect``/
    ``tags``/``created_at``/``title`` projected from the already-loaded spec
    (present only when the spec carries them; a provider-supplied ``title``/
    ``snippet`` is never overwritten), plus ``personal: bool`` — the per-ITEM
    flag telling whether the hit resolves from the caller's ``personal:<oid>``
    partition rather than the shared base it is unioned with.
    """
    now_dt = now or datetime.now(timezone.utc)
    overfetch = max(k * 3, 10)
    degraded = False
    merged: list[dict[str, Any]] = []
    for kind in kinds:
        try:
            res = await kernel.search(scope, query, kind=kind, k=overfetch, tenant=tenant)
        except Exception:  # noqa: BLE001 — recall is a read; never breaks
            continue
        degraded = degraded or bool(res.get("degraded"))
        for hit in res.get("hits", []):
            hit = dict(hit)
            hit.setdefault("kind", kind)
            merged.append(hit)

    scored: list[dict[str, Any]] = []
    spec_by_name: dict[str, dict[str, Any]] = {}
    for hit in merged:
        kind = hit.get("kind")
        name = hit.get("name")
        if not name:
            continue
        spec = await _load_spec(kernel, scope, kind, name, tenant)
        # Bi-temporal filter — a memory invalidated in the past never surfaces.
        if not currently_valid(spec.get("valid_to"), now=now_dt):
            continue
        base = float(hit.get("score", 0.0) or 0.0)
        if kind == "Engram" and spec:
            adjusted, retention = decay_adjusted_score(base, spec, now=now_dt)
            adjusted *= affect_factor(spec.get("affect"))
            hit["score"] = adjusted
            hit["retention"] = round(retention, 4)
        # i-068: display enrichment + the per-item personal flag — additive,
        # zero extra I/O for the fields (the spec is already in hand) and one
        # CACHED base probe per hit only on a personal-partition recall.
        _attach_display_fields(hit, spec)
        hit["personal"] = await is_personal_doc(kernel, scope, kind, name, spec, tenant)
        scored.append(hit)
        spec_by_name.setdefault(str(name), spec)

    scored.sort(key=lambda h: (-float(h.get("score", 0.0) or 0.0), h.get("name", "")))

    semantic_active = semantic is True or (semantic is None and _provider(kernel) is not None)
    if semantic_active and scored:
        try:
            scored = await _semantic_rerank(kernel, scored, spec_by_name, query, now_dt)
        except Exception:  # noqa: BLE001 — the semantic plane is additive; degrade honestly
            logger.warning("recall: semantic plane failed; keeping base ranking", exc_info=True)
            semantic_active = False

    top = scored[:k]

    if reconsolidate:
        await _reconsolidate(kernel, scope, top, query, actor, tenant, now_dt)

    return {
        "query": query, "scope": scope,
        "degraded": degraded, "semantic": semantic_active,
        "hits": top,
    }


async def _semantic_rerank(
    kernel: Any,
    scored: list[dict[str, Any]],
    spec_by_name: dict[str, dict[str, Any]],
    query: str,
    now: datetime,
) -> list[dict[str, Any]]:
    """The kernel-bound half of semantic recall: ONE ``kernel.embed`` batch for
    the cue + every candidate's semantic payload
    (:func:`dna.memory.semantic.engram_text` — area/title/summary/body, the
    same planes ecphory scores), cosine per memory, then the pure fusion
    (:func:`dna.memory.semantic.fuse_semantic_recall`)."""
    names = list(spec_by_name.keys())
    engrams = [EngramRef(name, spec_by_name[name]) for name in names]
    texts = [engram_text(spec_by_name[name]) for name in names]
    vectors = await kernel.embed([query] + texts)
    sem_scores = semantic_scores_from_vectors(names, vectors[1:], vectors[0])
    return fuse_semantic_recall(scored, engrams, query, sem_scores, now=now)


async def _reconsolidate(
    kernel: Any, scope: str, hits: list[dict[str, Any]],
    cue: str, actor: str, tenant: str | None, now: datetime,
) -> None:
    """Append cue + bump confidence on surfaced Engram memories.
    Read-modify-write with a deep copy; fail-soft per doc. Nader (2000) light
    reconsolidation: recall reawakens the engram and reinforces it."""
    now_iso = _now_iso(now)
    write_kernel = (
        kernel.with_tenant(tenant, allow_personal=is_personal_tenant(tenant))
        if tenant else kernel
    )
    for hit in hits:
        if hit.get("kind") != "Engram":
            continue
        name = hit.get("name")
        try:
            spec = await _load_spec(kernel, scope, "Engram", name, tenant)
            if not spec:
                continue
            cues = list(spec.get("cues_history") or [])
            cues.append({"at": now_iso, "cue": (cue or "")[:120], "actor": actor or "unknown"})
            spec["cues_history"] = cues[-50:]
            spec["last_surfaced"] = now_iso
            spec["surface_count"] = int(spec.get("surface_count") or 0) + 1
            old = spec.get("confidence_score")
            if isinstance(old, (int, float)):
                spec["confidence_score"] = round(min(10.0, float(old) + 0.05), 3)
            raw = {"kind": "Engram", "metadata": {"name": name}, "spec": spec}
            api_version = _resolve_api_version(kernel, "Engram")
            if api_version:
                raw["apiVersion"] = api_version
            await write_kernel.write_document(
                scope, "Engram", name, raw, invalidate_mode="doc",
            )
        except Exception as exc:  # noqa: BLE001 — recall must not fail on a bump hiccup
            logger.warning("recall reconsolidation failed for %s: %s", name, exc)


# ─────────────────────────── forget ───────────────────────────


async def forget(
    kernel: Any,
    scope: str,
    name: str,
    *,
    kind: str = "Engram",
    tenant: str | None = None,
    superseded_by: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Bi-temporal DEMOTION — set ``valid_to`` so the memory drops out of
    default recall. NEVER hard-deletes (auditable, point-in-time reconstructable,
    revivable). Optionally records ``superseded_by_memory``. Idempotent: an
    already-invalidated memory keeps its original ``valid_to``.

    Returns ``{kind, name, valid_to, already_forgotten}``.
    """
    spec = await _load_spec(kernel, scope, kind, name, tenant)
    if not spec:
        raise KeyError(f"forget: {kind}/{name} not found in scope {scope!r}")
    already = bool(spec.get("valid_to"))
    valid_to = spec.get("valid_to") or _now_iso(now)
    spec["valid_to"] = valid_to
    if superseded_by:
        spec["superseded_by_memory"] = superseded_by
    raw: dict[str, Any] = {"kind": kind, "metadata": {"name": name}, "spec": spec}
    api_version = _resolve_api_version(kernel, kind)
    if api_version:
        raw["apiVersion"] = api_version
    write_kernel = (
        kernel.with_tenant(tenant, allow_personal=is_personal_tenant(tenant))
        if tenant else kernel
    )
    await write_kernel.write_document(scope, kind, name, raw, invalidate_mode="doc")
    return {
        "kind": kind, "name": name,
        "valid_to": valid_to, "already_forgotten": already,
    }


# ─────────────────────────── consolidate ───────────────────────────


async def consolidate(
    kernel: Any,
    scope: str,
    *,
    kind: str = "Engram",
    tenant: str | None = None,
    stale_retention_floor: float = 0.15,
    apply: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Deterministic consolidation pass — NO LLM (the LLM/deep-sleep scribe is
    external + optional; the SDK core only does the deterministic part).

    Recomputes Ebbinghaus retention for every currently-valid memory. Memories
    whose retention has fallen below ``stale_retention_floor`` are reported as
    stale; with ``apply=True`` they are soft-forgotten (``forget`` — bi-temporal
    ``valid_to``, never deleted). Returns a report:
    ``{evaluated, stale:[{name,retention,stability_days}], archived, applied}``.
    """
    now_dt = now or datetime.now(timezone.utc)
    evaluated = 0
    stale: list[dict[str, Any]] = []
    async for raw in kernel.query(scope, kind, tenant=tenant):
        spec = raw.get("spec") or {}
        name = (raw.get("metadata") or {}).get("name") or raw.get("name")
        if not name:
            continue
        if not currently_valid(spec.get("valid_to"), now=now_dt):
            continue  # already invalidated — skip
        evaluated += 1
        _adjusted, retention = decay_adjusted_score(1.0, spec, floor=0.0, now=now_dt)
        if retention < stale_retention_floor:
            stale.append({
                "name": name,
                "retention": round(retention, 4),
                "stability_days": round(stability_from_spec(spec), 2),
                "days_since": round(
                    days_since(spec.get("last_surfaced") or spec.get("created_at"), now=now_dt) or 0.0, 2,
                ),
            })
    stale.sort(key=lambda s: (s["retention"], s["name"]))

    archived = 0
    if apply:
        for s in stale:
            try:
                await forget(kernel, scope, s["name"], kind=kind, tenant=tenant, now=now_dt)
                archived += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("consolidate: archive failed for %s: %s", s["name"], exc)

    return {
        "evaluated": evaluated,
        "stale": stale,
        "archived": archived,
        "applied": apply,
    }


async def import_mif_docs(
    kernel: Any,
    scope: str,
    docs: list[dict[str, Any]],
    *,
    as_mode: str = "both",
    dedupe: str = "id",
    tenant: str | None = None,
) -> dict[str, Any]:
    """Ingest already-parsed MIF Memory Units into ``scope``/``tenant`` — the
    ONE write pipeline behind ``dna memory import`` (CLI) and
    ``POST /v1/memories/import`` (REST face), so the two can never drift.

    ``docs`` are validated MIF dicts (see
    :func:`dna.memory.interchange.parse_mif_bundle`) — parsing/IO is the
    caller's job.

    ``as_mode``:

    * ``passthrough`` — store the original MIF doc byte-for-byte as
      ``mif-spec.dev/v1 · Memory`` (auditable, stable re-export);
    * ``native`` — project an ``Engram`` via :func:`from_mif` only
      (indexable / recallable);
    * ``both`` (default) — do both.

    ``dedupe``: ``id`` skips a doc whose MIF id was already imported (the §6
    idempotence contract), ``content-hash`` skips by exact content match,
    ``off`` pre-checks nothing.

    ``tenant`` may name a reserved ``personal:<oid>`` partition — the caller
    (a face) is responsible for having derived that oid SERVER-SIDE
    (INV-PERSONAL layer 1); this binds the write kernel with the matching
    ``allow_personal`` authorization.

    One bad doc lands in ``errors`` and does NOT abort the batch, but the
    counts always reconcile (``imported + skipped + failed == len(docs)``) so a
    partial import is always REPORTED, never silent. Deterministic — no LLM, no
    network.
    """
    from dna.memory.interchange import (
        KNOWN_MIF_FIELDS,
        engram_doc_name,
        from_mif,
        mif_doc_name,
    )
    from dna.memory.personal import is_personal_tenant

    if as_mode not in ("passthrough", "native", "both"):
        raise ValueError(
            f"as_mode must be one of passthrough/native/both, got {as_mode!r}"
        )
    if dedupe not in ("id", "content-hash", "off"):
        raise ValueError(f"dedupe must be one of id/content-hash/off, got {dedupe!r}")

    write_kernel = (
        kernel.with_tenant(tenant, allow_personal=is_personal_tenant(tenant))
        if tenant
        else kernel
    )
    engram_api_version = _resolve_api_version(kernel, "Engram")
    memory_api_version = _resolve_api_version(kernel, "Memory")

    existing_passthrough_ids: set[str] = set()
    existing_engram_mif_ids: set[str] = set()
    existing_content_hashes: set[str] = set()

    def _hash(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    if dedupe != "off":
        if as_mode in ("passthrough", "both"):
            async for raw in kernel.query(scope, "Memory", tenant=tenant):
                doc_spec = raw.get("spec") or {}
                if dedupe == "id" and doc_spec.get("id"):
                    existing_passthrough_ids.add(str(doc_spec["id"]))
                elif dedupe == "content-hash":
                    existing_content_hashes.add(_hash(doc_spec.get("content") or ""))
        if as_mode in ("native", "both"):
            async for raw in kernel.query(scope, "Engram", tenant=tenant):
                e_spec = raw.get("spec") or {}
                ec = e_spec.get("encoding_context") or {}
                if dedupe == "id" and ec.get("mif_id"):
                    existing_engram_mif_ids.add(str(ec["mif_id"]))
                elif dedupe == "content-hash":
                    existing_content_hashes.add(_hash(e_spec.get("body") or ""))

    imported: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []

    for doc in docs:
        doc_id = str(doc.get("id") or "")
        content_hash = _hash(doc.get("content") or "")

        already = False
        if dedupe == "id":
            already = (
                (as_mode == "passthrough" and doc_id in existing_passthrough_ids)
                or (as_mode == "native" and doc_id in existing_engram_mif_ids)
                or (
                    as_mode == "both"
                    and (
                        doc_id in existing_passthrough_ids
                        or doc_id in existing_engram_mif_ids
                    )
                )
            )
        elif dedupe == "content-hash":
            already = content_hash in existing_content_hashes
        if already:
            skipped.append(doc_id)
            continue

        try:
            if as_mode in ("passthrough", "both"):
                name = mif_doc_name(doc_id)
                clean_spec = {k: v for k, v in doc.items() if k in KNOWN_MIF_FIELDS}
                raw_doc: dict[str, Any] = {
                    "kind": "Memory",
                    "metadata": {"name": name},
                    "spec": clean_spec,
                }
                if memory_api_version:
                    raw_doc["apiVersion"] = memory_api_version
                await write_kernel.write_document(
                    scope, "Memory", name, raw_doc, invalidate_mode="doc"
                )
                existing_passthrough_ids.add(doc_id)

            if as_mode in ("native", "both"):
                engram_spec = from_mif(doc)
                engram_name = engram_doc_name(doc_id)
                e_raw: dict[str, Any] = {
                    "kind": "Engram",
                    "metadata": {"name": engram_name},
                    "spec": engram_spec,
                }
                if engram_api_version:
                    e_raw["apiVersion"] = engram_api_version
                await write_kernel.write_document(
                    scope, "Engram", engram_name, e_raw, invalidate_mode="doc"
                )
                existing_engram_mif_ids.add(doc_id)
        except Exception as exc:  # noqa: BLE001 — one bad doc must not abort the batch
            failed.append({"id": doc_id, "error": str(exc)})
            continue

        imported.append(doc_id)
        if dedupe == "content-hash":
            existing_content_hashes.add(content_hash)

    return {
        "as": as_mode,
        "dedupe": dedupe,
        "imported": len(imported),
        "skipped": len(skipped),
        "failed": len(failed),
        "ids": imported,
        "errors": failed,
    }


__all__ = [
    "MEMORY_KINDS",
    "remember",
    "recall",
    "forget",
    "consolidate",
    "backfill_index",
    "import_mif_docs",
    "memory_created_at",
    "is_personal_doc",
]
