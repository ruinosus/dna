/**
 * AgentsMdExtension — AgentDefinition kind + AgentDefinitionReader + Writer.
 *
 * 1:1 parity with Python dna.v3.extensions.agentsmd.
 */

import yaml from "js-yaml";
import { deriveFirstLine } from "../kernel/_text.js";
import { nodeFS } from "../kernel/fs.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { KindBase } from "../kernel/kind_base.js";
import type { FSLike } from "../kernel/fs.js";
import { AgentDefinitionSchema, AgentDefinitionSpecSchema, zodSpecToJsonSchema } from "../kernel/models.js";
import type { Extension, KindPort, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { SD } from "../kernel/protocols.js";

// ---------------------------------------------------------------------------
// Frontmatter helpers
// ---------------------------------------------------------------------------

function parseAgentsFrontmatter(text: string): { metadata: Record<string, unknown>; body: string } {
  const match = text.match(/^---\n([\s\S]*?)---\n?([\s\S]*)$/);
  if (!match) return { metadata: {}, body: text };
  try {
    const parsed = yaml.load(match[1]);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return {
        metadata: parsed as Record<string, unknown>,
        body: match[2].replace(/^\n+/, ""),
      };
    }
  } catch {}
  return { metadata: {}, body: text };
}

// ---------------------------------------------------------------------------
// AgentDefinitionKind
// ---------------------------------------------------------------------------

class AgentDefinitionKind extends KindBase {
  readonly apiVersion = "agents.md/v1";
  readonly kind = "AgentDefinition";
  readonly alias = "agentsmd-agent";
  readonly origin = "agents.md";
  readonly isPromptTarget = true;
  readonly promptTargetPriority = 1;
  readonly flattenInContext = true;
  readonly descriptionFallbackField = "content";
  readonly storage = SD.standalone("AGENTS.md");
  readonly graphStyle = { fill: "#6366F1", stroke: "#4F46E5", textColor: "#fff" };
  readonly asciiIcon = "📝";
  readonly displayLabel = "AGENTS.md";
  readonly _sourceUrl = import.meta.url;
  readonly docs =
    "AgentDefinition wraps a standalone AGENTS.md file — the emerging " +
    "community convention (https://agents.md) for repo-level coding-agent " +
    "instructions. Flattened into context for agents working in the scope.";

  schema() { return zodSpecToJsonSchema(AgentDefinitionSpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    return AgentDefinitionSchema.parse(raw);
  }

  summary() { return null; }

  promptTemplate() {
    return "{{{content}}}";
  }

  preview(doc: import("../kernel/document.js").Document): import("../kernel/preview.js").PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const content = typeof spec.content === "string" ? spec.content : "";
    if (!content) {
      return [{ kind: "empty", title: "AGENTS.md (empty)" }];
    }
    return [{ kind: "markdown", title: "AGENTS.md", body: content }];
  }
}

// ---------------------------------------------------------------------------
// AgentDefinitionReader
// ---------------------------------------------------------------------------

class AgentDefinitionReader implements ReaderPort {
  constructor(private fs: FSLike) {}

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    if (!this.fs.exists(`${path}/AGENTS.md`)) return false;
    // Skip if inside a soul bundle
    if (this.fs.exists(`${path}/SOUL.md`) || this.fs.exists(`${path}/soul.json`)) {
      return false;
    }
    return true;
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const text = this.fs.readFile(`${path}/AGENTS.md`);
    const name = path.split("/").pop() || "";
    const { metadata: fm, body } = parseAgentsFrontmatter(text);
    const metadata: Record<string, unknown> = { ...fm };
    if (metadata.name == null) metadata.name = name;

    // When no frontmatter was present, preserve the full original text
    // (byte-compat). When frontmatter IS present, spec.content is the body
    // after it.
    const hasFm = Object.keys(fm).length > 0;
    const content = hasFm ? body : text;

    return {
      apiVersion: "agents.md/v1",
      kind: "AgentDefinition",
      metadata,
      spec: { content },
    };
  }
}

// ---------------------------------------------------------------------------
// AgentDefinitionWriter
// ---------------------------------------------------------------------------

export class AgentDefinitionWriter implements WriterPort {
  constructor(private fs: FSLike = nodeFS) {}

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === "AgentDefinition";
  }

  write(bundle: BundleHandle, raw: Record<string, unknown>): void { const path = bundle.path ?? "";
    this.fs.mkdir(path);
    for (const f of this.serialize(raw)) {
      this.fs.writeFile(`${path}/${f.relativePath}`, f.content ?? "");
    }
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const spec = (raw.spec ?? {}) as Record<string, unknown>;
    const meta = (raw.metadata ?? {}) as Record<string, unknown>;
    const body = ((spec.content as string) ?? "") || "";

    // Drop null/undefined before deciding whether to emit frontmatter.
    const fm: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(meta)) {
      if (v == null) continue;
      fm[k] = v;
    }

    // F3 market fidelity: metadata.description may have been ENRICHED at
    // parse time (deriveFirstLine of the body). Persisting it would emit
    // frontmatter the source bundle never had — elide when derivable.
    if (typeof fm.description === "string" && fm.description === deriveFirstLine(body)) {
      delete fm.description;
    }
    const bodyHasFm = body.trimStart().startsWith("---");
    const fmKeys = Object.keys(fm);
    // Byte-compat for the simple "only name" case — previous writer emitted
    // just the body. Keeps existing fixture AGENTS.md files from diffing.
    const onlyName = fmKeys.length === 0 || (fmKeys.length === 1 && fmKeys[0] === "name");
    const needsFm = fmKeys.length > 0 && !bodyHasFm && !onlyName;

    if (needsFm) {
      const fmBody = yaml.dump(fm, { flowLevel: -1, sortKeys: false, lineWidth: -1 }).replace(/\n+$/, "");
      return [{ relativePath: "AGENTS.md", content: `---\n${fmBody}\n---\n${body}` }];
    }
    return [{ relativePath: "AGENTS.md", content: body }];
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class AgentsMdExtension implements Extension {
  readonly name = "agentsmd";
  readonly version = "1.0.0";

  constructor(private fs: FSLike = nodeFS) {}

  register(kernel: unknown): void {
    const k = kernel as {
      kind(kp: KindPort): void;
      reader(r: ReaderPort): void;
      writer(w: WriterPort): void;
    };
    k.kind(new AgentDefinitionKind());
    k.reader(new AgentDefinitionReader(this.fs));
    k.writer(new AgentDefinitionWriter(this.fs));
  }
}
