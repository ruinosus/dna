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
| `.dna/dna-development/spikes/sp-copilot-hitl-on-mcp.yaml` | Spike A (tracked Spike Kind, via CLI): does Agno `external_execution` fire on an `MCPTools` tool? | create |
| `.dna/dna-development/spikes/sp-copilot-multi-artifact-emit.yaml` | Spike B (tracked Spike Kind, via CLI): the multi-artifact `EmitResult` shape + byte-equal target | create |
| `scratch/copilot-spikes/` | Throwaway spike code (scratch; findings recorded on the Spike docs) | create |
| `packages/sdk-py/dna/extensions/helix/kinds/copilot.kind.yaml` | The `Copilot` Kind schema (mounts/serving/hitl/knowledge/frontend/tenant) — **no `workflow` field** (deferred to Plan 3) | create |
| `packages/sdk-ts/src/extensions/helix/kinds/copilot.kind.yaml` | Byte-identical TS twin (mandatory — `test_descriptor_hash_parity.py` enforces both sides) | create |
| `packages/sdk-py/dna/emit/__init__.py` (`build_copilot_context`) | Resolve a `Copilot` doc → `EmitContext` (the Chunk 1↔3 seam) | modify |
| `packages/sdk-py/dna/emit/__init__.py` | Multi-artifact `EmitResult`; `EmitContext` projection of mcp_servers/hitl/tenant/knowledge | modify |
| `packages/sdk-py/dna/emit/scaffold.py` | Multi-artifact scaffold support | modify |
| `packages/sdk-py/dna/emit/agno.py` | The Agno `copilot` scaffold case (serving + mount + inbound-tenant + tool-HITL) | modify |
| `packages/sdk-py/dna/emit/scaffolds/agno/copilot.py.tmpl` | The emitted servable `/agui` app template | create |
| `packages/sdk-ts/src/emit/*` | TS twins of the port + projection (byte-equal backend) | modify |
| `packages/sdk-py/tests/test_copilot_emit.py` | Golden + projection + context tests (flat `tests/`, `test_emit_<target>` convention) | create |
| `packages/sdk-py/tests/test_emit_contract.py` | Extend for multi-artifact (the real generic contract suite) | modify |
| `packages/sdk-ts/tests/emit-contract.test.ts` | TS contract twin (flat `tests/`) | modify |

> **Verified layout (do not deviate):** tests are **flat** in `packages/sdk-py/tests/` — there is **no** `tests/emit/`; the contract harness is `tests/test_emit_contract.py`. Kinds live in `extensions/helix/kinds/`; the TS twin is byte-identical and mandatory. Scaffold templates are `scaffolds/agno/*.py.tmpl`. Follow these patterns — do not restructure.

---

## Chunk 0: Phase-0 de-risk spikes (GATING — do first)

These two investigations determine the design of Chunks 3–4. Do not detail-build the Agno scaffold's HITL or the emit-port until these resolve.

### Task 0A: Spike — HITL on an MCP-mounted Agno tool

**Files:**
- Create (tracked Spike Kind, via CLI): `sp-copilot-hitl-on-mcp`
- Scratch code: `scratch/copilot-spikes/hitl_on_mcp/` (throwaway; findings live on the Spike doc)

- [ ] **Step 1: File the Spike doc.**

```bash
dna sdlc spike create sp-copilot-hitl-on-mcp \
  --question "Does Agno external_execution fire on an MCPTools-provided tool, or must HITL wrap a local tool?" \
  --feature f-dna-copilot-emitter --time-box 4 --scope dna-development
dna sdlc spike start sp-copilot-hitl-on-mcp --scope dna-development
```

- [ ] **Step 2: Stand up a minimal MCP server with one write tool** under `scratch/copilot-spikes/hitl_on_mcp/`. A tiny FastMCP server exposing `remember(text) -> str` (streamable-http). Reuse the `aap-knowledge-base` `mcp:` reference `MCPTools(url, transport="streamable-http")` (`apps/agent/src/agents/factory.py:90`, `_build_mcp_tools`).

- [ ] **Step 3: Build an Agno agent that mounts it and try to gate it.** Attempt `@tool(external_execution=True)` semantics on the MCP-provided `remember`. Run a turn that calls it and inspect `agent.get_last_run_output(session_id=…).tools_awaiting_external_execution` (the aap-kb pattern — note the accessor takes `session_id`, `core/agui_hitl.py:85`).

