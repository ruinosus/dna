"""Copilot emitter — Kind schema + (later) emit context/scaffold tests.

Chunk 1 (this file's first slice): the ``Copilot`` Kind — a servable-copilot
binder over Agent/Tool/MCPFederation. It ships as a record-plane descriptor
(``dna/extensions/helix/kinds/copilot.kind.yaml``), exactly like the
``Tool`` Kind (f-dna-tools-as-data) — data, not a class — and its spec is
validated against the descriptor's JSON Schema on parse.

``load_kind_doc`` is a thin test helper: it loads the shipped helix
descriptor for the given target Kind, synthesizes the DeclarativeKindPort the
kernel would register, and parses (== validates) a doc's spec through it. A
malformed spec raises (jsonschema ``required``/``enum`` violations surface as
``ValueError`` out of ``DeclarativeKindPort.parse``).
"""
from __future__ import annotations

import pathlib
import types

import pytest


def _kind_port(kind_name: str):
    """Synthesize the DeclarativeKindPort for a shipped helix descriptor."""
    from dna.kernel.descriptor_loader import load_descriptors
    from dna.kernel.meta import DeclarativeKindPort
    from dna.kernel.models import TypedKindDefinition

    for raw in load_descriptors("dna.extensions.helix"):
        if raw.get("spec", {}).get("target_kind") == kind_name:
            return DeclarativeKindPort.from_typed(TypedKindDefinition.from_raw(raw))
    raise KeyError(f"No helix descriptor registers target_kind={kind_name!r}")


def _ns(obj):
    """Recursively wrap dicts as attribute-accessible namespaces."""
    if isinstance(obj, dict):
        return types.SimpleNamespace(**{k: _ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_ns(v) for v in obj]
    return obj


def load_kind_doc(kind_name: str, spec: dict):
    """Load + validate a minimal doc of ``kind_name`` against its descriptor.

    Returns an attribute-accessible view of the parsed doc
    (``doc.spec.<field>``). Raises ``ValueError`` if the spec violates the
    descriptor's JSON Schema.
    """
    port = _kind_port(kind_name)
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": kind_name,
        "metadata": {"name": "test"},
        "spec": spec,
    }
    return _ns(port.parse(raw))


# ── Chunk 1 · Task 1: the Copilot Kind schema ──────────────────────────────


def test_copilot_kind_loads_minimal():
    doc = load_kind_doc("Copilot", {
        "mounts": [{"id": "memory", "agent": "memory-agent", "path": "/agui"}],
        "serving": {"transport": "ag-ui"},
    })
    assert doc.spec.mounts[0].path == "/agui"
    assert doc.spec.serving.transport == "ag-ui"


def test_copilot_kind_requires_mounts():
    """No ``mounts`` → schema error (a copilot must mount at least one agent)."""
    with pytest.raises(ValueError):
        load_kind_doc("Copilot", {"serving": {"transport": "ag-ui"}})


def test_copilot_kind_requires_serving():
    """No ``serving`` → schema error (a copilot must declare a transport)."""
    with pytest.raises(ValueError):
        load_kind_doc("Copilot", {
            "mounts": [{"id": "memory", "agent": "memory-agent", "path": "/agui"}],
        })


def test_copilot_kind_rejects_unknown_transport():
    """Unknown ``serving.transport`` → schema enum error."""
    with pytest.raises(ValueError):
        load_kind_doc("Copilot", {
            "mounts": [{"id": "memory", "agent": "memory-agent", "path": "/agui"}],
            "serving": {"transport": "carrier-pigeon"},
        })


def test_copilot_kind_optional_fields_absent_is_valid():
    """A pure-action copilot — no knowledge/hitl/tenant/frontend — is valid."""
    doc = load_kind_doc("Copilot", {
        "mounts": [{"id": "actions", "agent": "action-agent", "path": "/agui"}],
        "serving": {"transport": "ag-ui"},
    })
    assert not hasattr(doc.spec, "knowledge")
    assert doc.spec.mounts[0].agent == "action-agent"


