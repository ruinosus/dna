/**
 * LessonExtension — declarative educational activity Kind (TS twin).
 *
 * 1:1 parity with python/dna/extensions/lesson/__init__.py.
 * A Lesson is a short structured activity a child-companion agent runs. Bundle
 * storage: LESSON.md (frontmatter = spec). GLOBAL — the catalog is per-scope.
 */
import yaml from "js-yaml";

import type { ExtensionHost, Extension, ReaderPort, SerializedFile, WriterPort } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD, TenantScope } from "../kernel/protocols.js";
import type { BundleHandle } from "../kernel/bundle-handle.js";
import type { Document } from "../kernel/document.js";
import { writeEntriesToHandle } from "../kernel/writer-helpers.js";

const API_VERSION = "github.com/ruinosus/dna/lesson/v1";

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

class LessonKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "Lesson";
  readonly alias = "lesson-lesson";
  readonly origin = "github.com/ruinosus/dna/lesson";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  // GLOBAL — the catalog is per-scope, not per-tenant.
  readonly scope = TenantScope.GLOBAL;
  readonly storage = SD.bundle("lessons", "LESSON.md");
  readonly graphStyle = { fill: "#F59E0B", stroke: "#D97706", textColor: "#fff" };
  readonly asciiIcon = "📚";
  readonly displayLabel = "Lessons";
  readonly docs =
    "A Lesson is a short, structured educational activity the agent can run with " +
    "a pre-reader child. Declarative — content is in YAML, edited by caregivers " +
    "in Studio, no code review. Tools: start_lesson(subject) picks one; " +
    "record_attempt(concept, correct) tracks performance into Engram docs.";

  dependencies() { return null; }

  schema() {
    return {
      type: "object",
      required: ["subject", "target_concepts", "prompts"],
      additionalProperties: true,
      properties: {
        subject: { type: "string", description: "Short concept group ('cores-basicas', 'animais-conhecidos', 'rotina-comer')." },
        title: { type: "string", description: "Display title in PT-BR ('Cores básicas', 'Animais que você conhece')." },
        skill: {
          type: "string",
          enum: ["reconhecer", "identificar", "parear", "repetir", "associar", "contar", "ordenar"],
          default: "reconhecer",
        },
        modality: {
          type: "array",
          items: { type: "string", enum: ["visual", "audio", "interativo"] },
          default: ["visual", "audio", "interativo"],
        },
        difficulty: { type: "integer", minimum: 1, maximum: 5, default: 1 },
        duration_seconds_max: { type: "integer", default: 120, description: "Cap to respect TDAH attention budget. 60-180 typical for ages 8-12." },
        target_concepts: { type: "array", items: { type: "string" }, description: "Concept slugs that match Pictogram.spec.concept (azul, vermelho, etc)." },
        prompts: { type: "array", items: { type: "string" }, description: "DEPRECATED v2: legacy flat list of Lumi-spoken prompts. Use `steps` instead. Kept for back-compat with v1 seeds — if `steps` is missing, runtime synthesizes a 1-step-per-prompt timeline." },
        steps: {
          type: "array",
          description: "Ordered list of LessonStep objects. Agent walks them in order, listening to Mateus between each, calling show_pictogram for visual anchor and record_attempt on test steps.",
          items: {
            type: "object",
            required: ["kind", "prompt"],
            additionalProperties: true,
            properties: {
              kind: {
                type: "string",
                enum: ["present", "repeat", "test", "celebrate", "review"],
                description: "present = introduce concept; repeat = ask Mateus to repeat/imitate; test = ask Mateus to identify (calls record_attempt); celebrate = positive reinforcement; review = recap before next step.",
              },
              prompt: { type: "string", description: "Short PT-BR phrase Lumi speaks at this step. ≤6 words ideal." },
              expected_concept: { type: "string", description: "Optional Pictogram concept slug to show via show_pictogram(). Required on `test` steps so record_attempt knows the target." },
              on_correct: { type: "string", description: "Lumi's reaction on success. Default: 'Isso!' for test, advance otherwise." },
              on_incorrect: { type: "string", description: "Lumi's reaction on failure. Default: gentle re-prompt + show pictogram again." },
              hint_ladder: { type: "array", items: { type: "string" }, description: "Optional 1-3 progressively stronger hints if Mateus errs (silhouette → color → sound)." },
            },
          },
        },
        reinforcement: { type: "string", enum: ["celebrate", "gentle", "neutral"], default: "celebrate", description: "How Lumi reacts to correct answers. 'celebrate' = set_pose celebrating + warm phrase." },
        on_no_response: { type: "string", default: "Vamos tentar outra coisa?", description: "Phrase Lumi says after ~30s of no input. Always gentle, never pressuring." },
        success_criteria: { type: "object", additionalProperties: true, description: "How to mark this lesson 'done well'. Example: {matches: 3, duration_min: 30}." },
        approved_by: { type: "array", items: { type: "string" }, default: [] },
        labels: { type: "array", items: { type: "string" }, default: [] },
      },
    };
  }


  describe(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const title = (spec.title as string) || (spec.subject as string) || "?";
    const diff = (spec.difficulty as number) ?? 1;
    return `${title} (lv ${diff})`;
  }

  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const concepts = (spec.target_concepts as unknown[]) ?? [];
    const steps = (spec.steps as unknown[]) ?? [];
    return {
      subject: (spec.subject as string) ?? "",
      skill: (spec.skill as string) ?? "",
      difficulty: (spec.difficulty as number) ?? 1,
      concept_count: concepts.length,
      step_count: steps.length,
      format: steps.length ? "multi-step" : "legacy-prompts",
    };
  }

}

