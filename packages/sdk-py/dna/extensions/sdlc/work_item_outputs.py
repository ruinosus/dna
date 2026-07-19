"""Unified work-item outputs (s-produces-schema-resolver).

A work item (Spike/Story/Feature/Epic) is a HUB: its outputs are the union of

  1. the explicit ``spec.produces: [{kind, name, role?, at?}]`` relationship
     (mirrors ``AgentSession.spec.produced_artifacts``), and
  2. the legacy per-Kind back-refs scattered across the schemas today —
     ``spec_refs`` → Spec, ``research_refs`` → Research, ``html_artifacts`` →
     HtmlArtifact, ``references`` → Reference, ``follow_up_story``/``follow_up_adr``,
     a linked Plan (``Plan.story_ref`` — the start-gate), and an Engram
     whose ``source_refs`` point back at the work item.

Deduped by ``(kind, name)`` with explicit ``produces[]`` winning. Pure — no
kernel/source dependency — so it feeds the derived journey, the CLI
``produces list``, and the FOCUS endpoint from one place (no drift, zero
migration: docs with only legacy back-refs still surface their outputs).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _as_list(v: Any) -> list[Any]:
    if isinstance(v, list):
        return v
    if v:
        return [v]
    return []


def _spec_of(doc: Mapping[str, Any]) -> Mapping[str, Any]:
    inner = doc.get("spec")
    return inner if isinstance(inner, Mapping) else {}


def resolve_work_item_outputs(
    wi_name: str,
    wi_spec: Mapping[str, Any],
    *,
    plans: Sequence[Mapping[str, Any]] = (),
    lessons: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return the unified output list of a work item.

    Each entry: ``{kind, name, role, at, source}`` where ``source`` is
    ``"produces"`` (explicit) or ``"legacy"`` (back-ref). Deduped by
    ``(kind, name)`` — explicit ``produces[]`` is emitted first and wins.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: Any, name: Any, *, role: Any = None, at: Any = None, source: str = "produces") -> None:
        if not isinstance(kind, str) or not isinstance(name, str) or not kind or not name:
            return
        key = (kind, name)
        if key in seen:
            return
        seen.add(key)
        out.append({
            "kind": kind,
            "name": name,
            "role": role if isinstance(role, str) else None,
            "at": at if isinstance(at, str) else None,
            "source": source,
        })

    # 1. explicit produces[] (wins on dedup — emitted first)
    for p in _as_list(wi_spec.get("produces")):
        if isinstance(p, Mapping):
            add(p.get("kind"), p.get("name"), role=p.get("role"), at=p.get("at"), source="produces")

    # 2. legacy back-refs that live ON the work item
    for s in _as_list(wi_spec.get("spec_refs")):
        add("Spec", s, source="legacy")
    for r in _as_list(wi_spec.get("research_refs")):
        add("Research", r, source="legacy")
    for h in _as_list(wi_spec.get("html_artifacts")):
        add("HtmlArtifact", h, source="legacy")
    for rr in _as_list(wi_spec.get("references")):
        add("Reference", rr, source="legacy")
    add("Story", wi_spec.get("follow_up_story"), role="follow-up", source="legacy")
    add("ADR", wi_spec.get("follow_up_adr"), role="follow-up", source="legacy")
    add("Spec", wi_spec.get("follow_up_spec"), role="follow-up", source="legacy")

    # 3. legacy back-refs that live on the ARTIFACT pointing back at the work item
    for pd in plans:
        ps = _spec_of(pd)
        if wi_name in {ps.get("story_ref"), ps.get("story"), ps.get("parent_ref")}:
            add("Plan", pd.get("name"), source="legacy")
    for ld in lessons:
        refs = [r for r in _as_list(_spec_of(ld).get("source_refs")) if isinstance(r, str)]
        if any(r == wi_name or r.endswith(f"/{wi_name}") for r in refs):
            add("Engram", ld.get("name"), source="legacy")

    return out
