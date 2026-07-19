/**
 * MifExtension — the MIF (Memory Interchange Format, mif-spec.dev)
 * passthrough Kind (s-mif-passthrough-kind, feature f-portable-memory).
 *
 * 1:1 parity with Python `dna.extensions.mif`.
 *
 * Registers `mif-spec.dev/v1 · Memory` from a descriptor (F3 — record Kinds
 * are data, not classes). A dedicated extension, not a Kind bolted onto an
 * existing one, following the precedent set by the other two foreign-
 * namespace passthrough Kinds:
 *
 *   - `AgentSkillsExtension` — agentskills.io/v1 · Skill
 *   - `SoulSpecExtension`    — soulspec.org/v1 · Soul
 *
 * Those two ship as hand-written KindPort classes (their bundles carry
 * sidecar files — scripts/references/assets, SOUL.md+IDENTITY.md+
 * HEARTBEAT.md — that need custom Reader/Writer logic). MIF Memory is a
 * single frontmatter+body marker with no sidecars, so it ships as
 * `kinds/memory.kind.yaml` instead (the same choice `DocExtension` made for
 * its own single-marker bundle) — same market-fidelity mechanic (origin =
 * the owner's domain, target_api_version = the owner's namespace, schema =
 * the owner's fields, unchanged), different registration mechanism because
 * the bundle shape is simpler.
 *
 * This is the interchange face only — see `HelixExtension` for Engram (the
 * native memory engine). `dna memory export`/`import` (a later story)
 * projects between the two.
 */

import type { ExtensionHost, Extension } from "../kernel/protocols.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";

export class MifExtension implements Extension {
  name = "mif";
  version = "1.0.0";

  register(kernel: ExtensionHost) {
    // F3: ships as kinds/*.kind.yaml package data (byte-identical Py↔TS
    // mirror), registered through the SAME funnel as per-scope
    // KindDefinitions (plane lint + digest idempotency + builtin conflict
    // marker).
    for (const raw of loadDescriptors(import.meta.url, "mif/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
  }
}
