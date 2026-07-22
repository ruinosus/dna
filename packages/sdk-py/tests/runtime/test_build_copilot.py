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

    # mcp_url is unreachable in this test (no live DNA MCP endpoint) — stub
    # load_mcp_tools so the test verifies ASSEMBLY (config derivation +
    # middleware stack + create_agent compiles), not a live MCP round-trip.
    async def fake_load_mcp_tools(mcp_url, auth):
        return []

    monkeypatch.setattr(
        "dna.runtime.builder.load_mcp_tools", fake_load_mcp_tools
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
