# Retrofit findings: does the Copilot emitter reproduce the two hand-built apps?

**Date:** 2026-07-16 · **Feature:** `f-copilot-retrofit` (absorption phase 7) ·
**Validates:** `docs/design/2026-07-16-copilot-absorption-design.md` §8 step 7.

## What this is

The Copilot absorption thesis is that DNA becomes the **single evolution point**:
one declarative `Copilot` definition emits a full servable AG-UI backend for any
target runtime, and the two apps that independently hand-built the same scaffold
(a Microsoft Agent Framework helpdesk and an Agno knowledge/RFP analyst) become
**consumers** of that emit instead of bespoke code.

Phase 7 is the honest test of that claim: author two `Copilot` definitions
**shaped after** the two reference apps, emit them, and diff the emitted backend
against each reference's load-bearing structure — **converge modulo per-app
bodies**. This report is the verdict.

- **Fixtures** (neutral-named — the references are structural, not the vendor
  code): `examples/emitting-to-a-runtime/.dna/retrofit/`
  - `copilots/helpdesk-copilot.yaml` → **agent-framework** target, a
    `triage→retrieve→resolve` workflow chain + workflow-level `request_info`
    escalation, over `federations/helpdesk-mcp.yaml` (read/write + min-role RBAC).
    Shaped after `foundry-assured/apps/backend`.
  - `copilots/rfp-copilot.yaml` → **agno** target, `knowledge.collections`, an
    MCP mount, tool-level HITL, inbound tenant, a CopilotKit frontend. Shaped
    after the Agno KB reference app (`apps/agent/src`).
- **Validation tests:** `packages/sdk-py/tests/test_copilot_retrofit.py` (17
  assertions; every row below with a ✓ is pinned by a test).

Method: assert **structure** (the load-bearing identifiers/idioms each reference
hand-wrote), not a byte-diff of the whole app — per-app bodies are out of scope
for the emitter by design (§5).

---

## Reference A — foundry-assured (Microsoft Agent Framework)

Emit: `helpdesk-copilot` → `agent-framework`. Reference: `~/projects/foundry-assured/apps/backend`.

| Contract element | Reference (hand-written) | Emitted | Verdict |
|---|---|---|---|
| agent build | `FoundryChatClient(...).as_agent(name, instructions, …)` per step (`app/workflow/agents.py`) | `FoundryChatClient(model, credential).as_agent(name, instructions, tools)` | **CONVERGES** ✓ |
| instructions | soul/guardrail/instruction composed in `prompts.py` | flat `INSTRUCTIONS`, byte-equal to `build_prompt` (persona inside) | **CONVERGES** ✓ |
| workflow chain | `WorkflowBuilder(…).add_chain([triage, retrieve, resolve, escalate]).build()` (`app/workflow/graph.py`) | identical shape, one agent-executor per declared step + appended escalate | **CONVERGES** ✓ |
| workflow HITL | `EscalationExecutor(Executor, id="escalate")`, `ctx.request_info(...)` in `@handler`, `@response_handler` (`app/workflow/escalation.py`) | same class/idiom; MCP mount drops to `never_require` (writes gated at workflow level) | **CONVERGES** ✓ |
| MCP mount (allowlist) | `MCPStreamableHTTPTool` + `header_provider` (`app/agents/mcp/tools.py`) | `MCPStreamableHTTPTool(name, url, allowed_tools, approval_mode, header_provider)` | **CONVERGES** ✓ |
| MCP RBAC (role floors) | `McpServer.min_role`/`min_role_write` + `visible_tools(server, roles)` (`app/agents/mcp/registry.py`) | **dropped** — `EmitMcpServer` projects `allowed_tools` only | **GAP** ✓ (see below) |
| inbound tenant bridge | ContextVar + `header_provider` + serving middleware | ContextVar + `_tenant_header_provider` + `@app.middleware("http")` | **CONVERGES** (mechanism) ✓ |
| tenant SOURCE | Entra `tid` claim + OBO credential broker (`app/core/tenant.py`, `auth.py`) | DNA-native `X-DNA-Tenant/-Workspace/X-Tenant-OID` trusted headers | **PER-APP** (IdP/token derivation) ✓ |
| AG-UI serving | `add_agent_framework_fastapi_endpoint(app, AgentFrameworkWorkflow(...), path="/helpdesk")` (`app/domains.py`) | same fn + `AgentFrameworkWorkflow(workflow_factory=build_workflow)`, `path="/agui"` | **CONVERGES** (fn) ✓ / **PER-APP** (path) |
| stream ordering | `OrderedAgentFrameworkWorkflow` rc5 bug workaround (`app/workflow/stream_fix.py`) | **not emitted** | **PER-APP** ✓ (version-pinned throwaway, design §1) |
| per-step instructions | each step has real instructions (`prompts.py`) | first step = byte-equal prompt; rest are `_STEP_INSTRUCTIONS` stubs | **PER-APP** (documented loss) |
| response-handler effect | `create_ticket(...)` + `has_role("Approver","Admin")` gate | `ctx.yield_output("Approved."/…)` stub | **PER-APP** (tool body) |

