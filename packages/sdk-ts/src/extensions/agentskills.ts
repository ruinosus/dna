/**
 * AgentSkillsExtension — Skill kind + SkillReader.
 *
 * 1:1 parity with Python dna.v3.extensions.agentskills.
 */

import yaml from "js-yaml";
import { deriveFirstLine } from "../kernel/_text.js";
import { SkillSchema, SkillSpecSchema, zodSpecToJsonSchema } from "../kernel/models.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { KindBase } from "../kernel/kind_base.js";
import type { Extension, KindPort, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { SD } from "../kernel/protocols.js";
import { nodeFS, readTextSafe, collectDir } from "../kernel/fs.js";
import type { FSLike } from "../kernel/fs.js";
import type { Document } from "../kernel/document.js";
import type { PreviewBlock } from "../kernel/preview.js";

// ---------------------------------------------------------------------------
// SkillKind
// ---------------------------------------------------------------------------

class SkillKind extends KindBase {
  readonly apiVersion = "agentskills.io/v1";
  readonly kind = "Skill";
  readonly alias = "agentskills-skill";
  readonly isSchemaAffecting = true;
  readonly origin = "agentskills.io";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly descriptionFallbackField = "instruction";
  readonly storage = SD.bundle("skills", "SKILL.md");
  readonly graphStyle = { fill: "#10B981", stroke: "#059669", textColor: "#fff" };
  readonly asciiIcon = "📖";
  readonly displayLabel = "Skills";
  readonly _sourceUrl = import.meta.url;
  readonly docs =
    "A Skill is a modular, progressively-disclosed unit of know-how stored " +
    "as a bundle rooted on SKILL.md with optional scripts/, references/, " +
    "assets/. Skills are NOT flattened into prompts; the harness exposes a " +
    "catalogue and agents read full SKILL.md on demand.";
  readonly uiSchema = {
    instruction: {
      widget: "markdown-toc",
      label: "SKILL.md",
      help: "The skill's instruction body (progressive disclosure, ≤500 lines).",
      height: 520,
      order: 10,
    },
    scripts: { widget: "readonly", label: "scripts/", help: "Bundled scripts directory. Edit on disk.", order: 20 },
    references: { widget: "readonly", label: "references/", help: "Bundled reference files. Edit on disk.", order: 30 },
    assets: { widget: "readonly", label: "assets/", help: "Binary/static assets. Edit on disk.", order: 40 },
  };

  schema() { return zodSpecToJsonSchema(SkillSpecSchema); }

  parse(raw: Record<string, unknown>): unknown {
    return SkillSchema.parse(raw);
  }

  summary() { return null; }

  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const instruction =
      typeof spec.instruction === "string" ? spec.instruction : "";
    if (!instruction) {
      return [{ kind: "empty", title: "Skill (empty)" }];
    }
    return [
      {
        kind: "markdown",
        title: "SKILL.md",
        body: instruction,
      },
    ];
  }
}

// ---------------------------------------------------------------------------
// SkillReader
// ---------------------------------------------------------------------------

const KNOWN_DIRS = new Set(["scripts", "references", "assets"]);

export class SkillReader implements ReaderPort {
  constructor(private fs: FSLike) {}

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    return this.fs.exists(`${path}/SKILL.md`);
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const skillMd = this.fs.readFile(`${path}/SKILL.md`);
    const metadata = parseFrontmatter(skillMd);
    const name =
      (typeof metadata.name === "string" && metadata.name) ||
      path.split("/").pop() ||
      "";
    const description =
      typeof metadata.description === "string" ? metadata.description : "";

    // Extract body (after frontmatter) — F3 market fidelity: keep the
    // tail byte-exact except the ONE leading newline the writer
    // canonically re-emits ("---\\n\\n"). Trailing newlines and extra
    // blank lines are part of the artifact.
    const fmMatch = skillMd.match(/^---\n[\s\S]*?---(?:\n|$)/);
    const tail = fmMatch ? skillMd.slice(fmMatch[0].length) : skillMd;
    const body = tail.startsWith("\n") ? tail.slice(1) : tail;

    const spec: Record<string, unknown> = { instruction: body };

    // Collect known subdirectories (scripts/, references/, assets/)
    for (const dirName of KNOWN_DIRS) {
      const sub = `${path}/${dirName}`;
      if (this.fs.isDirectory(sub)) {
        const files = collectDir(this.fs, sub, sub);
        if (Object.keys(files).length > 0) {
          spec[dirName] = files;
        }
      }
    }

    // Single readDir call, reused for extras + root files
    const entries = this.fs.readDir(path);

    // Collect ALL other subdirectories as extra bundles
    const extras: Record<string, Record<string, string>> = {};
    for (const entry of entries) {
      const full = `${path}/${entry}`;
      if (!this.fs.isDirectory(full) || KNOWN_DIRS.has(entry)) continue;
      const files = collectDir(this.fs, full, full);
      if (Object.keys(files).length > 0) {
        extras[entry] = files;
      }
    }
    if (Object.keys(extras).length > 0) {
      spec.extras = extras;
    }

