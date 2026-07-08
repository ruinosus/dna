/**
 * SafetyPolicyExtension — SafetyPolicy kind + SafetyPolicyReader + SafetyPolicyWriter.
 *
 * Declarative safety enforcement rules. Tier 1 (regex) is built-in;
 * heavier tiers (ml, api, llm_judge) are opt-in.
 *
 * 1:1 parity with Python dna.v3.extensions.safety.
 */

import yaml from "js-yaml";
import { nodeFS } from "../kernel/fs.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { KindBase } from "../kernel/kind_base.js";
import type { FSLike } from "../kernel/fs.js";
import { SafetyPolicySchema, SafetyPolicySpecSchema, zodSpecToJsonSchema } from "../kernel/models.js";
import type { ExtensionHost, Extension, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { SD } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";
import type { PreviewBlock } from "../kernel/preview.js";

// ---------------------------------------------------------------------------
// SafetyPolicyKind
// ---------------------------------------------------------------------------

class SafetyPolicyKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "SafetyPolicy";
  readonly alias = "helix-safety-policy";
  readonly isSchemaAffecting = true;
  readonly origin = "github.com/ruinosus/dna";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly descriptionFallbackField = "instruction";
  readonly storage = SD.bundle("safety", "SAFETYPOLICY.md", "list", "rules");
  readonly graphStyle = { fill: "#DC2626", stroke: "#B91C1C", textColor: "#fff" };
  readonly asciiIcon = "🔒";
  readonly displayLabel = "Safety Policies";
  readonly _sourceUrl = import.meta.url;
  readonly docs =
    "A SafetyPolicy declares runtime enforcement rules for PII masking, " +
    "content safety, topic restriction, prompt injection detection, and " +
    "custom regex patterns. Rules are tiered: regex (built-in), ml, api, " +
    "llm_judge. Stored as a bundle rooted on SAFETYPOLICY.md.";

  readonly uiSchema = {
    scope: {
      widget: "select",
      label: "Scope",
      help: "input guards the user prompt; output guards the agent response; both runs on each side.",
      options: ["input", "output", "both"],
      order: 1,
    },
    action: {
      widget: "select",
      label: "Action",
      help: "mask: redact PII inline; block: reject the message; log: pass through with violation metadata.",
      options: ["mask", "block", "log"],
      order: 2,
    },
    severity: {
      widget: "select",
      label: "Severity",
      help: "error fails the turn; warn lets the turn continue.",
      options: ["error", "warn"],
      order: 3,
    },
    rules: {
      widget: "code",
      language: "yaml",
      label: "Rules",
      help: "YAML list of safety rules (type, tier, entities, patterns, etc.)",
      height: 300,
      order: 4,
    },
  };

  depFilters() { return { recognizers: "presidio-recognizer" }; }
  schema() { return zodSpecToJsonSchema(SafetyPolicySpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    return SafetyPolicySchema.parse(raw);
  }

  describe(doc: Document): string | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return `SafetyPolicy: ${doc.name} (scope=${spec.scope}, action=${spec.action})`;
  }

  summary(doc: Document): Record<string, unknown> | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      scope: typeof spec.scope === "string" ? spec.scope : "both",
      action: typeof spec.action === "string" ? spec.action : "mask",
      severity: typeof spec.severity === "string" ? spec.severity : "error",
      rules: Array.isArray(spec.rules) ? spec.rules.length : 0,
    };
  }


  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const blocks: PreviewBlock[] = [];

    // Policy fields
    const meta: Array<{ label: string; value: string }> = [];
    if (typeof spec.scope === "string") meta.push({ label: "Scope", value: spec.scope });
    if (typeof spec.action === "string") meta.push({ label: "Action", value: spec.action });
    if (typeof spec.severity === "string") meta.push({ label: "Severity", value: spec.severity });
    if (meta.length > 0) {
      blocks.push({ kind: "fields", title: "Policy", fields: meta });
    }

    // Rules as YAML code block
    const rules = spec.rules;
    if (Array.isArray(rules) && rules.length > 0) {
      blocks.push({
        kind: "code",
        title: "Rules",
        body: yaml.dump(rules, { flowLevel: 3 }).trim(),
        language: "yaml",
      });
    }

    if (blocks.length === 0) {
      return [{ kind: "empty", title: "SafetyPolicy (empty)" }];
    }
    return blocks;
  }
}

