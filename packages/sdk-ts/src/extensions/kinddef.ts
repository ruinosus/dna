/**
 * KindDefinitionExtension — the built-in meta-kind extension.
 *
 * Ships the `KindDefinition` kind itself. Documents live at
 * `.dna/<scope>/kinds/<name>/KIND.yaml` (bundle layout). The kernel's
 * 2-phase loader parses these first and synthesizes a DeclarativeKindPort
 * for each before parsing the rest of the manifest.
 *
 * 1:1 parity with Python dna.extensions.kinddef.
 */

import yaml from "js-yaml";
import { nodeFS } from "../kernel/fs.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import { KindBase } from "../kernel/kind_base.js";
import type { FSLike } from "../kernel/fs.js";
import {
  KIND_DEFINITION_API_VERSION,
  KIND_DEFINITION_KIND,
  KindDefinitionSchema,
  KindDefinitionSpecSchema,
  zodSpecToJsonSchema,
} from "../kernel/models.js";
import type {
  Extension,
  KindPort,
  ReaderPort,
  SerializedFile,
  WriterPort,
  LayerPolicy,
} from "../kernel/protocols.js";
import { SD } from "../kernel/protocols.js";
import type { ExtensionHost } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";
import type { PreviewBlock } from "../kernel/preview.js";

class KindDefinitionKind extends KindBase {
  readonly apiVersion = KIND_DEFINITION_API_VERSION;
  readonly kind = KIND_DEFINITION_KIND;
  readonly alias = "kinddef-kinddefinition";
  readonly isSchemaAffecting = true;
  readonly isOverlayable = false;
  readonly scopeInheritable = false;
  readonly origin = "github.com/ruinosus/dna/core";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.bundle("kinds", "KIND.yaml");
  readonly visibleInBackend = true;  // user-authored via wizard, not system-generated
  readonly graphStyle = { fill: "#A855F7", stroke: "#9333EA", textColor: "#fff" };
  readonly asciiIcon = "🧬";
  readonly displayLabel = "KindDefinitions";
  readonly _sourceUrl = import.meta.url;
  readonly docs =
    "A KindDefinition declaratively defines a brand-new kind without " +
    "writing TypeScript code. Its spec carries the target apiVersion, kind " +
    "name, alias, JSON Schema for the document spec, storage layout, and " +
    "prompt flags. The kernel's 2-phase loader parses KindDefinitions first, " +
    "synthesizes a DeclarativeKindPort for each, then parses the rest of " +
    "the manifest so regular documents can reference the newly registered kind.";

  depFilters(): Record<string, string> | null {
    return null;
  }
  dependencies(): Record<string, string> | null {
    return this.depFilters();
  }
  schema(): Record<string, unknown> | null {
    return zodSpecToJsonSchema(KindDefinitionSpecSchema);
  }
  getDefaultAgentName(_doc: Document): string | null {
    return null;
  }
  getLayerPolicies(_doc: Document): Record<string, LayerPolicy | string> | null {
    return null;
  }
  parse(raw: Record<string, unknown>): unknown {
    return KindDefinitionSchema.parse(raw);
  }
  describe(): string | null {
    return null;
  }
  summary(): Record<string, unknown> | null {
    return null;
  }
  promptTemplate(): string | null {
    return null;
  }

  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const fields: Array<{ label: string; value: string }> = [];
    if (typeof spec.target_kind === "string")
      fields.push({ label: "target_kind", value: spec.target_kind });
    if (typeof spec.target_api_version === "string")
      fields.push({ label: "target_api_version", value: spec.target_api_version });
    if (typeof spec.alias === "string")
      fields.push({ label: "alias", value: spec.alias });
    if (typeof spec.origin === "string")
      fields.push({ label: "origin", value: spec.origin });
    for (const flag of ["is_root", "prompt_target", "flatten_in_context"]) {
      if (spec[flag] != null) {
        fields.push({ label: flag, value: String(spec[flag]) });
      }
    }
    if (spec.storage) {
      fields.push({
        label: "storage",
        value: JSON.stringify(spec.storage, null, 2),
      });
    }
    if (spec.schema) {
      fields.push({
        label: "schema",
        value: JSON.stringify(spec.schema, null, 2),
      });
    }
    if (typeof spec.docs === "string" && spec.docs) {
      fields.push({ label: "docs", value: spec.docs });
    }
    if (fields.length === 0) {
      return [{ kind: "empty", title: `KindDefinition ${doc.name}` }];
    }
    return [{ kind: "fields", title: `KindDefinition ${doc.name}`, fields }];
  }
}

/** Reader for `kinds/<name>/KIND.yaml` — plain YAML, not frontmatter+body. */
export class KindDefinitionReader implements ReaderPort {
  /** Exposed for deferred-generic-registration detection. */
  readonly _marker = "KIND.yaml";

  constructor(private fs: FSLike = nodeFS) {}

  detect(bundle: BundleHandle): boolean { const path = bundle.path ?? "";
    return this.fs.exists(`${path}/KIND.yaml`);
  }

  read(bundle: BundleHandle): Record<string, unknown> { const path = bundle.path ?? "";
    const text = this.fs.readFile(`${path}/KIND.yaml`);
    const doc = yaml.load(text);
    if (doc == null || typeof doc !== "object") {
      throw new Error(`${path}/KIND.yaml did not parse into a mapping`);
    }
    const raw = doc as Record<string, unknown>;
    if (!raw.apiVersion) raw.apiVersion = KIND_DEFINITION_API_VERSION;
    if (!raw.kind) raw.kind = KIND_DEFINITION_KIND;
    const meta = (raw.metadata as Record<string, unknown> | undefined) ?? {};
    if (!meta.name) meta.name = path.split("/").pop() ?? "";
    raw.metadata = meta;
    return raw;
  }
}

/** Writer for KindDefinition bundles — plain YAML. */
export class KindDefinitionWriter implements WriterPort {
  /** Exposed for deferred-generic-registration detection. */
  readonly _kind = KIND_DEFINITION_KIND;

  constructor(private fs: FSLike = nodeFS) {}

  canWrite(raw: Record<string, unknown>): boolean {
    return raw.kind === KIND_DEFINITION_KIND;
  }

  write(bundle: BundleHandle, raw: Record<string, unknown>): void { const path = bundle.path ?? "";
    this.fs.mkdir(path);
    this.fs.writeFile(
      `${path}/KIND.yaml`,
      yaml.dump(raw, { sortKeys: false, flowLevel: -1 }),
    );
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    return [
      {
        relativePath: "KIND.yaml",
        content: yaml.dump(raw, { sortKeys: false, flowLevel: -1 }),
      },
    ];
  }
}

export class KindDefinitionExtension implements Extension {
  readonly name = "kinddef";
  readonly version = "1.0.0";

  constructor(private fs: FSLike = nodeFS) {}

  register(kernel: ExtensionHost): void {
    kernel.kind(new KindDefinitionKind());
    kernel.reader(new KindDefinitionReader(this.fs));
    kernel.writer(new KindDefinitionWriter(this.fs));
  }
}
