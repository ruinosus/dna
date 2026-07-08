"""Kernel-driven reports + lock — replaces mi.reports / mi.generate_lock.

Story s-reports-and-lock-lazy (Feature f-mi-class-extinction).

Free functions taking ``(kernel, scope, ...)`` that compute report
text + Lockfile snapshot via bounded ``kernel.query`` per Kind. No
MI shell materialized.

Reports surfaced:
  - eval_summary(scope, suite=None)
  - findings_summary(scope, min_severity="low")
  - evidence_manifest(scope)
  - compliance_matrix(scope, framework)
  - generate_lock(scope)

Each report queries ONE specific Kind (EvalRun, Finding, Evidence) —
big perf win vs the legacy ``self._mi.all("X")`` walk that traversed
the full mi.documents list.

Parity contract: produces byte-identical output to the legacy
ReportBuilder / LockManager methods for the same scope.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from dna.kernel.lock import LockEntry, Lockfile


_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# Compliance frameworks — copied from legacy ReportBuilder._COMPLIANCE_MAPPINGS
# verbatim to preserve byte-parity with existing report consumers.
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
    """Generate report frontmatter — matches legacy ReportBuilder shape."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return f"---\nreport: {report_type}\ngenerated_at: {now}\nscope: {scope}\n---\n\n"


async def eval_summary_async(
    kernel: Any, scope: str, *, suite: str | None = None,
    tenant: str | None = None,
) -> str:
    """Generate eval summary grouped by suite. Same shape as
    ReportBuilder.eval_summary."""
    runs = []
    async for raw in kernel.query(scope, "EvalRun", tenant=tenant):
        spec = raw.get("spec") or {}
        if suite and spec.get("suite") != suite:
            continue
        runs.append(raw)

    md = _frontmatter("eval_summary", scope)
    md += "# Eval Summary\n\n"
    if not runs:
        md += "_No eval runs found._\n"
        return md

    by_suite: dict[str, Any] = {}
    for run in runs:
        spec = run.get("spec") or {}
        s = spec.get("suite", "unknown")
        existing = by_suite.get(s)
        if existing is None:
            by_suite[s] = run
        else:
            new_ts = spec.get("saved_at", "")
            old_ts = (existing.get("spec") or {}).get("saved_at", "")
            if new_ts > old_ts:
                by_suite[s] = run

    for suite_name, run in sorted(by_suite.items()):
        spec = run.get("spec") or {}
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


async def findings_summary_async(
    kernel: Any, scope: str, *, min_severity: str = "low",
    tenant: str | None = None,
) -> str:
    """Findings grouped by severity. Filters below min_severity."""
    min_level = _SEVERITY_ORDER.get(min_severity, 3)
    filtered: list[dict] = []
    async for raw in kernel.query(scope, "Finding", tenant=tenant):
        spec = raw.get("spec") or {}
        if _SEVERITY_ORDER.get(spec.get("severity", "low"), 3) <= min_level:
            filtered.append(raw)

    md = _frontmatter("findings_summary", scope)
    md += "# Findings Summary\n\n"
    if not filtered:
        md += "_No findings found._\n"
        return md

    by_sev: dict[str, list[dict]] = {}
    for f in filtered:
        spec = f.get("spec") or {}
        sev = spec.get("severity", "low")
        by_sev.setdefault(sev, []).append(f)

    for sev in ["critical", "high", "medium", "low"]:
        group = by_sev.get(sev, [])
        if not group:
            continue
        md += f"## {sev.upper()} ({len(group)})\n\n"
        for f in group:
            spec = f.get("spec") or {}
            meta = f.get("metadata") or {}
            title = spec.get("title", meta.get("name", ""))
            status = spec.get("status", "open")
            rec = spec.get("recommendation", "")
            md += f"### {title}\n\n"
            md += f"- **Status:** {status}\n"
            if rec:
                md += f"- **Recommendation:** {rec}\n"
            md += "\n"
    return md


