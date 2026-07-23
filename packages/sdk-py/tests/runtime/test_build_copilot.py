import asyncio
import shutil
from pathlib import Path

from dna.runtime.builder import build_copilot

# Committed fixture (this repo), NOT the sibling dna-cloud repo — must pass on
# a fresh clone with no dna-cloud checkout present.
FIXTURE_SRC = Path(__file__).parent / "fixtures" / "dna" / "dna-cloud-dev"


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / ".dna" / "dna-cloud-dev"
    dest.mkdir(parents=True)
    for subdir in ("copilots", "agents", "federations", "tools"):
        shutil.copytree(FIXTURE_SRC / subdir, dest / subdir)
    return tmp_path / ".dna"


def test_build_copilot_compiles_with_the_dna_stack(tmp_path, monkeypatch):
    base_dir = _copy_fixture(tmp_path)

    # init_chat_model constructs a real ChatOpenAI client at build time (it
    # doesn't call out to the network to do so, but it does require an
    # api_key to be present) — this test never invokes the graph, so a dummy
    # key is enough to let assembly (create_agent(...)) complete.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")

    # MCP discovery is now LAZY (DnaMcpToolsMiddleware, first model call), so
    # build makes no MCP round-trip and needs no stub — mcp_url stays unreachable
    # and build must still compile. We stub load_mcp_tools defensively and assert
    # it is NOT touched at build time (the discovery moved off the boot path).
    calls = {"n": 0}

    async def fake_load_mcp_tools(mcp_url, auth):
        calls["n"] += 1
        return []

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", fake_load_mcp_tools
    )

    # The fixture's memory-copilot declares `persistence.{checkpoint,memory}`
    # on Postgres (ref `primary-pg`) — since these callers pass no
    # `hooks.checkpointer`, the adapter now resolves it declaratively
    # (Task 4). Stub the resolver so this parity test stays a pure
    # in-process build with no real Postgres — `resolve_persistence`'s own
    # DSN/env-var behavior is covered by test_declarative_config.py.
    async def fake_resolve_persistence(_persistence):
        return None, None

    monkeypatch.setattr(
        "dna.runtime.persistence.resolve_persistence", fake_resolve_persistence
    )

    async def compose(_):
        return "PROMPT"

    graph = asyncio.run(
        build_copilot(
            "memory-copilot",
            base_dir=str(base_dir),
            scope="dna-cloud-dev",
            mcp_url="http://127.0.0.1:9/mcp",
            mcp_auth=lambda: {},
            compose=compose,
            extra_tools=[],
            extra_middleware=[],
        )
    )
    assert graph is not None
    assert hasattr(graph, "ainvoke")
    assert calls["n"] == 0  # no eager MCP discovery at build (lazy now)
