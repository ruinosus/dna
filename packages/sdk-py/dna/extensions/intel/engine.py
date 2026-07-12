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

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dna.extensions.intel.analyzer import Analyzer, SeedAnalyzer
from dna.extensions.intel.ranker import rank_and_suppress

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

    @property
    def kept_count(self) -> int:
        return len(self.kept)

    @property
    def suppressed_count(self) -> int:
        return len(self.suppressed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "scope": self.scope,
            "tenant": self.tenant,
            "analyzer": self.analyzer,
            "kept_count": self.kept_count,
            "suppressed_count": self.suppressed_count,
            "kept": self.kept,
            "suppressed": self.suppressed,
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

    candidates = analyzer.analyze(src_spec, context)
    kept, suppressed = rank_and_suppress(candidates, threshold, src_spec)

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
        kept=written, suppressed=suppressed_summary,
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
    return {"name": name, "state": state, "scope": scope, "tenant": tenant}
