# DNA Copilot Emitter — Walking Skeleton Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve DNA's emitter so one declarative `Copilot` definition emits a servable AG-UI copilot backend (Agno target) — the single evolution point that DNA Cloud's Memory copilot (Plan 2) consumes.

**Architecture:** Extend the existing `EmitterPort`/`ScaffoldEmitter` surface. Two phase-0 spikes de-risk the load-bearing unknowns first (HITL on an MCP-mounted tool; multi-artifact emit). Then: a `Copilot` Kind (binder over Agent/Tool/MCPFederation + `knowledge`/`hitl`/`frontend`/`mounts`/`serving`), a multi-artifact `EmitResult`, an extended `EmitContext` projection (mcp_servers, hitl-intent, inbound-tenant, knowledge), and an Agno `copilot` scaffold case emitting the servable `/agui` app. Byte-equal golden governs the scaffold.

**Tech Stack:** Python (`dna/emit`, `dna/extensions`), TypeScript twin (`sdk-ts/src/emit`), Agno 2.x + AgentOS, `ag-ui-protocol`, pytest, the existing `test_emit_contract.py` parity harness.

**Spec:** `docs/design/2026-07-16-copilot-absorption-design.md` (this repo).
**Scope note:** Plan 1 = the emitter skeleton (absorption phases 0–2 + the Agno scaffold). Plan 2 = the DNA Cloud consumer (`dna-cloud`, `s-copilot-design-spec`), written after the spikes + Kind land. Later fill-out (MS-AF scaffold, shared frontend, `MCPFederation` RBAC extension, foundry/aap-kb retrofit) = Plan 3.

---

## File structure (what this plan creates/modifies)

| File | Responsibility | New? |
|---|---|---|
| `spikes/2026-07-16-hitl-on-mcp/` | Spike A harness: does Agno `external_execution` fire on an `MCPTools` tool? | create |
| `spikes/2026-07-16-multi-artifact-emit/NOTES.md` | Spike B findings: the multi-artifact `EmitResult` shape + byte-equal target | create |
| `packages/sdk-py/dna/extensions/helix/kinds/copilot.kind.yaml` | The `Copilot` Kind schema (mounts/serving/hitl/knowledge/frontend/tenant/workflow) | create |
| `packages/sdk-py/dna/emit/__init__.py` | Multi-artifact `EmitResult`; `EmitContext` projection of mcp_servers/hitl/tenant/knowledge | modify |
| `packages/sdk-py/dna/emit/scaffold.py` | Multi-artifact scaffold support | modify |
| `packages/sdk-py/dna/emit/agno.py` | The Agno `copilot` scaffold case (serving + mount + inbound-tenant + tool-HITL) | modify |
| `packages/sdk-py/dna/emit/scaffolds/agno/copilot.py.tmpl` | The emitted servable `/agui` app template | create |
| `packages/sdk-ts/src/emit/*` | TS twins of the port + projection (byte-equal backend) | modify |
| `packages/sdk-py/tests/emit/test_copilot_emit.py` | Golden + projection tests | create |
| `packages/sdk-py/tests/emit/test_emit_contract.py` | Extend for multi-artifact | modify |

> Confirm exact paths against the tree before writing (`dna/extensions/helix/kinds/` and `tests/emit/` locations). Follow the established emitter patterns in `agno.py`/`scaffold.py` — do not restructure.

---

## Chunk 0: Phase-0 de-risk spikes (GATING — do first)

These two investigations determine the design of Chunks 3–4. Do not detail-build the Agno scaffold's HITL or the emit-port until these resolve.

### Task 0A: Spike — HITL on an MCP-mounted Agno tool

**Files:**
- Create: `spikes/2026-07-16-hitl-on-mcp/spike.py`, `spikes/2026-07-16-hitl-on-mcp/NOTES.md`

- [ ] **Step 1: Stand up a minimal MCP server with one write tool.** A tiny FastMCP server exposing `remember(text) -> str` (streamable-http). Reuse the `aap-knowledge-base` `mcp:` pattern (`apps/agent/src/agents/factory.py:_build_mcp_tools`) as the reference for `MCPTools(url, transport="streamable-http")`.

- [ ] **Step 2: Build an Agno agent that mounts it and try to gate it.** Attempt `@tool(external_execution=True)` semantics on the MCP-provided `remember`. Run a turn that calls `remember` and inspect `get_last_run_output().tools_awaiting_external_execution` (the aap-kb pattern, `core/agui_hitl.py`).

- [ ] **Step 3: Record the verdict in NOTES.md.** Does external-execution fire on the MCP tool? (a) YES → the emitter can gate the remote tool directly. (b) NO → the emitter must emit a **local wrapper tool** that calls the MCP tool, with `external_execution` on the wrapper. Write which, with the evidence.

- [ ] **Step 4: Commit the spike + verdict.**

```bash
git add spikes/2026-07-16-hitl-on-mcp/
git commit -m "spike(copilot): HITL on MCP-mounted Agno tool — verdict recorded"
```

