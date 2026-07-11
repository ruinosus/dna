/**
 * `loadTools` — the agent-facing tool surface, as data (TS twin of python
 * `dna.load_tools`).
 *
 * The DNA already governs persona, instruction and guardrails declaratively.
 * A **Tool** (record-plane Kind, `helix/kinds/tool.kind.yaml`) moves the last
 * hard-coded piece into the same plane: the `description` the model reads to
 * decide whether to call a tool, and the JSON Schema of its `parameters`.
 * `loadTools` is the consumer one-liner — the twin of `loadPrompts`:
 *
 * ```ts
 * import { loadTools } from "@ruinosus/dna";
 *
 * const tools = await loadTools("open-swe");
 * const surface = tools.get("github-search"); // or throws ToolNotFound
 * surface.description;                          // the text the model reads
 * surface.parameters;                           // the args JSON Schema
 * ```
 *
 * Because a Tool is ONE declarative document, the SAME surface is served to a
 * Python backend (a `@tool` function's `description=`) and this TypeScript
 * frontend (CopilotKit `useCopilotAction`) from one source of truth — the
 * first place the Py↔TS descriptor parity pays off in a real consumer (see
 * `examples/tools_as_data`).
 *
 * TS/Py asymmetry: `loadTools` is async (booting the kernel is async, exactly
 * like `loadPrompts`), but `get(name)` is SYNC — reading a record document
 * needs no async work (unlike `loadPrompts.get`, which awaits composition).
 * A missing tool throws {@link ToolNotFound} (never an empty surface).
 * Overlay-aware: a tenant overlay that overrides a tool's
 * `metadata.description` / `spec.input_schema` is reflected here.
 */
import { quickInstance } from "./bootstrap.js";
import { ToolNotFound } from "./kernel/errors.js";
import type { ManifestInstance } from "./kernel/instance.js";

export { ToolNotFound };

/**
 * The agent-facing surface of a Tool — exactly what a tool-calling model is
 * shown to decide whether, and how, to call it.
 */
export interface ToolSurface {
  /** Natural-language description (`metadata.description`) — the text the
   *  model reads. */
  readonly description: string;
  /** JSON Schema of the arguments (`spec.input_schema`) — what the model
   *  fills in. Empty `{}` when the tool takes no args. */
  readonly parameters: Record<string, unknown>;
}

/** Lazy, cached view `tool name -> ToolSurface` over one scope. */
export class ToolLibrary {
  private readonly cache = new Map<string, ToolSurface>();

  constructor(
    /** The underlying ManifestInstance (drop down for the full surface). */
    readonly mi: ManifestInstance,
  ) {}

  /**
   * Project `name`'s agent-facing surface (cached). Throws {@link ToolNotFound}
   * on a miss.
   */
  get(name: string): ToolSurface {
    const cached = this.cache.get(name);
    if (cached !== undefined) return cached;
    const doc = this.mi._one("Tool", name);
    if (doc === null) {
      throw new ToolNotFound(name, this.mi.scope ?? null, this.names());
    }
    const meta = doc.metadata as Record<string, unknown>;
    const spec = doc.spec as Record<string, unknown>;
    const description = typeof meta.description === "string" ? meta.description : "";
    const rawParams = spec.input_schema;
    const parameters =
      rawParams && typeof rawParams === "object" && !Array.isArray(rawParams)
        ? { ...(rawParams as Record<string, unknown>) }
        : {};
    const surface: ToolSurface = { description, parameters };
    this.cache.set(name, surface);
    return surface;
  }

  /** True when `name` is a Tool document in the scope (no projection). */
  has(name: string): boolean {
    return this.names().includes(name);
  }

  /** Names of every Tool document in the scope, sorted. */
  names(): string[] {
    return this.mi._all("Tool").map((d) => d.name).sort();
  }
}

/**
 * Load the Tool surfaces of `scope` behind a {@link ToolLibrary}.
 *
 * `baseDir` follows the {@link quickInstance} convention — the directory that
 * holds `<scope>/` (the `.dna` scopes root). Omitted → the `DNA_BASE_DIR` env
 * var, then `.dna` in the cwd.
 */
export async function loadTools(
  scope: string,
  baseDir?: string,
): Promise<ToolLibrary> {
  const resolved = baseDir ?? process.env.DNA_BASE_DIR ?? ".dna";
  const mi = await quickInstance(scope, resolved);
  return new ToolLibrary(mi);
}