def test_copilot_kind_accepts_full_optional_shape():
    """All six fields populated validate together (hitl/knowledge/frontend/tenant)."""
    doc = load_kind_doc("Copilot", {
        "mounts": [{"id": "memory", "agent": "memory-agent", "path": "/agui"}],
        "serving": {"transport": "ag-ui"},
        "tenant": {"propagate": True},
        "hitl": {"approval_card": {
            "title": "Confirm write",
            "details_from": "args.text",
            "reason_from": "args.reason",
        }},
        "knowledge": {"collections": ["knowledge-base"]},
        "frontend": {
            "console": "copilotkit",
            "panels": ["memory-timeline"],
            "suggested_prompts": ["What did I ask you to remember?"],
        },
    })
    assert doc.spec.tenant.propagate is True
    assert doc.spec.hitl.approval_card.title == "Confirm write"
    assert doc.spec.knowledge.collections[0] == "knowledge-base"
    assert doc.spec.frontend.console == "copilotkit"


# ── Chunk 3 · the Copilot → EmitContext seam ────────────────────────────────
#
# A live filesystem scope (``examples/emitting-to-a-runtime/.dna``) carries the
# copilot fixtures: ``memory-copilot`` mounts ``memory-agent`` (an MCP-mounted,
# HITL-gated agent) and ``pure-action-copilot`` mounts ``pure-action-agent``
# (one local tool, no MCP, no RAG). ``build_copilot_context`` resolves each
# Copilot doc to the mounted agent's base EmitContext and enriches it.

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"


@pytest.fixture()
def mi():
    from dna.kernel import Kernel

    return Kernel.quick(_SCOPE, base_dir=_BASE)


# ── Task 3a: build_copilot_context resolves the mounted agent's base ctx ─────


def test_build_copilot_context_resolves_mounted_agent(mi):
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(
        mi, "memory-copilot", model="azure/gpt-4o", provider="azure"
    )
    # The base ctx is the MOUNTED agent's — name + instructions come from it,
    # unchanged (the byte-equal instruction contract stays intact).
    assert ctx.name == "memory-agent"
    assert ctx.instructions == mi.build_prompt("memory-agent")


# ── Task 3b: enrich the ctx — mcp_servers / hitl-intent / tenant / knowledge ─


def test_copilot_ctx_projects_mcp_servers(mi):
    """The mounted agent's ``mcp_servers`` refs resolve to their MCPFederation
    docs, projected with the MCP client wire transport + effective allowlist."""
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "memory-copilot", model="azure/gpt-4o")
    assert len(ctx.mcp_servers) == 1
    fed = ctx.mcp_servers[0]
    assert fed.ref == "dna-mcp"
    assert fed.transport == "streamable-http"  # normalized from streamable_http
    assert fed.url == "https://mcp.dna.example/agui"
    assert fed.auth == {"kind": "bearer_env", "env": "DNA_MCP_TOKEN"}
    # agent allowlist ∩ federation allowlist.
    assert fed.allowed_tools == ["remember", "forget", "recall"]
    assert fed.propagate_tenant is True


def test_copilot_ctx_projects_hitl_intent(mi):
    """Tools the mounted agent gates (``requires_confirmation``) surface as the
    HITL-write intent — ``recall`` (read-only) is NOT gated."""
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "memory-copilot", model="azure/gpt-4o")
    assert ctx.tools_requiring_confirmation == {"remember", "forget"}


def test_copilot_ctx_projects_tenant_propagate(mi):
    """The Copilot ``tenant.propagate`` drives inbound-tenant derivation."""
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "memory-copilot", model="azure/gpt-4o")
    assert ctx.tenant_propagate is True


def test_copilot_ctx_projects_knowledge(mi):
    """The Copilot ``knowledge.collections`` refs ride on the ctx."""
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "memory-copilot", model="azure/gpt-4o")
    assert ctx.knowledge == ["knowledge-base"]


# ── Task 3b negatives: everything optional is empty when undeclared ──────────


def test_copilot_ctx_knowledge_optional(mi):
    """RAG is optional — a pure-action copilot carries no knowledge."""
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "pure-action-copilot", model="azure/gpt-4o")
    assert ctx.knowledge == []


