"""ASCII tree rendering — standalone function operating on ManifestInstance.

Extracted from ManifestInstance to keep the kernel class focused.
1:1 parity with TypeScript viz/ascii.ts.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel.instance import ManifestInstance


def ascii_tree(mi: ManifestInstance) -> str:
    """Terminal-friendly dependency tree. No renderer needed."""
    tree = mi.dependency_tree()
    if not tree:
        return "(no dependencies)"

    lines = [f"\U0001f4e6 {mi.scope}"]

    agent_names = sorted(tree.keys())
    for i, agent_name in enumerate(agent_names):
        info = tree[agent_name]
        is_last_agent = i == len(agent_names) - 1
        prefix = "\u2514\u2500\u2500 " if is_last_agent else "\u251c\u2500\u2500 "
        child_prefix = "    " if is_last_agent else "\u2502   "

        lines.append(f"{prefix}\U0001f916 {agent_name}")

        dep_groups = list(info.get("depends_on", {}).items())
        for j, (dep_type, deps) in enumerate(dep_groups):
            is_last_group = j == len(dep_groups) - 1
            group_prefix = "\u2514\u2500\u2500 " if is_last_group else "\u251c\u2500\u2500 "
            item_prefix = "    " if is_last_group else "\u2502   "

            lines.append(f"{child_prefix}{group_prefix}{dep_type}/")

            dep_items = list(deps.items())
            for k, (dep_name, dep_info) in enumerate(dep_items):
                is_last_dep = k == len(dep_items) - 1
                dep_prefix = "\u2514\u2500\u2500 " if is_last_dep else "\u251c\u2500\u2500 "
                kind = dep_info.get("kind", "")
                found = dep_info.get("found", True)

                # Use KindPort.ascii_icon + graph_meta for kind-specific labels
                dep_kp = mi.kind_for(kind)
                dep_icon = getattr(dep_kp, "ascii_icon", "") or ""
                dep_doc = mi._kernel.get_document_sync(mi.scope, kind, dep_name)
                dep_meta = {}
                # KindPresentation.graph_meta — optional capability member,
                # typed access with default; summary is a core KindPort
                # member but dep_kp may be None (unknown kind name).
                graph_meta_fn = getattr(dep_kp, "graph_meta", None)
                summary_fn = getattr(dep_kp, "summary", None)
                if dep_doc and callable(graph_meta_fn):
                    dep_meta = graph_meta_fn(dep_doc) or {}
                elif dep_doc and callable(summary_fn):
                    dep_meta = summary_fn(dep_doc) or {}

                if dep_meta.get("severity"):
                    sev_icon = "\U0001f534" if dep_meta["severity"] == "error" else "\U0001f7e1"
                    rules_count = dep_meta.get("rules", 0)
                    label = f"{sev_icon} {dep_name} ({rules_count} rules, {dep_meta['severity']})"
                elif dep_icon:
                    label = f"{dep_icon} {dep_name}"
                else:
                    label = dep_name

                if not found:
                    label += " \u274c MISSING"

                lines.append(f"{child_prefix}{item_prefix}{dep_prefix}{label}")

    return "\n".join(lines)
