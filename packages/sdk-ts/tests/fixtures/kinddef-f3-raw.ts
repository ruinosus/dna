/**
 * Shared fixture for the F3 descriptor tests (spec
 * docs/superpowers/specs/2026-06-10-kinds-descriptor-f3-design.md, D2/D3).
 *
 * 1:1 mirror of RAW_FULL in packages/sdk-py/tests/test_kinddef_f3_fields.py —
 * keep the two in sync (the descriptor format is parity-critical).
 */
import {
  KIND_DEFINITION_API_VERSION,
  KIND_DEFINITION_KIND,
} from "../../src/kernel/models.js";

export const RAW_FULL: Record<string, unknown> = {
  apiVersion: KIND_DEFINITION_API_VERSION,
  kind: KIND_DEFINITION_KIND,
  metadata: { name: "kz" },
  spec: {
    target_api_version: "github.com/ruinosus/dna/sdlc/v1",
    target_kind: "KaizenLike",
    alias: "test-kaizenlike",
    origin: "github.com/ruinosus/dna/sdlc",
    storage: { type: "yaml", container: "kaizens" },
    schema: {
      type: "object",
      required: ["body"],
      properties: {
        body: { type: "string" },
        status: { type: "string", enum: ["observed", "routed"] },
        labels: { type: "array", items: { type: "string" } },
      },
    },
    // — campos F3 —
    plane: "record",
    tenant_scope: "global",
    summary: { status: "observed", work_item: "", labels: [] },
    embed: ["body", "labels"],
    is_runtime_artifact: true,
    prompt_target_priority: 0,
    // is_overlayable=false ≠ default true — pins the wiring (a true here
    // would pass even if parsing dropped the field; C1 review carry-over)
    scope_inheritable: false,
    is_overlayable: false,
    volatile_spec_fields: ["updated_at", "closed_at"],
  },
};

const CORE_KEYS = [
  "target_api_version",
  "target_kind",
  "alias",
  "origin",
  "storage",
  "schema",
] as const;

/** RAW_FULL stripped down to the pre-F3 core fields (defaults path). */
export function minimalRaw(): Record<string, unknown> {
  const spec = RAW_FULL.spec as Record<string, unknown>;
  const minimal: Record<string, unknown> = {};
  for (const k of CORE_KEYS) minimal[k] = spec[k];
  return { ...RAW_FULL, spec: minimal };
}
