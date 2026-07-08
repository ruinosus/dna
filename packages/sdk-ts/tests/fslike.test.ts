import { describe, test, expect } from "bun:test";
import type { FSLike } from "../src/kernel/fs";
import { nodeFS, relativePath, createMemoryFS, readTextSafe, collectDir } from "../src/kernel/fs";

describe("FSLike", () => {
  test("nodeFS.exists returns true for existing file", async () => {
    expect(nodeFS.exists("package.json")).toBe(true);
  });

  test("nodeFS.exists returns false for missing file", async () => {
    expect(nodeFS.exists("__nonexistent__")).toBe(false);
  });

  test("nodeFS.readFile reads text content", async () => {
    const content = nodeFS.readFile("package.json");
    expect(content).toContain('"name"');
  });

  test("nodeFS.readDir lists directory entries sorted", async () => {
    const entries = nodeFS.readDir("src");
    expect(entries).toContain("kernel");
    expect(entries).toContain("extensions");
    const sorted = [...entries].sort();
    expect(entries).toEqual(sorted);
  });

  test("nodeFS.isDirectory returns true for dirs", async () => {
    expect(nodeFS.isDirectory("src")).toBe(true);
    expect(nodeFS.isDirectory("package.json")).toBe(false);
  });

  test("nodeFS.isFile returns true for files", async () => {
    expect(nodeFS.isFile("package.json")).toBe(true);
    expect(nodeFS.isFile("src")).toBe(false);
  });

  test("nodeFS.isDirectory returns false for nonexistent", async () => {
    expect(nodeFS.isDirectory("__nope__")).toBe(false);
  });

  test("nodeFS.isFile returns false for nonexistent", async () => {
    expect(nodeFS.isFile("__nope__")).toBe(false);
  });
});

describe("relativePath", () => {
  test("strips root prefix", async () => {
    expect(relativePath("/a/b", "/a/b/c/d.txt")).toBe("c/d.txt");
  });

  test("returns full path if no prefix match", async () => {
    expect(relativePath("/a/b", "/x/y.txt")).toBe("/x/y.txt");
  });
});

describe("createMemoryFS", () => {
  test("round-trips files", async () => {
    const fs = createMemoryFS({ "foo/bar.txt": "hello" });
    expect(fs.exists("foo/bar.txt")).toBe(true);
    expect(fs.readFile("foo/bar.txt")).toBe("hello");
    expect(fs.isFile("foo/bar.txt")).toBe(true);
    expect(fs.isDirectory("foo")).toBe(true);
    expect(fs.readDir("foo")).toEqual(["bar.txt"]);
  });

  test("writeFile creates new entry", async () => {
    const fs = createMemoryFS({});
    fs.writeFile("a/b.txt", "hi");
    expect(fs.readFile("a/b.txt")).toBe("hi");
  });

  test("readFile throws on missing file", async () => {
    const fs = createMemoryFS({});
    expect(() => fs.readFile("nope")).toThrow("ENOENT");
  });

  test("exists returns true for directories", async () => {
    const fs = createMemoryFS({ "a/b/c.txt": "x" });
    expect(fs.exists("a")).toBe(true);
    expect(fs.exists("a/b")).toBe(true);
  });
});

describe("readTextSafe", () => {
  test("returns content for text files", async () => {
    const fs = createMemoryFS({ "file.txt": "hello" });
    expect(readTextSafe(fs, "file.txt")).toBe("hello");
  });

  test("returns null for binary extensions", async () => {
    const fs = createMemoryFS({ "img.png": "bytes" });
    expect(readTextSafe(fs, "img.png")).toBeNull();
  });

  test("returns null for missing files", async () => {
    const fs = createMemoryFS({});
    expect(readTextSafe(fs, "nope.txt")).toBeNull();
  });
});

describe("collectDir", () => {
  test("collects files recursively with relative paths", async () => {
    const fs = createMemoryFS({
      "root/a.txt": "A",
      "root/sub/b.txt": "B",
    });
    const result = collectDir(fs, "root", "root");
    expect(result).toEqual({ "a.txt": "A", "sub/b.txt": "B" });
  });

  test("skips binary files", async () => {
    const fs = createMemoryFS({
      "dir/readme.md": "# Hi",
      "dir/image.png": "bytes",
    });
    const result = collectDir(fs, "dir", "dir");
    expect(result).toEqual({ "readme.md": "# Hi" });
  });
});
