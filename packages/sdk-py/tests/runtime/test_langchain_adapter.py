import asyncio
import shutil
from pathlib import Path

from fastapi import FastAPI

from dna.emit import build_copilot_context
from dna.kernel import Kernel
from dna.runtime.adapters.langchain_rt import LangChainRuntime
from dna.runtime.port import AGUIApp, RuntimeHooks

# Committed fixture (this repo), NOT the sibling dna-cloud repo — must pass on
# a fresh clone with no dna-cloud checkout present.
FIXTURE_SRC = Path(__file__).parent / "fixtures" / "dna" / "dna-cloud-dev"


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / ".dna" / "dna-cloud-dev"
    dest.mkdir(parents=True)
    for subdir in ("copilots", "agents", "federations", "tools"):
        shutil.copytree(FIXTURE_SRC / subdir, dest / subdir)
    return tmp_path / ".dna"


def _build_ctx(tmp_path):
    base_dir = _copy_fixture(tmp_path)
    mi = Kernel.quick("dna-cloud-dev", base_dir=str(base_dir))
    return build_copilot_context(mi, "memory-copilot")


async def _compose(_headers):
    return "PROMPT"


def _stub_no_mcp_discovery(monkeypatch):
    # MCP discovery is LAZY (DnaMcpToolsMiddleware, first authenticated model
    # call), so build makes no MCP round-trip. We stub load_mcp_tools
    # defensively and assert it is NOT touched at build time — same
    # discipline as test_build_copilot.py.
    calls = {"n": 0}

    async def fake_load_mcp_tools(mcp_url, auth):
        calls["n"] += 1
        return []

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", fake_load_mcp_tools
    )
    return calls


def _stub_no_persistence_resolution(monkeypatch):
    # The fixture's memory-copilot declares `persistence.{checkpoint,memory}`
    # on Postgres (ref `primary-pg`) — since these tests pass no
    # `hooks.checkpointer`, the adapter now resolves it declaratively
    # (Task 4). Stub the resolver so this parity test never dials real
    # Postgres — `resolve_persistence`'s own DSN/env-var behavior is covered
    # by test_declarative_config.py.
    async def fake_resolve_persistence(_persistence):
        return None, None

    monkeypatch.setattr(
        "dna.runtime.persistence.resolve_persistence", fake_resolve_persistence
    )


def test_build_returns_aguiapp_with_a_compiled_graph(tmp_path, monkeypatch):
    # init_chat_model constructs a real ChatOpenAI client at build time (it
    # doesn't call out to the network to do so, but it does require an
    # api_key to be present) — this test never invokes the graph, so a dummy
    # key is enough to let assembly (create_agent(...)) complete.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    calls = _stub_no_mcp_discovery(monkeypatch)
    _stub_no_persistence_resolution(monkeypatch)

    ctx = _build_ctx(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)

    app = asyncio.run(LangChainRuntime().build(ctx, hooks))

    assert isinstance(app, AGUIApp)
    assert app.graph is not None
    assert hasattr(app.graph, "ainvoke")
    assert hasattr(app.graph, "invoke")
    assert calls["n"] == 0  # no eager MCP discovery at build (lazy)


def test_attach_registers_the_agui_route(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    _stub_no_mcp_discovery(monkeypatch)
    _stub_no_persistence_resolution(monkeypatch)

    ctx = _build_ctx(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    app = asyncio.run(LangChainRuntime().build(ctx, hooks))

    fastapi_app = FastAPI()
    app.attach(fastapi_app, path="/agui")

    paths = {route.path for route in fastapi_app.routes}
    assert "/agui" in paths
    assert "/agui/health" in paths
