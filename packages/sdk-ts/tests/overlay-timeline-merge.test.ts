/**
 * Cross-overlay timeline merging — TS twin of
 * python/tests/test_overlay_timeline_merge.py.
 *
 * ADR docs/superpowers/specs/2026-05-10-tenant-overlay-timeline-adr.md.
 * `spec.timeline[]` is append-only — events recorded against an overlay
 * concat with base events (sorted newest-first), not replace them. Even
 * under LOCKED policy.
 */

import { describe, test, expect } from "bun:test";
import {
  DefaultLayerResolver,
  mergeTimelineArrays,
  type LayerSource,
} from "../src/kernel/layer-resolver.js";
import { LayerPolicy } from "../src/kernel/protocols.js";

class FakeSource implements LayerSource {
  constructor(private layers: Record<string, Record<string, unknown>[]>) {}
  loadLayer(_scope: string, layerId: string, value: string) {
    return this.layers[`${layerId}=${value}`] ?? [];
  }
}

const ev = (
  at: string,
  type: string,
  extra: Record<string, unknown> = {},
): Record<string, unknown> => ({ at, actor: "claude-code", type, ...extra });

const story = (
  name = "s-foo",
  opts: { timeline?: Record<string, unknown>[]; extra?: Record<string, unknown> } = {},
): Record<string, unknown> => {
  const spec: Record<string, unknown> = {
    description: "x",
    status: "todo",
    feature: "f-bar",
  };
  if (opts.timeline !== undefined) spec.timeline = opts.timeline;
  if (opts.extra) Object.assign(spec, opts.extra);
  return {
    apiVersion: "github.com/ruinosus/dna/sdlc/v1",
    kind: "Story",
    metadata: { name },
    spec,
  };
};

// ---------------------------------------------------------------------------
// mergeTimelineArrays helper
// ---------------------------------------------------------------------------