- [ ] **Step 4: Record the verdict on the Spike doc.** (a) YES → the emitter can gate the remote tool directly. (b) NO → the emitter emits a **local wrapper tool** that calls the MCP tool, with `external_execution` on the wrapper. Answer the spike:

```bash
dna sdlc spike answer sp-copilot-hitl-on-mcp \
  --findings "<yes/no + evidence>" \
  --recommendation "<gate-remote | local-wrapper>" --scope dna-development
```

- [ ] **Step 5: Commit (Spike doc + scratch, or discard scratch).**

```bash
git add .dna/dna-development/spikes/sp-copilot-hitl-on-mcp.yaml scratch/copilot-spikes/hitl_on_mcp/
git commit -m "spike(copilot): HITL on MCP-mounted Agno tool — verdict recorded"
```

**Feeds:** Chunk 4 (Agno scaffold HITL) and Plan 2 §4.2.

### Task 0B: Spike — multi-artifact EmitResult shape

**Files:**
- Read: `packages/sdk-py/dna/emit/__init__.py` (`EmitResult`, `EmitterPort.extract_instructions`, the byte-equal assertion at `tests/test_emit_contract.py:55`), `scaffold.py`
- Create (tracked Spike Kind, via CLI): `sp-copilot-multi-artifact-emit`

- [ ] **Step 1: File + start the Spike doc** (`dna sdlc spike create/start sp-copilot-multi-artifact-emit --feature f-dna-copilot-emitter --scope dna-development`).

- [ ] **Step 2: Map the current single-artifact contract.** Document `EmitResult{artifact, filename}` and how `tests/test_emit_contract.py` asserts `emitter.extract_instructions(result.artifact) == ctx.instructions` (a **method** on the emitter, not a free function).

- [ ] **Step 3: Design the multi-artifact shape.** A copilot emits N files (agent module + AG-UI serve + route). Propose `EmitResult.artifacts: list[EmitArtifact{path, content, role}]` (back-compat: single-artifact stays valid via a `role="agent"` default), and decide **which artifact carries the byte-equal assertion** (the `role="agent"` module) + **how N artifacts reach disk** (the `dna emit` CLI writer — see `packages/cli/tests/test_emit_cmd.py`).

- [ ] **Step 4: Answer the spike** with the recorded shape + the harness change + the write-out plan.

- [ ] **Step 5: Commit.**

```bash
git add .dna/dna-development/spikes/sp-copilot-multi-artifact-emit.yaml
git commit -m "spike(copilot): multi-artifact EmitResult shape + byte-equal target + write-out"
```

**Feeds:** Chunk 2 (+ the CLI write-out).

---

## Chunk 1: The `Copilot` Kind

### Task 1: Copilot Kind schema (Py) + parity twin

**Files:**
- Create: `packages/sdk-py/dna/extensions/helix/kinds/copilot.kind.yaml`
- Test: `packages/sdk-py/tests/test_copilot_emit.py`
- Parity: `packages/sdk-ts/src/extensions/helix/kinds/copilot.kind.yaml` (byte-identical; enforced by `test_descriptor_hash_parity.py`)

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
Run: `uv run pytest packages/sdk-py/tests/test_copilot_emit.py::test_copilot_kind_loads_minimal -v`
Expected: FAIL (no such Kind `Copilot`).

- [ ] **Step 3: Author `copilot.kind.yaml`** with schemas for **six** fields (NOT `workflow` — deferred to Plan 3, agent-framework-only): `mounts[]{id, agent(ref), path}` (required), `serving{transport}` (required), and optional `tenant{propagate}`, `hitl{approval_card{title, details_from, reason_from}}`, `knowledge{collections[](ref)}`, `frontend{console, panels[], suggested_prompts[]}`. Follow the shape of `tool.kind.yaml` (same dir).

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Add validation tests** — required-field failures (no `mounts` → error; unknown `transport` → error); optional fields absent → valid (a pure-action copilot with no `knowledge`).

- [ ] **Step 6: Run all + commit.**

```bash
git add packages/sdk-py/dna/extensions/helix/kinds/copilot.kind.yaml packages/sdk-py/tests/test_copilot_emit.py
git commit -m "feat(kind): Copilot Kind — servable-copilot binder over Agent/Tool/MCPFederation"
```

