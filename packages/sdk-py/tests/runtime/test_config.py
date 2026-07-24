import asyncio
import shutil
from pathlib import Path

from dna.runtime.config import copilot_config

# Committed fixture (this repo), NOT the sibling dna-cloud repo — must pass on
# a fresh clone with no dna-cloud checkout present.
FIXTURE_SRC = Path(__file__).parent / "fixtures" / "dna" / "dna-cloud-dev"


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / ".dna" / "dna-cloud-dev"
    dest.mkdir(parents=True)
    for subdir in ("copilots", "agents", "federations", "tools"):
        shutil.copytree(FIXTURE_SRC / subdir, dest / subdir)
    return tmp_path / ".dna"


def test_derives_allowlist_model_confirm_from_def(tmp_path):
    # Uses the committed dna-cloud-dev-shaped fixture (copy the memory-copilot
    # + memory-agent + dna-mcp federation + tool docs into tmp_path/.dna).
    base_dir = _copy_fixture(tmp_path)
    # copilot_config is async now (reads the def from the env-configured source;
    # base_dir is the filesystem fallback used here). Drive it with asyncio.run,
    # the same pattern test_build_copilot.py uses.
    cfg = asyncio.run(
        copilot_config("memory-copilot", base_dir=str(base_dir), scope="dna-cloud-dev")
    )
    assert cfg.model == "gpt-5-mini"
    # config.py sorts `confirm_tools` at the source (dna.emit._project_hitl_intent
    # returns a set, so raw iteration order is not stable across process
    # invocations / hash randomization).
    assert cfg.confirm_tools == ("consolidate", "forget", "remember")
    # `list` (Tool-doc alias) expands to the runtime name `list_memories`:
    assert cfg.allowed_tools == frozenset(
        {"consolidate", "forget", "list", "list_memories", "recall", "remember"}
    )
    assert "compositor" in cfg.instructions.lower()
