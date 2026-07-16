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
  // ── copilot-only projections (filled by buildCopilotContext) ──────────────
  /** External MCP servers the mounted agent consumes, resolved from its
   *  `mcp_servers` refs → `MCPFederation` docs. Empty for a single agent. */
  mcpServers: EmitMcpServer[];
  /** Tool names the mounted agent gates on human approval
   *  (`Tool.requires_confirmation`) — the HITL-write surface. Empty = none. */
  toolsRequiringConfirmation: Set<string>;
  /** Whether the emitted serving layer derives inbound tenant from request
   *  headers into run-state (Copilot `tenant.propagate` / federation
   *  `propagate_tenant`). */
  tenantPropagate: boolean;
  /** RAG collection refs the copilot may read (`knowledge.collections`). Empty
   *  when the copilot declares no knowledge (RAG optional). */
  knowledge: string[];
  /** Ordered workflow step ids (Copilot `workflow.chain`) — the agent-framework
   *  (MS Agent Framework) target emits a `WorkflowBuilder` chain + a
   *  workflow-level escalation node when present. Empty = plain single-agent app. */
  workflow: string[];
}

export interface EmitTool {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

/** Neutral projection of ONE `MCPFederation` the mounted agent consumes. Filled
 *  by {@link buildCopilotContext}. `transport` is normalized to the MCP client
 *  wire form (`streamable-http`) that Chunk 4's `MCPTools(url, transport)`
 *  consumes — the federation Kind stores it as `streamable_http`. */
export interface EmitMcpServer {
  /** Name of the `MCPFederation` doc (`mcp_servers[].ref`). */
  ref: string;
  /** MCP transport wire name — `streamable-http` or `stdio`. */
  transport: string;
  /** Server endpoint (`streamable_http` only), or null. */
  url: string | null;
  /** Auth block by env-var NAME (`{kind, env, header?}`) — never a secret. */
  auth: Record<string, unknown>;
  /** Effective tool allowlist — per-agent allowlist ∩ the federation's own.
   *  Empty = everything the federation allows. */
  allowedTools: string[];
  /** Whether the HTTP transport stamps tenant/scope/agent headers. */
  propagateTenant: boolean;
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
    // copilot-only projections stay at their empty defaults for a single agent.
    mcpServers: [],
    toolsRequiringConfirmation: new Set<string>(),
    tenantPropagate: false,
    knowledge: [],
    workflow: [],
  };
}

/** Compose a `Copilot` doc through the kernel and project it to an enriched
 *  {@link EmitContext} — the Chunk 1↔4 seam (TS twin of Python
 *  `build_copilot_context`).
 *
 *  Resolves the mounted agent's base ctx via the existing front door
 *  ({@link buildEmitContext} — so the byte-equal instruction contract is
 *  untouched), then enriches it with the mounted `mcp_servers` (→ `MCPFederation`
 *  docs), the HITL-gated tools (`Tool.requires_confirmation`), the inbound-tenant
 *  signal (`tenant.propagate` / federation `propagate_tenant`), and the
 *  `knowledge.collections` refs. Chunk 4's Agno scaffold emits from *this*. */
