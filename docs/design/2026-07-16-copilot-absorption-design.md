# Design: AG-UI Copilot Absorption into DNA

**Date:** 2026-07-16 · **Status:** Draft (for owner review)
**Epic:** `e-dna-copilot-absorption` · **Feature:** `f-dna-copilot-emitter`
**First consumer:** `f-dna-cloud-copilot` (dna-cloud-dev)
**Inputs:** diff-study of `foundry-assured` (MS Agent Framework) + the Agno KB reference app;
prior-art brief `dna-cloud/docs/research/2026-07-16-copilot-agentic-ui-stack.md`.

---

## 1. Why

Two of our projects independently hand-built the **same** "AG-UI copilot" scaffold in
two different agent runtimes:

- **`foundry-assured`** — Microsoft Agent Framework; `/helpdesk` over AG-UI; agents
  declared in `.dna/helpdesk/agents/*.yaml`. **It already runs on DNA** for the
  instruction layer (`Kernel.quick(".dna/helpdesk")` → `mi.build_prompt`).
- **The Agno KB reference app** — Agno + AgentOS; `/agui`; agents as `Content` rows;
  MCP-tool mounting, HITL, tenant injection all hand-rolled.

That convergence is the case for absorption: **make the AG-UI copilot a first-class
DNA emit capability**, so one declarative definition emits a full servable copilot
for any target runtime. DNA becomes the **single evolution point**; DNA Cloud,
foundry, and the KB reference app become **consumers**.

### The key finding — and its honest limit
The declarative **field substrate for the hard parts already exists in DNA's Kinds**
(verified against code) — the emitter just **drops** it today:
- `Agent.spec.mcp_servers` (`kernel/models.py:374`) → the MCP-tool mount, dropped in
  `EmitContext` (which projects only `{name,description,parameters}`).
- `Tool.requires_confirmation` / `read_only` (`helix/kinds/tool.kind.yaml:107`) → the
  HITL **intent**, already declarable.
- `MCPFederation` + `propagate_tenant` (`federation/__init__.py:146`) → the **outbound**
  tenant-header stamp (agent → federated MCP).

**But "stop dropping + emit" is honest only about the KINDS, not the total effort.**
The *servable runtime* — the AG-UI serving glue, the paused-run resume machinery, the
**inbound** frontend→run-state tenant derivation — is hand-written in the two apps and
exists in **neither** DNA today. The KB reference app's `agui_hitl.py` is ~391 lines of resume +
inject + a re-emit de-dup fix; `foundry` needs `stream_fix.py` to suppress duplicated
events. Both are **explicitly temporary, version-pinned workarounds** (Agno 2.6 /
CopilotKit 1.60 / agent-framework-ag-ui 1.0rc5). Reproducing that glue as byte-stable
golden scaffolds is the **bulk** of phases 2 & 5 — and it freezes framework-version
glue designed to be thrown away (a decay risk on the golden). So: the Kinds are cheap;
the servable runtime is the real work.

---

## 2. What DNA emits today (baseline)

`dna/emit/`: per agent, ONE artifact — a config-declarative doc (`agent_framework.py`
→ `PromptAgent` YAML) or a scaffold `.py` (`scaffold.py`/`agno.py` → byte-equal
`INSTRUCTIONS = …` + `agent = Agent(...)` with tool bodies as `NotImplementedError`
stubs). `EmitContext` = `{name, description, instructions, model, tools[{name,
description, parameters}], output_schema, scope, options}`. Byte-equal harness:
`extract_instructions` + `test_emit_contract.py`, TS twin in `sdk-ts/src/emit/`.

**Covered:** instructions (byte-equal), the agent object, tool signatures (stubbed).
**Not covered (the backlog):** AG-UI serving, MCP-tool mount, HITL pause/resume,
tenant injection, knowledge/RAG, the frontend. All 0%.

---

## 3. The `Copilot` Kind

Composition-plane Kind, one per servable surface. It has **seven** top-level fields.
Three **bind existing** Kinds (`mounts`→Agent, `hitl`→Tool intent, `tenant`→MCPFederation);
`knowledge`, `frontend`, and the `serving`/`workflow` selectors are **new structure**
that needs real schemas (`mounts` multi-surface especially is not a mere bind). This
draft sketches shape, not final schemas.

