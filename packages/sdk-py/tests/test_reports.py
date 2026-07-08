"""Tests for ReportBuilder — eval_summary, findings_summary, evidence_manifest, compliance_matrix."""
from dna.kernel.document import Document
from dna.kernel.instance import ManifestInstance
from dna.kernel.reports import ReportBuilder


def _make_mi(docs: list[Document]) -> ManifestInstance:
    """Create a minimal ManifestInstance with the given documents."""
    return ManifestInstance(
        scope="test-scope",
        documents=docs,
        kinds={},
    )


def _eval_run(name: str, suite: str, passed: int, total: int, **extra) -> Document:
    spec = {"suite": suite, "passed": passed, "total": total, "failed": total - passed}
    spec.update(extra)
    return Document(
        api_version="github.com/ruinosus/dna/eval/v1",
        kind="EvalRun",
        name=name,
        spec=spec,
    )


def _finding(name: str, severity: str, title: str, **extra) -> Document:
    spec = {"title": title, "severity": severity, "source": "eval", "status": "open"}
    spec.update(extra)
    return Document(
        api_version="github.com/ruinosus/dna/eval/v1",
        kind="Finding",
        name=name,
        spec=spec,
    )


def _evidence(name: str, event_type: str, doc_ref: str, sha256: str, captured_at: str) -> Document:
    return Document(
        api_version="github.com/ruinosus/dna/evidence/v1",
        kind="Evidence",
        name=name,
        spec={
            "event_type": event_type,
            "document_ref": doc_ref,
            "sha256": sha256,
            "captured_at": captured_at,
        },
    )


# ─── eval_summary ────────────────────────────────────────────────────