- [ ] **Step 7: Parity twin (MANDATORY).** Create the byte-identical `packages/sdk-ts/src/extensions/helix/kinds/copilot.kind.yaml`; run `uv run pytest packages/sdk-py/tests/test_descriptor_hash_parity.py -v` (it auto-globs `*/kinds/*.kind.yaml` and fails if either side is missing or differs). Commit.

---

## Chunk 2: Multi-artifact EmitResult (per Spike 0B)

### Task 2: Multi-artifact emit port

**Files:**
- Modify: `packages/sdk-py/dna/emit/__init__.py`, `scaffold.py`
- Modify: `packages/sdk-py/tests/test_emit_contract.py`
- Modify: the `dna emit` CLI writer + `packages/cli/tests/test_emit_cmd.py` (multi-file write-out)
- Parity: `packages/sdk-ts/src/emit/*`, `packages/sdk-ts/tests/emit-contract.test.ts`

- [ ] **Step 1: Write the failing test — an emitter can return >1 artifact, byte-equal asserted on the agent artifact.** Note `extract_instructions` is an **emitter method** (`emitter.extract_instructions(artifact)`), not a free function.

```python
def test_multi_artifact_emit_result():
    res = EmitResult(artifacts=[
        EmitArtifact(path="agent.py", content=agent_src, role="agent"),
        EmitArtifact(path="serve.py", content=serve_src, role="serving"),
    ])
    emitter = AgnoEmitter()
    assert emitter.extract_instructions(res.artifact_for("agent")) == ctx.instructions
    assert {a.role for a in res.artifacts} == {"agent", "serving"}
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement `EmitArtifact` + `EmitResult.artifacts` (back-compat: `artifact`/`filename` still work as a single `role="agent"` artifact via a property).** Per Spike 0B's recorded shape.

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Update `tests/test_emit_contract.py`** to assert byte-equal via `emitter.extract_instructions(res.artifact_for("agent"))` for multi-artifact emitters; keep the single-artifact assertion (`emitter.extract_instructions(result.artifact)`) unchanged.

- [ ] **Step 6: Multi-file write-out.** Extend the `dna emit` CLI to write every `EmitResult.artifacts` entry (`path`+`content`) to disk (single-artifact path unchanged); add a `test_emit_cmd.py` case asserting N files land. Per Spike 0B's write-out plan.

- [ ] **Step 7: TS twin + parity (`emit-contract.test.ts`). Commit.**

```bash
git commit -am "feat(emit): multi-artifact EmitResult (back-compat single) + byte-equal on agent role + CLI write-out"
```

---

## Chunk 3: Copilot → EmitContext (the Chunk 1↔4 seam) + projection

> **The missing seam (plan-review S2).** The existing front door is
> `build_emit_context(mi, agent, *, model, provider)` (`emit/__init__.py:271`) — keyed
> by an **Agent name**, resolved via `mi.find_agent(agent)`. A `Copilot` doc has a
> *mounted* agent plus `hitl`/`tenant`/`knowledge`/`serving` on the Copilot itself. We
> need a `build_copilot_context(mi, copilot_name)` that resolves the mounted agent's
> base ctx via the existing front door, then **enriches** it. Chunk 4 emits from *this*.

### Task 3a: `build_copilot_context` — resolve the mounted agent's base ctx

**Files:**
- Modify: `packages/sdk-py/dna/emit/__init__.py`
- Test: `packages/sdk-py/tests/test_copilot_emit.py`

- [ ] **Step 1: Failing test — a Copilot resolves to the mounted agent's base EmitContext.**

```python
def test_build_copilot_context_resolves_mounted_agent():
    ctx = build_copilot_context(mi, "memory-copilot", model="…", provider="…")
    assert ctx.name == "memory-agent"   # the mounted agent's base ctx
    assert ctx.instructions             # instructions come from the agent, unchanged
```

- [ ] **Step 2: Run — expect FAIL (no `build_copilot_context`).**

- [ ] **Step 3: Implement `build_copilot_context`** — load the Copilot doc, read `mounts[0].agent`, delegate to `build_emit_context(mi, that_agent, model=…, provider=…)` for the base ctx. (Keep the byte-equal instruction contract intact — instructions still come from the agent.)

- [ ] **Step 4: Run — expect PASS. Commit.**

### Task 3b: Enrich the ctx — project mcp_servers / hitl-intent / inbound-tenant / knowledge

**Files:**
- Modify: `packages/sdk-py/dna/emit/__init__.py` (`EmitContext` + `build_copilot_context` enrichment)
- Test: `packages/sdk-py/tests/test_copilot_emit.py`

- [ ] **Step 1: Write failing tests — the enriched ctx carries what the projection used to drop.**

```python
def test_copilot_ctx_projects_mcp_servers():
    ctx = build_copilot_context(mi, "memory-copilot", model="…", provider="…")
    assert ctx.mcp_servers[0].transport == "streamable-http"

