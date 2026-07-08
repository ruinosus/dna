/**
 * ReportBuilder — structured markdown reports for eval, findings, evidence, compliance.
 *
 * Accessed via `mi.reports.evalSummary()`, `mi.reports.findingsSummary()`,
 * `mi.reports.evidenceManifest()`, `mi.reports.complianceMatrix(framework)`.
 *
 * Each report returns Markdown with YAML frontmatter.
 *
 * 1:1 parity with Python dna.kernel.reports.
 */

import type { ManifestInstance } from "./instance.js";
import type { Document } from "./document.js";

// ─── Severity ordering (lower = more severe) ─────────────────────────
const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

// ─── Compliance mappings ─────────────────────────────────────────────
const COMPLIANCE_MAPPINGS: Record<string, Record<string, string[]>> = {
  lgpd: {
    critical: ["Art. 6 (tratamento de dados)", "Art. 46 (seguranca)"],
    high: ["Art. 50 (boas praticas)"],
  },
  gdpr: {
    critical: ["Art. 25 (data protection by design)", "Art. 35 (DPIA)"],
    high: ["Art. 32 (security of processing)"],
  },
  nist_ai_rmf: {
    critical: ["MAP-1.1 (intended purpose)", "MEASURE-2.6 (bias)"],
    high: ["MANAGE-2.2 (risk response)"],
  },
};

function frontmatter(reportType: string, scope: string): string {
  const now = new Date().toISOString();
  return `---\nreport: ${reportType}\ngenerated_at: ${now}\nscope: ${scope}\n---\n\n`;
}

export class ReportBuilder {
  private readonly _mi: ManifestInstance;

  constructor(mi: ManifestInstance) {
    this._mi = mi;
  }

  // ─── evalSummary ──────────────────────────────────────────────────

  /** Generate an eval summary report grouped by suite.
   *  If `suite` is given, only that suite is included. */
  evalSummary(suite?: string): string {
    let runs = this._mi._all("EvalRun");
    if (suite) {
      runs = runs.filter(
        (r) => (r.spec as Record<string, unknown>).suite === suite,
      );
    }

    let md = frontmatter("eval_summary", this._mi.scope);
    md += "# Eval Summary\n\n";

    if (runs.length === 0) {
      md += "_No eval runs found._\n";
      return md;
    }

    // Group by suite, keep latest per suite (by saved_at)
    const bySuite = new Map<string, Document>();
    for (const run of runs) {
      const spec = run.spec as Record<string, unknown>;
      const s = (spec.suite as string) ?? "unknown";
      const existing = bySuite.get(s);
      if (!existing) {
        bySuite.set(s, run);
      } else {
        const newTs = (spec.saved_at as string) ?? "";
        const oldTs =
          ((existing.spec as Record<string, unknown>).saved_at as string) ?? "";
        if (newTs > oldTs) {
          bySuite.set(s, run);
        }
      }
    }

    const sortedSuites = [...bySuite.entries()].sort(([a], [b]) =>
      a.localeCompare(b),
    );

    for (const [suiteName, run] of sortedSuites) {
      const spec = run.spec as Record<string, unknown>;
      const total = (spec.total as number) ?? 0;
      const passed = (spec.passed as number) ?? 0;
      const rate = total ? `${((passed / total) * 100).toFixed(1)}%` : "N/A";
      const agg = spec.aggregate_score as number | undefined;
      const aggStr =
        agg != null ? (agg as number).toFixed(2) : "N/A";
      const cost = spec.total_cost_usd as number | undefined;
      const costStr =
        cost != null ? `$${(cost as number).toFixed(4)}` : "N/A";
      const tokens = spec.total_tokens as number | undefined;
      const tokensStr = tokens != null ? String(tokens) : "N/A";

      md += `## Suite: ${suiteName}\n\n`;
      md += `- **Pass rate:** ${rate}\n`;
      md += `- **Aggregate score:** ${aggStr}\n`;
      md += `- **Cost:** ${costStr}\n`;
      md += `- **Tokens:** ${tokensStr}\n\n`;

      const results = (spec.results ?? []) as Array<Record<string, unknown>>;
      if (results.length > 0) {
        md += "| Case | Status | Score |\n";
        md += "|------|--------|-------|\n";
        for (const r of results) {
          const caseName = (r.case as string) ?? "";
          const status = (r.status as string) ?? "";
          const score = r.score as number | undefined;
          const scoreStr =
            score != null ? (score as number).toFixed(2) : "-";
          md += `| ${caseName} | ${status} | ${scoreStr} |\n`;
        }
        md += "\n";
      }
    }

    return md;
  }

  // ─── findingsSummary ──────────────────────────────────────────────

