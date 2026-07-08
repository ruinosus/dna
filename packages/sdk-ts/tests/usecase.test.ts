/**
 * Tests for the UseCase kind (github.com/ruinosus/dna/v1).
 */
import { describe, test, expect } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { Kernel, HelixExtension, FilesystemSource, FilesystemCache, UseCaseSchema } from "../src/index.js";

describe("UseCaseSchema", () => {
  test("parses full fields", async () => {
    const uc = UseCaseSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "UseCase",
      metadata: { name: "checkout", description: "Customer checks out" },
      spec: {
        primary_actor: "shopper",
        supporting_actors: ["payment-gateway", "inventory"],
        agents: ["order-bot"],
        preconditions: ["cart not empty"],
        main_flow: ["select items", "pay", "confirm"],
        alternate_flows: [{ name: "out of stock", steps: ["notify", "remove"] }],
        postconditions: ["order created"],
        success_criteria: ["payment captured"],
      },
    });
    expect(uc.metadata.name).toBe("checkout");
    expect(uc.spec.primary_actor).toBe("shopper");
    expect(uc.spec.supporting_actors).toEqual(["payment-gateway", "inventory"]);
    expect(uc.spec.main_flow).toEqual(["select items", "pay", "confirm"]);
    expect(uc.spec.alternate_flows[0]!.name).toBe("out of stock");
  });

  test("parses minimal fields", async () => {
    const uc = UseCaseSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "UseCase",
      metadata: { name: "u1" },
      spec: {},
    });
    expect(uc.metadata.name).toBe("u1");
    expect(uc.spec.primary_actor).toBeUndefined();
    expect(uc.spec.main_flow).toEqual([]);
  });
});

describe("UseCase kind registration", () => {
  test("HelixExtension registers UseCase kind", async () => {
    const k = new Kernel();
    k.load(new HelixExtension());
    // @ts-expect-error — _kinds is internal
    const kinds = k._kinds as Map<string, unknown>;
    const found = Array.from(kinds.keys()).some((key) =>
      String(key).includes("UseCase"),
    );
    expect(found).toBe(true);
  });
});

describe("UseCase filesystem load", () => {
  test("loads usecase yaml from manifest scope", async () => {
    const base = mkdtempSync(join(tmpdir(), "dna-uc-"));
    const scope = join(base, "mod");
    mkdirSync(scope, { recursive: true });
    writeFileSync(
      join(scope, "manifest.yaml"),
      "apiVersion: github.com/ruinosus/dna/v1\nkind: Module\nmetadata:\n  name: mod\nspec: {}\n",
    );
    const ucDir = join(scope, "use_cases");
    mkdirSync(ucDir, { recursive: true });
    writeFileSync(
      join(ucDir, "checkout.yaml"),
      [
        "apiVersion: github.com/ruinosus/dna/v1",
        "kind: UseCase",
        "metadata:",
        "  name: checkout",
        "spec:",
        "  primary_actor: shopper",
        "  main_flow:",
        "    - select",
        "    - pay",
        "",
      ].join("\n"),
    );

    const k = new Kernel();
    k.source(new FilesystemSource(base));
    k.cache(new FilesystemCache(base));
    k.load(new HelixExtension());

    const mi = await k.instance("mod");
    const ucs = mi.documents.filter((d) => d.kind === "UseCase");
    expect(ucs.length).toBe(1);
    expect(ucs[0]!.name).toBe("checkout");
    expect(ucs[0]!.spec.primary_actor).toBe("shopper");
    expect(ucs[0]!.spec.main_flow).toEqual(["select", "pay"]);
  });
});
