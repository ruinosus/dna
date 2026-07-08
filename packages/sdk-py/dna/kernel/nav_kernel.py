"""Kernel-driven nav/composition operations — replaces mi.nav / mi.composition.

Story s-composition-and-nav-lazy (Feature f-mi-class-extinction).

Free functions taking ``(kernel, scope, ...)`` that compute:
  - scope_summary: text listing (Kind: count, names)
  - scope_inventory: structured per-Kind detail + composition result
  - scope_describe: per-doc description
  - validate_composition: cross-kind dep validation

Implementation strategy: iterate ``kernel._kinds`` (registry, cheap)
and use ``kernel.query(scope, kind, tenant=...)`` per Kind. The
``kernel.list_documents`` granular L1 method is used when only
``(kind, name)`` refs are needed (avoids materializing doc bodies).

Cost vs legacy mi-based namespaces: same total I/O on a single full
walk, but the MI shell is never constructed → no eager scope cache
held across requests. Bounded RAM, no leak driver.
"""
from __future__ import annotations

import logging
from typing import Any

from dna.kernel.preview import PreviewBlock, generic_spec_dump
from dna.kernel.protocols import CompositionResult

logger = logging.getLogger(__name__)


# -- Doc helpers ---------------------------------------------------------


async def _docs_by_kind(
    kernel: Any, scope: str, *, tenant: str | None = None,
) -> dict[str, list[Any]]:
    """Iterate every Kind in the registry and materialize its docs.

    Returns {kind_name: [Document, ...]}. Used by inventory + composition
    when we need ALL docs (the "eager scan" — but bounded per-Kind so
    the kernel's L2 list cache covers it).
    """
    out: dict[str, list[Any]] = {}
    seen_kinds: set[str] = set()
    for kp in kernel._kinds.values():
        if kp.kind in seen_kinds:
            continue
        seen_kinds.add(kp.kind)
        docs: list[Any] = []
        async for raw in kernel.query(scope, kp.kind, tenant=tenant):
            doc = kernel._parse_doc(raw, origin="local")
            if doc is not None:
                docs.append(doc)
        out[kp.kind] = docs
    return out


async def _doc_index(
    kernel: Any, scope: str, *, tenant: str | None = None,
) -> set[tuple[str, str]]:
    """Build {(kind, name)} set across all Kinds. Cheap path: uses
    ``kernel.list_documents`` (L1 refs only — no bodies materialized).
    """
    out: set[tuple[str, str]] = set()
    seen_kinds: set[str] = set()
    for kp in kernel._kinds.values():
        if kp.kind in seen_kinds:
            continue
        seen_kinds.add(kp.kind)
        try:
            refs = await kernel.list_documents(scope, kind=kp.kind, tenant=tenant)
        except Exception as e:  # noqa: BLE001
            # fail-soft: read path — a broken Kind listing drops out of the
            # index instead of failing the whole walk (logged).
            logger.debug(
                "_doc_index: list_documents failed for kind %s in %s: %s",
                kp.kind, scope, e,
            )
            refs = []
        for k, n in refs:
            out.add((k, n))
    return out


# -- Composition --------------------------------------------------------


async def validate_composition_async(
    kernel: Any, scope: str, *, tenant: str | None = None,
) -> CompositionResult:
    """Validate cross-kind references against declared dep_filters.

    Source-plane reader of the shared ``validate_refs`` core
    (s-unify-composition-subsystems): consulta o SOURCE direto via
    ``_docs_by_kind`` — records aparecem no índice, então refs a records
    presentes resolvem; refs a records ausentes vão pra ``deferred``
    (nunca falso-``missing``). Mesma regra e mesmo resolvedor de targets
    (``KindRegistry.resolve_dep_filter_target``) do
    ``mi.composition.validate()`` — só muda o plano de entrada.
    """
    from dna.kernel.composition_resolver import validate_refs
    from dna.kernel.kind_registry import KindRegistry

    docs_by_kind = await _docs_by_kind(kernel, scope, tenant=tenant)
    all_docs = [d for docs in docs_by_kind.values() for d in docs]
    doc_index = {(d.kind, d.name) for d in all_docs}
    return validate_refs(
        all_docs, doc_index, kernel._kinds, KindRegistry(kernel._kinds),
    )


# -- Navigation ---------------------------------------------------------


async def scope_summary_async(
    kernel: Any, scope: str, *, tenant: str | None = None,
) -> str:
    """Human-readable summary (Kind: count + names list)."""
    seen: set[str] = set()
    kinds = [kp.kind for kp in kernel._kinds.values() if kp.kind not in seen and not seen.add(kp.kind)]
    lines = [f"Scope: {scope}", f"Kinds: {len(kinds)}"]
    for k in kinds:
        try:
            refs = await kernel.list_documents(scope, kind=k, tenant=tenant)
        except Exception as e:  # noqa: BLE001
            # fail-soft: read path — summary shows 0 docs for a broken Kind
            # instead of failing the whole summary (logged).
            logger.debug(
                "scope_summary: list_documents failed for kind %s in %s: %s",
                k, scope, e,
            )
            refs = []
        names = [n for _kind, n in refs]
        lines.append(f"  {k}: {len(names)} ({', '.join(names)})")
    return "\n".join(lines)


