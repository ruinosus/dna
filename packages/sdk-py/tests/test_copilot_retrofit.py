"""Retrofit validation (absorption phase 7, design §8 step 7).

Proves DNA's **single-evolution-point** thesis: two `Copilot` definitions shaped
after the two hand-built reference apps — a Microsoft Agent Framework helpdesk
(``helpdesk-copilot``, a triage→retrieve→resolve→escalate workflow over an
RBAC-governed MCP registry) and an Agno knowledge/RFP analyst (``rfp-copilot``, a
corpus + tool-level ``external_execution`` HITL) — are emitted and asserted to
**reproduce each reference's load-bearing servable shape**.

The fixtures live in the ``retrofit`` scope of ``examples/emitting-to-a-runtime/
.dna`` (neutral-named — the two references are structural, not the vendor code).
This asserts STRUCTURE (the load-bearing identifiers/idioms each reference
hand-wrote), not a full byte-diff of the app — per-app bodies (tool impls,
per-step instructions, IdP/OBO, retrieval store, canvas) are documented as PER-APP
in ``docs/design/2026-07-16-copilot-retrofit-findings.md``.

Each assertion block is tagged CONVERGES / PER-APP / GAP to mirror the findings
table. A GAP asserted here is a KNOWN limitation pinned by the test so it can't
silently regress or silently "become fixed" without updating the report.
"""
from __future__ import annotations

import pathlib
import py_compile
import tempfile

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "retrofit"


