/**
 * Tests for ReportBuilder — evalSummary, findingsSummary, evidenceManifest, complianceMatrix.
 *
 * 1:1 parity with Python tests/test_reports.py.
 */

import { describe, test, expect } from "bun:test";
import { Document } from "../src/kernel/document.js";
import { ManifestInstance } from "../src/kernel/instance.js";
import { ReportBuilder } from "../src/kernel/reports.js";

function makeMi(docs: Document[]): ManifestInstance {
  return new ManifestInstance({
    scope: "test-scope",
    documents: docs,
    kinds: new Map(),
  });
}

function evalRun(
  name: string,
  suite: string,
  passed: number,
  total: number,
  extra: Record<string, unknown> = {},
): Document {
  return new Document({
    apiVersion: "github.com/ruinosus/dna/eval/v1",
    kind: "EvalRun",
    name,
    spec: { suite, passed, total, failed: total - passed, ...extra },
  });
}

function finding(
  name: string,
  severity: string,
  title: string,
  extra: Record<string, unknown> = {},
): Document {
  return new Document({
    apiVersion: "github.com/ruinosus/dna/eval/v1",
    kind: "Finding",
    name,
    spec: { title, severity, source: "eval", status: "open", ...extra },
  });
}

function evidence(
  name: string,
  eventType: string,
  docRef: string,
  sha256: string,
  capturedAt: string,
): Document {
  return new Document({
    apiVersion: "github.com/ruinosus/dna/evidence/v1",
    kind: "Evidence",
    name,
    spec: {
      event_type: eventType,
      document_ref: docRef,
      sha256,
      captured_at: capturedAt,
    },
  });
}

// ─── evalSummary ────────────────────────────────────────────────────

describe("evalSummary", () => {
  test("empty", async () => {
    const mi = makeMi([]);
    const report = mi.reports.evalSummary();
    expect(report).toContain("No eval runs found");
    expect(report).toContain("report: eval_summary");
  });

  test("with runs", async () => {
    const docs = [
      evalRun("run-1", "screening-reads", 8, 10, {
        aggregate_score: 0.85,
        total_cost_usd: 0.12,
        total_tokens: 5000,
        saved_at: "2026-04-13T10:00:00Z",
        results: [
          { case: "case-1", status: "passed", score: 0.9 },
          { case: "case-2", status: "failed", score: 0.3 },
        ],
      }),
    ];
    const mi = makeMi(docs);
    const report = mi.reports.evalSummary();
    expect(report).toContain("screening-reads");
    expect(report).toContain("80.0%");
    expect(report).toContain("0.85");
    expect(report).toContain("$0.1200");
    expect(report).toContain("5000");
    expect(report).toContain("case-1");
    expect(report).toContain("case-2");
  });

  test("filter by suite", async () => {
    const docs = [
      evalRun("run-1", "reads", 8, 10, { saved_at: "2026-04-13T10:00:00Z" }),
      evalRun("run-2", "writes", 5, 10, { saved_at: "2026-04-13T10:00:00Z" }),
    ];
    const mi = makeMi(docs);
    const report = mi.reports.evalSummary("reads");
    expect(report).toContain("reads");
    expect(report).not.toContain("writes");
  });

  test("latest run per suite", async () => {
    const docs = [
      evalRun("old-run", "reads", 5, 10, { saved_at: "2026-04-12T08:00:00Z" }),
      evalRun("new-run", "reads", 9, 10, { saved_at: "2026-04-13T10:00:00Z" }),
    ];
    const mi = makeMi(docs);
    const report = mi.reports.evalSummary();
    expect(report).toContain("90.0%");
    expect(report).not.toContain("50.0%");
  });

  test("frontmatter", async () => {
    const mi = makeMi([]);
    const report = mi.reports.evalSummary();
    expect(report.startsWith("---\n")).toBe(true);
    expect(report).toContain("report: eval_summary");
    expect(report).toContain("scope: test-scope");
  });
});

// ─── findingsSummary ────────────────────────────────────────────────

