"""Engine — the intel pipeline orchestrator (pure application logic, in the CORE).

``source → pass → insight → rank → suppress → deliver``. This module is the
CORE per adr-faces-reorg: it is transport-agnostic (no HTTP, no CLI, no
FastAPI/Click imports) and takes a ``kernel`` handle. The CLI and REST faces are
THIN adapters that only translate transport and delegate here.

Surface:
  - :func:`run_pass` — the full pipeline for ONE source: read the ``IntelSource``
    doc, build its context, run the analyzer → candidates, ``rank_and_suppress``,
    persist the survivors as ``IntelInsight`` docs (state=``new``), and return a
    :class:`PassResult` (kept + suppressed, with counts, for auditability).
  - :func:`list_sources` / :func:`list_insights` — read projections the faces
    render.
  - :func:`set_insight_state` — the feedback transition (new→actioned|dismissed|
    snoozed), read-modify-write through the kernel.

All writes go through ``kernel.write_document`` so cache invalidation, hooks and
schema validation fire — the same funnel ``dna research`` / ``dna sdlc`` use.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dna.extensions.intel import dedup as dedup_core
from dna.extensions.intel import feedback as feedback_core
from dna.extensions.intel.analyzer import Analyzer, SeedAnalyzer
from dna.extensions.intel.ranker import rank_and_suppress, score as score_candidate

logger = logging.getLogger("dna.intel.engine")

# Kind identities (aliases are the cross-stage contract, but write/read take the
# kind name).
SOURCE_KIND = "IntelSource"
INSIGHT_KIND = "IntelInsight"
INSIGHT_API_VERSION = "github.com/ruinosus/dna/intel/v1"
DEFAULT_SCOPE = "dna-development"

VALID_STATES = ("new", "actioned", "dismissed", "snoozed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str, *, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:maxlen].strip("-") or "insight"


def _spec_of(doc: Any) -> dict[str, Any]:
    """Extract a spec dict from either a parsed Document or a raw dict."""
    spec = getattr(doc, "spec", None)
    if spec is None and isinstance(doc, dict):
        spec = doc.get("spec")
    if not isinstance(spec, dict):
        spec = dict(spec) if spec else {}
    return spec


def _name_of(doc: Any, fallback: str = "?") -> str:
    name = getattr(doc, "name", None)
    if not name and isinstance(doc, dict):
        name = (doc.get("metadata") or {}).get("name")
    return name or fallback


# ── PassResult ─────────────────────────────────────────────────────────────


@dataclass
class PassResult:
    """The auditable summary of one intel pass over a source."""

    source: str
    scope: str
    tenant: str | None
    analyzer: str
    kept: list[dict[str, Any]] = field(default_factory=list)
    suppressed: list[dict[str, Any]] = field(default_factory=list)
    deduped: list[dict[str, Any]] = field(default_factory=list)

    @property
    def kept_count(self) -> int:
        return len(self.kept)

    @property
    def suppressed_count(self) -> int:
        return len(self.suppressed)

    @property
    def deduped_count(self) -> int:
        return len(self.deduped)

    @property
    def dedup_rate(self) -> float:
        """Fraction of the candidates that cleared the threshold but were
        dropped as duplicates (the per-pass dedup metric). 0.0 when nothing
        cleared the threshold."""
        cleared = self.kept_count + self.deduped_count
        return round(self.deduped_count / cleared, 4) if cleared else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "scope": self.scope,
            "tenant": self.tenant,
            "analyzer": self.analyzer,
            "kept_count": self.kept_count,
            "suppressed_count": self.suppressed_count,
            "deduped_count": self.deduped_count,
            "dedup_rate": self.dedup_rate,
            "kept": self.kept,
            "suppressed": self.suppressed,
            "deduped": self.deduped,
        }


# ── the pipeline ───────────────────────────────────────────────────────────


async def run_pass(
    kernel: Any,
    source_name: str,
    *,
    scope: str = DEFAULT_SCOPE,
    analyzer: Analyzer | None = None,
    tenant: str | None = None,
) -> PassResult:
    """Run the intel pipeline for one ``IntelSource``.

    Reads the source doc, builds its context, runs ``analyzer`` (default
    :class:`SeedAnalyzer`) → candidates, scores + suppresses below the source's
    ``threshold``, and persists the survivors as ``IntelInsight`` docs
    (``state='new'``, stamping ``score``, ``source_ref`` and ``created_at``).

    Returns a :class:`PassResult`; the suppressed list is kept for auditability
    (it is NOT written). Raises ``LookupError`` if the source doc is absent.
    """
    analyzer = analyzer or SeedAnalyzer()

    raw = await kernel.get_document(scope, SOURCE_KIND, source_name, tenant=tenant)
    if raw is None:
        raise LookupError(
            f"IntelSource {source_name!r} not found in scope {scope!r}"
            + (f" (tenant={tenant})" if tenant else "")
        )
    src_spec = dict(_spec_of(raw))
    src_spec.setdefault("name", source_name)

    if src_spec.get("muted"):
        return PassResult(
            source=source_name, scope=scope, tenant=tenant,
            analyzer=type(analyzer).__name__, kept=[], suppressed=[],
        )

    threshold = float(src_spec.get("threshold", 0.6))
    context = {
        "source_name": source_name,
        "scope": scope,
        "tenant": tenant,
        "pirs": src_spec.get("pirs") or [],
        "notes": src_spec.get("notes"),
    }

    # For a `type: scope` source the research material is the TARGET scope's docs.
    # The analyzer is pure (no kernel) — so the engine, which owns kernel I/O,
    # pre-fetches them into context['documents'] (fail-soft, bounded). The
    # SeedAnalyzer ignores this; the LLMAnalyzer folds it into its prompt.
    if src_spec.get("type") == "scope":
        target_scope = src_spec.get("uri") or source_name
        context["documents"] = await _gather_scope_documents(
            kernel, str(target_scope), tenant,
        )

    candidates = analyzer.analyze(src_spec, context)

    # 1. Base actionability score (+ inspectable rationale) for every candidate.
    scored: list[dict[str, Any]] = []
    for cand in candidates:
        s = score_candidate(cand, src_spec)
        annotated = dict(cand)
        annotated["score"] = s.value
        annotated["score_rationale"] = s.rationale
        scored.append(annotated)

    # 2. Feedback loop (s-intel-feedback-loop): past dispositions tune the score
    #    — dismissed-similar candidates lose score (effective threshold rises),
    #    actioned-similar gain a reinforcement bump. No feedback engrams → no-op.
    await _apply_feedback(kernel, scored, source_name, scope, tenant)

    # 3. Partition at the (feedback-adjusted) threshold.
    scored.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    kept = [c for c in scored if c["score"] >= threshold]
    suppressed = [c for c in scored if c["score"] < threshold]
    for c in suppressed:
        logger.info(
            "intel: suppressed insight %r (score=%.2f < threshold=%.2f) — %s",
            c.get("title"), c.get("score", 0.0), threshold, c.get("score_rationale"),
        )

    # 4. Dedup (s-intel-dedup-memory): drop candidates already surfaced for this
    #    source (any state). Re-running a pass yields 0 new insights.
    kept, deduped = await _dedup_candidates(kernel, kept, source_name, scope, tenant)

    written: list[dict[str, Any]] = []
    for cand in kept:
        name = f"ins-{_slug(source_name, maxlen=24)}-{_slug(cand.get('title', ''))}"
        insight_raw = {
            "apiVersion": INSIGHT_API_VERSION,
            "kind": INSIGHT_KIND,
            "metadata": {"name": name},
            "spec": {
                "title": cand.get("title"),
                "fact": cand.get("fact") or "",
                "why": cand.get("why"),
                "action": cand.get("action"),
                "score": cand.get("score", 0.0),
                "source_ref": source_name,
                "pirs": list(cand.get("pirs") or []),
                "citations": list(cand.get("citations") or []),
                "state": "new",
                "evidence_rating": cand.get("evidence_rating") or "anecdotal",
                "created_at": _now(),
            },
        }
        await kernel.write_document(
            scope, INSIGHT_KIND, name, insight_raw, tenant=tenant,
        )
        written.append(
            {
                "name": name,
                "title": cand.get("title"),
                "score": cand.get("score", 0.0),
                "rationale": cand.get("score_rationale"),
                "action": cand.get("action"),
            }
        )

    suppressed_summary = [
        {
            "title": c.get("title"),
            "score": c.get("score", 0.0),
            "rationale": c.get("score_rationale"),
        }
        for c in suppressed
    ]

    return PassResult(
        source=source_name, scope=scope, tenant=tenant,
        analyzer=type(analyzer).__name__,
        kept=written, suppressed=suppressed_summary, deduped=deduped,
    )


# ── context gathering (kernel-bound; the analyzer is pure) ─────────────────────


_SCOPE_DOC_MAX = 12          # cap docs pulled for a `type: scope` source
_SCOPE_DOC_CHARS = 4000      # per-doc text budget


def _doc_text(spec: dict[str, Any]) -> str:
    """A compact text projection of a doc's spec for LLM context — the string
    scalar fields joined ``key: value``, longest-form fields first. Bounded."""
    parts: list[str] = []
    for key, val in spec.items():
        if isinstance(val, str) and val.strip():
            parts.append(f"{key}: {val}")
    return "\n".join(parts)[:_SCOPE_DOC_CHARS]


async def _gather_scope_documents(
    kernel: Any, target_scope: str, tenant: str | None,
) -> list[dict[str, Any]]:
    """Pull the target scope's prompt-target docs as ``[{title, text}]`` research
    material for a ``type: scope`` IntelSource. Bounded to ``_SCOPE_DOC_MAX`` and
    fail-soft — a scope we cannot read yields ``[]`` (an honest empty context),
    never an aborted pass."""
    docs: list[dict[str, Any]] = []
    try:
        ports = kernel.kind_ports()
    except Exception as exc:  # noqa: BLE001 — introspection failure must not break a pass
        logger.warning("intel: could not enumerate kinds for scope %r: %s", target_scope, exc)
        return docs
    for port in ports:
        if len(docs) >= _SCOPE_DOC_MAX:
            break
        if not getattr(port, "is_prompt_target", False):
            continue
        kind = getattr(port, "kind", None)
        if not kind:
            continue
        try:
            async for row in kernel.query(target_scope, kind, tenant=tenant):
                if not isinstance(row, dict):
                    continue
                text = _doc_text(_spec_of(row))
                if not text.strip():
                    continue
                docs.append({"title": f"{kind}/{_name_of(row)}", "text": text})
                if len(docs) >= _SCOPE_DOC_MAX:
                    break
        except Exception as exc:  # noqa: BLE001 — one bad kind/scope must not abort
            logger.warning(
                "intel: scope-doc query failed (%s/%s): %s", target_scope, kind, exc,
            )
            continue
    return docs


# ── feedback + dedup helpers (kernel-bound; pure decisions live in the ─────────
# ── dedup / feedback modules) ─────────────────────────────────────────────────


def _kind_registered(kernel: Any, kind: str) -> bool:
    """True when ``kind`` is registered in the kernel — so a feedback write /
    recall against a Kind the host didn't load degrades to a no-op instead of
    raising (an IntelExtension-only kernel has no Engram)."""
    kinds = getattr(kernel, "_kinds", None)
    if isinstance(kinds, dict):
        for kp in kinds.values():
            if getattr(kp, "kind", None) == kind:
                return True
    return False


async def _load_feedback_memories(
    kernel: Any, scope: str, source_name: str, tenant: str | None,
) -> list[dict[str, Any]]:
    """The source's feedback engrams (Engram tagged ``intel-feedback``),
    projected to ``{disposition, text}``. Empty when the memory Kind is not
    registered — the co-pillar is optional, feedback then degrades to a no-op."""
    if not _kind_registered(kernel, "Engram"):
        return []
    area = feedback_core.feedback_area(source_name)
    out: list[dict[str, Any]] = []
    try:
        async for row in kernel.query(scope, "Engram", tenant=tenant):
            if not isinstance(row, dict):
                continue
            spec = _spec_of(row)
            if spec.get("area") != area:
                continue
            tags = [str(t) for t in (spec.get("tags") or [])]
            if feedback_core.FEEDBACK_TAG not in tags:
                continue
            disposition = next(
                (d for d in feedback_core.FEEDBACK_DISPOSITIONS if d in tags), None
            )
            if disposition is None:
                continue
            # The engram body carries the dismissed/actioned insight's own
            # title+fact text (stored on write) — compared on the SAME planes as
            # the candidate (dedup_core.insight_text), so the cosine is honest.
            text = spec.get("body") or spec.get("summary") or ""
            out.append({"disposition": disposition, "text": str(text)})
    except Exception as exc:  # noqa: BLE001 — feedback recall must never break a pass
        logger.warning("intel: feedback recall failed for %s: %s", source_name, exc)
        return []
    return out


async def _apply_feedback(
    kernel: Any, candidates: list[dict[str, Any]], source_name: str,
    scope: str, tenant: str | None,
) -> None:
    """Tune each candidate's score by the source's past dispositions (in place).

    Uses the memory co-pillar's semantic machinery: ONE ``kernel.embed`` batch
    over the candidate texts + engram texts, then per-candidate max cosine to the
    dismissed / actioned engrams (:func:`dna.memory.semantic.cosine_similarity`),
    fed to the pure :func:`feedback.adjust_score`. No engrams → no-op."""
    if not candidates:
        return
    memories = await _load_feedback_memories(kernel, scope, source_name, tenant)
    if not memories:
        return
    from dna.memory.semantic import cosine_similarity

    cand_texts = [dedup_core.insight_text(c) for c in candidates]
    mem_texts = [m["text"] for m in memories]
    try:
        vectors = await kernel.embed(cand_texts + mem_texts)
    except Exception as exc:  # noqa: BLE001 — degrade honestly to the base ranking
        logger.warning("intel: feedback embed failed for %s: %s", source_name, exc)
        return
    cand_vecs = vectors[: len(cand_texts)]
    mem_vecs = vectors[len(cand_texts):]
    dismissed_vecs = [
        mem_vecs[i] for i, m in enumerate(memories)
        if m["disposition"] == feedback_core.DISPOSITION_DISMISSED
    ]
    actioned_vecs = [
        mem_vecs[i] for i, m in enumerate(memories)
        if m["disposition"] == feedback_core.DISPOSITION_ACTIONED
    ]
    for cand, cv in zip(candidates, cand_vecs):
        sim_dismissed = max((cosine_similarity(cv, v) for v in dismissed_vecs), default=0.0)
        sim_actioned = max((cosine_similarity(cv, v) for v in actioned_vecs), default=0.0)
        adjusted, notes = feedback_core.adjust_score(
            float(cand.get("score", 0.0)), sim_dismissed, sim_actioned,
        )
        if notes:
            cand["score"] = adjusted
            cand["score_rationale"] = (
                f"{cand.get('score_rationale', '')} · feedback: {'; '.join(notes)}"
            )


async def _dedup_candidates(
    kernel: Any, candidates: list[dict[str, Any]], source_name: str,
    scope: str, tenant: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split threshold-clearing candidates into ``(fresh, deduped)`` against the
    insights already surfaced for this source (any state).

    The deterministic ``normalized_key`` is the floor; when there ARE existing
    insights a single ``kernel.embed`` batch adds the semantic cosine. Returns
    the fresh candidates + an auditable summary of the dropped duplicates."""
    if not candidates:
        return candidates, []
    existing = await list_insights(
        kernel, scope=scope, tenant=tenant, source_ref=source_name,
    )
    existing_keys = {dedup_core.normalized_key(e, source_name) for e in existing}
    cand_keys = [dedup_core.normalized_key(c, source_name) for c in candidates]

    max_cosines: list[float] | None = None
    if existing:
        from dna.memory.semantic import cosine_similarity

        cand_texts = [dedup_core.insight_text(c) for c in candidates]
        ex_texts = [dedup_core.insight_text(e) for e in existing]
        try:
            vectors = await kernel.embed(cand_texts + ex_texts)
            cand_vecs = vectors[: len(cand_texts)]
            ex_vecs = vectors[len(cand_texts):]
            max_cosines = [
                max((cosine_similarity(cv, ev) for ev in ex_vecs), default=0.0)
                for cv in cand_vecs
            ]
        except Exception as exc:  # noqa: BLE001 — fall back to the key-only floor
            logger.warning("intel: dedup embed failed for %s: %s", source_name, exc)
            max_cosines = None

    fresh_idx, dup_idx, reasons = dedup_core.dedup_partition(
        cand_keys, max_cosines, existing_keys,
    )
    fresh = [candidates[i] for i in fresh_idx]
    deduped = [
        {
            "title": candidates[i].get("title"),
            "score": candidates[i].get("score", 0.0),
            "reason": reasons[i][0],
            "cosine": round(reasons[i][1], 4),
        }
        for i in dup_idx
    ]
    if deduped:
        logger.info(
            "intel: deduped %d already-surfaced insight(s) for source %r",
            len(deduped), source_name,
        )
    return fresh, deduped