def test_copilot_ctx_projects_hitl_intent():
    ctx = build_copilot_context(mi, "memory-copilot", model="…", provider="…")
    assert ctx.tools_requiring_confirmation == {"remember", "forget"}

def test_copilot_ctx_knowledge_optional():
    ctx = build_copilot_context(mi, "pure-action-copilot", model="…", provider="…")
    assert ctx.knowledge == []   # RAG optional
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Extend `EmitContext`** with `mcp_servers` (from the mounted `Agent.spec.mcp_servers` + referenced `MCPFederation` docs: transport/url/auth/allowed_tools — `models.py:376`, `federation/__init__.py`), `tools_requiring_confirmation` (from `Tool.requires_confirmation` — `tool.kind.yaml:111`), `tenant_propagate` (from the Copilot `tenant`/the federation `propagate_tenant`), `knowledge` refs. Enrich in `build_copilot_context`.

- [ ] **Step 4: Run — expect PASS. Add negatives: `knowledge`/`mcp_servers` empty when undeclared.**

- [ ] **Step 5: TS twin + parity. Commit.**

```bash
git commit -am "feat(emit): build_copilot_context + project mcp_servers/hitl-intent/tenant/knowledge"
```

---

## Chunk 4: Agno `copilot` scaffold case (HITL per Spike 0A)

### Task 4: Emit the servable Agno `/agui` app

> **This is the ~391-line `agui_hitl.py`-class glue the spec calls "the bulk of the
> work" — decomposed into four test→golden→commit slices, each its own golden slice,
> not one bundled step (plan-review S3).** All emit from `build_copilot_context` (Chunk 3).

**Files:**
- Create: `packages/sdk-py/dna/emit/scaffolds/agno/copilot.py.tmpl`
- Modify: `packages/sdk-py/dna/emit/agno.py`
- Test: `packages/sdk-py/tests/test_copilot_emit.py` (golden)

- [ ] **Task 4a — agent + `/agui` serving.** Failing golden: `res.artifact_for("agent") == read_golden("agno/copilot_agent.py")` and `res.artifact_for("serving") == read_golden("agno/copilot_serve.py")`; assert `AgnoEmitter().extract_instructions(res.artifact_for("agent")) == ctx.instructions`. Template emits the Agno `Agent(model, instructions, tools, session_state, db)` + the AgentOS `AGUI` subclass → `/agui`. Generate → eyeball → freeze golden → PASS → commit.

- [ ] **Task 4b — MCP-tool mount.** Failing golden slice: the emitted agent builds `MCPTools(url, transport="streamable-http")` from `ctx.mcp_servers`. Extend template → regen golden → PASS → commit.

- [ ] **Task 4c — inbound-tenant derivation.** Failing golden slice: the emitted serving layer derives tenant/`oid` from request headers into run-state, tools read via `RunContext.session_state` (NOT a `propagate_tenant` freebie; mirrors aap-kb `inject_tenant`). Extend → regen → PASS → commit.

- [ ] **Task 4d — HITL per Spike 0A.** Failing golden slice: if 0A=YES, the emitted agent gates the MCP write tool directly; if 0A=NO, it emits a **local wrapper tool** carrying `external_execution` that calls the MCP write. Non-HITL tool bodies stay stubs (per-app fill). Extend → regen → PASS → commit.

- [ ] **Task 4e — Integration test.** The emitted app imports, mounts `/agui`, and (with a fake MCP) a `remember` turn pauses for HITL; assert the pause/resume shape matches the aap-kb reference (`core/agui_hitl.py`). Commit.

- [ ] **Task 4f — TS parity.** Backend scaffold parity Py↔TS (byte-identical template + render context); run the emit parity/contract suite. Commit.

```bash
git commit -am "feat(emit): Agno copilot scaffold — servable /agui (mount+tenant+HITL) + goldens"
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