**Feeds:** Chunk 4 (Agno scaffold HITL) and Plan 2 §4.2.

### Task 0B: Spike — multi-artifact EmitResult shape

**Files:**
- Read: `packages/sdk-py/dna/emit/__init__.py` (`EmitResult`, `extract_instructions`, the byte-equal assertion), `scaffold.py`
- Create: `spikes/2026-07-16-multi-artifact-emit/NOTES.md`

- [ ] **Step 1: Map the current single-artifact contract.** Document `EmitResult{artifact, filename}` and how `test_emit_contract.py` asserts `extract_instructions(artifact) == ctx.instructions`.

- [ ] **Step 2: Design the multi-artifact shape.** A copilot emits N files (agent module + AG-UI serve + route). Propose `EmitResult.artifacts: list[EmitArtifact{path, content, role}]` (back-compat: single-artifact stays valid), and decide **which artifact carries the byte-equal instruction assertion** (the agent module).

- [ ] **Step 3: Record the shape + the harness change in NOTES.md** (what `test_emit_contract.py` must do for multi-artifact: assert byte-equal on the `role=agent` artifact; golden the rest).

- [ ] **Step 4: Commit.**

```bash
git add spikes/2026-07-16-multi-artifact-emit/
git commit -m "spike(copilot): multi-artifact EmitResult shape + byte-equal target"
```

**Feeds:** Chunk 2.

---

## Chunk 1: The `Copilot` Kind

### Task 1: Copilot Kind schema (Py) + parity twin

**Files:**
- Create: `packages/sdk-py/dna/extensions/helix/kinds/copilot.kind.yaml`
- Test: `packages/sdk-py/tests/emit/test_copilot_emit.py`
- Parity: the TS twin loader (confirm how helix kinds mirror to TS)

- [ ] **Step 1: Write the failing test — the Kind loads + validates a minimal Copilot doc.**

```python
def test_copilot_kind_loads_minimal():
    doc = load_kind_doc("Copilot", {
        "mounts": [{"id": "memory", "agent": "memory-agent", "path": "/agui"}],
        "serving": {"transport": "ag-ui"},
    })
    assert doc.spec.mounts[0].path == "/agui"
    assert doc.spec.serving.transport == "ag-ui"
```

- [ ] **Step 2: Run it — expect FAIL (Kind unknown).**
Run: `uv run pytest packages/sdk-py/tests/emit/test_copilot_emit.py::test_copilot_kind_loads_minimal -v`
Expected: FAIL (no such Kind `Copilot`).

- [ ] **Step 3: Author `copilot.kind.yaml`** with schemas for all seven fields: `mounts[]{id, agent(ref), path}` (required), `serving{transport}` (required), and optional `tenant{propagate}`, `hitl{approval_card{title, details_from, reason_from}}`, `knowledge{collections[](ref)}`, `frontend{console, panels[], suggested_prompts[]}`, `workflow{chain[]}`. Follow the shape of an existing `*.kind.yaml` (e.g. `tool.kind.yaml`).

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Add validation tests** — required-field failures (no `mounts` → error; unknown `transport` → error); optional fields absent → valid (a pure-action copilot with no `knowledge`).

- [ ] **Step 6: Run all + commit.**

```bash
git add packages/sdk-py/dna/extensions/helix/kinds/copilot.kind.yaml packages/sdk-py/tests/emit/test_copilot_emit.py
git commit -m "feat(kind): Copilot Kind — servable-copilot binder over Agent/Tool/MCPFederation"
```

- [ ] **Step 7: Parity twin** — mirror the Kind to TS per the descriptor-parity convention; run the descriptor-hash parity test. Commit.

---

## Chunk 2: Multi-artifact EmitResult (per Spike 0B)

### Task 2: Multi-artifact emit port

**Files:**
- Modify: `packages/sdk-py/dna/emit/__init__.py`, `scaffold.py`
- Modify: `packages/sdk-py/tests/emit/test_emit_contract.py`
- Parity: `packages/sdk-ts/src/emit/*`

- [ ] **Step 1: Write the failing test — an emitter can return >1 artifact, byte-equal asserted on the agent artifact.**

```python
def test_multi_artifact_emit_result():
    res = EmitResult(artifacts=[
        EmitArtifact(path="agent.py", content=agent_src, role="agent"),
        EmitArtifact(path="serve.py", content=serve_src, role="serving"),
    ])
    assert extract_instructions(res.artifact_for("agent")) == ctx.instructions
    assert {a.role for a in res.artifacts} == {"agent", "serving"}
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement `EmitArtifact` + `EmitResult.artifacts` (back-compat: `artifact`/`filename` still work as a single `role=agent` artifact).** Per Spike 0B's recorded shape.

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Update `test_emit_contract.py`** to assert byte-equal on the `role=agent` artifact for multi-artifact emitters; keep single-artifact assertions unchanged.

- [ ] **Step 6: TS twin + parity. Commit.**

```bash
git commit -am "feat(emit): multi-artifact EmitResult (back-compat single) + byte-equal on agent role"
```

---

## Chunk 3: EmitContext projection

### Task 3: Project mcp_servers / hitl-intent / inbound-tenant / knowledge

**Files:**
- Modify: `packages/sdk-py/dna/emit/__init__.py` (`EmitContext`, the projection that today drops these)
- Test: `packages/sdk-py/tests/emit/test_copilot_emit.py`

- [ ] **Step 1: Write failing tests — the projection now carries what it used to drop.**

```python
def test_emitcontext_projects_mcp_servers():
    ctx = build_emit_context(copilot_doc_with_mcp_federation)
    assert ctx.mcp_servers[0].transport == "streamable-http"

