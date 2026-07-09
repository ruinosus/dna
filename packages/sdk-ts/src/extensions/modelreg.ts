/**
 * ModelRegExtension — per-model capability/limit registry.
 *
 * 1:1 parity with Python `dna.extensions.modelreg`.
 *
 * Registers 1 Kind, from a descriptor (F3 — record Kinds are data, not
 * classes):
 *
 *   - ModelProfile (`modelreg-model-profile`) — hard limits
 *     (`instruction_token_cap`, `context_window`, `tools_cap`) +
 *     modalities + cost of one LLM model, as a first-class GLOBAL Kind so
 *     limits are project data, not implicit knowledge. Ported from the
 *     internal SDK's model registry, motivated by a real outage: a
 *     17269-token voice persona silently exceeded the realtime model's
 *     16384-token session-instructions cap because the cap lived in
 *     nobody's code.
 *
 * CONTRACT — never hardcode token caps. The single source of truth for a
 * model's limits is its ModelProfile doc (`_lib` scope,
 * `model-profiles/<model_id>.yaml`), resolved via
 * `kernel.modelProfile(idOrAlias)`. The prompt-budget write guard
 * (`src/extensions/helix/write-guards.ts` + Python twin) reads the cap
 * from there — a token-cap literal in code is a bug.
 */

import type { ExtensionHost, Extension } from "../kernel/protocols.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";

export class ModelRegExtension implements Extension {
  name = "modelreg";
  version = "1.0.0";

  register(kernel: ExtensionHost) {
    // F3: ModelProfile ships as kinds/model-profile.kind.yaml package data
    // (byte-identical Py↔TS mirror), registered through the SAME funnel as
    // per-scope KindDefinitions (plane lint + digest idempotency + builtin
    // conflict marker).
    for (const raw of loadDescriptors(import.meta.url, "modelreg/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
  }
}