describe("findingsSummary", () => {
  test("empty", async () => {
    const mi = makeMi([]);
    const report = mi.reports.findingsSummary();
    expect(report).toContain("No findings found");
    expect(report).toContain("report: findings_summary");
  });

  test("grouped by severity", async () => {
    const docs = [
      finding("f-1", "critical", "PII Leak in response"),
      finding("f-2", "high", "Slow response time"),
      finding("f-3", "low", "Minor formatting issue"),
    ];
    const mi = makeMi(docs);
    const report = mi.reports.findingsSummary();
    expect(report).toContain("CRITICAL (1)");
    expect(report).toContain("HIGH (1)");
    expect(report).toContain("LOW (1)");
    expect(report).toContain("PII Leak in response");
  });

  test("min severity filter", async () => {
    const docs = [
      finding("f-1", "critical", "Critical issue"),
      finding("f-2", "high", "High issue"),
      finding("f-3", "low", "Low issue"),
    ];
    const mi = makeMi(docs);
    const report = mi.reports.findingsSummary("high");
    expect(report).toContain("CRITICAL");
    expect(report).toContain("HIGH");
    expect(report).not.toContain("LOW");
  });

  test("recommendation shown", async () => {
    const docs = [
      finding("f-1", "high", "Issue", { recommendation: "Fix the thing" }),
    ];
    const mi = makeMi(docs);
    const report = mi.reports.findingsSummary();
    expect(report).toContain("Fix the thing");
  });

  test("status shown", async () => {
    const docs = [finding("f-1", "high", "Issue", { status: "mitigated" })];
    const mi = makeMi(docs);
    const report = mi.reports.findingsSummary();
    expect(report).toContain("mitigated");
  });
});

// ─── evidenceManifest ───────────────────────────────────────────────

describe("evidenceManifest", () => {
  test("empty", async () => {
    const mi = makeMi([]);
    const report = mi.reports.evidenceManifest();
    expect(report).toContain("No evidence documents found");
    expect(report).toContain("report: evidence_manifest");
  });

  test("with docs", async () => {
    const docs = [
      evidence(
        "ev-1",
        "eval_run_completed",
        "evalrun/run-1",
        "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "2026-04-13T10:00:00Z",
      ),
    ];
    const mi = makeMi(docs);
    const report = mi.reports.evidenceManifest();
    expect(report).toContain("eval_run_completed");
    expect(report).toContain("evalrun/run-1");
    expect(report).toContain("abcdef123456...");
    expect(report).toContain("2026-04-13T10:00:00Z");
  });

  test("table header", async () => {
    const docs = [evidence("ev-1", "custom", "ref", "abc", "2026-01-01T00:00:00Z")];
    const mi = makeMi(docs);
    const report = mi.reports.evidenceManifest();
    expect(report).toContain("| Event Type |");
    expect(report).toContain("| Document Ref |");
  });
});

// ─── complianceMatrix ───────────────────────────────────────────────

describe("complianceMatrix", () => {
  test("lgpd", async () => {
    const docs = [
      finding("f-1", "critical", "PII exposure"),
      finding("f-2", "high", "Missing encryption"),
    ];
    const mi = makeMi(docs);
    const report = mi.reports.complianceMatrix("lgpd");
    expect(report).toContain("LGPD");
    expect(report).toContain("Art. 6 (tratamento de dados)");
    expect(report).toContain("Art. 46 (seguranca)");
    expect(report).toContain("Art. 50 (boas praticas)");
    expect(report).toContain("CRITICAL | 1");
    expect(report).toContain("HIGH | 1");
  });

  test("gdpr", async () => {
    const mi = makeMi([finding("f-1", "critical", "Issue")]);
    const report = mi.reports.complianceMatrix("gdpr");
    expect(report).toContain("GDPR");
    expect(report).toContain("Art. 25 (data protection by design)");
  });

  test("nist", async () => {
    const mi = makeMi([]);
    const report = mi.reports.complianceMatrix("nist_ai_rmf");
    expect(report).toContain("NIST_AI_RMF");
    expect(report).toContain("MAP-1.1 (intended purpose)");
  });

  test("unknown framework", async () => {
    const mi = makeMi([]);
    const report = mi.reports.complianceMatrix("unknown_fw");
    expect(report).toContain("Unknown framework: unknown_fw");
    expect(report).toContain("lgpd");
  });

  test("findings by article", async () => {
    const docs = [
      finding("f-1", "critical", "Data breach"),
      finding("f-2", "critical", "Auth bypass"),
    ];
    const mi = makeMi(docs);
    const report = mi.reports.complianceMatrix("lgpd");
    expect(report).toContain("Findings by Article");
    expect(report).toContain("Data breach");
    expect(report).toContain("Auth bypass");
  });
});

// ─── mi.reports lazy property ───────────────────────────────────────

describe("reports namespace", () => {
  test("returns ReportBuilder", async () => {
    const mi = makeMi([]);
    expect(mi.reports).toBeInstanceOf(ReportBuilder);
  });

  test("same instance on repeated access", async () => {
    const mi = makeMi([]);
    const r1 = mi.reports;
    const r2 = mi.reports;
    expect(r1).toBe(r2);
  });
});
