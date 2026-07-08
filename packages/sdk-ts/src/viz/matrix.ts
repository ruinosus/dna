/**
 * Matrix views — standalone functions operating on ManifestInstance.
 *
 * Extracted from ManifestInstance to keep the kernel class focused.
 */

import type { ManifestInstance } from "../kernel/instance.js";

// ---------------------------------------------------------------------------
// Matrix (structured)
// ---------------------------------------------------------------------------

export function matrix(mi: ManifestInstance): Record<string, unknown> {
  const tree = mi.dependencyTree();
  if (Object.keys(tree).length === 0) {
    return { agents: [], dependencies: {}, matrix: {} };
  }

  const agents = Object.keys(tree).sort();

  // Collect all deps grouped by kind
  const depsByKind = new Map<string, Set<string>>();
  for (const info of Object.values(tree)) {
    const treeInfo = info as Record<string, unknown>;
    const dependsOn = treeInfo.depends_on as Record<string, Record<string, Record<string, unknown>>> | undefined;
    if (!dependsOn) continue;
    for (const deps of Object.values(dependsOn)) {
      for (const [depName, depInfo] of Object.entries(deps)) {
        const kind = (depInfo.kind as string) ?? "Unknown";
        if (!depsByKind.has(kind)) depsByKind.set(kind, new Set());
        depsByKind.get(kind)!.add(depName);
      }
    }
  }

  // Build matrix
  const matrixData: Record<string, Record<string, boolean>> = {};
  for (const [agentName, info] of Object.entries(tree)) {
    const treeInfo = info as Record<string, unknown>;
    const dependsOn = treeInfo.depends_on as Record<string, Record<string, unknown>> | undefined;
    const row: Record<string, boolean> = {};
    if (dependsOn) {
      for (const deps of Object.values(dependsOn)) {
        for (const depName of Object.keys(deps)) {
          row[depName] = true;
        }
      }
    }
    matrixData[agentName] = row;
  }

  // Build sorted dependencies object
  const dependencies: Record<string, string[]> = {};
  const sortedKinds = [...depsByKind.keys()].sort();
  for (const kind of sortedKinds) {
    dependencies[kind] = [...depsByKind.get(kind)!].sort();
  }

  return { agents, dependencies, matrix: matrixData };
}

// ---------------------------------------------------------------------------
// Matrix Markdown
// ---------------------------------------------------------------------------

export function matrixMarkdown(mi: ManifestInstance): string {
  const data = matrix(mi);
  const agents = data.agents as string[];
  if (agents.length === 0) {
    return "No agents with dependencies found.";
  }

  const dependencies = data.dependencies as Record<string, string[]>;
  const matrixData = data.matrix as Record<string, Record<string, boolean>>;

  // Flatten all dep names in kind order
  const allDeps: Array<[string, string]> = []; // [kind, name]
  for (const [kind, names] of Object.entries(dependencies)) {
    for (const name of names) {
      allDeps.push([kind, name]);
    }
  }

  // Header
  const depHeaders = allDeps.map(([, n]) => n);
  const header = `| Agent | ${depHeaders.join(" | ")} |`;
  const sep = `|-------|${allDeps.map(() => ":---:").join("|")}|`;

  const rows: string[] = [];
  for (const agent of agents) {
    const cells = allDeps.map(([, depName]) =>
      matrixData[agent]?.[depName] ? "\u25CF" : " "
    );
    rows.push(`| **${agent}** | ${cells.join(" | ")} |`);
  }

  // Kind legend row
  const kindRow = `| *Kind* | ${allDeps.map(([k]) => `*${k[0].toUpperCase()}*`).join(" | ")} |`;

  return [header, sep, kindRow, ...rows].join("\n");
}