## Reference B — the Agno KB reference app (Agno + AgentOS)

Emit: `rfp-copilot` → `agno`. Reference: the Agno KB reference app (`apps/agent/src`).

| Contract element | Reference (hand-written) | Emitted | Verdict |
|---|---|---|---|
| agent build | `Agent(name, db, model=OpenAILike(id,…), instructions, tools, knowledge, search_knowledge, skills, session_state, add_session_state_to_context, markdown)` (`agents/factory.py`) | `Agent(name, model=OpenAILike(id), instructions, tools=_mcp_tools(), knowledge, search_knowledge, db, session_state, add_session_state_to_context, markdown)` | **CONVERGES** ✓ |
| instructions | composed | byte-equal `INSTRUCTIONS` | **CONVERGES** ✓ |
| MCP mount | `MCPTools(url=…, transport="streamable-http")`, built-not-connected (`_build_mcp_tools`) | identical | **CONVERGES** ✓ |
| knowledge binding | `knowledge=build_knowledge(collection)` + `search_knowledge=knowledge is not None` (`factory.py`) | `_knowledge()` wiring-point factory + both kwargs, carrying the DNA collection refs | **CONVERGES** (seam) ✓ — **fixed in this feature** |
| knowledge retrieval impl | `Knowledge(vector_db=PgVector(schema="ai", …), …)` + `AzureOpenAIEmbedder` (`services/collections.py`) | `_knowledge()` returns `None` with a `TODO(consumer)` over the refs | **PER-APP** ✓ (§6.3) |
| AG-UI serving | subclass `AGUI`, `@router.post("/agui")` | `TenantAGUI(AGUI)`, `@router.post("/agui")` | **CONVERGES** ✓ |
| app assembly | AGUI router on a **plain FastAPI** (deliberately NOT AgentOS — base_app clobber) | `AgentOS(agents, interfaces=[TenantAGUI]).get_app()` | **DELIBERATE DELTA** (both expose POST /agui) |
| inbound tenant | `tenant_from_request` → `inject_tenant` → `run_input.state["tenant"]`; tools read `RunContext.session_state` (`core/agui_hitl.py`) | same functions + `run_input.state["tenant"]` | **CONVERGES** ✓ |
| tenant headers + grants | app-specific tenant/user headers + `run_input.state["grants"]` RBAC | `X-DNA-*` trusted headers, no `grants` | **PER-APP** (header names + grant store) |
| tool-level HITL | LOCAL `@tool(external_execution=True)` (record_rfp_verdict) + `acontinue_run` (`tools/rfp_tools.py`) | gate DIRECTLY on the remote MCP tool via `external_execution_required_tools` (Spike 0A) | **CONVERGES** (pause/resume contract) ✓ / **DELIBERATE DELTA** (gate locus, §6.1 B2) |
| resume + de-dup glue | ~391 lines `run_agent_hitl` + `filter_reemitted_text` (`core/agui_hitl.py`) | **not emitted** — Agno ≥2.7 resumes `external_execution` natively | **GAP-CLOSED-BY-VERSION** ✓ (convergence win, contingent on Agno version; design risk 2) |
| skills / canvas tools | `LocalSkills`/`Skills`, doc-author canvas | not emitted | **PER-APP** |
| model api_key/base_url | `OpenAILike(id, api_key, base_url)` | `OpenAILike(id)` | **PER-APP** (wire-up) |

