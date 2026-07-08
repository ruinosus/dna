/**
 * Mermaid diagram generators — standalone functions that operate on a ManifestInstance.
 *
 * Extracted from ManifestInstance to keep the kernel class focused on
 * query/prompt/composition. The original methods on ManifestInstance are
 * preserved for backwards compat; these functions are the canonical
 * implementation going forward.
 */

import type { ManifestInstance } from "../kernel/instance.js";
import type { KindPort } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";
import type { CompositionProfile } from "../kernel/composition-resolver.js";

// ---------------------------------------------------------------------------
// Helpers (private access via cast)
// ---------------------------------------------------------------------------

function _kinds(mi: ManifestInstance): Map<string, KindPort> {
  return (mi as any)._kinds;
}

function _profiles(mi: ManifestInstance): readonly CompositionProfile[] {
  return (mi as any)._profiles;
}

// ---------------------------------------------------------------------------
// Dependency Tree Mermaid
// ---------------------------------------------------------------------------

export function dependencyTreeMermaid(mi: ManifestInstance): string {
  const tree = mi.dependencyTree();
  if (Object.keys(tree).length === 0) {
    return "graph TB\n    empty[No dependencies found]";
  }

  const kinds = _kinds(mi);

  // Dynamic style lookup via KindPort.graphStyle — no hardcoded palette.
  const _styleFor = (kind: string, apiVersion?: string): string => {
    let kp: KindPort | undefined;
    if (apiVersion) {
      kp = kinds.get(`${apiVersion}\0${kind}`);
    }
    if (!kp) kp = mi.kindFor(kind) ?? undefined;
    const gs = kp?.graphStyle;
    if (gs) return `fill:${gs.fill},color:${gs.textColor},stroke:${gs.stroke}`;
    return "fill:#95A5A6,color:#fff,stroke:#64748B";
  };

  const nodeIds = new Map<string, string>();
  let counter = 0;
  const declaredNodes = new Map<string, string>();
  const styles = new Map<string, string>();
  const edges: string[] = [];

  const nodeId = (name: string): string => {
    if (!nodeIds.has(name)) {
      nodeIds.set(name, `n${counter++}`);
    }
    return nodeIds.get(name)!;
  };

  const truncate = (text: string, max = 45): string =>
    text.length > max ? text.slice(0, max) + "..." : text;

  for (const [docName, info] of Object.entries(tree)) {
    const i = info as Record<string, unknown>;
    const nid = nodeId(docName);
    const kind = i.kind as string;
    const desc = (i.description as string) ?? "";
    const label = desc ? `${docName}<br/><i>${truncate(desc)}</i>` : docName;
    declaredNodes.set(nid, `    ${nid}["${label}"]`);
    styles.set(nid, _styleFor(kind));

    const dependsOn = (i.depends_on as Record<string, unknown>) ?? {};
    for (const [depType, deps] of Object.entries(dependsOn)) {
      for (const [depName, depInfo] of Object.entries(deps as Record<string, unknown>)) {
        const di = depInfo as Record<string, unknown>;
        const depNid = nodeId(depName);
        const depKind = (di.kind as string) ?? "";

        if (!declaredNodes.has(depNid)) {
          // Use kp.graphMeta (or summary fallback) for kind-specific labels
          const depKp = mi.kindFor(depKind);
          const depDoc = mi.one(depKind, depName);
          const meta = (depKp && depDoc)
            ? (depKp.graphMeta?.(depDoc) ?? depKp.summary(depDoc) ?? {})
            : {};
          let depLabel: string;
          if ((meta as Record<string, unknown>).severity) {
            const m = meta as Record<string, unknown>;
            const sevIcon = m.severity === "error" ? "\u{1F534}" : "\u{1F7E1}";
            depLabel = `${sevIcon} ${depName}<br/>${m.rules ?? 0} rules \u00B7 ${m.severity}`;
            // Guardrail severity-specific style override
            const sevStyles: Record<string, string> = {
              error: "fill:#E74C3C,color:#fff,stroke:#C0392B",
              warn: "fill:#F39C12,color:#fff,stroke:#D68910",
            };
            styles.set(depNid, sevStyles[m.severity as string] ?? _styleFor(depKind));
          } else {
            const depDesc = (di.description as string) ?? "";
            depLabel = depDesc ? `${depName}<br/><i>${truncate(depDesc)}</i>` : depName;
            styles.set(depNid, _styleFor(depKind));
          }
          declaredNodes.set(depNid, `    ${depNid}["${depLabel}"]`);
        }

        const found = di.found !== false;
        const arrow = found ? "-->|" : "-.->|";
        edges.push(`    ${nid} ${arrow}${depType}| ${depNid}`);
      }
    }
  }

  const lines = ["graph TB"];
  lines.push(...declaredNodes.values());
  lines.push("");
  lines.push(...edges);
  lines.push("");
  for (const [nid, style] of styles) {
    lines.push(`    style ${nid} ${style}`);
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Composition Flowchart Mermaid
// ---------------------------------------------------------------------------

export function compositionFlowchartMermaid(mi: ManifestInstance): string {
  const kinds = _kinds(mi);
  const profiles = _profiles(mi);

  const lines = ["graph LR"];
  const root = mi.root;
  const packageName = root?.name ?? mi.scope;
  const esc = (s: string) => s.replace(/"/g, "'").replace(/\n/g, " ");
  const safe = (s: string) => s.replace(/-/g, "_").replace(/[^a-zA-Z0-9_]/g, "_");

  const classFor = (kind: string) => safe(kind).toLowerCase();
  const paletteFor = (kind: string): { fill: string; stroke: string; textColor: string } => {
    const kp = mi.kindFor(kind);
    return kp?.graphStyle ?? { fill: "#6B7280", stroke: "#4B5563", textColor: "#fff" };
  };

  // Emit classDef for every kind present in the manifest.
  const presentKinds = new Set<string>();
  if (root) presentKinds.add(root.kind);
  for (const d of mi.documents) presentKinds.add(d.kind);
  for (const kind of Array.from(presentKinds).sort()) {
    const p = paletteFor(kind);
    lines.push(`  classDef ${classFor(kind)} fill:${p.fill},color:${p.textColor},stroke:${p.stroke},stroke-width:2px`);
  }
  lines.push("");

  // Genome node
  const rootKp = root ? kinds.get(`${root.apiVersion}\0${root.kind}`) : null;
  const rootLabel = rootKp?.displayLabel ?? root?.kind ?? "Genome";
  lines.push(`  mod["<b>${esc(packageName)}</b><br/><i>${rootLabel}</i>"]:::${classFor(root?.kind ?? "Genome")}`);
  lines.push("");

  const declaredNodes = new Set<string>();
  const nodeIdFor = (kind: string, name: string) => `n_${safe(kind)}_${safe(name)}`;

  const declareNode = (kind: string, name: string, label?: string) => {
    const id = nodeIdFor(kind, name);
    if (declaredNodes.has(id)) return id;
    declaredNodes.add(id);
    lines.push(`  ${id}["${esc(label ?? name)}"]:::${classFor(kind)}`);
    return id;
  };

  // Richer label via kp.graphMeta or kp.summary — no kind-name branching.
  const makeLabel = (doc: Document): string => {
    const kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
    const meta = kp?.graphMeta?.(doc) ?? kp?.summary(doc) ?? null;
    if (!meta) return doc.name;
    const m = meta as Record<string, unknown>;
    if (typeof m.model === "string" && m.model) {
      return `<b>${doc.name}</b><br/><i>${m.model}</i>`;
    }
    if (typeof m.severity === "string") {
      return `${doc.name}<br/><i>${m.severity}</i>`;
    }
    if (typeof m.type === "string") {
      return `${doc.name}<br/><i>${m.type}</i>`;
    }
    return doc.name;
  };

  // Orchestrator kinds from profiles — used for default_agent edge styling.
  const orchestratorKinds = new Set<string>();
  for (const p of profiles) {
    const kp = mi.kindForAlias(p.orchestratorAlias);
    if (kp) orchestratorKinds.add(kp.kind);
  }

  // Walk every non-root document and declare it as a node.
  for (const doc of mi.documents) {
    if (mi.isRootDoc(doc)) continue;
    declareNode(doc.kind, doc.name, makeLabel(doc));
  }

  lines.push("");

  // Edges from the Module root via its declared dep_filters.
  if (root) {
    const defaultAgent = (root.spec.default_agent as string) ?? "";
    for (const dep of mi.iterDocDeps(root)) {
      for (const name of dep.names) {
        const tid = nodeIdFor(dep.targetKind, name);
        if (!declaredNodes.has(tid)) {
          declareNode(dep.targetKind, name, `${name}<br/><i>(missing)</i>`);
        }
        if (orchestratorKinds.has(dep.targetKind) && name === defaultAgent) {
          lines.push(`  mod ==>|default| ${tid}`);
        } else {
          lines.push(`  mod -->|${dep.label}| ${tid}`);
        }
      }
    }
  }

  // Edges from every orchestrator (agent) via its declared dep_filters.
  for (const agent of mi.allWhere(kp => kp.isPromptTarget && !kp.isRoot && !kp.flattenInContext)) {
    const src = nodeIdFor(agent.kind, agent.name);
    for (const dep of mi.iterDocDeps(agent)) {
      for (const name of dep.names) {
        const tid = nodeIdFor(dep.targetKind, name);
        if (!declaredNodes.has(tid)) {
          declareNode(dep.targetKind, name, `${name}<br/><i>(missing)</i>`);
        }
        lines.push(`  ${src} -->|${dep.label}| ${tid}`);
      }
    }
  }

  // Edges from every non-root, non-agent doc that has depFilters.
  for (const depDoc of mi.documents.filter(d => {
    const kp = kinds.get(`${d.apiVersion}\0${d.kind}`);
    return kp && !kp.isRoot && !kp.isPromptTarget && kp.depFilters();
  })) {
    const src = nodeIdFor(depDoc.kind, depDoc.name);
    for (const dep of mi.iterDocDeps(depDoc)) {
      for (const name of dep.names) {
        const tid = nodeIdFor(dep.targetKind, name);
        if (!declaredNodes.has(tid)) {
          declareNode(dep.targetKind, name, `${name}<br/><i>(missing)</i>`);
        }
        lines.push(`  ${src} -.->|${dep.label}| ${tid}`);
      }
    }
  }

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// C4 Component Mermaid
// ---------------------------------------------------------------------------

export function c4ComponentMermaid(mi: ManifestInstance): string {
  const profiles = _profiles(mi);

  const lines = ["graph LR"];
  const root = mi.root;
  const packageName = root?.name ?? mi.scope;
  const agents = mi.allWhere(kp => kp.isPromptTarget && !kp.isRoot && !kp.flattenInContext);
  const esc = (s: string) => s.replace(/"/g, "'").replace(/\n/g, " ");
  const safe = (s: string) => s.replace(/-/g, "_").replace(/[^a-zA-Z0-9_]/g, "_");

  lines.push("  classDef module fill:#3B82F6,color:#fff,stroke:#2563EB,stroke-width:2px,font-size:14px");
  lines.push("  classDef agent fill:#F97316,color:#fff,stroke:#EA580C,stroke-width:2px");
  lines.push("  classDef stat fill:#F8FAFC,color:#334155,stroke:#CBD5E1,stroke-width:1px");
  lines.push("");

  const kindCounts = new Map<string, number>();
  for (const d of mi.documents) {
    if (mi.isRootDoc(d)) continue;
    kindCounts.set(d.kind, (kindCounts.get(d.kind) ?? 0) + 1);
  }
  const orchestratorKinds = new Set<string>();
  for (const p of profiles) {
    const kp = mi.kindForAlias(p.orchestratorAlias);
    if (kp) orchestratorKinds.add(kp.kind);
  }
  const countParts: string[] = [];
  for (const ok of orchestratorKinds) {
    const n = kindCounts.get(ok) ?? 0;
    const label = mi.kindFor(ok)?.displayLabel ?? ok;
    if (n > 0) countParts.push(`${n} ${label.toLowerCase()}`);
  }
  const otherKinds = Array.from(kindCounts.entries())
    .filter(([k]) => !orchestratorKinds.has(k))
    .sort(([a], [b]) => a.localeCompare(b));
  for (const [k, n] of otherKinds) {
    const label = mi.kindFor(k)?.displayLabel ?? k;
    countParts.push(`${n} ${label.toLowerCase()}${n === 1 ? "" : "s"}`);
  }
  const countLabel = countParts.join(" \u00B7 ") || "empty";
  lines.push(`  mod["<b>${esc(packageName)}</b><br/><i>${countLabel}</i>"]:::module`);
  lines.push("");

  const defaultAgent = (root?.spec.default_agent as string) ?? "";

  for (const agent of agents) {
    const agentId = `a_${safe(agent.name)}`;
    const model = (agent.spec.model as string) ?? "";
    const isDefault = agent.name === defaultAgent;

    const deps = mi.iterDocDeps(agent);
    const statParts: string[] = [];
    for (const dep of deps) {
      if (dep.names.length === 1) {
        statParts.push(`${dep.label}: ${dep.names[0]}`);
      } else {
        statParts.push(`${dep.names.length} ${dep.label}`);
      }
    }

    const label = `<b>${esc(agent.name)}</b><br/><i>${esc(model)}</i><br/>${statParts.join(" \u00B7 ")}`;
    lines.push(`  ${agentId}["${label}"]:::agent`);

    const edgeLabel = isDefault ? "default agent" : "agent";
    const edgeStyle = isDefault ? "==>" : "-->";
    lines.push(`  mod ${edgeStyle}|${edgeLabel}| ${agentId}`);
  }

  if (root) {
    const rootDeps = mi.iterDocDeps(root);
    for (const dep of rootDeps) {
      if (dep.label === "agents") continue;
      const nodeId = `m_${safe(dep.label)}`;
      const preview = dep.names.slice(0, 4).join(", ") + (dep.names.length > 4 ? ", \u2026" : "");
      lines.push(`  ${nodeId}["<b>${dep.names.length} ${dep.targetKind}${dep.names.length === 1 ? "" : "s"}</b><br/>${esc(preview)}"]:::stat`);
      lines.push(`  mod -->|${dep.label}| ${nodeId}`);
    }
  }

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// ER Model (structured)
// ---------------------------------------------------------------------------

export function erModel(mi: ManifestInstance): {
  entities: { id: string; kind: string; name: string; attrs: { key: string; type: string; value: string }[] }[];
  relationships: { sourceId: string; targetId: string; label: string; isMany: boolean }[];
} {
  const kinds = _kinds(mi);
  const profiles = _profiles(mi);

  const _SKIP_TEXT = new Set([
    "instruction", "content", "soul_content", "identity_content",
    "style_content", "heartbeat_content", "agents_content", "soul_json",
  ]);
  const _SKIP_REF = new Set(["dependencies", "default_agent"]);
  for (const profile of profiles) {
    for (const slot of profile.slots) _SKIP_REF.add(slot.name);
  }
  const _SKIP_OBJ = new Set([
    "scripts", "references", "assets", "extras", "root_files", "budget", "layers", "custom_kinds",
  ]);

  const entityId = (kind: string, name: string): string => {
    const raw = `${kind}_${name}`;
    return raw.replace(/[^a-zA-Z0-9_]/g, "_").replace(/_{2,}/g, "_").replace(/_$/, "").slice(0, 80);
  };

  const cleanVal = (v: string, max = 50): string =>
    v.replace(/"/g, "'").replace(/\n/g, " ").slice(0, max);

  const entities: { id: string; kind: string; name: string; attrs: { key: string; type: string; value: string }[] }[] = [];
  const relationships: { sourceId: string; targetId: string; label: string; isMany: boolean }[] = [];

  for (const d of mi.documents) {
    const attrs: { key: string; type: string; value: string }[] = [];
    const spec = d.spec;

    for (const [k, v] of Object.entries(spec)) {
      if (_SKIP_TEXT.has(k) || _SKIP_REF.has(k)) continue;
      if ((typeof v === "object" && v !== null && !Array.isArray(v)) && _SKIP_OBJ.has(k)) continue;
      if (Array.isArray(v) && _SKIP_OBJ.has(k)) continue;

      if (typeof v === "string" && v.length > 0 && v.length < 60 && !v.includes("\n")) {
        attrs.push({ key: k, type: "string", value: cleanVal(v) });
      } else if (Array.isArray(v)) {
        const strItems = v.filter((x): x is string => typeof x === "string");
        if (strItems.length > 0 && strItems.length === v.length) {
          attrs.push({ key: k, type: "list", value: cleanVal(strItems.join(", ")) });
        } else if (v.length > 0) {
          attrs.push({ key: k, type: "list", value: `${v.length} items` });
        }
      }
    }

    entities.push({ id: entityId(d.kind, d.name), kind: d.kind, name: d.name, attrs });
  }

  // Build relationships from depFilters
  for (const d of mi.documents) {
    const kp = kinds.get(`${d.apiVersion}\0${d.kind}`);
    if (!kp) continue;
    const filters = kp.depFilters();
    if (!filters) continue;

    const spec = d.spec;
    const srcId = entityId(d.kind, d.name);

    for (const [field, targetAlias] of Object.entries(filters)) {
      const declared = spec[field];
      if (!declared) continue;

      const refs: string[] = Array.isArray(declared)
        ? declared as string[]
        : typeof declared === "string" ? [declared] : [];

      let targetKindName: string | null = null;
      for (const [, tkp] of kinds) {
        if (tkp.alias === targetAlias) { targetKindName = tkp.kind; break; }
      }

      for (const ref of refs) {
        const targetDoc = mi.documents.find(
          (td) => td.name === ref && (targetKindName ? td.kind === targetKindName : true),
        );
        const tgtId = targetDoc
          ? entityId(targetDoc.kind, targetDoc.name)
          : ref.replace(/-/g, "_").replace(/ /g, "_");

        relationships.push({ sourceId: srcId, targetId: tgtId, label: field, isMany: field.endsWith("s") });
      }
    }
  }

  // Root -> default_agent
  const root = mi.root;
  if (root) {
    const da = (root.spec.default_agent as string) ?? null;
    if (da) {
      const targetDoc = mi.documents.find((td) => {
        if (td.name !== da) return false;
        const kp = kinds.get(`${td.apiVersion}\0${td.kind}`);
        return kp?.isPromptTarget && !kp.flattenInContext;
      });
      const tgtId = targetDoc ? entityId(targetDoc.kind, da) : da.replace(/-/g, "_");
      relationships.push({ sourceId: entityId(root.kind, root.name), targetId: tgtId, label: "default_agent", isMany: false });
    }
  }

  return { entities, relationships };
}

// ---------------------------------------------------------------------------
// ER Diagram Mermaid
// ---------------------------------------------------------------------------

export function erDiagramMermaid(mi: ManifestInstance): string {
  const { entities, relationships } = erModel(mi);
  const lines = ["erDiagram"];

  const safeId = (s: string) => s.replace(/-/g, "_").replace(/ /g, "_").replace(/\./g, "_");

  for (const e of entities) {
    lines.push(`    ${e.id} {`);
    lines.push(`        string kind "${e.kind}"`);
    for (const a of e.attrs) {
      lines.push(`        ${a.type} ${safeId(a.key)} "${a.value.replace(/"/g, "'")}"`);
    }
    lines.push(`    }`);
  }

  for (const r of relationships) {
    const rel = r.isMany ? "}o--||" : "||--||";
    lines.push(`    ${r.sourceId} ${rel} ${r.targetId} : "${r.label}"`);
  }

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Mindmap Mermaid
// ---------------------------------------------------------------------------

export function mindmapMermaid(mi: ManifestInstance): string {
  const root = mi.root;
  const rootName = root?.name ?? mi.scope;
  const lines = ["mindmap", `  root((${rootName}))`];

  const tree = mi.dependencyTree();
  if (Object.keys(tree).length === 0) {
    const byKind = new Map<string, string[]>();
    for (const d of mi.documents) {
      if (!byKind.has(d.kind)) byKind.set(d.kind, []);
      byKind.get(d.kind)!.push(d.name);
    }
    for (const [kind, names] of byKind) {
      lines.push(`    ${kind}`);
      for (const n of names) lines.push(`      ${n}`);
    }
    return lines.join("\n");
  }

  for (const [docName, info] of Object.entries(tree)) {
    const i = info as Record<string, unknown>;
    lines.push(`    ${docName}`);
    const dependsOn = (i.depends_on as Record<string, unknown>) ?? {};
    for (const deps of Object.values(dependsOn)) {
      for (const depName of Object.keys(deps as Record<string, unknown>)) {
        lines.push(`      ${depName}`);
      }
    }
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Pie Chart Mermaid
// ---------------------------------------------------------------------------

export function pieChartMermaid(mi: ManifestInstance): string {
  const counts = new Map<string, number>();
  for (const d of mi.documents) {
    counts.set(d.kind, (counts.get(d.kind) ?? 0) + 1);
  }

  const lines = [`pie title Documents by Kind (${mi.documents.length} total)`];
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  for (const [kind, count] of sorted) {
    lines.push(`    "${kind}" : ${count}`);
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Quadrant Mermaid
// ---------------------------------------------------------------------------

export function quadrantMermaid(mi: ManifestInstance): string {
  const profiles = _profiles(mi);

  let xSlot: { name: string; label: string; maxScale: number } | null = null;
  let ySlot: { name: string; label: string; maxScale: number } | null = null;
  for (const profile of profiles) {
    for (const slot of profile.slots) {
      if (slot.quadrant?.axis === "x") xSlot = { name: slot.name, label: slot.quadrant.label, maxScale: slot.quadrant.maxScale };
      if (slot.quadrant?.axis === "y") ySlot = { name: slot.name, label: slot.quadrant.label, maxScale: slot.quadrant.maxScale };
    }
  }

  const xLabel = xSlot?.label ?? "X-axis";
  const yLabel = ySlot?.label ?? "Y-axis";

  const lines = [
    "quadrantChart",
    "    title Agent Complexity",
    `    x-axis ${xLabel}`,
    `    y-axis ${yLabel}`,
    "    quadrant-1 High safety + High capability",
    "    quadrant-2 High safety + Low capability",
    "    quadrant-3 Low safety + Low capability",
    "    quadrant-4 Low safety + High capability",
  ];

  const tree = mi.dependencyTree();
  for (const [docName, info] of Object.entries(tree)) {
    const i = info as Record<string, unknown>;
    const dependsOn = (i.depends_on as Record<string, unknown>) ?? {};
    const nX = xSlot ? Object.keys((dependsOn[xSlot.name] as Record<string, unknown>) ?? {}).length : 0;
    const nY = ySlot ? Object.keys((dependsOn[ySlot.name] as Record<string, unknown>) ?? {}).length : 0;
    const x = nX > 0 ? Math.min(nX / (xSlot?.maxScale ?? 10), 1.0) : 0.05;
    const y = nY > 0 ? Math.min(nY / (ySlot?.maxScale ?? 10), 1.0) : 0.05;
    lines.push(`    ${docName}: [${x.toFixed(2)}, ${y.toFixed(2)}]`);
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Timeline Mermaid
// ---------------------------------------------------------------------------

export function timelineMermaid(mi: ManifestInstance): string {
  const kinds = _kinds(mi);
  const root = mi.root;
  let agentDoc: Document | null = null;
  if (root) {
    const kp = kinds.get(`${root.apiVersion}\0${root.kind}`);
    if (kp) {
      const agentName = kp.getDefaultAgentName(root);
      if (agentName) {
        // Find agent by name + highest promptTargetPriority (same logic as PromptBuilder._findAgent)
        let best: Document | null = null;
        let bestPriority = -1;
        for (const d of mi.documents) {
          const dkp = kinds.get(`${d.apiVersion}\0${d.kind}`);
          if (dkp?.isPromptTarget && d.name === agentName) {
            const priority = dkp.promptTargetPriority ?? 0;
            if (priority > bestPriority) {
              best = d;
              bestPriority = priority;
            }
          }
        }
        agentDoc = best;
      }
    }
  }

  const lines = ["timeline", "    title Prompt Composition Phases"];

  if (root) {
    lines.push("    section 1. Root Module");
    lines.push(`        ${root.name} : Module loaded`);
  }

  if (agentDoc) {
    lines.push("    section 2. Agent Resolution");
    lines.push(`        ${agentDoc.name} : default_agent resolved`);

    const profile = mi.profileFor(agentDoc);
    if (profile) {
      const sortedSlots = [...profile.slots]
        .filter(s => s.timeline)
        .sort((a, b) => a.order - b.order);
      let sectionNum = 3;
      for (const slot of sortedSlots) {
        const deps = mi.iterDocDeps(agentDoc);
        const slotDeps = deps.find(d => d.label === slot.name);
        const names = slotDeps?.names ?? [];
        if (names.length > 0 || slot.cardinality === "one") {
          if (slot.cardinality === "one" && names.length > 0) {
            lines.push(`    section ${sectionNum}. ${slot.timeline!.label} (flatten)`);
            lines.push(`        ${names[0]} : ${slot.timeline!.itemLabel}`);
          } else if (names.length > 0) {
            lines.push(`    section ${sectionNum}. ${slot.timeline!.label}`);
            for (const n of names) {
              lines.push(`        ${n} : ${slot.timeline!.itemLabel}`);
            }
          }
          sectionNum++;
        }
      }
    }
  }

  lines.push("    section 6. Render");
  lines.push("        Template cascade : agent \u2192 kind \u2192 fallback");
  lines.push("        Mustache render : final prompt");
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Sankey Mermaid
// ---------------------------------------------------------------------------

export function sankeyMermaid(mi: ManifestInstance): string {
  const lines = ["sankey-beta", ""];

  const tree = mi.dependencyTree();
  const rootName = mi.root?.name ?? "";
  const seen = new Set<string>();

  for (const [docName, info] of Object.entries(tree)) {
    const i = info as Record<string, unknown>;
    const docKind = (i.kind as string) ?? "";
    const docKp = mi.kindFor(docKind);
    if (!docKp?.isPromptTarget || docKp.isRoot) continue;

    const dependsOn = (i.depends_on as Record<string, unknown>) ?? {};
    for (const deps of Object.values(dependsOn)) {
      for (const depName of Object.keys(deps as Record<string, unknown>)) {
        if (depName === rootName) continue;
        const key = `${depName}\u2192${docName}`;
        if (seen.has(key)) continue;
        seen.add(key);
        lines.push(`"${depName}","${docName}",1`);
      }
    }
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Kind Catalog Mermaid
// ---------------------------------------------------------------------------

export function kindCatalogMermaid(mi: ManifestInstance): string {
  const kinds = _kinds(mi);

  const seen = new Set<string>();
  const lines = ["classDiagram"];
  const edgeLines: string[] = [];

  for (const doc of mi.documents) {
    const kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
    if (!kp || seen.has(kp.kind)) continue;
    seen.add(kp.kind);

    const safe = kp.kind.replace(/ /g, "_");
    lines.push(`    class ${safe} {`);
    lines.push(`        <<${kp.alias}>>`);
    lines.push(`        ${kp.apiVersion}`);
    lines.push(`        ---`);
    const flags: string[] = [];
    if (kp.isRoot) flags.push("is_root");
    if (kp.isPromptTarget) flags.push(`prompt_target (priority=${kp.promptTargetPriority})`);
    if (kp.flattenInContext) flags.push("flatten_in_context");
    if (flags.length > 0) {
      for (const f of flags) lines.push(`        ${f}`);
    } else {
      lines.push(`        passive`);
    }
    const filters = kp.depFilters();
    if (filters) {
      lines.push(`        ---`);
      for (const [field, alias] of Object.entries(filters)) {
        lines.push(`        ${field} -> ${alias}`);
      }
    }
    lines.push(`    }`);

    if (filters) {
      for (const [field, alias] of Object.entries(filters)) {
        for (const tkp of kinds.values()) {
          if (tkp.alias === alias) {
            edgeLines.push(`    ${safe} --> ${tkp.kind.replace(/ /g, "_")} : ${field}`);
            break;
          }
        }
      }
    }
  }

  if (edgeLines.length > 0) {
    lines.push("");
    lines.push(...edgeLines);
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Export Diagrams Markdown
// ---------------------------------------------------------------------------

export function exportDiagramsMd(mi: ManifestInstance, path?: string): Record<string, string> {
  const diagrams: [string, string, string][] = [
    ["c4-component", "C4 Component (Architecture)", c4ComponentMermaid(mi)],
    ["composition-flowchart", "Composition Flowchart", compositionFlowchartMermaid(mi)],
    ["er-diagram", "Entity Relationship", erDiagramMermaid(mi)],
    ["dependency-tree", "[Deprecated] Dependency Tree", dependencyTreeMermaid(mi)],
    ["kind-catalog", "Kind Catalog", kindCatalogMermaid(mi)],
    ["mindmap", "Mindmap", mindmapMermaid(mi)],
    ["pie-chart", "Document Distribution", pieChartMermaid(mi)],
    ["quadrant", "Agent Complexity", quadrantMermaid(mi)],
    ["timeline", "Prompt Composition", timelineMermaid(mi)],
    ["sankey", "Document Flow", sankeyMermaid(mi)],
  ];

  const files: Record<string, string> = {};

  for (const [slug, title, mermaid] of diagrams) {
    files[`${slug}.md`] = `# ${title}\n\n\`\`\`mermaid\n${mermaid}\n\`\`\`\n`;
  }

  const allLines = [`# ${mi.scope} \u2014 All Diagrams\n`];
  for (const [, title, mermaid] of diagrams) {
    allLines.push(`## ${title}\n\n\`\`\`mermaid\n${mermaid}\n\`\`\`\n`);
  }
  files["all-diagrams.md"] = allLines.join("\n");

  if (path) {
    const { mkdirSync, writeFileSync } = require("node:fs");
    const { join } = require("node:path");
    mkdirSync(path, { recursive: true });
    for (const [fname, content] of Object.entries(files)) {
      writeFileSync(join(path, fname), content, "utf-8");
    }
  }

  return files;
}
