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
        "knowledge": {"collections": ["aap-knowledge-base"]},
        "frontend": {
            "console": "copilotkit",
            "panels": ["memory-timeline"],
            "suggested_prompts": ["What did I ask you to remember?"],
        },
    })
    assert doc.spec.tenant.propagate is True
    assert doc.spec.hitl.approval_card.title == "Confirm write"
    assert doc.spec.knowledge.collections[0] == "aap-knowledge-base"
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
    assert ctx.knowledge == ["aap-knowledge-base"]


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
