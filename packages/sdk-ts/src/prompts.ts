/**
 * `loadPrompts` — the one call that collapses the prompt shim (TS twin of
 * python `dna.load_prompts`).
 *
 * With the fail-loud builder (s-dx-build-prompt-fail-loud) and clean output
 * (s-dx-clean-composition-output) in place, a hand-rolled prompt module
 * becomes:
 *
 * ```ts
 * import { loadPrompts } from "@ruinosus/dna";
 *
 * const prompts = await loadPrompts("helpdesk");
 * export const TRIAGE = await prompts.get("triage"); // composed, clean, or throws
 * ```
 *
 * `loadPrompts` boots a filesystem kernel for `scope` and returns a
 * {@link PromptLibrary} — a lazy, cached, read-only view from agent name to
 * composed system prompt. A missing agent throws {@link AgentNotFound} (never a
 * placeholder string); the returned text is already stripped of trailing
 * newlines.
 *
 * TS/Py asymmetry: composition is async in TS, so `get(name)` returns a
 * `Promise<string>` (python's `lib[name]` is sync — same reason `buildPrompt`
 * is `await`ed in TS but not in Python).
 */
import { quickInstance } from "./bootstrap.js";
import type { ManifestInstance } from "./kernel/instance.js";

/** Lazy, cached view `agent name -> composed prompt` over one scope. */
export class PromptLibrary {
  private readonly cache = new Map<string, string>();

  constructor(
    /** The underlying ManifestInstance (drop down for the full surface). */
    readonly mi: ManifestInstance,
  ) {}

  /**
   * Compose `name`'s prompt (cached). Throws {@link AgentNotFound} on a miss;
   * the returned text is clean (no trailing newlines).
   */
  async get(name: string): Promise<string> {
    const cached = this.cache.get(name);
    if (cached !== undefined) return cached;
    // buildPrompt throws AgentNotFound on a miss and returns clean text.
    const text = await this.mi.buildPrompt({ agent: name });
    this.cache.set(name, text);
    return text;
  }

  /** True when `name` is a prompt-target document in the scope (no compose). */
  has(name: string): boolean {
    return this.names().includes(name);
  }

  /** Names of every prompt-target document in the scope, sorted. */
  names(): string[] {
    const kinds = (this.mi as unknown as { _kinds: Map<string, unknown> })._kinds;
    const seen = new Set<string>();
    for (const doc of this.mi.documents) {
      const kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`) as
        | { isPromptTarget?: boolean }
        | undefined;
      if (kp?.isPromptTarget) seen.add(doc.name);
    }
    return [...seen].sort();
  }
}

/**
 * Compose the prompts of `scope` behind a {@link PromptLibrary}.
 *
 * `baseDir` follows the {@link quickInstance} convention — the directory that
 * holds `<scope>/` (the `.dna` scopes root). Omitted → the `DNA_BASE_DIR` env
 * var, then `.dna` in the cwd.
 */
export async function loadPrompts(
  scope: string,
  baseDir?: string,
): Promise<PromptLibrary> {
  const resolved = baseDir ?? process.env.DNA_BASE_DIR ?? ".dna";
  const mi = await quickInstance(scope, resolved);
  return new PromptLibrary(mi);
}
