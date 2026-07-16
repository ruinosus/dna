/**
 * DNA → **hosted-variant** deployment artifacts for a servable Copilot (TS twin
 * of python `dna.emit.hosting`).
 *
 * Where the backend emitters materialize the *self-hosted* AG-UI app and the
 * frontend emit its console, this module emits the **hosted** variant — a
 * container image + a managed-runtime manifest. Design §2 — *"`hosting.mode` is a
 * variant selector over ONE agent def: the same agent emits BOTH the per-user
 * AG-UI app AND the single-identity hosted agent; the hosted variant DEGRADES"*.
 *
 * Gated on `ctx.hosting.mode === "hosted"` ({@link hasHosting}): a copilot with no
 * `hosting`, or `mode: self-hosted`, keeps the existing AG-UI emit UNCHANGED. The
 * emit routes on `ctx.hosting.target`:
 *   - `foundry` — FIRST-CLASS: Dockerfile (8088, linux/amd64) + main.py
 *     (`ResponsesHostServer(build_agent()).run()`, DEGRADED single-identity) +
 *     requirements.txt + the `host: azure.ai.agent` azure.yaml block.
 *   - `langgraph-platform` / `agentos` — DOCUMENTED: self-host artifacts + a note.
 *
 * NOT a registered {@link EmitterPort} — hosting artifacts carry no byte-equal
 * instruction. The emitter has a 1:1 Py/TS twin rendering byte-identical
 * templates, so both SDKs emit the same hosted variant.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import Mustache from "mustache";

import { persistenceFacts, pgUrlExpr, pyIdentifier, pyStrLiteral } from "./scaffold.js";
import { EmitError, EmitResult, type EmitArtifact, type EmitContext } from "./index.js";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Default serve port per hosting target (design §2: 8088 / 8123 / 7777). */
const DEFAULT_PORT: Record<string, number> = {
  foundry: 8088,
  "langgraph-platform": 8123,
  agentos: 7777,
};

/** Whether `ctx` declares a **hosted** variant to emit — `hosting` present AND
 *  `mode === "hosted"`. A copilot with no `hosting`, or `mode: self-hosted`,
 *  keeps the existing self-hosted AG-UI emit unchanged (the variant selector). */
export function hasHosting(ctx: EmitContext): boolean {
  return ctx.hosting !== null && ctx.hosting.mode === "hosted";
}

function readTemplate(name: string): string {
  const path = join(HERE, "scaffolds", "hosting", name);
  if (!existsSync(path)) throw new EmitError(`missing hosting template '${name}'`);
  return readFileSync(path, "utf-8");
}

function render(name: string, variables: Record<string, unknown>): string {
  return Mustache.render(readTemplate(name), variables);
}

/** Render a YAML scalar for the azure.yaml block — a numeric-looking string is
 *  quoted (`"0.5"`), a plain token (`1Gi`) is bare. Mirrors the reference. */
function yamlScalar(value: string | null): string {
  if (value === null || value === undefined) return '""';
  const s = String(value);
  return s !== "" && !Number.isNaN(Number(s)) ? `"${s}"` : s;
}

function foundryVariables(ctx: EmitContext): Record<string, unknown> {
  const hosting = ctx.hosting;
  const image = hosting?.image ?? null;
  const resources = hosting?.resources ?? null;
  const port = image?.port ?? DEFAULT_PORT.foundry;

  const facts = persistenceFacts(ctx);
  const hasPgvector = facts.vectorPg;

  // DEGRADED MCP mount: the SAME tools, but no approval_mode (HITL stripped) and
  // no header_provider (per-user OBO/tenant stripped) — a single service identity.
  const servers = ctx.mcpServers.map((s) => {
    const allowedSorted = [...s.allowedTools].sort();
    return {
      name_literal: pyStrLiteral(`mcp_${s.ref}`),
      url_literal: s.url ? pyStrLiteral(s.url) : "None",
      allowed_tools_literal: "[" + allowedSorted.map((t) => pyStrLiteral(t)).join(", ") + "]",
    };
  });

  const cpu = resources?.cpu ?? null;
  const memory = resources?.memory ?? null;

  return {
    name: ctx.name,
    name_literal: pyStrLiteral(ctx.name),
    instructions_literal: pyStrLiteral(ctx.instructions),
    has_model: ctx.model !== null,
    model_literal: ctx.model ? pyStrLiteral(ctx.model) : "",
    port,
    has_mcp: servers.length > 0,
    mcp_servers: servers,
    needs_os: hasPgvector,
    has_pgvector: hasPgvector,
    vector_ref: facts.vectorRef ?? "",
    vector_collection_literal: pyStrLiteral(
      ctx.knowledge.length > 0 ? pyIdentifier(ctx.knowledge[0]) : "knowledge",
    ),
    vector_db_url_expr: hasPgvector && facts.vectorRef ? pgUrlExpr(facts.vectorRef) : "",
    embed_model_literal: pyStrLiteral(facts.embedModel ?? "text-embedding-3-small"),
    embed_dims: facts.embedDims !== null ? facts.embedDims : 1536,
    service_name: ctx.name,
    remote_build: Boolean(image?.remote_build),
    has_resources: Boolean(cpu || memory),
    cpu_literal: yamlScalar(cpu),
    memory_literal: yamlScalar(memory),
  };
}

