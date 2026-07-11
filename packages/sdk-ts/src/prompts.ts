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
import { anchorScopesRoot } from "./package-scope.js";
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

/** Options for {@link loadPrompts}. */
export interface LoadPromptsOptions {
  /**
   * The directory that holds `<scope>/` (the `.dna` scopes root), following
   * the {@link quickInstance} convention.
   */
  baseDir?: string;
  /**
   * A package specifier whose package data embeds the scope. When given, the
   * scope is resolved from INSIDE the installed package (via its
   * `package.json`), so it TRAVELS with the app — an `npm`/`bun install`
   * carries the package data into the published tarball and into a Docker
   * image, and resolution works identically from a source checkout, an
   * installed dependency, or a container whose CWD is not the repo (no
   * `path.resolve(__dirname, "../..")` navigation, no manual `COPY .dna`).
   * A scope embedded via `anchor` is READ-ONLY. See the guide "Shipping a
   * scope with your app".
   */
  anchor?: string;
}

/**
 * Compose the prompts of `scope` behind a {@link PromptLibrary}.
 *
 * Precedence for the scopes-root (first one set wins):
 *
 *   `opts.baseDir`  >  `$DNA_BASE_DIR`  >  `opts.anchor` (package data)  >  `.dna`
 *
 * The legacy positional-string form (`loadPrompts(scope, "/path/.dna")`) is
 * still accepted for back-compat and is treated as `baseDir`.
 */
export async function loadPrompts(
  scope: string,
  opts?: string | LoadPromptsOptions,
): Promise<PromptLibrary> {
  const o: LoadPromptsOptions =
    typeof opts === "string" ? { baseDir: opts } : opts ?? {};
  const mi = await quickInstance(scope, resolveScopeBaseDir(o));
  return new PromptLibrary(mi);
}

/** Pick the `.dna` scopes-root by the documented precedence. */
function resolveScopeBaseDir(o: LoadPromptsOptions): string {
  if (o.baseDir !== undefined) return o.baseDir;
  const env = process.env.DNA_BASE_DIR;
  if (env) return env;
  if (o.anchor !== undefined) return anchorScopesRoot(o.anchor);
  return ".dna";
}