def _compiles(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        path = fh.name
    try:
        py_compile.compile(path, doraise=True)
        return True
    except py_compile.PyCompileError:
        return False


@pytest.fixture()
def mi():
    from dna.kernel import Kernel

    return Kernel.quick(_SCOPE, base_dir=_BASE)


# ════════════════════════════════════════════════════════════════════════════
# Reference A — foundry-assured (Microsoft Agent Framework): the /helpdesk
# workflow, the request_info escalation, the RBAC MCP registry, tenant, serving.
# Emitted via the `agent-framework` target from `helpdesk-copilot`.
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def helpdesk(mi):
    from dna.emit import build_copilot_context
    from dna.emit.agent_framework import AgentFrameworkEmitter

    ctx = build_copilot_context(
        mi, "helpdesk-copilot", model="azure/gpt-4o", provider="azure"
    )
    res = AgentFrameworkEmitter().emit(ctx)
    return ctx, res


def test_helpdesk_emits_two_artifacts_that_compile(helpdesk):
    """CONVERGES — a servable backend: an agent module + an AG-UI serving app."""
    _ctx, res = helpdesk
    assert {a.role for a in res.artifacts} == {"agent", "serving"}
    assert res.target == "agent-framework"
    assert _compiles(res.artifact_for("agent"))
    assert _compiles(res.artifact_for("serving"))


def test_helpdesk_agent_build_via_foundry_as_agent(helpdesk):
    """CONVERGES — the foundry reference builds every step with
    ``FoundryChatClient(...).as_agent(...)`` (app/workflow/agents.py)."""
    _ctx, res = helpdesk
    agent = res.artifact_for("agent")
    assert "from agent_framework.foundry import FoundryChatClient" in agent
    assert ".as_agent(" in agent


def test_helpdesk_instructions_byte_equal_composed_prompt(mi, helpdesk):
    """CONVERGES — Soul + Guardrail + instruction collapse to one flat prompt,
    carried byte-equal (the DNA-only value the retrofit measures)."""
    from dna.emit.agent_framework import AgentFrameworkEmitter

    _ctx, res = helpdesk
    recovered = AgentFrameworkEmitter().extract_instructions(res.artifact_for("agent"))
    assert recovered == mi.build_prompt("helpdesk-agent")
    # composition really happened — the Soul persona is inside the flat prompt.
    assert "Helpdesk Concierge" in recovered


def test_helpdesk_reproduces_workflow_builder_chain(helpdesk):
    """CONVERGES — the foundry reference's ``build_helpdesk_workflow``:
    ``WorkflowBuilder(...).add_chain([triage, retrieve, resolve, escalate])``
    with one Foundry agent-executor per step (app/workflow/graph.py)."""
    _ctx, res = helpdesk
    agent = res.artifact_for("agent")
    assert "def build_triage_agent() -> Agent:" in agent
    assert "def build_retrieve_agent() -> Agent:" in agent
    assert "def build_resolve_agent() -> Agent:" in agent
    assert "WorkflowBuilder(" in agent
    assert ".add_chain([triage, retrieve, resolve, escalate])" in agent
    assert "def build_workflow() -> Workflow:" in agent


def test_helpdesk_reproduces_request_info_escalation(helpdesk):
    """CONVERGES — the foundry reference's workflow-level HITL: an
    ``EscalationExecutor(Executor)`` that calls ``ctx.request_info(...)`` in its
    ``@handler`` and acts in a ``@response_handler`` (app/workflow/escalation.py)
    — NOT a tool gate (the AG-UI workflow adapter double-emits TOOL_CALL_START)."""
    _ctx, res = helpdesk
    agent = res.artifact_for("agent")
    assert "class EscalationExecutor(Executor):" in agent
    assert 'super().__init__(id="escalate")' in agent
    assert "await ctx.request_info(request_data=text, response_type=bool)" in agent
    assert "@response_handler" in agent
    # writes gated at the workflow level → the MCP mount drops to never_require.
    assert "approval_mode='never_require'," in agent
    assert "approval_mode={" not in agent


def test_helpdesk_reproduces_rbac_mcp_mount(helpdesk):
    """CONVERGES (allowlist) / GAP (role floor) — the foundry McpServer registry
    (app/agents/mcp/registry.py) governs read/write tool split + per-tool role
    floors. The emitted ``MCPStreamableHTTPTool`` mount reproduces the
    allowlist + the read/write approval intent, but DROPS the min_role/
    min_role_write role FLOORS (documented GAP — EmitMcpServer projects
    allowed_tools only; see findings §Gaps)."""
    ctx, res = helpdesk
    agent = res.artifact_for("agent")
    # CONVERGES: the RBAC-aware mount — allowlist carried verbatim, over the
    # streamable-http registry the federation declares.
    assert "from agent_framework import MCPStreamableHTTPTool" in agent
    assert "name='mcp_helpdesk-mcp'," in agent
    assert "url='https://mcp.helpdesk.example/agui'," in agent
    assert "allowed_tools=['open-ticket', 'search-runbooks']," in agent
    # the federation DECLARES RBAC (read/write split + role floors) …
    fed = ctx.mcp_servers[0]
    assert fed.ref == "helpdesk-mcp"
    assert sorted(fed.allowed_tools) == ["open-ticket", "search-runbooks"]
    # … but GAP: the role FLOORS are not projected onto EmitMcpServer, so they
    # cannot reach the emitted mount. Pin the gap so it can't silently drift.
    assert not hasattr(fed, "min_role")
    assert "min_role" not in agent
    assert "min_role_write" not in agent


def test_helpdesk_reproduces_inbound_tenant_bridge(helpdesk):
    """CONVERGES (mechanism) / PER-APP (source) — the emitted app carries the
    inbound→outbound tenant bridge (ContextVar + header_provider + serving
    middleware). The foundry reference derives tenant from the Entra ``tid``
    claim + an OBO credential broker (app/core/tenant.py) rather than X-DNA-*
    headers — that IdP/token derivation is PER-APP; the emitter's DNA-native
    header convention is the vendor-neutral default."""
    _ctx, res = helpdesk
    agent = res.artifact_for("agent")
    serving = res.artifact_for("serving")
    assert "contextvars.ContextVar" in agent
    assert "def _tenant_header_provider(_existing: dict) -> dict:" in agent
    assert "header_provider=_tenant_header_provider," in agent
    assert '"X-DNA-Tenant"' in agent
    assert '@app.middleware("http")' in serving
    assert "set_request_tenant(tenant_from_headers(request.headers))" in serving


def test_helpdesk_reproduces_agui_serving(helpdesk):
    """CONVERGES (serving fn) / PER-APP (path + stream_fix) — the foundry
    reference mounts the workflow via ``add_agent_framework_fastapi_endpoint``
    (app/domains.py). PER-APP: the path (``/helpdesk`` vs the emitter's ``/agui``)
    and the ``OrderedAgentFrameworkWorkflow`` rc5 stream-order workaround
    (app/workflow/stream_fix.py — a version-pinned throwaway, design §1)."""
    _ctx, res = helpdesk
    serving = res.artifact_for("serving")
    assert (
        "from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint"
        in serving
    )
    assert "add_agent_framework_fastapi_endpoint(" in serving
    assert "AgentFrameworkWorkflow(workflow_factory=build_workflow)" in serving
    assert 'path="/agui",' in serving
    # PER-APP shape the emitter does NOT (and should not) reproduce:
    assert "OrderedAgentFrameworkWorkflow" not in serving  # stream_fix is per-app
    assert "request_info" not in serving  # the stream_fix suppression is per-app


# ════════════════════════════════════════════════════════════════════════════
# Reference B — the Agno KB reference app (Agno + AgentOS): the build_agent
# factory, the MCPTools mount, the knowledge binding, AG-UI serving, tenant
# injection, tool-level external_execution HITL. Emitted via `agno` from
# `rfp-copilot`.
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def rfp(mi):
    from dna.emit import build_copilot_context
    from dna.emit.agno import AgnoEmitter

    ctx = build_copilot_context(
        mi, "rfp-copilot", model="azure/gpt-4o", provider="azure"
    )
    res = AgnoEmitter().emit(ctx)
    return ctx, res


def test_rfp_emits_two_artifacts_that_compile(rfp):
    """CONVERGES — an agent module + an AG-UI serving app."""
    _ctx, res = rfp
    assert {a.role for a in res.artifacts} == {"agent", "serving"}
    assert res.target == "agno"
    assert _compiles(res.artifact_for("agent"))
    assert _compiles(res.artifact_for("serving"))


def test_rfp_agent_build_factory(rfp):
    """CONVERGES — the KB reference's ``build_agent`` factory: an
    ``Agent(name, model=OpenAILike(id=...), instructions, tools, ...,
    session_state, add_session_state_to_context=True, markdown=True)``
    (apps/agent/src/agents/factory.py). PER-APP: db (InMemoryDb vs PostgresDb),
    api_key/base_url, skills."""
    _ctx, res = rfp
    agent = res.artifact_for("agent")
    assert "from agno.agent import Agent" in agent
    assert "from agno.models.openai import OpenAILike" in agent
    assert "def build_agent(session_state: dict | None = None) -> Agent:" in agent
    assert "model=OpenAILike(id='azure/gpt-4o')," in agent
    assert "add_session_state_to_context=True," in agent
    assert "markdown=True," in agent


def test_rfp_instructions_byte_equal(mi, rfp):
    """CONVERGES — the mounted agent's composed prompt carried byte-equal."""
    from dna.emit.agno import AgnoEmitter

    _ctx, res = rfp
    recovered = AgnoEmitter().extract_instructions(res.artifact_for("agent"))
    assert recovered == mi.build_prompt("rfp-analyst")


def test_rfp_reproduces_mcp_tools_mount(rfp):
    """CONVERGES — the KB reference's ``mcp:`` mount:
    ``MCPTools(url=..., transport="streamable-http")``, built-not-connected
    (apps/agent/src/agents/factory.py::_build_mcp_tools)."""
    _ctx, res = rfp
    agent = res.artifact_for("agent")
    assert "from agno.tools.mcp import MCPTools" in agent
    assert "url='https://mcp.docs.example/agui'," in agent
    assert "transport='streamable-http'," in agent
    assert "tools=_mcp_tools()," in agent


def test_rfp_reproduces_knowledge_binding(rfp):
    """CONVERGES (binding seam) / PER-APP (retrieval impl) — the KB reference
    binds ``knowledge=build_knowledge(collection)`` + ``search_knowledge=
    knowledge is not None`` (factory.py). The emitter now reproduces that BINDING
    SEAM (the ``_knowledge()`` factory + the two kwargs) carrying the DNA
    collection refs; the vector store + embedder behind it (PgVector +
    AzureOpenAIEmbedder, apps/agent/src/services/collections.py) is PER-APP (§6.3).

    (Regression guard for the f-copilot-retrofit knowledge-binding fix — before
    it, ctx.knowledge was silently dropped from the Agno backend.)"""
    ctx, res = rfp
    assert ctx.knowledge == ["rfp-corpus"]
    agent = res.artifact_for("agent")
    assert "def _knowledge() -> object | None:" in agent
    assert "knowledge = _knowledge()" in agent
    assert "knowledge=knowledge," in agent
    assert "search_knowledge=knowledge is not None," in agent
    # the collection ref rides into the wiring point.
    assert "rfp-corpus" in agent


def test_rfp_reproduces_tool_level_hitl(rfp):
    """CONVERGES (contract) / DELIBERATE DELTA (locus) — the KB reference gates a
    LOCAL ``@tool(external_execution=True)`` (record_rfp_verdict) and resumes via
    ``acontinue_run``. The emitter gates the write DIRECTLY on the remote MCP
    tool (``external_execution_required_tools``, Spike 0A: gate-remote-directly)
    — same pause/resume contract, gate at the remote tool instead of a local
    wrapper (design §6.1 B2)."""
    ctx, res = rfp
    assert ctx.tools_requiring_confirmation == {"record-verdict"}
    agent = res.artifact_for("agent")
    assert "external_execution_required_tools=['record-verdict']" in agent
    # no local wrapper tool — the gate rides on the remote MCP tool itself.
    assert "def record_verdict(" not in agent


def test_rfp_reproduces_agui_serving_and_tenant(rfp):
    """CONVERGES (AGUI subclass + /agui + inbound tenant) / DELIBERATE DELTA
    (host) — the KB reference subclasses ``agno.os.interfaces.agui.AGUI``, derives
    tenant via ``tenant_from_request``/``inject_tenant`` into
    ``run_input.state["tenant"]`` (apps/agent/src/core/agui_hitl.py). PER-APP:
    header names (X-DNA-* vs the app's headers) + the ``grants`` RBAC injection.
    DELIBERATE DELTA: the emitter assembles via ``AgentOS.get_app()`` where the
    reference mounts the AGUI router on a plain FastAPI (both expose POST /agui)."""
    _ctx, res = rfp
    serving = res.artifact_for("serving")
    assert "from agno.os.interfaces.agui import AGUI" in serving
    assert "class TenantAGUI(AGUI):" in serving
    assert "def tenant_from_request(request: Request)" in serving
    assert "def inject_tenant(run_input: RunAgentInput, tenant: dict)" in serving
    assert 'run_input.state["tenant"] = tenant' in serving
    assert '@router.post("/agui", name="run_agent")' in serving


def test_rfp_no_hand_rolled_resume_glue(rfp):
    """GAP-CLOSED-BY-VERSION — the KB reference hand-wrote ~391 lines of resume +
    de-dup glue (agui_hitl.py: run_agent_hitl / filter_reemitted_text). The
    emitter relies on Agno ≥2.7 resuming ``external_execution`` gates natively in
    its AG-UI router, so that glue is NOT reproduced — a convergence WIN (less
    code) contingent on the Agno version (design §1, risk 2)."""
    _ctx, res = rfp
    serving = res.artifact_for("serving")
    agent = res.artifact_for("agent")
    assert "filter_reemitted_text" not in serving and "filter_reemitted_text" not in agent
    assert "run_agent_hitl" not in serving and "run_agent_hitl" not in agent


# ── the shared CopilotKit frontend also emits from the rfp-copilot ───────────


def test_rfp_frontend_console_emits(mi):
    """CONVERGES — the copilot's ``frontend`` block emits the shared CopilotKit
    console + the per-runtime (agno) resume adapter (both reference web apps are
    ~95% generic CopilotKit v2, design §6.2)."""
    from dna.emit import build_copilot_context
    from dna.emit.frontend import emit_frontend_console, has_frontend

    ctx = build_copilot_context(mi, "rfp-copilot", model="azure/gpt-4o")
    assert has_frontend(ctx)
    res = emit_frontend_console(ctx, runtime="agno")
    paths = {a.path for a in res.artifacts}
    assert "components/copilot/console.tsx" in paths
    assert "lib/copilot/resume-adapter.ts" in paths
    assert res.target == "copilotkit-agno"
