/**
 * GenericBundleReader / GenericBundleWriter — auto-generated from StorageDescriptor.
 *
 * Custom kinds that follow the standard BUNDLE layout can use these instead of
 * hand-writing dedicated Reader/Writer classes.
 *
 * 1:1 parity with Python dna.kernel.generic_rw.
 */

import yaml from "js-yaml";
import { nodeFS } from "./fs.js";
import type { FSLike } from "./fs.js";
import type { BundleHandle, ReaderPort, WriterPort, SerializedFile } from "./protocols.js";
import type { StorageDescriptor, BodyMode } from "./protocols.js";

const META_FIELDS = new Set(["name", "description", "labels"]);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseFrontmatter(
  text: string,
  source?: string,
): [Record<string, unknown>, string] {
  const match = text.match(/^---\n([\s\S]*?)---\n?/);
  if (!match) return [{}, text];
  let fm: Record<string, unknown> = {};
  try {
    const parsed = yaml.load(match[1]);
    if (typeof parsed === "object" && parsed !== null) {
      fm = parsed as Record<string, unknown>;
    }
  } catch (e) {
    // Surface the failure loudly instead of silently dropping spec fields.
    // Matches the Python `FrontmatterParseWarning` hardening in generic_rw.py.
    const where = source ? ` in ${source}` : "";
    const message = e instanceof Error ? e.message : String(e);
    const mark = (e as { mark?: { line?: number; column?: number } })?.mark;
    const location =
      mark && typeof mark.line === "number"
        ? ` (line ${mark.line + 1}, column ${(mark.column ?? 0) + 1})`
        : "";
    console.warn(
      `[dna-sdk] Invalid YAML frontmatter${where}${location}: ${message}. ` +
        `Falling back to empty frontmatter — all spec fields from this file ` +
        `will be missing. Fix the frontmatter and reload the manifest.`,
    );
  }
  const body = text.slice(match[0].length);
  return [fm, body];
}

function parseBody(body: string, bodyAs: BodyMode): unknown {
  if (bodyAs === "text") {
    return body.trim();
  }
  if (bodyAs === "list") {
    return body
      .split("\n")
      .filter((l) => l.trim().startsWith("- "))
      .map((l) => l.trim().slice(2));
  }
  if (bodyAs === "sections") {
    const sections: Record<string, string> = {};
    let currentHeading: string | null = null;
    const lines: string[] = [];

    for (const line of body.split("\n")) {
      const headingMatch = line.match(/^## (.+)$/);
      if (headingMatch && !line.startsWith("### ")) {
        const block = lines.join("\n").trim();
        if (currentHeading === null) {
          if (block) sections["_preamble"] = block;
        } else {
          sections[currentHeading] = block;
        }
        currentHeading = headingMatch[1].trim();
        lines.length = 0;
      } else {
        lines.push(line);
      }
    }
    const block = lines.join("\n").trim();
    if (currentHeading === null) {
      if (block) sections["_preamble"] = block;
    } else {
      sections[currentHeading] = block;
    }
    return sections;
  }
  return body.trim();
}

function buildBody(value: unknown, bodyAs: BodyMode): string {
  if (bodyAs === "text") {
    return value != null ? String(value) : "";
  }
  if (bodyAs === "list") {
    if (!Array.isArray(value)) return "";
    return value.map((item) => `- ${item}`).join("\n");
  }
  if (bodyAs === "sections") {
    if (typeof value !== "object" || value === null) return "";
    const parts: string[] = [];
    const dict = value as Record<string, string>;
    if ("_preamble" in dict) {
      parts.push(dict["_preamble"].trim());
    }
    for (const [heading, content] of Object.entries(dict)) {
      if (heading === "_preamble") continue;
      parts.push(`## ${heading}\n\n${typeof content === "string" ? content.trim() : content}`);
    }
    return parts.join("\n\n");
  }
  return value != null ? String(value) : "";
}

// ---------------------------------------------------------------------------
// GenericBundleReader
// ---------------------------------------------------------------------------

export class GenericBundleReader implements ReaderPort {
  /** Exposed for deferred registration detection. */
  readonly _marker: string;

  constructor(
    private sd: StorageDescriptor,
    private apiVersion: string,
    private kindName: string,
    private fs: FSLike = nodeFS,
  ) {
    this._marker = sd.marker!;
  }

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    return this.fs.exists(`${path}/${this.sd.marker!}`);
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const markerPath = `${path}/${this.sd.marker!}`;
    const text = this.fs.readFile(markerPath);
    const [fm, body] = parseFrontmatter(text, markerPath);

    const metadata: Record<string, unknown> = { name: path.split("/").pop() };
    const spec: Record<string, unknown> = {};

    for (const [k, v] of Object.entries(fm)) {
      if (META_FIELDS.has(k)) metadata[k] = v;
      else spec[k] = v;
    }

    const bodyField = this.sd.bodyField ?? "content";
    const bodyAs: BodyMode = this.sd.bodyAs ?? "text";

    if (this.sd.bodyParser) {
      Object.assign(spec, this.sd.bodyParser(body));
    } else {
      spec[bodyField] = parseBody(body, bodyAs);
    }

    return {
      apiVersion: this.apiVersion,
      kind: this.kindName,
      metadata,
      spec,
    };
  }
}

