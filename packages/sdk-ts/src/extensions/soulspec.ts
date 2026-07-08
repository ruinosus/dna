/**
 * SoulSpecExtension — Soul kind + SoulReader.
 *
 * 1:1 parity with Python dna.v3.extensions.soulspec.
 */

import yaml from "js-yaml";
import { deriveFirstLine } from "../kernel/_text.js";
import { nodeFS } from "../kernel/fs.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { KindBase } from "../kernel/kind_base.js";
import type { FSLike } from "../kernel/fs.js";
import { SoulSchema, SoulSpecSchema, zodSpecToJsonSchema } from "../kernel/models.js";
import type { Extension, KindPort, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { SD } from "../kernel/protocols.js";

// ---------------------------------------------------------------------------
// Frontmatter helpers
// ---------------------------------------------------------------------------

function parseSoulFrontmatter(text: string): { metadata: Record<string, unknown>; body: string } {
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
// SoulKind
// ---------------------------------------------------------------------------

class SoulKind extends KindBase {
  readonly apiVersion = "soulspec.org/v1";
  readonly kind = "Soul";
  readonly alias = "soulspec-soul";
  readonly isSchemaAffecting = true;
  readonly origin = "soulspec.org";
  readonly isPromptTarget = true;
  readonly promptTargetPriority = 1;
  readonly flattenInContext = true;
  readonly descriptionFallbackField = "soul_content";
  readonly storage = SD.bundle("souls", "SOUL.md");
  readonly graphStyle = { fill: "#8B5CF6", stroke: "#7C3AED", textColor: "#fff" };
  readonly asciiIcon = "🧠";
  readonly displayLabel = "Souls";
  readonly _sourceUrl = import.meta.url;
  readonly docs =
    "A Soul defines an agent's personality, voice, and guiding principles " +
    "as prose — not code. Stored as a bundle: SOUL.md plus optional " +
    "STYLE.md and soul.json. When an agent references a Soul, the kernel " +
    "flattens it directly into the system prompt (flatten_in_context=true).";
  readonly uiSchema = {
    soul_content: {
      widget: "markdown-toc",
      label: "SOUL.md",
      help: "Main prose describing the agent's personality, voice, and principles.",
      height: 480,
      order: 10,
    },
    style_content: {
      widget: "markdown",
      label: "STYLE.md",
      help: "Communication style, formatting conventions, tone.",
      height: 260,
      order: 20,
    },
    soul_json: {
      widget: "code",
      language: "json",
      label: "soul.json",
      help: "Structured soulspec.org metadata (specVersion, tags, etc.).",
      height: 220,
      order: 30,
    },
    agents_content: {
      widget: "markdown",
      label: "AGENTS.md (companion)",
      help: "Optional agents.md-style workflow description.",
      height: 220,
      order: 40,
    },
    identity_content: {
      widget: "markdown",
      label: "IDENTITY.md",
      help: "Who the agent is — role, background, expertise.",
      height: 220,
      order: 50,
    },
    heartbeat_content: {
      widget: "markdown",
      label: "HEARTBEAT.md",
      help: "Autonomous scheduled tasks — cron for the agent, in plain language.",
      height: 220,
      order: 60,
    },
  };

  schema() { return zodSpecToJsonSchema(SoulSpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    return SoulSchema.parse(raw);
  }

  summary() { return null; }

  promptTemplate() {
    return "{{{soul_content}}}";
  }

  preview(doc: import("../kernel/document.js").Document): import("../kernel/preview.js").PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const blocks: import("../kernel/preview.js").PreviewBlock[] = [];
    if (typeof spec.soul_content === "string" && spec.soul_content) {
      blocks.push({ kind: "markdown", title: "SOUL.md", body: spec.soul_content });
    }
    if (typeof spec.style_content === "string" && spec.style_content) {
      blocks.push({ kind: "markdown", title: "STYLE.md", body: spec.style_content });
    }
    if (spec.soul_json && typeof spec.soul_json === "object") {
      blocks.push({
        kind: "code",
        title: "soul.json",
        body: JSON.stringify(spec.soul_json, null, 2),
        language: "json",
      });
    }
    if (typeof spec.agents_content === "string" && spec.agents_content) {
      blocks.push({
        kind: "markdown",
        title: "AGENTS.md (companion)",
        body: spec.agents_content,
      });
    }
    if (typeof spec.identity_content === "string" && spec.identity_content) {
      blocks.push({ kind: "markdown", title: "IDENTITY.md", body: spec.identity_content });
    }
    if (typeof spec.heartbeat_content === "string" && spec.heartbeat_content) {
      blocks.push({ kind: "markdown", title: "HEARTBEAT.md", body: spec.heartbeat_content });
    }
    if (blocks.length === 0) {
      return [{ kind: "empty", title: "Soul (empty)" }];
    }
    return blocks;
  }
}

// ---------------------------------------------------------------------------
// SoulReader
// ---------------------------------------------------------------------------

class SoulReader implements ReaderPort {
  constructor(private fs: FSLike) {}

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    return this.fs.exists(`${path}/SOUL.md`) || this.fs.exists(`${path}/soul.json`);
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const name = path.split("/").pop() || "";
    const spec: Record<string, unknown> = {};
    const metadata: Record<string, unknown> = {};

    // Read SOUL.md — parse frontmatter if present
    if (this.fs.exists(`${path}/SOUL.md`)) {
      const text = this.fs.readFile(`${path}/SOUL.md`);
      const { metadata: fm, body } = parseSoulFrontmatter(text);
      if (Object.keys(fm).length > 0) {
        Object.assign(metadata, fm);
        spec.soul_content = body;
      } else {
        spec.soul_content = text;
      }
    }

    // Read soul.json
    if (this.fs.exists(`${path}/soul.json`)) {
      const parsed = JSON.parse(this.fs.readFile(`${path}/soul.json`));
      spec.soul_json = parsed;
      if (!spec.soul_content) {
        spec.soul_content = JSON.stringify(parsed, null, 2);
      }
    }

    // Companion files — soulspec.org standard
    const companions: [string, string][] = [
      ["style_content", "STYLE.md"],
      ["agents_content", "AGENTS.md"],
      ["identity_content", "IDENTITY.md"],
      ["heartbeat_content", "HEARTBEAT.md"],
    ];
    for (const [field, fname] of companions) {
      if (this.fs.exists(`${path}/${fname}`)) {
        spec[field] = this.fs.readFile(`${path}/${fname}`);
      }
    }

    // name fallback — always ensure metadata has a name
    if (metadata.name == null) metadata.name = name;

    return {
      apiVersion: "soulspec.org/v1",
      kind: "Soul",
      metadata,
      spec,
    };
  }
}

// ---------------------------------------------------------------------------
// SoulWriter
// ---------------------------------------------------------------------------

export class SoulWriter implements WriterPort {
  constructor(private fs: FSLike = nodeFS) {}

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === "Soul";
  }

  write(bundle: BundleHandle, raw: Record<string, unknown>): void { const path = bundle.path ?? "";
    this.fs.mkdir(path);
    for (const f of this.serialize(raw)) {
      this.fs.writeFile(`${path}/${f.relativePath}`, f.content ?? "");
    }
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const files: SerializedFile[] = [];
    const spec = (raw.spec ?? {}) as Record<string, unknown>;
    const meta = (raw.metadata ?? {}) as Record<string, unknown>;

    // Build frontmatter preserving insertion order. Skip null/undefined.
    const fm: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(meta)) {
      if (v == null) continue;
      fm[k] = v;
    }

    const soulBody = (spec.soul_content as string) ?? "";
    // F3 market fidelity: metadata.description may have been ENRICHED at
    // parse time (deriveFirstLine of the body). Persisting it would emit
    // frontmatter the source bundle never had — elide when derivable.
    if (typeof fm.description === "string" && fm.description === deriveFirstLine(soulBody)) {
      delete fm.description;
    }
    const bodyHasFm = soulBody.trimStart().startsWith("---");
    // Byte-compat for the simple "only name" case — previous writer emitted
    // just the body. Keeps existing fixture SOUL.md files from diffing.
    const fmKeys = Object.keys(fm);
    const onlyName = fmKeys.length === 0 || (fmKeys.length === 1 && fmKeys[0] === "name");
    const needsFm = fmKeys.length > 0 && !bodyHasFm && !onlyName;

    if (needsFm) {
      const fmBody = yaml.dump(fm, { flowLevel: -1, sortKeys: false, lineWidth: -1 }).replace(/\n+$/, "");
      files.push({ relativePath: "SOUL.md", content: `---\n${fmBody}\n---\n${soulBody}` });
    } else {
      files.push({ relativePath: "SOUL.md", content: soulBody });
    }

    // soul.json
    const soulJson = spec.soul_json as Record<string, unknown> | undefined;
    if (soulJson) {
      files.push({ relativePath: "soul.json", content: JSON.stringify(soulJson, null, 2) });
    }

    // Companion files (soulspec.org standard)
    const companions: [string, string][] = [
      ["style_content", "STYLE.md"],
      ["agents_content", "AGENTS.md"],
      ["identity_content", "IDENTITY.md"],
      ["heartbeat_content", "HEARTBEAT.md"],
    ];
    for (const [specKey, filename] of companions) {
      const content = spec[specKey] as string | undefined;
      if (content) {
        files.push({ relativePath: filename, content });
      }
    }

    return files;
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class SoulSpecExtension implements Extension {
  readonly name = "soulspec";
  readonly version = "1.0.0";

  constructor(private fs: FSLike = nodeFS) {}

  register(kernel: unknown): void {
    const k = kernel as {
      kind(kp: KindPort): void;
      reader(r: ReaderPort): void;
      writer(w: WriterPort): void;
    };
    k.kind(new SoulKind());
    k.reader(new SoulReader(this.fs));
    k.writer(new SoulWriter(this.fs));
  }
}
