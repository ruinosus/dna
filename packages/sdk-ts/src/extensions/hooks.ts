/**
 * HookExtension — Hook kind for declarative hook configuration.
 *
 * Hooks declared as YAML documents in the manifest. The kernel auto-registers
 * them on the HookRegistry during instance creation.
 */

import yaml from "js-yaml";
import { nodeFS } from "../kernel/fs.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { KindBase } from "../kernel/kind_base.js";
import type { FSLike } from "../kernel/fs.js";
import { HookSchema, HookSpecSchema, zodSpecToJsonSchema } from "../kernel/models.js";
import type { ExtensionHost, Extension, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { SD } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";
import type { PreviewBlock } from "../kernel/preview.js";

// ---------------------------------------------------------------------------
// HookKind
// ---------------------------------------------------------------------------

class HookKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/v1";
  readonly kind = "Hook";
  readonly alias = "helix-hook";
  readonly isSchemaAffecting = true;
  readonly origin = "github.com/ruinosus/dna";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.bundle("hooks", "HOOK.md", "text", "body");
  readonly graphStyle = { fill: "#F59E0B", stroke: "#D97706", textColor: "#fff" };
  readonly asciiIcon = "\u26A1";
  readonly displayLabel = "Hooks";
  readonly _sourceUrl = import.meta.url;
  readonly docs =
    "A Hook declares a middleware or event handler that the kernel auto-registers " +
    "on the HookRegistry when the manifest is loaded. Hooks can inject fields into " +
    "the prompt context (inject_fields), log events (log), or run custom scripts (script).";

  readonly uiSchema = {
    target: {
      widget: "select",
      label: "Target Hook",
      help: "Which kernel hook this attaches to",
      options: ["pre_build_prompt", "post_build_prompt", "parse_error", "extension_error", "kinddef_conflict"],
      order: 1,
    },
    type: {
      widget: "select",
      label: "Type",
      help: "Middleware transforms context (returns modified ctx). Event is fire-and-forget.",
      options: ["middleware", "event"],
      order: 2,
    },
    action: {
      widget: "select",
      label: "Action",
      help: "inject_fields: merge YAML key-value pairs into prompt context. log: log event to console. script: run custom code.",
      options: ["inject_fields", "log", "script"],
      order: 3,
    },
    fields: {
      widget: "code",
      language: "yaml",
      label: "Injected Fields (YAML)",
      help: "Key-value pairs merged into the prompt context when action is inject_fields",
      height: 200,
      order: 4,
    },
    body: {
      widget: "code",
      language: "javascript",
      label: "Script",
      help: "JavaScript function: (ctx) => { ... return ctx; } for middleware, or (ctx) => { ... } for events",
      height: 300,
      order: 5,
    },
  };

  schema() { return zodSpecToJsonSchema(HookSpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    return HookSchema.parse(raw);
  }

  describe(doc: Document): string | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return `Hook: ${doc.name} \u2192 ${spec.target} (${spec.action})`;
  }

  summary(doc: Document): Record<string, unknown> | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      target: spec.target ?? "",
      type: spec.type ?? "middleware",
      action: spec.action ?? "inject_fields",
    };
  }


  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const blocks: PreviewBlock[] = [];

    blocks.push({
      kind: "fields",
      title: "Hook Configuration",
      fields: [
        { label: "Target", value: String(spec.target ?? "") },
        { label: "Type", value: String(spec.type ?? "middleware") },
        { label: "Action", value: String(spec.action ?? "inject_fields") },
      ],
    });

    const action = spec.action as string;
    if (action === "inject_fields") {
      const fields = spec.fields as Record<string, unknown> | undefined;
      if (fields && Object.keys(fields).length > 0) {
        blocks.push({
          kind: "code",
          title: "Injected Fields",
          body: JSON.stringify(fields, null, 2),
          language: "json",
        });
      }
    } else if (action === "script") {
      const body = spec.body as string | undefined;
      if (body) {
        blocks.push({
          kind: "code",
          title: "Script",
          body,
          language: "javascript",
        });
      }
    }

    return blocks.length > 0 ? blocks : [{ kind: "empty", title: "Hook (empty)" }];
  }
}

// ---------------------------------------------------------------------------
// HookReader: detects HOOK.md and parses frontmatter + body
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

export class HookReader implements ReaderPort {
  readonly _marker = "HOOK.md";

  constructor(private fs: FSLike = nodeFS) {}

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    return this.fs.exists(`${path}/HOOK.md`);
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const text = this.fs.readFile(`${path}/HOOK.md`);
    const [fm, body] = parseFrontmatter(text);

    const name = String(fm.name || "") || path.split("/").pop() || "";
    const description = String(fm.description || "");

    const spec: Record<string, unknown> = {
      target: fm.target ?? "pre_build_prompt",
      type: fm.type ?? "middleware",
      action: fm.action ?? "inject_fields",
      body: body.trim(),
    };

    // Parse body based on action type
    const action = spec.action as string;
    if (action === "inject_fields" && body.trim()) {
      try {
        const parsed = yaml.load(body.trim());
        if (typeof parsed === "object" && parsed !== null) {
          spec.fields = parsed;
        }
      } catch {
        // If YAML parse fails, treat as raw text
        spec.fields = {};
      }
    }

    return {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Hook",
      metadata: { name, description },
      spec,
    };
  }
}

// ---------------------------------------------------------------------------
// HookWriter: serializes Hook back to HOOK.md
// ---------------------------------------------------------------------------

export class HookWriter implements WriterPort {
  readonly _kind = "Hook";

  constructor(private fs: FSLike = nodeFS) {}

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === "Hook";
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
    fmParts.push(`target: ${spec.target ?? "pre_build_prompt"}`);
    fmParts.push(`type: ${spec.type ?? "middleware"}`);
    fmParts.push(`action: ${spec.action ?? "inject_fields"}`);
    const frontmatter = fmParts.join("\n");

    let body = "";
    const action = spec.action as string;
    if (action === "inject_fields" && spec.fields) {
      body = yaml.dump(spec.fields, { flowLevel: -1 }).trim();
    } else if (action === "script" && spec.body) {
      body = String(spec.body);
    }

    const content = body
      ? `---\n${frontmatter}\n---\n\n${body}\n`
      : `---\n${frontmatter}\n---\n`;

    return [{ relativePath: "HOOK.md", content }];
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class HookExtension implements Extension {
  readonly name = "hooks";
  readonly version = "1.0.0";

  constructor(private fs: FSLike = nodeFS) {}

  register(kernel: ExtensionHost): void {
    kernel.kind(new HookKind());
    kernel.reader(new HookReader(this.fs));
    kernel.writer(new HookWriter(this.fs));
  }
}