```yaml
Copilot:
  mounts:                                   # multi-surface (helpdesk/platform; rfp/doc/author)
    - id: memory
      agent: <Agent ref>                    # existing Agent Kind (instructions/model/tools)
      path: /agui
  serving: { transport: ag-ui }             # target runtime chosen at emit time
  tenant: { propagate: true }               # reuse MCPFederation.propagate_tenant
  hitl:                                      # DERIVED from Tool.requires_confirmation
    approval_card: { title, details_from, reason_from }
  knowledge:                                # NEW — optional RAG binding
    collections: [<ref>]                    # maps to DNA native search (pgvector/embedding/graph)
  frontend:                                 # NEW — optional
    console: chat+canvas
    panels: [evidence|sources]
    suggested_prompts: [...]
  workflow:                                 # optional, agent-framework-only step chain (YAGNI core)
    chain: [triage, retrieve, resolve, escalate]
```

MCP-mount and instructions/soul/guardrails/model/tools need **no new fields** —
already on `Agent`/`MCPFederation`; the work is **projecting them into `EmitContext`
and emitting them**.

---

## 4. The extended emitter (per target)

`EmitContext` grows to carry: `mcp_servers` (from `Agent.spec.mcp_servers` +
`MCPFederation` docs — transport/url/auth/allowed_tools/read+write/min-role),
`hitl` (from `Tool.requires_confirmation`/`read_only`), `tenant.propagate`,
`knowledge` refs, and the serving/frontend binding.

A new scaffold **case** per runtime — `scaffolds/<framework>/copilot.<py|ts>.tmpl` —
emits the **servable app**:

| Emitted piece | Agno / AgentOS | MS Agent Framework |
|---|---|---|
| agent build | `Agent(model=OpenAILike, instructions, tools, knowledge, session_state, db)` | `FoundryChatClient(...).as_agent(name, instructions, context_providers, tools)` |
| MCP mount | `MCPTools(url, transport)` | `MCPStreamableHTTPTool(name, url, allowed_tools, approval_mode, header_provider)` |
| AG-UI serve | subclass `agno.os.interfaces.agui.AGUI` → `/agui` | `add_agent_framework_fastapi_endpoint(app, agent, path)` |
| HITL pause | `@tool(external_execution=True)` | `ctx.request_info(req, response_type)` in an Executor |
| HITL resume | `acontinue_run(run_id, updated_tools)` (tool-result content) | `@response_handler`; wire `{interrupts:[{id,value}]}` |
| tenant carrier | `run_input.state` / `RunContext.session_state` | `ContextVar` + `header_provider` closure |
| knowledge | `knowledge=Knowledge` (PgVector) | `AzureAISearchContextProvider(mode="agentic")` |

The **HITL rows are different execution models**, not just APIs — see §6.1.

**Tenant has two seams, don't conflate them.** `MCPFederation.propagate_tenant` is the
**outbound** stamp (agent → federated MCP: `X-DNA-Tenant-Effective/-Scope/-Agent`) — a
Kind field, emitted for free. But the **inbound** derivation (frontend request →
run-state, so tools read it via `RunContext.session_state`) is what both apps
hand-wrote (`agui_hitl.py:127` `tenant_from_request`/`inject_tenant`) and is **not** in
DNA. The emitted scaffold must **generate the inbound derivation** — it is not a
`propagate_tenant` freebie.

---

## 5. Common / per-runtime / per-app

- **Emit once (common):** byte-equal `INSTRUCTIONS`; the AG-UI wire vocabulary; the
  **entire CopilotKit frontend scaffold**; the tenant-as-header convention
  (`MCPFederation.propagate_tenant`).
- **Parameterize per-runtime:** agent-build API, MCP-mount API, serving-mount fn,
  HITL pause/resume idiom + wire shape, knowledge-attach API. → one scaffold case per
  framework (exactly like today's `{framework × case}` templates).
- **Left to the consumer (per-app):** tool **bodies** (still stubs), domain
  canvas/panels, ACL-trim retrieval, the tenant store / IdP, the memory provider.

---

## 6. Decisions (ratified with the owner)

### 6.1 HITL — the gate emits the TOOL-level idiom only; workflow HITL is separate
There are **two different HITL mechanisms**, and `Tool.requires_confirmation` can only
derive one:
- **Tool-level** (the Agno KB reference): `@tool(external_execution=True)` + `acontinue_run`
  continuing the same run. This **IS** derivable from `Tool.requires_confirmation` →
  the emitter emits it. This is what the DNA Cloud consumer uses.
- **Workflow-level** (`foundry`): a workflow `request_info` **Executor** node, fused
  with RBAC and triggered by a magic string — chosen **deliberately instead of** a
  tool gate because the AG-UI workflow adapter double-emits `TOOL_CALL_START` for an
  agent's approval-gated tool call (`app/workflow/escalation.py:9`). It is **NOT**
  derivable from `Tool.requires_confirmation` and **requires the `workflow` capability
  (§6.5).**

So: the gate declares intent and emits the **tool-level** idiom natively. Workflow-level
HITL is a **separate, workflow-coupled** emit, gated on the `workflow` capability — the
`foundry` retrofit's HITL therefore depends on `workflow`, not on the tool flag (see
§8, re-sequenced). **Do NOT invent a unified runtime HITL protocol** across the two —
it yields a leaky lowest-common denominator.

