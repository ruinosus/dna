/**
 * GuardrailExtension — Guardrail kind + GuardrailReader + GuardrailWriter.
 *
 * 1:1 parity with Python dna.v3.extensions.guardrails.
 */

import yaml from "js-yaml";
import { nodeFS } from "../kernel/fs.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { KindBase } from "../kernel/kind_base.js";
import type { FSLike } from "../kernel/fs.js";
import { GuardrailSchema, GuardrailSpecSchema, zodSpecToJsonSchema } from "../kernel/models.js";
import type { ExtensionHost, Extension, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { SD } from "../kernel/protocols.js";

// ---------------------------------------------------------------------------
// GuardrailKind
// ---------------------------------------------------------------------------

class GuardrailKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "Guardrail";
  readonly alias = "guardrails-guardrail";
  readonly isSchemaAffecting = true;
  readonly origin = "github.com/ruinosus/dna/guardrails";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly descriptionFallbackField = "instruction";
  // Validate on read/compose, not only on write (i-validation-shallow) — parity
  // with Python GuardrailKind.validate_on_parse. parse() below already throws on
  // a bad severity/scope via GuardrailSchema (z.enum); this declares the intent.
  readonly validateOnParse = true;
  readonly storage = SD.bundle("guardrails", "GUARDRAIL.md", "list", "rules");
  readonly graphStyle = { fill: "#EF4444", stroke: "#DC2626", textColor: "#fff" };
  readonly asciiIcon = "🛡️";
  readonly displayLabel = "Guardrails";
  readonly _sourceUrl = import.meta.url;
  readonly docs =
    "A Guardrail declares a hard safety, compliance, or policy rule " +
    "enforced on every agent turn. Stored as a bundle rooted on " +
    "GUARDRAIL.md. Flattened directly into the system prompt — helix- " +
    "native, inspired by OpenAI Agents SDK tripwires, not guardrails.ai.";
  readonly uiSchema = {
    instruction: {
      widget: "markdown",
      label: "GUARDRAIL.md",
      help: "Prose body explaining the intent behind the rule set.",
      height: 280,
      order: 10,
    },
    rules: {
      widget: "list-markdown",
      label: "Rules",
      help: "Individual directives the agent must follow every turn.",
      order: 20,
    },
    severity: {
      widget: "select",
      label: "Severity",
      help: "warn lets the turn continue; error fails the turn; hard refuses to answer.",
      order: 30,
    },
    scope: {
      widget: "select",
      label: "Scope",
      help: "input guards the user prompt; output guards the agent response; both runs on each side.",
      order: 40,
    },
  };

  schema() { return zodSpecToJsonSchema(GuardrailSpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    return GuardrailSchema.parse(raw);
  }


  summary(doc: import("../kernel/document.js").Document): Record<string, unknown> | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      severity: typeof spec.severity === "string" ? spec.severity : "warn",
      scope: typeof spec.scope === "string" ? spec.scope : "both",
      rules: Array.isArray(spec.rules) ? spec.rules.length : 0,
    };
  }

  preview(doc: import("../kernel/document.js").Document): import("../kernel/preview.js").PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const blocks: import("../kernel/preview.js").PreviewBlock[] = [];

    const instruction = typeof spec.instruction === "string" ? spec.instruction : "";
    if (instruction) {
      blocks.push({ kind: "markdown", title: "GUARDRAIL.md", body: instruction });
    }

    const rules = spec.rules;
    if (Array.isArray(rules) && rules.length > 0) {
      blocks.push({
        kind: "markdown",
        title: "Rules",
        body: rules
          .map((r) => `- ${typeof r === "string" ? r : JSON.stringify(r)}`)
          .join("\n"),
      });
    }

    const meta: Array<{ label: string; value: string }> = [];
    if (typeof spec.severity === "string") meta.push({ label: "severity", value: spec.severity });
    if (typeof spec.scope === "string") meta.push({ label: "scope", value: spec.scope });
    if (meta.length > 0) {
      blocks.push({ kind: "fields", title: "Policy", fields: meta });
    }

    if (blocks.length === 0) {
      return [{ kind: "empty", title: "Guardrail (empty)" }];
    }
    return blocks;
  }
}