async def evidence_manifest_async(
    kernel: Any, scope: str, *, tenant: str | None = None,
) -> str:
    """Evidence Kind manifest."""
    evidence: list[dict] = []
    async for raw in kernel.query(scope, "Evidence", tenant=tenant):
        evidence.append(raw)

    md = _frontmatter("evidence_manifest", scope)
    md += "# Evidence Manifest\n\n"
    if not evidence:
        md += "_No evidence documents found._\n"
        return md

    md += "| Event Type | Document Ref | SHA-256 | Captured At |\n"
    md += "|------------|-------------|---------|-------------|\n"
    for e in evidence:
        spec = e.get("spec") or {}
        event_type = spec.get("event_type", "")
        doc_ref = spec.get("document_ref", "")
        sha = spec.get("sha256", "")
        sha_short = sha[:12] + "..." if len(sha) > 12 else sha
        captured = spec.get("captured_at", "")
        md += f"| {event_type} | {doc_ref} | {sha_short} | {captured} |\n"
    md += "\n"
    return md


async def compliance_matrix_async(
    kernel: Any, scope: str, framework: str, *,
    tenant: str | None = None,
) -> str:
    """Findings → regulatory articles matrix."""
    md = _frontmatter("compliance_matrix", scope)
    md += f"# Compliance Matrix: {framework.upper()}\n\n"

    mapping = _COMPLIANCE_MAPPINGS.get(framework)
    if not mapping:
        md += (
            f"_Unknown framework: {framework}. Supported: "
            f"{', '.join(sorted(_COMPLIANCE_MAPPINGS.keys()))}._\n"
        )
        return md

    findings: list[dict] = []
    async for raw in kernel.query(scope, "Finding", tenant=tenant):
        findings.append(raw)

    md += "| Severity | Count | Regulatory Articles |\n"
    md += "|----------|-------|--------------------|\n"
    for sev in ["critical", "high", "medium", "low"]:
        articles = mapping.get(sev, [])
        count = sum(1 for f in findings if (f.get("spec") or {}).get("severity") == sev)
        articles_str = ", ".join(articles) if articles else "-"
        md += f"| {sev.upper()} | {count} | {articles_str} |\n"
    md += "\n"

    if findings:
        md += "## Findings by Article\n\n"
        for sev in ["critical", "high"]:
            articles = mapping.get(sev, [])
            sev_findings = [f for f in findings if (f.get("spec") or {}).get("severity") == sev]
            if sev_findings and articles:
                for article in articles:
                    md += f"### {article}\n\n"
                    for f in sev_findings:
                        spec = f.get("spec") or {}
                        meta = f.get("metadata") or {}
                        title = spec.get("title", meta.get("name", ""))
                        md += f"- {title}\n"
                    md += "\n"
    return md


async def generate_lock_async(
    kernel: Any, scope: str, *, tenant: str | None = None,
) -> Lockfile:
    """Lockfile snapshot of every doc in scope, sorted by (kind, name).

    Replaces ``LockManager.generate`` which walks ``self._host.documents``.
    We iterate every Kind registered on the kernel + every reader-detected
    kind in list_documents (covers bundle-override kinds).
    """
    # Collect ALL docs across all kinds present in scope.
    all_kinds_in_scope: set[str] = set()
    refs = await kernel.list_documents(scope, kind=None, tenant=tenant)
    for k, _n in refs:
        all_kinds_in_scope.add(k)
    # Plus all registered kinds (in case some have docs the L1 doesn't
    # surface due to bundle overrides — covered by kernel.query slow path).
    for kp in kernel._kinds.values():
        all_kinds_in_scope.add(kp.kind)

    entries: list[LockEntry] = []
    for kind in sorted(all_kinds_in_scope):
        async for raw in kernel.query(scope, kind, tenant=tenant):
            doc = kernel._parse_doc(raw, origin="local")
            if doc is None:
                continue
            raw_json = json.dumps(doc.raw, sort_keys=True, ensure_ascii=False)
            sha = hashlib.sha256(raw_json.encode()).hexdigest()
            entries.append(LockEntry(
                name=doc.name, kind=doc.kind, api_version=doc.api_version,
                origin=getattr(doc, "origin", "local"),
                path="",
                sha256=sha,
            ))
    return Lockfile(scope=scope, documents=entries)


__all__ = [
    "eval_summary_async",
    "findings_summary_async",
    "evidence_manifest_async",
    "compliance_matrix_async",
    "generate_lock_async",
]
