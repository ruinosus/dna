"""ReportBuilder — structured markdown reports for eval, findings, evidence, compliance.

Accessed via ``mi.reports.eval_summary()``, ``mi.reports.findings_summary()``,
``mi.reports.evidence_manifest()``, ``mi.reports.compliance_matrix(framework)``.

Each report returns Markdown with YAML frontmatter.

two-planes F2.5 — EvalRun/Finding/Evidence são plane=record: as leituras
``self._mi.all`` abaixo DELEGAM pro kernel record-plane (query_list_sync,
Task 1). Contexto de thread verificado (2026-06-10): os métodos são SYNC e
os únicos chamadores são a API pública ``mi.reports`` (testes/uso direto,
off-loop); o caminho async de produção é ``reports_kernel.py`` (operations),
que JÁ usa ``kernel.query`` por Kind. Chamada sync na thread do loop
levantaria via _run_sync_helper — failing loud, by design. Push-down de
filtro aqui é follow-up sem ganho real (superfície legada, fria).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel.instance import ManifestInstance

# ─── Severity ordering (lower = more severe) ─────────────────────────
_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

# ─── Compliance mappings ─────────────────────────────────────────────
_COMPLIANCE_MAPPINGS: dict[str, dict[str, list[str]]] = {
    "lgpd": {
        "critical": ["Art. 6 (tratamento de dados)", "Art. 46 (seguranca)"],
        "high": ["Art. 50 (boas praticas)"],
    },
    "gdpr": {
        "critical": ["Art. 25 (data protection by design)", "Art. 35 (DPIA)"],
        "high": ["Art. 32 (security of processing)"],
    },
    "nist_ai_rmf": {
        "critical": ["MAP-1.1 (intended purpose)", "MEASURE-2.6 (bias)"],
        "high": ["MANAGE-2.2 (risk response)"],
    },
}


def _frontmatter(report_type: str, scope: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return f"---\nreport: {report_type}\ngenerated_at: {now}\nscope: {scope}\n---\n\n"


class ReportBuilder:
    """Namespace for generating Markdown reports from manifest documents."""

    def __init__(self, mi: ManifestInstance) -> None:
        self._mi = mi

    # ─── eval_summary ────────────────────────────────────────────────

    def eval_summary(self, suite: str | None = None) -> str:
        """Generate an eval summary report grouped by suite.

        If *suite* is given, only that suite is included.
        Shows latest run per suite with pass rate, aggregate_score, cost, tokens,
        and per-case table.
        """
        # two-planes F2.5: record → delega via query (caller off-loop, ver topo).
        runs = self._mi._all("EvalRun")
        if suite:
            runs = [r for r in runs if r.spec.get("suite") == suite]

        md = _frontmatter("eval_summary", self._mi.scope)
        md += "# Eval Summary\n\n"

        if not runs:
            md += "_No eval runs found._\n"
            return md

        # Group by suite, keep latest per suite (by saved_at or doc order)
        by_suite: dict[str, Any] = {}
        for run in runs:
            s = run.spec.get("suite", "unknown")
            existing = by_suite.get(s)
            if existing is None:
                by_suite[s] = run
            else:
                # Compare saved_at — later wins
                new_ts = run.spec.get("saved_at", "")
                old_ts = existing.spec.get("saved_at", "")
                if new_ts > old_ts:
                    by_suite[s] = run

        for suite_name, run in sorted(by_suite.items()):
            spec = run.spec
            total = spec.get("total", 0)
            passed = spec.get("passed", 0)
            rate = f"{(passed / total * 100):.1f}%" if total else "N/A"
            agg = spec.get("aggregate_score")
            agg_str = f"{agg:.2f}" if agg is not None else "N/A"
            cost = spec.get("total_cost_usd")
            cost_str = f"${cost:.4f}" if cost is not None else "N/A"
            tokens = spec.get("total_tokens")
            tokens_str = str(tokens) if tokens is not None else "N/A"

            md += f"## Suite: {suite_name}\n\n"
            md += f"- **Pass rate:** {rate}\n"
            md += f"- **Aggregate score:** {agg_str}\n"
            md += f"- **Cost:** {cost_str}\n"
            md += f"- **Tokens:** {tokens_str}\n\n"

            results = spec.get("results", [])
            if results:
                md += "| Case | Status | Score |\n"
                md += "|------|--------|-------|\n"
                for r in results:
                    case = r.get("case", "")
                    status = r.get("status", "")
                    score = r.get("score")
                    score_str = f"{score:.2f}" if score is not None else "-"
                    md += f"| {case} | {status} | {score_str} |\n"
                md += "\n"

        return md

    # ─── findings_summary ────────────────────────────────────────────

    def findings_summary(self, min_severity: str = "low") -> str:
        """Generate a findings summary grouped by severity.

        Filters out findings with severity below *min_severity*.
        """
        # two-planes F2.5: record → delega via query (caller off-loop, ver topo).
        findings = self._mi._all("Finding")
        min_level = _SEVERITY_ORDER.get(min_severity, 3)

        # Filter by min_severity
        filtered = [
            f for f in findings
            if _SEVERITY_ORDER.get(f.spec.get("severity", "low"), 3) <= min_level
        ]

        md = _frontmatter("findings_summary", self._mi.scope)
        md += "# Findings Summary\n\n"

        if not filtered:
            md += "_No findings found._\n"
            return md

        # Group by severity
        by_severity: dict[str, list] = {}
        for f in filtered:
            sev = f.spec.get("severity", "low")
            by_severity.setdefault(sev, []).append(f)

        # Output in severity order
        for sev in ["critical", "high", "medium", "low"]:
            group = by_severity.get(sev, [])
            if not group:
                continue
            md += f"## {sev.upper()} ({len(group)})\n\n"
            for f in group:
                spec = f.spec
                title = spec.get("title", f.name)
                status = spec.get("status", "open")
                recommendation = spec.get("recommendation", "")
                md += f"### {title}\n\n"
                md += f"- **Status:** {status}\n"
                if recommendation:
                    md += f"- **Recommendation:** {recommendation}\n"
                md += "\n"

        return md

    # ─── evidence_manifest ───────────────────────────────────────────

    def evidence_manifest(self) -> str:
        """Generate a manifest of all evidence documents."""
        # two-planes F2.5: Evidence é plane=record (verificado, extensão
        # evidence) → delega via query (caller off-loop, ver topo).
        evidence = self._mi._all("Evidence")

        md = _frontmatter("evidence_manifest", self._mi.scope)
        md += "# Evidence Manifest\n\n"

        if not evidence:
            md += "_No evidence documents found._\n"
            return md

        md += "| Event Type | Document Ref | SHA-256 | Captured At |\n"
        md += "|------------|-------------|---------|-------------|\n"
        for e in evidence:
            spec = e.spec
            event_type = spec.get("event_type", "")
            doc_ref = spec.get("document_ref", "")
            sha = spec.get("sha256", "")
            sha_short = sha[:12] + "..." if len(sha) > 12 else sha
            captured = spec.get("captured_at", "")
            md += f"| {event_type} | {doc_ref} | {sha_short} | {captured} |\n"

        md += "\n"
        return md

    # ─── compliance_matrix ───────────────────────────────────────────

    def compliance_matrix(self, framework: str) -> str:
        """Generate a compliance matrix mapping findings to regulatory articles.

        Supported frameworks: lgpd, gdpr, nist_ai_rmf.
        Unknown frameworks produce an empty matrix with a note.
        """
        md = _frontmatter("compliance_matrix", self._mi.scope)
        md += f"# Compliance Matrix: {framework.upper()}\n\n"

        mapping = _COMPLIANCE_MAPPINGS.get(framework)
        if not mapping:
            md += f"_Unknown framework: {framework}. Supported: {', '.join(sorted(_COMPLIANCE_MAPPINGS.keys()))}._\n"
            return md

        # two-planes F2.5: record → delega via query (caller off-loop, ver topo).
        findings = self._mi._all("Finding")

        md += "| Severity | Count | Regulatory Articles |\n"
        md += "|----------|-------|--------------------|\n"
        for sev in ["critical", "high", "medium", "low"]:
            articles = mapping.get(sev, [])
            count = sum(1 for f in findings if f.spec.get("severity") == sev)
            articles_str = ", ".join(articles) if articles else "-"
            md += f"| {sev.upper()} | {count} | {articles_str} |\n"

        md += "\n"

        if findings:
            md += "## Findings by Article\n\n"
            for sev in ["critical", "high"]:
                articles = mapping.get(sev, [])
                sev_findings = [f for f in findings if f.spec.get("severity") == sev]
                if sev_findings and articles:
                    for article in articles:
                        md += f"### {article}\n\n"
                        for f in sev_findings:
                            title = f.spec.get("title", f.name)
                            md += f"- {title}\n"
                        md += "\n"

        return md