async def _record_feedback(
    kernel: Any, insight_spec: dict[str, Any], insight_name: str,
    disposition: str, scope: str, tenant: str | None,
) -> None:
    """Record a disposition as a feedback engram in the memory co-pillar.

    ``dismissed`` → a ``regret`` Engram (negative feedback that suppresses
    similar future candidates); ``actioned`` → a ``triumph`` one (reinforcement).
    The engram body carries the insight's own title+fact so the ranker can
    compare candidates against it. Fail-soft + skipped when the memory Kind is
    not registered — never blocks the state transition."""
    if disposition not in feedback_core.FEEDBACK_DISPOSITIONS:
        return
    if not _kind_registered(kernel, "Engram"):
        return
    try:
        from dna.memory import remember

        source_ref = insight_spec.get("source_ref") or "?"
        affect = "regret" if disposition == feedback_core.DISPOSITION_DISMISSED else "triumph"
        text = dedup_core.insight_text(insight_spec)
        mem_name = f"fb-{disposition}-{_slug(insight_name, maxlen=48)}"
        mem_spec = {
            "area": feedback_core.feedback_area(source_ref),
            "surface_when": ["feature_touched"],
            "source_refs": [f"IntelInsight/{insight_name}"],
            "affect": affect,
            "affect_reason": (
                f"Reader marked intel insight {insight_name!r} as {disposition} "
                f"for source {source_ref!r}; recording it tunes the ranker so "
                f"similar candidates are {'suppressed' if affect == 'regret' else 'reinforced'}."
            ),
            "affect_evidence_refs": [f"IntelInsight/{insight_name}"],
            "summary": (f"[{disposition}] {insight_spec.get('title') or insight_name}")[:280],
            "body": text,
            "tags": [feedback_core.FEEDBACK_TAG, disposition],
            "owner": "intel-feedback",
        }
        await remember(
            kernel, scope, kind="Engram", name=mem_name, spec=mem_spec,
            tenant=tenant,
        )
    except Exception as exc:  # noqa: BLE001 — feedback is best-effort, never blocks
        logger.warning(
            "intel: recording %s feedback for %s failed: %s",
            disposition, insight_name, exc,
        )