  /** Generate a findings summary grouped by severity.
   *  Filters out findings with severity below `minSeverity`. */
  findingsSummary(minSeverity: string = "low"): string {
    const findings = this._mi._all("Finding");
    const minLevel = SEVERITY_ORDER[minSeverity] ?? 3;

    const filtered = findings.filter((f) => {
      const sev = (f.spec as Record<string, unknown>).severity as string;
      return (SEVERITY_ORDER[sev ?? "low"] ?? 3) <= minLevel;
    });

    let md = frontmatter("findings_summary", this._mi.scope);
    md += "# Findings Summary\n\n";

    if (filtered.length === 0) {
      md += "_No findings found._\n";
      return md;
    }

    // Group by severity
    const bySeverity = new Map<string, Document[]>();
    for (const f of filtered) {
      const sev =
        ((f.spec as Record<string, unknown>).severity as string) ?? "low";
      const arr = bySeverity.get(sev) ?? [];
      arr.push(f);
      bySeverity.set(sev, arr);
    }

    for (const sev of ["critical", "high", "medium", "low"]) {
      const group = bySeverity.get(sev);
      if (!group || group.length === 0) continue;
      md += `## ${sev.toUpperCase()} (${group.length})\n\n`;
      for (const f of group) {
        const spec = f.spec as Record<string, unknown>;
        const title = (spec.title as string) ?? f.name;
        const status = (spec.status as string) ?? "open";
        const recommendation = (spec.recommendation as string) ?? "";
        md += `### ${title}\n\n`;
        md += `- **Status:** ${status}\n`;
        if (recommendation) {
          md += `- **Recommendation:** ${recommendation}\n`;
        }
        md += "\n";
      }
    }

    return md;
  }

  // ─── evidenceManifest ─────────────────────────────────────────────

  /** Generate a manifest of all evidence documents. */
  evidenceManifest(): string {
    const evidence = this._mi._all("Evidence");

    let md = frontmatter("evidence_manifest", this._mi.scope);
    md += "# Evidence Manifest\n\n";

    if (evidence.length === 0) {
      md += "_No evidence documents found._\n";
      return md;
    }

    md += "| Event Type | Document Ref | SHA-256 | Captured At |\n";
    md += "|------------|-------------|---------|-------------|\n";
    for (const e of evidence) {
      const spec = e.spec as Record<string, unknown>;
      const eventType = (spec.event_type as string) ?? "";
      const docRef = (spec.document_ref as string) ?? "";
      const sha = (spec.sha256 as string) ?? "";
      const shaShort = sha.length > 12 ? sha.slice(0, 12) + "..." : sha;
      const captured = (spec.captured_at as string) ?? "";
      md += `| ${eventType} | ${docRef} | ${shaShort} | ${captured} |\n`;
    }

    md += "\n";
    return md;
  }

  // ─── complianceMatrix ─────────────────────────────────────────────

  /** Generate a compliance matrix mapping findings to regulatory articles.
   *  Supported frameworks: lgpd, gdpr, nist_ai_rmf. */
  complianceMatrix(framework: string): string {
    let md = frontmatter("compliance_matrix", this._mi.scope);
    md += `# Compliance Matrix: ${framework.toUpperCase()}\n\n`;

    const mapping = COMPLIANCE_MAPPINGS[framework];
    if (!mapping) {
      const supported = Object.keys(COMPLIANCE_MAPPINGS).sort().join(", ");
      md += `_Unknown framework: ${framework}. Supported: ${supported}._\n`;
      return md;
    }

    const findings = this._mi._all("Finding");

    md += "| Severity | Count | Regulatory Articles |\n";
    md += "|----------|-------|--------------------|\n";
    for (const sev of ["critical", "high", "medium", "low"]) {
      const articles = mapping[sev] ?? [];
      const count = findings.filter(
        (f) => (f.spec as Record<string, unknown>).severity === sev,
      ).length;
      const articlesStr = articles.length > 0 ? articles.join(", ") : "-";
      md += `| ${sev.toUpperCase()} | ${count} | ${articlesStr} |\n`;
    }

    md += "\n";

    if (findings.length > 0) {
      md += "## Findings by Article\n\n";
      for (const sev of ["critical", "high"]) {
        const articles = mapping[sev] ?? [];
        const sevFindings = findings.filter(
          (f) => (f.spec as Record<string, unknown>).severity === sev,
        );
        if (sevFindings.length > 0 && articles.length > 0) {
          for (const article of articles) {
            md += `### ${article}\n\n`;
            for (const f of sevFindings) {
              const title =
                ((f.spec as Record<string, unknown>).title as string) ?? f.name;
              md += `- ${title}\n`;
            }
            md += "\n";
          }
        }
      }
    }

    return md;
  }
}