def test_copilot_ctx_mcp_servers_empty_when_undeclared(mi):
    """A mounted agent with no ``mcp_servers`` projects an empty list."""
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "pure-action-copilot", model="azure/gpt-4o")
    assert ctx.mcp_servers == []


def test_copilot_ctx_hitl_empty_when_no_gated_tools(mi):
    """No tool gates on approval → the HITL-write surface is empty."""
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "pure-action-copilot", model="azure/gpt-4o")
    assert ctx.tools_requiring_confirmation == set()


def test_copilot_ctx_tenant_default_false_when_undeclared(mi):
    """No Copilot ``tenant`` block + no federation → tenant is NOT propagated."""
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "pure-action-copilot", model="azure/gpt-4o")
    assert ctx.tenant_propagate is False


# ── Chunk 4 · the Agno `copilot` scaffold case ──────────────────────────────
#
# ``build_copilot_context`` (Chunk 3) → ``AgnoEmitter().emit(ctx)`` renders TWO
# artifacts: a ``role="agent"`` module (the ``build_agent`` factory + MCP mount +
# the HITL write-gate) and a ``role="serving"`` module (Agno AgentOS exposing
# ``/agui`` + inbound-tenant derivation). Byte-equal goldens govern both. The
# goldens are regenerated as each slice (4a→4d) extends the templates.

import py_compile
import tempfile