class TestEvalSummary:
    def test_empty(self):
        mi = _make_mi([])
        report = mi.reports.eval_summary()
        assert "No eval runs found" in report
        assert "report: eval_summary" in report

    def test_with_runs(self):
        docs = [
            _eval_run("run-1", "screening-reads", 8, 10,
                      aggregate_score=0.85, total_cost_usd=0.12, total_tokens=5000,
                      saved_at="2026-04-13T10:00:00Z",
                      results=[
                          {"case": "case-1", "status": "passed", "score": 0.9},
                          {"case": "case-2", "status": "failed", "score": 0.3},
                      ]),
        ]
        mi = _make_mi(docs)
        report = mi.reports.eval_summary()
        assert "screening-reads" in report
        assert "80.0%" in report
        assert "0.85" in report
        assert "$0.1200" in report
        assert "5000" in report
        assert "case-1" in report
        assert "case-2" in report

    def test_filter_by_suite(self):
        docs = [
            _eval_run("run-1", "reads", 8, 10, saved_at="2026-04-13T10:00:00Z"),
            _eval_run("run-2", "writes", 5, 10, saved_at="2026-04-13T10:00:00Z"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.eval_summary(suite="reads")
        assert "reads" in report
        assert "writes" not in report

    def test_latest_run_per_suite(self):
        """When multiple runs exist for the same suite, only the latest is shown."""
        docs = [
            _eval_run("old-run", "reads", 5, 10, saved_at="2026-04-12T08:00:00Z"),
            _eval_run("new-run", "reads", 9, 10, saved_at="2026-04-13T10:00:00Z"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.eval_summary()
        # Only one "Suite: reads" section, with 90% pass rate from the newer run
        assert "90.0%" in report
        assert "50.0%" not in report

    def test_frontmatter(self):
        mi = _make_mi([])
        report = mi.reports.eval_summary()
        assert report.startswith("---\n")
        assert "report: eval_summary" in report
        assert "scope: test-scope" in report


# ─── findings_summary ────────────────────────────────────────────────

class TestFindingsSummary:
    def test_empty(self):
        mi = _make_mi([])
        report = mi.reports.findings_summary()
        assert "No findings found" in report
        assert "report: findings_summary" in report

    def test_grouped_by_severity(self):
        docs = [
            _finding("f-1", "critical", "PII Leak in response"),
            _finding("f-2", "high", "Slow response time"),
            _finding("f-3", "low", "Minor formatting issue"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.findings_summary()
        assert "CRITICAL (1)" in report
        assert "HIGH (1)" in report
        assert "LOW (1)" in report
        assert "PII Leak in response" in report

    def test_min_severity_filter(self):
        docs = [
            _finding("f-1", "critical", "Critical issue"),
            _finding("f-2", "high", "High issue"),
            _finding("f-3", "low", "Low issue"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.findings_summary(min_severity="high")
        assert "CRITICAL" in report
        assert "HIGH" in report
        assert "LOW" not in report

    def test_recommendation_shown(self):
        docs = [
            _finding("f-1", "high", "Issue", recommendation="Fix the thing"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.findings_summary()
        assert "Fix the thing" in report

    def test_status_shown(self):
        docs = [
            _finding("f-1", "high", "Issue", status="mitigated"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.findings_summary()
        assert "mitigated" in report


# ─── evidence_manifest ───────────────────────────────────────────────

class TestEvidenceManifest:
    def test_empty(self):
        mi = _make_mi([])
        report = mi.reports.evidence_manifest()
        assert "No evidence documents found" in report
        assert "report: evidence_manifest" in report

    def test_with_docs(self):
        docs = [
            _evidence("ev-1", "eval_run_completed", "evalrun/run-1",
                      "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                      "2026-04-13T10:00:00Z"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.evidence_manifest()
        assert "eval_run_completed" in report
        assert "evalrun/run-1" in report
        assert "abcdef123456..." in report  # truncated SHA
        assert "2026-04-13T10:00:00Z" in report

    def test_table_header(self):
        docs = [
            _evidence("ev-1", "custom", "ref", "abc", "2026-01-01T00:00:00Z"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.evidence_manifest()
        assert "| Event Type |" in report
        assert "| Document Ref |" in report


# ─── compliance_matrix ───────────────────────────────────────────────

class TestComplianceMatrix:
    def test_lgpd(self):
        docs = [
            _finding("f-1", "critical", "PII exposure"),
            _finding("f-2", "high", "Missing encryption"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.compliance_matrix("lgpd")
        assert "LGPD" in report
        assert "Art. 6 (tratamento de dados)" in report
        assert "Art. 46 (seguranca)" in report
        assert "Art. 50 (boas praticas)" in report
        assert "CRITICAL | 1" in report
        assert "HIGH | 1" in report

    def test_gdpr(self):
        mi = _make_mi([_finding("f-1", "critical", "Issue")])
        report = mi.reports.compliance_matrix("gdpr")
        assert "GDPR" in report
        assert "Art. 25 (data protection by design)" in report

    def test_nist(self):
        mi = _make_mi([])
        report = mi.reports.compliance_matrix("nist_ai_rmf")
        assert "NIST_AI_RMF" in report
        assert "MAP-1.1 (intended purpose)" in report

    def test_unknown_framework(self):
        mi = _make_mi([])
        report = mi.reports.compliance_matrix("unknown_fw")
        assert "Unknown framework: unknown_fw" in report
        assert "lgpd" in report  # mentions supported frameworks

    def test_findings_by_article(self):
        docs = [
            _finding("f-1", "critical", "Data breach"),
            _finding("f-2", "critical", "Auth bypass"),
        ]
        mi = _make_mi(docs)
        report = mi.reports.compliance_matrix("lgpd")
        assert "Findings by Article" in report
        assert "Data breach" in report
        assert "Auth bypass" in report


# ─── mi.reports lazy property ────────────────────────────────────────

class TestReportsNamespace:
    def test_lazy_init(self):
        mi = _make_mi([])
        assert mi._report_builder is None
        _ = mi.reports
        assert mi._report_builder is not None

    def test_same_instance(self):
        mi = _make_mi([])
        r1 = mi.reports
        r2 = mi.reports
        assert r1 is r2

    def test_is_report_builder(self):
        mi = _make_mi([])
        assert isinstance(mi.reports, ReportBuilder)