describe("mergeTimelineArrays", () => {
  test("returns null when neither side has timeline", () => {
    expect(mergeTimelineArrays({}, {})).toBeNull();
    expect(mergeTimelineArrays({ x: 1 }, { y: 2 })).toBeNull();
  });

  test("concats sorted descending by at", () => {
    const merged = mergeTimelineArrays(
      { timeline: [ev("2026-05-09T10:00:00Z", "groom")] },
      { timeline: [ev("2026-05-10T12:00:00Z", "comment")] },
    );
    expect(merged).not.toBeNull();
    expect(merged!.map((e) => e.at)).toEqual([
      "2026-05-10T12:00:00Z",
      "2026-05-09T10:00:00Z",
    ]);
  });

  test("dedups identical events", () => {
    const e = ev("2026-05-10T10:00:00Z", "status_change", {
      from: "todo",
      to: "done",
    });
    const merged = mergeTimelineArrays(
      { timeline: [e] },
      { timeline: [{ ...e }] },
    );
    expect(merged).not.toBeNull();
    expect(merged!.length).toBe(1);
  });

  test("passes through when only one side has timeline", () => {
    const events = [ev("2026-05-10T10:00:00Z", "groom")];
    expect(mergeTimelineArrays({}, { timeline: events })!.length).toBe(1);
    expect(mergeTimelineArrays({ timeline: events }, {})!.length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// OPEN policy
// ---------------------------------------------------------------------------

describe("OPEN policy timeline merging", () => {
  test("timeline concats base and overlay", () => {
    const r = new DefaultLayerResolver();
    const base = story("s-foo", {
      timeline: [ev("2026-05-09T10:00:00Z", "groom")],
    });
    const overlay = {
      kind: "Story",
      metadata: { name: "s-foo" },
      spec: {
        timeline: [ev("2026-05-10T12:00:00Z", "comment", { actor: "bob" })],
      },
    };
    const out = r.resolve(
      [base],
      { tenant: "acme" },
      new FakeSource({ "tenant=acme": [overlay] }),
      "scope",
      {},
    );
    const tl = (out[0].spec as Record<string, unknown>).timeline as Record<
      string,
      unknown
    >[];
    expect(tl.map((e) => e.at)).toEqual([
      "2026-05-10T12:00:00Z",
      "2026-05-09T10:00:00Z",
    ]);
  });

  test("timeline-only overlay does NOT stamp has_overlay", () => {
    // Timeline is append-only metadata, not a per-field override —
    // an overlay that adds only timeline events shouldn't make
    // Studio show the "this story is forked" banner.
    const r = new DefaultLayerResolver();
    const base = story("s-foo", {
      timeline: [ev("2026-05-09T10:00:00Z", "groom")],
    });
    const overlay = {
      kind: "Story",
      metadata: { name: "s-foo" },
      spec: { timeline: [ev("2026-05-10T10:00:00Z", "comment")] },
    };
    const out = r.resolve(
      [base],
      { tenant: "acme" },
      new FakeSource({ "tenant=acme": [overlay] }),
      "scope",
      {},
    );
    const md = out[0].metadata as Record<string, unknown>;
    expect(md.has_overlay).not.toBe(true);
    expect(md.overlay_fields ?? []).toEqual([]);
  });

  test("timeline excluded from overlay_fields when present alongside overrides", () => {
    const r = new DefaultLayerResolver();
    const base = story("s-foo");
    const overlay = {
      kind: "Story",
      metadata: { name: "s-foo" },
      spec: {
        status: "in-progress",
        timeline: [ev("2026-05-10T10:00:00Z", "status_change")],
      },
    };
    const out = r.resolve(
      [base],
      { tenant: "acme" },
      new FakeSource({ "tenant=acme": [overlay] }),
      "scope",
      {},
    );
    const md = out[0].metadata as Record<string, unknown>;
    expect(md.has_overlay).toBe(true);
    expect(md.overlay_fields).toEqual(["status"]);
  });
});

// ---------------------------------------------------------------------------
// RESTRICTED policy
// ---------------------------------------------------------------------------

describe("RESTRICTED policy timeline merging", () => {
  test("timeline merges under restricted", () => {
    const r = new DefaultLayerResolver();
    const base = story("s-foo", {
      timeline: [ev("2026-05-09T10:00:00Z", "groom")],
    });
    const overlay = {
      kind: "Story",
      metadata: { name: "s-foo" },
      spec: { timeline: [ev("2026-05-10T12:00:00Z", "comment")] },
    };
    const out = r.resolve(
      [base],
      { tenant: "acme" },
      new FakeSource({ "tenant=acme": [overlay] }),
      "scope",
      { Story: LayerPolicy.RESTRICTED },
    );
    const tl = (out[0].spec as Record<string, unknown>).timeline as unknown[];
    expect(tl.length).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// LOCKED policy
// ---------------------------------------------------------------------------

describe("LOCKED policy timeline merging", () => {
  test("timeline-only overlay still appends under LOCKED", () => {
    const r = new DefaultLayerResolver();
    const base = story("s-foo", {
      timeline: [ev("2026-05-09T10:00:00Z", "groom")],
    });
    const overlay = {
      kind: "Story",
      metadata: { name: "s-foo" },
      spec: { timeline: [ev("2026-05-10T12:00:00Z", "comment")] },
    };
    const out = r.resolve(
      [base],
      { tenant: "acme" },
      new FakeSource({ "tenant=acme": [overlay] }),
      "scope",
      { Story: LayerPolicy.LOCKED },
    );
    const tl = (out[0].spec as Record<string, unknown>).timeline as unknown[];
    expect(tl.length).toBe(2);
  });

  test("LOCKED still blocks non-timeline field changes", () => {
    const r = new DefaultLayerResolver();
    const base = story("s-foo");
    const overlay = {
      kind: "Story",
      metadata: { name: "s-foo" },
      spec: { status: "done" }, // pure override attempt, no timeline
    };
    const out = r.resolve(
      [base],
      { tenant: "acme" },
      new FakeSource({ "tenant=acme": [overlay] }),
      "scope",
      { Story: LayerPolicy.LOCKED },
    );
    expect((out[0].spec as Record<string, unknown>).status).toBe("todo");
  });
});