function foundryLosses(ctx: EmitContext): string[] {
  const out = [
    "per-user OBO — the hosted variant authenticates as the platform-injected " +
      "AGENT identity (`DefaultAzureCredential`), NOT the signed-in user; the " +
      "on-behalf-of flow lives only in the self-hosted AG-UI app (design §2)",
    "HITL approval gates — the single-turn hosted agent has no approval card / " +
      "no workflow escalation; write tools run ungated under the agent identity " +
      "(the AG-UI variant keeps the gate)",
    "per-user long-term memory — Foundry hosting manages conversation history; " +
      "the cross-session per-user memory store is dropped in the hosted variant",
    "the agent VERSION is not built here — `azd deploy` builds the image " +
      "(remoteBuild via ACR) and publishes a new agent version (a deploy step, " +
      "not an artifact)",
  ];
  if (ctx.mcpServers.length > 0) {
    out.push(
      "MCP tool bodies — the hosted agent calls the DNA MCP server's tools over " +
        "Streamable HTTP (mounted WITHOUT approval_mode / header_provider — the " +
        "degrade); the tool implementations live on the remote MCP server",
    );
  }
  if (persistenceFacts(ctx).vectorPg) {
    out.push(
      "pgvector RAG — the surviving single-identity knowledge grounding binds " +
        "`PostgresVectorStore` (DSN from the infra ref via env var); wire it as " +
        "`context_providers` + load the corpus CONTENT per-app",
    );
  }
  if (ctx.model === null) {
    out.push(
      "model unbound in DNA and none supplied — emitted `FoundryChatClient(...)` " +
        "has no `model=`; supply one at wire-up",
    );
  }
  return out;
}

function emitFoundry(ctx: EmitContext): EmitResult {
  const variables = foundryVariables(ctx);
  const artifacts: EmitArtifact[] = [
    { path: "Dockerfile", content: render("foundry/Dockerfile.tmpl", variables), role: "hosting" },
    { path: "main.py", content: render("foundry/main.py.tmpl", variables), role: "hosting" },
    {
      path: "requirements.txt",
      content: render("foundry/requirements.txt.tmpl", variables),
      role: "hosting",
    },
    { path: "azure.yaml", content: render("foundry/azure.yaml.tmpl", variables), role: "hosting" },
  ];
  return new EmitResult({
    target: "foundry-hosted",
    artifacts,
    losses: foundryLosses(ctx),
    mapping: {
      "Copilot.hosting.target=foundry": "host: azure.ai.agent service block (azure.yaml)",
      "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (main.py, byte-equal)",
      "Copilot.hosting.image.port": "EXPOSE <port> (Dockerfile) — default 8088",
      "Copilot.hosting.image.remote_build": "docker.remoteBuild (azure.yaml)",
      "Copilot.hosting.resources": "config.container.resources (azure.yaml)",
      "Copilot.hosting.mode=hosted": "the DEGRADED single-identity variant (no OBO/memory/HITL)",
    },
  });
}

function langgraphVariables(ctx: EmitContext): Record<string, unknown> {
  const image = ctx.hosting?.image ?? null;
  const port = image?.port ?? DEFAULT_PORT["langgraph-platform"];
  const module = pyIdentifier(ctx.name);
  return { name: ctx.name, module, graph_id: module, port };
}

