/**
 * RecognizerExtension — Recognizer kind (Presidio ad-hoc recognizer).
 *
 * Declares PII detection patterns as manifest documents. Recognizers are
 * referenced by SafetyPolicy documents via dep_filters and exported to
 * LiteLLM/Presidio at runtime.
 *
 * 1:1 parity with Python dna.extensions.recognizer.
 */

import yaml from "js-yaml";
import { nodeFS } from "../kernel/fs.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { KindBase } from "../kernel/kind_base.js";
import type { FSLike } from "../kernel/fs.js";
import { RecognizerSchema, RecognizerSpecSchema, zodSpecToJsonSchema } from "../kernel/models.js";
import type { Extension, KindPort, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { SD } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";
import type { PreviewBlock } from "../kernel/preview.js";

// ---------------------------------------------------------------------------
// RecognizerKind
// ---------------------------------------------------------------------------

class RecognizerKind extends KindBase {
  readonly apiVersion = "presidio/v1";
  readonly kind = "Recognizer";
  readonly alias = "presidio-recognizer";
  readonly isSchemaAffecting = true;
  readonly origin = "microsoft.github.io/presidio";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly descriptionFallbackField = "entity_type";
  readonly storage = SD.bundle("recognizers", "RECOGNIZER.md", "text", "patterns");
  readonly graphStyle = { fill: "#6366F1", stroke: "#4F46E5", textColor: "#fff" };
  readonly asciiIcon = "\uD83D\uDD0D";
  readonly displayLabel = "Recognizers";
  readonly _sourceUrl = import.meta.url;
  readonly docs =
    "A Recognizer is a Presidio ad-hoc recognizer that detects PII entities " +
    "using regex patterns or deny lists. Recognizers are referenced by " +
    "SafetyPolicy documents and exported to LiteLLM/Presidio at runtime.";

  readonly uiSchema = {
    entity_type: {
      widget: "input",
      label: "Entity Type",
      help: "Presidio entity name, e.g. BR_CPF, BR_CNPJ",
      order: 1,
    },
    language: {
      widget: "select",
      options: ["en", "pt", "es", "de", "fr"],
      label: "Language",
      order: 2,
    },
    patterns: {
      widget: "code",
      language: "yaml",
      label: "Patterns",
      help: "List of {name, regex, score} objects",
      height: 200,
      order: 3,
    },
    deny_list: {
      widget: "tags",
      label: "Deny List",
      help: "Words that always match this entity",
      order: 4,
    },
    context: {
      widget: "tags",
      label: "Context Words",
      help: "Words near the entity that boost confidence",
      order: 5,
    },
  };

  schema() { return zodSpecToJsonSchema(RecognizerSpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    // patterns comes as raw text (body_as=text). Parse as YAML to get array of pattern objects.
    const spec = (raw.spec ?? {}) as Record<string, unknown>;
    if (typeof spec.patterns === "string" && spec.patterns.trim()) {
      try {
        const parsed = yaml.load(spec.patterns);
        if (Array.isArray(parsed)) {
          spec.patterns = parsed;
        } else {
          spec.patterns = [];
        }
      } catch {
        spec.patterns = [];
      }
    }
    return RecognizerSchema.parse(raw);
  }

  describe(doc: Document): string | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return `Recognizer: ${doc.name} (entity=${spec.entity_type})`;
  }

  summary(doc: Document): Record<string, unknown> | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      entity_type: typeof spec.entity_type === "string" ? spec.entity_type : "",
      language: typeof spec.language === "string" ? spec.language : "en",
      patterns: Array.isArray(spec.patterns) ? spec.patterns.length : 0,
      deny_list: Array.isArray(spec.deny_list) ? spec.deny_list.length : 0,
    };
  }


  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const blocks: PreviewBlock[] = [];

    const meta: Array<{ label: string; value: string }> = [];
    if (typeof spec.entity_type === "string") meta.push({ label: "Entity Type", value: spec.entity_type });
    if (typeof spec.language === "string") meta.push({ label: "Language", value: spec.language });
    if (meta.length > 0) {
      blocks.push({ kind: "fields", title: "Recognizer", fields: meta });
    }

    const patterns = spec.patterns;
    if (Array.isArray(patterns) && patterns.length > 0) {
      blocks.push({
        kind: "code",
        title: "Patterns",
        body: yaml.dump(patterns, { flowLevel: 3 }).trim(),
        language: "yaml",
      });
    }

    const denyList = spec.deny_list;
    if (Array.isArray(denyList) && denyList.length > 0) {
      blocks.push({
        kind: "code",
        title: "Deny List",
        body: denyList.join(", "),
        language: "text",
      });
    }

    const context = spec.context;
    if (Array.isArray(context) && context.length > 0) {
      blocks.push({
        kind: "code",
        title: "Context Words",
        body: context.join(", "),
        language: "text",
      });
    }

    if (blocks.length === 0) {
      return [{ kind: "empty", title: "Recognizer (empty)" }];
    }
    return blocks;
  }
}