**Open, load-bearing (B2):** the consumer gates tools that are **MCP-mounted** (remote),
but `external_execution` is a property of a **local** Agno `@tool` (both references gate
a *local* tool). Whether `external_execution`/`acontinue_run` works on an `MCPTools`
tool is **unproven** → a spike gates phase 1 (§8). The safe fallback: gate a **local
wrapper tool** that calls the MCP tool, so the confirmation lives on a local callable.

### 6.2 Frontend — one shared template + a tiny per-runtime resume-adapter
Both frontends are ~95% generic CopilotKit v2 + `HttpAgent`. The KB reference app's web app has
**zero** backend leak; `foundry` leaks exactly four things (the `withResumeBridge`
dict shape, the `TicketApproval` `request_info` matcher, `WorkflowSteps`
`executor_id/ActivitySnapshot`, hardcoded step ids). → **one shared frontend scaffold
+ a small per-runtime resume-adapter.** (If agent-framework used a standard AG-UI
interrupt instead of a `CUSTOM request_info` event, one scaffold would serve both.)

### 6.3 Knowledge/RAG — absorb the ref field only (optional capability)
RAG is **NOT** a mandatory pillar. The Kind carries a `knowledge.collections` ref;
the **retrieval implementation stays per-app / native DNA search** (`search:
pgvector|sqlite-vec` + `embedding` + `graph` in `dna/config.py`). A copilot with no
corpus (pure-action) declares no `knowledge` — `search: off` is valid. `foundry`'s
`AzureAISearchContextProvider(mode="agentic")` + ACL-trim and the KB reference app's Agno
`Knowledge`/PgVector are per-app retrieval impls, not absorbed.

### 6.4 MCPFederation extension — the one real new work
`foundry`'s MCP registry (`registry.py:McpServer`) has **read/write tool split +
min-role RBAC**, richer than DNA's flat `MCPFederation.allowed_tools`. To retrofit
foundry without losing its RBAC, **extend `MCPFederation`** with read/write tool
governance + a per-tool role floor. This is the only genuinely new Kind work (not
free).

### 6.5 Multi-agent workflow — YAGNI, per-target option (but foundry HITL needs it)
`foundry`'s `WorkflowBuilder` chain has no Agno equivalent and is foundry's own
highest-risk item. Keep `workflow.chain` a per-target **advanced option**; do NOT
hoist it into the core `Copilot` Kind. **Caveat (from §6.1):** foundry's HITL lives
*inside* the workflow, so the foundry retrofit's HITL is **gated on `workflow`** — the
retrofit cannot emit foundry's approval gate until the workflow capability ships. This
is sequenced explicitly in §8 so the retrofit doesn't silently depend on a deferred
feature.

---

## 7. Parity + the emit-port contract change

- **The current port is single-artifact.** `EmitResult` carries one `artifact: str` +
  `filename: str` (`emit/__init__.py:140`), and the byte-equal harness asserts
  `extract_instructions(artifact) == ctx.instructions` over that one string. A copilot
  emits a **backend app** (agent + AG-UI serve + route) **± a frontend tree** — many
  files. So a **multi-artifact `EmitResult`/`EmitterPort` shape is required new work**,
  plus a decision on **which artifact carries the byte-equal instruction assertion**.
  This is an explicit phase-1 sub-task (§8), not a freebie.
- **Backend scaffolds** parity Py↔TS like today's scaffolds (byte-identical template +
  render context; `extract_instructions` unchanged **inside** the emitted agent module).
- **The frontend scaffold is TS-only** → it breaks the symmetric Py↔TS twin-diff model
  and MUST be governed as a **separate template family with its own golden**. Note the
  governance gap: nothing beyond the golden render enforces frontend correctness — the
  twin-diff safety net does not apply to it.

---

## 8. Build order (machine emerges from the concrete case)

Rule of three is met: 2 hand-built references + DNA Cloud as the first emitted case.
**The two hardest unknowns live early — surface them first, don't bury them in a
"skeleton" label.**