// ---------------------------------------------------------------------------
// GenericBundleWriter
// ---------------------------------------------------------------------------

export class GenericBundleWriter implements WriterPort {
  /** Exposed for deferred registration detection. */
  readonly _kind: string;
  /** Exposed for serialize() and deferred registration. */
  readonly _sd: StorageDescriptor;

  constructor(sd: StorageDescriptor, kind: string, private fs: FSLike = nodeFS) {
    this._sd = sd;
    this._kind = kind;
  }

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === this._kind;
  }

  write(bundle: BundleHandle, raw: Record<string, unknown>): void { const path = bundle.path ?? "";
    this.fs.mkdir(path);
    const meta = (raw.metadata ?? {}) as Record<string, unknown>;
    const spec = (raw.spec ?? {}) as Record<string, unknown>;

    const bodyField = this._sd.bodyField ?? "content";
    const bodyAs: BodyMode = this._sd.bodyAs ?? "text";

    // Build frontmatter: metadata fields first, then spec fields (excluding body_field)
    const fm: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(meta)) {
      if (v != null) fm[k] = v;
    }
    for (const [k, v] of Object.entries(spec)) {
      if (k !== bodyField && v != null) fm[k] = v;
    }

    const frontmatter = yaml.dump(fm, { flowLevel: -1, sortKeys: false });
    const bodyValue = spec[bodyField];
    const body = buildBody(bodyValue, bodyAs);

    this.fs.writeFile(
      `${path}/${this._sd.marker!}`,
      `---\n${frontmatter}---\n\n${body}`,
    );
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const meta = (raw.metadata ?? {}) as Record<string, unknown>;
    const spec = (raw.spec ?? {}) as Record<string, unknown>;

    const fm: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(meta)) { if (v != null) fm[k] = v; }
    const bodyField = this._sd.bodyField;
    for (const [k, v] of Object.entries(spec)) {
      if (k !== bodyField && v != null) fm[k] = v;
    }
    const frontmatter = yaml.dump(fm, { flowLevel: -1, sortKeys: false });

    const bodyData = spec[bodyField!];
    let body: string;
    if (this._sd.bodyAs === "list" && Array.isArray(bodyData)) {
      body = bodyData.map((item: unknown) => `- ${item}`).join("\n");
    } else if (this._sd.bodyAs === "sections" && typeof bodyData === "object" && bodyData) {
      const parts: string[] = [];
      for (const [heading, content] of Object.entries(bodyData as Record<string, string>)) {
        if (heading === "_preamble") parts.unshift(content);
        else parts.push(`## ${heading}\n\n${content}`);
      }
      body = parts.join("\n\n");
    } else {
      body = String(bodyData ?? "");
    }

    return [{ relativePath: this._sd.marker!, content: `---\n${frontmatter}---\n\n${body}` }];
  }
}