# ── read projections (faces render these) ──────────────────────────────────


async def list_sources(
    kernel: Any, *, scope: str = DEFAULT_SCOPE, tenant: str | None = None,
) -> list[dict[str, Any]]:
    """List ``IntelSource`` docs in ``scope`` (tenant-aware), projected to the
    surface the CLI/REST render."""
    out: list[dict[str, Any]] = []
    async for row in kernel.query(scope, SOURCE_KIND, tenant=tenant):
        if not isinstance(row, dict):
            continue
        spec = _spec_of(row)
        out.append(
            {
                "name": _name_of(row),
                "type": spec.get("type"),
                "cadence": spec.get("cadence", "weekly"),
                "threshold": spec.get("threshold", 0.6),
                "pirs": list(spec.get("pirs") or []),
                "muted": bool(spec.get("muted", False)),
            }
        )
    out.sort(key=lambda r: r["name"] or "")
    return out


async def list_insights(
    kernel: Any,
    *,
    scope: str = DEFAULT_SCOPE,
    tenant: str | None = None,
    state: str | None = None,
    source_ref: str | None = None,
) -> list[dict[str, Any]]:
    """List ``IntelInsight`` docs in ``scope`` (tenant-aware), optionally
    filtered by ``state`` and/or ``source_ref``, projected to the render
    surface and sorted by score descending."""
    out: list[dict[str, Any]] = []
    async for row in kernel.query(scope, INSIGHT_KIND, tenant=tenant):
        if not isinstance(row, dict):
            continue
        spec = _spec_of(row)
        if state and spec.get("state") != state:
            continue
        if source_ref and spec.get("source_ref") != source_ref:
            continue
        out.append(
            {
                "name": _name_of(row),
                "title": spec.get("title"),
                "fact": spec.get("fact"),
                "why": spec.get("why"),
                "action": spec.get("action"),
                "score": spec.get("score", 0.0),
                "state": spec.get("state", "new"),
                "source_ref": spec.get("source_ref"),
                "pirs": list(spec.get("pirs") or []),
                "evidence_rating": spec.get("evidence_rating"),
                "created_at": spec.get("created_at"),
            }
        )
    out.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return out


