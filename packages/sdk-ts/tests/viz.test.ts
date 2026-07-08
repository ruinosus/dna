/**
 * Viz module parity tests — verify standalone functions produce identical
 * output to the ManifestInstance methods they were extracted from.
 */

import { describe, expect, test, beforeAll } from "bun:test";
import path from "node:path";
import { quickInstance } from "../src/bootstrap.js";
import {
  dependencyTreeMermaid,
  compositionFlowchartMermaid,
  c4ComponentMermaid,
  erDiagramMermaid,
  erModel,
  mindmapMermaid,
  pieChartMermaid,
  quadrantMermaid,
  timelineMermaid,
  sankeyMermaid,
  kindCatalogMermaid,
  exportDiagramsMd,
} from "../src/viz/mermaid.js";
import { healthReport, impact } from "../src/viz/health.js";
import { matrix, matrixMarkdown } from "../src/viz/matrix.js";
import { asciiTree } from "../src/viz/ascii.js";

const BASE_DIR = path.resolve(import.meta.dir, "../../../scopes/open-swe/.dna");

describe("viz module parity", () => {
  let mi: Awaited<ReturnType<typeof quickInstance>>;
  beforeAll(async () => { mi = await quickInstance("open-swe", BASE_DIR); });

  test("dependencyTreeMermaid", async () => {
    expect(dependencyTreeMermaid(mi)).toBe(mi.dependencyTreeMermaid());
  });

  test("compositionFlowchartMermaid", async () => {
    expect(compositionFlowchartMermaid(mi)).toBe(mi.compositionFlowchartMermaid());
  });

  test("c4ComponentMermaid", async () => {
    expect(c4ComponentMermaid(mi)).toBe(mi.c4ComponentMermaid());
  });

  test("erDiagramMermaid", async () => {
    expect(erDiagramMermaid(mi)).toBe(mi.erDiagramMermaid());
  });

  test("erModel", async () => {
    expect(erModel(mi)).toEqual(mi.erModel());
  });

  test("mindmapMermaid", async () => {
    expect(mindmapMermaid(mi)).toBe(mi.mindmapMermaid());
  });

  test("pieChartMermaid", async () => {
    expect(pieChartMermaid(mi)).toBe(mi.pieChartMermaid());
  });

  test("quadrantMermaid", async () => {
    expect(quadrantMermaid(mi)).toBe(mi.quadrantMermaid());
  });

  test("timelineMermaid", async () => {
    expect(timelineMermaid(mi)).toBe(mi.timelineMermaid());
  });

  test("sankeyMermaid", async () => {
    expect(sankeyMermaid(mi)).toBe(mi.sankeyMermaid());
  });

  test("kindCatalogMermaid", async () => {
    expect(kindCatalogMermaid(mi)).toBe(mi.kindCatalogMermaid());
  });

  test("exportDiagramsMd", async () => {
    // Compare without writing to disk (no path arg)
    const vizResult = exportDiagramsMd(mi);
    const instanceResult = mi.exportDiagramsMd();
    expect(Object.keys(vizResult).sort()).toEqual(Object.keys(instanceResult).sort());
    for (const key of Object.keys(vizResult)) {
      expect(vizResult[key]).toBe(instanceResult[key]);
    }
  });

  test("healthReport", async () => {
    expect(healthReport(mi)).toEqual(mi.health());
  });

  test("impact", async () => {
    // Test with a skill that exists in the fixture
    const skills = mi.documents.filter((d) => d.kind === "Skill");
    if (skills.length > 0) {
      const skill = skills[0];
      expect(impact(mi, skill.kind, skill.name)).toEqual(mi.impact(skill.kind, skill.name));
    }
  });

  test("matrix", async () => {
    expect(matrix(mi)).toEqual(mi.matrix());
  });

  test("matrixMarkdown", async () => {
    expect(matrixMarkdown(mi)).toBe(mi.matrixMarkdown());
  });

  test("asciiTree", async () => {
    expect(asciiTree(mi)).toBe(mi.asciiTree());
  });
});