---

## The verdict on the thesis

**The single-evolution-point thesis is VALIDATED for the load-bearing servable
shape of both apps.** From one `Copilot` definition per reference, the emitter
reproduces — asserted by 17 structural tests — the entire servable spine each app
hand-wrote: agent/step build, the AG-UI serving mount, the MCP tool mount, the
inbound-tenant bridge, the HITL pause/resume contract, and (foundry) the full
`WorkflowBuilder` chain + `request_info` escalation. The bytes the emitter does
NOT produce fall into three honest buckets, none of which refute the thesis:

1. **Genuinely per-app** (correctly left to the consumer, design §5): tool
   bodies, per-step instructions, the IdP/OBO credential derivation, the
   retrieval store (PgVector/embedder / AzureAISearch), skills, canvas tools,
   app-specific header names, and the RBAC grant/ticket effects.
2. **Deliberate design deltas** (a choice, not a miss): gate-remote-directly vs a
   local-tool gate (Spike 0A); `AgentOS.get_app()` vs a plain-FastAPI mount;
   DNA-native `X-DNA-*` headers vs each app's own. All expose the same `/agui`
   contract.
3. **Obviated glue** (a convergence WIN): the Agno KB app's ~391 lines of
   hand-rolled resume/de-dup machinery are not reproduced because Agno ≥2.7
   resumes `external_execution` gates natively — the emitted app is smaller than
   the hand-written one, contingent on the pinned Agno version (design risk 2).

## Emitter gaps found

### Fixed in this feature (small)
- **Agno `knowledge=` binding was dropped.** `ctx.knowledge` rode on the context
  but the Agno backend emitted no `knowledge=`/`search_knowledge=` — the KB
  reference's load-bearing binding was silently absent. **Fixed**: the Agno
  copilot scaffold now emits a `_knowledge()` wiring-point factory (carrying the
  DNA collection refs) + both kwargs, mirroring the reference's `build_agent`
  shape; the retrieval impl stays a documented PER-APP `TODO(consumer)` (§6.3).
  Py + TS templates + emitters + goldens updated (parity held); pinned by
  `test_rfp_reproduces_knowledge_binding` + the regenerated `agno/copilot_agent.py`
  golden. Loss list updated (`_copilot_losses`).

### Documented as follow-up (not small — needs its own feature)
- **MCP RBAC role floors are not emitted.** `MCPFederation` already carries the
  read/write split + `min_role`/`min_role_write` (absorption phase 6a), and the
  pure `resolve_tools`/`visible_tools` governance functions exist — but
  `EmitMcpServer` projects `allowed_tools` only, so the role floors never reach
  the emitted mount. The emitted mount reproduces the allowlist + the read/write
  **approval** split (`approval_mode`, sourced from `Tool.requires_confirmation`),
  which is a real slice of the foundry registry's behavior, but not the role
  gate. This is **not** a small template edit: role visibility is a **per-request**
  decision (it needs the caller's roles at call time — `visible_tools(server,
  roles)`), so a static mount cannot resolve it faithfully. The honest shapes are
  either (a) emit the RBAC metadata as governance the serving layer feeds to
  `resolve_tools` at request time, or (b) emit a request-scoped role→tool filter
  — both are runtime-machinery on the order of the tenant bridge, not a literal.
  Pinned as a known gap by `test_helpdesk_reproduces_rbac_mcp_mount` (asserts the
  floors are absent) so it cannot silently drift. → **follow-up feature**
  (`f-copilot-mcp-rbac-emit`, depends on the request-scoped role source).

## Also confirmed per-app (not gaps — correctly out of scope)
per-step instructions, tool/response-handler bodies, the `stream_fix` rc5
workaround, PgVector/embedder + AzureAISearch retrieval, Entra/OBO + app-specific-header
IdPs, the `grants` RBAC store, and skills/canvas — all §5/§10.7 per-app, wired at
the consumer.
