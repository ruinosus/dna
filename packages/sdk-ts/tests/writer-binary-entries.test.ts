/**
 * L3 (s-writer-binary-entries 2026-05-25) — TS twin of
 * tests/test_writer_binary_entries.py.
 */
import { describe, expect, test } from "bun:test";

import {
  popSourceFilesAsEntries,
  writeEntriesToHandle,
} from "../src/kernel/writer-helpers.js";
import { DictBundleHandle } from "../src/kernel/bundle-handle.js";

describe("popSourceFilesAsEntries", () => {
  test("handles text payloads", () => {
    const spec: Record<string, unknown> = {
      foo: "bar",
      source_files: { "a.html": "<p>hi</p>" },
    };
    const out = popSourceFilesAsEntries(spec, "HtmlArtifact");
    expect("source_files" in spec).toBe(false);
    expect(spec).toEqual({ foo: "bar" });
    expect(out).toEqual([{ relativePath: "a.html", content: "<p>hi</p>" }]);
  });

  test("handles bytes payloads (Uint8Array)", () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
    const spec: Record<string, unknown> = { source_files: { "thumb.png": png } };
    const out = popSourceFilesAsEntries(spec, "ImagePrompt");
    expect(out).toEqual([{ relativePath: "thumb.png", contentBytes: png }]);
  });

  test("handles mixed text + bytes", () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
    const spec: Record<string, unknown> = {
      source_files: { "page.html": "<html></html>", "img.png": png },
    };
    const out = popSourceFilesAsEntries(spec, "HtmlArtifact");
    const byPath = Object.fromEntries(out.map((e) => [e.relativePath, e]));
    expect(byPath["page.html"]!.content).toBe("<html></html>");
    expect(byPath["img.png"]!.contentBytes).toEqual(png);
  });

  test("missing or empty returns empty list", () => {
    expect(popSourceFilesAsEntries({}, "X")).toEqual([]);
    expect(popSourceFilesAsEntries({ source_files: null }, "X")).toEqual([]);
    expect(popSourceFilesAsEntries({ source_files: {} }, "X")).toEqual([]);
  });

  test("rejects invalid payload type", () => {
    expect(() =>
      popSourceFilesAsEntries({ source_files: { x: 123 } }, "HtmlArtifact"),
    ).toThrow(TypeError);
  });

  test("rejects non-object source_files", () => {
    expect(() =>
      popSourceFilesAsEntries({ source_files: ["a"] }, "HtmlArtifact"),
    ).toThrow(TypeError);
  });
});

describe("writeEntriesToHandle", () => {
  test("dispatches text and bytes to BundleHandle correctly", async () => {
    const handle = new DictBundleHandle("test", {});
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
    await writeEntriesToHandle(handle, [
      { relativePath: "PROMPT.md", content: "frontmatter" },
      { relativePath: "output.png", contentBytes: png },
    ]);
    expect(await handle.readText("PROMPT.md")).toBe("frontmatter");
    expect(await handle.readBytes("output.png")).toEqual(png);
  });
});
