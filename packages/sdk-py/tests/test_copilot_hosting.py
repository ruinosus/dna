"""Copilot → **hosted-variant** deployment artifacts (f-copilot-hosting).

``build_copilot_context`` → :func:`dna.emit.hosting.emit_hosting` renders the
HOSTED variant of a copilot (design §2 variant selector). Gated on
``ctx.hosting.mode == "hosted"``: a self-hosted / no-hosting copilot keeps the
existing AG-UI emit UNCHANGED.

- ``target: foundry`` (FIRST-CLASS): Dockerfile (port 8088, linux/amd64) + main.py
  (``ResponsesHostServer(build_agent()).run()``, the DEGRADED single-identity
  variant) + requirements.txt + the ``host: azure.ai.agent`` azure.yaml block.
- ``target: langgraph-platform`` / ``agentos`` (DOCUMENTED): the self-host
  artifacts + an honest HOSTING.md note.

The live fixture is ``examples/emitting-to-a-runtime/.dna`` (concierge scope):
``hosted-copilot`` mounts the SAME ``memory-agent`` as ``memory-copilot`` but with
``hosting.mode: hosted`` — the variant selector in action. Byte-stable goldens
(``tests/goldens/hosting/``) govern the emit; the emitted files are byte-identical
to the TS twin (``hosting.ts``).
"""
from __future__ import annotations

import json
import pathlib
import py_compile
import tempfile

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"


@pytest.fixture()
def mi():
    from dna.kernel import Kernel

    return Kernel.quick(_SCOPE, base_dir=_BASE)


@pytest.fixture()
def hosted_ctx(mi):
    from dna.emit import build_copilot_context

    return build_copilot_context(
        mi, "hosted-copilot", model="azure/gpt-4o", provider="azure"
    )


def read_golden(name: str) -> str:
    return (
        pathlib.Path(__file__).parent / "goldens" / "hosting" / name
    ).read_text(encoding="utf-8")


