/**
 * ResearchExtension — curated research syntheses with evidence ratings (TS twin).
 *
 * 1:1 parity with python/dna/extensions/research/__init__.py.
 *
 * Storage layout per doc:
 *
 *   .dna/<scope>/research/<name>/
 *       RESEARCH.md            ← marker (frontmatter = spec)
 *
 * A Research synthesizes N Reference docs with objective, methodology,
 * evidence-rated findings, and priority recommendations — agent-facing
 * knowledge WITH provenance (the declarative counter to LLM-generated
 * repo-wiki prose).
 *
 * Tenancy: PERMISSIVE — no `scope` attribute declared, so the write
 * pipeline treats it as permissive (base writes with or without a
 * tenant). Research is repo-authored knowledge, not per-client data.
 *
 * The Reference companion Kind is provided by the sdlc extension
 * (alias sdlc-reference); it is NOT registered here.
 */

import yaml from "js-yaml";

import type { ExtensionHost, Extension, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD } from "../kernel/protocols.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { writeEntriesToHandle } from "../kernel/writer-helpers.js";

const API_VERSION = "github.com/ruinosus/dna/research/v1";

export const METHODOLOGIES = [
  "web-search-curated",
  "literature-review",
  "interview",
  "field-study",
  "experiment",
  "synthesis",
  "other",
] as const;

export const EVIDENCE_RATINGS = ["evidence-based", "opinion-practice", "anecdotal"] as const;

export const STATUSES = ["brief", "ready", "draft", "published", "superseded", "retracted"] as const;

export const VISIBILITY = ["scope-private", "shared"] as const;


function parseFrontmatter(text: string): { fm: Record<string, unknown>; body: string } {
  const m = text.match(/^---\n([\s\S]*?)---\n?([\s\S]*)$/);
  if (!m) return { fm: {}, body: text };
  try {
    const parsed = yaml.load(m[1]!) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { fm: parsed as Record<string, unknown>, body: (m[2] ?? "").replace(/^\n+/, "") };
    }
  } catch {
    // fall through
  }
  return { fm: {}, body: text };
}


// ---------------------------------------------------------------------------
// Research Kind
// ---------------------------------------------------------------------------

class ResearchKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "Research";
  // alias generated as <owner>-<kebab(kind)> = "research-research" (owner =
  // extension name). New Kinds must not TYPE an explicit alias (guard:
  // tests/alias-generation.test.ts, EXPLICIT_ALIAS_ALLOWLIST). Empty here
  // keeps the KindPort shape while triggering generation at register time.
  readonly alias = "";
  readonly aliasOwner = "research";
  readonly origin = "github.com/ruinosus/dna/research";
  // PERMISSIVE tenancy — NO `scope` declared (base writes with or without tenant).
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.bundle("research", "RESEARCH.md");
  readonly graphStyle = { fill: "#7C3AED", stroke: "#5B21B6", textColor: "#fff" };
  readonly asciiIcon = "🔬";
  readonly displayLabel = "Research";
  readonly docs =
    "A Research is a curated synthesis of N external sources " +
    "(Reference docs) with objective, methodology, evidence-rated " +
    "findings, and priority recommendations. Designed for " +
    "auditability + agent consumption.";

  dependencies() { return null; }

  schema() {
    return {
      type: "object",
      required: ["title", "objective", "methodology", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string" },
        objective: { type: "string" },
        executive_summary: { type: "string" },
        key_takeaways: { type: "array", items: { type: "string" }, default: [] },
        overall_confidence: { type: "string", enum: ["high", "moderate", "low", "very-low"] },
        last_reviewed_at: { type: "string", format: "date-time" },
        next_review_due: { type: "string", format: "date-time" },
        methodology: { type: "string", enum: [...METHODOLOGIES], default: "web-search-curated" },
        conducted_by: { type: "string" },
        conducted_at: { type: "string", format: "date-time" },
        scope_ref: { type: "string" },
        visibility: { type: "string", enum: [...VISIBILITY], default: "scope-private" },
        sources: {
          type: "array",
          items: { type: "string" },
          default: [],
        },
        findings: {
          type: "array",
          items: {
            type: "object",
            required: ["id", "title", "evidence_rating"],
            additionalProperties: true,
            properties: {
              id: { type: "string", pattern: "^f-[a-z0-9-]+$" },
              title: { type: "string" },
              summary: { type: "string" },
              evidence_rating: { type: "string", enum: [...EVIDENCE_RATINGS] },
              source_refs: { type: "array", items: { type: "string" }, default: [] },
              tags: { type: "array", items: { type: "string" }, default: [] },
            },
          },
          default: [],
        },
        recommendations: {
          type: "array",
          items: {
            type: "object",
            required: ["id", "priority", "summary"],
            additionalProperties: true,
            properties: {
              id: { type: "string", pattern: "^rec-[a-z0-9-]+$" },
              priority: { type: "string", enum: ["high", "medium", "low"] },
              summary: { type: "string" },
              effort_hours: { type: "number" },
              clinical_decision: { type: "boolean", default: false },
              depends_on: { type: "array", items: { type: "string" }, default: [] },
              backed_by_findings: { type: "array", items: { type: "string" }, default: [] },
              status: {
                type: "string",
                enum: ["proposed", "accepted", "rejected", "implemented", "blocked"],
                default: "proposed",
              },
            },
          },
          default: [],
        },
        status: { type: "string", enum: [...STATUSES], default: "draft" },
        superseded_by: { type: "string" },
        retracted_reason: { type: "string" },
        audience_context: { type: "string" },
        research_blocks: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: true,
            properties: {
              title: { type: "string" },
              questions: { type: "array", items: { type: "string" } },
            },
          },
          default: [],
        },
        output_constraints: { type: "array", items: { type: "string" }, default: [] },
        reference_baselines: { type: "array", items: { type: "string" }, default: [] },
        brief_notes: { type: "string" },
        tags: { type: "array", items: { type: "string" }, default: [] },
        owner: { type: "string" },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
    };
  }


  parse(raw: Record<string, unknown>): Record<string, unknown> {
    return raw;
  }

  describe(doc: { spec?: Record<string, unknown> }): string | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const title = (spec["title"] as string) ?? "?";
    const status = (spec["status"] as string) ?? "draft";
    return `${title} [${status}]`;
  }

  summary(doc: { spec?: Record<string, unknown> }): Record<string, unknown> {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const findings = (spec["findings"] as { evidence_rating?: string }[]) ?? [];
    const recs = (spec["recommendations"] as unknown[]) ?? [];
    const evFindings = findings.filter((f) => f.evidence_rating === "evidence-based").length;
    return {
      title: spec["title"] ?? "",
      methodology: spec["methodology"] ?? "",
      status: spec["status"] ?? "draft",
      sources_count: ((spec["sources"] as unknown[]) ?? []).length,
      findings_count: findings.length,
      evidence_based_count: evFindings,
      recommendations_count: recs.length,
    };
  }

  promptTemplate(): string | null { return null; }
}


