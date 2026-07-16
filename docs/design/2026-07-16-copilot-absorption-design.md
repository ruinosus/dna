# Design: AG-UI Copilot Absorption into DNA

**Date:** 2026-07-16 · **Status:** Draft (for owner review)
**Epic:** `e-dna-copilot-absorption` · **Feature:** `f-dna-copilot-emitter`
**First consumer:** `f-dna-cloud-copilot` (dna-cloud-dev)
**Inputs:** diff-study of `foundry-assured` (MS Agent Framework) + `aap-knowledge-base` (Agno);
prior-art brief `dna-cloud/docs/research/2026-07-16-copilot-agentic-ui-stack.md`.

---

## 1. Why

Two of our projects independently hand-built the **same** "AG-UI copilot" scaffold in
two different agent runtimes:

- **`foundry-assured`** — Microsoft Agent Framework; `/helpdesk` over AG-UI; agents
  declared in `.dna/helpdesk/agents/*.yaml`. **It already runs on DNA** for the
  instruction layer (`Kernel.quick(".dna/helpdesk")` → `mi.build_prompt`).
- **`aap-knowledge-base`** — Agno + AgentOS; `/agui`; agents as `Content` rows;
  MCP-tool mounting, HITL, tenant injection all hand-rolled.

That convergence is the case for absorption: **make the AG-UI copilot a first-class
DNA emit capability**, so one declarative definition emits a full servable copilot
for any target runtime. DNA becomes the **single evolution point**; DNA Cloud,
foundry, and aap-kb become **consumers**.

### The key finding (this is cheaper than it looks)
The declarative **substrate for the hard parts already exists in DNA's Kinds** — the
emitter just **drops** it today:
- `MCPFederation` + `propagate_tenant` → the `X-DNA-Tenant-*` header pattern both apps
  hand-wrote for tenant injection.
- `Tool.requires_confirmation` / `read_only` → the HITL gate, already declarable.
- `Agent.spec.mcp_servers` → the MCP-tool mount, dropped in `EmitContext`.

So the absorption is mostly **"stop dropping + emit"**, not "invent new Kinds."

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

## 3. The `Copilot` Kind (a binder + 3 new fields)

Composition-plane Kind, one per servable surface. Most fields **bind existing**
Agent/Tool/MCPFederation Kinds; only `knowledge`, `hitl`, `frontend` are new.

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

### 6.1 HITL — declare intent, emit the native idiom, stop there
`foundry` pauses a whole **workflow** (`request_info`/`response_handler`); `aap-kb`
pauses a single **tool** (`external_execution` + `acontinue_run` continuing the same
run). A declarative gate (`Tool.requires_confirmation`) **emits both** idioms. **Do
NOT invent a unified runtime HITL protocol** — it yields a leaky lowest-common
denominator. Declare intent in the Kind; emit the runtime-native mechanism.

### 6.2 Frontend — one shared template + a tiny per-runtime resume-adapter
Both frontends are ~95% generic CopilotKit v2 + `HttpAgent`. `aap-kb`'s web app has
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
`AzureAISearchContextProvider(mode="agentic")` + ACL-trim and `aap-kb`'s Agno
`Knowledge`/PgVector are per-app retrieval impls, not absorbed.

### 6.4 MCPFederation extension — the one real new work
`foundry`'s MCP registry (`registry.py:McpServer`) has **read/write tool split +
min-role RBAC**, richer than DNA's flat `MCPFederation.allowed_tools`. To retrofit
foundry without losing its RBAC, **extend `MCPFederation`** with read/write tool
governance + a per-tool role floor. This is the only genuinely new Kind work (not
free).

### 6.5 Multi-agent workflow — YAGNI, per-target option
`foundry`'s `WorkflowBuilder` chain has no Agno equivalent and is foundry's own
highest-risk item. Keep `workflow.chain` a per-target **advanced option**; do NOT
hoist it into the core `Copilot` Kind.

---

## 7. Parity implications

- **Backend scaffolds** parity Py↔TS exactly like today's scaffolds (byte-identical
  template + render context; `extract_instructions` unchanged **inside** the emitted
  agent module).
- **A Copilot emit now produces MULTIPLE artifacts** (backend ± frontend). The
  **frontend scaffold is TS-only** → it breaks the symmetric Py↔TS twin-diff model
  and MUST be governed as a **separate template family with its own golden**, not the
  twin harness.

---

## 8. Build order (machine emerges from the concrete case)

Rule of three is met: 2 hand-built references + DNA Cloud as the first emitted case.

1. **`Copilot` Kind + `EmitContext` projection** (mcp_servers, hitl, tenant,
   knowledge) — Py + TS twin.
2. **Agno `copilot` scaffold case** (serving + MCP-mount + HITL + tenant + optional
   knowledge) — the runtime DNA Cloud's Memory copilot targets.
3. **DNA Cloud Memory copilot = the first emitted consumer** (`f-dna-cloud-copilot`)
   — proves the emit end-to-end.
4. **MS Agent Framework `copilot` scaffold case** — enables the foundry retrofit.
5. **Shared frontend scaffold** + per-runtime resume-adapter.
6. **`MCPFederation` read/write + min-role extension** (needed for the foundry
   retrofit's RBAC).
7. **Retrofit `foundry` + `aap-kb`** — validation that the emitter reproduces both.

Phases 1–3 are the walking skeleton; 4–7 are the fill-out. Extract the scaffold from
the concrete Agno case (step 2/3) rather than designing all runtimes up front.

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

1. **HITL lossy seam** (§6.1) — accept per-runtime idioms; don't force a protocol.
2. **Frontend TS-only** (§7) — new golden family; governance divergence from the twin.
3. **MCPFederation RBAC extension** (§6.4) — real scope; sequence before the foundry
   retrofit.
4. **Don't over-generalize:** memory provider, connection brokering, MSAL/Entra vs
   Clerk auth, tenant stores — all per-app, out of scope for the emitter.
5. **Knowledge divergence** (§6.3) — absorb the ref only; retrieval per-app.

---

## 11. Bottom line

The absorption is smaller than it looked: foundry already round-trips DNA's
instruction emit, and the substrate for MCP-federation, tenant-header propagation,
and confirmation gates **already lives in DNA's Kinds** — the work is (a) projecting
those into `EmitContext`, (b) a per-runtime `copilot` scaffold that emits the servable
AG-UI app, (c) one shared CopilotKit frontend scaffold + a per-runtime resume adapter,
and (d) one real Kind extension (`MCPFederation` read/write + min-role) to preserve
foundry's RBAC. DNA Cloud's Memory copilot is the first emitted consumer; foundry and
aap-kb are the retrofit validation.
