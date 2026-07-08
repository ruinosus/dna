import { describe, test, expect } from "bun:test";
import { Resource } from "../src/kernel/resource.js";
import type { KindLike } from "../src/kernel/resource.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Minimal KindLike stub for Agent-style dep_filters. */
function agentKind(): KindLike {
  return {
    apiVersion: "github.com/ruinosus/dna/v1",
    kind: "Agent",
    alias: "helix-agent",
    depFilters: () => ({
      soul: "soulspec-soul",
      skills: "agentskills-skill",
      guardrails: "guardrails-guardrail",
    }),
  };
}

/** KindLike that returns null dep_filters (e.g. a Skill). */
function leafKind(): KindLike {
  return {
    apiVersion: "agentskills.io/v1",
    kind: "Skill",
    alias: "agentskills-skill",
    depFilters: () => null,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Resource", () => {
  describe("fromRaw constructs with correct fields", () => {
    test("basic fields from raw dict", async () => {
      const raw = {
        apiVersion: "github.com/ruinosus/dna/v1",
        kind: "Agent",
        metadata: { name: "brad", description: "test agent" },
        spec: { instruction: "Be helpful", soul: "brad" },
      };
      const res = Resource.fromRaw(raw, undefined, "local");

      expect(res.apiVersion).toBe("github.com/ruinosus/dna/v1");
      expect(res.kind).toBe("Agent");
      expect(res.name).toBe("brad");
      expect(res.origin).toBe("local");
      expect(res.raw).toBe(raw);
      expect(res.typed).toBeNull();
      expect(res.kindRef).toBeNull();
    });

    test("kindRef is set when provided", async () => {
      const kp = agentKind();
      const res = Resource.fromRaw(
        { apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", metadata: { name: "x" }, spec: {} },
        undefined,
        "local",
        kp,
      );
      expect(res.kindRef).toBe(kp);
    });

    test("defaults for missing fields", async () => {
      const res = Resource.fromRaw({});
      expect(res.apiVersion).toBe("");
      expect(res.kind).toBe("");
      expect(res.name).toBe("");
      expect(res.origin).toBe("local");
      expect(res.spec).toEqual({});
      expect(res.metadata).toEqual({});
    });
  });

  describe("spec prefers typed over raw", () => {
    test("spec from raw dict when no typed", async () => {
      const res = Resource.fromRaw({
        apiVersion: "github.com/ruinosus/dna/v1",
        kind: "Agent",
        metadata: { name: "brad" },
        spec: { instruction: "Be helpful", soul: "brad" },
      });
      expect(res.spec.instruction).toBe("Be helpful");
      expect(res.spec.soul).toBe("brad");
    });

    test("spec from typed model takes precedence", async () => {
      const raw = {
        apiVersion: "github.com/ruinosus/dna/v1",
        kind: "Agent",
        metadata: { name: "brad" },
        spec: { instruction: "raw value" },
      };
      const typed = {
        metadata: { name: "brad" },
        spec: { instruction: "typed value", skills: ["greet"] },
      };
      const res = Resource.fromRaw(raw, typed);
      expect(res.spec.instruction).toBe("typed value");
      expect(res.spec.skills).toEqual(["greet"]);
    });

    test("metadata from typed model takes precedence", async () => {
      const raw = {
        apiVersion: "v1",
        kind: "X",
        metadata: { name: "raw-name" },
        spec: {},
      };
      const typed = {
        metadata: { name: "typed-name", description: "from typed" },
        spec: {},
      };
      const res = Resource.fromRaw(raw, typed);
      expect(res.metadata.name).toBe("typed-name");
      expect(res.metadata.description).toBe("from typed");
    });
  });

  describe("deps returns empty when no kindRef", () => {
    test("no kindRef → empty deps", async () => {
      const res = Resource.fromRaw({
        apiVersion: "github.com/ruinosus/dna/v1",
        kind: "Agent",
        metadata: { name: "brad" },
        spec: { soul: "brad", skills: ["greet"] },
      });
      expect(res.deps()).toEqual([]);
    });

    test("kindRef with null depFilters → empty deps", async () => {
      const res = Resource.fromRaw(
        {
          apiVersion: "agentskills.io/v1",
          kind: "Skill",
          metadata: { name: "greet" },
          spec: { instruction: "hello" },
        },
        undefined,
        "local",
        leafKind(),
      );
      expect(res.deps()).toEqual([]);
    });
  });

  describe("deps resolves from kindRef", () => {
    test("array values produce multi-name deps", async () => {
      const res = Resource.fromRaw(
        {
          apiVersion: "github.com/ruinosus/dna/v1",
          kind: "Agent",
          metadata: { name: "brad" },
          spec: { skills: ["greet", "search"], guardrails: ["safety"] },
        },
        undefined,
        "local",
        agentKind(),
      );
      const deps = res.deps();
      expect(deps).toHaveLength(2);

      const skillsDep = deps.find((d) => d.field === "skills");
      expect(skillsDep).toBeDefined();
      expect(skillsDep!.targetAlias).toBe("agentskills-skill");
      expect(skillsDep!.names).toEqual(["greet", "search"]);

      const guardrailDep = deps.find((d) => d.field === "guardrails");
      expect(guardrailDep).toBeDefined();
      expect(guardrailDep!.targetAlias).toBe("guardrails-guardrail");
      expect(guardrailDep!.names).toEqual(["safety"]);
    });

    test("scalar value produces single-name dep", async () => {
      const res = Resource.fromRaw(
        {
          apiVersion: "github.com/ruinosus/dna/v1",
          kind: "Agent",
          metadata: { name: "brad" },
          spec: { soul: "brad" },
        },
        undefined,
        "local",
        agentKind(),
      );
      const deps = res.deps();
      expect(deps).toHaveLength(1);
      expect(deps[0].field).toBe("soul");
      expect(deps[0].targetAlias).toBe("soulspec-soul");
      expect(deps[0].names).toEqual(["brad"]);
    });

    test("empty arrays and missing fields are skipped", async () => {
      const res = Resource.fromRaw(
        {
          apiVersion: "github.com/ruinosus/dna/v1",
          kind: "Agent",
          metadata: { name: "brad" },
          spec: { skills: [], soul: "" },
        },
        undefined,
        "local",
        agentKind(),
      );
      expect(res.deps()).toEqual([]);
    });

    test("mixed scalar and array deps together", async () => {
      const res = Resource.fromRaw(
        {
          apiVersion: "github.com/ruinosus/dna/v1",
          kind: "Agent",
          metadata: { name: "brad" },
          spec: { soul: "brad", skills: ["greet"], guardrails: ["safety", "compliance"] },
        },
        undefined,
        "local",
        agentKind(),
      );
      const deps = res.deps();
      expect(deps).toHaveLength(3);

      const soulDep = deps.find((d) => d.field === "soul");
      expect(soulDep!.names).toEqual(["brad"]);

      const skillsDep = deps.find((d) => d.field === "skills");
      expect(skillsDep!.names).toEqual(["greet"]);

      const guardrailDep = deps.find((d) => d.field === "guardrails");
      expect(guardrailDep!.names).toEqual(["safety", "compliance"]);
    });
  });

  describe("toString", () => {
    test("returns readable format", async () => {
      const res = Resource.fromRaw({
        apiVersion: "github.com/ruinosus/dna/v1",
        kind: "Agent",
        metadata: { name: "brad" },
        spec: {},
      });
      expect(res.toString()).toBe("Resource(github.com/ruinosus/dna/v1/Agent: brad)");
    });

    test("handles empty fields gracefully", async () => {
      const res = Resource.fromRaw({});
      expect(res.toString()).toBe("Resource(/: )");
    });
  });
});
