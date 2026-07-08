"""Health report and impact analysis — standalone functions operating on ManifestInstance.

Extracted from ManifestInstance to keep the kernel class focused.
1:1 parity with TypeScript viz/health.ts.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel.instance import ManifestInstance


def health_report(mi: ManifestInstance) -> dict[str, Any]:
    """Health report: coverage gaps, orphan documents, missing refs.

    Iterates CompositionProfile slots generically — no kind names
    hardcoded. Each slot with a health_check hint generates issue
    lists automatically.
    """
    tree = mi.dependency_tree()
    comp = mi.composition_result

    # All orchestrators (agents)
    all_agents = mi.all_where(
        lambda kp: kp.is_prompt_target
        and not getattr(kp, "is_root", False)
        and not getattr(kp, "flatten_in_context", False)
    )
    agent_names = {a.name for a in all_agents}

    # --- Generic slot-based health checks via CompositionProfile ---
    slot_issues: dict[str, list[str]] = {}
    slot_coverage: dict[str, str] = {}
    slot_totals: dict[str, int] = {}
    has_issues = False

    for agent in all_agents:
        profile = mi.profile_for(agent)
        if not profile:
            continue
        for slot in profile.slots:
            if not slot.health_check:
                continue
            deps = mi.iter_doc_deps(agent)
            slot_deps = next((d for d in deps if d["label"] == slot.name), None)
            names = slot_deps["names"] if slot_deps else []

            if slot.health_check.rule == "at-least-one" and not names:
                key = slot.health_check.issue_key
                slot_issues.setdefault(key, []).append(agent.name)
                has_issues = True

    # Coverage stats + totals per slot
    for profile in mi._profiles:
        for slot in profile.slots:
            if not slot.health_check:
                continue
            issue_list = slot_issues.get(slot.health_check.issue_key, [])
            covered = len(all_agents) - len(issue_list)
            slot_coverage[slot.name] = f"{covered}/{len(all_agents)} agents"

            target_kp = mi.kind_for_alias(slot.target_alias)
            if target_kp:
                all_of_kind = mi._kernel.query_list_sync(mi.scope, target_kp.kind)
                slot_totals[f"{slot.name}_total"] = len(all_of_kind)

                # Count rules via graphMeta/summary
                rules_count = 0
                for d in all_of_kind:
                    meta = {}
                    gm = getattr(target_kp, "graph_meta", None)
                    if callable(gm):
                        meta = gm(d) or {}
                    elif hasattr(target_kp, "summary") and callable(target_kp.summary):
                        meta = target_kp.summary(d) or {}
                    r = meta.get("rules")
                    if isinstance(r, int):
                        rules_count += r
                if rules_count > 0:
                    slot_totals[f"{slot.name}_rules_total"] = rules_count

                # Error-severity coverage check
                error_docs = []
                for d in all_of_kind:
                    meta = {}
                    gm = getattr(target_kp, "graph_meta", None)
                    if callable(gm):
                        meta = gm(d) or {}
                    elif hasattr(target_kp, "summary") and callable(target_kp.summary):
                        meta = target_kp.summary(d) or {}
                    if meta.get("severity") == "error":
                        error_docs.append(d)

                if error_docs:
                    agents_with_error: set[str] = set()
                    for agent in all_agents:
                        deps = mi.iter_doc_deps(agent)
                        slot_deps = next((dd for dd in deps if dd["label"] == slot.name), None)
                        for dep_name in (slot_deps["names"] if slot_deps else []):
                            if any(ed.name == dep_name for ed in error_docs):
                                agents_with_error.add(agent.name)
                    missing = sorted(agent_names - agents_with_error)
                    if missing:
                        slot_issues[f"agents_missing_error_{slot.name}"] = missing

    # Referenced deps (from tree)
    referenced: set[str] = set()
    for info in tree.values():
        for deps in info.get("depends_on", {}).values():
            referenced.update(deps.keys())

    # Find orphan documents
    orphans: list[dict[str, str]] = []
    for doc in mi.documents:
        kp = mi._kinds.get((doc.api_version, doc.kind))
        if mi._is_root_doc(doc) or getattr(kp, "is_prompt_target", False):
            continue
        if doc.name not in referenced:
            orphans.append({"kind": doc.kind, "name": doc.name})

    is_healthy = comp.valid and not has_issues

    return {
        "status": "healthy" if is_healthy else "warnings",
        "composition_valid": comp.valid,
        "missing_refs": comp.missing,
        "agents_total": len(all_agents),
        **slot_issues,
        **slot_totals,
        "orphan_documents": orphans,
        "coverage": slot_coverage,
    }


def impact(mi: ManifestInstance, kind: str, name: str) -> dict[str, Any]:
    """Analyze the impact of changing or removing a document.

    Returns which agents depend on this document and how.
    """
    tree = mi.dependency_tree()
    affected: list[dict[str, Any]] = []

    for agent_name, info in tree.items():
        for dep_type, deps in info.get("depends_on", {}).items():
            if name in deps:
                affected.append({
                    "agent": agent_name,
                    "relationship": dep_type,
                })

    # Check if other non-agent docs reference it (reverse lookup)
    doc = mi._kernel.get_document_sync(mi.scope, kind, name)
    return {
        "kind": kind,
        "name": name,
        "description": doc.metadata.get("description", "") if doc else "",
        "found": doc is not None,
        "affected_agents": affected,
        "affected_count": len(affected),
        "safe_to_remove": len(affected) == 0,
    }
