/**
 * `emit` — the vendor-neutral EMITTER layer (TS twin of python `dna.emit`).
 *
 * DNA authors an agent ONCE — a persona (Soul), an instruction (Agent), wired
 * Guardrails, and Tools — as declarative Kinds. This module materializes that
 * one neutral definition into the NATIVE artifact each runtime framework
 * consumes. The concrete first step of "DNA as the Terraform of agents": author
 * once, emit per runtime, swap runtimes without rewriting the agent.
 *
 * The {@link EmitterPort} is a **first-class DNA port** — a documented contract
 * on the same footing as the kernel's five ports, one layer OUT: the kernel
 * *composes* the neutral agent; the EmitterPort *materializes* it for a runtime.
 * See the `How to write an emitter` guide (`docs/guides/writing-an-emitter.md`).
 *
 * The contract has two surfaces: `buildEmitContext(mi, agent)` (the kernel-facing
 * half — compose + project to the neutral {@link EmitContext}) and
 * `EmitterPort.emit(ctx)` (the runtime-facing half a target implements — PURE,
 * no kernel I/O). Its **central invariant**: the composed `instructions` in the
 * emitted artifact is byte-equal to `mi.buildPrompt({agent})`. That invariant is
 * checkable and *inheritable* via {@link EmitterPort.extractInstructions} — one
 * generic test runs it over EVERY registered target.
 *
 * Two flavors satisfy the same port: **config-declarative** (a runtime with a
 * published declarative schema — agent-framework / bedrock / vertex) and
 * **scaffold-code** (a code-first runtime — see `scaffold.ts`; the `openai-agents`
 * target is the reference).
 *
 * Parity: the pure de-para (`toPromptAgent` in `agentFramework.ts`) mirrors the
 * Python emitter field-for-field; the serialization (js-yaml vs PyYAML) is a
 * rendering detail, so the parity contract is the emitted OBJECT/behavior, not
 * the bytes.
 *
 * Shape: {@link EmitContext} (runtime-agnostic view of a composed agent) →
 * {@link EmitterPort} (a target) → {@link EmitResult} (artifact + honest
 * `losses`). {@link registerEmitter}/{@link getEmitter}/{@link availableTargets}
 * are the pluggable registry — a new target is a class + one register call.
 */
import type { ManifestInstance } from "../kernel/instance.js";
import { ToolLibrary } from "../tools.js";

/** Runtime-agnostic view of ONE composed DNA agent. */
export interface EmitContext {
  /** The DNA agent slug (`metadata.name`). */
  name: string;
  /** `metadata.description`, or "". */
  description: string;
  /** DNA-composed system prompt (Soul + guardrails + instruction, flat). The
   *  byte-equal gate: an emitter MUST carry it verbatim. */
  instructions: string;
  /** Raw DNA model coordinate (`openai:gpt-4o-mini` / `azure/gpt-4o` / bare), or
   *  null when the DNA leaves the model unbound. */
  model: string | null;
  /** Resolved tool surfaces (`spec.tools` → Tool Kind). */
  tools: EmitTool[];
  /** Optional response JSON Schema (`spec.output_schema`), or null. */
  outputSchema: Record<string, unknown> | null;
  /** Scope the agent was composed from (provenance). */
  scope: string | null;
  /** Per-emitter hints (e.g. a `--provider` override). */
  options: Record<string, unknown>;
}