// ---------------------------------------------------------------------------
// SafetyPolicyReader
// ---------------------------------------------------------------------------

function parseFrontmatter(text: string): [Record<string, unknown>, string] {
  const match = text.match(/^---\n([\s\S]*?)---\n?/);
  if (!match) return [{}, text];
  let fm: Record<string, unknown> = {};
  try {
    const parsed = yaml.load(match[1]);
    if (typeof parsed === "object" && parsed !== null) {
      fm = parsed as Record<string, unknown>;
    }
  } catch { /* ignore */ }
  const body = text.slice(match[0].length);
  return [fm, body];
}

export class SafetyPolicyReader implements ReaderPort {
  readonly _marker = "SAFETYPOLICY.md";

  constructor(private fs: FSLike = nodeFS) {}

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    return this.fs.exists(`${path}/SAFETYPOLICY.md`);
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const text = this.fs.readFile(`${path}/SAFETYPOLICY.md`);
    const [fm, body] = parseFrontmatter(text);

    const name = String(fm.name || "") || path.split("/").pop() || "";
    const description = String(fm.description || "");
    const scope = String(fm.scope || "both");
    const action = String(fm.action || "mask");
    const severity = String(fm.severity || "error");

    // Parse body as YAML list of rules
    let rules: unknown[] = [];
    const trimmedBody = body.trim();
    if (trimmedBody) {
      try {
        const parsed = yaml.load(trimmedBody);
        if (Array.isArray(parsed)) {
          rules = parsed;
        }
      } catch { /* ignore invalid YAML */ }
    }

    return {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "SafetyPolicy",
      metadata: { name, description },
      spec: { scope, action, severity, rules },
    };
  }
}

// ---------------------------------------------------------------------------
// SafetyPolicyWriter
// ---------------------------------------------------------------------------

export class SafetyPolicyWriter implements WriterPort {
  readonly _kind = "SafetyPolicy";

  constructor(private fs: FSLike = nodeFS) {}

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === "SafetyPolicy";
  }

  write(bundle: BundleHandle, raw: Record<string, unknown>): void { const path = bundle.path ?? "";
    this.fs.mkdir(path);
    for (const f of this.serialize(raw)) {
      this.fs.writeFile(`${path}/${f.relativePath}`, f.content ?? "");
    }
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const meta = (raw.metadata ?? {}) as Record<string, unknown>;
    const spec = (raw.spec ?? {}) as Record<string, unknown>;

    const fmParts: string[] = [];
    if (meta.name) fmParts.push(`name: ${meta.name}`);
    if (meta.description) fmParts.push(`description: ${meta.description}`);
    fmParts.push(`scope: ${spec.scope ?? "both"}`);
    fmParts.push(`action: ${spec.action ?? "mask"}`);
    fmParts.push(`severity: ${spec.severity ?? "error"}`);
    const frontmatter = fmParts.join("\n");

    // Serialize rules as YAML list
    const rules = (spec.rules as unknown[]) ?? [];
    let body = "";
    if (rules.length > 0) {
      body = yaml.dump(rules, { flowLevel: 3 }).trim();
    }

    const content = body
      ? `---\n${frontmatter}\n---\n\n${body}\n`
      : `---\n${frontmatter}\n---\n`;

    return [{ relativePath: "SAFETYPOLICY.md", content }];
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class SafetyPolicyExtension implements Extension {
  readonly name = "safety";
  readonly version = "1.0.0";

  constructor(private fs: FSLike = nodeFS) {}

  register(kernel: ExtensionHost): void {
    kernel.kind(new SafetyPolicyKind());
    kernel.reader(new SafetyPolicyReader(this.fs));
    kernel.writer(new SafetyPolicyWriter(this.fs));
  }
}
