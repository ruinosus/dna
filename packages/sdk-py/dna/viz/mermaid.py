"""Mermaid diagram generators — standalone functions receiving ManifestInstance.

Extracted from ManifestInstance to keep the kernel class focused on
query/prompt/composition. The original methods on ManifestInstance are
preserved for backwards compat; these functions are the canonical
implementation going forward.

1:1 parity with TypeScript viz/mermaid.ts.
"""
from __future__ import annotations
import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel.instance import ManifestInstance


# ---------------------------------------------------------------------------
# Dependency Tree Mermaid
# ---------------------------------------------------------------------------


def dependency_tree_mermaid(mi: ManifestInstance) -> str:
    """Generate a Mermaid flowchart from the dependency tree."""
    tree = mi.dependency_tree()
    if not tree:
        return "graph TB\n    empty[No dependencies found]"

    # Dynamic style lookup via KindPort.graph_style — no hardcoded palette.
    def _style_for(kind_name: str) -> str:
        kp = mi.kind_for(kind_name)
        gs = getattr(kp, "graph_style", None)
        if isinstance(gs, dict) and gs.get("fill") and gs.get("stroke"):
            tc = gs.get("text_color", "#fff")
            return f"fill:{gs['fill']},color:{tc},stroke:{gs['stroke']}"
        return "fill:#95A5A6,color:#fff,stroke:#64748B"

    node_ids: dict[str, str] = {}
    node_counter = 0
    declared_nodes: dict[str, str] = {}  # nid -> declaration line
    styles: dict[str, str] = {}
    edges: list[str] = []

    def node_id(name: str) -> str:
        nonlocal node_counter
        if name not in node_ids:
            node_ids[name] = f"n{node_counter}"
            node_counter += 1
        return node_ids[name]

    def truncate(text: str, max_len: int = 45) -> str:
        text = text.replace('"', "")
        return text[:max_len] + "..." if len(text) > max_len else text

    for doc_name, info in tree.items():
        nid = node_id(doc_name)
        kind = info["kind"]
        desc = info.get("description", "")
        label = doc_name
        if desc:
            label = f"{doc_name}<br/><i>{truncate(desc)}</i>"
        declared_nodes[nid] = f"    {nid}[\"{label}\"]"
        styles[nid] = _style_for(kind)

        for dep_type, deps in info.get("depends_on", {}).items():
            for dep_name, dep_info in deps.items():
                dep_nid = node_id(dep_name)
                dep_kind = dep_info.get("kind", "")

                # Only declare each node once
                if dep_nid not in declared_nodes:
                    dep_kp = mi.kind_for(dep_kind)
                    dep_doc = mi._kernel.get_document_sync(mi.scope, dep_kind, dep_name)
                    meta = {}
                    if dep_kp and dep_doc:
                        gm = getattr(dep_kp, "graph_meta", None)
                        if callable(gm):
                            meta = gm(dep_doc) or {}
                        elif hasattr(dep_kp, "summary") and callable(dep_kp.summary):
                            meta = dep_kp.summary(dep_doc) or {}
                    if meta.get("severity"):
                        sev = meta["severity"]
                        rules_c = meta.get("rules", 0)
                        sev_icon = "\U0001f534" if sev == "error" else "\U0001f7e1"
                        dep_label = f"{sev_icon} {dep_name}<br/>{rules_c} rules \u00b7 {sev}"
                        sev_styles = {
                            "error": "fill:#E74C3C,color:#fff,stroke:#C0392B",
                            "warn": "fill:#F39C12,color:#fff,stroke:#D68910",
                        }
                        styles[dep_nid] = sev_styles.get(sev, _style_for(dep_kind))
                    else:
                        dep_desc = dep_info.get("description", "")
                        dep_label = dep_name
                        if dep_desc:
                            dep_label = f"{dep_name}<br/><i>{truncate(dep_desc)}</i>"
                        styles[dep_nid] = _style_for(dep_kind)
                    declared_nodes[dep_nid] = f"    {dep_nid}[\"{dep_label}\"]"

                found = dep_info.get("found", True)
                arrow = "-.->|" if not found else "-->|"
                edges.append(f"    {nid} {arrow}{dep_type}| {dep_nid}")

    lines = ["graph TB"]
    lines.extend(declared_nodes.values())
    lines.append("")
    lines.extend(edges)
    lines.append("")
    for nid, style in styles.items():
        lines.append(f"    style {nid} {style}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Composition Flowchart Mermaid
# ---------------------------------------------------------------------------


def composition_flowchart_mermaid(mi: ManifestInstance) -> str:
    """Generate a composition flowchart showing Module -> Agents -> deps."""
    kinds = mi._kinds
    profiles = mi._profiles

    lines = ["graph LR"]
    root = mi.root
    package_name = root.name if root else mi.scope
    esc = lambda s: s.replace('"', "'").replace("\n", " ")
    safe = lambda s: re.sub(r"[^a-zA-Z0-9_]", "_", s.replace("-", "_"))

    class_for = lambda kind: safe(kind).lower()

    def palette_for(kind: str) -> dict:
        kp = mi.kind_for(kind)
        gs = getattr(kp, "graph_style", None)
        if isinstance(gs, dict) and gs.get("fill"):
            return gs
        return {"fill": "#6B7280", "stroke": "#4B5563", "text_color": "#fff"}

    # Emit classDef for every kind present in the manifest.
    present_kinds: set[str] = set()
    if root:
        present_kinds.add(root.kind)
    for d in mi.documents:
        present_kinds.add(d.kind)
    for kind in sorted(present_kinds):
        p = palette_for(kind)
        tc = p.get("text_color", "#fff")
        lines.append(f"  classDef {class_for(kind)} fill:{p['fill']},color:{tc},stroke:{p['stroke']},stroke-width:2px")
    lines.append("")

    # Genome node
    root_kp = kinds.get((root.api_version, root.kind)) if root else None
    root_label = getattr(root_kp, "display_label", None) or (root.kind if root else "Genome")
    lines.append(f'  mod["<b>{esc(package_name)}</b><br/><i>{root_label}</i>"]:::{class_for(root.kind if root else "Genome")}')
    lines.append("")

    declared_nodes: set[str] = set()
    node_id_for = lambda kind, name: f"n_{safe(kind)}_{safe(name)}"

    def declare_node(kind: str, name: str, label: str | None = None) -> str:
        nid = node_id_for(kind, name)
        if nid in declared_nodes:
            return nid
        declared_nodes.add(nid)
        lines.append(f'  {nid}["{esc(label or name)}"]:::{class_for(kind)}')
        return nid

    # Richer label via kp.graph_meta or kp.summary
    def make_label(doc: Any) -> str:
        kp = kinds.get((doc.api_version, doc.kind))
        meta = None
        if kp:
            gm = getattr(kp, "graph_meta", None)
            if callable(gm):
                meta = gm(doc)
            if meta is None and hasattr(kp, "summary") and callable(kp.summary):
                meta = kp.summary(doc)
        if not meta:
            return doc.name
        if isinstance(meta.get("model"), str) and meta["model"]:
            return f"<b>{doc.name}</b><br/><i>{meta['model']}</i>"
        if isinstance(meta.get("severity"), str):
            return f"{doc.name}<br/><i>{meta['severity']}</i>"
        if isinstance(meta.get("type"), str):
            return f"{doc.name}<br/><i>{meta['type']}</i>"
        return doc.name

    # Orchestrator kinds from profiles
    orchestrator_kinds: set[str] = set()
    for p in profiles:
        kp = mi.kind_for_alias(p.orchestrator_alias)
        if kp:
            orchestrator_kinds.add(kp.kind)

    # Walk every non-root document and declare it as a node.
    for doc in mi.documents:
        if mi.is_root_doc(doc):
            continue
        declare_node(doc.kind, doc.name, make_label(doc))

    lines.append("")

    # Edges from the Module root via its declared dep_filters.
    if root:
        default_agent = root.spec.get("default_agent", "")
        for dep in mi.iter_doc_deps(root):
            for name in dep["names"]:
                tid = node_id_for(dep["target_kind"], name)
                if tid not in declared_nodes:
                    declare_node(dep["target_kind"], name, f"{name}<br/><i>(missing)</i>")
                if dep["target_kind"] in orchestrator_kinds and name == default_agent:
                    lines.append(f"  mod ==>|default| {tid}")
                else:
                    lines.append(f"  mod -->|{dep['label']}| {tid}")

    # Edges from every orchestrator (agent) via its declared dep_filters.
    for agent in mi.all_where(
        lambda kp: kp.is_prompt_target
        and not getattr(kp, "is_root", False)
        and not getattr(kp, "flatten_in_context", False)
    ):
        src = node_id_for(agent.kind, agent.name)
        for dep in mi.iter_doc_deps(agent):
            for name in dep["names"]:
                tid = node_id_for(dep["target_kind"], name)
                if tid not in declared_nodes:
                    declare_node(dep["target_kind"], name, f"{name}<br/><i>(missing)</i>")
                lines.append(f"  {src} -->|{dep['label']}| {tid}")

    # Edges from every non-root, non-agent doc that has dep_filters.
    for dep_doc in mi.documents:
        kp = kinds.get((dep_doc.api_version, dep_doc.kind))
        if not kp or getattr(kp, "is_root", False) or getattr(kp, "is_prompt_target", False):
            continue
        filters = kp.dep_filters() if hasattr(kp, "dep_filters") else None
        if not filters:
            continue
        src = node_id_for(dep_doc.kind, dep_doc.name)
        for dep in mi.iter_doc_deps(dep_doc):
            for name in dep["names"]:
                tid = node_id_for(dep["target_kind"], name)
                if tid not in declared_nodes:
                    declare_node(dep["target_kind"], name, f"{name}<br/><i>(missing)</i>")
                lines.append(f"  {src} -.->|{dep['label']}| {tid}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# C4 Component Mermaid
# ---------------------------------------------------------------------------


def c4_component_mermaid(mi: ManifestInstance) -> str:
    """Generate a C4-style component diagram."""
    kinds = mi._kinds
    profiles = mi._profiles

    lines = ["graph LR"]
    root = mi.root
    package_name = root.name if root else mi.scope
    agents = mi.all_where(
        lambda kp: kp.is_prompt_target
        and not getattr(kp, "is_root", False)
        and not getattr(kp, "flatten_in_context", False)
    )
    esc = lambda s: s.replace('"', "'").replace("\n", " ")
    safe = lambda s: re.sub(r"[^a-zA-Z0-9_]", "_", s.replace("-", "_"))

    lines.append('  classDef module fill:#3B82F6,color:#fff,stroke:#2563EB,stroke-width:2px,font-size:14px')
    lines.append('  classDef agent fill:#F97316,color:#fff,stroke:#EA580C,stroke-width:2px')
    lines.append('  classDef stat fill:#F8FAFC,color:#334155,stroke:#CBD5E1,stroke-width:1px')
    lines.append("")

    kind_counts: dict[str, int] = {}
    for d in mi.documents:
        if mi.is_root_doc(d):
            continue
        kind_counts[d.kind] = kind_counts.get(d.kind, 0) + 1

    orchestrator_kinds: set[str] = set()
    for p in profiles:
        kp = mi.kind_for_alias(p.orchestrator_alias)
        if kp:
            orchestrator_kinds.add(kp.kind)

    count_parts: list[str] = []
    for ok in orchestrator_kinds:
        n = kind_counts.get(ok, 0)
        label = getattr(mi.kind_for(ok), "display_label", None) or ok
        if n > 0:
            count_parts.append(f"{n} {label.lower()}")

    other_kinds = sorted(
        [(k, n) for k, n in kind_counts.items() if k not in orchestrator_kinds],
        key=lambda x: x[0],
    )
    for k, n in other_kinds:
        label = getattr(mi.kind_for(k), "display_label", None) or k
        suffix = "" if n == 1 else "s"
        count_parts.append(f"{n} {label.lower()}{suffix}")

    count_label = " \u00b7 ".join(count_parts) or "empty"
    lines.append(f'  mod["<b>{esc(package_name)}</b><br/><i>{count_label}</i>"]:::module')
    lines.append("")

    default_agent = root.spec.get("default_agent", "") if root else ""

    for agent in agents:
        agent_id = f"a_{safe(agent.name)}"
        model = agent.spec.get("model", "")
        is_default = agent.name == default_agent

        deps = mi.iter_doc_deps(agent)
        stat_parts: list[str] = []
        for dep in deps:
            if len(dep["names"]) == 1:
                stat_parts.append(f"{dep['label']}: {dep['names'][0]}")
            else:
                stat_parts.append(f"{len(dep['names'])} {dep['label']}")

        label = f"<b>{esc(agent.name)}</b><br/><i>{esc(model)}</i><br/>{' \u00b7 '.join(stat_parts)}"
        lines.append(f'  {agent_id}["{label}"]:::agent')

        edge_label = "default agent" if is_default else "agent"
        edge_style = "==>" if is_default else "-->"
        lines.append(f"  mod {edge_style}|{edge_label}| {agent_id}")

    if root:
        root_deps = mi.iter_doc_deps(root)
        for dep in root_deps:
            if dep["label"] == "agents":
                continue
            node_id = f"m_{safe(dep['label'])}"
            preview_names = dep["names"][:4]
            preview = ", ".join(preview_names) + (", \u2026" if len(dep["names"]) > 4 else "")
            suffix = "" if len(dep["names"]) == 1 else "s"
            lines.append(f'  {node_id}["<b>{len(dep["names"])} {dep["target_kind"]}{suffix}</b><br/>{esc(preview)}"]:::stat')
            lines.append(f"  mod -->|{dep['label']}| {node_id}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ER Diagram Mermaid
# ---------------------------------------------------------------------------


def er_diagram_mermaid(mi: ManifestInstance) -> str:
    """Generate a Mermaid ER diagram showing document instances and their relationships."""
    lines = ["erDiagram"]

    def safe_id(name: str) -> str:
        result = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        result = re.sub(r"_{2,}", "_", result).rstrip("_")
        return result[:80]

    def clean_val(v: str, max_len: int = 30) -> str:
        return v.replace('"', "'").replace("\n", " ")[:max_len]

    def entity_id(kind: str, name: str) -> str:
        return safe_id(f"{kind}_{name}")

    # Skip fields that are shown as relationships or are internal.
    _SKIP_FIELDS = {
        "instruction", "content", "soul_content", "identity_content",
        "style_content", "heartbeat_content", "agents_content", "soul_json",
        "dependencies", "default_agent",
    }
    for _prof in mi._profiles:
        for _slot in _prof.slots:
            _SKIP_FIELDS.add(_slot.name)
    _SKIP_OBJECT_FIELDS = {
        "scripts", "references", "assets", "extras", "root_files",
        "budget", "layers", "custom_kinds",
    }

    # 1. Emit entities — one per document.
    for d in mi.documents:
        eid = entity_id(d.kind, d.name)
        spec = d.spec
        lines.append(f"    {eid} {{")
        lines.append(f'        string kind "{d.kind}"')
        for k, v in spec.items():
            if k in _SKIP_FIELDS:
                continue
            if isinstance(v, dict) and k in _SKIP_OBJECT_FIELDS:
                continue
            if isinstance(v, list) and k in _SKIP_OBJECT_FIELDS:
                continue
            if isinstance(v, str) and 0 < len(v) < 60 and "\n" not in v:
                lines.append(f'        string {safe_id(k)} "{clean_val(v)}"')
            elif isinstance(v, list):
                str_items = [x for x in v if isinstance(x, str)]
                if str_items and len(str_items) == len(v):
                    joined = ", ".join(str_items)
                    lines.append(f'        list {safe_id(k)} "{clean_val(joined, 50)}"')
                elif len(v) > 0:
                    lines.append(f'        list {safe_id(k)} "{len(v)} items"')
        lines.append(f"    }}")

    # 2. Emit instance-level relationships
    for d in mi.documents:
        kp = mi._kinds.get((d.api_version, d.kind))
        if not kp:
            continue
        filters = kp.dep_filters()
        if not filters:
            continue

        spec = d.spec
        src = entity_id(d.kind, d.name)

        for field, target_alias in filters.items():
            declared = spec.get(field)
            if not declared:
                continue
            # 2026-05-15 — filter refs to strings only. Some specs declare
            # list-of-dicts shapes (e.g. `team_members: [{name: ...}]`),
            # which fed dicts into safe_id() → TypeError on re.sub.
            if isinstance(declared, str):
                refs = [declared]
            elif isinstance(declared, list):
                refs = [x for x in declared if isinstance(x, str)]
            else:
                refs = []

            target_kind_name = None
            for tkp in mi._kinds.values():
                if tkp.alias == target_alias:
                    target_kind_name = tkp.kind
                    break

            is_many = field.endswith("s")
            for ref in refs:
                target_doc = next(
                    (td for td in mi.documents if td.name == ref and (target_kind_name is None or td.kind == target_kind_name)),
                    None,
                )
                tgt = entity_id(target_doc.kind, target_doc.name) if target_doc else safe_id(ref)
                rel = "}o--||" if is_many else "||--||"
                lines.append(f'    {src} {rel} {tgt} : "{field}"')

    # 3. Root -> default_agent
    root = mi.root
    if root:
        da = root.spec.get("default_agent")
        if da:
            target_doc = next(
                (td for td in mi.documents
                 if td.name == da
                 and getattr(mi._kinds.get((td.api_version, td.kind)), "is_prompt_target", False)
                 and not getattr(mi._kinds.get((td.api_version, td.kind)), "flatten_in_context", False)),
                None,
            )
            tgt = entity_id(target_doc.kind, da) if target_doc else safe_id(da)
            lines.append(f'    {entity_id(root.kind, root.name)} ||--|| {tgt} : "default_agent"')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mindmap Mermaid
# ---------------------------------------------------------------------------


def mindmap_mermaid(mi: ManifestInstance) -> str:
    """Generate a Mermaid mindmap centered on the root Module."""
    root = mi.root
    root_name = root.name if root else mi.scope
    lines = ["mindmap", f"  root(({root_name}))"]

    tree = mi.dependency_tree()
    if not tree:
        # No deps — just list all docs by kind
        by_kind: dict[str, list[str]] = {}
        for d in mi.documents:
            by_kind.setdefault(d.kind, []).append(d.name)
        for kind, names in by_kind.items():
            lines.append(f"    {kind}")
            for n in names:
                lines.append(f"      {n}")
        return "\n".join(lines)

    for doc_name, info in tree.items():
        lines.append(f"    {doc_name}")
        depends_on = info.get("depends_on", {})
        for dep_type, deps in depends_on.items():
            for dep_name in deps:
                lines.append(f"      {dep_name}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pie Chart Mermaid
# ---------------------------------------------------------------------------


def pie_chart_mermaid(mi: ManifestInstance) -> str:
    """Generate a Mermaid pie chart showing document distribution by Kind."""
    counts: dict[str, int] = {}
    for d in mi.documents:
        counts[d.kind] = counts.get(d.kind, 0) + 1

    lines = [f'pie title Documents by Kind ({len(mi.documents)} total)']
    for kind, count in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f'    "{kind}" : {count}')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Quadrant Mermaid
# ---------------------------------------------------------------------------


def quadrant_mermaid(mi: ManifestInstance) -> str:
    """Generate a Mermaid quadrant chart — axes from CompositionProfile."""
    # Find axis slots from profiles
    x_slot = y_slot = None
    for profile in mi._profiles:
        for slot in profile.slots:
            if slot.quadrant and slot.quadrant.axis == "x":
                x_slot = slot
            if slot.quadrant and slot.quadrant.axis == "y":
                y_slot = slot

    x_label = x_slot.quadrant.label if x_slot and x_slot.quadrant else "X-axis"
    y_label = y_slot.quadrant.label if y_slot and y_slot.quadrant else "Y-axis"

    lines = [
        "quadrantChart",
        "    title Agent Complexity",
        f"    x-axis {x_label}",
        f"    y-axis {y_label}",
        "    quadrant-1 High safety + High capability",
        "    quadrant-2 High safety + Low capability",
        "    quadrant-3 Low safety + Low capability",
        "    quadrant-4 Low safety + High capability",
    ]

    tree = mi.dependency_tree()
    for doc_name, info in tree.items():
        depends_on = info.get("depends_on", {})
        n_x = len(depends_on.get(x_slot.name, {})) if x_slot else 0
        n_y = len(depends_on.get(y_slot.name, {})) if y_slot else 0
        max_x = x_slot.quadrant.max_scale if x_slot and x_slot.quadrant else 10
        max_y = y_slot.quadrant.max_scale if y_slot and y_slot.quadrant else 10
        x = min(n_x / max_x, 1.0) if n_x > 0 else 0.05
        y = min(n_y / max_y, 1.0) if n_y > 0 else 0.05
        lines.append(f"    {doc_name}: [{x:.2f}, {y:.2f}]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Timeline Mermaid
# ---------------------------------------------------------------------------


def timeline_mermaid(mi: ManifestInstance) -> str:
    """Generate a Mermaid timeline showing buildPrompt composition phases."""
    root = mi.root
    agent_doc = None
    if root:
        kp = mi._kinds.get((root.api_version, root.kind))
        if kp:
            agent_name = kp.get_default_agent_name(root)
            if agent_name:
                agent_doc = mi._find_agent(agent_name)

    lines = ["timeline", "    title Prompt Composition Phases"]

    # Phase 1: Root
    if root:
        lines.append(f"    section 1. Root Module")
        lines.append(f"        {root.name} : Module loaded")

    # Phase 2: Agent resolution
    if agent_doc:
        lines.append(f"    section 2. Agent Resolution")
        lines.append(f"        {agent_doc.name} : default_agent resolved")

    # Phase 3+: Dependencies — iterate composition profile slots by order
    if agent_doc:
        profile = mi.profile_for(agent_doc)
        if profile:
            sorted_slots = sorted(
                [s for s in profile.slots if s.timeline],
                key=lambda s: s.order,
            )
            section_num = 3
            for slot in sorted_slots:
                deps = mi.iter_doc_deps(agent_doc)
                slot_deps = next((d for d in deps if d["label"] == slot.name), None)
                names = slot_deps["names"] if slot_deps else []
                if names or slot.cardinality == "one":
                    if slot.cardinality == "one" and names:
                        lines.append(f"    section {section_num}. {slot.timeline.label} (flatten)")
                        lines.append(f"        {names[0]} : {slot.timeline.item_label}")
                    elif names:
                        lines.append(f"    section {section_num}. {slot.timeline.label}")
                        for n in names:
                            lines.append(f"        {n} : {slot.timeline.item_label}")
                    section_num += 1

    # Phase 4: Template
    lines.append(f"    section 6. Render")
    lines.append(f"        Template cascade : agent \u2192 kind \u2192 fallback")
    lines.append(f"        Mustache render : final prompt")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sankey Mermaid
# ---------------------------------------------------------------------------


def sankey_mermaid(mi: ManifestInstance) -> str:
    """Generate a Mermaid sankey diagram showing document flow to agents."""
    lines = ["sankey-beta", ""]
    root = mi.root
    root_name = root.name if root else ""
    seen: set[str] = set()

    tree = mi.dependency_tree()
    for doc_name, info in tree.items():
        # Only emit edges for prompt-target orchestrators (agents).
        doc_kind = info.get("kind", "")
        doc_kp = mi.kind_for(doc_kind)
        if not doc_kp or not getattr(doc_kp, "is_prompt_target", False) or getattr(doc_kp, "is_root", False):
            continue
        depends_on = info.get("depends_on", {})
        for _dep_type, deps in depends_on.items():
            for dep_name in deps:
                # Skip edges TO the root — prevents Agent<->Module cycle
                if dep_name == root_name:
                    continue
                key = f"{dep_name}\u2192{doc_name}"
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f'"{dep_name}","{doc_name}",1')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Kind Catalog Mermaid
# ---------------------------------------------------------------------------


def kind_catalog_mermaid(mi: ManifestInstance) -> str:
    """Generate a Mermaid classDiagram showing all registered Kinds."""
    seen: set[str] = set()
    lines = ["classDiagram"]
    edges: list[str] = []

    for doc in mi.documents:
        kp = mi._kinds.get((doc.api_version, doc.kind))
        if not kp or kp.kind in seen:
            continue
        seen.add(kp.kind)

        safe = kp.kind.replace(" ", "_")
        lines.append(f"    class {safe} {{")
        lines.append(f"        <<{kp.alias}>>")
        lines.append(f"        {kp.api_version}")
        lines.append(f"        ---")
        flags = []
        if kp.is_root:
            flags.append("is_root")
        if kp.is_prompt_target:
            flags.append(f"prompt_target (priority={kp.prompt_target_priority})")
        if kp.flatten_in_context:
            flags.append("flatten_in_context")
        if flags:
            for f in flags:
                lines.append(f"        {f}")
        else:
            lines.append(f"        passive")
        filters = kp.dep_filters()
        if filters:
            lines.append(f"        ---")
            for field, alias in filters.items():
                lines.append(f"        {field} -> {alias}")
        lines.append(f"    }}")

        # Collect edges from dep_filters
        if filters:
            for field, alias in filters.items():
                for tkp in mi._kinds.values():
                    if tkp.alias == alias:
                        target_safe = tkp.kind.replace(" ", "_")
                        edges.append(f"    {safe} --> {target_safe} : {field}")
                        break

    # Add edges after all classes
    if edges:
        lines.append("")
        lines.extend(edges)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export Diagrams Markdown
# ---------------------------------------------------------------------------


def export_diagrams_md(mi: ManifestInstance, path: str | None = None) -> dict[str, str]:
    """Export all diagrams as Markdown files with embedded Mermaid blocks.

    Args:
        path: Directory to write files. If None, returns dict without writing.

    Returns:
        Dict mapping filename to markdown content.

    2026-05-15 — each generator is now isolated in try/except so a
    failure in one (e.g. an unhandled Kind shape from a custom Kind)
    doesn't abort the whole export. Failed generators emit a Mermaid
    comment placeholder so the UI can surface the error per-slug.
    """
    import logging as _log
    _logger = _log.getLogger(__name__)

    _generators = [
        ("c4-component", "C4 Component (Architecture)", c4_component_mermaid),
        ("composition-flowchart", "Composition Flowchart", composition_flowchart_mermaid),
        ("er-diagram", "Entity Relationship", er_diagram_mermaid),
        ("dependency-tree", "[Deprecated] Dependency Tree", dependency_tree_mermaid),
        ("kind-catalog", "Kind Catalog", kind_catalog_mermaid),
        ("mindmap", "Mindmap", mindmap_mermaid),
        ("pie-chart", "Document Distribution", pie_chart_mermaid),
        ("quadrant", "Agent Complexity", quadrant_mermaid),
        ("timeline", "Prompt Composition", timeline_mermaid),
        ("sankey", "Document Flow", sankey_mermaid),
    ]
    diagrams: list[tuple[str, str, str]] = []
    for slug, title, fn in _generators:
        try:
            mermaid = fn(mi)
        except Exception as e:  # noqa: BLE001 — render placeholder, keep going
            _logger.warning("diagram generator %r failed: %s", slug, e)
            mermaid = (
                f"graph TD\n"
                f"    err[\"⚠ {slug} generator failed\"]\n"
                f"    msg[\"{type(e).__name__}: {str(e)[:120]}\"]\n"
                f"    err --> msg\n"
            )
        diagrams.append((slug, title, mermaid))

    files: dict[str, str] = {}

    # Individual files
    for slug, title, mermaid in diagrams:
        md = f"# {title}\n\n```mermaid\n{mermaid}\n```\n"
        files[f"{slug}.md"] = md

    # All-in-one file
    all_lines = [f"# {mi.scope} \u2014 All Diagrams\n"]
    for slug, title, mermaid in diagrams:
        all_lines.append(f"## {title}\n\n```mermaid\n{mermaid}\n```\n")
    files["all-diagrams.md"] = "\n".join(all_lines)

    if path:
        from pathlib import Path
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        for fname, content in files.items():
            (out / fname).write_text(content, encoding="utf-8")

    return files