def test_emitcontext_projects_hitl_intent():
    ctx = build_emit_context(copilot_doc_with_confirm_tool)
    assert ctx.tools_requiring_confirmation == {"remember", "forget"}

def test_emitcontext_projects_knowledge_optional():
    assert build_emit_context(pure_action_copilot).knowledge == []  # RAG optional
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Extend `EmitContext`** with `mcp_servers` (from `Agent.spec.mcp_servers` + `MCPFederation` docs: transport/url/auth/allowed_tools), `tools_requiring_confirmation` (from `Tool.requires_confirmation`), `tenant_propagate`, `knowledge` refs. Stop dropping them in the projection.

- [ ] **Step 4: Run — expect PASS. Add the negative: `knowledge` empty when undeclared; `mcp_servers` empty when none.**

- [ ] **Step 5: TS twin + parity. Commit.**

```bash
git commit -am "feat(emit): project mcp_servers/hitl-intent/tenant/knowledge into EmitContext"
```

---

## Chunk 4: Agno `copilot` scaffold case (HITL per Spike 0A)

### Task 4: Emit the servable Agno `/agui` app

**Files:**
- Create: `packages/sdk-py/dna/emit/scaffolds/agno/copilot.py.tmpl`
- Modify: `packages/sdk-py/dna/emit/agno.py`
- Test: `packages/sdk-py/tests/emit/test_copilot_emit.py` (golden)

- [ ] **Step 1: Write the failing golden test — emitting a minimal Copilot yields a byte-stable servable app.**

```python
def test_agno_copilot_scaffold_golden():
    res = AgnoEmitter().emit(memory_copilot_ctx)
    assert res.artifact_for("agent") == read_golden("agno/copilot_agent.py")
    assert res.artifact_for("serving") == read_golden("agno/copilot_serve.py")
    assert extract_instructions(res.artifact_for("agent")) == memory_copilot_ctx.instructions
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Write the scaffold template** emitting: the Agno `Agent(model, instructions, tools, knowledge?, session_state, db)`; the **MCP-tool mount** (`MCPTools(url, transport)` from `ctx.mcp_servers`); the **inbound-tenant derivation** (request headers → run-state, tools read via `RunContext.session_state` — NOT a propagate_tenant freebie); the **AG-UI serving** (AgentOS `AGUI` subclass → `/agui`); and **HITL per Spike 0A** — if 0A=YES, gate the MCP tool; if 0A=NO, emit a **local wrapper tool** carrying `external_execution` that calls the MCP write. Tool bodies for non-HITL remain stubs (per-app fill).

- [ ] **Step 4: Generate + eyeball the golden, then freeze it. Run — expect PASS.**

- [ ] **Step 5: Integration test** — the emitted app imports, mounts `/agui`, and (with a fake MCP) a `remember` turn pauses for HITL. Assert the pause/resume shape matches the aap-kb reference.

- [ ] **Step 6: TS parity note** — backend scaffold parity Py↔TS (byte-identical template). Commit.

```bash
git commit -am "feat(emit): Agno copilot scaffold — servable /agui (mount+tenant+HITL) + golden"
```

---

## Subsequent chunks (separate plans — do NOT build here)

- **Plan 2 — DNA Cloud consumer** (`dna-cloud`): author the `.dna/dna-cloud/copilots/memory.yaml`, emit it via this Agno scaffold, wire the CopilotKit console + MCP-token acquisition. Written after Chunks 0–4 land + the spikes resolve.
- **Plan 3 — fill-out:** MS Agent Framework scaffold case (+ `workflow` capability for foundry's workflow-HITL); the shared CopilotKit frontend scaffold + per-runtime resume-adapter; the `MCPFederation` read/write + min-role RBAC extension; foundry/aap-kb retrofit validation.

---

## Definition of done (this plan)

- Both spikes recorded with verdicts driving Chunk 4.
- `Copilot` Kind loads/validates (Py + TS parity).
- Multi-artifact `EmitResult` (back-compat) with byte-equal on the agent artifact.
- `EmitContext` projects mcp_servers/hitl-intent/tenant/knowledge (no longer dropped).
- Agno `copilot` scaffold emits a servable `/agui` app that mounts the DNA MCP, derives inbound tenant, and gates writes per Spike 0A — under a frozen golden + an integration test.
- `test_emit_contract.py` green (single + multi-artifact); descriptor-hash parity green.