// ---------------------------------------------------------------------------
// GuardrailReader
// ---------------------------------------------------------------------------

function parseFrontmatter(text: string): Record<string, unknown> {
  const match = text.match(/^---\n([\s\S]*?)---\n?/);
  if (!match) return {};
  try {
    const parsed = yaml.load(match[1]);
    return typeof parsed === "object" && parsed !== null ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

export class GuardrailReader implements ReaderPort {
  constructor(private fs: FSLike = nodeFS) {}

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    return this.fs.exists(`${path}/GUARDRAIL.md`);
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const guardrailMd = this.fs.readFile(`${path}/GUARDRAIL.md`);
    const metadata = parseFrontmatter(guardrailMd);
    const name = String(metadata.name || "") || path.split("/").pop() || "";
    const description = String(metadata.desc || metadata.description || "");
    const severity = String(metadata.severity || "warn");
    const scope = String(metadata.scope || "both");

    // Extract body (after frontmatter)
    const body = guardrailMd.replace(/^---\n[\s\S]*?---\n?/, "").trim();

    // Parse rules from body: lines starting with "- "
    const bodyRules: string[] = [];
    for (const line of body.split("\n")) {
      const trimmed = line.trimStart();
      if (trimmed.startsWith("- ")) {
        bodyRules.push(trimmed.slice(2).trim());
      }
    }

    // Rules can come from frontmatter (YAML list) or body (markdown list)
    const frontmatterRules = metadata.rules;
    let rules: string[];
    if (Array.isArray(frontmatterRules) && frontmatterRules.length > 0) {
      rules = frontmatterRules.map(String);
    } else {
      rules = bodyRules;
    }

    return {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Guardrail",
      metadata: { name, description },
      spec: { rules, severity, scope },
    };
  }
}

// ---------------------------------------------------------------------------
// GuardrailWriter
// ---------------------------------------------------------------------------

export class GuardrailWriter implements WriterPort {
  constructor(private fs: FSLike = nodeFS) {}

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === "Guardrail";
  }

  /** Shared by write()/serialize() so the two surfaces cannot drift
   *  (s-dna-rw-roundtrip-suite). */
  private entries(raw: Record<string, unknown>, defaultName: string): SerializedFile[] {
    const spec = (raw.spec as Record<string, unknown>) ?? {};
    const meta = (raw.metadata as Record<string, unknown>) ?? {};

    const name = (meta.name as string) || defaultName;
    const description = (meta.description as string) ?? "";
    const severity = (spec.severity as string) ?? "warn";
    const scope = (spec.scope as string) ?? "both";
    const rules = (spec.rules as string[]) ?? [];

    // Build frontmatter lines
    const fmLines: string[] = [];
    fmLines.push(`name: ${name}`);
    if (description) fmLines.push(`desc: ${description}`);
    // Only write severity/scope if non-default
    if (severity !== "warn") fmLines.push(`severity: ${severity}`);
    if (scope !== "both") fmLines.push(`scope: ${scope}`);

    const frontmatter = fmLines.join("\n");

    // Build body: rules as "- " lines
    const bodyLines = rules.map((r) => `- ${r}`);
    const body = bodyLines.join("\n");

    const content = body
      ? `---\n${frontmatter}\n---\n\n${body}\n`
      : `---\n${frontmatter}\n---\n`;

    return [{ relativePath: "GUARDRAIL.md", content }];
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    return this.entries(raw, "");
  }

  write(bundle: BundleHandle, raw: Record<string, unknown>): void { const path = bundle.path ?? "";
    this.fs.mkdir(path);
    for (const f of this.entries(raw, path.split("/").pop() || "")) {
      this.fs.writeFile(`${path}/${f.relativePath}`, f.content ?? "");
    }
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class GuardrailExtension implements Extension {
  readonly name = "guardrails";
  readonly version = "1.0.0";

  constructor(private fs: FSLike = nodeFS) {}

  register(kernel: ExtensionHost): void {
    kernel.kind(new GuardrailKind());
    kernel.reader(new GuardrailReader(this.fs));
    kernel.writer(new GuardrailWriter(this.fs));
  }
}