export interface EmitTool {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

/** One emitted file, tagged with a semantic role. A single-agent emit produces
 *  one `role="agent"` artifact; a servable copilot emits several. */
export interface EmitArtifact {
  /** Target-relative output path (`"agent.py"`, `"serve.py"`). */
  path: string;
  /** Serialized file content (source / YAML / JSON). */
  content: string;
  /** Semantic role — `"agent"` carries the byte-equal instruction; `"serving"`
   *  is the AG-UI serve app. Extensible. */
  role: string;
}

/** Constructor init for {@link EmitResult}: either the legacy `artifact`+
 *  `filename` pair OR a full `artifacts` list. */
export interface EmitResultInit {
  target: string;
  artifact?: string;
  filename?: string;
  artifacts?: EmitArtifact[];
  losses?: string[];
  mapping?: Record<string, string>;
}

/** The emitted native artifact(s) + an honest account of the de-para.
 *
 *  `artifacts` is the SINGLE SOURCE OF TRUTH; `artifact`/`filename` are
 *  read-only views of the `role="agent"` entry (back-compat). Mirrors the Python
 *  `EmitResult`: a class (not a plain object) so the legacy single-artifact
 *  accessors coexist with the N-artifact list. */
export class EmitResult {
  readonly artifacts: EmitArtifact[];
  readonly target: string;
  readonly losses: string[];
  readonly mapping: Record<string, string>;

  constructor(init: EmitResultInit) {
    this.target = init.target;
    this.losses = init.losses ?? [];
    this.mapping = init.mapping ?? {};
    if (init.artifacts) {
      this.artifacts = init.artifacts;
    } else {
      if (init.artifact == null || init.filename == null) {
        throw new EmitError(
          "EmitResult needs `artifacts` or the legacy `artifact`+`filename` pair",
        );
      }
      this.artifacts = [{ path: init.filename, content: init.artifact, role: "agent" }];
    }
  }

  /** Content of the artifact tagged `role` (throws if absent). */
  artifactFor(role: string): string {
    const a = this.artifacts.find((x) => x.role === role);
    if (!a) throw new EmitError(`no artifact with role '${role}'`);
    return a.content;
  }

  /** Legacy single-artifact content = the `role="agent"` entry. */
  get artifact(): string {
    return this.artifactFor("agent");
  }