// ---------------------------------------------------------------------------
// Reader / Writer
// ---------------------------------------------------------------------------

class ResearchReader implements ReaderPort {
  async detect(bundle: BundleHandle): Promise<boolean> {
    return bundle.exists("RESEARCH.md");
  }

  async read(bundle: BundleHandle): Promise<Record<string, unknown>> {
    const text = await bundle.readText("RESEARCH.md");
    const { fm } = parseFrontmatter(text);
    if (
      fm &&
      typeof fm === "object" &&
      "spec" in fm &&
      fm["spec"] &&
      typeof fm["spec"] === "object"
    ) {
      const metadata = (fm["metadata"] as Record<string, unknown>) ?? {};
      if (!metadata["name"]) metadata["name"] = bundle.name;
      return {
        apiVersion: fm["apiVersion"] ?? API_VERSION,
        kind: fm["kind"] ?? "Research",
        metadata,
        spec: fm["spec"],
      };
    }
    return {
      apiVersion: API_VERSION,
      kind: "Research",
      metadata: { name: bundle.name },
      spec: fm,
    };
  }
}


class ResearchWriter implements WriterPort {
  canWrite(raw: Record<string, unknown>): boolean {
    return raw["kind"] === "Research";
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const spec = (raw["spec"] as Record<string, unknown>) ?? {};
    const meta = (raw["metadata"] as Record<string, unknown>) ?? {};

    const cleanSpec: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(spec)) {
      if (v === null || v === undefined || v === "") continue;
      if (Array.isArray(v) && v.length === 0) continue;
      if (typeof v === "object" && !Array.isArray(v) && Object.keys(v as object).length === 0) continue;
      cleanSpec[k] = v;
    }
    const cleanMeta: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(meta)) {
      if (v !== null && v !== undefined) cleanMeta[k] = v;
    }

    const envelope = {
      apiVersion: raw["apiVersion"] ?? API_VERSION,
      kind: raw["kind"] ?? "Research",
      metadata: cleanMeta,
      spec: cleanSpec,
    };
    const fmYaml = yaml.dump(envelope, {
      sortKeys: false,
      lineWidth: 100,
      noRefs: true,
      noCompatMode: true,
    }).replace(/\n+$/, "");
    const title = (cleanSpec["title"] as string) ?? "?";
    const method = (cleanSpec["methodology"] as string) ?? "synthesis";
    const nFindings = ((cleanSpec["findings"] as unknown[]) ?? []).length;
    const nSources = ((cleanSpec["sources"] as unknown[]) ?? []).length;
    const body =
      `# Research — ${title}\n\n` +
      `Methodology: ${method} · ${nSources} sources · ${nFindings} findings.\n\n` +
      `This file's spec (frontmatter above) is the authoritative ` +
      `data. The prose below is for human reading and is regenerated ` +
      `on each write.\n`;
    return [
      { relativePath: "RESEARCH.md", content: `---\n${fmYaml}\n---\n\n${body}` },
    ];
  }

  async write(bundle: BundleHandle, raw: Record<string, unknown>): Promise<void> {
    await writeEntriesToHandle(bundle, this.serialize(raw));
  }
}


// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class ResearchExtension implements Extension {
  name = "research";
  version = "1.2.0";
  register(kernel: ExtensionHost) {
    kernel.kind(new ResearchKind());
    // Reference companion is provided by the sdlc extension — not here.
    kernel.reader(new ResearchReader());
    kernel.writer(new ResearchWriter());
  }
}
