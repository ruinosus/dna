// s-portfolio-kinds — portfolio-console data foundation (5 record Kinds).
// TS twin of tests/test_portfolio_kinds.py.
//
// Five record Kinds shipped as the `portfolio` extension (F3 descriptors,
// record plane, TENANTED — per-tenant portfolio data, NOT inheritable), the
// data model of adr-portfolio-project-model:
//   Organization (portfolio-org) · Project (portfolio-project) ·
//   Repo (portfolio-repo) · Membership (portfolio-membership) · Role (portfolio-role)
import { describe, it, expect } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { TenantScope } from "../src/kernel/protocols.js";
import { PortfolioExtension } from "../src/extensions/portfolio.js";

const EXPECTED: Record<string, [string, string]> = {
  Organization: ["portfolio-org", "organizations"],
  Project: ["portfolio-project", "projects"],
  Repo: ["portfolio-repo", "repos"],
  Membership: ["portfolio-membership", "memberships"],
  Role: ["portfolio-role", "roles"],
};

describe("PortfolioExtension Kinds (descriptors)", () => {
  for (const [kindName, [alias, container]] of Object.entries(EXPECTED)) {
    it(`registers ${kindName} from its descriptor`, () => {
      const k = new Kernel();
      k.load(new PortfolioExtension());
      const kp = k.kindPortFor(kindName);
      expect(kp).not.toBeNull();
      expect(kp!.alias).toBe(alias);
      expect((kp as any).plane).toBe("record");
      // TENANTED — per-tenant portfolio data, NOT inheritable.
      expect((kp as any).scope).toBe(TenantScope.TENANTED);
      expect(kp!.storage.container).toBe(container);
      expect((kp as any).__declarative__).toBe(true);
      // strict-schema-lint: every portfolio Kind is a closed schema.
      expect((kp!.schema() as any).additionalProperties).toBe(false);
    });
  }

  it("registers all five portfolio Kinds", () => {
    const k = new Kernel();
    k.load(new PortfolioExtension());
    for (const kindName of Object.keys(EXPECTED)) {
      expect(k.kindPortFor(kindName)).not.toBeNull();
    }
  });

  it("does not collide with the pre-existing tenant Kinds (no i-195 clash)", () => {
    const k = new Kernel();
    k.load(new PortfolioExtension());
    // Loading only the portfolio extension, the tenant Kinds are absent —
    // Organization/Membership are distinct names, never Tenant/TenantMembership.
    expect(k.kindPortFor("Organization")!.alias).toBe("portfolio-org");
    expect(k.kindPortFor("Membership")!.alias).toBe("portfolio-membership");
    expect(k.kindPortFor("Tenant")).toBeNull();
    expect(k.kindPortFor("TenantMembership")).toBeNull();
  });

  it("Project carries the N—N edge; Repo has no project back-ref", () => {
    const k = new Kernel();
    k.load(new PortfolioExtension());
    const projectProps = (k.kindPortFor("Project")!.schema() as any).properties;
    expect(projectProps.repo_refs.type).toBe("array");
    // Project owns board_scope + intel_source_refs (container of board + intel).
    expect(projectProps.board_scope).toBeDefined();
    expect(projectProps.intel_source_refs).toBeDefined();
    const repoProps = (k.kindPortFor("Repo")!.schema() as any).properties;
    // The N—N edge is Project-side only — Repo has no back-ref field.
    expect(Object.keys(repoProps).some((f) => f.includes("project"))).toBe(false);
  });
});