function emitLanggraph(ctx: EmitContext): EmitResult {
  const variables = langgraphVariables(ctx);
  const module = variables.module as string;
  const artifacts: EmitArtifact[] = [
    {
      path: "langgraph.json",
      content: render("langgraph/langgraph.json.tmpl", variables),
      role: "hosting",
    },
    { path: "HOSTING.md", content: render("langgraph/HOSTING.md.tmpl", variables), role: "hosting" },
  ];
  return new EmitResult({
    target: "langgraph-platform",
    artifacts,
    losses: [
      "LangGraph Platform is a stateful SERVER, not a Foundry-style managed " +
        "hosted agent — the hosting abstraction leaks (design §2/§6): `identity` " +
        "and `protocol` don't map, and `langgraph build` (not this emit) produces " +
        "the image from langgraph.json. Emitted DOCUMENTED, lower v1 priority.",
      `graph body — \`langgraph.json\` points at \`./${module}:graph\`; the compiled ` +
        "StateGraph is a per-app body (the self-hosted LangGraph scaffold emits " +
        "it), not part of the hosting manifest.",
    ],
    mapping: {
      "Copilot.hosting.target=langgraph-platform": "langgraph.json (graphs + dependencies + env)",
      "`langgraph build`": "the container image (NOT this emit)",
    },
  });
}

function agentosVariables(ctx: EmitContext): Record<string, unknown> {
  const image = ctx.hosting?.image ?? null;
  const port = image?.port ?? DEFAULT_PORT.agentos;
  const module = pyIdentifier(ctx.name);
  return {
    name: ctx.name,
    name_literal: pyStrLiteral(ctx.name),
    instructions_literal: pyStrLiteral(ctx.instructions),
    has_model: ctx.model !== null,
    model_literal: ctx.model ? pyStrLiteral(ctx.model) : "",
    module,
    port,
  };
}

function emitAgentos(ctx: EmitContext): EmitResult {
  const variables = agentosVariables(ctx);
  const port = variables.port as number;
  const artifacts: EmitArtifact[] = [
    { path: "main.py", content: render("agentos/main.py.tmpl", variables), role: "hosting" },
    {
      path: "compose.yaml",
      content: render("agentos/compose.yaml.tmpl", variables),
      role: "hosting",
    },
    { path: "HOSTING.md", content: render("agentos/HOSTING.md.tmpl", variables), role: "hosting" },
  ];
  return new EmitResult({
    target: "agentos",
    artifacts,
    losses: [
      "Agno AgentOS has NO managed runtime — `mode: hosted` for agentos ≈ " +
        "self-host (the emitted `AgentOS(...)` app + compose.yaml) + an optional " +
        "control-plane REGISTRATION step; there is no Foundry-style hosted agent " +
        "(design §2/§6). Emitted DOCUMENTED, lower v1 priority.",
      `the compose.yaml is a THIN single-service scaffold (port ${port}); wire the ` +
        "managed Postgres/Redis + JWT secrets + ingress via " +
        "f-copilot-infra-binding, not this file.",
    ],
    mapping: {
      "Copilot.hosting.target=agentos": "AgentOS(...) main.py + thin compose.yaml",
      "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (main.py, byte-equal)",
      "Copilot.hosting.mode=hosted": "self-host + control-plane registration (no managed runtime)",
    },
  });
}

const TARGETS: Record<string, (ctx: EmitContext) => EmitResult> = {
  foundry: emitFoundry,
  "langgraph-platform": emitLanggraph,
  agentos: emitAgentos,
};

/** Render the **hosted** variant deployment artifacts for a Copilot.
 *
 * `ctx` is an enriched copilot context ({@link buildCopilotContext}) carrying a
 * `hosting` block with `mode: hosted`. Routes on `hosting.target` (`foundry`
 * first-class; `langgraph-platform` / `agentos` documented) and returns an
 * {@link EmitResult} whose artifacts are all tagged `role="hosting"`. Throws when
 * the copilot has no hosted variant or names an unknown target. */
export function emitHosting(ctx: EmitContext): EmitResult {
  if (!hasHosting(ctx)) {
    throw new EmitError(
      `copilot '${ctx.name}' declares no HOSTED variant (\`hosting.mode\` is not ` +
        "'hosted') — the self-hosted AG-UI emit is unchanged; there is nothing to " +
        "emit here (design §2 variant selector)",
    );
  }
  const target = ctx.hosting?.target ?? null;
  const emit = target ? TARGETS[target] : undefined;
  if (emit === undefined) {
    throw new EmitError(
      `hosting target '${target}' has no emitter (design §2 covers foundry, ` +
        "langgraph-platform, agentos)",
    );
  }
  return emit(ctx);
}