async def scope_inventory_async(
    kernel: Any, scope: str, *, tenant: str | None = None,
) -> dict[str, Any]:
    """Structured inventory: per-Kind docs + composition result.

    Each doc entry includes refs/refs_confidence based on dep_filters
    (matches mi.nav.inventory shape — EXTRACTED / AMBIGUOUS / INFERRED).
    """
    docs_by_kind = await _docs_by_kind(kernel, scope, tenant=tenant)

    # Build the same doc_index for confidence classification.
    doc_index: dict[tuple[str, str], bool] = {}
    for kind_name, docs in docs_by_kind.items():
        for d in docs:
            doc_index[(d.kind, d.name)] = True

    from dna.kernel.kind_registry import KindRegistry
    registry = KindRegistry(kernel._kinds)

    def _resolve_kind(filter_value: str) -> str | None:
        """Resolve a dep_filter value (alias or legacy ``kind=``) to a kind
        name via the canonical resolver — the same path used by
        ``validate_refs`` / ``mi.composition`` (s-unify-composition-subsystems).
        """
        kp = registry.resolve_dep_filter_target(filter_value)
        return kp.kind if kp is not None else None

    def _classify(target_alias: str, value: Any) -> str:
        kind_name = _resolve_kind(target_alias)
        if kind_name is None:
            return "AMBIGUOUS"
        if isinstance(value, str):
            names = [value]
        elif isinstance(value, list):
            names = [str(v) for v in value if v]
        else:
            return "EXTRACTED"
        for n in names:
            if (kind_name, n) not in doc_index:
                return "AMBIGUOUS"
        return "EXTRACTED"

    kinds_data: dict[str, Any] = {}
    total = 0
    for kind_name, docs in docs_by_kind.items():
        doc_entries: list[dict[str, Any]] = []
        for doc in docs:
            entry: dict[str, Any] = {
                "name": doc.name,
                "description": doc.metadata.get("description", ""),
            }
            kp = kernel._kinds.get((doc.api_version, doc.kind))
            if kp:
                filters = kp.dep_filters() or {}
                if filters:
                    refs: dict[str, Any] = {}
                    refs_confidence: dict[str, str] = {}
                    for spec_field, alias in filters.items():
                        val = doc.spec.get(spec_field)
                        if val is None:
                            continue
                        refs[spec_field] = val
                        refs_confidence[spec_field] = _classify(alias, val)
                    if refs:
                        entry["refs"] = refs
                        entry["refs_confidence"] = refs_confidence
                extra = kp.summary(doc)
                if extra:
                    entry.update(extra)
            doc_entries.append(entry)
        kinds_data[kind_name] = {
            "count": len(docs),
            "documents": doc_entries,
        }
        total += len(docs)

    comp = await validate_composition_async(kernel, scope, tenant=tenant)
    return {
        "scope": scope,
        "total_documents": total,
        "kinds": kinds_data,
        "composition": {
            "valid": comp.valid,
            "resolved": comp.resolved,
            "missing": comp.missing,
            "warnings": comp.warnings,
            "deferred": comp.deferred,
        },
    }


async def scope_describe_async(
    kernel: Any, scope: str, kind: str, name: str, *,
    tenant: str | None = None,
) -> str:
    """Per-doc human-readable description."""
    raw = await kernel.get_document(scope, kind, name, tenant=tenant)
    if raw is None:
        return f"{kind}/{name} not found"
    doc = kernel._parse_doc(raw, origin="local")
    if doc is None:
        return f"{kind}/{name} not found"
    kp = kernel._kinds.get((doc.api_version, doc.kind))
    if kp:
        custom = kp.describe(doc)
        if custom:
            return custom
    lines = [
        f"Name:       {doc.name}",
        f"Kind:       {doc.kind}",
        f"ApiVersion: {doc.api_version}",
    ]
    desc = doc.metadata.get("description")
    if desc:
        lines.append(f"Description: {desc}")
    return "\n".join(lines)


async def render_doc_async(
    kernel: Any, scope: str, kind: str, name: str, *,
    tenant: str | None = None,
) -> list[PreviewBlock]:
    """Polymorphic per-Kind preview blocks (KindPort.preview hook)."""
    raw = await kernel.get_document(scope, kind, name, tenant=tenant)
    if raw is None:
        return []
    doc = kernel._parse_doc(raw, origin="local")
    if doc is None:
        return []
    kp = kernel._kinds.get((doc.api_version, doc.kind))
    # KindPresentation.preview — optional capability member, typed
    # access with default (absence/None result → generic fallback).
    preview_fn = getattr(kp, "preview", None)
    if callable(preview_fn):
        blocks = preview_fn(doc)
        if blocks is not None:
            return blocks
    return generic_spec_dump(doc)


__all__ = [
    "validate_composition_async",
    "scope_summary_async",
    "scope_inventory_async",
    "scope_describe_async",
    "render_doc_async",
]