  /** Legacy single-artifact path = the `role="agent"` entry's path. */
  get filename(): string {
    const a = this.artifacts.find((x) => x.role === "agent");
    if (!a) throw new EmitError("EmitResult has no role='agent' artifact");
    return a.path;
  }
}

/** A runtime emitter — pure: reads an {@link EmitContext}, returns an
 *  {@link EmitResult}. No kernel I/O, no network.
 *
 *  A conforming emitter provides identity (`target` / `fileExtension`), the
 *  materialization ({@link emit}), and the byte-equal invariant hook
 *  ({@link extractInstructions}) that makes the central invariant inheritable. */
export interface EmitterPort {
  readonly target: string;
  readonly fileExtension: string;
  emit(ctx: EmitContext): EmitResult;
  /** Recover the composed instruction embedded in `artifact` (the inverse of the
   *  instruction half of {@link emit}) — used by the generic byte-equal contract
   *  test. Returns null only when the target has no instruction slot at all. */
  extractInstructions(artifact: string): string | null;
}

export class EmitError extends Error {}

export class UnknownTarget extends EmitError {
  constructor(
    readonly target: string,
    readonly available: string[],
  ) {
    super(
      `no emitter registered for target '${target}'; available: ` +
        (available.join(", ") || "(none)"),
    );
    this.name = "UnknownTarget";
  }
}

// ── registry ──────────────────────────────────────────────────────────────

const EMITTER_REGISTRY = new Map<string, EmitterPort>();
let builtinsWired = false;

async function ensureBuiltins(): Promise<void> {
  if (builtinsWired) return;
  builtinsWired = true;
  const { AgentFrameworkEmitter } = await import("./agentFramework.js");
  const { BedrockEmitter } = await import("./bedrock.js");
  const { VertexEmitter } = await import("./vertex.js");
  const { OpenAIAgentsEmitter } = await import("./openaiAgents.js");
  const { LanggraphEmitter } = await import("./langgraph.js");
  const { AgnoEmitter } = await import("./agno.js");
  const { DeepAgentsEmitter } = await import("./deepagents.js");
  for (const e of [
    new AgentFrameworkEmitter(),
    new BedrockEmitter(),
    new VertexEmitter(),
    new OpenAIAgentsEmitter(),
    new LanggraphEmitter(),
    new AgnoEmitter(),
    new DeepAgentsEmitter(),
  ]) {
    if (!EMITTER_REGISTRY.has(e.target)) EMITTER_REGISTRY.set(e.target, e);
  }
}

/** Register an emitter under its `target` (last registration wins). */
export function registerEmitter(emitter: EmitterPort): EmitterPort {
  EMITTER_REGISTRY.set(emitter.target, emitter);
  return emitter;
}

/** Remove a registered emitter (a host override or a test double). Returns
 *  whether a target was actually removed. Parity with the Python side popping
 *  from `EMITTER_REGISTRY`. */
export function unregisterEmitter(target: string): boolean {
  return EMITTER_REGISTRY.delete(target);
}

/** Look up a registered emitter or throw {@link UnknownTarget}. */
export async function getEmitter(target: string): Promise<EmitterPort> {
  await ensureBuiltins();
  const e = EMITTER_REGISTRY.get(target);
  if (!e) throw new UnknownTarget(target, await availableTargets());
  return e;
}

/** Sorted list of registered target ids. */
export async function availableTargets(): Promise<string[]> {
  await ensureBuiltins();
  return [...EMITTER_REGISTRY.keys()].sort();
}

// ── composition: DNA agent → neutral EmitContext ────────────────────────────

export interface BuildEmitContextOpts {
  model?: string | null;
  provider?: string | null;
}

/** Compose a DNA agent through the kernel and project it to an
 *  {@link EmitContext}. `mi` is a live ManifestInstance. */
export async function buildEmitContext(
  mi: ManifestInstance,
  agent: string,
  opts: BuildEmitContextOpts = {},
): Promise<EmitContext> {
  const doc = mi.findAgent(agent);
  if (!doc) {
    throw new EmitError(`agent '${agent}' not found in scope '${mi.scope ?? "?"}'`);
  }
  const spec = (doc.spec ?? {}) as Record<string, unknown>;
  const meta = (doc.metadata ?? {}) as Record<string, unknown>;
  const description = (meta.description as string | undefined) ?? "";

  const instructions = await mi.buildPrompt({ agent });

  let resolvedModel: string | null =
    opts.model ?? (spec.model as string | undefined) ?? null;
  if (!resolvedModel) {
    const root = mi.root;
    const rootSpec = (root?.spec ?? {}) as Record<string, unknown>;
    resolvedModel = (rootSpec.default_llm as string | undefined) ?? null;
  }

  const tools = resolveTools(mi, spec);
  const outputSchema = (spec.output_schema as Record<string, unknown> | undefined) ?? null;

  return {
    name: doc.name ?? agent,
    description,
    instructions,
    model: resolvedModel,
    tools,
    outputSchema,
    scope: mi.scope ?? null,
    options: opts.provider ? { provider: opts.provider } : {},
  };
}

function resolveTools(mi: ManifestInstance, spec: Record<string, unknown>): EmitTool[] {
  const names = spec.tools as string[] | undefined;
  if (!names || names.length === 0) return [];
  const lib = new ToolLibrary(mi);
  return names.map((name) => {
    const surface = lib.get(name); // throws ToolNotFound (fail-loud)
    return {
      name,
      description: surface.description,
      parameters: { ...surface.parameters },
    };
  });
}

// ── high-level surface ──────────────────────────────────────────────────────

/** Compose `agent` from `mi` and emit it for `target`. */
export async function emitAgent(
  mi: ManifestInstance,
  agent: string,
  target: string,
  opts: BuildEmitContextOpts = {},
): Promise<EmitResult> {
  const emitter = await getEmitter(target);
  const ctx = await buildEmitContext(mi, agent, opts);
  return emitter.emit(ctx);
}