def _compiles(source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(source)
        path = fh.name
    try:
        py_compile.compile(path, doraise=True)
        return True
    except py_compile.PyCompileError:
        return False


def _files(res) -> dict:
    return {a.path: a.content for a in res.artifacts}


# ── has_hosting gating (mode == "hosted") ─────────────────────────────────────


def test_has_hosting_true_for_hosted_mode(hosted_ctx):
    from dna.emit.hosting import has_hosting

    assert has_hosting(hosted_ctx) is True


def test_has_hosting_false_for_self_hosted(mi):
    """memory-copilot declares ``hosting.mode: self-hosted`` — no hosted variant."""
    from dna.emit import build_copilot_context
    from dna.emit.hosting import emit_hosting, has_hosting

    ctx = build_copilot_context(mi, "memory-copilot", model="azure/gpt-4o")
    assert ctx.hosting is not None and ctx.hosting["mode"] == "self-hosted"
    assert has_hosting(ctx) is False
    with pytest.raises(Exception):
        emit_hosting(ctx)


def test_has_hosting_false_when_undeclared(mi):
    from dna.emit import build_copilot_context
    from dna.emit.hosting import has_hosting

    ctx = build_copilot_context(mi, "pure-action-copilot", model="azure/gpt-4o")
    assert ctx.hosting is None
    assert has_hosting(ctx) is False


# ── Foundry (FIRST-CLASS): the four artifacts ────────────────────────────────


def test_foundry_emits_four_hosting_artifacts(hosted_ctx):
    from dna.emit.hosting import emit_hosting

    res = emit_hosting(hosted_ctx)
    assert res.target == "foundry-hosted"
    assert {a.role for a in res.artifacts} == {"hosting"}
    assert set(_files(res)) == {"Dockerfile", "main.py", "requirements.txt", "azure.yaml"}


def test_foundry_dockerfile_matches_golden(hosted_ctx):
    from dna.emit.hosting import emit_hosting

    files = _files(emit_hosting(hosted_ctx))
    assert files["Dockerfile"] == read_golden("foundry/Dockerfile")


def test_foundry_main_matches_golden(hosted_ctx):
    from dna.emit.hosting import emit_hosting

    files = _files(emit_hosting(hosted_ctx))
    assert files["main.py"] == read_golden("foundry/main.py")


def test_foundry_requirements_matches_golden(hosted_ctx):
    from dna.emit.hosting import emit_hosting

    files = _files(emit_hosting(hosted_ctx))
    assert files["requirements.txt"] == read_golden("foundry/requirements.txt")


def test_foundry_azure_yaml_matches_golden(hosted_ctx):
    from dna.emit.hosting import emit_hosting

    files = _files(emit_hosting(hosted_ctx))
    assert files["azure.yaml"] == read_golden("foundry/azure.yaml")


# ── Foundry Dockerfile shape (port 8088, linux/amd64, CMD python main.py) ─────


def test_foundry_dockerfile_shape(hosted_ctx):
    from dna.emit.hosting import emit_hosting

    df = _files(emit_hosting(hosted_ctx))["Dockerfile"]
    assert "FROM python:3.12-slim" in df
    assert "EXPOSE 8088" in df
    assert "linux/amd64" in df
    assert 'CMD ["python", "main.py"]' in df


# ── Foundry main.py: ResponsesHostServer + the DEGRADE + byte-equal ──────────


def test_foundry_main_uses_responses_host_server(hosted_ctx):
    from dna.emit.hosting import emit_hosting

    main = _files(emit_hosting(hosted_ctx))["main.py"]
    assert "from agent_framework_foundry_hosting import ResponsesHostServer" in main
    assert "ResponsesHostServer(build_agent()).run()" in main
    # the MS-AF agent build reused from the self-hosted copilot scaffold.
    assert "from agent_framework.foundry import FoundryChatClient" in main
    assert "return client.as_agent(" in main
    assert "instructions=INSTRUCTIONS," in main


def test_foundry_main_compiles(hosted_ctx):
    from dna.emit.hosting import emit_hosting

    assert _compiles(_files(emit_hosting(hosted_ctx))["main.py"])


def test_foundry_main_carries_instructions_byte_equal(hosted_ctx):
    """The composed prompt travels byte-equal into the hosted main.py (recovered
    the same way the scaffold emitters recover it — an AST read of INSTRUCTIONS)."""
    import ast

    from dna.emit.hosting import emit_hosting

    main = _files(emit_hosting(hosted_ctx))["main.py"]
    module = ast.parse(main)
    found = None
    for node in module.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "INSTRUCTIONS":
                    found = ast.literal_eval(node.value)
    assert found == hosted_ctx.instructions


def test_foundry_variant_degrades_per_user_concerns(hosted_ctx):
    """The hosted variant strips per-user OBO / HITL / per-user tenant even though
    the SAME agent's self-hosted variant wires them: single-service identity via
    DefaultAzureCredential, NO approval_mode (HITL), NO header_provider (OBO)."""
    from dna.emit.hosting import emit_hosting

    assert hosted_ctx.tools_requiring_confirmation == {"remember", "forget"}
    assert hosted_ctx.tenant_propagate is True  # self-hosted wires it; hosted drops it
    main = _files(emit_hosting(hosted_ctx))["main.py"]
    assert "DefaultAzureCredential()" in main
    # HITL stripped — no approval_mode kwarg on the MCP mount (prose may name it).
    assert "approval_mode=" not in main
    # per-user OBO/tenant stripped — no header_provider kwarg / ContextVar / headers.
    assert "header_provider=" not in main
    assert "contextvars" not in main
    assert "X-DNA-Tenant" not in main
    # but the single-identity RAG grounding SURVIVES (shared corpus, not per-user).
    assert "PostgresVectorStore(" in main


# ── Foundry requirements + azure.yaml manifest shape ─────────────────────────


def test_foundry_requirements_include_hosting_and_persistence_deps(hosted_ctx):
    from dna.emit.hosting import emit_hosting

    req = _files(emit_hosting(hosted_ctx))["requirements.txt"]
    lines = req.splitlines()
    assert "agent-framework" in lines
    assert "agent-framework-foundry-hosting" in lines
    # pgvector knowledge store survives → its dep rides along.
    assert "agent-framework-postgres" in lines


def test_foundry_azure_yaml_is_azure_ai_agent_service_block(hosted_ctx):
    """The NON-deprecated Foundry hosted-agent manifest: `host: azure.ai.agent`,
    docker.remoteBuild (image.remote_build=true), resources from hosting.resources,
    startupCommand — NOT the deprecated agent.yaml."""
    from dna.emit.hosting import emit_hosting

    y = _files(emit_hosting(hosted_ctx))["azure.yaml"]
    assert "host: azure.ai.agent" in y
    assert "language: docker" in y
    assert "remoteBuild: true" in y
    assert "startupCommand: python main.py" in y
    assert 'cpu: "0.5"' in y
    assert "memory: 1Gi" in y
    # the service is keyed by the mounted agent slug.
    assert "  memory-agent:" in y
    # NOT the deprecated legacy manifest.
    assert "agent.yaml" not in y or "deprecated" in y  # only the comment may name it


# ── unknown / documented targets ─────────────────────────────────────────────


def test_unknown_hosting_target_raises():
    from dna.emit import EmitContext
    from dna.emit.hosting import emit_hosting

    ctx = EmitContext(
        name="weird",
        description="",
        instructions="x",
        model="azure/gpt-4o",
        hosting={"mode": "hosted", "target": "heroku", "resources": None,
                 "image": None, "env": None, "stores": None},
    )
    with pytest.raises(Exception):
        emit_hosting(ctx)


def _synthetic(target: str, **overrides):
    from dna.emit import EmitContext

    hosting = {
        "mode": "hosted",
        "target": target,
        "resources": {"cpu": "1", "memory": "2Gi"},
        "image": {"registry_hint": "ghcr", "remote_build": False,
                  "base_image": None, "port": None},
        "env": None,
        "stores": {"postgres": "required", "redis": "required"},
    }
    hosting.update(overrides)
    return EmitContext(
        name=f"{target.split('-')[0]}-copilot",
        description="",
        instructions="Answer.",
        model="azure/gpt-4o",
        hosting=hosting,
    )


# ── LangGraph Platform (DOCUMENTED) ──────────────────────────────────────────


def test_langgraph_emits_json_and_note():
    from dna.emit.hosting import emit_hosting

    ctx = _synthetic("langgraph-platform")
    ctx.name = "lg-copilot"
    res = emit_hosting(ctx)
    assert res.target == "langgraph-platform"
    files = _files(res)
    assert set(files) == {"langgraph.json", "HOSTING.md"}
    assert files["langgraph.json"] == read_golden("langgraph/langgraph.json")
    assert files["HOSTING.md"] == read_golden("langgraph/HOSTING.md")


def test_langgraph_json_is_valid_and_documents_build():
    from dna.emit.hosting import emit_hosting

    ctx = _synthetic("langgraph-platform")
    ctx.name = "lg-copilot"
    res = emit_hosting(ctx)
    files = _files(res)
    doc = json.loads(files["langgraph.json"])
    assert "graphs" in doc and "dependencies" in doc
    # documented, not over-built: langgraph build produces the image.
    assert "langgraph build" in files["HOSTING.md"]
    assert any("stateful" in l.lower() and "server" in l.lower() for l in res.losses)


# ── AgentOS (DOCUMENTED — no managed runtime) ────────────────────────────────


def test_agentos_emits_app_compose_and_note():
    from dna.emit.hosting import emit_hosting

    ctx = _synthetic("agentos")
    ctx.name = "ao-copilot"
    res = emit_hosting(ctx)
    assert res.target == "agentos"
    files = _files(res)
    assert set(files) == {"main.py", "compose.yaml", "HOSTING.md"}
    assert files["main.py"] == read_golden("agentos/main.py")
    assert files["compose.yaml"] == read_golden("agentos/compose.yaml")
    assert files["HOSTING.md"] == read_golden("agentos/HOSTING.md")


def test_agentos_app_compiles_and_compose_binds_7777():
    from dna.emit.hosting import emit_hosting

    ctx = _synthetic("agentos")
    ctx.name = "ao-copilot"
    files = _files(emit_hosting(ctx))
    assert _compiles(files["main.py"])
    assert "from agno.os import AgentOS" in files["main.py"]
    assert '"7777:7777"' in files["compose.yaml"]
    # honest about the leak: no managed runtime.
    assert "no managed runtime" in files["HOSTING.md"].lower()


# ── back-compat: the self-hosted emit is UNCHANGED ───────────────────────────


def test_self_hosted_agno_emit_unchanged_by_hosting(mi):
    """A hosted-variant emit is a SEPARATE surface — the self-hosted AG-UI emit
    (agno) for the same mounted agent is byte-identical to its existing golden."""
    from dna.emit import build_copilot_context
    from dna.emit.agno import AgnoEmitter

    ctx = build_copilot_context(mi, "memory-copilot", model="azure/gpt-4o", provider="azure")
    res = AgnoEmitter().emit(ctx)
    agno_golden = (
        pathlib.Path(__file__).parent / "goldens" / "agno" / "copilot_agent.py"
    ).read_text(encoding="utf-8")
    assert res.artifact_for("agent") == agno_golden