def _compiles(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        path = fh.name
    try:
        py_compile.compile(path, doraise=True)
        return True
    except py_compile.PyCompileError:
        return False


def read_golden(name: str) -> str:
    """Read a frozen golden under ``tests/goldens/`` (e.g. ``agno/copilot_agent.py``)."""
    return (
        pathlib.Path(__file__).parent / "goldens" / name
    ).read_text(encoding="utf-8")


@pytest.fixture()
def copilot_ctx(mi):
    from dna.emit import build_copilot_context

    return build_copilot_context(
        mi, "memory-copilot", model="azure/gpt-4o", provider="azure"
    )


# ── Task 4a: agent + /agui serving ──────────────────────────────────────────


def test_copilot_emit_is_two_artifacts(copilot_ctx):
    """A servable copilot emits an ``agent`` module + a ``serving`` module."""
    from dna.emit.agno import AgnoEmitter

    res = AgnoEmitter().emit(copilot_ctx)
    assert {a.role for a in res.artifacts} == {"agent", "serving"}
    assert res.target == "agno"
    # module paths are valid python identifiers (the mounted agent's slug).
    assert res.artifact_for("agent") is not None
    paths = {a.role: a.path for a in res.artifacts}
    assert paths["agent"] == "memory_agent.py"
    assert paths["serving"] == "memory_agent_serve.py"


def test_copilot_agent_artifact_matches_golden(copilot_ctx):
    from dna.emit.agno import AgnoEmitter

    res = AgnoEmitter().emit(copilot_ctx)
    assert res.artifact_for("agent") == read_golden("agno/copilot_agent.py")


def test_copilot_serving_artifact_matches_golden(copilot_ctx):
    from dna.emit.agno import AgnoEmitter

    res = AgnoEmitter().emit(copilot_ctx)
    assert res.artifact_for("serving") == read_golden("agno/copilot_serve.py")


def test_copilot_agent_carries_instructions_byte_equal(copilot_ctx):
    """The byte-equal invariant, recovered via the emitter METHOD off the
    ``role="agent"`` artifact — the mounted agent's composed prompt, verbatim."""
    from dna.emit.agno import AgnoEmitter

    emitter = AgnoEmitter()
    res = emitter.emit(copilot_ctx)
    assert emitter.extract_instructions(res.artifact_for("agent")) == copilot_ctx.instructions


def test_copilot_artifacts_compile(copilot_ctx):
    from dna.emit.agno import AgnoEmitter

    res = AgnoEmitter().emit(copilot_ctx)
    assert _compiles(res.artifact_for("agent"))
    assert _compiles(res.artifact_for("serving"))


def test_copilot_serving_exposes_agui(copilot_ctx):
    """The serving artifact wires Agno's AgentOS + AGUI interface → /agui."""
    from dna.emit.agno import AgnoEmitter

    serving = AgnoEmitter().emit(copilot_ctx).artifact_for("serving")
    assert "from agno.os import AgentOS" in serving
    assert "from agno.os.interfaces.agui import AGUI" in serving
    assert "app = agent_os.get_app()" in serving
    assert "from memory_agent import build_agent" in serving


def test_plain_agent_still_single_artifact(mi):
    """Back-compat: a plain agent (no copilot signals) stays a single artifact."""
    from dna.emit import emit_agent

    res = emit_agent(mi, "concierge", "agno")
    assert [a.role for a in res.artifacts] == ["agent"]
    assert "AgentOS" not in res.artifact


# ── Task 4b: MCP-tool mount ─────────────────────────────────────────────────


def test_copilot_agent_mounts_mcp_tools(copilot_ctx):
    """The mounted agent builds ``MCPTools(url, transport="streamable-http")``
    from ``ctx.mcp_servers`` and wires them into ``Agent(tools=...)``."""
    from dna.emit.agno import AgnoEmitter

    agent = AgnoEmitter().emit(copilot_ctx).artifact_for("agent")
    assert "from agno.tools.mcp import MCPTools" in agent
    assert "url='https://mcp.dna.example/agui'" in agent
    assert "transport='streamable-http'" in agent
    assert "tools=_mcp_tools()" in agent


def test_copilot_agent_mcp_matches_golden(copilot_ctx):
    from dna.emit.agno import AgnoEmitter

    res = AgnoEmitter().emit(copilot_ctx)
    assert res.artifact_for("agent") == read_golden("agno/copilot_agent.py")


# ── Task 4c: inbound-tenant derivation ──────────────────────────────────────


def test_copilot_serving_derives_inbound_tenant(copilot_ctx):
    """When ``ctx.tenant_propagate`` is set the serving layer derives tenant/oid
    from request headers into run-state; tools read it via RunContext.session_state
    (mirrors the Agno KB reference ``inject_tenant`` — NOT a propagate_tenant freebie)."""
    from dna.emit.agno import AgnoEmitter

    assert copilot_ctx.tenant_propagate is True
    serving = AgnoEmitter().emit(copilot_ctx).artifact_for("serving")
    assert "class TenantAGUI(AGUI):" in serving
    assert "def tenant_from_request(request: Request)" in serving
    assert "def inject_tenant(run_input: RunAgentInput, tenant: dict)" in serving
    assert 'run_input.state["tenant"] = tenant' in serving
    assert "from agno.os.interfaces.agui.router import run_entity" in serving
    assert "interfaces=[TenantAGUI(agent=agent)]" in serving


def test_copilot_serving_tenant_matches_golden(copilot_ctx):
    from dna.emit.agno import AgnoEmitter

    res = AgnoEmitter().emit(copilot_ctx)
    assert res.artifact_for("serving") == read_golden("agno/copilot_serve.py")


def test_copilot_serving_no_tenant_when_not_propagated():
    """A copilot that does not propagate tenant serves the plain ``AGUI`` — no
    header-derivation machinery. Synthesized ctx: a knowledge-only copilot signal
    with ``tenant_propagate=False``."""
    from dna.emit import EmitContext
    from dna.emit.agno import AgnoEmitter

    ctx = EmitContext(
        name="kb-copilot",
        description="",
        instructions="Answer from the KB.",
        model="azure/gpt-4o",
        knowledge=["some-collection"],  # copilot signal, but no tenant/mcp/hitl
        tenant_propagate=False,
    )
    res = AgnoEmitter().emit(ctx)
    serving = res.artifact_for("serving")
    assert "TenantAGUI" not in serving
    assert "interfaces=[AGUI(agent=agent)]" in serving
    assert _compiles(serving)


# ── Task 4d: HITL (gate-remote-directly per Spike 0A) ───────────────────────


def test_copilot_gates_write_tools_on_remote_mcp(copilot_ctx):
    """Spike 0A verdict = gate-remote-directly: the emitted MCPTools mount carries
    ``external_execution_required_tools`` = ``ctx.tools_requiring_confirmation``
    (sorted) — the DNA write tools are gated on the REMOTE tool, no local wrapper."""
    from dna.emit.agno import AgnoEmitter

    assert copilot_ctx.tools_requiring_confirmation == {"remember", "forget"}
    agent = AgnoEmitter().emit(copilot_ctx).artifact_for("agent")
    assert "external_execution_required_tools=['forget', 'remember']" in agent
    # no local wrapper tool — the gate rides on the remote MCP tool itself.
    assert "def remember(" not in agent
    assert "def forget(" not in agent


def test_copilot_hitl_agent_matches_golden(copilot_ctx):
    from dna.emit.agno import AgnoEmitter

    res = AgnoEmitter().emit(copilot_ctx)
    assert res.artifact_for("agent") == read_golden("agno/copilot_agent.py")


def test_copilot_no_gate_when_no_confirmation_tools():
    """A copilot with MCP but no confirmation-gated tools omits
    ``external_execution_required_tools`` entirely."""
    from dna.emit import EmitContext, EmitMcpServer
    from dna.emit.agno import AgnoEmitter

    ctx = EmitContext(
        name="reader",
        description="",
        instructions="Read only.",
        model="azure/gpt-4o",
        mcp_servers=[EmitMcpServer(ref="dna-mcp", transport="streamable-http",
                                   url="https://mcp.example/agui")],
        tools_requiring_confirmation=set(),
    )
    agent = AgnoEmitter().emit(ctx).artifact_for("agent")
    # the docstring mentions the kwarg; assert the ASSIGNMENT is absent.
    assert "external_execution_required_tools=" not in agent
    assert _compiles(agent)


# ── Task 4e: integration — the emitted app imports, mounts /agui, pauses/resumes ─
#
# Guarded by an agno import: the emit + golden slices above run with NO runtime
# dep; this slice needs a live agno/ag-ui/fastapi/mcp/openai stack to IMPORT the
# emitted app and drive a real run. It proves the emitted shape end-to-end and
# that the external_execution pause/resume the emitted MCP-gate relies on behaves
# exactly as Spike 0A + the Agno KB reference recorded.

import sys as _sys


def _write_and_import(copilot_ctx, tmp_path):
    """Emit both artifacts to ``tmp_path`` and import them as real modules."""
    import importlib

    from dna.emit.agno import AgnoEmitter

    res = AgnoEmitter().emit(copilot_ctx)
    for a in res.artifacts:
        (tmp_path / a.path).write_text(a.content, encoding="utf-8")
    # module names = artifact paths minus the .py extension.
    names = {a.role: a.path[:-3] for a in res.artifacts}
    _sys.path.insert(0, str(tmp_path))
    try:
        for n in names.values():
            _sys.modules.pop(n, None)
        agent_mod = importlib.import_module(names["agent"])
        serve_mod = importlib.import_module(names["serving"])
        return agent_mod, serve_mod
    finally:
        _sys.path.remove(str(tmp_path))
        for n in names.values():
            _sys.modules.pop(n, None)


def test_emitted_copilot_imports_and_mounts_agui(copilot_ctx, tmp_path):
    """The emitted agent + serving modules import against real agno: build_agent
    returns an Agno Agent whose MCP mount gates exactly the confirmation tools,
    and the serving app is a FastAPI exposing POST /agui."""
    pytest.importorskip("agno")
    pytest.importorskip("ag_ui")
    pytest.importorskip("fastapi")
    pytest.importorskip("mcp")
    pytest.importorskip("openai")
    from agno.agent import Agent
    from fastapi import FastAPI

    agent_mod, serve_mod = _write_and_import(copilot_ctx, tmp_path)

    # 1. the agent factory builds a real Agno Agent with the MCP gate wired.
    agent = agent_mod.build_agent()
    assert isinstance(agent, Agent)
    mcp = agent.tools[0]
    assert sorted(mcp.external_execution_required_tools) == ["forget", "remember"]

    # 2. the serving app is a FastAPI mounting /agui, with the tenant hook.
    assert isinstance(serve_mod.app, FastAPI)
    assert "/agui" in serve_mod.app.openapi().get("paths", {})
    assert hasattr(serve_mod, "TenantAGUI")
    assert callable(serve_mod.tenant_from_request)


def test_emitted_copilot_pauses_and_resumes_on_gate(tmp_path):
    """The pause/resume shape the emitted MCP gate depends on, proven against real
    agno with a stub model + a local ``external_execution`` tool (a live MCP
    connection is out of scope). A ``remember`` turn PAUSES (RunStatus.paused,
    tools_awaiting_external_execution == ['remember']); ``acontinue_run`` resumes
    to completion — matching Spike 0A + the Agno KB reference ``agui_hitl``."""
    pytest.importorskip("agno")
    pytest.importorskip("openai")
    import asyncio

    from agno.agent import Agent
    from agno.db.in_memory import InMemoryDb
    from agno.models.base import Model
    from agno.models.response import ModelResponse
    from agno.run.base import RunStatus
    from agno.tools import tool

    class _StubModel(Model):
        """Emits a `remember` tool call on turn 1, a final answer on resume."""

        def __init__(self) -> None:
            super().__init__(id="stub")
            self._calls = 0

        async def ainvoke(self, *a, **k) -> ModelResponse:
            self._calls += 1
            if self._calls == 1:
                return ModelResponse(role="assistant", tool_calls=[{
                    "id": "call_1", "type": "function",
                    "function": {"name": "remember", "arguments": '{"text": "buy milk"}'},
                }])
            return ModelResponse(role="assistant", content="Done — remembered.")

        def invoke(self, *a, **k):  # pragma: no cover - non-stream unused
            raise NotImplementedError

        def invoke_stream(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        async def ainvoke_stream(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        def _parse_provider_response(self, r, **k):  # pragma: no cover
            raise NotImplementedError

        def _parse_provider_response_delta(self, r):  # pragma: no cover
            raise NotImplementedError

    @tool(external_execution=True)
    def remember(text: str) -> str:
        """Persist a note (gated — resolved outside the agent, like the remote MCP write)."""
        return "stored"

    async def _drive() -> None:
        agent = Agent(model=_StubModel(), tools=[remember], db=InMemoryDb())
        out = await agent.arun(input="remember buy milk", stream=False, session_id="s1")
        assert out.status == RunStatus.paused
        awaiting = [t.tool_name for t in out.tools_awaiting_external_execution]
        assert awaiting == ["remember"]
        for t in out.tools_awaiting_external_execution:
            t.result = "stored ok"
            t.external_execution_required = False
        resumed = await agent.acontinue_run(
            run_id=out.run_id, session_id="s1",
            updated_tools=out.tools_awaiting_external_execution, stream=False,
        )
        assert resumed.status == RunStatus.completed

    asyncio.run(_drive())


# ── Chunk 5 · the shared CopilotKit frontend console scaffold ────────────────
#
# ``build_copilot_context`` also projects the Copilot's ``frontend`` + ``hitl.
# approval_card`` blocks; ``emit_frontend_console`` renders the shared CopilotKit
# v2 console (route + console + approval-card + suggested-prompts) plus the ONE
# per-runtime resume-adapter. This is a TS-only golden family (design §7): the
# emitted files are TypeScript, governed by their own byte-stable golden, with no
# Py↔TS twin-diff (there is no Python frontend to diff against).


def _fe_files(res) -> dict:
    """The emitted frontend artifacts keyed by their target-relative path."""
    return {a.path: a.content for a in res.artifacts}


# ── Task 5a: build_copilot_context projects the frontend + hitl.approval_card ─


def test_copilot_ctx_projects_frontend(mi):
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "memory-copilot", model="azure/gpt-4o")
    assert ctx.frontend_console == "copilotkit"
    assert ctx.frontend_panels == ["memory-timeline"]
    assert ctx.frontend_suggested_prompts == ["What did I ask you to remember?"]


def test_copilot_ctx_projects_approval_card(mi):
    from dna.emit import build_copilot_context

    ctx = build_copilot_context(mi, "memory-copilot", model="azure/gpt-4o")
    assert ctx.hitl_approval_card == {
        "title": "Confirm write",
        "details_from": "args.text",
        "reason_from": "args.reason",
    }


def test_copilot_ctx_frontend_absent_when_undeclared(mi):
    """A pure-action copilot declares no ``frontend`` / ``hitl`` — the ctx carries
    None/empty, and ``has_frontend`` is False (no console to emit)."""
    from dna.emit import build_copilot_context
    from dna.emit.frontend import has_frontend

    ctx = build_copilot_context(mi, "pure-action-copilot", model="azure/gpt-4o")
    assert ctx.frontend_console is None
    assert ctx.frontend_panels == []
    assert ctx.frontend_suggested_prompts == []
    assert ctx.hitl_approval_card is None
    assert has_frontend(ctx) is False


# ── Task 5b: the frontend emit — one shared console tree (role="frontend") ────


@pytest.fixture()
def fe_ctx(mi):
    from dna.emit import build_copilot_context

    return build_copilot_context(
        mi, "memory-copilot", model="azure/gpt-4o", provider="azure"
    )


def test_frontend_emit_is_the_shared_console_tree(fe_ctx):
    """Five files, all ``role="frontend"``, at their target-relative paths."""
    from dna.emit.frontend import emit_frontend_console

    res = emit_frontend_console(fe_ctx, runtime="agno")
    assert {a.role for a in res.artifacts} == {"frontend"}
    assert set(_fe_files(res)) == {
        "app/api/copilotkit/route.ts",
        "components/copilot/console.tsx",
        "components/copilot/approval-card.tsx",
        "components/copilot/suggested-prompts.tsx",
        "lib/copilot/resume-adapter.ts",
    }
    assert res.target == "copilotkit-agno"


def test_frontend_route_matches_golden(fe_ctx):
    from dna.emit.frontend import emit_frontend_console

    files = _fe_files(emit_frontend_console(fe_ctx, runtime="agno"))
    assert files["app/api/copilotkit/route.ts"] == read_golden("frontend/route.ts")


def test_frontend_console_matches_golden(fe_ctx):
    from dna.emit.frontend import emit_frontend_console

    files = _fe_files(emit_frontend_console(fe_ctx, runtime="agno"))
    assert files["components/copilot/console.tsx"] == read_golden("frontend/console.tsx")


def test_frontend_approval_card_matches_golden(fe_ctx):
    from dna.emit.frontend import emit_frontend_console

    files = _fe_files(emit_frontend_console(fe_ctx, runtime="agno"))
    assert files["components/copilot/approval-card.tsx"] == read_golden(
        "frontend/approval-card.tsx"
    )


def test_frontend_suggested_prompts_matches_golden(fe_ctx):
    from dna.emit.frontend import emit_frontend_console

    files = _fe_files(emit_frontend_console(fe_ctx, runtime="agno"))
    assert files["components/copilot/suggested-prompts.tsx"] == read_golden(
        "frontend/suggested-prompts.tsx"
    )


# ── Task 5c: the console is parameterized from Copilot.frontend / hitl ────────


def test_frontend_console_wires_chat_and_provider(fe_ctx):
    from dna.emit.frontend import emit_frontend_console

    console = _fe_files(emit_frontend_console(fe_ctx))["components/copilot/console.tsx"]
    assert 'const AGENT_ID = "memory-agent";' in console
    assert "<CopilotChat agentId={AGENT_ID} />" in console
    assert 'runtimeUrl="/api/copilotkit"' in console


def test_frontend_console_wires_panels_and_prompts(fe_ctx):
    from dna.emit.frontend import emit_frontend_console

    console = _fe_files(emit_frontend_console(fe_ctx))["components/copilot/console.tsx"]
    # panel from frontend.panels
    assert 'data-panel="memory-timeline"' in console
    # starter prompt from frontend.suggested_prompts (anti-blank-box)
    assert '"What did I ask you to remember?"' in console
    assert "<SuggestedPrompts agentId={AGENT_ID} prompts={SUGGESTED_PROMPTS} />" in console


def test_frontend_console_gates_write_tools_via_hitl(fe_ctx):
    """One useHumanInTheLoop hook per gated write tool, driving the ApprovalCard
    with the Copilot's approval_card copy (title + details_from/reason_from)."""
    from dna.emit.frontend import emit_frontend_console

    console = _fe_files(emit_frontend_console(fe_ctx))["components/copilot/console.tsx"]
    assert 'name: "remember",' in console
    assert 'name: "forget",' in console
    assert 'title="Confirm write"' in console
    assert 'pick(args as Record<string, unknown>, "args.text")' in console
    assert 'pick(args as Record<string, unknown>, "args.reason")' in console


def test_frontend_console_forwards_only_dna_tenant_headers(fe_ctx):
    """DNA tenant model: X-DNA-Tenant (workspace) + X-Tenant-OID (server-derived).
    NO license/namespace dimension anywhere in the emitted console."""
    from dna.emit.frontend import emit_frontend_console

    console = _fe_files(emit_frontend_console(fe_ctx))["components/copilot/console.tsx"]
    assert '"X-DNA-Tenant"' in console
    assert "X-Tenant-OID" in console  # documented as server-derived
    assert "License" not in console
    assert "Namespace" not in console
    assert "headers={dnaTenantHeaders()}" in console


# ── Task 5d: the per-runtime resume-adapter (the ONE per-runtime file) ────────


def test_frontend_agno_resume_adapter_is_native(fe_ctx):
    """agno resumes external_execution gates natively → identity HttpAgent, no
    payload rewrite."""
    from dna.emit.frontend import emit_frontend_console

    adapter = _fe_files(emit_frontend_console(fe_ctx, runtime="agno"))[
        "lib/copilot/resume-adapter.ts"
    ]
    assert adapter == read_golden("frontend/resume-adapter.agno.ts")
    assert "return new HttpAgent({ url });" in adapter
    # no payload-rewrite bridge (that is the MS-AF adapter's job).
    assert "body.resume" not in adapter
    assert "fetch:" not in adapter


def test_frontend_msaf_resume_adapter_bridges_interrupts(fe_ctx):
    """MS Agent Framework needs the AG-UI resume array → {interrupts:[…]} bridge —
    the ONLY file that differs from the agno emit."""
    from dna.emit.frontend import emit_frontend_console

    res = emit_frontend_console(fe_ctx, runtime="agent-framework")
    adapter = _fe_files(res)["lib/copilot/resume-adapter.ts"]
    assert adapter == read_golden("frontend/resume-adapter.msaf.ts")
    assert "interrupts:" in adapter
    assert res.target == "copilotkit-agent-framework"
    # the SHARED files are byte-identical to the agno emit — only the adapter differs.
    agno = _fe_files(emit_frontend_console(fe_ctx, runtime="agno"))
    msaf = _fe_files(res)
    for path in agno:
        if path != "lib/copilot/resume-adapter.ts":
            assert agno[path] == msaf[path]


def test_frontend_emit_rejects_unknown_runtime(fe_ctx):
    from dna.emit import EmitError
    from dna.emit.frontend import emit_frontend_console

    with pytest.raises(EmitError):
        emit_frontend_console(fe_ctx, runtime="carrier-pigeon")


def test_frontend_emit_requires_a_frontend_block(mi):
    """A copilot with no ``frontend`` block has no console to emit → EmitError."""
    from dna.emit import EmitError, build_copilot_context
    from dna.emit.frontend import emit_frontend_console

    ctx = build_copilot_context(mi, "pure-action-copilot", model="azure/gpt-4o")
    with pytest.raises(EmitError):
        emit_frontend_console(ctx)


def test_frontend_backend_emit_still_two_artifacts(fe_ctx):
    """The frontend emit is a SEPARATE surface — the backend copilot emit is
    unchanged (agent + serving only, no frontend leak)."""
    from dna.emit.agno import AgnoEmitter

    res = AgnoEmitter().emit(fe_ctx)
    assert {a.role for a in res.artifacts} == {"agent", "serving"}
