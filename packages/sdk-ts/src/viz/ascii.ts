/**
 * ASCII tree rendering — standalone function operating on ManifestInstance.
 *
 * Extracted from ManifestInstance to keep the kernel class focused.
 */

import type { ManifestInstance } from "../kernel/instance.js";

// ---------------------------------------------------------------------------
// ASCII Tree
// ---------------------------------------------------------------------------

export function asciiTree(mi: ManifestInstance): string {
  const tree = mi.dependencyTree();
  if (Object.keys(tree).length === 0) {
    return "(no dependencies)";
  }

  const lines: string[] = [`\u{1F4E6} ${mi.scope}`];
  const agentNames = Object.keys(tree).sort();

  for (let i = 0; i < agentNames.length; i++) {
    const agentName = agentNames[i];
    const info = tree[agentName] as Record<string, unknown>;
    const isLastAgent = i === agentNames.length - 1;
    const prefix = isLastAgent ? "\u2514\u2500\u2500 " : "\u251C\u2500\u2500 ";
    const childPrefix = isLastAgent ? "    " : "\u2502   ";

    lines.push(`${prefix}\u{1F916} ${agentName}`);

    const dependsOn = (info.depends_on ?? {}) as Record<string, Record<string, Record<string, unknown>>>;
    const depGroups = Object.entries(dependsOn);

    for (let j = 0; j < depGroups.length; j++) {
      const [depType, deps] = depGroups[j];
      const isLastGroup = j === depGroups.length - 1;
      const groupPrefix = isLastGroup ? "\u2514\u2500\u2500 " : "\u251C\u2500\u2500 ";
      const itemPrefix = isLastGroup ? "    " : "\u2502   ";

      lines.push(`${childPrefix}${groupPrefix}${depType}/`);

      const depItems = Object.entries(deps);
      for (let k = 0; k < depItems.length; k++) {
        const [depName, depInfo] = depItems[k];
        const isLastDep = k === depItems.length - 1;
        const depPrefix = isLastDep ? "\u2514\u2500\u2500 " : "\u251C\u2500\u2500 ";
        const kind = (depInfo.kind as string) ?? "";
        const found = (depInfo.found as boolean) ?? true;

        // Use KindPort.asciiIcon + graphMeta for kind-specific labels
        const depKp = mi.kindFor(kind);
        const depIcon = depKp?.asciiIcon ?? "";
        const depDoc = mi._one(kind, depName);
        const depMeta = depDoc ? (depKp?.graphMeta?.(depDoc) ?? {}) : {};
        let label: string;
        if ((depMeta as Record<string, unknown>).severity) {
          const m = depMeta as Record<string, unknown>;
          const severityIcon = m.severity === "error" ? "\u{1F534}" : "\u{1F7E1}";
          label = `${severityIcon} ${depName} (${m.rules ?? 0} rules, ${m.severity})`;
        } else {
          label = depIcon ? `${depIcon} ${depName}` : depName;
        }

        if (!found) {
          label += " \u274C MISSING";
        }

        lines.push(`${childPrefix}${itemPrefix}${depPrefix}${label}`);
      }
    }
  }

  return lines.join("\n");
}