class InsightNotFound(LookupError):
    """The requested IntelInsight is absent for this (scope, tenant)."""


async def set_insight_state(
    kernel: Any,
    name: str,
    state: str,
    *,
    scope: str = DEFAULT_SCOPE,
    tenant: str | None = None,
) -> dict[str, Any]:
    """The feedback transition: set an insight's ``state`` (new|actioned|
    dismissed|snoozed) via read-modify-write through the kernel.

    Raises ``ValueError`` on an invalid state, ``InsightNotFound`` if the doc is
    absent for this (scope, tenant)."""
    if state not in VALID_STATES:
        raise ValueError(
            f"invalid state {state!r} — must be one of {', '.join(VALID_STATES)}"
        )
    raw = await kernel.get_document(scope, INSIGHT_KIND, name, tenant=tenant)
    if raw is None:
        raise InsightNotFound(
            f"IntelInsight {name!r} not found in scope {scope!r}"
            + (f" (tenant={tenant})" if tenant else "")
        )
    # Deep-ish copy so we never mutate the kernel's cached dict in place
    # (cache returns the same ref across calls — kernel-doc-cache-mutation guard).
    new_raw = dict(raw)
    spec = dict(_spec_of(raw))
    spec["state"] = state
    new_raw["spec"] = spec
    await kernel.write_document(scope, INSIGHT_KIND, name, new_raw, tenant=tenant)

    # Feedback loop (s-intel-feedback-loop): a disposition tunes the ranker via
    # the memory co-pillar. Fail-soft — the transition already persisted above.
    await _record_feedback(kernel, spec, name, state, scope=scope, tenant=tenant)

    return {"name": name, "state": state, "scope": scope, "tenant": tenant}


async def feedback_metrics(
    kernel: Any,
    *,
    scope: str = DEFAULT_SCOPE,
    tenant: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """The feedback KPIs — inspectable, read-only.

    Counts ``IntelInsight`` docs per state (optionally for one ``source_ref``)
    and derives the precision (``actioned / (actioned+dismissed)``) and the
    product KPI noise-rate (``dismissed / (actioned+dismissed)``). Faces render
    this; the arithmetic is the pure :func:`feedback.summarize_states`."""
    counts: dict[str, int] = {s: 0 for s in VALID_STATES}
    async for row in kernel.query(scope, INSIGHT_KIND, tenant=tenant):
        if not isinstance(row, dict):
            continue
        spec = _spec_of(row)
        if source_ref and spec.get("source_ref") != source_ref:
            continue
        st = spec.get("state", "new")
        counts[st] = counts.get(st, 0) + 1
    metrics = feedback_core.summarize_states(counts)
    metrics.update({"scope": scope, "tenant": tenant, "source_ref": source_ref})
    return metrics