class LessonReader implements ReaderPort {
  async detect(bundle: BundleHandle): Promise<boolean> {
    return bundle.exists("LESSON.md");
  }

  async read(bundle: BundleHandle): Promise<Record<string, unknown>> {
    const text = await bundle.readText("LESSON.md");
    const { fm } = parseFrontmatter(text);
    if (fm && typeof fm === "object" && "spec" in fm && fm["spec"] && typeof fm["spec"] === "object") {
      const metadata = (fm["metadata"] as Record<string, unknown>) ?? {};
      if (!("name" in metadata)) metadata["name"] = bundle.name;
      return {
        apiVersion: (fm["apiVersion"] as string) ?? API_VERSION,
        kind: (fm["kind"] as string) ?? "Lesson",
        metadata,
        spec: fm["spec"] as Record<string, unknown>,
      };
    }
    return {
      apiVersion: API_VERSION,
      kind: "Lesson",
      metadata: { name: bundle.name },
      spec: fm,
    };
  }
}

class LessonWriter implements WriterPort {
  canWrite(raw: Record<string, unknown>): boolean {
    return raw["kind"] === "Lesson";
  }

  serialize(raw: Record<string, unknown>): SerializedFile[] {
    const spec = (raw["spec"] ?? {}) as Record<string, unknown>;
    const meta = { ...((raw["metadata"] ?? {}) as Record<string, unknown>) };
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
      apiVersion: (raw["apiVersion"] as string) ?? API_VERSION,
      kind: (raw["kind"] as string) ?? "Lesson",
      metadata: cleanMeta,
      spec: cleanSpec,
    };
    const fmYaml = yaml.dump(envelope, { lineWidth: 100, noRefs: true, sortKeys: false }).trimEnd();
    const title = (cleanSpec["title"] as string) || (cleanSpec["subject"] as string) || "?";
    const skill = (cleanSpec["skill"] as string) ?? "reconhecer";
    const diff = (cleanSpec["difficulty"] as number) ?? 1;
    const subject = (cleanSpec["subject"] as string) ?? "?";
    const body =
      `# Lesson — ${title} (skill: ${skill}, lv ${diff})\n\n` +
      `Curated educational activity for child-companion agents. Run via ` +
      `\`start_lesson(${subject})\`.\n`;
    return [{ relativePath: "LESSON.md", content: `---\n${fmYaml}\n---\n\n${body}` }];
  }

  async write(bundle: BundleHandle, raw: Record<string, unknown>): Promise<void> {
    await writeEntriesToHandle(bundle, this.serialize(raw));
  }
}

export class LessonExtension implements Extension {
  name = "lesson";
  version = "1.0.0";
  register(kernel: ExtensionHost) {
    kernel.kind(new LessonKind());
    kernel.reader(new LessonReader());
    kernel.writer(new LessonWriter());
  }
}