// ---------------------------------------------------------------------------
// RecognizerReader
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

export class RecognizerReader implements ReaderPort {
  readonly _marker = "RECOGNIZER.md";

  constructor(private fs: FSLike = nodeFS) {}

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    return this.fs.exists(`${path}/RECOGNIZER.md`);
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const text = this.fs.readFile(`${path}/RECOGNIZER.md`);
    const [fm, body] = parseFrontmatter(text);

    const name = String(fm.name || "") || path.split("/").pop() || "";
    const description = String(fm.description || "");
    const entity_type = String(fm.entity_type || "");
    const language = String(fm.language || "en");

    // Parse deny_list and context from frontmatter
    const deny_list = Array.isArray(fm.deny_list) ? fm.deny_list.map(String) : [];
    const context = Array.isArray(fm.context) ? fm.context.map(String) : [];

    // Parse body as YAML list of pattern objects
    let patterns: unknown[] = [];
    const trimmedBody = body.trim();
    if (trimmedBody) {
      try {
        const parsed = yaml.load(trimmedBody);
        if (Array.isArray(parsed)) {
          patterns = parsed;
        }
      } catch { /* ignore invalid YAML */ }
    }

    return {
      apiVersion: "presidio/v1",
      kind: "Recognizer",
      metadata: { name, description },
      spec: { entity_type, language, patterns, deny_list, context },
    };
  }
}

// ---------------------------------------------------------------------------
// RecognizerWriter
// ---------------------------------------------------------------------------

export class RecognizerWriter implements WriterPort {
  readonly _kind = "Recognizer";

  constructor(private fs: FSLike = nodeFS) {}

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === "Recognizer";
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
    if (spec.entity_type) fmParts.push(`entity_type: ${spec.entity_type}`);
    fmParts.push(`language: ${spec.language ?? "en"}`);

    const denyList = spec.deny_list as string[] | undefined;
    if (denyList && denyList.length > 0) {
      fmParts.push(`deny_list:\n${denyList.map(w => `  - ${w}`).join("\n")}`);
    }

    const context = spec.context as string[] | undefined;
    if (context && context.length > 0) {
      fmParts.push(`context:\n${context.map(w => `  - ${w}`).join("\n")}`);
    }

    const frontmatter = fmParts.join("\n");

    // Serialize patterns as YAML list
    const patterns = (spec.patterns as unknown[]) ?? [];
    let body = "";
    if (patterns.length > 0) {
      body = yaml.dump(patterns, { flowLevel: 3 }).trim();
    }

    const content = body
      ? `---\n${frontmatter}\n---\n\n${body}\n`
      : `---\n${frontmatter}\n---\n`;

    return [{ relativePath: "RECOGNIZER.md", content }];
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class RecognizerExtension implements Extension {
  readonly name = "recognizer";
  readonly version = "1.0.0";

  constructor(private fs: FSLike = nodeFS) {}

  register(kernel: unknown): void {
    const k = kernel as {
      kind(kp: KindPort): void;
      reader(r: ReaderPort): void;
      writer(w: WriterPort): void;
    };
    k.kind(new RecognizerKind());
    k.reader(new RecognizerReader(this.fs));
    k.writer(new RecognizerWriter(this.fs));
  }
}
