/**
 * Health report and impact analysis — standalone functions operating on ManifestInstance.
 *
 * Extracted from ManifestInstance to keep the kernel class focused.
 */

import type { ManifestInstance } from "../kernel/instance.js";
import type { KindPort } from "../kernel/protocols.js";
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
// Health Report
// ---------------------------------------------------------------------------

export function healthReport(mi: ManifestInstance): Record<string, unknown> {
  const kinds = _kinds(mi);
  const profiles = _profiles(mi);

  const tree = mi.dependencyTree();
  const comp = mi.compositionResult;

  // All orchestrators (agents) — found via composition profiles
  const allAgents = mi.allWhere(kp => kp.isPromptTarget && !kp.isRoot && !kp.flattenInContext);
  const agentNames = new Set(allAgents.map((a) => a.name));

  // --- Generic slot-based health checks via CompositionProfile ---
  const slotIssues: Record<string, string[]> = {};
  const slotCoverage: Record<string, string> = {};
  const slotTotals: Record<string, number> = {};
  let hasIssues = false;

  for (const agent of allAgents) {
    const profile = mi.profileFor(agent);
    if (!profile) continue;

    for (const slot of profile.slots) {
      if (!slot.healthCheck) continue;
      const deps = mi.iterDocDeps(agent);
      const slotDeps = deps.find(d => d.label === slot.name);
      const names = slotDeps?.names ?? [];

      if (slot.healthCheck.rule === "at-least-one" && names.length === 0) {
        const key = slot.healthCheck.issueKey;
        (slotIssues[key] ??= []).push(agent.name);
        hasIssues = true;
      }
    }
  }

  // Coverage stats per slot
  for (const profile of profiles) {
    for (const slot of profile.slots) {
      if (!slot.healthCheck) continue;
      const issueList = slotIssues[slot.healthCheck.issueKey] ?? [];
      const covered = allAgents.length - issueList.length;
      slotCoverage[slot.name] = `${covered}/${allAgents.length} agents`;

      // Count total docs of this slot's target kind
      const targetKp = mi.kindForAlias(slot.targetAlias);
      if (targetKp) {
        const allOfKind = mi._all(targetKp.kind);
        slotTotals[`${slot.name}_total`] = allOfKind.length;

        // For kinds with graphMeta returning severity, count rules
        let rulesCount = 0;
        for (const d of allOfKind) {
          const meta = targetKp.graphMeta?.(d) ?? targetKp.summary(d) ?? {};
          const m = meta as Record<string, unknown>;
          if (typeof m.rules === "number") rulesCount += m.rules;
        }
        if (rulesCount > 0) slotTotals[`${slot.name}_rules_total`] = rulesCount;

        // has-error-severity: find agents missing error-severity docs
        if (slot.healthCheck.rule === "at-least-one") {
          const errorDocs = allOfKind.filter(d => {
            const m = (targetKp.graphMeta?.(d) ?? targetKp.summary(d) ?? {}) as Record<string, unknown>;
            return m.severity === "error";
          });
          if (errorDocs.length > 0) {
            const agentsWithError = new Set<string>();
            for (const agent of allAgents) {
              const deps = mi.iterDocDeps(agent);
              const slotDeps = deps.find(dd => dd.label === slot.name);
              for (const depName of slotDeps?.names ?? []) {
                if (errorDocs.some(ed => ed.name === depName)) {
                  agentsWithError.add(agent.name);
                }
              }
            }
            const missing = [...agentNames].filter(n => !agentsWithError.has(n)).sort();
            if (missing.length > 0) {
              slotIssues[`agents_missing_error_${slot.name}`] = missing;
            }
          }
        }
      }
    }
  }

  // Referenced deps (from tree)
  const referenced = new Set<string>();
  for (const info of Object.values(tree)) {
    const treeInfo = info as Record<string, unknown>;
    const dependsOn = treeInfo.depends_on as Record<string, Record<string, unknown>> | undefined;
    if (!dependsOn) continue;
    for (const deps of Object.values(dependsOn)) {
      for (const depName of Object.keys(deps)) {
        referenced.add(depName);
      }
    }
  }

  // Find orphan documents (not referenced, not root, not prompt-target)
  const orphans: Array<{ kind: string; name: string }> = [];
  for (const doc of mi.documents) {
    const _kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
    if (_kp?.isRoot || _kp?.isPromptTarget) continue;
    if (!referenced.has(doc.name)) {
      orphans.push({ kind: doc.kind, name: doc.name });
    }
  }

  const isHealthy = comp.missing.length === 0 && !hasIssues;

  return {
    status: isHealthy ? "healthy" : "warnings",
    composition_valid: comp.missing.length === 0,
    missing_refs: comp.missing,
    agents_total: allAgents.length,
    // Slot issues — each key comes from slot.healthCheck.issueKey
    ...slotIssues,
    // Slot totals (e.g. guardrails_total, guardrails_rules_total)
    ...slotTotals,
    orphan_documents: orphans,
    coverage: slotCoverage,
  };
}

// ---------------------------------------------------------------------------
// Impact Analysis
// ---------------------------------------------------------------------------

export function impact(mi: ManifestInstance, kind: string, name: string): Record<string, unknown> {
  const tree = mi.dependencyTree();
  const affected: Array<{ agent: string; relationship: string }> = [];

  for (const [agentName, info] of Object.entries(tree)) {
    const treeInfo = info as Record<string, unknown>;
    const dependsOn = treeInfo.depends_on as Record<string, Record<string, unknown>> | undefined;
    if (!dependsOn) continue;
    for (const [depType, deps] of Object.entries(dependsOn)) {
      if (name in deps) {
        affected.push({ agent: agentName, relationship: depType });
      }
    }
  }

  const doc = mi._one(kind, name);
  return {
    kind,
    name,
    description: doc ? ((doc.metadata as Record<string, unknown>).description ?? "") : "",
    found: doc !== null,
    affected_agents: affected,
    affected_count: affected.length,
    safe_to_remove: affected.length === 0,
  };
}
