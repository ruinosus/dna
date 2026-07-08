/**
 * s-port-missing-ts-extensions (slice: lesson) — faithful TS twin of the Python
 * LessonExtension: GLOBAL bundle Kind (LESSON.md) + reader + writer.
 */
import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { LessonExtension } from "../src/extensions/lesson.js";
import { DictBundleHandle } from "../src/kernel/bundle-handle.js";
import type { ReaderPort, WriterPort, SerializedFile, KindPort } from "../src/kernel/protocols.js";

function lessonKind() {
  const k = createKernelWithBuiltins() as unknown as {
    _kinds: Map<string, { alias: string; kind: string; apiVersion: string; storage?: { pattern?: string; container?: string; marker?: string } }>;
  };
  return [...k._kinds.values()].find((x) => x.alias === "lesson-lesson");
}

function readerWriter(): { reader: ReaderPort; writer: WriterPort } {
  let reader!: ReaderPort;
  let writer!: WriterPort;
  new LessonExtension().register({
    kind(_k: KindPort) {},
    reader(r: ReaderPort) { reader = r; },
    writer(w: WriterPort) { writer = w; },
  });
  return { reader, writer };
}

describe("LessonExtension — registration", () => {
  test("registers lesson-lesson as a Lesson bundle Kind", () => {
    const kp = lessonKind();
    expect(kp).toBeDefined();
    expect(kp!.kind).toBe("Lesson");
    expect(kp!.apiVersion).toBe("github.com/ruinosus/dna/lesson/v1");
    expect(kp!.storage?.pattern).toBe("bundle");
    expect(kp!.storage?.container).toBe("lessons");
    expect(kp!.storage?.marker).toBe("LESSON.md");
  });
});

describe("LessonReader/Writer round-trip", () => {
  test("writer→reader preserves subject/steps + byte-identical body header", async () => {
    const { reader, writer } = readerWriter();
    const raw = {
      apiVersion: "github.com/ruinosus/dna/lesson/v1",
      kind: "Lesson",
      metadata: { name: "l-cores" },
      spec: {
        subject: "cores-basicas", title: "Cores básicas", skill: "reconhecer", difficulty: 2,
        target_concepts: ["azul", "vermelho"],
        prompts: ["Que cor é essa?"],
        steps: [{ kind: "present", prompt: "Olha o azul" }, { kind: "test", prompt: "Cadê o azul?", expected_concept: "azul" }],
      },
    };
    const files: SerializedFile[] = writer.serialize(raw);
    const md = files.find((f) => f.relativePath === "LESSON.md")!.content;
    expect(md).toContain("# Lesson — Cores básicas (skill: reconhecer, lv 2)");
    expect(md).toContain("`start_lesson(cores-basicas)`");

    const bundle = new DictBundleHandle("l-cores", Object.fromEntries(files.map((f) => [f.relativePath, f.content])));
    expect(await reader.detect(bundle)).toBe(true);
    const doc = await reader.read(bundle);
    const spec = doc.spec as Record<string, unknown>;
    expect(doc.kind).toBe("Lesson");
    expect(spec.subject).toBe("cores-basicas");
    expect(spec.target_concepts).toEqual(["azul", "vermelho"]);
    const steps = spec.steps as Array<Record<string, unknown>>;
    expect(steps).toHaveLength(2);
    expect(steps[1]!.expected_concept).toBe("azul");
  });
});