0. **De-risk spikes (BEFORE phase 1):**
   - **B2 — HITL on an MCP-mounted tool.** Prove `external_execution`/`acontinue_run`
     works on an Agno `MCPTools` tool. If not, adopt the **local-wrapper-tool** fallback
     (confirm on a local callable that calls the MCP tool). This gates the whole wedge.
   - **Multi-artifact `EmitResult`/`EmitterPort`** (§7) + the byte-equal-assertion
     target decision.
1. **`Copilot` Kind (schemas for `mounts`/`serving`/`frontend`/`workflow`) +
   `EmitContext` projection** (mcp_servers, hitl intent, inbound-tenant, knowledge) —
   Py + TS twin.
2. **Agno `copilot` scaffold case** — the servable AG-UI app: serving glue + MCP-mount +
   the inbound-tenant derivation + tool-level HITL (per B2's outcome) + optional
   knowledge. **This reproduces the ~391 lines of `agui_hitl.py`-class resume glue as a
   golden** — the bulk of the work, not a stub.
3. **DNA Cloud Memory copilot = the first emitted consumer** (`f-dna-cloud-copilot`).
   **This is the real integration risk** (B2 + multi-artifact emit first bite here), not
   a skeleton.
4. **MS Agent Framework `copilot` scaffold case** — enables the foundry retrofit
   (tool-level HITL only; workflow HITL waits on step 6b).
5. **Shared frontend scaffold** + per-runtime resume-adapter.
6. **(a)** `MCPFederation` read/write + min-role extension (foundry RBAC); **(b)** the
   `workflow` capability (foundry's workflow-level HITL depends on it — §6.5).
7. **Retrofit `foundry` + the KB reference app** — validation that the emitter reproduces both.

Steps 0–3 are the walking skeleton **and** where the risk is concentrated; 4–7 are the
fill-out. Extract the scaffold from the concrete Agno case (2/3) rather than designing
all runtimes up front.

---

## 9. Testing / parity

- Unit: `EmitContext` projection (mcp_servers/hitl/tenant/knowledge present + correct).
- Golden: the Agno `copilot` scaffold render (byte-stable); the MS-AF scaffold render.
- Parity: backend Py↔TS twin-diff (unchanged harness); frontend TS-only golden (new
  family).
- Integration: emit the DNA Cloud Memory copilot definition → a servable AG-UI app
  that mounts the DNA MCP, gates `remember`/`forget` via HITL, injects tenant.
- Retrofit validation (later): emit foundry's `.dna/helpdesk` agents → diff against
  the hand-written backend (should converge modulo per-app bodies).

---

## 10. Risks / open questions

1. **B2 — HITL on an MCP-mounted tool is unproven** (§6.1) — spike gates phase 1;
   local-wrapper fallback if unsupported. Highest risk (the wedge depends on it).
2. **Servable-runtime glue is the real cost** (§1, §7) — the ~391-line resume machinery
   is version-pinned throwaway code; freezing it as a golden carries a decay risk.
3. **Multi-artifact emit-port change** (§7) — the single-artifact `EmitResult`/harness
   must be reshaped; explicit phase-1 work.
4. **HITL is two mechanisms, not one** (§6.1, B1) — tool-level (derivable) vs
   workflow-level (foundry; gated on `workflow`); don't force a unified protocol.
5. **Frontend TS-only** (§7) — new golden family; only the golden guards it (no twin).
6. **MCPFederation RBAC extension** (§6.4) — real scope; sequence before the foundry
   retrofit.
7. **Don't over-generalize:** memory provider, connection brokering, MSAL/Entra vs
   Clerk auth, tenant stores — all per-app, out of scope for the emitter.
8. **Knowledge divergence** (§6.3) — absorb the ref only; retrieval per-app.

---

## 11. Bottom line

The **declarative half** is cheap: foundry already round-trips DNA's instruction emit,
and the *fields* for MCP mount, confirmation intent, and outbound tenant propagation
already live in DNA's Kinds — the emitter just drops them. The **runtime half is the
real work**: a per-runtime `copilot` scaffold that emits the servable AG-UI app
(serving + MCP-mount + the **inbound** tenant derivation + tool-level HITL), reproducing
~391 lines of version-pinned resume glue as a golden; a multi-artifact emit-port; one
shared CopilotKit frontend scaffold + a per-runtime resume adapter; and one Kind
extension (`MCPFederation` read/write + min-role) plus the `workflow` capability to
retrofit foundry's workflow-coupled HITL. Two unknowns gate the start (HITL-on-MCP,
multi-artifact port) and must be spiked first. DNA Cloud's Memory copilot is the first
emitted consumer; foundry and the KB reference app are the retrofit validation.