    // Collect root-level extra files (not SKILL.md)
    const rootFiles: Record<string, string> = {};
    for (const entry of entries) {
      const full = `${path}/${entry}`;
      if (!this.fs.isFile(full) || entry === "SKILL.md") continue;
      const text = readTextSafe(this.fs, full);
      if (text !== null) {
        rootFiles[entry] = text;
      }
    }
    if (Object.keys(rootFiles).length > 0) {
      spec.root_files = rootFiles;
    }

    // Preserve all frontmatter keys (tags, owner, priority, …). SkillWriter
    // already round-trips extras; spreading metadata first then overriding
    // name/description defaults closes the asymmetry on the reader side.
    return {
      apiVersion: "agentskills.io/v1",
      kind: "Skill",
      metadata: { ...metadata, name, description },
      spec,
    };
  }
}

function parseFrontmatter(text: string): Record<string, unknown> {
  const match = text.match(/^---\n([\s\S]*?)---\n?/);
  if (!match) return {};
  try {
    const parsed = yaml.load(match[1]);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {}
  return {};
}

// ---------------------------------------------------------------------------
// SkillWriter
// ---------------------------------------------------------------------------

export class SkillWriter implements WriterPort {
  constructor(private fs: FSLike) {}

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === "Skill";
  }

  write(bundle: BundleHandle, raw: Record<string, unknown>): void { const path = bundle.path ?? "";
    this.fs.mkdir(path);
    for (const f of this.serialize(raw)) {
      this.fs.writeFile(`${path}/${f.relativePath}`, f.content ?? "");
    }
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const files: SerializedFile[] = [];
    const meta = (raw.metadata ?? {}) as Record<string, unknown>;
    const spec = (raw.spec ?? {}) as Record<string, unknown>;

    // SKILL.md with frontmatter + instruction body
    const fm: Record<string, unknown> = {};
    if (meta.name) fm.name = meta.name;
    if (meta.description) fm.description = meta.description;
    // Preserve extra metadata (e.g. tenant for RLS) — frontmatter is the
    // authoritative metadata block for bundle kinds.
    for (const [key, value] of Object.entries(meta)) {
      if (key === "name" || key === "description") continue;
      if (value == null) continue;
      fm[key] = value;
    }
    // F3 market fidelity: metadata.description may have been ENRICHED at
    // parse time (deriveFirstLine of the body). Persisting it would emit
    // frontmatter the source bundle never had — elide when derivable.
    if (typeof fm.description === "string" && fm.description === deriveFirstLine((spec.instruction as string) ?? "")) {
      delete fm.description;
    }
    // lineWidth: real marketplace skills author description as ONE long
    // line — the default width 80 would wrap it (not byte-faithful).
    const frontmatter = yaml.dump(fm, { flowLevel: -1, sortKeys: false, lineWidth: -1 });
    const instruction = (spec.instruction as string) ?? "";
    files.push({ relativePath: "SKILL.md", content: `---\n${frontmatter}---\n\n${instruction}` });

    // Sub-directories: scripts, references, assets
    for (const dirName of ["scripts", "references", "assets"]) {
      const dirFiles = spec[dirName];
      if (dirFiles != null && typeof dirFiles === "object") {
        for (const [fname, fcontent] of Object.entries(dirFiles as Record<string, string>)) {
          files.push({ relativePath: `${dirName}/${fname}`, content: fcontent });
        }
      }
    }

    // Extras
    const extras = spec.extras;
    if (extras != null && typeof extras === "object") {
      for (const [dirName, dirFiles] of Object.entries(extras as Record<string, Record<string, string>>)) {
        if (typeof dirFiles === "object") {
          for (const [fname, fcontent] of Object.entries(dirFiles)) {
            files.push({ relativePath: `${dirName}/${fname}`, content: fcontent });
          }
        }
      }
    }

    // Root files
    const rootFiles = spec.root_files;
    if (rootFiles != null && typeof rootFiles === "object") {
      for (const [fname, fcontent] of Object.entries(rootFiles as Record<string, string>)) {
        files.push({ relativePath: fname, content: fcontent });
      }
    }

    return files;
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class AgentSkillsExtension implements Extension {
  readonly name = "agentskills";
  readonly version = "1.0.0";

  constructor(private fs: FSLike = nodeFS) {}

  register(kernel: unknown): void {
    const k = kernel as {
      kind(kp: KindPort): void;
      reader(r: ReaderPort): void;
      writer(w: WriterPort): void;
    };
    k.kind(new SkillKind());
    k.reader(new SkillReader(this.fs));
    k.writer(new SkillWriter(this.fs));
  }
}