export async function buildCopilotContext(
  mi: ManifestInstance,
  copilot: string,
  opts: BuildEmitContextOpts = {},
): Promise<EmitContext> {
  const doc = mi._one("Copilot", copilot);
  if (!doc) {
    throw new EmitError(`copilot '${copilot}' not found in scope '${mi.scope ?? "?"}'`);
  }
  const cspec = (doc.spec ?? {}) as Record<string, unknown>;
  const mounts = (cspec.mounts as Array<Record<string, unknown>> | undefined) ?? [];
  if (mounts.length === 0) {
    throw new EmitError(`copilot '${copilot}' declares no mounts`);
  }
  const agentName = mounts[0].agent as string | undefined;
  if (!agentName) {
    throw new EmitError(`copilot '${copilot}' mount[0] has no agent`);
  }

  // Base ctx from the EXISTING front door — keyed by the mounted agent's name.
  const ctx = await buildEmitContext(mi, agentName, opts);

  // ── enrich ──────────────────────────────────────────────────────────────
  const agentDoc = mi.findAgent(agentName);
  const agentSpec = (agentDoc?.spec ?? {}) as Record<string, unknown>;

  const mcpServers = projectMcpServers(mi, agentSpec);
  ctx.mcpServers = mcpServers;
  ctx.toolsRequiringConfirmation = projectHitlIntent(mi, agentSpec);

  const tenantBlock = (cspec.tenant as Record<string, unknown> | undefined) ?? {};
  const copilotPropagate = tenantBlock.propagate as boolean | undefined;
  ctx.tenantPropagate =
    copilotPropagate !== undefined
      ? Boolean(copilotPropagate)
      : mcpServers.some((s) => s.propagateTenant);

  const knowledgeBlock = (cspec.knowledge as Record<string, unknown> | undefined) ?? {};
  ctx.knowledge = ((knowledgeBlock.collections as string[] | undefined) ?? []).slice();

  const workflowBlock = (cspec.workflow as Record<string, unknown> | undefined) ?? {};
  ctx.workflow = ((workflowBlock.chain as string[] | undefined) ?? []).slice();

  return ctx;
}

/** Resolve the mounted `Agent.spec.mcp_servers` refs → their `MCPFederation`
 *  docs, projected to neutral {@link EmitMcpServer} surfaces. Each entry is
 *  EITHER a string ref OR a `{ref, allowed_tools?}` dict; the effective allowlist
 *  is the per-agent allowlist ∩ the federation's own. `transport` is normalized
 *  from `streamable_http` to the MCP client wire form `streamable-http`. */
function projectMcpServers(
  mi: ManifestInstance,
  agentSpec: Record<string, unknown>,
): EmitMcpServer[] {
  const entries = (agentSpec.mcp_servers as Array<string | Record<string, unknown>> | undefined) ?? [];
  const out: EmitMcpServer[] = [];
  for (const entry of entries) {
    let ref: string | undefined;
    let agentAllow: string[] = [];
    if (typeof entry === "string") {
      ref = entry;
    } else {
      ref = entry.ref as string | undefined;
      agentAllow = ((entry.allowed_tools as string[] | undefined) ?? []).slice();
    }
    if (!ref) continue;
    const fed = mi._one("MCPFederation", ref);
    if (!fed) {
      throw new EmitError(
        `MCPFederation '${ref}' referenced by the mounted agent was not found in scope '${mi.scope ?? "?"}'`,
      );
    }
    const fspec = (fed.spec ?? {}) as Record<string, unknown>;
    const fedAllow = ((fspec.allowed_tools as string[] | undefined) ?? []).slice();
    let allowed: string[];
    if (agentAllow.length > 0 && fedAllow.length > 0) {
      allowed = agentAllow.filter((t) => fedAllow.includes(t));
    } else {
      allowed = agentAllow.length > 0 ? agentAllow : fedAllow;
    }
    const rawTransport = (fspec.transport as string | undefined) ?? "stdio";
    const transport = rawTransport === "streamable_http" ? "streamable-http" : rawTransport;
    const auth = fspec.auth as Record<string, unknown> | undefined;
    const propagate = fspec.propagate_tenant as boolean | undefined;
    out.push({
      ref,
      transport,
      url: (fspec.url as string | undefined) ?? null,
      auth: auth && typeof auth === "object" ? { ...auth } : {},
      allowedTools: allowed,
      propagateTenant: propagate === undefined ? true : Boolean(propagate),
    });
  }
  return out;
}

/** The mounted agent's tools whose `Tool.spec.requires_confirmation` is true —
 *  the HITL-gated write surface. */
function projectHitlIntent(
  mi: ManifestInstance,
  agentSpec: Record<string, unknown>,
): Set<string> {
  const names = (agentSpec.tools as string[] | undefined) ?? [];
  const gated = new Set<string>();
  for (const name of names) {
    const tdoc = mi._one("Tool", name);
    if (!tdoc) continue;
    const tspec = (tdoc.spec ?? {}) as Record<string, unknown>;
    if (Boolean(tspec.requires_confirmation)) gated.add(name);
  }
  return gated;
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
