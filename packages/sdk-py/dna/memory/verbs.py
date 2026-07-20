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
    retention?,semantic?,rank_recall?,rank_ecphory?,...}]}``.
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


__all__ = [
    "MEMORY_KINDS",
    "remember",
    "recall",
    "forget",
    "consolidate",
    "backfill_index",
]
